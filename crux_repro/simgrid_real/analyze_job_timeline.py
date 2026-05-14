#!/usr/bin/env python3
"""Analyze job-level SimGrid output and generate SVG/Markdown artifacts."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str) -> float:
    return float(row[key])


def pct(base: float, value: float) -> float:
    return (base - value) / base * 100.0 if base else 0.0


def svg_text(x: float, y: float, text: str, size: int = 12, anchor: str = "start", weight: str = "400") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="#1f2937">{text}</text>'
    )


def write_jct_cdf(rows_by_scheduler: dict[str, list[dict[str, str]]], out: Path) -> None:
    width, height = 760, 420
    margin_l, margin_r, margin_t, margin_b = 70, 24, 36, 58
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    all_jcts = [f(r, "jct_s") for rows in rows_by_scheduler.values() for r in rows]
    max_x = max(all_jcts) * 1.08
    colors = {
        "random_same": "#64748b",
        "random_intensity": "#0ea5e9",
        "crux_no_compress": "#22c55e",
        "crux": "#ef4444",
    }

    def xscale(x: float) -> float:
        return margin_l + x / max_x * plot_w

    def yscale(y: float) -> float:
        return margin_t + (1.0 - y) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 24, "Job JCT CDF", 18, "middle", "700"),
        f'<line x1="{margin_l}" y1="{margin_t + plot_h}" x2="{margin_l + plot_w}" y2="{margin_t + plot_h}" stroke="#334155"/>',
        f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l}" y2="{margin_t + plot_h}" stroke="#334155"/>',
    ]
    for i in range(6):
        x = max_x * i / 5
        sx = xscale(x)
        parts.append(f'<line x1="{sx:.1f}" y1="{margin_t}" x2="{sx:.1f}" y2="{margin_t + plot_h}" stroke="#e5e7eb"/>')
        parts.append(svg_text(sx, height - 28, f"{x:.0f}s", 11, "middle"))
    for i in range(6):
        y = i / 5
        sy = yscale(y)
        parts.append(f'<line x1="{margin_l}" y1="{sy:.1f}" x2="{margin_l + plot_w}" y2="{sy:.1f}" stroke="#e5e7eb"/>')
        parts.append(svg_text(44, sy + 4, f"{y:.1f}", 11, "end"))
    parts.append(svg_text(width / 2, height - 8, "JCT seconds", 12, "middle"))
    parts.append(svg_text(18, height / 2, "CDF", 12, "middle"))

    legend_x = margin_l + 12
    legend_y = margin_t + 18
    for idx, (scheduler, rows) in enumerate(rows_by_scheduler.items()):
        values = sorted(f(r, "jct_s") for r in rows)
        if not values:
            continue
        points = []
        n = len(values)
        for i, value in enumerate(values, start=1):
            points.append(f"{xscale(value):.1f},{yscale(i / n):.1f}")
        color = colors.get(scheduler, "#111827")
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        y = legend_y + idx * 20
        parts.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 24}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        parts.append(svg_text(legend_x + 32, y + 4, scheduler, 12))
    parts.append("</svg>")
    out.write_text("\n".join(parts), encoding="utf-8")


def write_delta_bar(deltas: list[dict[str, str]], out: Path, target: str) -> None:
    width = 900
    bar_h = 24
    margin_l, margin_r, margin_t, margin_b = 250, 150, 42, 34
    height = margin_t + margin_b + len(deltas) * bar_h
    max_abs = max(abs(float(r["jct_delta_s"])) for r in deltas) * 1.15 or 1.0
    zero_x = margin_l + (width - margin_l - margin_r) / 2
    scale = (width - margin_l - margin_r) / 2 / max_abs
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 24, f"Per-job JCT delta: {target} vs random_same", 18, "middle", "700"),
        f'<line x1="{zero_x:.1f}" y1="{margin_t - 8}" x2="{zero_x:.1f}" y2="{height - margin_b + 4}" stroke="#334155"/>',
    ]
    for i, row in enumerate(deltas):
        y = margin_t + i * bar_h
        delta = float(row["jct_delta_s"])
        x = zero_x if delta >= 0 else zero_x + delta * scale
        w = abs(delta * scale)
        color = "#ef4444" if delta > 0 else "#22c55e"
        label = f"job {row['job_id']} {row['model']}"
        parts.append(svg_text(12, y + 16, label, 11))
        parts.append(f'<rect x="{x:.1f}" y="{y + 4:.1f}" width="{w:.1f}" height="14" rx="3" fill="{color}"/>')
        parts.append(svg_text(width - 12, y + 16, f"{delta:+.2f}s", 11, "end"))
    parts.append(svg_text(zero_x, height - 10, "0", 11, "middle"))
    parts.append("</svg>")
    out.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--target", default="crux_no_compress")
    parser.add_argument("--baseline", default="random_same")
    parser.add_argument("--out-dir", type=Path, default=Path("crux_repro/results/job_analysis"))
    args = parser.parse_args()

    rows = read_rows(args.jobs)
    if not rows:
        raise ValueError(f"empty jobs csv: {args.jobs}")
    rows_by_scheduler: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        rows_by_scheduler.setdefault(row["scheduler"], []).append(row)

    if args.baseline not in rows_by_scheduler or args.target not in rows_by_scheduler:
        raise ValueError(f"need both baseline={args.baseline} and target={args.target} in {args.jobs}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base = {row["job_id"]: row for row in rows_by_scheduler[args.baseline]}
    target = {row["job_id"]: row for row in rows_by_scheduler[args.target]}
    deltas: list[dict[str, str]] = []
    for job_id, brow in base.items():
      if job_id not in target:
        continue
      trow = target[job_id]
      base_jct = f(brow, "jct_s")
      target_jct = f(trow, "jct_s")
      base_comm = f(brow, "comm_s")
      target_comm = f(trow, "comm_s")
      deltas.append({
          "job_id": job_id,
          "model": brow["model"],
          "ranks": brow["ranks"],
          "base_jct_s": f"{base_jct:.6f}",
          "target_jct_s": f"{target_jct:.6f}",
          "jct_delta_s": f"{target_jct - base_jct:.6f}",
          "jct_gain_pct": f"{pct(base_jct, target_jct):.6f}",
          "base_comm_s": f"{base_comm:.6f}",
          "target_comm_s": f"{target_comm:.6f}",
          "comm_delta_s": f"{target_comm - base_comm:.6f}",
          "comm_gain_pct": f"{pct(base_comm, target_comm):.6f}",
          "base_placement": brow["placement"],
          "target_placement": trow["placement"],
      })
    deltas.sort(key=lambda r: float(r["jct_delta_s"]), reverse=True)

    delta_csv = args.out_dir / f"{args.target}_vs_{args.baseline}_job_deltas.csv"
    with delta_csv.open("w", newline="") as fcsv:
        fieldnames = list(deltas[0].keys()) if deltas else []
        writer = csv.DictWriter(fcsv, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deltas)

    cdf_svg = args.out_dir / "jct_cdf.svg"
    bar_svg = args.out_dir / f"{args.target}_jct_delta.svg"
    write_jct_cdf(rows_by_scheduler, cdf_svg)
    write_delta_bar(deltas, bar_svg, args.target)

    improved = [r for r in deltas if float(r["jct_delta_s"]) < 0]
    regressed = [r for r in deltas if float(r["jct_delta_s"]) > 0]
    lines = [
        "# SimGrid Job-Level Analysis",
        "",
        f"- job 输入：`{args.jobs}`",
        f"- baseline：`{args.baseline}`",
        f"- target：`{args.target}`",
        f"- job delta CSV：`{delta_csv}`",
        "",
        f"![JCT CDF]({cdf_svg.name})",
        "",
        f"![JCT Delta]({bar_svg.name})",
        "",
        "## Summary",
        "",
        f"- 改善 job 数：{len(improved)} / {len(deltas)}",
        f"- 退化 job 数：{len(regressed)} / {len(deltas)}",
        "",
        "## Top JCT Gains",
        "",
        "| job | model | JCT delta | JCT gain | comm delta | comm gain |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in sorted(deltas, key=lambda r: float(r["jct_delta_s"]))[:5]:
        lines.append(
            f"| {row['job_id']} | {row['model']} | {float(row['jct_delta_s']):+.3f}s | "
            f"{float(row['jct_gain_pct']):+.2f}% | {float(row['comm_delta_s']):+.3f}s | {float(row['comm_gain_pct']):+.2f}% |"
        )
    lines.extend(["", "## Top JCT Regressions", "", "| job | model | JCT delta | JCT gain | comm delta | comm gain |", "|---:|---|---:|---:|---:|---:|"])
    for row in deltas[:5]:
        lines.append(
            f"| {row['job_id']} | {row['model']} | {float(row['jct_delta_s']):+.3f}s | "
            f"{float(row['jct_gain_pct']):+.2f}% | {float(row['comm_delta_s']):+.3f}s | {float(row['comm_gain_pct']):+.2f}% |"
        )
    report = args.out_dir / f"{args.target}_vs_{args.baseline}_job_analysis.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {report}")
    print(f"wrote {delta_csv}")
    print(f"wrote {cdf_svg}")
    print(f"wrote {bar_svg}")


if __name__ == "__main__":
    main()
