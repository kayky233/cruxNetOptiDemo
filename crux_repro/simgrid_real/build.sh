#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIMGRID_PREFIX="$ROOT/.simgrid_install"
DEPS_PREFIX="$ROOT/.simgrid_env"
SRC_DIR="$ROOT/crux_repro/simgrid_real"
OUT="$SRC_DIR/collective_sim"

export PKG_CONFIG_PATH="$SIMGRID_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export DYLD_LIBRARY_PATH="$SIMGRID_PREFIX/lib:${DYLD_LIBRARY_PATH:-}"

c++ -std=c++17 -O2 \
  "$SRC_DIR/collective_sim.cpp" \
  -I"$DEPS_PREFIX/include" \
  -I"$SRC_DIR" \
  -L"$DEPS_PREFIX/lib" \
  $(pkg-config --cflags --libs simgrid) \
  -Wl,-rpath,"$SIMGRID_PREFIX/lib" \
  -Wl,-rpath,"$DEPS_PREFIX/lib" \
  -o "$OUT"

echo "$OUT"
