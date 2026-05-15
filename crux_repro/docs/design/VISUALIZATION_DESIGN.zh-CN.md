# Crux/SimGrid 可视化方案设计

## 0. 目的

基于当前 SimGrid 模拟产生的数据和拓扑定义，实现三类可视化：

1. **GPU 可视化**：GPU 放置热力图、利用率、job 时间线
2. **交换机网络可视化**：静态拓扑图、链路利用率、瓶颈分析
3. **网络路径选择可视化**：job 流量的交换机路径分布、跨主机通信矩阵

产出物为 Python 脚本 + SVG/PNG 图表，可直接嵌入 Markdown 报告或用于评审。

---

## 1. 现有数据与缺口分析

### 1.1 可直接使用的数据

| 数据文件 | 关键字段 | 用途 |
|---|---|---|
| `results/simgrid_real_trace_optimize_balanced_results.csv` | scheduler, makespan_s, avg_jct_s, avg_comm_s, useful_gpu_fraction | 汇总对比 |
| `results/simgrid_real_trace_optimize_balanced_jobs.csv` | scheduler, job_id, model, ranks, sim_start_s, sim_finish_s, jct_s, comm_s, compute_s, intensity, placement | job 时间线、GPU 放置、per-job 对比 |
| `results/simgrid_trace_workload.csv` | job_id, model, ranks, compute_s, tensor_gib | 模型标注 |
| `simgrid_real/topology.h` | star/fat_tree/three_tier_clos/dragonfly 参数 | 拓扑图渲染、路径计算 |

### 1.2 需要补充的数据

| 缺口 | 当前状态 | 补充方式 | 优先级 |
|---|---|---|---|
| 链路利用率数据 | `--link-out` 参数存在，但近期未使用 | 重跑一次 trace optimize balanced 加 `--link-out` 参数 | 高 |
| 每 GPU 时间线 | 仅 aggregate useful GPU fraction | 需在 C++ 模拟器里增加 per-GPU busy/idle 采样输出 | 中 |
| flow 级路径跟踪 | 仅知道 placement，可推算路径 | 可从 placement + topology 确定性计算 | 低（可算） |
| 通信 step 级分解 | 仅 aggregate comm_s | 需在 C++ 模拟器增加 step 级 timing 输出 | 低 |

### 1.3 关键洞察：路径可从 placement 确定性计算

当前 C++ 模拟器的路由是确定的：

```cpp
// collective_sim.cpp build_platform()
sw[lvl][(h1*31 + h2*17 + (int)lvl*7) % sw[lvl].size()]
```

已知 job 的 placement（`host:gpu;host:gpu;...`）和 topology 定义，就可以计算出该 job 的 Ring AllReduce 每一步每一对 rank 之间的跨机流量经过哪些交换机，无需修改 C++ 代码即可做路径可视化。

---

## 2. 分阶段实现方案

### Phase 1 — 零代码改动，基于现有 CSV 立即可做

不需要重新跑模拟，不需要改 C++，直接 Python 读取现有 CSV 渲染。

#### 图 1.1：Job Gantt 图（时间线）

- **数据源**：`jobs.csv` → `sim_start_s`, `sim_finish_s`, `model`
- **图表形式**：水平条形图，x 轴为时间，每个 job 一条，颜色按 model 或 intensity
- **对比维度**：左右并排 `random_same` vs `crux_no_compress`
- **可读出**：哪些 job 变短了，makespan 的构成，job 并发窗口

#### 图 1.2：GPU 放置热力图

- **数据源**：`jobs.csv` → `placement` 字段（`host:gpu;host:gpu;...`）
- **图表形式**：矩阵热力图，行 = host (0..7)，列 = GPU slot (0..3)，格子颜色 = 该 GPU 被哪个 job 占用
- **对比维度**：`random_same` vs `crux_no_compress` 并排
- **可读出**：crux 把高通信强度 job 收敛到更少 host，减少跨机通信

#### 图 1.3：Job 级 JCT / Comm 对比

- **数据源**：`jobs.csv` → `jct_s`, `comm_s`
- **图表形式**：分组柱状图，每 job 两根柱子（baseline vs crux），分 JCT 和 comm 两个子图
- **对比维度**：12 个 job，看每个 job 的收益/退化
- **可读出**：哪些 job 改善最大，哪些退化，退化原因

#### 图 1.4：静态网络拓扑图

