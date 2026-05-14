#!/usr/bin/env python3
"""Small offline simulator for the Crux paper's core scheduling idea.

The simulator is intentionally compact and dependency-light. It models a
two-layer Clos-like cluster, synthetic DLT jobs, and a simple communication
contention model. The goal is to reproduce the Crux mechanism qualitatively,
not to match the paper's production numbers.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean


Link = tuple[str, str]
PathLinks = tuple[Link, ...]


@dataclass
class Job:
    jid: int
    model: str
    gpu_count: int
    hosts: tuple[int, ...]
    compute_work: float
    base_compute_time: float
    base_comm_time: float
    overlap_ratio: float
    traffic: float
    candidate_paths: tuple[PathLinks, ...]
    selected_path: PathLinks | None = None
    intensity: float = 0.0
    logical_priority: float = 0.0
    hw_priority: int = 0

    @property
    def sensitivity(self) -> float:
        """How much communication delay escapes compute/comm overlap."""
        return max(0.05, 1.0 - self.overlap_ratio)


@dataclass(frozen=True)
class TraceJob:
    job_name: str
    model: str
    start_ts: float
    end_ts: float
    gpu_count: int
    host_ips: tuple[str, ...]
    duration_minutes: float


@dataclass(frozen=True)
class HostTopo:
    host_id: int
    asw: str
    psw: str
    dsw: str


@dataclass
class RoundResult:
    round_id: int
    scheduler: str
    gpu_util: float
    avg_iter_time: float
    high_intensity_jct: float
    low_intensity_jct: float


def edge(a: str, b: str) -> Link:
    return (a, b) if a <= b else (b, a)


def build_candidate_paths(hosts: tuple[int, ...], aggs: int) -> tuple[PathLinks, ...]:
    """Return candidate inter-host paths for a job's dominant communication."""
    if len(hosts) == 1:
        h = hosts[0]
        return ((edge(f"h{h}:gpu", f"h{h}:pcie"),),)

    src, dst = hosts[0], hosts[-1]
    src_tor, dst_tor = src // 4, dst // 4
    paths: list[PathLinks] = []
    for a in range(aggs):
        paths.append(
            (
                edge(f"h{src}", f"tor{src_tor}"),
                edge(f"tor{src_tor}", f"agg{a}"),
                edge(f"agg{a}", f"tor{dst_tor}"),
                edge(f"tor{dst_tor}", f"h{dst}"),
            )
        )
    return tuple(paths)


def build_trace_candidate_paths(
    host_ips: tuple[str, ...],
    topo: dict[str, HostTopo],
    dsw_choices: tuple[str, ...],
) -> tuple[PathLinks, ...]:
    """Return ECMP-like paths using the Lingjun ASW/PSW/DSW topology labels."""
    if len(host_ips) == 1:
        h = topo[host_ips[0]].host_id
        return ((edge(f"h{h}:gpu", f"h{h}:pcie"),),)

    src_ip, dst_ip = host_ips[0], host_ips[-1]
    src, dst = topo[src_ip], topo[dst_ip]
    if src.asw == dst.asw:
        return (
            (
                edge(f"h{src.host_id}", f"asw:{src.asw}"),
                edge(f"asw:{src.asw}", f"h{dst.host_id}"),
            ),
        )
    if src.psw == dst.psw:
        return (
            (
                edge(f"h{src.host_id}", f"asw:{src.asw}"),
                edge(f"asw:{src.asw}", f"psw:{src.psw}"),
                edge(f"psw:{src.psw}", f"asw:{dst.asw}"),
                edge(f"asw:{dst.asw}", f"h{dst.host_id}"),
            ),
        )

    choices = dsw_choices or (src.dsw,)
    paths: list[PathLinks] = []
    for dsw in choices:
        paths.append(
            (
                edge(f"h{src.host_id}", f"asw:{src.asw}"),
                edge(f"asw:{src.asw}", f"psw:{src.psw}"),
                edge(f"psw:{src.psw}", f"dsw:{dsw}"),
                edge(f"dsw:{dsw}", f"psw:{dst.psw}"),
                edge(f"psw:{dst.psw}", f"asw:{dst.asw}"),
                edge(f"asw:{dst.asw}", f"h{dst.host_id}"),
            )
        )
    return tuple(paths)


