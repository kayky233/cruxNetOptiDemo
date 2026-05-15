#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="$ROOT/crux_repro/simgrid_real/collective_sim"
WORKLOAD="${1:-$ROOT/crux_repro/results/simgrid_trace_workload.csv}"
OUT="${2:-$ROOT/crux_repro/results/simgrid_real_trace_replay_results.csv}"
PLACEMENT_MODE="${3:-replay}"
PLACEMENT_OBJECTIVE="${4:-throughput}"
JOB_OUT="${5:-}"
LINK_OUT="${6:-}"
LINK_TIMELINE_OUT="${7:-}"
OVERLAP="${8:-0.0}"

rm -f "$OUT"
if [[ -n "$JOB_OUT" ]]; then rm -f "$JOB_OUT"; fi
if [[ -n "$LINK_OUT" ]]; then rm -f "$LINK_OUT"; fi
if [[ -n "$LINK_TIMELINE_OUT" ]]; then rm -f "$LINK_TIMELINE_OUT"; fi

# Ablation: 6 schedulers covering placement × priority × compression
SCHEDULERS=(random_same random_intensity place_only priority_only crux_no_compress crux)

for scheduler in "${SCHEDULERS[@]}"; do
  args=(
    --scheduler "$scheduler"
    --workload-csv "$WORKLOAD"
    --placement-mode "$PLACEMENT_MODE"
    --placement-objective "$PLACEMENT_OBJECTIVE"
    --seed 7
    --hosts 8
    --gpus-per-host 8
    --rounds 3
    --nic-gbps 100
    --core-gbps 320
    --local-gbps 400
    --overlap-ratio "$OVERLAP"
    --out "$OUT"
  )
  if [[ -n "$JOB_OUT" ]]; then args+=(--job-out "$JOB_OUT"); fi
  if [[ -n "$LINK_OUT" ]]; then args+=(--link-out "$LINK_OUT"); fi
  if [[ -n "$LINK_TIMELINE_OUT" ]]; then
    timeline_file="${LINK_TIMELINE_OUT%.csv}_${scheduler}.csv"
    args+=(--link-timeline-out "$timeline_file")
  fi
  echo "=== Running scheduler=$scheduler mode=$PLACEMENT_MODE obj=$PLACEMENT_OBJECTIVE overlap=$OVERLAP ==="
  "$BIN" "${args[@]}"
done

echo "=== Results ==="
cat "$OUT"
