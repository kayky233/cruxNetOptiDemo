# 文档索引

> 从顶层 README 跳转：每个子目录有独立主题，按角色和场景导航。

---

## 目录一览

```
docs/
├── README.zh-CN.md                        ← 本文档（索引）
│
├── reports/                              评审 & 对比报告
│   ├── CRUX_REPRODUCTION_REPORT.zh-CN.md    给上级/同事的完整评审报告
│   └── TOPOLOGY_COMPARISON_REPORT.zh-CN.md  star vs clos vs ascend 拓扑对比
│
├── design/                               方案设计 & 规划
│   ├── SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md  ⭐ 总模拟方案（最重要）
│   ├── REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md       实机环境拓扑接入方案
│   ├── VISUALIZATION_DESIGN.zh-CN.md                可视化模块设计
│   ├── IMASTER_API_REQUIREMENTS.zh-CN.md            华为 iMaster NCE API 需求清单
│   ├── DEVELOPMENT_DESIGN.zh-CN.md                  早期开发设计（轻量模拟器）
│   ├── IMPLEMENTATION_MAP.zh-CN.md                  论文概念 → 代码映射
│   └── TRAINING_INFERENCE_OPTIMIZATION_MODEL.zh-CN.md 训练/推理统一优化模型
│
├── simgrid-guide/                        SimGrid 学习参考
│   ├── SIMGRID_INDEX.zh-CN.md             索引（含推荐阅读顺序）
│   └── SIMGRID_{INTRODUCTION,INSTALL,S4U,...}.zh-CN.md
│
└── assets/                               SVG 图表
    ├── gantt_comparison.svg               trace-driven 的 job Gantt
    ├── placement_heatmap.svg              trace-driven 的 GPU 放置
    ├── topology_diagram.svg               three_tier_clos 拓扑
    ├── ascend_gantt_comparison.svg        ascend 拓扑的 job Gantt
    ├── ascend_placement_heatmap.svg       ascend 拓扑的 GPU 放置
    ├── ascend_topology_diagram.svg        ascend Leaf-Spine 拓扑
    └── ascend_*.svg                       其余 ascend 对比图表
```

---

## 按角色导航

### 给上级 / 评审

| 文档 | 位置 |
|---|---|
| Crux 方法复现与模拟验证报告 | [`reports/CRUX_REPRODUCTION_REPORT.zh-CN.md`](reports/CRUX_REPRODUCTION_REPORT.zh-CN.md) |
| 拓扑模型对比报告 | [`reports/TOPOLOGY_COMPARISON_REPORT.zh-CN.md`](reports/TOPOLOGY_COMPARISON_REPORT.zh-CN.md) |
| 华为接口需求清单 | [`design/IMASTER_API_REQUIREMENTS.zh-CN.md`](design/IMASTER_API_REQUIREMENTS.zh-CN.md) |

### 给开发 / 接手

| 文档 | 位置 |
|---|---|
| 总模拟方案（入口） | [`design/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md`](design/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md) |
| 实机环境接入 | [`design/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md`](design/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md) |
| 可视化模块设计 | [`design/VISUALIZATION_DESIGN.zh-CN.md`](design/VISUALIZATION_DESIGN.zh-CN.md) |
| 实现映射 | [`design/IMPLEMENTATION_MAP.zh-CN.md`](design/IMPLEMENTATION_MAP.zh-CN.md) |
| 早期开发设计 | [`design/DEVELOPMENT_DESIGN.zh-CN.md`](design/DEVELOPMENT_DESIGN.zh-CN.md) |
| 训练推理建模 | [`design/TRAINING_INFERENCE_OPTIMIZATION_MODEL.zh-CN.md`](design/TRAINING_INFERENCE_OPTIMIZATION_MODEL.zh-CN.md) |

### 学习 SimGrid

| 文档 | 位置 |
|---|---|
| SimGrid 索引 | [`simgrid-guide/SIMGRID_INDEX.zh-CN.md`](simgrid-guide/SIMGRID_INDEX.zh-CN.md) |
| SimGrid 简介 | [`simgrid-guide/SIMGRID_INTRODUCTION.zh-CN.md`](simgrid-guide/SIMGRID_INTRODUCTION.zh-CN.md) |
| SimGrid 安装 | [`simgrid-guide/SIMGRID_INSTALL.zh-CN.md`](simgrid-guide/SIMGRID_INSTALL.zh-CN.md) |
| 中文手册 | [`simgrid-guide/simgrid-zh/index.html`](simgrid-guide/simgrid-zh/index.html) |

---

## 推荐阅读顺序

1. **[顶层 README](../README.zh-CN.md)** — 项目概览、当前结果
2. **[总模拟方案](design/SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md)** — 为什么用 SimGrid、怎么建模、结果、下一步
3. **[评审报告](reports/CRUX_REPRODUCTION_REPORT.zh-CN.md)** — 给同事/上级看的完整汇报
4. **[拓扑对比报告](reports/TOPOLOGY_COMPARISON_REPORT.zh-CN.md)** — ascend 拓扑下的 Crux 行为分析
5. **[实机接入方案](design/REAL_ENV_TOPOLOGY_INTEGRATION.zh-CN.md)** — 从模拟到实机的路线图

---

## 结果入口

- [results/README.zh-CN.md](../results/README.zh-CN.md) — 结果文件、图表、验证数据
