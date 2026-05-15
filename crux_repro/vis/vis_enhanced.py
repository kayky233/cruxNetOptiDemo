#!/usr/bin/env python3
"""Enhanced visualization for SimGrid simulation results.

Reads:
  - job-level CSV (from --job-out)
  - link aggregate CSV (from --link-out)
  - link timeline CSV (from --link-timeline-out)

Generates SVG:
  - Link utilization heatmap (time × link)
  - Compute/comm/wait breakdown waterfall per job
  - Ablation bar chart (gain decomposition across schedulers)
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str) -> float:
    return float(row[key])


def svg_text(x: float, y: float, text: str, size: int = 11, anchor: str = "start", weight: str = "400", fill: str = "#1f2937") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{text}</text>'
    )


# ── Palette ──────────────────────────────────────────────────
SCHED_COLORS = {
    "random_same": "#64748b",
    "random_intensity": "#0ea5e9",
    "place_only": "#8b5cf6",
    "priority_only": "#f59e0b",
    "crux_no_compress": "#22c55e",
    "crux": "#ef4444",
}


def write_link_heatmap(link_timeline_paths: dict[str, Path], out_path: Path) -> None:
    """Link utilization heatmap: time × link, color by instantaneous utilization."""
    all_data: dict[str, dict[str, list[tuple[float, float]]]] = {}  # scheduler -> link -> [(time, util)]

    for sched, path in link_timeline_paths.items():
        if not path.exists():
            continue
        rows = read_csv(path)
        links: dict[str, list[tuple[float, float]]] = defaultdict(list)
        # Get bandwidth for each link (need aggregate data for this)
        # For now, derive utilization from cumulative bytes delta
        link_bytes: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for r in rows:
            link_bytes[r["link_name"]].append((float(r["time_s"]), float(r["cumulative_bytes"])))

        # Use a fixed bw guess for display; real bw would come from link-out
        for link_name, points in link_bytes.items():
            if len(points) < 2:
                continue
            # Estimate bandwidth from max delta
            max_delta = 0
            for i in range(1, len(points)):
                delta_bytes = points[i][1] - points[i - 1][1]
                delta_time = points[i][0] - points[i - 1][0]
                if delta_time > 0:
                    bps = delta_bytes / delta_time
                    if bps > max_delta:
                        max_delta = bps
            if max_delta == 0:
                max_delta = 1e9  # fallback
            for i in range(1, len(points)):
                delta_bytes = points[i][1] - points[i - 1][1]
                delta_time = points[i][0] - points[i - 1][0]
                util = (delta_bytes / delta_time / max_delta) if delta_time > 0 else 0
                links[link_name].append((points[i][0], min(1.0, util)))
        all_data[sched] = dict(links)

    if not all_data:
        return

    # Pick first scheduler's links
    first_sched = list(all_data.keys())[0]
    link_names = sorted(all_data[first_sched].keys())
    if not link_names:
        return

    # Filter to top-N by variance
    link_names = link_names[:20]  # cap at 20 links

    width = 960
    h_per_sched = 220
    margin_l, margin_r, margin_t, margin_b = 160, 24, 48, 30
    bar_h = 14
    height = margin_t + margin_b + len(link_names) * bar_h * len(all_data) + 10 * (len(all_data) - 1)

    # Find max time
    max_t = 0
    for s_data in all_data.values():
        for pts in s_data.values():
            if pts:
                max_t = max(max_t, pts[-1][0])
    max_t = max(max_t, 1.0)

    plot_w = width - margin_l - margin_r

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 22, "Link Utilization Heatmap", 16, "middle", "700"),
    ]

    y_offset = margin_t
    for si, (sched, links) in enumerate(sorted(all_data.items())):
        color = SCHED_COLORS.get(sched, "#333")
        parts.append(svg_text(margin_l, y_offset - 4, sched, 12, "start", "700", color))
        y_offset += 8
        for li, link_name in enumerate(link_names):
            y = y_offset + li * bar_h
            parts.append(svg_text(8, y + 11, link_name[:20], 8, "start", "400", "#6b7280"))
            pts = links.get(link_name, [])
            for i in range(1, len(pts)):
                t0, u0 = pts[i - 1]
                t1, u1 = pts[i]
                x0 = margin_l + t0 / max_t * plot_w
                x1 = margin_l + t1 / max_t * plot_w
                w = max(1.0, x1 - x0)
                # Color: green=low util, red=high util
                r = int(255 * u0)
                g = int(255 * (1 - u0))
                parts.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bar_h}" fill="rgb({r},{g},0)" opacity="0.85"/>')
        y_offset += len(link_names) * bar_h + 10

    # Time axis
    for i in range(6):
        t = max_t * i / 5
        x = margin_l + t / max_t * plot_w
        parts.append(f'<line x1="{x:.1f}" y1="{y_offset - 8}" x2="{x:.1f}" y2="{y_offset - 2}" stroke="#334155"/>')
        parts.append(svg_text(x, y_offset + 14, f"{t:.0f}s", 10, "middle"))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def write_breakdown_bars(jobs_path: Path, out_path: Path, target: str = "crux_no_compress", baseline: str = "random_same") -> None:
    """Compute/comm/wait breakdown waterfall chart per job for target vs baseline."""
    rows = read_csv(jobs_path)
    by_sched: dict[str, dict[str, dict[str, str]]] = {}
    for r in rows:
        by_sched.setdefault(r["scheduler"], {})[r["job_id"]] = r

    if baseline not in by_sched or target not in by_sched:
        print(f"  skip breakdown: need {baseline} and {target}")
        return

    base_jobs = by_sched[baseline]
    tgt_jobs = by_sched[target]
    job_ids = sorted(base_jobs.keys(), key=lambda j: f(tgt_jobs.get(j, base_jobs[j]), "jct_s"))

    n = len(job_ids)
    bar_h = 22
    gap = 4
    width = 900
    margin_l, margin_r, margin_t, margin_b = 200, 150, 48, 30
    height = margin_t + margin_b + n * (bar_h * 2 + gap)
    max_jct = max(max(f(r, "jct_s") for r in base_jobs.values()), max(f(r, "jct_s") for r in tgt_jobs.values())) * 1.1

    scale = (width - margin_l - margin_r) / 2 / max_jct
    zero_x = margin_l + (width - margin_l - margin_r) / 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 22, f"JCT Breakdown: {target} vs {baseline}", 16, "middle", "700"),
        svg_text(zero_x - 10, 38, "← baseline better", 10, "end", "400", "#64748b"),
        svg_text(zero_x + 10, 38, "target better →", 10, "start", "400", "#22c55e"),
    ]

    for i, jid in enumerate(job_ids):
        y = margin_t + i * (bar_h * 2 + gap)
        brow = base_jobs[jid]
        trow = tgt_jobs.get(jid, brow)
        model = brow.get("model", "?")

        # Base bar (left of zero, mirrored)
        b_jct = f(brow, "jct_s")
        b_comm = f(brow, "comm_s")
        b_wait = f(brow, "compute_wait_s") if "compute_wait_s" in brow else 0
        b_comp = b_jct - b_comm - b_wait
        # Target bar (right of zero)
        t_jct = f(trow, "jct_s")
        t_comm = f(trow, "comm_s")
        t_wait = f(trow, "compute_wait_s") if "compute_wait_s" in trow else 0
        t_comp = t_jct - t_comm - t_wait

        parts.append(svg_text(12, y + 14, f"job {jid} {model[:12]}", 9, "start"))

        # Base: draw from zero_x leftward
        stack = 0
        for val, col, label in [(b_comp, "#3b82f6", "compute"), (b_comm, "#f59e0b", "comm"), (b_wait, "#ef4444", "wait")]:
            w = val * scale
            if w > 0.5:
                parts.append(f'<rect x="{zero_x - stack - w:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bar_h}" fill="{col}" opacity="0.7" rx="2"/>')
            stack += w

        # Target: draw from zero_x rightward
        stack = 0
        for val, col, label in [(t_comp, "#3b82f6", "compute"), (t_comm, "#f59e0b", "comm"), (t_wait, "#ef4444", "wait")]:
            w = val * scale
            if w > 0.5:
                parts.append(f'<rect x="{zero_x + stack:.1f}" y="{y + bar_h + 2:.1f}" width="{w:.1f}" height="{bar_h}" fill="{col}" opacity="0.85" rx="2"/>')
            stack += w

        # Delta annotation
        delta = b_jct - t_jct
        dx = zero_x + (10 if delta > 0 else -40)
        col = "#22c55e" if delta > 0 else "#ef4444"
        parts.append(svg_text(zero_x + stack + 6, y + bar_h + 16, f"{delta:+.1f}s", 9, "start", "700", col))

    # Legend
    ly = height - 20
    for dx, col, label in [(0, "#3b82f6", "compute"), (80, "#f59e0b", "comm"), (160, "#ef4444", "wait")]:
        parts.append(f'<rect x="{margin_l + dx:.0f}" y="{ly - 8:.0f}" width="14" height="10" fill="{col}" opacity="0.8" rx="2"/>')
        parts.append(svg_text(margin_l + dx + 18, ly, label, 10))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def write_ablation_bars(results_path: Path, out_path: Path) -> None:
    """Ablation gain decomposition bar chart."""
    rows = read_csv(results_path)
    if not rows:
        return

    base = next((r for r in rows if r["scheduler"] == "random_same"), rows[0])
    base_jct = float(base["avg_jct_s"])
    base_comm = float(base["avg_comm_s"])
    base_ms = float(base["makespan_s"])

    schedulers = [r["scheduler"] for r in rows]
    jct_gains = [(base_jct - float(r["avg_jct_s"])) / base_jct * 100 for r in rows]
    comm_gains = [(base_comm - float(r["avg_comm_s"])) / base_comm * 100 for r in rows]

    n = len(schedulers)
    bar_w = 36
    gap = 12
    width = max(480, margin_l := 140, margin_r := 60)
    plot_w = n * (bar_w * 2 + gap) - gap
    width = margin_l + plot_w + margin_r
    height = 340
    margin_t, margin_b = 48, 60
    plot_h = height - margin_t - margin_b
    max_val = max(max(jct_gains), max(comm_gains), 5) * 1.2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 24, "Ablation: JCT & Comm Gain vs random_same", 15, "middle", "700"),
    ]

    zero_y = margin_t + plot_h
    for i, (sched, jg, cg) in enumerate(zip(schedulers, jct_gains, comm_gains)):
        x = margin_l + i * (bar_w * 2 + gap)
        color = SCHED_COLORS.get(sched, "#333")
        # JCT bar
        jh = max(2, jg / max_val * plot_h)
        parts.append(f'<rect x="{x:.0f}" y="{zero_y - jh:.0f}" width="{bar_w}" height="{jh:.0f}" fill="{color}" rx="2"/>')
        parts.append(svg_text(x + bar_w / 2, zero_y - jh - 6, f"{jg:+.1f}%", 9, "middle", "600", color))
        # Comm bar
        ch = max(2, cg / max_val * plot_h)
        x2 = x + bar_w + 4
        parts.append(f'<rect x="{x2:.0f}" y="{zero_y - ch:.0f}" width="{bar_w}" height="{ch:.0f}" fill="{color}" opacity="0.45" rx="2"/>')
        parts.append(svg_text(x2 + bar_w / 2, zero_y - ch - 6, f"{cg:+.1f}%", 9, "middle", "400", color))
        # Label
        parts.append(svg_text(x + bar_w, zero_y + 16, sched.replace("_", " "), 9, "middle", "400", "#4b5563").replace(" ", "\n"))

    # Zero line
    parts.append(f'<line x1="{margin_l}" y1="{zero_y:.0f}" x2="{margin_l + plot_w}" y2="{zero_y:.0f}" stroke="#334155" stroke-width="1.5"/>')
    parts.append(svg_text(12, height / 2, "Gain %", 11, "middle", "400", "#6b7280", ).replace("middle", "start"))  # hack for vertical text
    # Legend
    parts.append(f'<rect x="{margin_l:.0f}" y="{height - 26:.0f}" width="14" height="10" fill="#22c55e" rx="2"/>')
    parts.append(svg_text(margin_l + 18, height - 18, "JCT gain", 10))
    parts.append(f'<rect x="{margin_l + 90:.0f}" y="{height - 26:.0f}" width="14" height="10" fill="#22c55e" opacity="0.45" rx="2"/>')
    parts.append(svg_text(margin_l + 108, height - 18, "Comm gain", 10))

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhanced SimGrid visualizations")
    parser.add_argument("--jobs", type=Path, help="Job-level CSV path")
    parser.add_argument("--results", type=Path, help="Aggregate results CSV path")
    parser.add_argument("--link-timeline-dir", type=Path, help="Directory with link timeline CSVs")
    parser.add_argument("--target", default="crux_no_compress")
    parser.add_argument("--baseline", default="random_same")
    parser.add_argument("--out-dir", type=Path, default=Path("results/vis_enhanced"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.results and args.results.exists():
        print("Generating ablation bars...")
        write_ablation_bars(args.results, args.out_dir / "ablation_bars.svg")

    if args.jobs and args.jobs.exists():
        print("Generating JCT breakdown...")
        write_breakdown_bars(args.jobs, args.out_dir / "breakdown.svg", args.target, args.baseline)

    if args.link_timeline_dir and args.link_timeline_dir.exists():
        timeline_files = {}
        for tf in args.link_timeline_dir.glob("*_timeline_*.csv"):
            # Extract scheduler name from filename like "default_links_timeline_crux_no_compress.csv"
            name = tf.stem
            for sched in SCHED_COLORS:
                if sched in name:
                    timeline_files[sched] = tf
                    break
        if timeline_files:
            print(f"Generating link heatmap ({len(timeline_files)} schedulers)...")
            write_link_heatmap(timeline_files, args.out_dir / "link_heatmap.svg")

    print(f"Visualizations written to {args.out_dir}")


if __name__ == "__main__":
    main()
