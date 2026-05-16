#!/usr/bin/env python3
"""Convert Lingjun production traces into a compact SimGrid workload CSV."""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class HostTopo:
    host_id: int
    asw: str
    psw: str
    dsw: str


@dataclass(frozen=True)
class TraceJob:
    job_name: str
    model: str
    start_ts: float
    end_ts: float
    gpu_count: int
    host_ids: tuple[int, ...]
    duration_minutes: float


def parse_time(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).timestamp()
        except ValueError:
            pass
    return None


def model_profile(model: str, gpu_count: int) -> tuple[str, float, float]:
    name = (model or "unknown").lower()
    if "resnet" in name:
        return ("ResNet", 0.85, 1.2)
    if "bert" in name:
        return ("BERT", 1.20, 2.7)
    if "gpt" in name or "llama" in name or "llm" in name or "large" in name:
        if gpu_count >= 24:
            return ("GPT-large", 2.30, 10.0)
        return ("GPT", 1.80, 5.8)
    if gpu_count >= 24:
        return ("unknown-large", 2.10, 8.0)
    if gpu_count >= 12:
        return ("unknown-mid", 1.60, 4.2)
    if gpu_count >= 8:
        return ("unknown-8gpu", 1.20, 2.4)
    return ("unknown-small", 0.85, 1.0)


def read_trace(data_dir: Path) -> list[TraceJob]:
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
            start = parse_time(row.get("gmt_job_running", ""))
            end = parse_time(row.get("gmt_job_finished", "")) or parse_time(row.get("gmt_job_stopped", ""))
            if name and start is not None and end is not None and end > start:
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
        trace_jobs.append(
            TraceJob(
                job_name=name,
                model=model,
                start_ts=start,
                end_ts=end,
                gpu_count=sum(host_gpu.values()),
                host_ids=tuple(topo[ip].host_id for ip in host_ips),
                duration_minutes=(end - start) / 60.0,
            )
        )
    return trace_jobs


def choose_active_window(trace_jobs: list[TraceJob], count: int, seed: int) -> tuple[float, list[TraceJob]]:
    rng = random.Random(seed)
    starts = sorted({j.start_ts for j in trace_jobs})
    candidates: list[tuple[int, float, list[TraceJob]]] = []
    for ts in rng.sample(starts, min(300, len(starts))):
        active = [j for j in trace_jobs if j.start_ts <= ts < j.end_ts]
        if active:
            candidates.append((min(abs(len(active) - count), count), ts, active))
    if not candidates:
        raise ValueError("no active trace window found")
    _, ts, active = min(candidates, key=lambda item: item[0])
    if len(active) > count:
        active = sorted(active, key=lambda j: (-j.gpu_count, j.start_ts, j.job_name))[:count]
    return ts, sorted(active, key=lambda j: (j.start_ts, j.job_name))


def choose_arrival_window(trace_jobs: list[TraceJob], count: int) -> tuple[float, list[TraceJob]]:
    ordered = sorted(trace_jobs, key=lambda j: (j.start_ts, j.job_name))
    if len(ordered) <= count:
        return ordered[0].start_ts, ordered
    best: tuple[float, int] | None = None
    for i in range(0, len(ordered) - count + 1):
        span = ordered[i + count - 1].start_ts - ordered[i].start_ts
        if best is None or span < best[0]:
            best = (span, i)
    assert best is not None
    _, idx = best
    window = ordered[idx:idx + count]
    return window[0].start_ts, window


def write_workload(
    jobs: list[TraceJob],
    window_ts: float,
    out: Path,
    hosts: int,
    max_ranks: int,
    seed: int,
    arrival_time_scale: float,
) -> None:
    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["job_id", "trace_job_name", "model", "start_s", "duration_s", "ranks", "compute_s", "tensor_gib", "hosts"])
        for jid, job in enumerate(jobs):
            model, compute_s, tensor_gib = model_profile(job.model, job.gpu_count)
            duration_factor = max(0.75, min(2.5, job.duration_minutes / 720.0))
            gpu_factor = max(1.0, job.gpu_count / 8.0)
            ranks = max(2, min(max_ranks, job.gpu_count))
            mapped_hosts = [h % hosts for h in job.host_ids]
            if not mapped_hosts:
                continue
            writer.writerow(
                [
                    jid,
                    job.job_name,
                    model,
                    round(max(0.0, job.start_ts - window_ts) / max(1e-9, arrival_time_scale), 6),
                    round(job.end_ts - job.start_ts, 6),
                    ranks,
                    round(compute_s * (0.85 + 0.15 * gpu_factor) * duration_factor * rng.uniform(0.95, 1.05), 6),
                    round(tensor_gib * max(1.0, ranks / 8.0) * rng.uniform(0.95, 1.05), 6),
                    ";".join(str(h) for h in mapped_hosts),
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("crux_repro/results/simgrid_trace_workload.csv"))
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--hosts", type=int, default=8)
    parser.add_argument("--max-ranks", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--window-mode", choices=("active", "arrival"), default="active",
                        help="active keeps the old concurrent-running window; arrival keeps real job start ordering")
    parser.add_argument("--arrival-time-scale", type=float, default=1.0,
                        help="Divide real inter-arrival seconds by this factor for replay visualization/runtime")
    args = parser.parse_args()

    trace_jobs = read_trace(args.trace_data_dir)
    if not trace_jobs:
        raise ValueError(f"no usable GPU jobs found in {args.trace_data_dir}")
    if args.window_mode == "arrival":
        window_ts, jobs = choose_arrival_window(trace_jobs, args.jobs)
    else:
        window_ts, jobs = choose_active_window(trace_jobs, args.jobs, args.seed)
    write_workload(jobs, window_ts, args.out, args.hosts, args.max_ranks, args.seed, args.arrival_time_scale)
    print(f"wrote {len(jobs)} jobs to {args.out}")


if __name__ == "__main__":
    main()
