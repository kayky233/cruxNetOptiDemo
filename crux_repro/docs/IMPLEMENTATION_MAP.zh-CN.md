# Crux 复现实现映射

这个文件说明离线模拟器中的实现如何对应 Crux 论文的各个章节。

## 论文第 3 节：GPU intensity

对应实现：`Job.intensity`

```python
job.intensity = job.compute_work / job.base_comm_time
```

模拟器把 `compute_work` 视为每轮迭代中的有效 GPU 计算工作量，把 `base_comm_time` 视为该作业在隔离环境下的通信时间。

## 论文第 4.1 节：感知 GPU intensity 的路径选择

对应实现：`assign_crux_paths`

作业会按照 GPU intensity 从高到低排序。每个作业会选择当前负载最低的候选 ECMP 路径。链路负载会按照流量和 intensity 加权，因此高 intensity 作业会优先被分散到不同路径上，避免彼此竞争。

## 论文第 4.2 节：优先级分配

对应实现：`assign_logical_priorities(..., mode="crux")`

论文会根据迭代特征和 compute/communication overlap 计算一个校正因子。这个模拟器使用一个紧凑的近似：

```python
correction = sensitivity * (1.0 + 1.0 / iteration_time)
logical_priority = intensity * correction
```

其中 `sensitivity = 1 - overlap_ratio`。如果一个作业的通信越难被计算隐藏，它就越紧急。

## 论文第 4.3 节：优先级压缩

对应实现：`contention_dag`、`random_topological_order`、`best_sequence_cut` 和 `compress_priorities`

模拟器会构造一个通信竞争 DAG：

- 节点：一个 DLT 作业；
- 有向边：高优先级作业可能与低优先级作业发生竞争；
- 边权重：高优先级作业的 GPU intensity。

代码会采样 10 个拓扑序，并选择最佳的序列 K-cut。由于本地复现使用的小规模作业数量较少，代码采用穷举切分；论文中使用的是更高效的动态规划形式。

## 论文第 5 节：部署机制

离线模拟器没有实现这一部分。

真实论文系统使用 RoCEv2 source-port steering 做 ECMP 路径选择，使用 traffic class 做跨主机优先级队列，并使用 semaphore 做主机内 PCIe 优先级。复现这些内容需要真实的多 GPU、多 NIC 测试环境。

## 论文第 6 节：评估

模拟器通过以下配置做定性对比：

- `random_same`：随机 ECMP，所有作业使用同一个优先级；
- `random_intensity`：随机 ECMP，加 intensity 优先级；
- `crux_no_compress`：Crux 路径选择，逻辑优先级数量充足，不做硬件优先级压缩；
- `crux`：Crux 路径选择，加有限硬件优先级下的优先级压缩。

预期趋势是：

```text
random_same < random_intensity < crux ~= crux_no_compress
```

这里不期待得到和论文完全一致的数值，因为这个模拟器没有使用生产 trace、NCCL kernel，也没有真实 GPU/NIC/PCIe 测量数据。
