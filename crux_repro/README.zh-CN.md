# Crux / SimGrid 多机多卡通信调度模拟

这是本项目的总入口。当前目录围绕 Crux 论文思想做了两层模拟：

1. 轻量离散事件模拟：快速复现 Crux 的 intensity-aware path selection、priority assignment、priority compression。
2. 真实 SimGrid S4U/C++ 模拟：在多机多卡、collective 通信竞争、trace-driven workload 下验证调度策略效果。

当前重点已经转向第二层：使用 SimGrid 模拟多机多卡训练集群中的 Ring AllReduce 竞争，并接入 Lingjun 开源生产 trace 做 workload replay/重排评估。

## 目录结构

```text
crux_repro/
  README.zh-CN.md                         # 总入口
  crux_sim.py                             # Crux 轻量离散事件模拟器
  simgrid_collective_sim.py               # SimGrid-style Python collective 模拟器
  run_verify.sh                           # 轻量模拟器验证脚本
  docs/                                   # 设计、建模、方案文档
  simgrid_real/                           # 真实 SimGrid S4U/C++ 模拟工程
  results/                                # 当前实验结果、报告、图表
    job_analysis/                         # job-level 图表和 delta 表
    verification/                         # 参数扫描验证结果
    archive/                              # 早期中间结果归档
```

关键子目录：

```text
simgrid_real/
  collective_sim.cpp       # S4U/C++ 主模拟器 (含 6-scheduler ablation)
  topology.h               # 拓扑定义 (star/fat_tree/clos/dragonfly/ascend)
  comm_plan.h              # 通信计划 (ring/tree/hierarchical/pipeline)
  build.sh                 # 构建 C++ 模拟器
  run_all.sh               # synthetic workload 批量运行
  make_trace_workload.py   # Lingjun trace -> SimGrid workload CSV
  run_trace.sh             # trace-driven 批量运行 (6 scheduler ablation)
  run_scan.py              # 自动化参数扫描脚本
  report_results.py        # scheduler 汇总报告 (含 ablation 分解)
  analyze_job_timeline.py  # job-level 分析和 SVG 图
```

## 实现目标

本项目不直接复现论文中的真实 96-GPU 测试床，也不模拟 HCCL/NCCL/RoCE 的协议细节。当前目标是做机制验证：

- 多个训练 job 并发运行；
- 每个 job 包含 compute 和 collective communication；
- collective 先实现 Ring AllReduce；
- 多个 rank-to-rank flow 在共享链路上竞争；
- 对比 random、priority-only、Crux-style placement/path/priority 策略；
- 用 trace-driven workload 评估 Crux 重排收益；
- 输出 scheduler 级和 job 级结果，方便和同事讨论。

## 模拟方式

### 1. 轻量 Crux 模拟器

入口：

```text
crux_repro/crux_sim.py
```

用途：

- 快速验证 Crux 抽象算法；
- 支持 synthetic workload；
- 支持 Lingjun trace 的 job/worker/topology 读取；
- 结果写入 `crux_repro/results/crux_sim_results.csv` 或 `crux_lingjun_results.csv`。

运行：

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/crux_sim.py \
  --seed 7 \
  --jobs 36 \
  --rounds 30
```

### 2. 真实 SimGrid S4U/C++ 模拟器

入口：

```text
crux_repro/simgrid_real/collective_sim.cpp
```

建模方式：

- 每张 GPU/NPU 卡建模为一个 SimGrid host；
- 每个 rank 是一个 SimGrid actor；
- compute 用 `this_actor::execute()` 表示；
- Ring AllReduce 用 mailbox communication 表示；
- 同机通信共享 local link；
- 跨机通信经过源 NIC、core、目的 NIC；
- trace-driven 模式下，rank actor 按 trace `start_s` 动态启动。

构建：

```bash
cd /Users/dkwyl/Documents/tmbProject/net
MAMBA_ROOT_PREFIX=/Users/dkwyl/Documents/tmbProject/net/.mamba \
  /Users/dkwyl/Documents/tmbProject/net/.tools/micromamba/bin/micromamba run \
  -p /Users/dkwyl/Documents/tmbProject/net/.simgrid_env \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/build.sh
