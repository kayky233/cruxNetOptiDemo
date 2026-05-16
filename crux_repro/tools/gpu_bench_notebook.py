#!/usr/bin/env python3
"""
GPU/NPU communication micro-benchmark for Crux calibration.

This script is intentionally conservative on Ascend NPU:
- it avoids large torch.randn() on device, which can launch random-generation
  kernels and trigger AICore timeout before the copy benchmark starts;
- it avoids single-process manual cross-NPU allreduce on torch_npu, because
  implicit cross-device arithmetic may route through fragile TVM kernels;
- it records pairwise P2P copy bandwidth, which is the safest first signal for
  topology-aware scheduling calibration.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-devices", type=int, default=8, help="Maximum devices to test")
    parser.add_argument("--size-mb", type=int, default=16, help="P2P tensor size in MB; keep small on NPU first")
    parser.add_argument("--intra-size-mb", type=int, default=64, help="Single-device copy tensor size in MB")
    parser.add_argument("--iters", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--json-out", type=Path, default=Path("npu_bench_result.json"))
    parser.add_argument("--unsafe-manual-allreduce", action="store_true",
                        help="Run old single-process manual allreduce. Not recommended on torch_npu.")
    return parser.parse_args()


def print_header() -> None:
    print("=" * 56)
    print("  GPU/NPU Communication Micro-Benchmark")
    print("=" * 56)


def sync_device(torch: Any, kind: str, index: int | None = None) -> None:
    if kind == "cuda":
        if index is None:
            torch.cuda.synchronize()
        else:
            with torch.cuda.device(index):
                torch.cuda.synchronize()
    elif kind == "npu":
        if index is not None and hasattr(torch.npu, "set_device"):
            torch.npu.set_device(index)
        # torch_npu 2.1 exposes synchronize() globally; setting device first
        # avoids accidentally syncing another device after a pairwise test.
        torch.npu.synchronize()


def empty_tensor(torch: Any, numel: int, device: str) -> Any:
    # Do not use randn() for bandwidth tests on Ascend. Large random generation
    # can produce Mul kernels and AICore timeouts unrelated to communication.
    return torch.empty(numel, dtype=torch.float32, device=device)


def measure_copy(torch: Any, src: Any, dst: Any, kind: str, dst_idx: int, size_mb: int, iters: int, warmup: int) -> dict[str, Any]:
    for _ in range(warmup):
        dst.copy_(src, non_blocking=False)
    sync_device(torch, kind, dst_idx)

    samples_ms: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        dst.copy_(src, non_blocking=False)
        sync_device(torch, kind, dst_idx)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    mean_ms = statistics.mean(samples_ms)
    gbps = size_mb / (mean_ms / 1000.0) / 1024.0
    return {
        "mean_ms": round(mean_ms, 4),
        "p50_ms": round(statistics.median(samples_ms), 4),
        "bandwidth_GBps": round(gbps, 4),
        "samples_ms": [round(x, 4) for x in samples_ms],
    }


def main() -> None:
    args = parse_args()
    print_header()

    try:
        import torch
    except ImportError:
        print("PyTorch: NOT INSTALLED")
        return

    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")

    has_npu = False
    torch_npu_version = None
    try:
        import torch_npu  # noqa: F401
        torch_npu_version = getattr(torch_npu, "__version__", "installed")
        has_npu = hasattr(torch, "npu") and torch.npu.is_available()
        print(f"torch_npu: {torch_npu_version}")
        print(f"NPU available: {has_npu}")
        if has_npu:
            print(f"NPU count:    {torch.npu.device_count()}")
    except ImportError:
        print("torch_npu: NOT INSTALLED (non-Ascend platform)")

    has_gpu = torch.cuda.is_available()
    kind = "cuda" if has_gpu else "npu" if has_npu else "cpu"
    n_dev = torch.cuda.device_count() if kind == "cuda" else torch.npu.device_count() if kind == "npu" else 0
    n_test = min(n_dev, args.max_devices)

    print(f"\nPlatform: {sys.platform}")
    print(f"Hostname: {platform.node() or os.uname().nodename}")
    print(f"Device: {kind}, test_devices={n_test}")

    result: dict[str, Any] = {
        "schema_version": "crux-device-bench/v1",
        "platform": sys.platform,
        "hostname": platform.node() or os.uname().nodename,
        "pytorch": torch.__version__,
        "torch_npu": torch_npu_version,
        "device_type": kind,
        "device_count": n_dev,
        "config": vars(args) | {"json_out": str(args.json_out)},
        "intra_device": {},
        "p2p": [],
        "allreduce": {"status": "skipped"},
        "notes": [],
    }

    if kind == "cpu" or n_test == 0:
        print("No GPU/NPU detected; skipping.")
        args.json_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return

    print("\n--- Cell H: Device Copy Bandwidth Test ---")
    print("Allocation uses torch.empty(), not torch.randn(), to avoid unrelated NPU random kernels.")

    try:
        numel = args.intra_size_mb * 1024 * 1024 // 4
        dev = f"{kind}:0"
        if kind == "npu":
            torch.npu.set_device(0)
        src = empty_tensor(torch, numel, dev)
        dst = empty_tensor(torch, numel, dev)
        row = measure_copy(torch, src, dst, kind, 0, args.intra_size_mb, args.iters, args.warmup)
        result["intra_device"] = row
        print(f"Intra-device copy: {row['bandwidth_GBps']:.2f} GB/s ({args.intra_size_mb} MB)")
        del src, dst
    except Exception as exc:
        result["intra_device"] = {"error": repr(exc)}
        result["notes"].append("intra_device_failed")
        print(f"  intra-device failed: {exc!r}")

    if n_test >= 2:
        print(f"\nP2P bandwidth matrix ({n_test} devices, {args.size_mb} MB):")
        header = "src\\dst " + " ".join(f"{i:>9}" for i in range(n_test))
        print(header)
        matrix: list[list[str]] = []
        for src_idx in range(n_test):
            row_text = [f"{src_idx:>7}"]
            row_values: list[str] = []
            for dst_idx in range(n_test):
                if src_idx == dst_idx:
                    row_text.append(f"{'--':>9}")
                    row_values.append("--")
                    continue
                try:
                    n_elem = args.size_mb * 1024 * 1024 // 4
                    if kind == "npu":
                        torch.npu.set_device(src_idx)
                    src = empty_tensor(torch, n_elem, f"{kind}:{src_idx}")
                    if kind == "npu":
                        torch.npu.set_device(dst_idx)
                    dst = empty_tensor(torch, n_elem, f"{kind}:{dst_idx}")
                    m = measure_copy(torch, src, dst, kind, dst_idx, args.size_mb, args.iters, args.warmup)
                    result["p2p"].append({"src": src_idx, "dst": dst_idx, **m})
                    row_text.append(f"{m['bandwidth_GBps']:>9.2f}")
                    row_values.append(f"{m['bandwidth_GBps']:.2f}")
                    del src, dst
                except Exception as exc:
                    result["p2p"].append({"src": src_idx, "dst": dst_idx, "error": repr(exc)})
                    row_text.append(f"{'ERR':>9}")
                    row_values.append("ERR")
                    result["notes"].append(f"p2p_failed_{src_idx}_to_{dst_idx}")
            matrix.append(row_values)
            print(" ".join(row_text))
        result["p2p_matrix_GBps"] = matrix
    else:
        print("(single device; skipping P2P)")

    print("\n--- Cell I: AllReduce Benchmark ---")
    if kind == "npu" and not args.unsafe_manual_allreduce:
        print("Skipped on NPU by default.")
        print("Reason: single-process manual cross-NPU arithmetic can trigger AICore timeout.")
        print("Use torchrun + torch.distributed.all_reduce(backend='hccl') for the next-stage collective benchmark.")
        result["allreduce"] = {
            "status": "skipped",
            "reason": "manual single-process NPU allreduce is unsafe; use HCCL distributed benchmark",
        }
    else:
        print("Manual allreduce is disabled in this safe script revision.")
        result["allreduce"] = {"status": "disabled"}

    print("\n--- Cell J: Suggested SimGrid Parameters ---")
    p2p_ok = [x["bandwidth_GBps"] for x in result["p2p"] if "bandwidth_GBps" in x]
    if p2p_ok:
        print(f"intra_host_bw_fast_GBps: {max(p2p_ok):.2f}")
        print(f"intra_host_bw_median_GBps: {statistics.median(p2p_ok):.2f}")
        print(f"intra_host_bw_slow_GBps: {min(p2p_ok):.2f}")
    else:
        print("No successful P2P samples; keep conservative defaults.")

    args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote JSON: {args.json_out}")
    print("=" * 56)
    print("Benchmark complete.")


if __name__ == "__main__":
    main()