def parse_lingjun_time(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).timestamp()
        except ValueError:
            pass
    return None


def model_profile(model: str, gpu_count: int) -> tuple[str, float, float, float, float]:
    name = (model or "unknown").lower()
    if "resnet" in name:
        return ("ResNet", 0.85, 0.22, 0.72, 1.0)
    if "bert" in name:
        return ("BERT", 1.20, 0.45, 0.48, 2.7)
    if "gpt" in name or "llama" in name or "llm" in name or "large" in name:
        if gpu_count >= 24:
            return ("GPT-large", 2.30, 1.55, 0.18, 14.0)
        return ("GPT", 1.80, 0.95, 0.28, 7.2)
    if gpu_count >= 24:
        return ("unknown-large", 2.10, 1.35, 0.22, 10.0)
    if gpu_count >= 12:
        return ("unknown-mid", 1.60, 0.75, 0.35, 5.0)
    if gpu_count >= 8:
        return ("unknown-8gpu", 1.20, 0.45, 0.48, 2.7)
    return ("unknown-small", 0.85, 0.24, 0.65, 1.2)


def read_lingjun_trace(data_dir: Path) -> tuple[list[TraceJob], dict[str, HostTopo]]:
    topo_path = data_dir / "topo.csv"
    job_path = data_dir / "job.csv"
    worker_path = data_dir / "worker.csv"
    for path in (topo_path, job_path, worker_path):
        if not path.exists():
            raise FileNotFoundError(f"missing Lingjun dataset file: {path}")

    topo: dict[str, HostTopo] = {}
    with topo_path.open(newline="") as f:
        for idx, row in enumerate(csv.DictReader(f)):
            ip = row.get("ip", "").strip()
            if ip:
                topo[ip] = HostTopo(idx, row.get("ASW", ""), row.get("PSW", ""), row.get("DSW", ""))

    jobs_meta: dict[str, tuple[str, float, float]] = {}
    with job_path.open(newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("job_name", "").strip()
            start = parse_lingjun_time(row.get("gmt_job_running", ""))
            end = (
                parse_lingjun_time(row.get("gmt_job_finished", ""))
                or parse_lingjun_time(row.get("gmt_job_stopped", ""))
            )
            if not name or start is None or end is None or end <= start:
                continue
            jobs_meta[name] = (row.get("model", "unknown").strip() or "unknown", start, end)

    workers: dict[str, dict[str, int]] = {}
    with worker_path.open(newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("job_name", "").strip()
            host_ip = row.get("host_ip", "").strip()
            if not name or host_ip not in topo:
                continue
            try:
                res = json.loads(row.get("RES", "{}") or "{}")
            except json.JSONDecodeError:
                res = {}
            gpu_count = int(float(res.get("nvidia.com/gpu", 0) or 0))
            if gpu_count <= 0:
                continue
            workers.setdefault(name, {})
            workers[name][host_ip] = workers[name].get(host_ip, 0) + gpu_count

    trace_jobs: list[TraceJob] = []
    for name, (model, start, end) in jobs_meta.items():
        host_gpu = workers.get(name)
        if not host_gpu:
            continue
        host_ips = tuple(sorted(host_gpu, key=lambda ip: topo[ip].host_id))
        gpu_count = sum(host_gpu.values())
        trace_jobs.append(
            TraceJob(
                job_name=name,
                model=model,
                start_ts=start,
                end_ts=end,
                gpu_count=gpu_count,
                host_ips=host_ips,
                duration_minutes=(end - start) / 60.0,
            )
        )
    return trace_jobs, topo


def make_jobs(seed: int, count: int, hosts: int, aggs: int) -> list[Job]:
    rng = random.Random(seed)
    templates = [
        # model, gpus, compute_time, comm_time, overlap, work_scale
        ("ResNet", 4, 0.85, 0.22, 0.72, 1.0),
        ("BERT", 8, 1.20, 0.45, 0.48, 2.7),
        ("GPT", 16, 1.80, 0.95, 0.28, 7.2),
        ("GPT-large", 32, 2.30, 1.55, 0.18, 14.0),
    ]
    jobs: list[Job] = []
    for jid in range(count):
        model, gpus, comp, comm, overlap, work = rng.choices(
            templates, weights=[0.42, 0.34, 0.18, 0.06], k=1
        )[0]
        host_count = max(1, min(hosts, (gpus + 7) // 8))
        start = rng.randrange(0, hosts - host_count + 1)
        # Add some scatter so jobs collide on aggregation links.
        if rng.random() < 0.45 and host_count > 1:
            chosen = tuple(sorted(rng.sample(range(hosts), host_count)))
        else:
            chosen = tuple(range(start, start + host_count))
        jitter = rng.uniform(0.85, 1.15)
        traffic = comm * rng.uniform(0.85, 1.25)
        job = Job(
            jid=jid,
            model=model,
            gpu_count=gpus,
            hosts=chosen,
            compute_work=work * gpus * jitter,
            base_compute_time=comp * rng.uniform(0.9, 1.1),
            base_comm_time=comm * rng.uniform(0.9, 1.15),
            overlap_ratio=max(0.0, min(0.9, overlap + rng.uniform(-0.08, 0.08))),
            traffic=traffic,
            candidate_paths=build_candidate_paths(chosen, aggs),
        )
        job.intensity = job.compute_work / job.base_comm_time
        jobs.append(job)
    return jobs


def make_lingjun_jobs(seed: int, count: int, data_dir: Path, aggs: int) -> list[Job]:
    rng = random.Random(seed)
    trace_jobs, topo = read_lingjun_trace(data_dir)
    if not trace_jobs:
        raise ValueError(f"no usable GPU jobs found in {data_dir}")

    starts = sorted({j.start_ts for j in trace_jobs})
    # Pick a real job start time and replay the jobs that were concurrently running.
    # This keeps the host placement and overlap structure from the trace.
    snapshot_ts = rng.choice(starts)
    active = [j for j in trace_jobs if j.start_ts <= snapshot_ts < j.end_ts]
    if len(active) < min(count, 4):
        active = sorted(trace_jobs, key=lambda j: abs(j.start_ts - snapshot_ts))[: max(count, len(active))]
    if len(active) > count:
        active = rng.sample(active, count)

    dsw_choices = tuple(sorted({h.dsw for h in topo.values() if h.dsw}))[: max(1, aggs)]
    jobs: list[Job] = []
    for jid, rec in enumerate(sorted(active, key=lambda j: (j.start_ts, j.job_name))):
        model, comp, comm, overlap, work = model_profile(rec.model, rec.gpu_count)
        duration_factor = max(0.75, min(2.5, rec.duration_minutes / 720.0))
        gpu_factor = max(1.0, rec.gpu_count / 8.0)
        jitter = rng.uniform(0.9, 1.1)
        base_compute = comp * (0.85 + 0.15 * gpu_factor) * jitter
        base_comm = comm * (1.0 + 0.08 * max(0, len(rec.host_ips) - 1)) * rng.uniform(0.9, 1.15)
        traffic = base_comm * max(1.0, rec.gpu_count / 8.0) * rng.uniform(0.9, 1.1)
        job = Job(
            jid=jid,
            model=model,
            gpu_count=rec.gpu_count,
            hosts=tuple(topo[ip].host_id for ip in rec.host_ips),
            compute_work=work * rec.gpu_count * duration_factor * jitter,
            base_compute_time=base_compute,
            base_comm_time=base_comm,
            overlap_ratio=max(0.0, min(0.9, overlap + rng.uniform(-0.06, 0.06))),
            traffic=traffic,
            candidate_paths=build_trace_candidate_paths(rec.host_ips, topo, dsw_choices),
        )
        job.intensity = job.compute_work / job.base_comm_time
        jobs.append(job)
    return jobs


def assign_random_paths(jobs: list[Job], rng: random.Random) -> None:
    for job in jobs:
        job.selected_path = rng.choice(job.candidate_paths)


def assign_crux_paths(jobs: list[Job]) -> None:
    link_load: dict[Link, float] = {}
    for job in sorted(jobs, key=lambda j: j.intensity, reverse=True):
        best_path = min(
            job.candidate_paths,
            key=lambda p: (sum(link_load.get(l, 0.0) for l in p), len(p)),
        )
        job.selected_path = best_path
        for link in best_path:
            link_load[link] = link_load.get(link, 0.0) + job.traffic * job.intensity


def assign_logical_priorities(jobs: list[Job], mode: str) -> None:
    for job in jobs:
        if mode == "same":
            job.logical_priority = 1.0
        elif mode == "intensity":
            job.logical_priority = job.intensity
        elif mode == "crux":
            # A compact proxy for the paper's correction factor: jobs with shorter
            # exposed communication and less overlap become more urgent.
            correction = job.sensitivity * (1.0 + 1.0 / (job.base_compute_time + job.base_comm_time))
            job.logical_priority = job.intensity * correction
        else:
            raise ValueError(mode)


def contention_dag(jobs: list[Job]) -> dict[int, dict[int, float]]:
    dag: dict[int, dict[int, float]] = {j.jid: {} for j in jobs}
    by_id = {j.jid: j for j in jobs}
    for i, a in enumerate(jobs):
        assert a.selected_path is not None
        links_a = set(a.selected_path)
        for b in jobs[i + 1 :]:
            assert b.selected_path is not None
            if not links_a.intersection(b.selected_path):
                continue
            hi, lo = (a, b) if a.logical_priority >= b.logical_priority else (b, a)
            if hi.logical_priority == lo.logical_priority:
                continue
            dag[hi.jid][lo.jid] = by_id[hi.jid].intensity
    return dag


def random_topological_order(dag: dict[int, dict[int, float]], rng: random.Random) -> list[int]:
    indeg = {u: 0 for u in dag}
    for outs in dag.values():
        for v in outs:
            indeg[v] += 1
    ready = [u for u, d in indeg.items() if d == 0]
    order: list[int] = []
    while ready:
        idx = rng.randrange(len(ready))
        u = ready.pop(idx)
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
    total = 0.0
    for u, outs in dag.items():
        for v, w in outs.items():
            if group[u] < group[v]:
                total += w
    return total


def best_sequence_cut(order: list[int], k: int, dag: dict[int, dict[int, float]]) -> list[int]:
    n = len(order)
    if k >= n:
        return list(range(1, n + 1))
    # Small n in this reproduction, so exhaustive split enumeration keeps the
    # code easier to audit than the optimized DP in the paper.
    best_score = -1.0
    best_cuts: list[int] = [n]

    def rec(prev: int, groups_left: int, cuts: list[int]) -> None:
        nonlocal best_score, best_cuts
        if groups_left == 1:
            candidate = cuts + [n]
            score = cut_value(order, candidate, dag)
            if score > best_score:
                best_score = score
                best_cuts = candidate
            return
        max_end = n - groups_left + 1
        for end in range(prev + 1, max_end + 1):
            rec(end, groups_left - 1, cuts + [end])

    rec(0, k, [])
    return best_cuts


def compress_priorities(jobs: list[Job], levels: int, rng: random.Random) -> None:
    if levels <= 1:
        for j in jobs:
            j.hw_priority = 0
        return
    dag = contention_dag(jobs)
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
        priority = levels - group_id - 1
        for jid in best_order[start:end]:
            by_id[jid].hw_priority = priority
        start = end


def flat_compress_priorities(jobs: list[Job], levels: int) -> None:
    ordered = sorted(jobs, key=lambda j: j.logical_priority, reverse=True)
    for rank, job in enumerate(ordered):
        job.hw_priority = max(0, levels - 1 - (rank * levels // max(1, len(ordered))))


def evaluate(jobs: list[Job]) -> tuple[float, float, float, float]:
    link_users: dict[Link, list[Job]] = {}
    for job in jobs:
        assert job.selected_path is not None
        for link in job.selected_path:
            link_users.setdefault(link, []).append(job)

    iter_times: dict[int, float] = {}
    for job in jobs:
        worst_delay = 1.0
        assert job.selected_path is not None
        for link in job.selected_path:
            users = link_users[link]
            higher = sum(u.traffic for u in users if u.hw_priority > job.hw_priority)
            same = sum(u.traffic for u in users if u.hw_priority == job.hw_priority)
            fair_share_delay = higher / max(job.traffic, 0.01) + same / max(job.traffic, 0.01)
            worst_delay = max(worst_delay, fair_share_delay)
        exposed_comm = job.base_comm_time * worst_delay * job.sensitivity
        iter_times[job.jid] = job.base_compute_time + exposed_comm

    allocated_gpus = sum(j.gpu_count for j in jobs)
    useful = sum(j.gpu_count * j.base_compute_time / iter_times[j.jid] for j in jobs)
    gpu_util = useful / allocated_gpus
    ranked = sorted(jobs, key=lambda j: j.intensity)
    low = ranked[: max(1, len(ranked) // 4)]
    high = ranked[-max(1, len(ranked) // 4) :]
    return (
        gpu_util,
        mean(iter_times.values()),
        mean(iter_times[j.jid] for j in high),
        mean(iter_times[j.jid] for j in low),
    )


def run_scheduler(
    base_jobs: list[Job],
    scheduler: str,
    seed: int,
    levels: int,
) -> tuple[float, float, float, float]:
    import copy

    jobs = copy.deepcopy(base_jobs)
    rng = random.Random(seed)
    if scheduler == "random_same":
        assign_random_paths(jobs, rng)
        assign_logical_priorities(jobs, "same")
        for j in jobs:
            j.hw_priority = 0
    elif scheduler == "random_intensity":
        assign_random_paths(jobs, rng)
        assign_logical_priorities(jobs, "intensity")
        flat_compress_priorities(jobs, levels)
    elif scheduler == "crux_no_compress":
        assign_crux_paths(jobs)
        assign_logical_priorities(jobs, "crux")
        flat_compress_priorities(jobs, max(levels, len(jobs)))
    elif scheduler == "crux":
        assign_crux_paths(jobs)
        assign_logical_priorities(jobs, "crux")
        compress_priorities(jobs, levels, rng)
    else:
        raise ValueError(scheduler)
    return evaluate(jobs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--jobs", type=int, default=36)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--hosts", type=int, default=16)
    parser.add_argument("--gpus-per-host", type=int, default=8)
    parser.add_argument("--aggs", type=int, default=4)
    parser.add_argument("--priority-levels", type=int, default=4)
    parser.add_argument("--trace-data-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("crux_repro/results/crux_sim_results.csv"))
    args = parser.parse_args()

    schedulers = ["random_same", "random_intensity", "crux_no_compress", "crux"]
    results: list[RoundResult] = []
    for r in range(args.rounds):
        if args.trace_data_dir:
            jobs = make_lingjun_jobs(args.seed + r, args.jobs, args.trace_data_dir, args.aggs)
        else:
            jobs = make_jobs(args.seed + r, args.jobs, args.hosts, args.aggs)
        for scheduler in schedulers:
            gpu_util, avg_iter, high_jct, low_jct = run_scheduler(
                jobs, scheduler, args.seed * 1000 + r, args.priority_levels
            )
            results.append(RoundResult(r, scheduler, gpu_util, avg_iter, high_jct, low_jct))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["round", "scheduler", "gpu_util", "avg_iter_time", "high_intensity_jct", "low_intensity_jct"])
        for row in results:
            writer.writerow(
                [
                    row.round_id,
                    row.scheduler,
                    f"{row.gpu_util:.6f}",
                    f"{row.avg_iter_time:.6f}",
                    f"{row.high_intensity_jct:.6f}",
                    f"{row.low_intensity_jct:.6f}",
                ]
            )

    print("scheduler           gpu_util   avg_iter   high_int_jct   low_int_jct   util_gain_vs_random")
    baseline = mean(r.gpu_util for r in results if r.scheduler == "random_same")
    for scheduler in schedulers:
        subset = [r for r in results if r.scheduler == scheduler]
        util = mean(r.gpu_util for r in subset)
        gain = (util / baseline - 1.0) * 100.0
        print(
            f"{scheduler:18s} {util:8.4f} {mean(r.avg_iter_time for r in subset):10.4f}"
            f" {mean(r.high_intensity_jct for r in subset):14.4f}"
            f" {mean(r.low_intensity_jct for r in subset):13.4f} {gain:17.2f}%"
        )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
