# iMaster NCE-Fabric 北向接口需求清单

> **用途**：提交华为侧接口对接人员，确认所需 API 的可用性、字段完整性、QPS 限制和认证方式。
> **项目**：Crux 通信感知调度 — 实机环境接入（阶段 1：只读采集）
> **日期**：2026-05-15

---

## 0. 背景

Crux 是一个通信强度感知的 GPU 集群调度优化器。它需要从 iMaster NCE-Fabric 获取集群的网络拓扑、链路状态、实时性能、AI 任务分布和 QoS 配置，作为调度决策的输入。

**阶段 1 目标**：只读采集，不修改任何网络配置。将环境数据写入本地 TDSQL + Redis，供优化器离线分析。

**数据流**：`iMaster API → Collector → TDSQL (历史) + Redis (在线快照) → Crux 优化器`

---

## 1. 接口清单

### 1.1 设备与拓扑

| # | 端点 | 方法 | 必需字段 | 用途 |
|---:|---|---|---|---|
| 1 | `/rest/openapi/network/nedevice` | GET | deviceId, deviceName, deviceType, deviceModel, ip, status, siteId | 获取集群内所有设备（服务器+交换机）清单。`deviceType=server/switch` 过滤 |
| 2 | `/acdcn/v3/topoapi/dcntopo/device` | GET | deviceId, deviceRole, rackId, siteId, uplinkDeviceList, downlinkDeviceList | 获取设备间拓扑层级（ToR/Leaf/Spine/Core）和机架位置 |

**分页**：`?pageIndex=N&pageSize=M`（需确认单页上限）
**QPS 预估**：1 次 / 5 min（全量采集，按 site 分组翻页）

### 1.2 链路与路径

| # | 端点 | 方法 | 必需字段 | 用途 |
|---:|---|---|---|---|
| 3 | `/rest/openapi/network/link` | GET | linkId, srcNodeId, dstNodeId, srcPortId, dstPortId, bandwidth, linkType, status | 获取所有物理链路及其带宽、类型 (HCCS/PCIe/Ethernet)、状态 |
| 4 | `/acdcn/v3/topoapi/dcntopo/getLinks` | POST | linkId, srcDeviceId, dstDeviceId, srcPortId, dstPortId | 批量获取链路拓扑（一次可传多个 deviceId） |
| 5 | `/rest/controller/dc/v3/north/dynamicmap/query-devicelink` | POST | 路径数组：经过的 deviceId 序列 | 查询两台设备间的端到端完整路径（经过哪些中间交换机） |

**分页**：link 接口 `pageIndex/pageSize`；getLinks 和 query-devicelink 为 POST body。
**QPS 预估**：2-3 次 / 1 min（按 site 分批拉取）

### 1.3 端口与接口

| # | 端点 | 方法 | 必需字段 | 用途 |
|---:|---|---|---|---|
| 6 | `/rest/openapi/network/port` | GET | portId, portName, portSpeed, portStatus, deviceId | 获取每台设备的物理端口及其协商速率、up/down 状态 |
| 7 | `/acdcn/v3/topoapi/dcntopo/getPorts` | POST | portId, deviceId, linkId | 批量获取端口-设备-链路三方绑定关系 |
| 8 | `/rest/openapi/networkinventoryservice/v2/interfaces` | GET | ifName, ifIndex, mtu, speed, adminStatus, operStatus, ipAddress | 获取逻辑接口详情（MTU、IP、状态） |

**分页**：按 deviceId 分批查询；getPorts 为 POST body 批量。
**QPS 预估**：3-5 次 / 30s（按设备分组翻页）

### 1.4 实时性能与历史数据 ⚠️ SLA: 不一致 < 30s

| # | 端点 | 方法 | 必需字段 | 用途 |
|---:|---|---|---|---|
| 9 | `/rest/openapi/dps-service/v1/realtime-task` | PUT | taskId（返回）, metricType, deviceIds[], interval | 创建实时性能采集任务。metricType 至少需要: `link_util`, `link_latency`, `link_loss` |
| 10 | `/rest/openapi/dps-service/v1/history-data` | POST | metricType, deviceIds[], timeRange, 时间序列数据点 | 查询历史性能。额外需要 metricType: `queue_depth`, `ecn_marked`, `pfc_pause` |

**QPS 预估**：
- 创建任务：1 次 / 5 min（任务长驻）
- 查询历史：3-5 次 / 30s（按时间窗口拉取）

**关键确认**：
- ⚠️ `link_latency` 是主动探测值 (TWAMP) 还是设备统计值？这影响路径代价公式。
- ⚠️ 是否支持 `queue_depth` / `ecn_marked` / `pfc_pause` 这些 metricType？

### 1.5 算卡与 AI 任务

| # | 端点 | 方法 | 必需字段 | 用途 |
|---:|---|---|---|---|
| 11 | 查询 NPU 卡地址信息 | GET | npuId, npuMac, npuIp, hostId, pcieAddr | 获取每张 NPU 的标识、网络地址、PCIe 地址 |
| 12 | VM/BM 列表 / Host 列表 | GET | hostId, hostName, hostType(BM/VM), npuList[], nicList[] | 获取服务器清单及其 NPU/NIC 绑定 |
| 13 | 查询主机链路 / 查询终端端口 | GET | hostId, switchId, switchPortId | 获取服务器到交换机的物理连接（用于构建 host↔ToR 映射） |
| 14 | 北向查询 AI 任务 | GET | jobId, jobName, status, npuList[], startTime, endTime | 获取当前运行的 AI 训练任务及其占用的 NPU 列表 |

