# 配置 SimGrid

> 原文: https://simgrid.org/doc/latest/Configuring_SimGrid.html

SimGrid 提供大量运行时配置项来控制模拟行为。完整列表可通过 `--help-cfg` 查看。

---

## 三种配置方式

### 1. 命令行参数（最常用）

```bash
./my_simulator --cfg=Item:Value
# 多个配置
./my_simulator --cfg=network/model:SMPI --cfg=network/latency-factor:2.0
```

### 2. 平台文件内嵌

```xml
<config>
  <prop id="Item" value="Value" />
</config>
```

必须放在平台文件的最前面（在任何 `<zone>`、`<cluster>` 等之前）。

### 3. 程序内设置

```cpp
#include <simgrid/s4u.hpp>

int main(int argc, char* argv[]) {
    simgrid::s4u::Engine e(&argc, argv);
    simgrid::s4u::Engine::set_config("Item:Value");
    // ...
}
```

---

## 核心配置项速查

### 平台模型选择

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `network/model` | LV08 | 网络模型: LV08 / CM02 / SMPI / IB / Constant / Raw / ns-3 |
| `cpu/model` | Cas01 | CPU 模型（目前仅此一个） |
| `host/model` | default | 主机模型: default / ptask_L07 |
| `storage/model` | S19 | 磁盘模型 |
| `vm/model` | — | 虚拟机模型 |

查看所有可选值：

```bash
./my_simulator --cfg=network/model:help
./my_simulator --help-models
```

### 求解器与优化

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `network/optim` | Lazy | Lazy（默认）/ TI（trace integration）/ Full（调试用） |
| `cpu/optim` | Lazy | 同上 |
| `network/solver` | maxmin | maxmin / fairbottleneck / bmf |
| `maxmin/concurrency-limit` | -1（无限制） | 每资源最大并发 action 数 |

### 数值精度

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `precision/timing` | 1e-9（秒） | 时间比较精度 |
| `precision/work-amount` | 1e-5（flops 或 bytes） | 工作量比较精度 |

### 网络模型校正因子

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `network/latency-factor` | 13.01 (LV08) | 延迟乘数，可设常数或分段值 |
| `network/bandwidth-factor` | 0.97 (LV08) | 带宽乘数 |
| `network/weight-S` | 20537 (LV08) | RTT 不公平性权重 |
| `network/TCP-gamma` | 4194304 | TCP 最大窗口大小（0 = 禁用窗口机制） |
| `network/crosstraffic` | 1（启用） | ACK 竞争流量（LV08 下额外 5% 反向负载） |
| `network/loopback-lat` | 0 | 本地回环链路延迟 |
| `network/loopback-bw` | 10GBps | 本地回环链路带宽 |

**分段校正因子语法**（SMPI 风格）:

```
--cfg=network/latency-factor:65472:11.6436;15424:3.48845;...
```

格式: `边界:因子;...`，消息大小在 `[边界, 下一个边界)` 区间内使用对应因子。

### SMPI 专用

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `smpi/host-speed` | 20kf | 宿主机计算速度 (flops/s)，auto 自动测算 |
| `smpi/cpu-threshold` | 1e-6 | 低于此值的计算不上报模拟内核 |
| `smpi/simulate-computation` | yes | 是否模拟计算时间 |
| `smpi/display-timing` | no | 模拟结束时显示时间 |
| `smpi/privatization` | dlopen | 全局变量自动私有化: no / dlopen / mmap |
| `smpi/async-small-thresh` | 0 | 异步发送阈值（低于此值立即发送） |
| `smpi/send-is-detached-thresh` | 65536 | 分离发送阈值 |
| `smpi/buffering` | infty | MPI 缓冲: zero（禁用）/ infty（无限） |
| `smpi/coll-selector` | naive | 集合操作算法选择: naive / ompi / mpich |

### 上下文工厂（用户代码虚拟化）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `contexts/factory` | raw | raw（最快，仅 x86/amd64） / boost / thread（最兼容调试器） |
| `contexts/stack-size` | 8192 KiB | 每个 actor 的栈大小 |
| `contexts/guard-size` | 1 page | 栈保护页数量（0 禁用，性能更高但危险） |
| `contexts/nthreads` | 1 | 并行执行用户代码的线程数 |

### 日志

```bash
# 基本用法
--log=root.thresh:error                       # 只显示 error 及以上
--log=s4u_host.thresh:debug                   # 特定类别 debug
--log=root.fmt:%m                             # 只显示消息内容
--log=root.app:file:mylogfile                 # 输出到文件
--log=root.app:splitfile:500:mylog_           # 按大小分割文件
--log=root.app:rollfile:500:mylog             # 滚动文件

# 日志格式指令
%r  模拟时间      %a  Actor 名     %i  Actor PID
%h  主机名        %p  优先级       %c  类别
%m  用户消息      %l  源码位置     %F  文件名     %L  行号
```

### 调试

| 配置项 | 说明 |
|---|---|
| `debug/verbose-exit` | Ctrl-C 时显示所有 actor 状态（默认 on） |
| `debug/breakpoint` | 在指定模拟时间设断点（发 SIGTRAP） |
| `debug/clean-atexit` | 模拟结束时清理（默认 on） |

### 路径与插件

| 配置项 | 说明 |
|---|---|
| `path` | 搜索路径（可多次设置） |
| `plugin` | 激活插件（如 `host_energy`、`link_energy`、`host_load`） |

---

## 常用组合示例

```bash
# HPC MPI 模拟
--cfg=network/model:SMPI --cfg=smpi/host-speed:auto

# 调试模式（线程上下文 + 详细日志）
--cfg=contexts/factory:thread --log=root.thresh:debug

# 高性能模拟（大栈、无保护页）
--cfg=contexts/stack-size:128 --cfg=contexts/guard-size:0

# 禁用 TCP 窗口（模拟 UDP 或机内总线）
--cfg=network/TCP-gamma:0

# 启用能耗追踪
--cfg=plugin:host_energy --cfg=plugin:link_energy
```
