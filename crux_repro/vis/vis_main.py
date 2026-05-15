"""Visualization CLI entry point.

Phase 1: generate 6 SVG charts from existing CSV data.
Usage:
    python -m vis.vis_main --results ... --jobs ... --out-dir results/vis/
"""

import argparse
import os
import sys

from .vis_utils import setup_mpl
from .vis_intensity import plot_intensity
from .vis_job_compare import plot_job_compare
from .vis_gantt import plot_gantt
from .vis_placement import plot_placement
from .vis_topo import plot_topology
from .vis_path import plot_path_heatmap
from .vis_report import generate_report

ALL_CHARTS = ["intensity", "job_compare", "gantt", "placement", "topo", "path"]

def main():
    p = argparse.ArgumentParser(description="Crux/SimGrid Phase 1 Visualization")
    p.add_argument("--results", default="results/simgrid_real_trace_optimize_balanced_results.csv",
                   help="Scheduler-level results CSV")
    p.add_argument("--jobs", default="results/simgrid_real_trace_optimize_balanced_jobs.csv",
                   help="Job-level CSV")
    p.add_argument("--topology", default="three_tier_clos",
                   choices=["star", "fat_tree", "three_tier_clos", "dragonfly", "ascend"],
                   help="Network topology name")
    p.add_argument("--hosts", type=int, default=8)
    p.add_argument("--gpus-per-host", type=int, default=4)
    p.add_argument("--baseline", default="random_same")
    p.add_argument("--crux", default="crux_no_compress")
    p.add_argument("--out-dir", default="results/vis")
    p.add_argument("--charts", default="all",
                   help=f"Comma-separated chart names or 'all'. Options: {','.join(ALL_CHARTS)}")
    p.add_argument("--no-report", action="store_true", help="Skip report generation")
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    setup_mpl()

    charts = ALL_CHARTS if args.charts == "all" else args.charts.split(",")
    charts = [c.strip() for c in charts]
    unknown = [c for c in charts if c not in ALL_CHARTS]
    if unknown:
        print(f"Unknown charts: {unknown}. Options: {ALL_CHARTS}")
        sys.exit(1)

    generated = []

    if "intensity" in charts:
        print("[vis] Intensity distribution...")
        plot_intensity(args.jobs, topology_name=args.topology,
                       out_dir=args.out_dir)
        generated.append("intensity_distribution")

    if "job_compare" in charts:
        print("[vis] Job JCT/Comm comparison...")
        plot_job_compare(args.jobs, baseline=args.baseline, crux=args.crux,
                         topology_name=args.topology,
                         out_dir=args.out_dir)
        generated.append("job_jct_comm_comparison")

    if "gantt" in charts:
        print("[vis] Job Gantt chart...")
        plot_gantt(args.jobs, baseline=args.baseline, crux=args.crux,
                   topology_name=args.topology,
                   out_dir=args.out_dir)
        generated.append("gantt_comparison")

    if "placement" in charts:
        print("[vis] GPU placement heatmap...")
        plot_placement(args.jobs, baseline=args.baseline, crux=args.crux,
                       hosts=args.hosts, gpus_per_host=args.gpus_per_host,
                       topology_name=args.topology,
                       out_dir=args.out_dir)
        generated.append("placement_heatmap")

    if "topo" in charts:
        print("[vis] Network topology diagram...")
        plot_topology(topology_name=args.topology,
                      hosts=args.hosts, gpus_per_host=args.gpus_per_host,
                      out_dir=args.out_dir)
        generated.append("topology_diagram")

    if "path" in charts:
        print("[vis] Switch path heatmap...")
        plot_path_heatmap(args.jobs, topology_name=args.topology,
                          hosts=args.hosts, gpus_per_host=args.gpus_per_host,
                          baseline=args.baseline, crux=args.crux,
                          out_dir=args.out_dir)
        generated.append("path_switch_heatmap")

    if not args.no_report:
        print("[vis] Generating report...")
        generate_report(args.results, args.jobs, args.baseline, args.crux,
                        generated, args.out_dir, topology_name=args.topology)

    print(f"[vis] Done. {len(generated)} charts + report → {args.out_dir}/")


if __name__ == "__main__":
    main()
