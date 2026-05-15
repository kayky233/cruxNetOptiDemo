# 部署应用

> 原文: https://simgrid.org/doc/latest/Deploying_your_application.html

部署（Deployment）是指定**哪个 Actor 在哪个 Host 上启动**的过程。可以在代码中直接做，也可以使用 XML 部署文件。

> 保持应用与部署分离是好习惯，便于后续实验。

---

## XML 部署文件

XML 部署只需要 3 个标签: `<actor>`、`<argument>`、`<prop>`，放在 `<platform>` 标签内。

### 基本示例

```xml
<?xml version='1.0'?>
<!DOCTYPE platform SYSTEM "https://simgrid.org/simgrid.dtd">
<platform version="4.1">

  <!-- 在 host1 上启动 alice() 函数，无参数 -->
  <actor host="host1" function="alice" />

  <!-- 在 host2 上启动 bob() 函数，参数 "3" 和 "3000" -->
  <actor host="host2" function="bob">
    <argument value="3" />
    <argument value="3000" />
  </actor>

  <!-- carol 在 host3 上启动，1 个参数 + 1 个属性 -->
  <actor host="host3" function="carol">
    <argument value="42" />
    <prop id="SomeProp" value="SomeValue" />
  </actor>

</platform>
```

### `<actor>` 标签属性

| 属性 | 必需 | 说明 |
|---|---|---|
| `host` | 是 | 启动该 Actor 的主机名 |
| `function` | 是 | 要执行的函数名（需提前通过 `Engine::register_actor()` 注册） |
| `start_time` | 否 | 延迟启动时间，-1 立即启动（默认） |
| `kill_time` | 否 | 自动终止时间，-1 不自动终止（默认） |
| `on_failure` | 否 | 主机故障重启后的行为: `DIE`（终止，默认）或 `RESTART` |

### `<argument>` 标签

向 Actor 的 argv 添加参数。语义完全取决于你的程序。

```xml
<argument value="hello" />
```

### `<prop>` 标签

设置 Actor 的属性，程序中用 `Actor::get_property()` 读取。

```xml
<prop id="batch_size" value="128" />
```

---

## 在代码中部署

```cpp
#include <simgrid/s4u.hpp>

int main(int argc, char* argv[]) {
    simgrid::s4u::Engine e(&argc, argv);
    e.load_platform("platform.xml");

    // 注册函数
    e.register_actor("alice", [](std::vector<std::string> args) {
        // Alice 的代码
    });

    // 直接在代码中创建 actor
    simgrid::s4u::Host* host1 = simgrid::s4u::Host::by_name("host1");
    simgrid::s4u::Actor::create("alice", host1, [](std::vector<std::string> args) {
        // Alice 的代码
    });

    e.run();
    return 0;
}
```

也可以混合使用：部分 actor 在 XML 部署，部分在代码中创建。

---

## 加载部署文件

```cpp
e.load_deployment("deploy.xml");
```

---

## 完整工作流

```
1. 写平台文件 (platform.xml)     → Host、Link、Route
2. 写应用代码 (main.cpp)         → Actor 逻辑
3. 写部署文件 (deploy.xml)       → Actor → Host 映射
4. 编译运行
```

```bash
# 编译
cmake . && make

# 运行（平台 + 部署）
./my_simulator platform.xml deploy.xml

# 或只给平台（actor 在代码中创建）
./my_simulator platform.xml
```
