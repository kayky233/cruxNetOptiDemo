# SimGrid 官方文档中文指引

> 原文: https://simgrid.org/doc/latest/Introduction.html
> SimGrid 版本: 4.1
> 翻译日期: 2026-05-14
> 说明: 本文档对 SimGrid 官方 Introduction 页面进行中文本地化，补充了本地环境相关注释，方便团队同事快速上手。

---

## 什么是 SimGrid

SimGrid 是一个**分布式应用在分布式平台上执行的模拟器开发框架**。它可以用于原型验证、评估和比较相关平台配置、系统设计以及算法方案。

简单来说：你写一份平台描述（有多少机器、网络怎么连、带宽多少），再写一份应用描述（程序做什么计算、发什么数据），SimGrid 负责模拟两者交互的整个过程，输出时间线、资源利用率等指标。

---

## SimGrid 能做什么

以下几个目标场景是 SimGrid 特别擅长且已被广泛使用的：

### 1. 方案对比

研究人员/开发者的经典用法：用 SimGrid 评估自己提出的方案（平台、系统、应用或算法设计）与文献中已有方案的优劣。不用买硬件就能跑对比实验。

### 2. 为给定应用设计最优模拟平台

修改平台描述文件来驱动模拟，远比搭建真实平台做测试容易。SimGrid 还支持平台和应用的**协同设计**——两者都可以低成本修改迭代。

### 3. 调试真实应用

在真实系统中，很难精确复现导致某个 bug 的具体执行过程。而 SimGrid 提供**可复现实验的"全知视角"**：你可以探查系统的每一个部分，并且探查行为不会改变模拟状态。还可以轻松地 mock 或抽象掉不相关的系统部分。

### 4. 形式化验证算法

受模型检验（model checking）启发，SimGrid 提供一种执行模式：不量化应用的性能表现，而是**穷举探索应用所有因果可能的执行结果**，以评估应用的正确性。这种穷举搜索非常适合发现难以通过实验触发的 bug。但由于是穷举，能处理的应用规模有限。

---

## 使用 SimGrid 的项目的组成结构

任何以 SimGrid 为模拟框架的项目，都包含以下组件：

| 组件 | 说明 |
|---|---|
| **应用 (Application)** | 一个或多个进程，可以用 C++、Python 或 C 的简易 API 描述分布式算法，也可以是完整的 MPI 并行程序 |
| **模拟平台 (Simulated Platform)** | 用 XML 或 C++ 描述的分布式系统硬件（计算节点、网络链路、磁盘、集群等）。支持加入动态行为，如链路降速（外部占用）或机器故障 |
| **部署描述 (Deployment)** | 指定哪个进程映射到哪台机器上运行 |
| **平台模型 (Platform Models)** | SimGrid 实现了一系列模型，描述模拟平台如何响应应用进程产生的模拟活动。用户可以按需选择和配置。SimGrid 的核心优势之一是**能精确建模并发通信产生的网络竞争（network contention）** |

以上组件组合在一起运行模拟实验，产出的结果（日志、可视化、统计数据）帮助回答研究和开发问题。产出通常包括应用执行的时间线和能耗信息。

> 注意：SimGrid 好用，但不要盲目信任结果，应始终努力验证模拟结果的合理性。评估结果的真实程度会引导你更好地校准模型，这是获得高精度模拟的最佳路径。

---

## 实际操作方式

SimGrid 用法灵活，但最典型的设置是：

1. **用 C++ 或 Python 写算法**（通过 SimGrid API）+ **用官方提供的 XML 平台文件**——参考第一个教程「模拟分布式算法」
2. 如果应用已经是 MPI 写的，直接使用 SimGrid 的 MPI 支持——参考第二个教程「模拟 MPI 应用」
3. 第三个教程关于「形式化验证与模型检验」

官方提供了 Docker 镜像，无需安装 SimGrid 之外的任何软件即可运行这些教程。

SimGrid 附带大量**示例**，可以通过拼装和修改示例来快速启动自己的模拟器。左侧菜单栏提供了完善的文档。

---

## SimGrid 成功案例

- 被 **3,000+ 篇科学论文**引用（Google Scholar）
- 其中 675+ 篇出版物将 SimGrid 作为科学仪器进行实验评估
- 横跨多个研究社区：高性能计算、云计算、工作流调度、大数据/MapReduce、数据网格、志愿计算、P2P 计算、网络架构、雾计算、批调度等