```

## Trace-Driven 实验流程

### 1. 生成 workload

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/simgrid_real/make_trace_workload.py \
  --trace-data-dir data/lingjun \
  --out crux_repro/results/simgrid_trace_workload.csv \
  --jobs 12 \
  --hosts 8 \
  --max-ranks 8 \
  --seed 7
```

生成文件：

```text
crux_repro/results/simgrid_trace_workload.csv
```

### 2. 运行 replay 模式

replay 模式保留生产 trace 原始 host placement，用来观察真实放置下的通信竞争。

```bash
cd /Users/dkwyl/Documents/tmbProject/net
DYLD_LIBRARY_PATH=/Users/dkwyl/Documents/tmbProject/net/.simgrid_install/lib:/Users/dkwyl/Documents/tmbProject/net/.simgrid_env/lib \
  crux_repro/simgrid_real/run_trace.sh \
  crux_repro/results/simgrid_trace_workload.csv \
  crux_repro/results/simgrid_real_trace_replay_results.csv \
  replay
```

### 3. 运行 optimize + balanced 模式

optimize 模式保留 trace 的到达时间、模型参数和 GPU/rank 数，但允许 scheduler 重新选择 rank placement，用来观察 Crux 重排收益。

```bash
cd /Users/dkwyl/Documents/tmbProject/net
DYLD_LIBRARY_PATH=/Users/dkwyl/Documents/tmbProject/net/.simgrid_install/lib:/Users/dkwyl/Documents/tmbProject/net/.simgrid_env/lib \
  crux_repro/simgrid_real/run_trace.sh \
  crux_repro/results/simgrid_trace_workload.csv \
  crux_repro/results/simgrid_real_trace_optimize_balanced_results.csv \
  optimize \
  balanced \
  crux_repro/results/simgrid_real_trace_optimize_balanced_jobs.csv
```

### 4. 生成汇总报告

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/simgrid_real/report_results.py \
  --results crux_repro/results/simgrid_real_trace_optimize_balanced_results.csv \
  --out crux_repro/results/simgrid_real_trace_optimize_balanced_report.md
```

### 5. 生成 Ablation 分解报告（新）

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/simgrid_real/report_results.py \
  --results crux_repro/results/ablation/ablation_results.csv \
  --out crux_repro/results/ablation/ablation_report.md
```

报告自动输出 scheduler 对比表、ablation 分解、收益来源分析。

### 6. 运行自动化参数扫描（新）

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/simgrid_real/run_scan.py \
  --scan-topology --scan-scale \
  --workload-csv crux_repro/results/simgrid_trace_workload.csv \
  --out-dir crux_repro/results/scan
```

支持 `--scan-topology`、`--scan-scale`、`--scan-bg`、`--scan-overlap`、`--scan-comm-plan` 或 `--all` 全量扫描。

### 7. 生成增强可视化（新）

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/vis/vis_enhanced.py \
  --results crux_repro/results/ablation/ablation_results.csv \
  --jobs crux_repro/results/ablation/ablation_jobs.csv \
  --out-dir crux_repro/results/ablation/vis
```

产出：ablation 收益分解柱状图、JCT compute/comm/wait 瀑布分解图、链路利用率热力图（需 `--link-timeline-dir`）。

### 8. 生成网络拓扑可视化（新）

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/vis/vis_network.py \
  --jobs crux_repro/results/ablation/ablation_jobs.csv \
  --links /tmp/netvis_links.csv \
  --topology three_tier_clos \
  --hosts 8 --gpus-per-host 8 \
  --baseline random_same --target crux_no_compress \
  --out-dir crux_repro/results/vis_network
