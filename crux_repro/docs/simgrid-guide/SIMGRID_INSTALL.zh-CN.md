# 安装 SimGrid

> 原文: https://simgrid.org/doc/latest/Installing_SimGrid.html
> 版本: SimGrid 4.1

SimGrid 可在 Linux、macOS、FreeBSD 和 Windows (WSL) 上开箱即用。

---

## 预编译包

### Linux

```bash
# Debian/Ubuntu — C/C++ 开发
apt install libsimgrid-dev

# Python 开发
apt install python3-simgrid

# Java 开发（如果还需要）
apt install simgrid-java
```

- **Nix**: `simgrid` 在 Nixpkgs 中
- **Arch Linux**: `simgrid` AUR 包
- 其他发行版可以联系我们

### macOS (Homebrew)

```bash
brew install simgrid
```

**常见问题**: 如果出现 `dylib was built for newer macOS version` 警告，编译前设置:

```bash
export MACOSX_DEPLOYMENT_TARGET=14.0
```

### 版本编号与废弃策略

- 每年 4 个稳定版，如 3.24、3.25
- **向后兼容期一年**: 3.24 上无警告编译的代码可以在 3.28 上编译（可能有 deprecation 警告）
- 兼容包装器通常在 4 个版本后被移除
- 建议每年至少更新一次 SimGrid，修复 deprecation 警告

---

## 从源码编译

### 获取依赖

| 依赖 | 说明 | Debian/Ubuntu 安装 |
|---|---|---|
| C++ 编译器 | g++ ≥7.0、clang 或 icc（C++17） | `apt install g++` |
| CMake | ≥3.12 | `apt install cmake` |
| Boost | ≥1.48（推荐 1.59） | `apt install libboost-dev` |
| Python 3 | 仅回归测试需要 | 系统自带 |

**可选依赖**:

| 依赖 | 用途 | 安装 |
|---|---|---|
| boost-context | 替代自研上下文切换（非 amd64 平台需要） | `apt install libboost-context-dev` |
| boost-stacktrace | 更好的错误栈追踪 | `apt install libboost-stacktrace-dev` |
| pybind11 + python3-dev | Python 绑定 | `apt install pybind11-dev python3-dev` |
| Eigen3 | 一些高级特性 | `apt install libeigen3-dev` |
| nlohmann-json3 | DAG wfcommons 加载器 | `apt install nlohmann-json3-dev` |

**macOS 上**:

```bash
brew install boost eigen
```

### 获取源码

**稳定版**（推荐）:

```bash
tar xf simgrid-4-XX.tar.gz
cd simgrid-*
cmake -DCMAKE_INSTALL_PREFIX=/opt/simgrid -GNinja .
ninja
sudo ninja install
```

**最新开发版**:

```bash
git clone https://framagit.org/simgrid/simgrid.git
cd simgrid
cmake -DCMAKE_INSTALL_PREFIX=/opt/simgrid -GNinja .
ninja
ninja install
```

### 编译配置选项

#### 通用 CMake 选项

```bash
# 指定编译器
export CC=gcc-5.1
export CXX=g++-5.1

# 或通过 -D 传递
cmake -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ .
```

#### SimGrid 专用选项

| 选项 | 默认值 | 说明 |
|---|---|---|
| `CMAKE_INSTALL_PREFIX` | — | 安装路径（如 `/opt/simgrid`） |
| `enable_compile_optimizations` | ON | 编译优化，加速模拟器 |
| `enable_debug` | ON | 启用 debug 级别日志，关闭可略微加速 |
| `enable_smpi` | ON | MPI 模拟支持 |
| `enable_model-checking` | ON | 模型检验支持 |
| `enable_ns3` | OFF | ns-3 网络模型绑定 |
| `enable_python` | 自动检测 | Python 绑定 |
| `enable_java` | 自动检测 | Java 绑定 |
| `enable_documentation` | OFF | 生成文档（建议用在线版） |
| `minimal-bindings` | OFF | 最小化 Python/Java 绑定依赖 |

> **注意**: 改变了系统依赖后，需要删除 `CMakeCache.txt` 重新配置，或者做**树外编译**（推荐）。

### 树外编译（推荐）

将编译产物放在独立目录，清理只需删除该目录：

```bash
mkdir build && cd build
cmake [options] ..
make
```

### 构建目标

```bash
make              # 构建核心库（不含示例）
make examples     # 构建示例
make simgrid      # 仅构建库
make tests        # 构建测试
make install      # 安装
ctest             # 运行所有测试
ctest -R s4u      # 只运行名称匹配 "s4u" 的测试
ctest -j4         # 并行运行测试
ctest --output-on-failure  # 失败时显示详情
```

---

## 平台特定说明

### macOS

SimGrid 在 macOS 上用 clang 编译顺利：

```bash
cmake -DCMAKE_C_COMPILER=/path/to/clang -DCMAKE_CXX_COMPILER=/path/to/clang++ .
make
```

**本团队 macOS arm64 注意事项**:
- Python binding (pybind11) 存在 `property/call_guard` 编译兼容问题，**当前不可用**
- 替代方案: 使用 C++ S4U 接口，或独立 Python 仿真脚本
- `/usr/include` 可能不存在，需要 `xcode-select --install`

### Windows

推荐使用 **WSL (Windows Subsystem for Linux)** 安装 Ubuntu。原生 Windows 编译从 v3.33 起已禁用。

### Python 绑定

```bash
# 从源码编译
cd simgrid-source-tree
python setup.py build install

# 或用 pip（v3.13+）
pip install simgrid
```

如果安装到非标准路径：

```bash
PYTHONPATH="/opt/simgrid/lib/python3/dist-packages" \
LD_LIBRARY_PATH="/opt/simgrid/lib" \
python your_script.py
```

---

## 本团队环境

本团队已在 macOS arm64 上完成 SimGrid 4.1 源码编译安装，详见总目录的本地环境部分。