**QPS 预估**：
- NPU / Host 列表：1 次 / 5 min
- AI 任务：1 次 / 30s（需轮询任务状态变化）

**关键确认**：
- ⚠️ NPU → NIC 绑定关系是直接可查，还是需要通过 hostId → NPU 列表 + hostId → NIC 列表交叉关联？
- ⚠️ AI 任务接口返回的 NPU 占用是实时还是最终一致？

### 1.6 RoCE 与 QoS 配置

| # | 端点 | 方法 | 必需字段 | 用途 |
|---:|---|---|---|---|
| 15 | RoCE 网络配置 | GET | roceEnable, globalConfig | RoCE 全局开关和参数 |
| 16 | 查询接口下 MTU/PFC/ECN/CRC/QoS | GET | ifName, pfcPriorityBitmap, ecnKmin/Kmax/Pmax, queueSchedule, crcErrorCount, trafficClassMap | 每接口的 PFC 使能优先级、ECN 阈值、队列调度策略、CRC 错误计数 |

**QPS 预估**：1 次 / 10 min（配置变更不频繁）
**关键确认**：是否支持按 deviceId 批量查询所有接口的 QoS 配置？

---

## 2. 汇总统计

| 类别 | 接口数 | 采集频率 | QPS 估算（单 site） |
|---|---|---|---|
| 设备与拓扑 | 2 | 5 min | < 1 QPS |
| 链路与路径 | 3 | 1 min | < 3 QPS |
| 端口与接口 | 3 | 30 s | < 5 QPS |
| 性能数据 | 2 | 10-30 s | < 5 QPS |
| 算卡与 AI 任务 | 4 | 30s-5min | < 2 QPS |
| QoS 配置 | 2 | 10 min | < 1 QPS |
| **合计** | **16** | — | **< 15 QPS** |

> 以上为单 site/集群的预估。多 site 场景按 site 数线性放大。请华为侧确认实际 QPS 上限，我们据此调整采集并发策略。

---

## 3. 数据依赖采集顺序

```
第 1 步 (初始化)          第 2 步 (拓扑构建)         第 3 步 (持续采集)
─────────────────────    ──────────────────────     ──────────────────────
nedevice (设备列表)  ──→  link (物理链路)      ──→  realtime-task (性能)
dcntopo/device       ──→  getLinks (链路拓扑)  ──→  history-data (历史)
Host 列表            ──→  port (端口)           ──→  AI 任务 (轮询)
                           getPorts (端口拓扑)
                           interfaces (接口)
                           query-devicelink (路径)
                           NPU 卡信息
                           RoCE/QoS 配置
```

- 第 1 步必须成功才能执行第 2 步（设备 ID 是后续查询的 key）
- 第 3 步是持续轮询，不依赖第 2 步的每次全量
- 每次全量采集的预期耗时 < 2 min（含翻页），留出 50% 空闲时间

---

## 4. 认证与环境

| 项 | 当前状态 | 说明 |
|---|---|---|
| 认证方式 | **待确认** | Token / HMAC / mTLS ? |
| 测试环境地址 | **待确认** | 测试集群的 iMaster NCE-Fabric 北向地址 |
| API 版本 | V100R024C10 | 基于 API 开发指南此版本 |
| 接口文档 | 已解包 (imaster_nce_fabric_api_extracted/) | 已做初步 API 检索 |
| 网络可达性 | **待确认** | Collector 部署机器到 iMaster 的网络连通性 |

---

## 5. 待华为侧确认的问题

按优先级排列：

| # | 问题 | 优先级 | 影响 |
|---:|---|---|---|
| Q1 | 各接口的 **QPS 上限** 和单次查询最大条目数？ | P0 | 决定并发采集策略 |
| Q2 | **NPU → NIC 绑定** 是否可直接查询？如果不能，如何交叉关联得到？ | P0 | host 内部拓扑建模的核心依赖 |
| Q3 | 性能接口的 `link_latency` 是 **主动探测** (TWAMP) 还是 **设备统计**？ | P0 | 决定路径代价公式使用什么时延值 |
| Q4 | 性能接口是否支持 `queue_depth` / `ecn_marked` / `pfc_pause` 这些 metricType？ | P1 | 影响拥塞感知精度 |
| Q5 | **认证方式** 和 **测试环境地址**？ | P0 | 阻塞联调 |
| Q6 | AI 任务接口返回的 NPU 占用是 **实时** 还是 **最终一致**？一致延迟约多少？ | P1 | 决定 placement 决策时效 |
| Q7 | 是否有接口可查询交换机的 **路由表 / FIB / ECMP 配置**？ | P1 | 影响 path selection 精度 |
| Q8 | 拓扑变更是否有 **webhook / 事件订阅** 机制？ | P2 | 目前可用定时全量对账替代 |

---

## 6. 联调接入计划

| 阶段 | 内容 | 预计耗时 | 入口 |
|---|---|---|---|
| 1 | 华为侧确认接口清单和 QPS 上限 | — | 本文档 |
| 2 | 获取测试环境地址 + 认证凭据 | 1d | 华为侧提供 |
| 3 | 单接口连通性验证（nedevice → link → port → metric） | 2d | Collector 开发 |
| 4 | 全量采集 + 翻页 + 错误处理 | 2d | Collector 开发 |
| 5 | TDSQL/Redis 写入 + 快照生成 | 2d | 存储层开发 |
| 6 | 数据质量校验（覆盖率、时效、缺失字段） | 1d | 质量报告 |
| 7 | 生成 SimGrid platform 配置文件 | 1d | topology_normalizer |

---

*此清单基于 iMaster NCE-Fabric V100R024C10 API 开发指南整理。接口细节以实际环境测试为准。*
