# Crux / SimGrid Multi-GPU Communication Scheduling Simulation

This directory now focuses on a SimGrid-based reproduction and exploration of the Crux paper idea: communication-intensity-aware placement/path/priority decisions for multi-job collective communication contention.

The main entry is the Chinese project guide:

- [README.zh-CN.md](README.zh-CN.md)

Key locations:

- `simgrid_real/`: real SimGrid S4U/C++ simulator and scripts.
- `docs/`: design notes, modeling plan, and optimization roadmap.
- `results/`: CSV results, Markdown reports, and SVG analysis charts.

Latest trace-driven optimize/balanced result:

- `crux_no_compress` improves makespan by about 12.73%, average JCT by about 15.07%, and average communication time by about 30.07% versus `random_same` on the current 12-job Lingjun trace window.
