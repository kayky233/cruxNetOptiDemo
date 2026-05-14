#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIMGRID_PREFIX="$ROOT/.simgrid_install"
DEPS_PREFIX="$ROOT/.simgrid_env"
OUT="$ROOT/crux_repro/simgrid_real/collective_sim"

export PKG_CONFIG_PATH="$SIMGRID_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export DYLD_LIBRARY_PATH="$SIMGRID_PREFIX/lib:${DYLD_LIBRARY_PATH:-}"

c++ -std=c++17 -O2 \
  "$ROOT/crux_repro/simgrid_real/collective_sim.cpp" \
  -I"$DEPS_PREFIX/include" \
  -L"$DEPS_PREFIX/lib" \
  $(pkg-config --cflags --libs simgrid) \
  -Wl,-rpath,"$SIMGRID_PREFIX/lib" \
  -Wl,-rpath,"$DEPS_PREFIX/lib" \
  -o "$OUT"

echo "$OUT"
