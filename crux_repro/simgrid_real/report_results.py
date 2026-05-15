#!/usr/bin/env python3
"""Generate a compact Markdown report from SimGrid result CSV files.
Handles ablation schedulers and new metrics (compute_wait, overlap_ratio)."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def pct(base: float, value: float) -> float:
    return (base - value) / base * 100.0 if base else 0.0


def fmt_gain(base: float, value: float) -> str:
    g = pct(base, value)
    return f"{g:+.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("crux_repro/results/simgrid_real_report.md"))
    args = parser.parse_args()

    rows = read_rows(args.results)
    if not rows:
        raise ValueError(f"empty results csv: {args.results}")
    base = next((r for r in rows if r["scheduler"] == "random_same"), rows[0])
    base_makespan = float(base["makespan_s"])
    base_jct = float(base["avg_jct_s"])
    base_comm = float(base["avg_comm_s"])
    base_ugf = float(base["useful_gpu_fraction"])

    # Metadata from first row
    workload = rows[0].get("workload", "unknown")
    placement_mode = rows[0].get("placement_mode", "unknown")
    placement_objective = rows[0].get("placement_objective", "unknown")
    topology = rows[0].get("topology", "unknown")
    comm_plan = rows[0].get("comm_plan", "unknown")
    overlap = rows[0].get("overlap_ratio", "0.0")
    has_wait = "avg_compute_wait_s" in rows[0]

    lines: list[str] = []
    lines.append("# SimGrid Collective 竞争模拟报告")
    lines.append("")
    lines.append(f"- 输入结果：`{args.results}`")
    lines.append(f"- topology：`{topology}`  |  comm plan：`{comm_plan}`  |  overlap：`{overlap}`")
    lines.append(f"- workload：`{workload}`  |  placement：`{placement_mode}` / `{placement_objective}`")
    lines.append(f"- baseline：`{base['scheduler']}`")
    lines.append("")

    # --- Main comparison table ---
    lines.append("## Scheduler 对比")
    lines.append("")
    header = "| scheduler | makespan(s) | gain | avg JCT(s) | gain | avg comm(s) | gain | GPU fraction |"
    if has_wait:
        header = "| scheduler | makespan(s) | gain | avg JCT(s) | gain | avg comm(s) | gain | wait(s) | GPU fraction |"
    lines.append(header)
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|"
    if has_wait:
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines.append(sep)
    for r in rows:
        ms = float(r["makespan_s"])
        jct = float(r["avg_jct_s"])
        comm = float(r["avg_comm_s"])
        ugf = float(r["useful_gpu_fraction"])
        if has_wait:
            wait = float(r.get("avg_compute_wait_s", 0))
            lines.append(
                f"| `{r['scheduler']}` | {ms:.3f} | {fmt_gain(base_makespan, ms)} | "
                f"{jct:.3f} | {fmt_gain(base_jct, jct)} | {comm:.3f} | {fmt_gain(base_comm, comm)} | "
                f"{wait:.3f} | {ugf:.4f} |"
            )
        else:
            lines.append(
                f"| `{r['scheduler']}` | {ms:.3f} | {fmt_gain(base_makespan, ms)} | "
                f"{jct:.3f} | {fmt_gain(base_jct, jct)} | {comm:.3f} | {fmt_gain(base_comm, comm)} | "
                f"{ugf:.4f} |"
            )

    # --- Ablation decomposition ---
    lines.append("")
    lines.append("## Ablation 收益分解")
    lines.append("")
    lines.append("| 组件 | 对比 | makespan gain | JCT gain | comm gain |")
    lines.append("|---|---:|---:|---:|")

    # Find individual schedulers
    by_name = {r["scheduler"]: r for r in rows}

    # Placement only vs baseline
    if "place_only" in by_name:
        r = by_name["place_only"]
        lines.append(
            f"| **placement only** | `place_only` vs `random_same` | "
            f"{fmt_gain(base_makespan, float(r['makespan_s']))} | "
            f"{fmt_gain(base_jct, float(r['avg_jct_s']))} | "
            f"{fmt_gain(base_comm, float(r['avg_comm_s']))} |"
        )

    # Priority only vs baseline
    if "priority_only" in by_name:
        r = by_name["priority_only"]
        lines.append(
            f"| **priority only** | `priority_only` vs `random_same` | "
            f"{fmt_gain(base_makespan, float(r['makespan_s']))} | "
            f"{fmt_gain(base_jct, float(r['avg_jct_s']))} | "
            f"{fmt_gain(base_comm, float(r['avg_comm_s']))} |"
        )

    # Intensity priority (random_intensity) vs baseline
    if "random_intensity" in by_name:
        r = by_name["random_intensity"]
        lines.append(
            f"| **intensity buckets** | `random_intensity` vs `random_same` | "
            f"{fmt_gain(base_makespan, float(r['makespan_s']))} | "
            f"{fmt_gain(base_jct, float(r['avg_jct_s']))} | "
            f"{fmt_gain(base_comm, float(r['avg_comm_s']))} |"
        )

    # Full Crux no compress vs baseline
    if "crux_no_compress" in by_name:
        r = by_name["crux_no_compress"]
        lines.append(
            f"| **full crux (no compress)** | `crux_no_compress` vs `random_same` | "
            f"{fmt_gain(base_makespan, float(r['makespan_s']))} | "
            f"{fmt_gain(base_jct, float(r['avg_jct_s']))} | "
            f"{fmt_gain(base_comm, float(r['avg_comm_s']))} |"
        )

    # Full Crux vs baseline
    if "crux" in by_name:
        r = by_name["crux"]
        lines.append(
            f"| **full crux (K=4)** | `crux` vs `random_same` | "
            f"{fmt_gain(base_makespan, float(r['makespan_s']))} | "
            f"{fmt_gain(base_jct, float(r['avg_jct_s']))} | "
            f"{fmt_gain(base_comm, float(r['avg_comm_s']))} |"
        )

    # Crux vs Crux no compress (compression loss)
    if "crux" in by_name and "crux_no_compress" in by_name:
        r_c = by_name["crux"]
        r_nc = by_name["crux_no_compress"]
        nc_ms = float(r_nc["makespan_s"])
        nc_jct = float(r_nc["avg_jct_s"])
        nc_comm = float(r_nc["avg_comm_s"])
        lines.append(
            f"| **compression gap** | `crux` vs `crux_no_compress` | "
            f"{fmt_gain(nc_ms, float(r_c['makespan_s']))} | "
            f"{fmt_gain(nc_jct, float(r_c['avg_jct_s']))} | "
            f"{fmt_gain(nc_comm, float(r_c['avg_comm_s']))} |"
        )

    # --- Conclusions ---
    lines.append("")
    lines.append("## 结论")
    lines.append("")

    best_jct = min(rows, key=lambda r: float(r["avg_jct_s"]))
    best_makespan = min(rows, key=lambda r: float(r["makespan_s"]))
    best_comm = min(rows, key=lambda r: float(r["avg_comm_s"]))
    best_ugf = max(rows, key=lambda r: float(r["useful_gpu_fraction"]))

    lines.append(f"- 平均 JCT 最优：`{best_jct['scheduler']}` ({float(best_jct['avg_jct_s']):.3f}s, {fmt_gain(base_jct, float(best_jct['avg_jct_s']))})")
    lines.append(f"- makespan 最优：`{best_makespan['scheduler']}` ({float(best_makespan['makespan_s']):.3f}s, {fmt_gain(base_makespan, float(best_makespan['makespan_s']))})")
    lines.append(f"- 通信时间最优：`{best_comm['scheduler']}` ({float(best_comm['avg_comm_s']):.3f}s, {fmt_gain(base_comm, float(best_comm['avg_comm_s']))})")
    lines.append(f"- GPU 利用率最优：`{best_ugf['scheduler']}` ({float(best_ugf['useful_gpu_fraction']):.4f})")

    # Decomposition insight
    lines.append("")
    lines.append("### 收益来源分解")
    if "place_only" in by_name and "crux_no_compress" in by_name:
        po_gain = pct(base_jct, float(by_name["place_only"]["avg_jct_s"]))
        full_gain = pct(base_jct, float(by_name["crux_no_compress"]["avg_jct_s"]))
        lines.append(f"- placement 贡献约占 JCT 改善的 {po_gain/full_gain*100:.0f}% " if full_gain > 0 else "- 无法计算")
        lines.append(f"- 剩余来自 priority + path selection 的协同效应")
    if "priority_only" in by_name:
        prio_gain = pct(base_jct, float(by_name["priority_only"]["avg_jct_s"]))
        lines.append(f"- priority-only 独立贡献 JCT 改善 {prio_gain:.2f}%，说明仅靠优先级（不改 placement）收益有限")

    lines.append("")
    lines.append("*此报告用于快速比较策略，完整分析见 job-level timeline、link heatmap 和 CDF 图。*")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
