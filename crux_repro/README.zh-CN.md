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
  collective_sim.cpp       # S4U/C++ 主模拟器
  build.sh                 # 构建 C++ 模拟器
  run_all.sh               # synthetic workload 批量运行
  make_trace_workload.py   # Lingjun trace -> SimGrid workload CSV
  run_trace.sh             # trace-driven 批量运行
  report_results.py        # scheduler 汇总报告
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

### 5. 生成 job-level 分析

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

## 关键产物

| 类型 | 文件 |
|---|---|
| 总方案 | `crux_repro/docs/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md` |
| 实机拓扑/时延接入方案 | `crux_repro/docs/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md` |
| SimGrid 工程说明 | `crux_repro/simgrid_real/README.zh-CN.md` |
| trace workload | `crux_repro/results/simgrid_trace_workload.csv` |
| optimize balanced 汇总 | `crux_repro/results/simgrid_real_trace_optimize_balanced_results.csv` |
| optimize balanced job 明细 | `crux_repro/results/simgrid_real_trace_optimize_balanced_jobs.csv` |
| scheduler 报告 | `crux_repro/results/simgrid_real_trace_optimize_balanced_report.md` |
| job-level 报告 | `crux_repro/results/job_analysis/crux_no_compress_vs_random_same_job_analysis.md` |
| DeepSeek 补充验证 | `crux_repro/results/verification/VERIFICATION_REPORT.md` |
| DeepSeek 验证图表 | `crux_repro/results/verification/figures/README.zh-CN.md` |
| JCT CDF | `crux_repro/results/job_analysis/jct_cdf.svg` |
| per-job delta 图 | `crux_repro/results/job_analysis/crux_no_compress_jct_delta.svg` |

## 文档入口

- **评审报告**: [Crux 方法复现与模拟验证报告](docs/CRUX_REPRODUCTION_REPORT.zh-CN.md) ← 给上级和同事审阅
- [文档索引](docs/README.zh-CN.md)
- [真实 SimGrid 工程说明](simgrid_real/README.zh-CN.md)
- [结果索引](results/README.zh-CN.md)

## 当前边界

- 尚未模拟 HCCL/NCCL/RoCE 协议细节；
- collective 目前以 Ring AllReduce 为主；
- 昇腾 920 + 910B 的真实拓扑、HCCS/PCIe/NIC 参数还未校准；
- compute time、tensor size 仍由模型模板补齐；
- priority compression 目前是近似逻辑，还未映射真实硬件 traffic class。

## 下一步

详细计划在：

[SimGrid Collective 模拟方案：第 11 节 后续改进路线](docs/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md#11-后续改进路线)

摘要：

1. 实机环境接入：通过华为接口采集拓扑/链路/时延，落 TDSQL/Redis，本地优化器读取环境快照；
2. 拓扑配置化：把当前 C++ 内置拓扑抽成配置文件，并支持从实机快照生成 SimGrid platform；
3. HCCL benchmark 校准：先让单 job collective 时间可信；
4. 增加 collective plan：Ring、Tree、Hierarchical、ReduceScatter、AllGather；
5. 策略消融：区分 placement/path/priority/compression 的独立贡献；
6. 加背景流和扰动：验证鲁棒性；
7. 做可视化报告：把结果变成可以评审的材料。

实机接入的独立方案见：

[实机环境拓扑与网络时延接入方案](docs/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md)
