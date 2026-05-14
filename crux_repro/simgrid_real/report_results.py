#!/usr/bin/env python3
"""Generate a compact Markdown report from SimGrid result CSV files."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def pct(base: float, value: float) -> float:
    return (base - value) / base * 100.0 if base else 0.0


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

    lines: list[str] = []
    lines.append("# SimGrid Trace-Driven Collective 模拟报告")
    lines.append("")
    lines.append(f"- 输入结果：`{args.results}`")
    lines.append(f"- workload：`{rows[0].get('workload', 'unknown')}`")
    lines.append(f"- placement mode：`{rows[0].get('placement_mode', 'unknown')}`")
    lines.append(f"- placement objective：`{rows[0].get('placement_objective', 'unknown')}`")
    lines.append(f"- baseline：`{base['scheduler']}`")
    lines.append("")
    lines.append("| scheduler | makespan(s) | makespan gain | avg JCT(s) | JCT gain | avg comm(s) | comm gain | useful GPU fraction |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        makespan = float(r["makespan_s"])
        jct = float(r["avg_jct_s"])
        comm = float(r["avg_comm_s"])
        util = float(r["useful_gpu_fraction"])
        lines.append(
            f"| `{r['scheduler']}` | {makespan:.3f} | {pct(base_makespan, makespan):.2f}% | "
            f"{jct:.3f} | {pct(base_jct, jct):.2f}% | {comm:.3f} | {pct(base_comm, comm):.2f}% | {util:.4f} |"
        )
    lines.append("")
    best_jct = min(rows, key=lambda r: float(r["avg_jct_s"]))
    best_makespan = min(rows, key=lambda r: float(r["makespan_s"]))
    best_comm = min(rows, key=lambda r: float(r["avg_comm_s"]))
    lines.append("## 结论")
    lines.append("")
    lines.append(
        f"- 平均 JCT 最优的是 `{best_jct['scheduler']}`，相对 baseline JCT 改善 "
        f"{pct(base_jct, float(best_jct['avg_jct_s'])):.2f}%。"
    )
    lines.append(
        f"- makespan 最优的是 `{best_makespan['scheduler']}`，相对 baseline makespan 改善 "
        f"{pct(base_makespan, float(best_makespan['makespan_s'])):.2f}%。"
    )
    lines.append(
        f"- 平均通信时间最优的是 `{best_comm['scheduler']}`，相对 baseline comm 改善 "
        f"{pct(base_comm, float(best_comm['avg_comm_s'])):.2f}%。"
    )
    lines.append("- 这份报告用于快速比较策略，后续可以继续扩展 job-level timeline、link heatmap 和 CDF 图。")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
