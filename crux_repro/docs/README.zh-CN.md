# 文档索引

这里收纳项目设计、建模、方案和历史分析文档。推荐阅读顺序如下。

## 推荐阅读顺序

1. [项目总入口](../README.zh-CN.md)
   - 项目目标、目录、运行方式、当前结果。

2. [SimGrid Collective 模拟方案](SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md)
   - 多机多卡建模方式；
   - SimGrid runtime 状态；
   - trace-driven workflow；
   - 当前实验结果；
   - 后续优化路线。

3. [开发设计文档](DEVELOPMENT_DESIGN.zh-CN.md)
   - 轻量 Crux 模拟器的数据结构、流程、策略实现。

4. [实现映射说明](IMPLEMENTATION_MAP.zh-CN.md)
   - 代码与 Crux 论文概念的对应关系。

5. [训练/推理优化建模](TRAINING_INFERENCE_OPTIMIZATION_MODEL.zh-CN.md)
   - 训练和推理场景下的统一问题建模与优化方向。

## 文档说明

| 文档 | 作用 |
|---|---|
| `SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md` | 当前最重要的方案文档，覆盖真实 SimGrid 模拟和实验结果 |
| `DEVELOPMENT_DESIGN.zh-CN.md` | 轻量模拟器的详细开发设计 |
| `IMPLEMENTATION_MAP.zh-CN.md` | 中文实现映射 |
| `IMPLEMENTATION_MAP.md` | 英文实现映射 |
| `TRAINING_INFERENCE_OPTIMIZATION_MODEL.zh-CN.md` | 扩展到训练/推理调度的建模文档 |

## 结果入口

实验结果和图表见：

- [results/README.zh-CN.md](../results/README.zh-CN.md)