**真实案例**：
- 在 Tibidabo ARM 集群**建立之前**就通过 SimGrid 预测了其加速比。模拟与实测之间的差异最终被追溯到真实平台的配置错误——SimGrid 甚至可以用来调试真实平台。
- 用于调试和改进多个大型应用：BigDFT（CEA 的大规模并行化学计算代码）、StarPU（Inria Bordeaux 的异构多核统一运行时系统）、TomP2P（苏黎世大学的高性能 KV 存储库）。

---

## SimGrid 的局限性

SimGrid 不是万能神器，有明确边界：

### 范围限制
- 专注于**分布式系统**，不适用于实时多线程系统
- 目前不支持 5G 或 LoRa 网络（可扩展，但尚未实现）

### 模型限制
没有完美的模型，只有适合你目标的模型。SimGrid 的模型设计目标是**大规模系统的快速、精确模拟**，因此抽象掉了许多对大多数场景无关的参数和现象。

**当前无法用 SimGrid 研究的问题**：
- L2/L3 缓存效应对应用的影响
- 内核调度器及策略对比
- TCP 变体对比
- TCP 崩溃导致的异常执行路径
- 存在恶意代理的安全问题

---

## 本地环境备忘

本团队已在 macOS arm64 上完成 SimGrid 4.1 的编译安装：

| 项目 | 路径 / 说明 |
|---|---|
| SimGrid 安装 | `/Users/dkwyl/Documents/tmbProject/net/.simgrid_install` |
| 依赖环境 | `/Users/dkwyl/Documents/tmbProject/net/.simgrid_env` (Boost/CMake/Ninja) |
| 模拟入口 (C++) | `crux_repro/simgrid_real/collective_sim.cpp` |
| 模拟入口 (Python) | `crux_repro/crux_sim.py` |
| Python 风格模拟器 | `crux_repro/simgrid_collective_sim.py` |
| 构建脚本 | `crux_repro/simgrid_real/build.sh` |
| 批量运行脚本 | `crux_repro/simgrid_real/run_all.sh` |

### 构建命令

```bash
cd /Users/dkwyl/Documents/tmbProject/net
MAMBA_ROOT_PREFIX=/Users/dkwyl/Documents/tmbProject/net/.mamba \
  /Users/dkwyl/Documents/tmbProject/net/.tools/micromamba/bin/micromamba run \
  -p /Users/dkwyl/Documents/tmbProject/net/.simgrid_env \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/build.sh
```

### 运行命令

```bash
cd /Users/dkwyl/Documents/tmbProject/net
DYLD_LIBRARY_PATH=/Users/dkwyl/Documents/tmbProject/net/.simgrid_install/lib:/Users/dkwyl/Documents/tmbProject/net/.simgrid_env/lib \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/run_all.sh
```

### macOS 注意事项
- SimGrid Python binding 在 macOS arm64 上存在 pybind11 property/call_guard 编译兼容问题，当前暂不使用
- 替代方案：通过 C++ S4U 接口直接编程，或用独立的 Python 仿真脚本（`crux_sim.py`、`simgrid_collective_sim.py`）做快速迭代

---

## 关键概念速查

| 英文术语 | 中文翻译 | SimGrid 中的含义 |
|---|---|---|
| Host | 主机 / 节点 | 模拟的计算节点，可执行计算任务 |
| Link | 链路 | 主机之间的网络连接，有带宽和延迟属性 |
| Route | 路由 | 从源主机到目标主机经过的链路序列 |
| Actor | 执行体 | SimGrid 中的并发执行单元，类似线程/进程 |
| Activity | 活动 | 计算 (execute)、通信 (comm)、I/O 等异步操作 |
| Mailbox | 邮箱 | Actor 之间通信的消息通道 |
| Platform | 平台 | 所有 Host/Link/Route 的集合描述 |
| Deployment | 部署 | Actor 到 Host 的映射关系 |
| S4U | SimGrid for You | SimGrid 的现代 C++ API |
| SMPI | Simulated MPI | SimGrid 的 MPI 模拟层 |

---

## 后续学习路径

1. 官方教程（https://simgrid.org/doc/latest/Tutorials.html）
   - Simulating Algorithms（分布式算法模拟 — 推荐首先阅读）
   - Simulating MPI Applications（MPI 应用模拟）
   - Model-checking Algorithms（模型检验）

2. 官方示例（安装目录下的 `examples/`）

3. 平台描述（https://simgrid.org/doc/latest/Platform.html）
   - XML 平台格式
   - C++ 平台定义
   - 网络拓扑示例

4. S4U API 文档（https://simgrid.org/doc/latest/API.html）

5. 当前项目的模拟方案：`SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md`
