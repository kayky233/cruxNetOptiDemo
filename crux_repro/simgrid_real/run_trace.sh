#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="$ROOT/crux_repro/simgrid_real/collective_sim"
WORKLOAD="${1:-$ROOT/crux_repro/results/simgrid_trace_workload.csv}"
OUT="${2:-$ROOT/crux_repro/results/simgrid_real_trace_replay_results.csv}"
PLACEMENT_MODE="${3:-replay}"
PLACEMENT_OBJECTIVE="${4:-throughput}"
JOB_OUT="${5:-}"

rm -f "$OUT"
if [[ -n "$JOB_OUT" ]]; then
  rm -f "$JOB_OUT"
fi
for scheduler in random_same random_intensity crux_no_compress crux; do
  args=(
    --scheduler "$scheduler" \
    --workload-csv "$WORKLOAD" \
    --placement-mode "$PLACEMENT_MODE" \
    --placement-objective "$PLACEMENT_OBJECTIVE" \
    --seed 7 \
    --hosts 8 \
    --gpus-per-host 4 \
    --rounds 3 \
    --nic-gbps 100 \
    --core-gbps 320 \
    --local-gbps 400 \
    --out "$OUT"
  )
  if [[ -n "$JOB_OUT" ]]; then
    args+=(--job-out "$JOB_OUT")
  fi
  "$BIN" "${args[@]}"
done

cat "$OUT"
