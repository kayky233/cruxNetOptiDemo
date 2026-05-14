# 模拟输出

> 原文: https://simgrid.org/doc/latest/Outcomes.html

SimGrid 提供三层输出机制：文本日志、图形/统计日志、自定义日志。

---

## 文本日志

使用 `printf` 或 `cout` 打印信息是可行的，但当多个 Actor 的输出混在一起时难以阅读。SimGrid 提供了受 Log4J 启发的日志机制。

### 四个核心概念

| 概念 | 说明 |
|---|---|
| **Category（类别）** | 消息主题，层次结构组织，大致对应 SimGrid 的模块架构 |
| **Priority（优先级）** | 严重程度：`trace` < `debug` < `verb` < `info` < `warn` < `error` < `critical` |
| **Threshold（阈值）** | 每个 Category 有一个阈值，低于阈值的消息被过滤 |
| **Appender（输出器）** | 决定消息输出到哪里：stderr、file、rollfile、splitfile |

### 基本命令行配置

```bash
# root 类别只显示 error 以上，s4u_host 显示 debug 以上
--log=root.thresh:error --log=s4u_host.thresh:debug

# 等价写法（空格分隔需要引号）
--log="root.thresh:error s4u_host.thresh:debug"
```

### 在代码中输出日志

```cpp
#include <simgrid/s4u.hpp>

XBT_INFO("Simulation starts");         // info 级别
XBT_DEBUG("Actor %s on %s", name, host); // debug 级别
XBT_WARN("Something unusual");         // warning 级别
XBT_CRITICAL("Fatal error");           // critical 级别
```

### 日志格式

```bash
# 默认格式 (info)
[hostname:actor_name:(pid) timestamp] file:line: message

# 自定义格式
--log=root.fmt:'[%h:%a:(%i) %r] %l: %m%n'
```

| 格式指令 | 含义 |
|---|---|
| `%r` | 模拟时间（从模拟开始算起） |
| `%a` | Actor 名称 |
| `%i` | Actor PID |
| `%h` | 主机名 |
| `%p` | 优先级名 |
| `%c` | 类别名 |
| `%m` | 用户消息 |
| `%F` | 源文件名 |
| `%L` | 行号 |
| `%l` | 位置（= `%F:%L`） |
| `%d` | 日期（UNIX 时间戳） |

`%15h` 限制主机名最多 15 字符，`%.4r` 限制时间精度到 4 位。

### 输出到文件

```bash
# 输出到文件
--log=root.app:file:mylogfile

# 分割文件（每 500 字节创建新文件）
--log=root.app:splitfile:500:mylog_

# 滚动文件（文件超过 500 字节时清空重写）
--log=root.app:rollfile:500:mylog
```

### 类别 Additivity

默认 appender 的 `additivity` 为 false（消息只传递到最具体的 appender）。设为 true 后消息会上传到父 appender。

```bash
# xbt 的消息会同时输出到 xbt.log 和 all.log
--log="root.app:file:all.log xbt.app:file:xbt.log xbt.add:yes"
```

### 实用命令

```bash
--help-logs              # 日志完整帮助
--help-log-categories     # 当前二进制的日志类别层次
--log=no_loc              # 隐藏源码位置（便于测试对比）
```

---

## 图形与统计日志

> 此部分原文标注 "To be written"。当前可通过 [FrameSaver/vizu 页面](https://simgrid.org/doc/latest/outcomes_vizu.html)了解更多。

---

## 自定义日志：信号（Signals）

可以为 SimGrid 的各种事件注册回调，自行决定如何记录和输出：

```cpp
// 注册通信完成回调
simgrid::s4u::Comm::on_completion_cb([](simgrid::s4u::Comm const& comm) {
    // 记录通信信息
    XBT_INFO("Comm from %s to %s completed, size=%zu",
             comm.get_sender()->get_cname(),
             comm.get_receiver()->get_cname(),
             comm.get_payload_size());
});

// 注册 Actor 创建/销毁回调
simgrid::s4u::Actor::on_creation_cb([](simgrid::s4u::Actor const& actor) {
    XBT_INFO("Actor %s created on %s", actor.get_cname(), actor.get_host()->get_cname());
});
```

一些用户用这种方式将模拟行为可视化到 **Jaeger** 等分布式追踪系统中。

---

## 追踪（Tracing）

SimGrid 的追踪子系统可以记录 Host 和 Link 的利用率时间线：

```bash
# S4U 模拟器 — 基础追踪
--cfg=tracing:yes --cfg=tracing/uncategorized:yes

# S4U 模拟器 — 分类追踪
--cfg=tracing:yes --cfg=tracing/categorized:yes

# SMPI 模拟器 — 时空视图
smpirun -trace ...
```

添加注释以标记实验：

```bash
--cfg=tracing/comment:my_simulation_identifier
--cfg=tracing/comment-file:my_file_with_additional_information.txt
```
