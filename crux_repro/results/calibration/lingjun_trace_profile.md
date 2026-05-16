# Alibaba Lingjun Trace Calibration Profile

## 数据规模

- Job 行数: 5180
- Worker 行数: 23742
- Topology host 行数: 847
- Worker 表中出现的 job: 5294
- 能在 job.csv 对上的 worker job: 5051
- 有 GPU worker 的 job: 2816
- Worker host topology 覆盖: 20493 / 23742 (0.863154)

## 拓扑摘要

- DSW 数: 1
- PSW 数: 3
- ASW 数: 48
- Host 数: 847

## 时间分布

- 运行时长有效样本: 4368, 负值/异常样本: 0
- 排队时间有效样本: 4376, 负值/异常样本: 1
- 运行时长分位数(分钟): `{"min": 0.0, "p25": 1.0, "p50": 4.0, "p75": 18.0, "p90": 165.0, "p95": 660.6, "p99": 3287.72, "max": 20631.0}`
- 排队时间分位数(分钟): `{"min": 0.0, "p25": 1.0, "p50": 1.0, "p75": 2.0, "p90": 3.0, "p95": 6.0, "p99": 36.0, "max": 5416.0}`

## 可校准边界

强校准: 到达顺序/GPU 需求/worker 数/host-ASW-PSW-DSW 跨域跨度。

中等校准: 同一 replay workload 下的放置局部性、跨 host/跨交换机压力趋势、调度目标相对对比。

弱校准: 通信强度、带宽、延迟和拥塞惩罚仍然主要来自估算或保守默认值。

不支持: 真实 per-link byte counter、NCCL/HCCL 分 message size 耗时、ECMP 哈希路径、PFC/ECN、重传、host 内 PCIe/NVLink 细节。

## 验收含义

当前 trace 可以把算法验证从纯 synthetic workload 推进到真实 job replay 与真实机架层级拓扑约束；它不能单独证明实机网络性能。后续只要补少量 Greyhound/hook benchmark 记录，就能把网络模型从估算推进到半实测。
