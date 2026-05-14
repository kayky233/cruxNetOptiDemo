# SimGrid Trace-Driven Collective 模拟报告

- 输入结果：`crux_repro/results/simgrid_real_trace_results.csv`
- workload：`trace`
- baseline：`random_same`

| scheduler | makespan(s) | makespan gain | avg JCT(s) | JCT gain | avg comm(s) | comm gain | useful GPU fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| `random_same` | 225.703 | 0.00% | 96.898 | 0.00% | 67.945 | 0.00% | 0.1980 |
| `random_intensity` | 225.733 | -0.01% | 96.956 | -0.06% | 68.010 | -0.10% | 0.1980 |
| `crux_no_compress` | 225.703 | 0.00% | 96.898 | 0.00% | 67.945 | 0.00% | 0.1980 |
| `crux` | 225.657 | 0.02% | 97.152 | -0.26% | 68.183 | -0.35% | 0.1981 |

## 结论

- 当前结果里平均 JCT 最优的是 `random_same`，相对 baseline JCT 改善 0.00%。
- 这份报告用于快速比较策略，后续可以继续扩展 job-level timeline、link heatmap 和 CDF 图。
