# 公开数据校准与算法验收方案

## 目标

把当前调度算法验证从“合成 job + 估算网络”推进到“真实 trace replay + 可接入实机 profiler 的半实测模型”。在只有 Alibaba Lingjun 公开 trace 和 Greyhound 开源 hook/profiler 代码的阶段，验收重点不是证明绝对性能，而是证明算法在真实到达、真实资源需求、真实拓扑层级约束下仍能给出稳定、可解释的相对收益。

## 两类公开数据的作用

Alibaba Lingjun trace 用于校准 workload 和拓扑 replay：

- `job.csv`: job 到达、运行/结束时间、模型名、状态、topology-aware 标记。
- `worker.csv`: job worker 数、每个 worker 的 GPU/RDMA 资源、host 归属。
- `topo.csv`: host 到 `ASW/PSW/DSW` 的层级映射。

Greyhound 用于定义后续 profiler schema 和 hook 边界：

- 复用其 NCCL/HCCL hook 思路，规范记录 backend、collective、message bytes、world size、placement span、耗时分位数。
- 现有公开样例不能直接覆盖大规模 RDMA fabric，所以先作为 schema/采集规范，不把它当成真实链路校准数据。

## 校准强度分层

强校准：

- job 到达顺序和 replay workload。
- GPU 需求、worker 数、8 卡 host 分布。
- host/ASW/PSW/DSW 跨域跨度。

中等校准：

- 同一 replay workload 下不同 scheduler 的 placement locality。
- 跨 host、跨交换机压力趋势。
- makespan、排队、资源碎片等相对指标。

弱校准：

- 通信强度。
- 链路带宽、延迟、拥塞惩罚。
- 不同 collective op 的真实耗时曲线。

公开数据不支持：

- 真实 per-link byte counter。
- NCCL/HCCL 分 message size 耗时。
- ECMP 哈希路径、PFC/ECN、重传、拥塞控制。
- host 内 PCIe/NVLink 拓扑。

## 当前验收标准

1. `tools/profile_lingjun_trace.py` 能从 `../data/lingjun` 生成 JSON/Markdown profile。
2. profile 必须显式报告数据量、schema、GPU/worker/job/topology 分布、时间分位数和异常时间戳样本。
3. profile 必须显式写出 strong/medium/weak/not_supported 边界。
4. `configs/calibration/public_profiler_schema.json` 能作为未来 Greyhound/hook benchmark 记录格式。
5. `configs/calibration/default_public_calibration.json` 只能把网络参数标为 assumed，不能伪装成实测。
6. 调度算法比较必须在同一 replay、同一默认网络模型、同一资源池下做相对比较。

## 后续少量实机 benchmark 接入

拿到少量机器后，优先采集以下矩阵：

- same-host 2/4/8 GPU all_reduce。
- same-ASW 跨 2/4/8 host all_reduce。
- cross-ASW/same-PSW。
- cross-PSW。
- message bytes 覆盖 16MB、64MB、256MB、1GB。

每条 benchmark 记录按 `public_profiler_schema.json` 输出。接入后更新 calibration：

- 用 measured bandwidth/latency 替换 assumed defaults。
- 对 collective timing 拟合 `duration_ms = alpha + bytes / effective_bandwidth + contention_penalty`。
- 用 measured placement span 对当前 scheduler 的跨域惩罚权重做回归校准。

## 实机失效风险与控制

主要风险在网络层：如果真实 ECMP/PFC/拥塞行为与估算模型差异很大，算法可能高估跨机并行收益。控制方式是把验收分成两段：

- 公开数据阶段只宣称 replay/locality/relative pressure 有效。
- 实机 benchmark 阶段才宣称网络模型半实测有效。

这样即使实机出现偏差，也能快速定位是 workload replay、placement objective，还是 network calibration 的问题，而不是把问题混在一个黑盒模拟器里。
