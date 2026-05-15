#!/usr/bin/env python3
"""Export SimGrid simulation data as JSON for the interactive web dashboard.

Reads job CSV + link timeline CSV → single JSON ready for dashboard.html.
Also supports generating staggered arrival times for dynamic playback.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def make_topo_spec(name: str, hosts: int, gpus_per_host: int) -> dict:
    """Mirrors topology.h presets, returns JSON-serializable dict."""
    spec: dict = {"name": name, "hosts": hosts, "gpus_per_host": gpus_per_host}
    if name == "star":
        spec.update({"nics_per_host": 1, "switch_levels": [{"count": 1, "label": "Core", "uplink_gbps": 320}]})
    elif name == "fat_tree":
        spec.update({"nics_per_host": 1, "switch_levels": [
            {"count": 4, "label": "ToR", "uplink_gbps": 200},
            {"count": 2, "label": "Spine", "uplink_gbps": 400}]})
    elif name == "three_tier_clos":
        spec.update({"nics_per_host": 1, "switch_levels": [
            {"count": 8, "label": "ToR", "uplink_gbps": 200},
            {"count": 4, "label": "Agg", "uplink_gbps": 400},
            {"count": 2, "label": "Core", "uplink_gbps": 800}]})
    elif name == "dragonfly":
        spec.update({"nics_per_host": 1, "switch_levels": [
            {"count": 4, "label": "Group", "uplink_gbps": 200},
            {"count": 2, "label": "Global", "uplink_gbps": 400}]})
    elif name == "ascend":
        spec.update({"nics_per_host": 2, "switch_levels": [
            {"count": hosts, "label": "Leaf", "uplink_gbps": 400},
            {"count": 4, "label": "Spine", "uplink_gbps": 800}]})
    else:
        spec.update({"nics_per_host": 1, "switch_levels": [
            {"count": 4, "label": "ToR", "uplink_gbps": 200},
            {"count": 2, "label": "Core", "uplink_gbps": 400}]})
    return spec


def compute_route_links(h1: int, g1: int, h2: int, g2: int, topo: dict, salt: int = 0) -> list[str]:
    """Compute link names along path (mirrors C++ build_platform)."""
    if h1 == h2:
        return [f"local{h1}"]
    nics = topo.get("nics_per_host", 1)
    nic1 = g1 % nics
    nic2 = g2 % nics
    links = [f"nic{h1}_{nic1}"]
    for lvl, sl in enumerate(topo.get("switch_levels", [])):
        idx = (h1 * 31 + h2 * 17 + lvl * 7 + salt * 13) % sl["count"]
        links.append(f"sw{lvl}_{idx}")
    links.append(f"nic{h2}_{nic2}")
    return links


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SimGrid data to web dashboard JSON")
    parser.add_argument("--jobs", type=Path, required=True, help="Job CSV from --job-out")
    parser.add_argument("--results", type=Path, default=None, help="Aggregate results CSV")
    parser.add_argument("--link-timeline-dir", type=Path, default=None, help="Directory with link timeline CSVs")
    parser.add_argument("--links", type=Path, default=None, help="Link aggregate CSV")
    parser.add_argument("--topology", default="three_tier_clos")
    parser.add_argument("--hosts", type=int, default=8)
    parser.add_argument("--gpus-per-host", type=int, default=8)
    parser.add_argument("--scheduler", default="crux_no_compress", help="Scheduler to export")
    parser.add_argument("--dynamic", action="store_true", help="Stagger job start times for dynamic playback")
    parser.add_argument("--dynamic-window", type=float, default=120.0, help="Time window to spread arrivals over (seconds)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("results/web_dashboard/data.json"))
    parser.add_argument("--merge-html", type=Path, default=None, help="Path to dashboard.html template; if set, produce self-contained merged HTML")
    args = parser.parse_args()

    rows = read_csv(args.jobs)
    if not rows:
        raise ValueError("empty jobs CSV")

    topo = make_topo_spec(args.topology, args.hosts, args.gpus_per_host)

    # Filter to target scheduler
    sched_rows = [r for r in rows if r["scheduler"] == args.scheduler]
    if not sched_rows:
        sched_rows = [r for r in rows if r["scheduler"] == "crux_no_compress"]
    if not sched_rows:
        sched_rows = rows

    # --- Jobs ---
    jobs: list[dict] = []
    all_times: list[float] = []
    for r in sched_rows:
        jid = int(r["job_id"])
        arrival = float(r.get("trace_start_s", 0))
        start = float(r.get("sim_start_s", 0))
        finish = float(r.get("sim_finish_s", 0))
        jct = float(r.get("jct_s", finish - start))
        comm = float(r.get("comm_s", 0))
        compute = float(r.get("compute_s", 0))
        model = r.get("model", "unknown")
        ranks = int(r.get("ranks", 8))
        intensity = float(r.get("intensity", 0))
        placement_str = r.get("placement", "")

        placement: list[list[int]] = []
        for part in placement_str.split(";"):
            try:
                h, g = part.split(":")
                placement.append([int(h), int(g)])
            except ValueError:
                pass

        # Compute ring paths for this job
        ring_paths = []
        n = len(placement)
        for step in range(max(1, 2 * (n - 1))):
          for i in range(n):
            h1, g1 = placement[i]
            h2, g2 = placement[(i + 1) % n]
            ring_paths.append(compute_route_links(h1, g1, h2, g2, topo, salt=jid * 97 + step * 17 + i))

        jobs.append({
            "id": jid,
            "model": model,
            "ranks": ranks,
            "arrival_s": round(arrival, 3),
            "start_s": round(start, 3),
            "finish_s": round(finish, 3),
            "jct_s": round(jct, 3),
            "comm_s": round(comm, 3),
            "compute_s": round(compute, 3),
            "intensity": round(intensity, 0),
            "placement": placement,
            "ring_paths": ring_paths,
            "cross_host_hops": sum(1 for i in range(n) if placement[i][0] != placement[(i+1)%n][0]),
        })
        all_times.append(finish)

    makespan = max(all_times) if all_times else 1.0

    # --- Dynamic arrival staggering ---
    if args.dynamic:
        rng = random.Random(args.seed)
        # Stagger arrivals: high-intensity jobs arrive earlier (they're "elephants")
        sorted_jobs = sorted(jobs, key=lambda j: -j["intensity"])
        current_time = 0.0
        for j in sorted_jobs:
            duration = max(0.001, j["finish_s"] - j["start_s"])
            # Random gap between 0 and window/N
            gap = rng.uniform(0, args.dynamic_window / len(sorted_jobs) * 2)
            current_time += gap
            j["arrival_s"] = round(current_time, 3)
            j["start_s"] = j["arrival_s"]  # assume immediate scheduling
            j["finish_s"] = round(j["arrival_s"] + duration, 3)
        # Recompute makespan
        makespan = max(j["finish_s"] for j in jobs)

    # --- Link timeline ---
    link_timeline: dict[str, list[list[float]]] = {}
    if args.link_timeline_dir:
        for tf in Path(args.link_timeline_dir).glob("*.csv"):
            # Extract scheduler name
            fname = tf.stem
            if args.scheduler not in fname:
                continue
            lrows = read_csv(tf)
            by_link: dict[str, list[tuple[float, float]]] = defaultdict(list)
            for lr in lrows:
                by_link[lr["link_name"]].append((float(lr["time_s"]), float(lr["cumulative_bytes"])))

            # Convert cumulative → instantaneous utilization (estimate from max delta)
            for link_name, points in by_link.items():
                if len(points) < 2:
                    continue
                # Estimate bandwidth
                max_bps = 1e9
                for i in range(1, len(points)):
                    db = points[i][1] - points[i-1][1]
                    dt = points[i][0] - points[i-1][0]
                    if dt > 0:
                        bps = db / dt
                        if bps > max_bps:
                            max_bps = bps
                max_bps = max(max_bps, 1e9)
                # Downsample to ~200 points
                stride = max(1, len(points) // 200)
                sampled: list[list[float]] = []
                for i in range(0, len(points), stride):
                    t = points[i][0]
                    if i > 0:
                        db = points[i][1] - points[i-1][1]
                        dt = points[i][0] - points[i-1][0]
                        util = min(1.0, (db / dt / max_bps)) if dt > 0 else 0
                    else:
                        util = 0
                    sampled.append([round(t, 3), round(util, 4)])
                link_timeline[link_name] = sampled

    # --- Link aggregate ---
    link_agg: dict[str, float] = {}
    if args.links and Path(args.links).exists():
        lrows = read_csv(args.links)
        for lr in lrows:
            if lr.get("scheduler", args.scheduler) == args.scheduler:
                link_agg[lr["link_name"]] = float(lr["utilization"])

    # --- GPU occupancy timeline ---
    # For each GPU, derive occupancy intervals from job placement + start/finish
    gpu_occupancy: dict[str, list[list[float]]] = {}
    for h in range(args.hosts):
        for g in range(args.gpus_per_host):
            gpu_occupancy[f"h{h}g{g}"] = []

    for j in jobs:
        for rank_pos, (h, g) in enumerate(j["placement"]):
            gid = f"h{h}g{g}"
            gpu_occupancy[gid].append([j["arrival_s"], j["finish_s"], j["id"]])

    # Sort and merge overlapping intervals per GPU
    for gid in gpu_occupancy:
        intervals = sorted(gpu_occupancy[gid], key=lambda x: x[0])
        gpu_occupancy[gid] = intervals

    # --- Metadata ---
    metadata: dict = {"makespan_s": round(makespan, 3), "total_gpus": args.hosts * args.gpus_per_host,
                       "total_jobs": len(jobs), "scheduler": args.scheduler}
    if args.results and Path(args.results).exists():
        rrows = read_csv(args.results)
        for rr in rrows:
            if rr["scheduler"] == args.scheduler:
                metadata["avg_jct_s"] = float(rr["avg_jct_s"])
                metadata["useful_gpu_fraction"] = float(rr["useful_gpu_fraction"])
                metadata["avg_comm_s"] = float(rr["avg_comm_s"])
                break

    # --- Assemble ---
    output = {
        "metadata": metadata,
        "topology": topo,
        "jobs": jobs,
        "gpu_occupancy": gpu_occupancy,
        "link_timeline": {k: v for k, v in sorted(link_timeline.items())},
        "link_aggregate": link_agg,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Exported {len(jobs)} jobs, {len(link_timeline)} link timelines → {args.out}")
    print(f"  makespan: {makespan:.1f}s, GPUs: {args.hosts * args.gpus_per_host}")
    print(f"  JSON size: {args.out.stat().st_size / 1024:.0f} KB")

    # Merge into self-contained HTML
    if args.merge_html:
        template = args.merge_html.read_text(encoding="utf-8")
        embedded_json = json.dumps(output, indent=2, ensure_ascii=False)
        old_load = """async function loadData() {
  try {
    const resp = await fetch('data.json');
    DATA = await resp.json();
    init();
  } catch(e) {
    document.body.innerHTML = `<div style="padding:40px;text-align:center"><h2>数据加载失败</h2><p>${e.message}</p><p>请确保 data.json 与本文件在同一目录</p></div>`;
  }
}"""
        new_load = f"""function loadData() {{
  const EMBEDDED_DATA = {embedded_json};
  DATA = EMBEDDED_DATA;
  init();
}}"""
        merged = template.replace(old_load, new_load)
        merged_path = args.out.parent / "dashboard.html"
        merged_path.write_text(merged, encoding="utf-8")
        print(f"  Merged HTML: {merged_path} ({merged_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
