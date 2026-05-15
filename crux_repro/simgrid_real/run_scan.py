#!/usr/bin/env python3
"""Automated parameter scan for SimGrid collective simulation.

Scans across: topology × scheduler × workload × background traffic × overlap.
Generates consolidated CSV results and a summary Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent  # crux_repro/
BIN = ROOT / "simgrid_real" / "collective_sim"
SIMGRID_LIB = os.environ.get(
    "SIMGRID_LIB",
    str(ROOT.parent / ".simgrid_install" / "lib"),
)


@dataclass
class ScanCase:
    name: str
    topology: str = "three_tier_clos"
    scheduler: Optional[str] = None  # None = run all 6
    workload_csv: Optional[str] = None  # None = synthetic
    comm_plan: str = "ring"
    hosts: int = 8
    gpus_per_host: int = 8
    jobs: int = 12
    ranks: int = 8
    rounds: int = 3
    placement_mode: str = "optimize"
    placement_objective: str = "balanced"
    overlap_ratio: float = 0.0
    seed: int = 7
    bg_checkpoint_gib: float = 0
    bg_inference_mbps: float = 0
    bg_dataset_pct: float = 0
    perturb_link_gbps: float = 0
    perturb_time_s: float = 0
    local_gbps: int = 400
    nic_gbps: int = 100
    core_gbps: int = 320
    extra_args: list[str] = field(default_factory=list)


ALL_SCHEDULERS = [
    "random_same",
    "random_intensity",
    "place_only",
    "priority_only",
    "crux_no_compress",
    "crux",
]

ALL_TOPOLOGIES = ["star", "fat_tree", "three_tier_clos", "dragonfly", "ascend"]


def build_scan_plan(args: argparse.Namespace) -> list[ScanCase]:
    """Generate the list of scan cases based on CLI flags."""
    cases: list[ScanCase] = []

    # --- Phase 1: Topology comparison (trace-driven) ---
    if args.scan_topology:
        workload = str(args.workload_csv) if args.workload_csv else None
        for topo in ALL_TOPOLOGIES:
            cases.append(
                ScanCase(
                    name=f"topo_{topo}",
                    topology=topo,
                    workload_csv=workload,
                    jobs=args.jobs,
                    hosts=args.hosts,
                    gpus_per_host=args.gpus_per_host,
                    ranks=args.ranks,
                    rounds=args.rounds,
                    placement_mode=args.placement_mode,
                    placement_objective=args.placement_objective,
                    seed=args.seed,
                )
            )

    # --- Phase 2: Scale pressure test (synthetic) ---
    if args.scan_scale:
        scales = [
            ("small", 12, 8),
            ("medium", 24, 16),
            ("large", 48, 24),
            ("xl", 72, 32),
        ]
        for label, jobs, hosts in scales:
            cases.append(
                ScanCase(
                    name=f"scale_{label}",
                    topology=args.topology,
                    jobs=jobs,
                    hosts=hosts,
                    gpus_per_host=8,
                    ranks=8,
                    rounds=args.rounds,
                    placement_mode="optimize",
                    placement_objective="balanced",
                    seed=args.seed,
                )
            )

    # --- Phase 3: Background traffic scenarios ---
    if args.scan_bg:
        bg_scenarios = [
            ("clean", 0, 0, 0),
            ("checkpoint_5gib", 5.0, 0, 0),
            ("checkpoint_10gib", 10.0, 0, 0),
            ("inference_500mbps", 0, 500, 0),
            ("inference_2000mbps", 0, 2000, 0),
            ("dataset_30pct", 0, 0, 30),
            ("mixed", 5.0, 500, 20),
        ]
        workload = str(args.workload_csv) if args.workload_csv else None
        for label, ckpt, infer, ds in bg_scenarios:
            cases.append(
                ScanCase(
                    name=f"bg_{label}",
                    topology=args.topology,
                    workload_csv=workload,
                    jobs=args.jobs,
                    hosts=args.hosts,
                    gpus_per_host=args.gpus_per_host,
                    ranks=args.ranks,
                    rounds=args.rounds,
                    placement_mode=args.placement_mode,
                    placement_objective=args.placement_objective,
                    seed=args.seed,
                    bg_checkpoint_gib=ckpt,
                    bg_inference_mbps=infer,
                    bg_dataset_pct=ds,
                )
            )

    # --- Phase 4: Overlap ratio sweep ---
    if args.scan_overlap:
        workload = str(args.workload_csv) if args.workload_csv else None
        for ov in [0.0, 0.15, 0.30, 0.50, 0.70]:
            cases.append(
                ScanCase(
                    name=f"overlap_{ov:.2f}",
                    topology=args.topology,
                    workload_csv=workload,
                    jobs=args.jobs,
                    hosts=args.hosts,
                    gpus_per_host=args.gpus_per_host,
                    ranks=args.ranks,
                    rounds=args.rounds,
                    placement_mode=args.placement_mode,
                    placement_objective=args.placement_objective,
                    seed=args.seed,
                    overlap_ratio=ov,
                )
            )

    # --- Phase 5: Comm plan comparison ---
    if args.scan_comm_plan:
        workload = str(args.workload_csv) if args.workload_csv else None
        for plan in ["ring", "tree", "hierarchical", "pipeline"]:
            cases.append(
                ScanCase(
                    name=f"comm_{plan}",
                    topology=args.topology,
                    comm_plan=plan,
                    workload_csv=workload,
                    jobs=args.jobs,
                    hosts=args.hosts,
                    gpus_per_host=args.gpus_per_host,
                    ranks=args.ranks,
                    rounds=args.rounds,
                    placement_mode=args.placement_mode,
                    placement_objective=args.placement_objective,
                    seed=args.seed,
                )
            )

    # --- Default: single ablation scan ---
    if not cases:
        workload = str(args.workload_csv) if args.workload_csv else None
        cases.append(
            ScanCase(
                name="default",
                topology=args.topology,
                workload_csv=workload,
                jobs=args.jobs,
                hosts=args.hosts,
                gpus_per_host=args.gpus_per_host,
                ranks=args.ranks,
                rounds=args.rounds,
                placement_mode=args.placement_mode,
                placement_objective=args.placement_objective,
                seed=args.seed,
                overlap_ratio=args.overlap,
                bg_checkpoint_gib=args.bg_checkpoint,
                bg_inference_mbps=args.bg_inference,
                bg_dataset_pct=args.bg_dataset,
            )
        )

    return cases


def run_case(case: ScanCase, out_dir: Path) -> list[dict[str, str]]:
    """Run all schedulers for one scan case. Returns list of result rows."""
    schedulers = [case.scheduler] if case.scheduler else ALL_SCHEDULERS
    out_csv = out_dir / f"{case.name}_results.csv"
    jobs_csv = out_dir / f"{case.name}_jobs.csv"
    link_csv = out_dir / f"{case.name}_links.csv"
    out_csv.unlink(missing_ok=True)
    jobs_csv.unlink(missing_ok=True)
    link_csv.unlink(missing_ok=True)

    env = os.environ.copy()
    env["DYLD_LIBRARY_PATH"] = SIMGRID_LIB

    for sched in schedulers:
        cmd = [
            str(BIN),
            "--scheduler", sched,
            "--topology", case.topology,
            "--comm-plan", case.comm_plan,
            "--hosts", str(case.hosts),
            "--gpus-per-host", str(case.gpus_per_host),
            "--jobs", str(case.jobs),
            "--ranks", str(case.ranks),
            "--rounds", str(case.rounds),
            "--seed", str(case.seed),
            "--placement-mode", case.placement_mode,
            "--placement-objective", case.placement_objective,
            "--overlap-ratio", str(case.overlap_ratio),
            "--local-gbps", str(case.local_gbps),
            "--nic-gbps", str(case.nic_gbps),
            "--core-gbps", str(case.core_gbps),
            "--out", str(out_csv),
            "--job-out", str(jobs_csv),
            "--link-out", str(link_csv),
        ]
        if case.workload_csv:
            cmd += ["--workload-csv", case.workload_csv]
        if case.bg_checkpoint_gib > 0:
            cmd += ["--bg-checkpoint-gib", str(case.bg_checkpoint_gib)]
        if case.bg_inference_mbps > 0:
            cmd += ["--bg-inference-mbps", str(case.bg_inference_mbps)]
        if case.bg_dataset_pct > 0:
            cmd += ["--bg-dataset-pct", str(case.bg_dataset_pct)]
        if case.perturb_link_gbps > 0:
            cmd += ["--perturb-link-gbps", str(case.perturb_link_gbps)]
        if case.perturb_time_s > 0:
            cmd += ["--perturb-time-s", str(case.perturb_time_s)]
        cmd += case.extra_args

        print(f"  [{case.name}] scheduler={sched} ...", end=" ", flush=True)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(ROOT.parent),
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )
            if result.returncode != 0:
                print(f"FAIL (exit={result.returncode})")
                print(f"  stderr: {result.stderr[:200]}")
            else:
                # Parse makespan from stderr (last line)
                for line in result.stderr.strip().split("\n"):
                    if "makespan=" in line:
                        print(f"OK ({line.strip()})")
                        break
                else:
                    print("OK")
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
        except FileNotFoundError:
            print(f"BINARY NOT FOUND: {BIN}")
            return []

    # Read results
    rows: list[dict[str, str]] = []
    if out_csv.exists():
        with out_csv.open(newline="") as f:
            rows = list(csv.DictReader(f))
    return rows


def generate_scan_report(all_results: dict[str, list[dict[str, str]]], out_dir: Path) -> None:
    """Generate a summary Markdown report for the entire scan."""
    lines = [
        "# SimGrid 参数扫描汇总报告",
        "",
        f"扫描时间：自动生成",
        f"场景数：{len(all_results)}",
        "",
        "## 各场景最优策略",
        "",
        "| 场景 | best makespan | best JCT | best comm | best GPU frac |",
        "|---|---:|---:|---:|---:|",
    ]

    for name, rows in all_results.items():
        if not rows:
            continue
        best_ms = min(rows, key=lambda r: float(r["makespan_s"]))
        best_jct = min(rows, key=lambda r: float(r["avg_jct_s"]))
        best_comm = min(rows, key=lambda r: float(r["avg_comm_s"]))
        best_ugf = max(rows, key=lambda r: float(r["useful_gpu_fraction"]))
        lines.append(
            f"| {name} | `{best_ms['scheduler']}` ({float(best_ms['makespan_s']):.1f}s) | "
            f"`{best_jct['scheduler']}` ({float(best_jct['avg_jct_s']):.1f}s) | "
            f"`{best_comm['scheduler']}` ({float(best_comm['avg_comm_s']):.1f}s) | "
            f"`{best_ugf['scheduler']}` ({float(best_ugf['useful_gpu_fraction']):.3f}) |"
        )

    # Per-scenario detail
    for name, rows in all_results.items():
        if not rows:
            continue
        lines.append(f"")
        lines.append(f"## {name}")
        lines.append(f"")
        base = next((r for r in rows if r["scheduler"] == "random_same"), rows[0])
        base_ms = float(base["makespan_s"])
        base_jct = float(base["avg_jct_s"])
        base_comm = float(base["avg_comm_s"])

        def gain_str(b, v):
            g = (b - v) / b * 100 if b else 0
            return f"{g:+.1f}%"

        lines.append("| scheduler | makespan | vs base | JCT | vs base | comm | vs base | ugf |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in rows:
            ms = float(r["makespan_s"])
            jct = float(r["avg_jct_s"])
            comm = float(r["avg_comm_s"])
            ugf = float(r["useful_gpu_fraction"])
            lines.append(
                f"| `{r['scheduler']}` | {ms:.2f} | {gain_str(base_ms, ms)} | "
                f"{jct:.2f} | {gain_str(base_jct, jct)} | {comm:.2f} | {gain_str(base_comm, comm)} | {ugf:.3f} |"
            )

    report_path = out_dir / "scan_summary.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSummary report: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated SimGrid parameter scanner")
    parser.add_argument("--topology", default="three_tier_clos")
    parser.add_argument("--workload-csv", type=Path, default=None)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--hosts", type=int, default=8)
    parser.add_argument("--gpus-per-host", type=int, default=8)
    parser.add_argument("--ranks", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--placement-mode", default="optimize")
    parser.add_argument("--placement-objective", default="balanced")
    parser.add_argument("--overlap", type=float, default=0.0)
    parser.add_argument("--bg-checkpoint", type=float, default=0)
    parser.add_argument("--bg-inference", type=float, default=0)
    parser.add_argument("--bg-dataset", type=float, default=0)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results" / "scan")

    # Phase toggles
    parser.add_argument("--scan-topology", action="store_true", help="Scan all 5 topologies")
    parser.add_argument("--scan-scale", action="store_true", help="Scan job/host scale stress test")
    parser.add_argument("--scan-bg", action="store_true", help="Scan background traffic scenarios")
    parser.add_argument("--scan-overlap", action="store_true", help="Scan overlap ratios")
    parser.add_argument("--scan-comm-plan", action="store_true", help="Scan comm plans")
    parser.add_argument("--all", action="store_true", help="Enable all scan phases")

    args = parser.parse_args()

    if args.all:
        args.scan_topology = True
        args.scan_scale = True
        args.scan_bg = True
        args.scan_overlap = True
        args.scan_comm_plan = True

    if not os.path.exists(BIN):
        print(f"Binary not found: {BIN}")
        print("Run build.sh first.")
        sys.exit(1)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    cases = build_scan_plan(args)
    print(f"Scan plan: {len(cases)} scenarios × up to {len(ALL_SCHEDULERS)} schedulers")
    print(f"Output dir: {args.out_dir}")
    print()

    all_results: dict[str, list[dict[str, str]]] = {}
    for i, case in enumerate(cases):
        print(f"[{i+1}/{len(cases)}] {case.name}")
        rows = run_case(case, args.out_dir)
        all_results[case.name] = rows
        print()

    generate_scan_report(all_results, args.out_dir)


if __name__ == "__main__":
    main()
