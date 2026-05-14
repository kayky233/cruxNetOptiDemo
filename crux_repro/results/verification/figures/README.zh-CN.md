# DeepSeek 补充验证图表

这些图来自 `crux_repro/results/verification/verify_*.csv`，用于展示轻量 `crux_sim.py` 参数扫描结果。

## 结论速读

- K=4 后收益基本饱和；
- 规模越大、拥塞越强，Crux 收益越明显；
- 多 seed 下 Crux 收益稳定；
- 极端拥塞下 Crux/Crux no compress 的优势最直观。

## 优先级级别敏感性

K 从 1 到 4 时 Crux 收益快速上升，K=4 后基本饱和。

![优先级级别敏感性](priority_levels_gain.svg)

## 规模压力

规模越大，随机调度越容易产生链路碰撞，Crux 的相对收益更明显。

![规模压力](scale_pressure_gain.svg)

## 聚合路径数

可选路径越少，路径选择越重要；路径增加后 baseline 也会改善，因此相对收益下降。

![聚合路径数](aggregation_paths_gain.svg)

## 多种子稳定性

不同随机种子下 Crux 都保持稳定收益，说明不是偶然 workload。

![多种子稳定性](seed_stability_gain.svg)

## 极端拥塞

高 job/host 比例下，Crux 和 Crux no compress 的收益最直观，说明该机制主要价值在高竞争场景。

![极端拥塞](extreme_congestion_gain.svg)
