# SimGrid 参数扫描汇总报告

扫描时间：自动生成
场景数：1

## 各场景最优策略

| 场景 | best makespan | best JCT | best comm | best GPU frac |
|---|---:|---:|---:|---:|
| default | `place_only` (170.0s) | `place_only` (11.5s) | `place_only` (9.3s) | `place_only` (0.075) |

## default

| scheduler | makespan | vs base | JCT | vs base | comm | vs base | ugf |
|---|---:|---:|---:|---:|---:|---:|---:|
| `random_same` | 289.53 | +0.0% | 17.60 | +0.0% | 15.46 | +0.0% | 0.044 |
| `random_intensity` | 406.93 | -40.5% | 15.88 | +9.7% | 13.75 | +11.1% | 0.032 |
| `place_only` | 170.02 | +41.3% | 11.46 | +34.9% | 9.32 | +39.7% | 0.075 |
| `priority_only` | 406.93 | -40.5% | 15.88 | +9.7% | 13.75 | +11.1% | 0.032 |
| `crux_no_compress` | 170.02 | +41.3% | 11.46 | +34.9% | 9.32 | +39.7% | 0.075 |
| `crux` | 170.24 | +41.2% | 11.51 | +34.6% | 9.37 | +39.4% | 0.075 |
