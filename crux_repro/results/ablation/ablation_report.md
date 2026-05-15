# SimGrid Collective 竞争模拟报告

- 输入结果：`crux_repro/results/ablation/ablation_results.csv`
- topology：`star`  |  comm plan：`ring`  |  overlap：`0.000000`
- workload：`trace`  |  placement：`optimize` / `balanced`
- baseline：`random_same`

## Scheduler 对比

| scheduler | makespan(s) | gain | avg JCT(s) | gain | avg comm(s) | gain | wait(s) | GPU fraction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `random_same` | 95.305 | +0.00% | 52.952 | +0.00% | 31.637 | +0.00% | 0.000 | 0.4689 |
| `random_intensity` | 94.997 | +0.32% | 52.844 | +0.20% | 31.538 | +0.31% | 0.000 | 0.4705 |
| `place_only` | 83.171 | +12.73% | 44.970 | +15.07% | 22.124 | +30.07% | 0.000 | 0.5374 |
| `priority_only` | 95.031 | +0.29% | 52.850 | +0.19% | 31.561 | +0.24% | 0.000 | 0.4703 |
| `crux_no_compress` | 83.171 | +12.73% | 44.970 | +15.07% | 22.124 | +30.07% | 0.000 | 0.5374 |
| `crux` | 83.985 | +11.88% | 45.074 | +14.88% | 22.291 | +29.54% | 0.000 | 0.5322 |

## Ablation 收益分解

| 组件 | 对比 | makespan gain | JCT gain | comm gain |
|---|---:|---:|---:|
| **placement only** | `place_only` vs `random_same` | +12.73% | +15.07% | +30.07% |
| **priority only** | `priority_only` vs `random_same` | +0.29% | +0.19% | +0.24% |
| **intensity buckets** | `random_intensity` vs `random_same` | +0.32% | +0.20% | +0.31% |
| **full crux (no compress)** | `crux_no_compress` vs `random_same` | +12.73% | +15.07% | +30.07% |
| **full crux (K=4)** | `crux` vs `random_same` | +11.88% | +14.88% | +29.54% |
| **compression gap** | `crux` vs `crux_no_compress` | -0.98% | -0.23% | -0.76% |

## 结论

- 平均 JCT 最优：`place_only` (44.970s, +15.07%)
- makespan 最优：`place_only` (83.171s, +12.73%)
- 通信时间最优：`place_only` (22.124s, +30.07%)
- GPU 利用率最优：`place_only` (0.5374)

### 收益来源分解
- placement 贡献约占 JCT 改善的 100% 
- 剩余来自 priority + path selection 的协同效应
- priority-only 独立贡献 JCT 改善 0.19%，说明仅靠优先级（不改 placement）收益有限

*此报告用于快速比较策略，完整分析见 job-level timeline、link heatmap 和 CDF 图。*
