# SimGrid 多机多卡 Collective 竞争模拟

这个目录是一个真实链接 SimGrid S4U/C++ runtime 的最小实验，用来模拟“多机多卡训练任务同时执行 Ring AllReduce 时的网络竞争”。

## 环境

- SimGrid 安装目录：`../../.simgrid_install`
- 依赖环境：`../../.simgrid_env`
- 入口程序：`collective_sim.cpp`

Python binding 在当前 macOS arm64 环境里会卡在 pybind11 的 property/call_guard 编译兼容问题，因此这里采用 SimGrid 官方 S4U/C++ API。这个路径更适合后续做可控网络拓扑、链路共享和 actor 级训练过程建模。

## 构建

```bash
cd /Users/dkwyl/Documents/tmbProject/net
MAMBA_ROOT_PREFIX=/Users/dkwyl/Documents/tmbProject/net/.mamba \
  /Users/dkwyl/Documents/tmbProject/net/.tools/micromamba/bin/micromamba run \
  -p /Users/dkwyl/Documents/tmbProject/net/.simgrid_env \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/build.sh
```

## 运行

```bash
cd /Users/dkwyl/Documents/tmbProject/net
DYLD_LIBRARY_PATH=/Users/dkwyl/Documents/tmbProject/net/.simgrid_install/lib \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/run_all.sh
```

结果输出到：

```text
/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_collective_results.csv
```

## Trace-driven 运行

先把 Lingjun trace 转成真实 SimGrid 程序可读的 workload CSV：

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/make_trace_workload.py \
  --trace-data-dir /Users/dkwyl/Documents/tmbProject/net/data/lingjun \
  --out /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_trace_workload.csv \
  --jobs 12 \
  --hosts 8 \
  --max-ranks 8 \
  --seed 7
```

再运行 trace-driven SimGrid 实验。第三个参数是 placement mode：

- `replay`：保留 trace 原始 host placement；
- `optimize`：保留 trace 的到达时间、模型参数和 GPU/rank 数，但允许调度器重新选择 rank placement，用于观察 Crux 重排收益。

```bash
cd /Users/dkwyl/Documents/tmbProject/net
DYLD_LIBRARY_PATH=/Users/dkwyl/Documents/tmbProject/net/.simgrid_install/lib:/Users/dkwyl/Documents/tmbProject/net/.simgrid_env/lib \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/run_trace.sh \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_trace_workload.csv \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_results.csv \
  optimize \
  balanced \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_jobs.csv
```

生成报告：

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/report_results.py \
  --results /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_results.csv \
  --out /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_report.md
```

相关产物：

- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_trace_workload.csv`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_replay_results.csv`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_results.csv`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_jobs.csv`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_report.md`

需要注意：`optimize` 不是改变 trace 的作业到达时间和 GPU 规模，而是在同一个 trace workload 上重新选择 rank placement。它用于回答“如果调度器有机会重排资源，Crux-style placement 能带来多少收益”。

当前已验证的一组输出：

| scheduler | makespan(s) | avg JCT(s) | avg comm(s) | useful GPU fraction |
|---|---:|---:|---:|---:|
| `random_same` | 107.579 | 75.983 | 72.603 | 0.0768 |
| `random_intensity` | 107.579 | 75.983 | 72.605 | 0.0768 |
| `crux_no_compress` | 42.550 | 33.353 | 28.113 | 0.1942 |
| `crux` | 42.550 | 33.353 | 28.113 | 0.1942 |

在这组小规模实验里，主要收益来自高通信强度 job 的拓扑感知放置：把 rank 收敛到更少物理机，减少 Ring AllReduce 的跨机路径和共享 NIC/core 链路竞争。`crux` 与 `crux_no_compress` 一致，说明当前 workload 下优先级/限速不是新的瓶颈；要验证 priority compression，需要引入更明显的低优先级背景通信或更接近硬件 traffic class 的服务模型。

当前 trace-driven replay 输出：

| scheduler | makespan(s) | avg JCT(s) | avg comm(s) | useful GPU fraction |
|---|---:|---:|---:|---:|
| `random_same` | 225.703 | 96.898 | 67.945 | 0.1980 |
| `random_intensity` | 225.733 | 96.956 | 68.010 | 0.1980 |
| `crux_no_compress` | 225.703 | 96.898 | 67.945 | 0.1980 |
| `crux` | 225.657 | 97.152 | 68.183 | 0.1981 |

这组结果接近 baseline，原因是 trace-driven 模式保留生产轨迹中的 host placement，没有让 Crux 重新放置 job；当前只验证动态到达、真实 host 分布和 priority/rate 策略。

当前 trace-driven optimize 输出：

| scheduler | makespan(s) | avg JCT(s) | avg comm(s) | useful GPU fraction |
|---|---:|---:|---:|---:|
| `random_same` | 95.305 | 52.952 | 31.637 | 0.4689 |
| `random_intensity` | 94.997 | 52.844 | 31.538 | 0.4705 |
| `crux_no_compress` | 83.171 | 44.970 | 22.124 | 0.5374 |
| `crux` | 83.985 | 45.074 | 22.291 | 0.5322 |

这组结果说明：开启 balanced 重排后，Crux-style placement 在 makespan 上相对 `random_same` 改善约 12.73%，平均 JCT 改善约 15.07%，平均通信时间改善约 30.07%，useful GPU fraction 从 0.4689 提升到 0.5374。

## Job-Level 分析

基于 `--job-out` 输出可以继续生成 job 级报告和 SVG 图：

```bash
cd /Users/dkwyl/Documents/tmbProject/net
/Users/dkwyl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/analyze_job_timeline.py \
  --jobs /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/simgrid_real_trace_optimize_balanced_jobs.csv \
  --target crux_no_compress \
  --baseline random_same \
  --out-dir /Users/dkwyl/Documents/tmbProject/net/crux_repro/results/job_analysis
```

已生成：

- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/job_analysis/crux_no_compress_vs_random_same_job_analysis.md`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/job_analysis/crux_no_compress_vs_random_same_job_deltas.csv`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/job_analysis/jct_cdf.svg`
- `/Users/dkwyl/Documents/tmbProject/net/crux_repro/results/job_analysis/crux_no_compress_jct_delta.svg`

当前 job-level 结论：

- 10 / 12 个 job 的 JCT 改善；
- 2 / 12 个 job 的 JCT 退化；
- Top gain 是 `GPT-large` job 4，JCT 降低 23.404s，通信时间降低 29.138s；
- 两个退化 job 的通信时间其实也下降了，但 JCT 变差，说明后续 objective 还需要继续加入 job fairness 或 rank 启动/算力拥塞的约束。

## 模型说明

- 每张 GPU/NPU 卡建模为一个 SimGrid host。
- 同一物理机内的卡通信共享 `localX` 链路。
- 跨机器通信经过源机器 `nicX`、共享 `core`、目的机器 `nicY`。
- 每个训练 job 有多个 rank，每个 rank 是一个 SimGrid actor。
- 每轮迭代包含 compute 和 Ring AllReduce。
- Ring AllReduce 建模为 `2 * (rank_count - 1)` 个 step，每个 step 向下一个 rank 发送 `tensor_bytes / rank_count`。

## 调度策略

- `random_same`：基线，固定放置，不做通信区分。
- `random_intensity`：按通信强度给低强度任务限速，模拟简单优先级。
- `crux_no_compress`：按通信强度做拓扑感知放置，但不做链路优先级。
- `crux`：拓扑感知放置 + 对低通信强度流量限速，让高通信强度任务更早释放关键链路。

当前模型还不是昇腾 HCCL/RoCE 细节模拟；它先验证 Crux 的核心抽象：通信强度、放置、共享链路竞争、优先级/限速对训练迭代时间的影响。
