#!/usr/bin/env python3
"""Compare simplified topologies vs a realistic ascend cluster topology.

Runs the SimGrid C++ simulator for each topology and produces a comparison report.
"""

import subprocess
import sys
import os
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parent
SIMGRID_LIB = "/Users/dkwyl/Documents/tmbProject/net/.simgrid_install/lib"
ENV_LIB = "/Users/dkwyl/Documents/tmbProject/net/.simgrid_env/lib"
BINARY = REPO / "simgrid_real" / "collective_sim"
BUILD_SH = REPO / "simgrid_real" / "build.sh"
PYTHON = "/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
MAMBA_PREFIX = "/Users/dkwyl/Documents/tmbProject/net/.mamba"
MICROMAMBA = "/Users/dkwyl/Documents/tmbProject/net/.tools/micromamba/bin/micromamba"
MAMBA_ENV = "/Users/dkwyl/Documents/tmbProject/net/.simgrid_env"

RESULTS_DIR = REPO / "results"
OUT_FILE = RESULTS_DIR / "topology_comparison_results.csv"
JOB_FILE = RESULTS_DIR / "topology_comparison_jobs.csv"

TOPOLOGIES = [
    ("star",           ["--hosts", "8", "--gpus-per-host", "4"]),
    ("three_tier_clos", ["--hosts", "8", "--gpus-per-host", "4"]),
    ("ascend",          ["--hosts", "8", "--gpus-per-host", "8"]),
]

SCHEDULERS = ["random_same", "random_intensity", "crux_no_compress", "crux"]
SEED = "7"
ROUNDS = "3"
JOBS = "12"

os.makedirs(RESULTS_DIR, exist_ok=True)


def build():
    """Build the C++ simulator."""
    print("=== Building collective_sim ===")
    env = os.environ.copy()
    env["MAMBA_ROOT_PREFIX"] = MAMBA_PREFIX
    result = subprocess.run(
        [MICROMAMBA, "run", "-p", MAMBA_ENV, str(BUILD_SH)],
        env=env, capture_output=True, text=True, cwd=str(REPO),
    )
    if result.returncode != 0:
        print("BUILD FAILED:", result.stderr[-500:])
        return False
    print("  build OK")
    return True


def run_sim(topology, extra_args, scheduler):
    """Run one simulation and return parsed results."""
    dyld = f"{SIMGRID_LIB}:{ENV_LIB}"
    args = [
        str(BINARY),
        "--scheduler", scheduler,
        "--topology", topology,
        "--out", str(OUT_FILE),
        "--job-out", str(JOB_FILE),
        "--seed", SEED,
        "--rounds", ROUNDS,
        "--jobs", JOBS,
        "--ranks", "8",
        "--placement-mode", "optimize",
        "--placement-objective", "balanced",
    ] + extra_args

    env = os.environ.copy()
    env["DYLD_LIBRARY_PATH"] = dyld

    print(f"  [{topology}/{scheduler}] ", end="", flush=True)
    result = subprocess.run(args, env=env, capture_output=True, text=True,
                           cwd=str(REPO), timeout=120)
    if result.returncode != 0:
        print("FAIL", result.stderr[-200:])
        return None
    # Parse the last CSV line
    lines = [l for l in result.stdout.strip().split("\n") if l and "," in l and "makespan" not in l]
    if lines:
        print(f"makespan={lines[-1].split(',')[6]}s")
    else:
        print("no output")
    return True


def main():
    # Clean output files
    for f in [OUT_FILE, JOB_FILE]:
        if f.exists():
            f.unlink()

    if not build():
        sys.exit(1)

    print("\n=== Running topology comparison ===")
    for topo_name, extra_args in TOPOLOGIES:
        for sched in SCHEDULERS:
            run_sim(topo_name, extra_args, sched)

    # Verify results
    if not OUT_FILE.exists():
        print("\nERROR: No results generated")
        sys.exit(1)

    with open(OUT_FILE) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"\n=== Results ({len(rows)} rows) ===")
    print(f"{'topology':<20} {'scheduler':<20} {'makespan':>10} {'avg_jct':>10} {'avg_comm':>10} {'GPU_frac':>8}")
    print("-" * 80)
    for r in rows:
        print(f"{r['topology']:<20} {r['scheduler']:<20} {float(r['makespan_s']):>10.3f} {float(r['avg_jct_s']):>10.3f} {float(r['avg_comm_s']):>10.3f} {float(r['useful_gpu_fraction']):>8.4f}")

    # Compute gains
    print("\n=== Crux gain vs random_same ===")
    for topo_name, _ in TOPOLOGIES:
        base = [r for r in rows if r['topology'] == topo_name and r['scheduler'] == 'random_same']
        crux = [r for r in rows if r['topology'] == topo_name and r['scheduler'] == 'crux_no_compress']
        if base and crux:
            b, c = base[0], crux[0]
            ms_gain = (float(b['makespan_s']) - float(c['makespan_s'])) / float(b['makespan_s']) * 100
            print(f"  {topo_name:<20} makespan gain: {ms_gain:+.1f}%")


if __name__ == "__main__":
    main()
