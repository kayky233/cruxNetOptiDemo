#!/usr/bin/env python3
"""Profile Alibaba Lingjun public trace for scheduler calibration.

The script intentionally stays stdlib-only so it can run in a clean checkout.
It does not infer real network counters from the trace; unsupported dimensions
are reported explicitly in the generated profile.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


TIME_FMT = "%Y/%m/%d %H:%M"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-data-dir", default="../data/lingjun", help="Directory with job.csv, worker.csv and topo.csv")
    parser.add_argument("--out-json", default="results/calibration/lingjun_trace_profile.json")
    parser.add_argument("--out-md", default="results/calibration/lingjun_trace_profile.md")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, TIME_FMT)
    except ValueError:
        return None


def parse_res(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {k: None for k in ("min", "p25", "p50", "p75", "p90", "p95", "p99", "max")}
    xs = sorted(values)

    def q(p: float) -> float:
        if len(xs) == 1:
            return xs[0]
        pos = (len(xs) - 1) * p
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return xs[lo]
        return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)

    return {
        "min": round(xs[0], 3),
        "p25": round(q(0.25), 3),
        "p50": round(q(0.50), 3),
        "p75": round(q(0.75), 3),
        "p90": round(q(0.90), 3),
        "p95": round(q(0.95), 3),
        "p99": round(q(0.99), 3),
        "max": round(xs[-1], 3),
    }


def top_counter(counter: Counter[str], limit: int = 20) -> dict[str, int]:
    return {str(k): int(v) for k, v in counter.most_common(limit)}


def count_distribution(values: list[int]) -> dict[str, int]:
    return {str(k): int(v) for k, v in sorted(Counter(values).items(), key=lambda kv: kv[0])}


def build_profile(trace_dir: Path) -> dict[str, Any]:
    job_rows = read_csv(trace_dir / "job.csv")
    worker_rows = read_csv(trace_dir / "worker.csv")
    topo_rows = read_csv(trace_dir / "topo.csv")

    topo_by_ip = {row.get("ip", ""): row for row in topo_rows if row.get("ip")}
    workers_by_job: dict[str, list[dict[str, str]]] = defaultdict(list)
    worker_gpu_counts: list[int] = []
    worker_rdma_counts: Counter[str] = Counter()
    hosts_with_topology = 0

    for row in worker_rows:
        workers_by_job[row.get("job_name", "")].append(row)
        res = parse_res(row.get("RES"))
        gpu_count = to_int(res.get("nvidia.com/gpu"))
        worker_gpu_counts.append(gpu_count)
        worker_rdma_counts[str(res.get("koordinator.sh/rdma", ""))] += 1
        if row.get("host_ip") in topo_by_ip:
            hosts_with_topology += 1

    jobs_by_name = {row.get("job_name", ""): row for row in job_rows if row.get("job_name")}
    usable_jobs = []
    duration_minutes: list[float] = []
    queue_minutes: list[float] = []
    invalid_queue_samples = 0
    invalid_duration_samples = 0
    per_job_spans: list[dict[str, int]] = []
    per_job_gpu_totals: list[int] = []
    per_job_worker_counts: list[int] = []

    for name, row in jobs_by_name.items():
        job_workers = workers_by_job.get(name, [])
        gpu_total = 0
        hosts = set()
        asw = set()
        psw = set()
        dsw = set()
        for worker in job_workers:
            res = parse_res(worker.get("RES"))
            gpu_total += to_int(res.get("nvidia.com/gpu"))
            host_ip = worker.get("host_ip")
            if host_ip:
                hosts.add(host_ip)
            topo = topo_by_ip.get(host_ip or "")
            if topo:
                if topo.get("ASW"):
                    asw.add(topo["ASW"])
                if topo.get("PSW"):
                    psw.add(topo["PSW"])
                if topo.get("DSW"):
                    dsw.add(topo["DSW"])

        if job_workers:
            per_job_worker_counts.append(len(job_workers))
            per_job_gpu_totals.append(gpu_total)
            per_job_spans.append({"hosts": len(hosts), "asw": len(asw), "psw": len(psw), "dsw": len(dsw)})
        if gpu_total > 0:
            usable_jobs.append(name)

        submitted = parse_time(row.get("gmt_job_submitted"))
        running = parse_time(row.get("gmt_job_running"))
        finished = parse_time(row.get("gmt_job_finished")) or parse_time(row.get("gmt_job_stopped"))
        if submitted and running:
            minutes = (running - submitted).total_seconds() / 60.0
            if minutes >= 0:
                queue_minutes.append(minutes)
            else:
                invalid_queue_samples += 1
        if running and finished:
            minutes = (finished - running).total_seconds() / 60.0
            if minutes >= 0:
                duration_minutes.append(minutes)
            else:
                invalid_duration_samples += 1

    span_distribution = {
        key: count_distribution([span[key] for span in per_job_spans])
        for key in ("hosts", "asw", "psw", "dsw")
    }

    worker_jobs_in_job_csv = sum(1 for name in workers_by_job if name in jobs_by_name)

    profile: dict[str, Any] = {
        "schema_version": "public-calibration-profile/v1",
        "source": {
            "name": "Alibaba Lingjun cluster trace",
            "trace_data_dir": str(trace_dir),
            "files": ["job.csv", "worker.csv", "topo.csv"],
        },
        "dataset": {
            "job_rows": len(job_rows),
            "worker_rows": len(worker_rows),
            "topology_rows": len(topo_rows),
            "jobs_with_workers_from_worker_csv": len(workers_by_job),
            "jobs_with_workers_in_job_csv": worker_jobs_in_job_csv,
            "jobs_with_gpu_workers": len(usable_jobs),
            "worker_topology_coverage": {
                "matched_rows": hosts_with_topology,
                "total_worker_rows": len(worker_rows),
                "ratio": round(hosts_with_topology / len(worker_rows), 6) if worker_rows else None,
            },
        },
        "schema_columns": {
            "job": list(job_rows[0].keys()) if job_rows else [],
            "worker": list(worker_rows[0].keys()) if worker_rows else [],
            "topology": list(topo_rows[0].keys()) if topo_rows else [],
        },
        "job_distributions": {
            "model_top20": top_counter(Counter(row.get("model", "") or "unknown" for row in job_rows)),
            "status": top_counter(Counter(row.get("status", "") or "unknown" for row in job_rows)),
            "gpu_topo_aware": top_counter(Counter(row.get("is_enable_gpu_topo_aware", "") or "unknown" for row in job_rows)),
        },
        "worker_distributions": {
            "gpu_per_worker": count_distribution(worker_gpu_counts),
            "rdma_resource": top_counter(worker_rdma_counts),
            "workers_per_job": count_distribution(per_job_worker_counts),
            "gpus_per_job": count_distribution(per_job_gpu_totals),
        },
        "topology": {
            "unique_hosts": len(topo_by_ip),
            "unique_dsw": len({row.get("DSW", "") for row in topo_rows if row.get("DSW")}),
            "unique_psw": len({row.get("PSW", "") for row in topo_rows if row.get("PSW")}),
            "unique_asw": len({row.get("ASW", "") for row in topo_rows if row.get("ASW")}),
            "per_job_span_distribution": span_distribution,
        },
        "timing": {
            "duration_minutes": {
                "valid_samples": len(duration_minutes),
                "invalid_negative_samples": invalid_duration_samples,
                "quantiles": quantiles(duration_minutes),
            },
            "queue_minutes": {
                "valid_samples": len(queue_minutes),
                "invalid_negative_samples": invalid_queue_samples,
                "quantiles": quantiles(queue_minutes),
            },
        },
        "calibration_boundary": {
            "strong": [
                "job arrival/order replay from gmt_job_submitted",
                "GPU demand and worker count distribution from worker.RES",
                "host/ASW/PSW/DSW topology span from topo.csv plus worker.host_ip",
            ],
            "medium": [
                "placement locality and cross-host/cross-switch pressure trends",
                "scheduler objective comparison under the same replay workload",
                "duration/queue-time sanity checks after filtering timestamp artifacts",
            ],
            "weak": [
                "communication intensity inferred from model/job shape only",
                "bandwidth and latency defaults before real benchmark calibration",
                "contention effects without real link counters",
            ],
            "not_supported": [
                "real per-link byte counters",
                "NCCL/HCCL collective timing by message size",
                "ECMP hashing, path selection, PFC/ECN, retransmit or congestion-control behavior",
                "host-level PCIe/NVLink topology inside a worker node",
            ],
        },
    }
    return profile


def render_markdown(profile: dict[str, Any]) -> str:
    dataset = profile["dataset"]
    timing = profile["timing"]
    topology = profile["topology"]
    lines = [
        "# Alibaba Lingjun Trace Calibration Profile",
        "",
        "## 数据规模",
        "",
        f"- Job 行数: {dataset['job_rows']}",
        f"- Worker 行数: {dataset['worker_rows']}",
        f"- Topology host 行数: {dataset['topology_rows']}",
        f"- Worker 表中出现的 job: {dataset['jobs_with_workers_from_worker_csv']}",
        f"- 能在 job.csv 对上的 worker job: {dataset['jobs_with_workers_in_job_csv']}",
        f"- 有 GPU worker 的 job: {dataset['jobs_with_gpu_workers']}",
        f"- Worker host topology 覆盖: {dataset['worker_topology_coverage']['matched_rows']} / {dataset['worker_topology_coverage']['total_worker_rows']} ({dataset['worker_topology_coverage']['ratio']})",
        "",
        "## 拓扑摘要",
        "",
        f"- DSW 数: {topology['unique_dsw']}",
        f"- PSW 数: {topology['unique_psw']}",
        f"- ASW 数: {topology['unique_asw']}",
        f"- Host 数: {topology['unique_hosts']}",
        "",
        "## 时间分布",
        "",
        f"- 运行时长有效样本: {timing['duration_minutes']['valid_samples']}, 负值/异常样本: {timing['duration_minutes']['invalid_negative_samples']}",
        f"- 排队时间有效样本: {timing['queue_minutes']['valid_samples']}, 负值/异常样本: {timing['queue_minutes']['invalid_negative_samples']}",
        f"- 运行时长分位数(分钟): `{json.dumps(timing['duration_minutes']['quantiles'], ensure_ascii=False)}`",
        f"- 排队时间分位数(分钟): `{json.dumps(timing['queue_minutes']['quantiles'], ensure_ascii=False)}`",
        "",
        "## 可校准边界",
        "",
        "强校准: 到达顺序/GPU 需求/worker 数/host-ASW-PSW-DSW 跨域跨度。",
        "",
        "中等校准: 同一 replay workload 下的放置局部性、跨 host/跨交换机压力趋势、调度目标相对对比。",
        "",
        "弱校准: 通信强度、带宽、延迟和拥塞惩罚仍然主要来自估算或保守默认值。",
        "",
        "不支持: 真实 per-link byte counter、NCCL/HCCL 分 message size 耗时、ECMP 哈希路径、PFC/ECN、重传、host 内 PCIe/NVLink 细节。",
        "",
        "## 验收含义",
        "",
        "当前 trace 可以把算法验证从纯 synthetic workload 推进到真实 job replay 与真实机架层级拓扑约束；它不能单独证明实机网络性能。后续只要补少量 Greyhound/hook benchmark 记录，就能把网络模型从估算推进到半实测。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    trace_dir = Path(args.trace_data_dir)
    profile = build_profile(trace_dir)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(profile), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