- **数据源**：`topology.h` → make_star / make_three_tier_clos 参数
- **图表形式**：networkx + matplotlib 绘制的拓扑图，节点 = host/switch，边 = link，标注带宽
- **配置**：当前配置 8 hosts × 4 GPUs，star 拓扑或 three_tier_clos
- **可读出**：网络层级结构、带宽层级、潜在瓶颈位置

#### 图 1.5：Job 通信强度分布

- **数据源**：`jobs.csv` → `intensity`, `model`, `tensor_gib`
- **图表形式**：散点图或柱状图，x=job_id，y=intensity，颜色按 model
- **可读出**：workload 中高/低通信 job 的分布

### Phase 2 — 一次重跑获取链路数据

需要重新运行一次 trace optimize balanced 模拟，加上 `--link-out` 参数。

#### 图 2.1：链路利用率排序图

- **数据源**：`--link-out` 输出的 CSV → link_name, utilization
- **图表形式**：水平条形图，利用率降序，标注瓶颈链路（>80%）
- **可读出**：哪些链路是系统瓶颈，瓶颈在 local / NIC / switch 哪一层

#### 图 2.2：链路利用率热力图

- **数据源**：同上
- **图表形式**：矩阵热力图，行 = 链路类型（local/NIC/sw0/sw1/sw2），列 = 索引，颜色 = 利用率
- **对比维度**：`random_same` vs `crux_no_compress`
- **可读出**：crux 是否把负载从拥塞链路移走了

#### 图 2.3：交换机层级利用率分布

- **数据源**：同上
- **图表形式**：箱线图或小提琴图，每个交换机层级一个分布
- **可读出**：瓶颈集中在哪一层（ToR / Agg / Core）

### Phase 3 — C++ 增加输出后实现（远期）

#### 图 3.1：流级别路径可视化

- 需要 C++ 模拟器输出每个 flow 的 (src_rank, dst_rank, bytes, path_links)
- 可视化：源-目的 pair 之间的箭头/路径高亮

#### 图 3.2：GPU 利用率时间线

- 需要 C++ 模拟器按固定间隔采样每个 GPU 的 busy/idle 状态
- 可视化：热力图，行=GPU，列=时间，颜色=利用率

#### 图 3.3：通信 step 分解

- 需要 C++ 模拟器输出每个 collective step 的起止时间
- 可视化：Gantt 子图，展示 compute/comm/waiting 的分解

---

## 3. 技术选型

| 层 | 选择 | 原因 |
|---|---|---|
| 语言 | Python 3 | 与现有 `report_results.py` / `analyze_job_timeline.py` 一致 |
| 数据加载 | pandas | CSV 读取方便 |
| 静态图表 | matplotlib + seaborn | 通用、可控、SVG 输出 |
| 拓扑图 | networkx + matplotlib | 图布局算法成熟，适合 small-scale 拓扑 |
| 交互式图表（可选） | plotly | 如果需要 hover 看数值细节 |
| 报告整合 | Markdown + 内嵌 SVG | 与现有报告风格一致 |
| 命令行接口 | argparse | 与现有脚本一致 |

---

## 4. 模块架构

```
crux_repro/
  vis/                          # 新增可视化模块目录
    __init__.py
    vis_main.py                 # 入口，argparse 调度
    vis_data.py                 # 数据加载与预处理
    vis_topo.py                 # 拓扑图渲染（图 1.4）
    vis_gantt.py                # Job Gantt 图（图 1.1）
    vis_placement.py            # GPU 放置热力图（图 1.2）
    vis_job_compare.py          # Job 级对比（图 1.3）
    vis_intensity.py            # 通信强度分布（图 1.5）
    vis_link.py                 # 链路利用率（Phase 2，图 2.1-2.3）
    vis_path.py                 # 路径选择分析（图 1.4 叠加 + Phase 3）
    vis_utils.py                # 通用样式、配色、字体
    vis_report.py               # 生成 Markdown 报告
```

### 命令行接口设计

```bash
# 生成全部 Phase 1 图表
python vis/vis_main.py \
  --results results/simgrid_real_trace_optimize_balanced_results.csv \
  --jobs results/simgrid_real_trace_optimize_balanced_jobs.csv \
  --topology three_tier_clos \
  --hosts 8 --gpus-per-host 4 \
  --out-dir results/vis/

# 只生成特定图
python vis/vis_main.py ... --charts gantt,placement,topo

# Phase 2: 带链路数据
python vis/vis_main.py ... \
  --links results/simgrid_real_trace_optimize_balanced_links.csv
```

