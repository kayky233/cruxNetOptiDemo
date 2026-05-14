#!/usr/bin/env python3
"""Generate SVG charts for DeepSeek verification CSV results."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


SCHEDULERS = ["random_intensity", "crux", "crux_no_compress"]
COLORS = {
    "random_intensity": "#0ea5e9",
    "crux": "#ef4444",
    "crux_no_compress": "#22c55e",
}
LABELS = {
    "random_intensity": "priority-only",
    "crux": "crux",
    "crux_no_compress": "crux no compress",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def summarize(path: Path) -> dict[str, dict[str, float]]:
    rows = read_csv(path)
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        scheduler = row["scheduler"]
        for key in ("gpu_util", "avg_iter_time", "high_intensity_jct", "low_intensity_jct"):
            grouped[scheduler][key].append(float(row[key]))
    return {
        scheduler: {metric: mean(values) for metric, values in metrics.items()}
        for scheduler, metrics in grouped.items()
    }


def gain(summary: dict[str, dict[str, float]], scheduler: str, metric: str = "gpu_util") -> float:
    base = summary["random_same"][metric]
    value = summary[scheduler][metric]
    if metric in ("avg_iter_time", "high_intensity_jct", "low_intensity_jct"):
        return (base - value) / base * 100.0
    return (value - base) / base * 100.0


def text(x: float, y: float, value: str, size: int = 12, anchor: str = "start", weight: str = "400") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="#1f2937">{value}</text>'
    )


def grouped_bar_chart(title: str, categories: list[str], series: dict[str, list[float]], out: Path, ylabel: str) -> None:
    width, height = 900, 460
    ml, mr, mt, mb = 78, 30, 54, 82
    pw, ph = width - ml - mr, height - mt - mb
    max_v = max(max(values) for values in series.values())
    min_v = min(min(values) for values in series.values())
    y_min = min(0.0, min_v)
    y_max = max_v * 1.18 if max_v > 0 else 1.0
    if y_min < 0:
        y_min *= 1.18

    def yscale(v: float) -> float:
        return mt + (y_max - v) / (y_max - y_min) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        text(width / 2, 28, title, 18, "middle", "700"),
        f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="#334155"/>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="#334155"/>',
        text(18, height / 2, ylabel, 12, "middle"),
    ]
    for i in range(6):
        v = y_min + (y_max - y_min) * i / 5
        y = yscale(v)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(text(ml - 10, y + 4, f"{v:.0f}%", 11, "end"))

    n_cat = len(categories)
    n_series = len(series)
    group_w = pw / n_cat
    bar_w = min(30, group_w * 0.68 / n_series)
    zero_y = yscale(0.0)
    for ci, cat in enumerate(categories):
        cx = ml + group_w * ci + group_w / 2
        parts.append(text(cx, height - 42, cat, 11, "middle"))
        for si, (name, values) in enumerate(series.items()):
            value = values[ci]
            x = cx - (n_series * bar_w) / 2 + si * bar_w
            y = yscale(max(value, 0.0))
            h = abs(zero_y - yscale(value))
            if value < 0:
                y = zero_y
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 3:.1f}" height="{h:.1f}" rx="3" fill="{COLORS.get(name, "#64748b")}"/>')
            parts.append(text(x + (bar_w - 3) / 2, y - 4 if value >= 0 else y + h + 12, f"{value:.1f}", 9, "middle"))

    lx = ml + 10
    ly = mt + 12
    for i, name in enumerate(series):
        x = lx + i * 185
        parts.append(f'<rect x="{x}" y="{ly - 10}" width="14" height="14" rx="2" fill="{COLORS.get(name, "#64748b")}"/>')
        parts.append(text(x + 20, ly + 2, LABELS.get(name, name), 12))
    parts.append("</svg>")
    out.write_text("\n".join(parts), encoding="utf-8")


def line_chart(title: str, categories: list[str], series: dict[str, list[float]], out: Path, ylabel: str) -> None:
    width, height = 900, 440
    ml, mr, mt, mb = 78, 30, 54, 72
    pw, ph = width - ml - mr, height - mt - mb
    max_v = max(max(values) for values in series.values()) * 1.18

    def xscale(i: int) -> float:
        return ml + (pw * i / max(1, len(categories) - 1))

    def yscale(v: float) -> float:
        return mt + (max_v - v) / max_v * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        text(width / 2, 28, title, 18, "middle", "700"),
        f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="#334155"/>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="#334155"/>',
        text(18, height / 2, ylabel, 12, "middle"),
    ]
    for i in range(6):
        v = max_v * i / 5
        y = yscale(v)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(text(ml - 10, y + 4, f"{v:.0f}%", 11, "end"))
    for i, cat in enumerate(categories):
        parts.append(text(xscale(i), height - 36, cat, 11, "middle"))
    for name, values in series.items():
        pts = " ".join(f"{xscale(i):.1f},{yscale(v):.1f}" for i, v in enumerate(values))
        color = COLORS.get(name, "#64748b")
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for i, v in enumerate(values):
            x, y = xscale(i), yscale(v)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
            parts.append(text(x, y - 8, f"{v:.1f}", 10, "middle"))
    lx, ly = ml + 10, mt + 12
    for i, name in enumerate(series):
        x = lx + i * 185
        parts.append(f'<line x1="{x}" y1="{ly - 4}" x2="{x + 18}" y2="{ly - 4}" stroke="{COLORS.get(name, "#64748b")}" stroke-width="3"/>')
        parts.append(text(x + 26, ly, LABELS.get(name, name), 12))
    parts.append("</svg>")
    out.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verification-dir", type=Path, default=Path("crux_repro/results/verification"))
    parser.add_argument("--out-dir", type=Path, default=Path("crux_repro/results/verification/figures"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    def gains(files: list[tuple[str, str]]) -> tuple[list[str], dict[str, list[float]]]:
        categories = []
        data = {s: [] for s in SCHEDULERS}
        for label, filename in files:
            summary = summarize(args.verification_dir / filename)
            categories.append(label)
            for scheduler in SCHEDULERS:
                data[scheduler].append(gain(summary, scheduler))
        return categories, data

    k_categories, k_data = gains([(k, f"verify_k{k}.csv") for k in ("1", "2", "3", "4", "6")])
    line_chart("Priority Levels Sensitivity", k_categories, k_data, args.out_dir / "priority_levels_gain.svg", "GPU util gain")

    scale_categories, scale_data = gains([
        ("small", "verify_scale_small.csv"),
        ("medium", "verify_scale_medium.csv"),
        ("large", "verify_scale_large.csv"),
        ("xl", "verify_scale_xl.csv"),
    ])
    grouped_bar_chart("Scale Pressure", scale_categories, scale_data, args.out_dir / "scale_pressure_gain.svg", "GPU util gain")

    aggs_categories, aggs_data = gains([(a, f"verify_aggs{a}.csv") for a in ("2", "4", "8")])
    grouped_bar_chart("Aggregation Path Count", aggs_categories, aggs_data, args.out_dir / "aggregation_paths_gain.svg", "GPU util gain")

    seed_categories, seed_data = gains([("7", "verify_scale_medium.csv"), ("42", "verify_seed42.csv"), ("100", "verify_seed100.csv"), ("2024", "verify_seed2024.csv")])
    line_chart("Multi-Seed Stability", seed_categories, seed_data, args.out_dir / "seed_stability_gain.svg", "GPU util gain")

    extreme_categories, extreme_data = gains([("48/8", "verify_extreme1.csv"), ("64/12", "verify_extreme2.csv")])
    grouped_bar_chart("Extreme Congestion", extreme_categories, extreme_data, args.out_dir / "extreme_congestion_gain.svg", "GPU util gain")

    report = args.out_dir / "README.zh-CN.md"
    report.write_text(
        "\n".join(
            [
                "# DeepSeek 补充验证图表",
                "",
                "这些图来自 `crux_repro/results/verification/verify_*.csv`，用于展示轻量 `crux_sim.py` 参数扫描结果。",
                "",
                "## 图表入口",
                "",
                "| 图 | 文件 | 说明 |",
                "|---|---|---|",
                "| 优先级级别敏感性 | `priority_levels_gain.svg` | K 从 1 到 6 时的 GPU util gain |",
                "| 规模压力 | `scale_pressure_gain.svg` | small/medium/large/xl 下的收益变化 |",
                "| 聚合路径数 | `aggregation_paths_gain.svg` | 可选路径数 2/4/8 下的收益变化 |",
                "| 多种子稳定性 | `seed_stability_gain.svg` | seed 7/42/100/2024 下的稳定性 |",
                "| 极端拥塞 | `extreme_congestion_gain.svg` | 高 job/host 比例下的收益 |",
                "",
                "## 结论速读",
                "",
                "- K=4 后收益基本饱和；",
                "- 规模越大、拥塞越强，Crux 收益越明显；",
                "- 多 seed 下 Crux 收益稳定；",
                "- 极端拥塞下 Crux/Crux no compress 的优势最直观。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out_dir}")


if __name__ == "__main__":
    main()
