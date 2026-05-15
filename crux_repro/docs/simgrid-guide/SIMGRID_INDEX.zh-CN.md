# SimGrid 官方文档中文本地化 — 总目录

> 翻译基准: SimGrid 4.1 (https://simgrid.org/doc/latest/)
> 翻译日期: 2026-05-14
> 本地环境: macOS arm64, SimGrid 已编译安装到 `.simgrid_install`

---

## 🌐 网页版（推荐部署到服务器）

> **[simgrid-manual-zh.html](./simgrid-manual-zh.html)** — 单文件网页，左侧导航 + 全部内容，可直接用浏览器打开或部署到 Nginx/Apache。

---

## 文档索引

| 序号 | 文档 | 原文 | 状态 |
|---:|---|---|:---:|
| 1 | [SimGrid 介绍](./SIMGRID_INTRODUCTION.zh-CN.md) | Introduction | ✅ |
| 2 | [安装 SimGrid](./SIMGRID_INSTALL.zh-CN.md) | Installing SimGrid | ✅ |
| 3 | [创建自己的项目](./SIMGRID_START_PROJECT.zh-CN.md) | Start your own project | ✅ |
| 4 | [描述模拟平台](./SIMGRID_PLATFORM.zh-CN.md) | Describing your simulated platform | ✅ |
| 5 | [S4U 接口指南](./SIMGRID_S4U.zh-CN.md) | The S4U Interface | ✅ |
| 6 | [性能模型](./SIMGRID_MODELS.zh-CN.md) | The SimGrid models | ✅ |
| 7 | [配置 SimGrid](./SIMGRID_CONFIG.zh-CN.md) | Configuring SimGrid | ✅ |
| 8 | [部署应用](./SIMGRID_DEPLOY.zh-CN.md) | Deploying your application | ✅ |
| 9 | [模拟输出](./SIMGRID_OUTCOMES.zh-CN.md) | Simulation outcomes | ✅ |
| — | [本地方案备忘](../SIMGRID_COLLECTIVE_SIMULATION_PLAN.zh-CN.md) | 内部文档 | 🔗 |

---

## 快速导航

- **新手入门**: 按 1 → 2 → 3 顺序阅读
- **写模拟实验**: 先看 4（平台）+ 5（S4U）+ 8（部署）
- **调优性能**: 看 6（模型）+ 7（配置）
- **分析结果**: 看 9（输出）
- **本团队多机多卡 Collective 模拟**: 看本地方案

---

## 本地环境快速参考

```
SimGrid 安装: /Users/dkwyl/Documents/tmbProject/net/.simgrid_install
依赖环境:    /Users/dkwyl/Documents/tmbProject/net/.simgrid_env
C++ 模拟入口: crux_repro/simgrid_real/collective_sim.cpp
Python 模拟:  crux_repro/crux_sim.py
构建:         crux_repro/simgrid_real/build.sh
运行:         crux_repro/simgrid_real/run_all.sh
```

### 构建

```bash
cd /Users/dkwyl/Documents/tmbProject/net
MAMBA_ROOT_PREFIX=/Users/dkwyl/Documents/tmbProject/net/.mamba \
  /Users/dkwyl/Documents/tmbProject/net/.tools/micromamba/bin/micromamba run \
  -p /Users/dkwyl/Documents/tmbProject/net/.simgrid_env \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/build.sh
```

### 运行

```bash
cd /Users/dkwyl/Documents/tmbProject/net
DYLD_LIBRARY_PATH=.../lib:.../lib \
  /Users/dkwyl/Documents/tmbProject/net/crux_repro/simgrid_real/run_all.sh
```