---

## 5. Phase 1 各图详细设计

### 5.1 Job Gantt 图

```
┌──────────────────────────────────────────────────────────┐
│  random_same                              crux_no_compress │
│                                                           │
│  job11 ████                                job11 ██       │
│  job5  ██████                              job5  ██████   │
│  job8  ████████                            job3  ███████  │
│  job3  ██████████                          job8  ███████  │
│  job6  ██████████████                      job6  █████████│
│  job7  ██████████████                      job7  █████████│
│  job0  ███████████████                     job9  █████████│
│  job9  █████████████████                   job0  █████████│
│  job10 ████████████████████                job10 █████████│
│  job4  ████████████████████████████        job4  █████████│
│  job1  █████████████████████████████████   job2  █████████│
│  job2  ███████████████████████████████████ job1  █████████│
│        0        50       95.3                    0      83.2│
└──────────────────────────────────────────────────────────┘
```

- Y 轴按 JCT 排序，短 job 在上
- 颜色按 model 类型
- 标注 makespan 竖线
- 输出：SVG + PNG

### 5.2 GPU 放置热力图

```
        random_same                  crux_no_compress
     GPU0 GPU1 GPU2 GPU3         GPU0 GPU1 GPU2 GPU3
H0  [ j0 ] [ j0 ] [ j4 ] [ j0 ]  [ j1 ] [ j9 ] [j10] [j10]
H1  [ j1 ] [j10] [ j0 ] [ j1 ]  [ j1 ] [ j9 ] [j10] [j10]
H2  [ j2 ] [ j0 ] [ j6 ] [ j4 ]  [ j9 ] [ j3 ] [ j6 ] [ j6 ]
H3  [ j2 ] [ j4 ] [ j4 ] [ j2 ]  [ j9 ] [ j3 ] [ j6 ] [ j6 ]
H4  [ j2 ] [ j6 ] [ j6 ] [ j1 ]  [ j7 ] [ j9 ] [ j3 ] [ j3 ]
H5  [ j2 ] [ j3 ] [ j7 ] [ j7 ]  [ j7 ] [ j9 ] [ j3 ] [ j3 ]
H6  [ j7 ] [ j8 ] [ j8 ] [ j8 ]  [ j4 ] [ j1 ] [ j5 ] [ j4 ]
H7  [ j4 ] [ j8 ] [ j8 ] [ j8 ]  [ j4 ] [ j1 ] [ j5 ] [ j4 ]
```

- 每个格子 = 一个 GPU slot
- 颜色 = job ID / model
- crux 侧明显可见高通信 job（如 GPT-large job4）集中在 H6/H7
- 下方标注每个 host 的 job 分布熵（集中度）

### 5.3 Job 级 JCT / Comm 对比

```
  JCT (s)                              Comm (s)
  random  crux                          random  crux
j0  ████████  ████████                  ██████  ████
j1  █████████████████  ███████████████  ██████████  ████████
...
```

- 双面板：左 JCT，右 comm
- 每 job 两根柱子
- 标注 gain/loss 百分比

### 5.4 静态拓扑图

```
     [H0] [H1] [H2] [H3] [H4] [H5] [H6] [H7]
      |    |    |    |    |    |    |    |
   NIC0 NIC1 NIC2 NIC3 NIC4 NIC5 NIC6 NIC7
      \    |    /    \    |    /    \    |
       [sw0_0]         [sw0_1]        [sw0_2]  ...   ← ToR (8)
           \              |             /
            [sw1_0]     [sw1_1]    [sw1_2]  [sw1_3]  ← Agg (4)
                 \       |       /
                [sw2_0]        [sw2_1]                 ← Core (2)
```

- networkx spring/分层布局
- 节点形状区分：方=host，圆=NIC，菱形=switch
- 边标注带宽
- 输出：SVG（可缩放）

### 5.5 通信强度分布

```
  intensity (log)
  10^10 ┤
        │       ● GPT-large
  10^9  │  ●●●  ●● GPT      ●● unknown-mid
        │  ● unknown-8gpu    ● unknown-large
  10^8  │
        └──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──
          0  1  2  3  4  5  6  7  8  9 10 11
```

- 标注 intensity 中位数分界线（balanced 模式用它区分高/低通信 job）
- 标注每个 job 的 model 名

---

## 6. 路径选择可视化（Phase 1 可做）

