# S4U 接口指南

> 原文: https://simgrid.org/doc/latest/app_s4u.html
> 注意: 本文档聚焦核心概念和常用 API，完整 API 参考请查阅原文

S4U（SimGrid for you）是 SimGrid 的现代 C++ 接口，融合了 SimGrid 的全部能力和 C++ 的全部表达能力。从 v3.33（2023 春）起，S4U 是 SimGrid 描述算法的主接口。

---

## 核心理念

一个典型的 SimGrid 模拟由多个 **Actor** 组成，它们执行用户提供的函数。Actor 必须显式使用 S4U 接口来表达它们的**计算、通信、磁盘 I/O** 等 **Activity**，这些 Activity 消耗 **资源**（Host、Link、Disk）上的能力。SimGrid 预测每个 Activity 的耗时并据此编排 Actor 的执行。

### 关键概念速览

| 概念 | SimGrid 类 | 一句话解释 |
|---|---|---|
| 执行流 | `Actor` | 模拟中的独立执行单元，类似进程/线程 |
| 模拟引擎 | `Engine` | 全局单例，管理整个模拟 |
| 通信汇聚点 | `Mailbox` | Actor 之间通信的"约会点"，通过名字匹配 send/recv |
| 主机 | `Host` | Actor 的所在地，提供计算能力 |
| 链路 | `Link` | 连接主机，有带宽和延迟 |
| 网络区域 | `NetZone` | 平台的子区域，包含资源和路由 |
| 虚拟机 | `VirtualMachine` | 可在主机间迁移的执行容器 |

### Activity 类型

| Activity | 类 | 消耗的资源 |
|---|---|---|
| 计算 | `Exec` | Host CPU |
| 通信 | `Comm` | Link 带宽 |
| 磁盘 I/O | `Io` | Disk |
| 活动集合 | `ActivitySet` | —（等待集合中任意/全部完成） |

---

## 通信模型：Mailbox

Mailbox 是 SimGrid 通信的核心抽象。**数据不直接在 Actor 间发送，而是投递到 Mailbox**。

### Mailbox 的特点

- 通过**名字**（唯一字符串）访问，类似 URL
- 多个 Actor 可以向同一个 Mailbox 发送/接收
- **先到先服务**匹配：新到达的 send 匹配最旧的 enqueued receive
- Mailbox 不在网络上，访问无延迟；网络延迟仅取决于通信双方的物理位置

### 常见用法模式

**模式 1: 模拟 Socket 通信** — 用 `"hostname:port"` 作为 mailbox 名，确保只有一个 Actor 读取

**模式 2: 黄页模式** — 用服务名作为 mailbox 名（如 `"worker"`, `"master"`），发件人不需要知道接收方的位置甚至名字

### 阻塞 vs 异步

```cpp
// 阻塞通信 — Actor 被阻塞直到通信完成
Mailbox::put(data, size);   // 发送
Mailbox::get(data, size);   // 接收

// 异步通信 — 立即返回，Actor 可继续执行
CommPtr comm = Mailbox::put_async(data, size);
// ... 做其他事情 ...
comm->wait();               // 等待完成
comm->test();               // 检查是否完成（非阻塞）
comm->wait_for(timeout);    // 等待最多 timeout 秒
```

### 直接通信（不用 Mailbox）

```cpp
// 在两个 Host 之间直接通信，不走 Mailbox
Comm::sendto(src_host, dst_host, data, size);

// 异步版本
CommPtr comm = Comm::sendto_init(src_host, dst_host, data, size);
Comm::sendto_async(comm);
```

---

## 常用 API 速查

### Engine（模拟引擎）

```cpp
Engine e(&argc, argv);        // 初始化
e.load_platform("platf.xml"); // 加载平台
e.register_actor("func_name", my_function);  // 注册 actor 函数
e.load_deployment("deploy.xml");  // 加载部署
e.run();                      // 运行模拟
```

### Actor（执行体）

```cpp
// 创建和启动
ActorPtr a = Actor::create("name", host, my_function);
ActorPtr a = Actor::create("name", host, my_function, arg1, arg2);

// 查询
a->get_name();      // 名字
a->get_pid();       // 进程 ID
a->get_host();      // 所在主机

// 控制
a->suspend();       // 挂起
a->resume();        // 恢复
a->kill();          // 终止
a->join();          // 等待完成
a->daemonize();     // 设为守护（最后常规 actor 结束时自动终止）

// 自身操作 (在 actor 函数内部使用)
Actor::self();               // 获取当前 actor
this_actor::sleep_for(10);   // 睡眠 10 秒
this_actor::execute(1e9);    // 执行 1Gflop 计算
```

### Host（主机）

```cpp
Host* h = Host::by_name("host0");
h->get_speed();          // 计算速度 (flops/s)
h->get_core_count();     // 核心数
h->is_on();              // 是否在线
h->turn_off();           // 关机（模拟故障）
```

### Mailbox（邮箱）

```cpp
Mailbox* mb = Mailbox::by_name("worker");
mb->put(data, size);            // 阻塞发送
mb->get(data, size);            // 阻塞接收
CommPtr c = mb->put_async(data, size);  // 异步发送
CommPtr c = mb->get_async(&data, size); // 异步接收
```

### Activity 控制

```cpp
CommPtr comm = ...;
comm->wait();            // 等待完成
comm->test();            // 检查是否完成（非阻塞）
comm->wait_for(5.0);     // 等待最多 5 秒
comm->cancel();          // 取消
comm->get_remaining();   // 剩余字节数

// ActivitySet — 等待多个 activity 中的任意一个
ActivitySet set;
set.push(comm1);
set.push(comm2);
ActivityPtr done = set.wait_any();  // 返回第一个完成的
```

---

## 内存管理

S4U 使用 RAII 和智能指针。大多数对象通过 `XxxPtr`（即 `boost::intrusive_ptr<Xxx>`）引用，**不需要手动释放**。

```cpp
void myFunc() {
  MutexPtr mutex = Mutex::create();
  mutex->lock();
  // ...使用互斥锁...
  mutex->unlock();
}  // mutex 自动释放
```

> Mailbox、Host、Link 目前不使用智能指针，不能销毁（Host 可以用 `Host::destroy()` 但通常不需要）。

---

## 本团队使用情况

当前 `collective_sim.cpp` 使用 S4U 接口：
- 每张 GPU 卡建模为一个 SimGrid Actor（rank actor）
- 使用 Mailbox 通信进行 Ring AllReduce 的每个 step
- 通过 `Comm::set_rate()` 近似实现优先级

下一步计划补充更多 S4U 特性（Tree/Hierarchical collective、traffic class 等）。
