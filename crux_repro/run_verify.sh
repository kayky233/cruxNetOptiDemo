#!/bin/bash
# Crux verification experiments — 6 groups of parameter sweeps
# Optimized: uses smaller job counts for high-K experiments to avoid
# combinatorial explosion in priority compression.
set -euo pipefail

PY=/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
SCRIPT=/Users/dkwyl/Documents/tmbProject/net/crux_repro/crux_sim.py
OUTDIR=/Users/dkwyl/Documents/tmbProject/net/crux_repro/results

echo "=========================================="
echo "Group 1: Priority Level Sensitivity (K=1,2,3,4,6) — 12 jobs"
echo "=========================================="
for K in 1 2 3 4 6; do
  echo "--- K=$K ---"
  $PY $SCRIPT --seed 7 --rounds 20 --jobs 12 --hosts 8 --gpus-per-host 8 --aggs 4 --priority-levels $K --out $OUTDIR/verify_k${K}.csv
done

echo ""
echo "=========================================="
echo "Group 2: Scale Sweep"
echo "=========================================="
echo "--- small (12 jobs, 8 hosts) ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 12 --hosts 8 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_scale_small.csv
echo "--- medium (24 jobs, 16 hosts) ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 24 --hosts 16 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_scale_medium.csv
echo "--- large (48 jobs, 24 hosts) ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 48 --hosts 24 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_scale_large.csv
echo "--- xl (72 jobs, 32 hosts) ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 72 --hosts 32 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_scale_xl.csv

echo ""
echo "=========================================="
echo "Group 3: Aggregation Path Count (aggs=2,4,8) — 24 jobs"
echo "=========================================="
for AGGS in 2 4 8; do
  echo "--- aggs=$AGGS ---"
  $PY $SCRIPT --seed 7 --rounds 20 --jobs 24 --hosts 16 --gpus-per-host 8 --aggs $AGGS --priority-levels 4 --out $OUTDIR/verify_aggs${AGGS}.csv
done

echo ""
echo "=========================================="
echo "Group 4: GPU Density — 24 jobs"
echo "=========================================="
echo "--- 4 GPUs/host ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 24 --hosts 16 --gpus-per-host 4 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_gpu4.csv
echo "--- 16 GPUs/host ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 24 --hosts 16 --gpus-per-host 16 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_gpu16.csv

echo ""
echo "=========================================="
echo "Group 5: Multi-seed Robustness — 24 jobs"
echo "=========================================="
for SEED in 42 100 2024; do
  echo "--- seed=$SEED ---"
  $PY $SCRIPT --seed $SEED --rounds 20 --jobs 24 --hosts 16 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_seed${SEED}.csv
done

echo ""
echo "=========================================="
echo "Group 6: Extreme Congestion"
echo "=========================================="
echo "--- extreme1 (48 jobs, 8 hosts) ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 48 --hosts 8 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_extreme1.csv
echo "--- extreme2 (64 jobs, 12 hosts) ---"
$PY $SCRIPT --seed 7 --rounds 20 --jobs 64 --hosts 12 --gpus-per-host 8 --aggs 4 --priority-levels 4 --out $OUTDIR/verify_extreme2.csv

echo ""
echo "=== ALL GROUPS DONE ==="