### 6.1 跨主机通信矩阵

对每个 job，从其 placement 计算出跨机 rank pair 集合：

```
Job 4 (GPT-large), random_same placement:
  hosts: {0,1,2,3,7}
  跨机连接: 0↔1, 0↔2, 0↔3, 0↔7, 1↔2, 1↔3, 1↔7, 2↔3, 2↔7, 3↔7
  → 涉及 5 台 host，最多 C(5,2)=10 条跨机路径

Job 4 (GPT-large), crux_no_compress placement:
  hosts: {6,7}
  跨机连接: 6↔7
  → 只涉及 2 台 host，1 条跨机路径
```

可视化：矩阵热力图，行=job，列=跨机路径数，对比 random vs crux。

### 6.2 交换机使用分布

对每个 job，计算其跨机流量经过哪些交换机：

```
Job 4 (GPT-large), random_same:
  ToR  : sw0_0, sw0_1, sw0_2, sw0_3, sw0_7  (5/8)
  Agg  : sw1_0, sw1_1, sw1_2, sw1_3          (4/4)
  Core : sw2_0, sw2_1                         (2/2)
  → 几乎全网

Job 4 (GPT-large), crux_no_compress:
  ToR  : sw0_6, sw0_7                         (2/8)
  Agg  : sw1_0, sw1_1, sw1_2, sw1_3          (4/4, 但流量少)
  Core : sw2_0                                 (1/2)
  → 大幅收敛
```

可视化：堆叠条形图或热力图，行=job，列=switch，颜色=是否经过。

### 6.3 总交换机负载热力图

对所有 job 的跨机流量做交换机级别的聚合：

```
         sw0_0 sw0_1 sw0_2 sw0_3 sw0_4 sw0_5 sw0_6 sw0_7
random   ████  ████  ████  ████  ████  ████  ████  ████
crux     ████  ████  ████  ████  ██    ██    ██████████
```

- 颜色深度 = 经过该交换机的 job 数或流量权重
- 可以按交换机层级分组

---

## 7. 输出物清单

### Phase 1 输出（6 张图 + 1 个报告）

| 序号 | 文件名 | 描述 | 数据依赖 |
|---|---:|---|---|
| 1 | `gantt_comparison.svg` | Job Gantt 对比 | jobs.csv |
| 2 | `placement_heatmap.svg` | GPU 放置热力图 | jobs.csv |
| 3 | `job_jct_comm_comparison.svg` | Job JCT/Comm 对比 | jobs.csv |
| 4 | `topology_diagram.svg` | 静态网络拓扑图 | topology.h 参数 |
| 5 | `intensity_distribution.svg` | Job 通信强度分布 | jobs.csv |
| 6 | `path_switch_heatmap.svg` | 交换机路径分布热力图 | jobs.csv + topology 计算 |
| - | `vis_report.md` | 可视化报告，内嵌所有 SVG | 以上全部 |

### Phase 2 输出（3 张图）

| 序号 | 文件名 | 描述 | 数据依赖 |
|---|---:|---|---|
| 7 | `link_utilization_bar.svg` | 链路利用率排序 | --link-out CSV |
| 8 | `link_utilization_heatmap.svg` | 链路利用率热力图 | --link-out CSV |
| 9 | `switch_level_utilization.svg` | 交换机层级利用率分布 | --link-out CSV |

---

## 8. 开发计划

### Step 1：搭框架（1 个文件）

`vis/vis_data.py` — 数据加载：

```python
def load_results(path) -> pd.DataFrame
def load_jobs(path) -> pd.DataFrame
def load_workload(path) -> pd.DataFrame
def load_topology(name, hosts, gpus_per_host) -> TopologyConfig
```

### Step 2：实现 Phase 1 六张图（每图一个文件）

按依赖顺序：

1. `vis_intensity.py`（无依赖，最简单）
2. `vis_topo.py`（只依赖 topology 定义）
3. `vis_gantt.py`（只依赖 jobs CSV）
4. `vis_placement.py`（只依赖 jobs CSV）
5. `vis_job_compare.py`（只依赖 jobs CSV）
6. `vis_path.py`（依赖 jobs CSV + topology 计算）

### Step 3：入口脚本 + 报告生成

`vis_main.py` + `vis_report.py`

### Step 4：Phase 2 链路图（需先重跑模拟）

`vis_link.py`

---

## 9. 配色与样式约定

