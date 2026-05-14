#!/usr/bin/env python3
"""SimGrid-style collective communication simulator for Crux scheduling.

This script models a multi-host, multi-card training cluster with actors,
hosts, links, point-to-point flows, and Ring AllReduce dependencies.  It does
not require SimGrid at runtime in this workspace, but the abstractions map
directly to a SimGrid S4U implementation:

- Host/GPU compute -> Actor::execute(flops)
- Flow over a path -> Mailbox::put/get(bytes) over platform routes
- Network contention -> shared links with weighted fair sharing
- Training job actor -> iteration loop with compute + collective

The goal is to validate the Crux paper's path-selection and priority ideas on
collective communication competition before wiring the model to real SimGrid.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean


Link = tuple[str, str]
PathLinks = tuple[Link, ...]


def edge(a: str, b: str) -> Link:
    return (a, b) if a <= b else (b, a)


@dataclass
class TrainJob:
    jid: int
    model: str
    gpu_count: int
    hosts: tuple[int, ...]
    compute_time: float
    tensor_bytes: float
    overlap_ratio: float
    iterations: int = 1
    intensity: float = 0.0
    logical_priority: float = 0.0
    hw_priority: int = 0
    selected_dsw: int | None = None
    finish_time: float = 0.0
    comm_time: float = 0.0
    compute_done_time: float = 0.0

    @property
    def sensitivity(self) -> float:
        return max(0.05, 1.0 - self.overlap_ratio)


@dataclass
class Cluster:
    hosts: int
    gpus_per_host: int
    asw_count: int
    psw_count: int
    dsw_count: int
    host_asw_bw: float
    asw_psw_bw: float
    psw_dsw_bw: float
    intra_host_bw: float
    latency: float

    def asw(self, host: int) -> int:
        return host // max(1, math.ceil(self.hosts / self.asw_count))

    def psw(self, host: int) -> int:
        return self.asw(host) // max(1, math.ceil(self.asw_count / self.psw_count))

    def path(self, src_host: int, dst_host: int, dsw_choice: int | None) -> PathLinks:
        if src_host == dst_host:
            return (edge(f"h{src_host}:gpu", f"h{src_host}:pcie"),)

        src_asw, dst_asw = self.asw(src_host), self.asw(dst_host)
        src_psw, dst_psw = self.psw(src_host), self.psw(dst_host)
        links: list[Link] = [edge(f"h{src_host}", f"asw{src_asw}")]
        if src_asw == dst_asw:
            links.append(edge(f"asw{dst_asw}", f"h{dst_host}"))
            return tuple(links)

        links.append(edge(f"asw{src_asw}", f"psw{src_psw}"))
        if src_psw != dst_psw:
            dsw = 0 if dsw_choice is None else dsw_choice
            links.append(edge(f"psw{src_psw}", f"dsw{dsw}"))
            links.append(edge(f"dsw{dsw}", f"psw{dst_psw}"))
        links.append(edge(f"psw{dst_psw}", f"asw{dst_asw}"))
        links.append(edge(f"asw{dst_asw}", f"h{dst_host}"))
        return tuple(links)

    def link_bw(self, link: Link) -> float:
        a, b = link
        joined = f"{a}-{b}"
        if ":pcie" in joined:
            return self.intra_host_bw
        if "dsw" in joined:
            return self.psw_dsw_bw
        if "psw" in joined:
            return self.asw_psw_bw
        return self.host_asw_bw


@dataclass
class Flow:
    fid: int
    job_id: int
    step_id: int
    src_rank: int
    dst_rank: int
    remaining: float
    links: PathLinks
    priority: int
    start_time: float
    end_time: float | None = None

    @property
    def weight(self) -> float:
        # Approximate hardware priority queues with weighted fair sharing.
        # Keep the ratio moderate; otherwise an "ideal" many-level priority
        # experiment unrealistically starves low-priority collectives.
        return 1.0 + 0.5 * float(self.priority)


@dataclass(order=True)
class Event:
    time: float
    seq: int
    kind: str = field(compare=False)
    job_id: int = field(compare=False)


def model_template(rng: random.Random) -> tuple[str, int, float, float, float]:
    templates = [
        ("ResNet", 8, 0.80, 0.7 * 1024**3, 0.70),
        ("BERT", 16, 1.20, 1.6 * 1024**3, 0.48),
        ("GPT", 32, 1.80, 3.6 * 1024**3, 0.30),
        ("GPT-large", 64, 2.60, 7.5 * 1024**3, 0.18),
    ]
    return rng.choices(templates, weights=[0.40, 0.35, 0.18, 0.07], k=1)[0]


def make_jobs(seed: int, count: int, cluster: Cluster) -> list[TrainJob]:
    rng = random.Random(seed)
    jobs: list[TrainJob] = []
    for jid in range(count):
        model, gpus, compute, tensor, overlap = model_template(rng)
        gpus = min(gpus, cluster.hosts * cluster.gpus_per_host)
        host_count = max(1, math.ceil(gpus / cluster.gpus_per_host))
        if rng.random() < 0.50 and host_count > 1:
            hosts = tuple(sorted(rng.sample(range(cluster.hosts), host_count)))
        else:
            start = rng.randrange(0, cluster.hosts - host_count + 1)
            hosts = tuple(range(start, start + host_count))
        compute *= rng.uniform(0.90, 1.12)
        tensor *= rng.uniform(0.85, 1.20)
        overlap = max(0.0, min(0.9, overlap + rng.uniform(-0.07, 0.07)))
        # Isolated ring allreduce approximation: 2*(n-1)/n bytes per rank.
        isolated_comm = (2.0 * (gpus - 1) / max(1, gpus)) * tensor / cluster.host_asw_bw
        job = TrainJob(
            jid=jid,
            model=model,
            gpu_count=gpus,
            hosts=hosts,
            compute_time=compute,
            tensor_bytes=tensor,
            overlap_ratio=overlap,
        )
        job.intensity = (gpus * compute) / max(isolated_comm * job.sensitivity, 1e-9)
        jobs.append(job)
    return jobs


def rank_hosts(job: TrainJob, cluster: Cluster) -> list[int]:
    ranks: list[int] = []
    for host in job.hosts:
        for _ in range(cluster.gpus_per_host):
            if len(ranks) < job.gpu_count:
                ranks.append(host)
    return ranks


def assign_random_paths(jobs: list[TrainJob], cluster: Cluster, rng: random.Random) -> None:
    for job in jobs:
        job.selected_dsw = rng.randrange(cluster.dsw_count)


def assign_crux_paths(jobs: list[TrainJob], cluster: Cluster) -> None:
    link_load: dict[Link, float] = {}
    for job in sorted(jobs, key=lambda j: j.intensity, reverse=True):
        best_dsw = 0
        best_cost = float("inf")
        ranks = rank_hosts(job, cluster)
        traffic = job.tensor_bytes * job.intensity
        for dsw in range(cluster.dsw_count):
            links: set[Link] = set()
            for i, src in enumerate(ranks):
                dst = ranks[(i + 1) % len(ranks)]
                links.update(cluster.path(src, dst, dsw))
            cost = sum(link_load.get(l, 0.0) for l in links)
            if cost < best_cost:
                best_cost = cost
                best_dsw = dsw
        job.selected_dsw = best_dsw
        for i, src in enumerate(ranks):
            dst = ranks[(i + 1) % len(ranks)]
            for link in cluster.path(src, dst, best_dsw):
                link_load[link] = link_load.get(link, 0.0) + traffic


def assign_logical_priorities(jobs: list[TrainJob], mode: str) -> None:
    for job in jobs:
        if mode == "same":
            job.logical_priority = 1.0
        elif mode == "intensity":
            job.logical_priority = job.intensity
        elif mode == "crux":
            correction = job.sensitivity * (1.0 + 1.0 / (job.compute_time + 1e-6))
            job.logical_priority = job.intensity * correction
        else:
            raise ValueError(mode)


def flat_compress_priorities(jobs: list[TrainJob], levels: int) -> None:
    ordered = sorted(jobs, key=lambda j: j.logical_priority, reverse=True)
    for rank, job in enumerate(ordered):
        job.hw_priority = max(0, levels - 1 - (rank * levels // max(1, len(ordered))))


def contention_dag(jobs: list[TrainJob], cluster: Cluster) -> dict[int, dict[int, float]]:
    dag: dict[int, dict[int, float]] = {j.jid: {} for j in jobs}
    link_sets: dict[int, set[Link]] = {}
    for job in jobs:
        ranks = rank_hosts(job, cluster)
        links: set[Link] = set()
        for i, src in enumerate(ranks):
            dst = ranks[(i + 1) % len(ranks)]
            links.update(cluster.path(src, dst, job.selected_dsw))
        link_sets[job.jid] = links
    for i, a in enumerate(jobs):
        for b in jobs[i + 1 :]:
            if not link_sets[a.jid].intersection(link_sets[b.jid]):
                continue
            hi, lo = (a, b) if a.logical_priority >= b.logical_priority else (b, a)
            if hi.logical_priority != lo.logical_priority:
                dag[hi.jid][lo.jid] = hi.intensity
    return dag


def random_topological_order(dag: dict[int, dict[int, float]], rng: random.Random) -> list[int]:
    indeg = {u: 0 for u in dag}
    for outs in dag.values():
        for v in outs:
            indeg[v] += 1
    ready = [u for u, d in indeg.items() if d == 0]
    order: list[int] = []
    while ready:
        u = ready.pop(rng.randrange(len(ready)))
        order.append(u)
        for v in dag[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
    return order


def cut_value(order: list[int], cuts: list[int], dag: dict[int, dict[int, float]]) -> float:
    group: dict[int, int] = {}
    start = 0
    for g, end in enumerate(cuts):
        for u in order[start:end]:
            group[u] = g
        start = end
    return sum(w for u, outs in dag.items() for v, w in outs.items() if group[u] < group[v])


def best_sequence_cut(order: list[int], k: int, dag: dict[int, dict[int, float]]) -> list[int]:
    n = len(order)
    if k >= n:
        return list(range(1, n + 1))
    best_score = -1.0
    best_cuts = [n]

    def rec(prev: int, groups_left: int, cuts: list[int]) -> None:
        nonlocal best_score, best_cuts
        if groups_left == 1:
            candidate = cuts + [n]
            score = cut_value(order, candidate, dag)
            if score > best_score:
                best_score = score
                best_cuts = candidate
            return
        for end in range(prev + 1, n - groups_left + 2):
            rec(end, groups_left - 1, cuts + [end])

    rec(0, k, [])
    return best_cuts


def compress_priorities(jobs: list[TrainJob], cluster: Cluster, levels: int, rng: random.Random) -> None:
    if levels <= 1:
        for job in jobs:
            job.hw_priority = 0
        return
    dag = contention_dag(jobs, cluster)
    best_order: list[int] | None = None
    best_cuts: list[int] | None = None
    best_score = -1.0
    for _ in range(10):
        order = random_topological_order(dag, rng)
        cuts = best_sequence_cut(order, min(levels, len(jobs)), dag)
        score = cut_value(order, cuts, dag)
        if score > best_score:
            best_order, best_cuts, best_score = order, cuts, score
    assert best_order is not None and best_cuts is not None
    by_id = {j.jid: j for j in jobs}
    start = 0
    for group_id, end in enumerate(best_cuts):
        prio = levels - group_id - 1
        for jid in best_order[start:end]:
            by_id[jid].hw_priority = prio
        start = end


class CollectiveSimulator:
    def __init__(self, cluster: Cluster, jobs: list[TrainJob]):
        self.cluster = cluster
        self.jobs = {j.jid: j for j in jobs}
        self.time = 0.0
        self.seq = 0
        self.events: list[Event] = []
        self.active: dict[int, Flow] = {}
        self.step_expected: dict[tuple[int, int], int] = {}
        self.step_done: dict[tuple[int, int], int] = {}
        self.next_fid = 0

    def push(self, time: float, kind: str, job_id: int) -> None:
        self.seq += 1
        heapq.heappush(self.events, Event(time, self.seq, kind, job_id))

    def ring_step_flows(self, job: TrainJob, step: int) -> list[Flow]:
        ranks = rank_hosts(job, self.cluster)
        n = len(ranks)
        # We do not explicitly simulate compute/communication overlap in this
        # first model.  Instead, only the non-hidden part of communication is
        # placed on the critical path.
        chunk = (job.tensor_bytes * job.sensitivity) / n
        flows: list[Flow] = []
        for r, src_host in enumerate(ranks):
            dst_host = ranks[(r + 1) % n]
            links = self.cluster.path(src_host, dst_host, job.selected_dsw)
            self.next_fid += 1
            flows.append(
                Flow(
                    fid=self.next_fid,
                    job_id=job.jid,
                    step_id=step,
                    src_rank=r,
                    dst_rank=(r + 1) % n,
                    remaining=chunk,
                    links=links,
                    priority=job.hw_priority,
                    start_time=self.time,
                )
            )
        return flows

    def start_step(self, job_id: int, step: int) -> None:
        job = self.jobs[job_id]
        total_steps = 2 * (job.gpu_count - 1)
        if step >= total_steps:
            job.finish_time = self.time
            job.comm_time = job.finish_time - job.compute_done_time
            return
        flows = self.ring_step_flows(job, step)
        self.step_expected[(job_id, step)] = len(flows)
        self.step_done[(job_id, step)] = 0
        for flow in flows:
            self.active[flow.fid] = flow

    def rates(self) -> dict[int, float]:
        rates = {fid: float("inf") for fid in self.active}
        users_by_link: dict[Link, list[Flow]] = {}
        for flow in self.active.values():
            for link in flow.links:
                users_by_link.setdefault(link, []).append(flow)
        for link, users in users_by_link.items():
            cap = self.cluster.link_bw(link)
            total_weight = sum(f.weight for f in users)
            for flow in users:
                rates[flow.fid] = min(rates[flow.fid], cap * flow.weight / total_weight)
        return rates

    def advance_to_next_completion(self) -> None:
        if not self.active:
            return
        rates = self.rates()
        dt = min(flow.remaining / rates[fid] for fid, flow in self.active.items())
        if dt < self.cluster.latency:
            dt += self.cluster.latency
        for fid, flow in list(self.active.items()):
            flow.remaining -= rates[fid] * dt
        self.time += dt
        finished = [fid for fid, f in self.active.items() if f.remaining <= 1e-3]
        for fid in finished:
            flow = self.active.pop(fid)
            key = (flow.job_id, flow.step_id)
            self.step_done[key] += 1
            if self.step_done[key] == self.step_expected[key]:
                self.start_step(flow.job_id, flow.step_id + 1)

    def run(self) -> None:
        for job in self.jobs.values():
            compute_done = job.compute_time
            job.compute_done_time = compute_done
            self.push(compute_done, "start_comm", job.jid)
        while self.events or self.active:
            if not self.active and self.events:
                ev = heapq.heappop(self.events)
                self.time = max(self.time, ev.time)
                if ev.kind == "start_comm":
                    self.start_step(ev.job_id, 0)
                continue
            if self.events and self.events[0].time < self.time:
                ev = heapq.heappop(self.events)
                if ev.kind == "start_comm":
                    self.start_step(ev.job_id, 0)
                continue
            self.advance_to_next_completion()
            while self.events and self.events[0].time <= self.time:
                ev = heapq.heappop(self.events)
                if ev.kind == "start_comm":
                    self.start_step(ev.job_id, 0)


def run_scheduler(base_jobs: list[TrainJob], scheduler: str, cluster: Cluster, seed: int, levels: int) -> dict[str, float]:
    import copy

    jobs = copy.deepcopy(base_jobs)
    rng = random.Random(seed)
    if scheduler == "random_same":
        assign_random_paths(jobs, cluster, rng)
        assign_logical_priorities(jobs, "same")
        for job in jobs:
            job.hw_priority = 0
    elif scheduler == "random_intensity":
        assign_random_paths(jobs, cluster, rng)
        assign_logical_priorities(jobs, "intensity")
        flat_compress_priorities(jobs, levels)
    elif scheduler == "crux_no_compress":
        assign_crux_paths(jobs, cluster)
        assign_logical_priorities(jobs, "crux")
        flat_compress_priorities(jobs, max(levels, len(jobs)))
    elif scheduler == "crux":
        assign_crux_paths(jobs, cluster)
        assign_logical_priorities(jobs, "crux")
        compress_priorities(jobs, cluster, levels, rng)
    else:
        raise ValueError(scheduler)

    sim = CollectiveSimulator(cluster, jobs)
    sim.run()
    finished = list(sim.jobs.values())
    allocated = sum(j.gpu_count for j in finished)
    useful = sum(j.gpu_count * j.compute_time / j.finish_time for j in finished)
    ranked = sorted(finished, key=lambda j: j.intensity)
    q = max(1, len(ranked) // 4)
    low = ranked[:q]
    high = ranked[-q:]
    return {
        "gpu_util": useful / allocated,
        "avg_iter_time": mean(j.finish_time for j in finished),
        "avg_comm_time": mean(j.comm_time for j in finished),
        "high_intensity_jct": mean(j.finish_time for j in high),
        "low_intensity_jct": mean(j.finish_time for j in low),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--jobs", type=int, default=24)
    parser.add_argument("--hosts", type=int, default=16)
    parser.add_argument("--gpus-per-host", type=int, default=8)
    parser.add_argument("--asw", type=int, default=8)
    parser.add_argument("--psw", type=int, default=4)
    parser.add_argument("--dsw", type=int, default=4)
    parser.add_argument("--priority-levels", type=int, default=4)
    parser.add_argument("--host-asw-gbps", type=float, default=200.0)
    parser.add_argument("--asw-psw-gbps", type=float, default=400.0)
    parser.add_argument("--psw-dsw-gbps", type=float, default=800.0)
    parser.add_argument("--intra-host-gbps", type=float, default=600.0)
    parser.add_argument("--latency-us", type=float, default=8.0)
    parser.add_argument("--out", type=Path, default=Path("crux_repro/results/simgrid_collective_results.csv"))
    args = parser.parse_args()

    gbps = 1024**3 / 8.0
    cluster = Cluster(
        hosts=args.hosts,
        gpus_per_host=args.gpus_per_host,
        asw_count=args.asw,
        psw_count=args.psw,
        dsw_count=args.dsw,
        host_asw_bw=args.host_asw_gbps * gbps,
        asw_psw_bw=args.asw_psw_gbps * gbps,
        psw_dsw_bw=args.psw_dsw_gbps * gbps,
        intra_host_bw=args.intra_host_gbps * gbps,
        latency=args.latency_us / 1_000_000.0,
    )
    schedulers = ["random_same", "random_intensity", "crux_no_compress", "crux"]
    rows: list[dict[str, str | float | int]] = []
    for r in range(args.rounds):
        jobs = make_jobs(args.seed + r, args.jobs, cluster)
        for scheduler in schedulers:
            metrics = run_scheduler(jobs, scheduler, cluster, args.seed * 1000 + r, args.priority_levels)
            rows.append({"round": r, "scheduler": scheduler, **metrics})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        fields = ["round", "scheduler", "gpu_util", "avg_iter_time", "avg_comm_time", "high_intensity_jct", "low_intensity_jct"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    baseline = mean(float(r["gpu_util"]) for r in rows if r["scheduler"] == "random_same")
    print("scheduler           gpu_util   avg_iter   avg_comm   high_int_jct   low_int_jct   util_gain_vs_random")
    for scheduler in schedulers:
        subset = [r for r in rows if r["scheduler"] == scheduler]
        util = mean(float(r["gpu_util"]) for r in subset)
        gain = (util / baseline - 1.0) * 100.0
        print(
            f"{scheduler:18s} {util:8.4f}"
            f" {mean(float(r['avg_iter_time']) for r in subset):10.4f}"
            f" {mean(float(r['avg_comm_time']) for r in subset):9.4f}"
            f" {mean(float(r['high_intensity_jct']) for r in subset):14.4f}"
            f" {mean(float(r['low_intensity_jct']) for r in subset):13.4f}"
            f" {gain:17.2f}%"
        )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
