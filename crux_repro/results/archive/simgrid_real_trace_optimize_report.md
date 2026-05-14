# SimGrid Trace-Driven Collective 模拟报告

- 输入结果：`crux_repro/results/simgrid_real_trace_optimize_results.csv`
- workload：`trace`
- placement mode：`optimize`
- baseline：`random_same`

| scheduler | makespan(s) | makespan gain | avg JCT(s) | JCT gain | avg comm(s) | comm gain | useful GPU fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| `random_same` | 95.305 | 0.00% | 52.952 | 0.00% | 31.637 | 0.00% | 0.4689 |
| `random_intensity` | 94.997 | 0.32% | 52.844 | 0.20% | 31.538 | 0.31% | 0.4705 |
| `crux_no_compress` | 92.173 | 3.29% | 53.008 | -0.11% | 26.469 | 16.34% | 0.4849 |
| `crux` | 92.169 | 3.29% | 53.009 | -0.11% | 26.470 | 16.33% | 0.4849 |

## 结论

- 平均 JCT 最优的是 `random_intensity`，相对 baseline JCT 改善 0.20%。
- makespan 最优的是 `crux`，相对 baseline makespan 改善 3.29%。
- 平均通信时间最优的是 `crux_no_compress`，相对 baseline comm 改善 16.34%。
- 这份报告用于快速比较策略，后续可以继续扩展 job-level timeline、link heatmap 和 CDF 图。