| 元素 | 配色 | 说明 |
|---|---|---|
| random_same | 灰色系 `#888888` | 基线，低调 |
| random_intensity | 蓝色系 `#4477AA` | 过渡策略 |
| crux_no_compress | 橙色系 `#EE7733` | 主要对比对象 |
| crux | 红色系 `#CC3311` | 完整 Crux |
| high intensity job | 暖色 | 通信密集型 |
| low intensity job | 冷色 | 计算密集型 |
| 改善 | 绿色 `#228833` | 正向收益 |
| 退化 | 红色 `#EE6677` | 负向退化 |

- 中文字体：PingFang SC / Heiti SC（macOS 系统自带）
- SVG 输出，确保文字可缩放、可搜索
- 统一 16:9 或 4:3 比例，适合嵌入幻灯片

---

## 10. 确认清单

在开始编码前确认：

- [ ] Phase 1 六张图的设计是否符合预期？
- [ ] 是否需要调整优先级（比如先做某几张）？
- [ ] 是否需要交互式版本（plotly HTML）还是纯静态 SVG？
- [ ] `--link-out` 重跑是否要现在就做（Phase 2）还是等 Phase 1 完成再说？
- [ ] 拓扑图需要展示哪种拓扑（star / three_tier_clos / 可切换）？
- [ ] 输出目录放在 `results/vis/` 是否合适？

---

## 11. 开源项目借鉴分析

对业界已有的集群拓扑、网络路径、通信调度可视化项目做了梳理，按相关度分为四档。

### 11.1 可直接参考的项目（同类场景、代码可读）

| 项目 | 仓库/站点 | 借鉴点 | 与我们方案的对应 |
|---|---|---|---|
| **SimGrid Graphicator** | `simgrid/tools/graphicator/` (C++) | 读取 SimGrid platform 定义，渲染 host-link-switch 层级拓扑图 | **图 1.4 静态拓扑图** — 其网络分层布局思路可直接复用。Graphicator 用简单的网格/分层 layout，不依赖复杂力导向算法，适合我们的 small-scale 拓扑 |
| **hwloc / lstopo** | `github.com/open-mpi/hwloc` | 硬件拓扑可视化标杆：CPU/GPU/NUMA/NIC 层级用嵌套方框 + 连线表达，支持 SVG/PNG/PDF/text 多种输出 | **图 1.2 GPU 放置热力图** — lstopo 的"方框嵌套 + 着色"风格可参考替代纯 heatmap；**图 1.4 拓扑图** — 其分层布局比 networkx spring layout 更适合网络拓扑 |
| **Nsight Systems** | NVIDIA 官方 | 分布式训练 trace 可视化黄金标准：时间线 + GPU kernel/NCCL communication 叠加显示，支持 per-GPU timeline 和 NCCL 通信矩阵 | **图 1.1 Job Gantt** — 参考其 compute/comm 分层时间线；**Phase 3 图 3.2** — per-GPU 时间线的目标形态 |

### 11.2 设计理念可借鉴（同类问题，但尺度/场景不同）

| 项目 | 借鉴点 | 我们的应用 |
|---|---|---|
| **Vampir / Intel Trace Analyzer** | MPI 通信 trace 分析：timeline 上每个 rank 的 compute/comm/wait，配通信矩阵视图和 call-tree。商业软件，但可视化范式成熟 | 我们的 Job Gantt + 跨机通信矩阵 = Vampir 的简化版。它的"timeline + matrix 联动"思路，可以用 plotly subplot 联动实现 |
| **Jumpshot (MPICH)** | 经典 MPI log 可视化：每个 MPI rank 一条时间线，颜色区分 compute / MPI / idle | 与 Vampir 类似，但更轻量。它的时间线渲染可以用 matplotlib `broken_barh` 等效实现 |
| **Paraver (BSC)** | 灵活的 trace 可视化：用户自定义 timeline 渲染规则（颜色、分组、统计），支持 CPU burst 和 MPI 通信叠加 | 其"可配置 timeline 配色规则"的思路可借鉴：按 intensity 分色、按 model 分色、按 placement 分色的多个视图 |
| **TensorBoard Profiler (PyTorch)** | 训练迭代的 trace viewer：显示 GPU kernel、CPU op、AllReduce 通信的时间线，支持按算子类型着色 | 如果后续 extends 到 per-step 输出（Phase 3），可参考其"compute bar + comm bar + overlap 虚线"的表达方式 |

### 11.3 Python 绘图生态中可直接用的轮子

