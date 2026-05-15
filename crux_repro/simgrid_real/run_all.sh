#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="$ROOT/crux_repro/simgrid_real/collective_sim"
OUT="${1:-$ROOT/crux_repro/results/simgrid_real_collective_results.csv}"

rm -f "$OUT"
for scheduler in random_same random_intensity crux_no_compress crux; do
  "$BIN" \
    --scheduler "$scheduler" \
    --seed 7 \
    --hosts 8 \
    --gpus-per-host 8 \
    --jobs 12 \
    --ranks 8 \
    --rounds 4 \
    --nic-gbps 100 \
    --core-gbps 320 \
    --local-gbps 400 \
    --out "$OUT"
done

cat "$OUT"