```

产出 7 张 SVG：

| 文件 | 内容 |
|---|---|
| `topology_map_{scheduler}.svg` | 完整网络拓扑（Switch/NIC/GPU 层级），GPU 按 job 着色，链路按利用率着色/加粗 |
| `link_congestion.svg` | 链路拥塞排序柱状图（local/NIC/switch 分组） |
| `job_ring_paths.svg` | Top-4 高通信强度 job 的 Ring AllReduce 环形路径，跨机红色/同机绿色 |
| `gpu_gantt_{scheduler}.svg` | GPU 占用时间线甘特图，每行一个 GPU，颜色=job |
| `placement_compare.svg` | baseline vs target 并排 GPU 放置热力图 |

### 9. 生成交互式 Web 动态回放（新）

```bash
# 一键生成自包含 HTML（数据直接嵌入，无需 data.json）
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/tools/export_web_data.py \
  --jobs crux_repro/results/ablation/ablation_jobs.csv \
  --results crux_repro/results/ablation/ablation_results.csv \
  --topology three_tier_clos --hosts 8 --gpus-per-host 8 \
  --scheduler crux_no_compress \
  --merge-html crux_repro/vis/dashboard.html \
  --out crux_repro/results/web_dashboard/data.json

# 浏览器打开
open crux_repro/results/web_dashboard/dashboard.html
```

页面功能：▶ 播放/暂停 | 拖拽进度条 | 0.5×~30× 变速 | GPU 甘特图(滚轮缩放) | 拓扑快照(GPU 按 job 着色) | 链路利用率柱状图 | Job 排队/运行/完成状态。

产物：`results/web_dashboard/dashboard.html` + `data.json`，以及 `web_dashboard_random/` 基线版本。

### 10. 生成 job-level 分析

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  crux_repro/simgrid_real/analyze_job_timeline.py \
  --jobs crux_repro/results/simgrid_real_trace_optimize_balanced_jobs.csv \
  --target crux_no_compress \
  --baseline random_same \
  --out-dir crux_repro/results/job_analysis
```

## 当前主要结果

### Trace Replay

replay 模式保留生产 trace 原始 placement。结果接近 baseline，说明当前收益主要不是来自 priority/rate，而是需要调度器参与重排。

| scheduler | makespan(s) | avg JCT(s) | avg comm(s) | useful GPU fraction |
|---|---:|---:|---:|---:|
| `random_same` | 225.703 | 96.898 | 67.945 | 0.1980 |
| `random_intensity` | 225.733 | 96.956 | 68.010 | 0.1980 |
| `crux_no_compress` | 225.703 | 96.898 | 67.945 | 0.1980 |
| `crux` | 225.657 | 97.152 | 68.183 | 0.1981 |

### Trace Optimize Balanced

balanced 重排同时考虑 host 负载和 GPU slot 负载，并用当前 workload 的 intensity 中位数动态划分高/低通信任务。

| scheduler | makespan(s) | avg JCT(s) | avg comm(s) | useful GPU fraction |
|---|---:|---:|---:|---:|
| `random_same` | 95.305 | 52.952 | 31.637 | 0.4689 |
| `random_intensity` | 94.997 | 52.844 | 31.538 | 0.4705 |
| `crux_no_compress` | 83.171 | 44.970 | 22.124 | 0.5374 |
| `crux` | 83.985 | 45.074 | 22.291 | 0.5322 |

相对 `random_same`：

- `crux_no_compress` makespan 改善约 12.73%；
- 平均 JCT 改善约 15.07%；
- 平均通信时间改善约 30.07%；
- useful GPU fraction 从 0.4689 提升到 0.5374。

### Ablation 收益分解（新）

2026-05-15 新增 6-scheduler ablation，用于分离 placement / priority / compression 的独立贡献：