| 库 | 用途 | 替代什么 |
|---|---|---|
| **networkx + matplotlib** | 图（graph）布局和渲染，内置 spring / shell / layered / bipartite 布局 | 当前方案已选用做拓扑图。对 hierarchical 网络拓扑，建议用 `nx.shell_layout` 或手写分层坐标，而非 `spring_layout`（后者会把 switch 弹得到处都是） |
| **plotly** | 交互式图表：hover 数值、缩放、pan、点击高亮 | 如果需要交互，plotly 的 `timeline` / `heatmap` / `sankey` 可替代 static SVG。Sankey 图特别适合表达 flow 级路径（源 GPU → 链路 → 目的 GPU） |
| **graphviz (dot)** | 声明式层级图布局，天然适合树形/层级网络拓扑 | 对于 three_tier_clos 这种严格的层级拓扑，dot 的布局质量远优于 networkx。可以用 `pygraphviz` 生成后导出 SVG |
| **seaborn** | 统计图表：heatmap、boxenplot、violin | 当前方案已部分使用。heatmap 用于 GPU 放置热力图；violin 用于交换机利用率分布 |
| **altair / vega-lite** | 声明式可视化，自动生成交互式 web 图表 | 轻量替代 plotly，JSON 可复现 |
| **d3.js + Observable** | Web 端交互式网络 + 时间线可视化。Observable 上有大量 network topology / Gantt / heatmap 模板 | 如果需要 web 版交互式报告，d3 的 force-directed graph + brushable timeline 是标配 |
| **datashader** | 大规模散点/热力渲染（百万级点） | 如果后续 trace 规模变大（数百 job），datashader 可避免过度绘制 |

### 11.4 关联但不直接适用的项目

| 项目 | 为什么不错但不直接适用 |
|---|---|
| **NVIDIA DCGM + Grafana** | 实时 GPU 集群监控，时间序列 dashboard。适合在线监控，不适合离线模拟结果分析 |
| **Ganglia** | HPC 集群监控，架构过时 |
| **Gephi / Cytoscape** | 通用图分析 GUI，适合探索性分析。但需要 GUI 手动操作，无法脚本化生成报告 |
| **OMNeT++ IDE** | 网络仿真器的内置可视化。功能齐全但绑定 OMNeT++ 生态，不可脱离 |
| **ns-3 NetAnim** | ns-3 的拓扑/动画可视化。绑定 ns-3 XML trace 格式 |
| **mininet + ONOS GUI** | SDN 网络可视化。面向实时 SDN 控制平面，不是离线模拟分析 |

### 11.5 推荐借鉴优先级

| 优先级 | 项目 | 借鉴内容 | 落地方式 |
|---|---|---|---|
| **P0 立刻** | Graphicator (SimGrid) | 分层节点布局算法、bandwidth 边标注样式 | 写 `vis_topo.py` 时直接参考其 layout 策略 |
| **P0 立刻** | lstopo (hwloc) | 硬件拓扑方框嵌套渲染风格、SVG 输出格式 | 做 `vis_placement.py` 时参考，可选将热力图升级为"GPU slot 方框图" |
| **P1 Phase 1 内** | Jumpshot / Vampir | 时间线 + 通信矩阵双视图联动 | 做 `vis_gantt.py` + `vis_path.py` 的组合视图 |
| **P2 Phase 2+** | plotly Sankey | flow 级路径可视化 | 当有了 per-flow trace 数据后（Phase 3），用 Sankey 图展示源 GPU → 交换机 → 目的 GPU |
| **P2 Phase 2+** | graphviz dot | 严格的层级网络拓扑布局 | 当需要高质量 three_tier_clos/fat_tree 图时，用 dot 替代 networkx |

### 11.6 对当前技术选型的微调建议

基于以上调研，对第 3 节技术选型做以下调整：

| 原选型 | 调整 | 原因 |
|---|---|---|
| networkx spring_layout | → 手写分层坐标 (layered layout) 或 graphviz dot | 网络拓扑是严格层级结构，spring layout 不可控 |
| 纯 matplotlib 拓扑图 | → pygraphviz (graphviz wrapper) 生成分层图，matplotlib 做标注美化 | dot 的层级布局远优于 networkx |
| heatmap 表达 GPU 放置 | → 同时提供 heatmap + lstopo-style 方框嵌套图 | 方框图更适合静态报告，heatmap 更适合数据探索 |
