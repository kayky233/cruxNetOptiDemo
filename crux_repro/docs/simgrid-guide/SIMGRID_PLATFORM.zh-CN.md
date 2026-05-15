# 描述模拟平台

> 原文: https://simgrid.org/doc/latest/Platform.html

SimGrid 中，平台通常用 **XML** 描述。将平台与应用程序分离是建模与仿真（M&S）工作的基本原则。当 XML 不够灵活时，可以[用 C++ 代码直接描述平台](https://simgrid.org/doc/latest/Platform_cpp.html)。

---

## 平台基本元素

任何模拟平台必须包含：

| 元素 | 说明 |
|---|---|
| `<host>` | 计算节点（CPU、内存） |
| `<link>` | 网络链路（带宽、延迟） |
| `<disk>` | 磁盘存储 |
| `<route>` | 主机之间的网络路径 |

SimGrid **不假设**平台的路由方式，你必须显式声明每对主机之间的网络路径。可以是一对一的 `<route>` 列表，也可以用**网络区域（NetZone）**来高效表达。

---

## 最小示例

```xml
<zone id="AS5-4" routing="Full">
  <host id="host0" speed="1Gf" />
  <host id="host1" speed="2Gf" />
  <link id="link0" bandwidth="125MBps" latency="100us" />
  <route src="host0" dst="host1">
    <link_ctn id="link0" />
  </route>
</zone>
```

- `routing="Full"` — 此区域内路由完全由显式的 `<route>` 描述
- 路由默认是对称的（双向）
- 不声明某些路由路径也是可以的，SimGrid 只在应用实际使用不存在的路径时才报错

> SimGrid 只做极小验证，允许奇特的拓扑（如整个平台共用一条链路）。**保证平台文件正确是你的责任。**

---

## 平台的关键概念

### 主机 (Host)

```xml
<host id="host0" speed="1Gf" core="4" />
```

- `speed`: 计算速度，单位 flops（如 `1Gf` = 1e9 flops）
- `core`: 核心数（默认 1）
- 可添加 `<prop>` 子元素设置自定义属性

### 链路 (Link)

```xml
<link id="link0" bandwidth="125MBps" latency="100us" />
```

- `bandwidth`: 带宽
- `latency`: 延迟
- `sharing_policy`: 共享策略（`SHARED`/`FATPIPE`）

### 网络区域 (NetZone)

平台是 NetZone 的树状结构。根区域包含整个平台。每个区域可使用不同的路由模型：

| 路由模型 | 说明 |
|---|---|
| `Full` | 显式声明所有 route |
| `Floyd` | 自动用 Floyd 算法计算最短路径 |
| `Dijkstra` | 用 Dijkstra 算法 |
| `Cluster` | 集群拓扑快捷方式 |
| `WIFI` | WiFi 网络 |

### 路由 (Route)

```xml
<!-- 对称路由 -->
<route src="host0" dst="host1">
  <link_ctn id="link0" />
</route>
```

区域间用 `<zoneRoute>` 连接。

---

## 实验场景（动态变化）

可以描述平台随时间的变化：

```xml
<!-- 带宽变化（模拟外部负载） -->
<prop id="availability_file" value="trace.txt" />

<!-- 机器故障和恢复 -->
<prop id="state_file" value="state_trace.txt" />
```

---

## 学习建议

- 最佳学习方式：参考 SimGrid 安装包中 `examples/platforms/` 目录下的大量示例
- 完整 XML 参考：[XML Reference](https://simgrid.org/doc/latest/XML_Reference.html)
- C++ 平台定义：[C++ platforms](https://simgrid.org/doc/latest/Platform_cpp.html)

---

## 本团队平台相关

当前 `collective_sim.cpp` 在 C++ 代码内动态创建平台（host、link、route）。按后续改进计划，将支持从配置文件生成平台，便于替换真实昇腾拓扑。