| scheduler | makespan(s) | avg JCT(s) | avg comm(s) | ugf | 说明 |
|---|---:|---:|---:|---:|---|
| `random_same` | 95.305 | 52.952 | 31.637 | 0.4689 | baseline：随机放置 + 同优先级 |
| `random_intensity` | 94.997 | 52.844 | 31.538 | 0.4705 | 仅 intensity 分桶限速 |
| `priority_only` | 95.031 | 52.850 | 31.561 | 0.4703 | **仅优先级，不改 placement** |
| `place_only` | **83.171** | **44.970** | **22.124** | **0.5374** | **仅 placement，不加优先级** |
| `crux_no_compress` | 83.171 | 44.970 | 22.124 | 0.5374 | placement + logical priority |
| `crux` | 83.985 | 45.074 | 22.291 | 0.5322 | placement + priority + DAG 压缩 |

**核心发现**：

- `place_only`（仅强度感知 placement）达到了与 `crux_no_compress` **完全相同的效果** — makespan 改善 12.73%，JCT 改善 15.07%
- `priority_only`（仅优先级 + 随机 placement）**几乎无收益**（JCT 改善 < 0.2%）
- `random_intensity`（简单 intensity 分桶）也几乎无收益
- **结论：当前模型下，Crux 的收益 ≈ 通信感知的 bin-packing placement。优先级/限速的边际贡献接近于零。**

这个发现在 replay 模式中已有预示（replay 无重排时收益为零），但 ablation 矩阵首次量化了各组件的独立贡献。

### Job-Level 结果

基于 `simgrid_real_trace_optimize_balanced_jobs.csv`：

- 10 / 12 个 job 的 JCT 改善；
- 2 / 12 个 job 的 JCT 退化；
- Top gain 是 `GPT-large` job 4，JCT 降低 23.404s，通信时间降低 29.138s；
- 两个退化 job 的通信时间也下降，但 JCT 变差，说明后续 objective 还需要加入更明确的 job fairness 或 rank 启动/算力拥塞约束。

### DeepSeek 补充验证

`crux_repro/results/verification/` 中保存了一组 DeepSeek 生成的轻量 Python 模拟参数扫描，用于验证 Crux 机制趋势和参数敏感性。它不替代真实 SimGrid trace-driven 结果，但可以作为补充证据：

- 常规负载下，`crux` 相对 `random_same` 的 GPU util 提升约 10-16%；
- 极端拥塞下，提升约 22-32%；
- K=4 在当前规模下基本达到饱和；
- K=1 时 Crux 退化明显，说明路径选择和优先级分配需要配合；
- 多 seed 下增益稳定，约 9.76%-12.47%；
- high-intensity job JCT 降幅约 15-28%。

入口文档：

```text
crux_repro/results/verification/VERIFICATION_REPORT.md
crux_repro/results/verification/figures/README.zh-CN.md
```

图表版文档已经直接嵌入 SVG，打开即可看到 K 敏感性、规模压力、路径数、多 seed、极端拥塞等图。

## 文档导航

```
📂 docs/
├── 📄 README.zh-CN.md                    ← 文档索引（本页入口）
│
├── 📂 reports/                           ← 评审报告（给上级和同事）
│   ├── CRUX_REPRODUCTION_REPORT.zh-CN.md   Crux 方法复现与模拟验证
│   └── TOPOLOGY_COMPARISON_REPORT.zh-CN.md 拓扑对比 (star vs clos vs ascend)
│
├── 📂 design/                            ← 方案设计文档
│   ├── SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md  总模拟方案 ⭐
│   ├── REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md       实机环境接入
│   ├── VISUALIZATION_DESIGN.zh-CN.md                可视化方案
│   ├── IMASTER_API_REQUIREMENTS.zh-CN.md            华为接口需求清单
│   ├── DEVELOPMENT_DESIGN.zh-CN.md                  开发设计
│   ├── IMPLEMENTATION_MAP.zh-CN.md                  实现映射
│   └── TRAINING_INFERENCE_OPTIMIZATION_MODEL.zh-CN.md 训练推理建模
│
├── 📂 simgrid-guide/                     ← SimGrid 学习参考
│   ├── SIMGRID_INDEX.zh-CN.md             索引
│   ├── SIMGRID_INTRODUCTION.zh-CN.md      简介
│   ├── SIMGRID_INSTALL.zh-CN.md           安装
│   └── SIMGRID_{S4U,PLATFORM,MODELS,...}.zh-CN.md
│
└── 📂 assets/                            ← SVG 图表
    ├── gantt_comparison.svg
    ├── placement_heatmap.svg
    └── ascend_*.svg
```

> 完整索引见 [docs/README.zh-CN.md](docs/README.zh-CN.md)

### 快速入口

| 看什么 | 文件 |
|---|---|
| **给上级汇报** | [`docs/reports/CRUX_REPRODUCTION_REPORT.zh-CN.md`](docs/reports/CRUX_REPRODUCTION_REPORT.zh-CN.md) |
| **拓扑对比结果** | [`docs/reports/TOPOLOGY_COMPARISON_REPORT.zh-CN.md`](docs/reports/TOPOLOGY_COMPARISON_REPORT.zh-CN.md) |
| **总模拟方案** | [`docs/design/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md`](docs/design/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md) |
| **实机接入方案** | [`docs/design/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md`](docs/design/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md) |
| **华为接口清单** | [`docs/design/IMASTER_API_REQUIREMENTS.zh-CN.md`](docs/design/IMASTER_API_REQUIREMENTS.zh-CN.md) |
| **网络拓扑可视化** | [`vis/vis_network.py`](vis/vis_network.py) 生成 GPU/交换机/链路拓扑图 + job 分布 + 拥塞热力图 |
| **可视化方案** | [`docs/design/VISUALIZATION_DESIGN.zh-CN.md`](docs/design/VISUALIZATION_DESIGN.zh-CN.md) |
| **SimGrid 学习** | [`docs/simgrid-guide/SIMGRID_INDEX.zh-CN.md`](docs/simgrid-guide/SIMGRID_INDEX.zh-CN.md) |
| **结果数据** | [`results/README.zh-CN.md`](results/README.zh-CN.md) |

## 当前边界

- 尚未模拟 HCCL/NCCL/RoCE 协议细节；
- collective 目前以 Ring AllReduce 为主（已实现 tree/hierarchical/pipeline plan）；
- 昇腾 920 + 910B 的真实拓扑、HCCS/PCIe/NIC 参数还未校准；
- compute time、tensor size 仍由模型模板补齐；
- 优先级实现为速率限制（`set_rate()`），非真实 hardware traffic class 队列模型。

## 新增功能（2026-05-15）

| 功能 | 文件 | 说明 |
|---|---|---|
| 6-scheduler ablation | `collective_sim.cpp` | `random_same` / `random_intensity` / `place_only` / `priority_only` / `crux_no_compress` / `crux` |
| Compute-comm overlap | `collective_sim.cpp` `--overlap-ratio` | 异步 backward compute 与 collective 通信重叠 |
| Compute wait 追踪 | `collective_sim.cpp` | `avg_compute_wait_s` 指标，量化 GPU 算力拥塞 |
| Link timeline 采样 | `collective_sim.cpp` `--link-timeline-out` | 每秒采样每条链路的 cumulative bytes |
| 自动化参数扫描 | `run_scan.py` | 遍历 topology × scheduler × workload × bg × overlap |
| Ablation 报告 | `report_results.py` | 自动输出 ablation 收益分解表 |
| 增强可视化 | `vis/vis_enhanced.py` | ablation 柱状图、JCT 瀑布分解图、link heatmap |
| 网络拓扑可视化 | `vis/vis_network.py` | GPU/交换机/NIC 拓扑图 + job 分布色块 + 链路拥塞 + Ring 路径 + Gantt |
| **交互式 Web 回放** | `vis/dashboard.html` | 动态 job 到达/释放、Gantt 时间线、拓扑快照、链路热力、播放/暂停/拖拽 |

## 下一步

详见 [总模拟方案 §11 后续改进路线](docs/design/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md#11-后续改进路线)

当前最高优先级的模拟层优化已完成（策略 ablation、参数扫描框架、增强可视化）。后续等待实机数据接入后，进行拓扑参数校准和 HCCL benchmark 拟合。
