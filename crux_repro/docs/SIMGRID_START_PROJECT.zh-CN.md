# 创建自己的 SimGrid 项目

> 原文: https://simgrid.org/doc/latest/Start_your_own_project.html

**不建议直接修改 SimGrid 源码**，这会导致升级困难。应该在自己的目录中创建项目。

---

## 方法一：克隆 S4U 模板项目（推荐）

最简单的 S4U 项目起步方式：克隆[模板项目](https://framagit.org/simgrid/simgrid-template-s4u)，内含 CMake 配置。

克隆后记得**移除 fork 关系**（除非你要向模板项目贡献代码）。

---

## 方法二：CMake 构建

### C++ S4U 项目的 CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.12)
project(MyFirstSimulator)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -funroll-loops -fno-strict-aliasing -flto=auto")

# 需要 FindSimGrid.cmake（从 SimGrid 源码树根目录复制到 cmake/Modules/）
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake/Modules/")
find_package(SimGrid REQUIRED)
include_directories(${SimGrid_INCLUDE_DIR})

# 第一个模拟器
set(SIMULATOR_SOURCES main.c other.c util.c)
add_executable(my_simulator ${SIMULATOR_SOURCES})
target_link_libraries(my_simulator ${SimGrid_LIBRARY})

# 第二个模拟器
set(OTHER_SOURCES blah.c bar.c foo.h)
add_executable(other_xp ${OTHER_SOURCES})
target_link_libraries(other_xp ${SimGrid_LIBRARY})
```

**关于 `FindSimGrid.cmake`**:
- 位于 SimGrid 源码树根目录
- 可复制到项目的 `cmake/Modules/` 目录
- 或使用系统安装版本
- 复制的好处：在没有 SimGrid 的机器上编译时能给出清晰的错误信息

### MPI 项目的 CMakeLists.txt

```cmake
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}")
find_package(SimGrid)

add_executable(roundtrip roundtrip.c)
smpi_c_target(roundtrip)   # 声明此目标在 smpirun 中运行

enable_testing()
add_test(NAME RoundTrip
  COMMAND ${SMPIRUN} -platform ${CMAKE_SOURCE_DIR}/../cluster_backbone.xml
          -np 2 ./roundtrip)
```

### Fortran 代码的 CMake

```bash
SMPI_PRETEND_CC=1 cmake \
  -DMPI_C_COMPILER=/opt/simgrid/bin/smpicc \
  -DMPI_CXX_COMPILER=/opt/simgrid/bin/smpicxx \
  -DMPI_Fortran_COMPILER=/opt/simgrid/bin/smpiff .
make
```

---

## 方法三：Makefile 构建

适用于简单的 C 项目（三个文件 `util.h`, `util.c`, `mysimulator.c`）：

```makefile
# 默认目标
all: mysimulator

# 二进制依赖
mysimulator: mysimulator.o util.o

# 源文件依赖
mysimulator.o: mysimulator.c util.h
util.o: util.c util.h

# 配置
SIMGRID_INSTALL_PATH = /opt/simgrid
CC = gcc
CFLAGS = -g -O2 -Wall

# 隐式规则（缩进必须是 Tab）
%: %.o
	$(CC) -L$(SIMGRID_INSTALL_PATH)/lib/ $(CFLAGS) $^ -lsimgrid -o $@

%.o: %.c
	$(CC) -I$(SIMGRID_INSTALL_PATH)/include $(CFLAGS) -c -o $@ $<

clean:
	rm -f *.o *~

.PHONY: clean
```

---

## 在 Eclipse 中开发 C++

1. 用 cmake 生成构建文件
2. 在 Eclipse 中作为 Makefile 项目导入
3. 在 CDT GCC Built-in Compiler Settings 中添加 `-std=c++17`

---

## 常见问题排查

### Library not found

```
./masterworker1: error while loading shared libraries: libsimgrid.so:
cannot open shared object file: No such file or directory
```

**解决**: 把 SimGrid 库路径加入 `LD_LIBRARY_PATH`，可写入 `~/.bashrc`:

```bash
export LD_LIBRARY_PATH=/opt/simgrid/lib
```

> macOS 上对应的是 `DYLD_LIBRARY_PATH`

### Many undefined references

```
masterworker.c:209: undefined reference to `sg_version_check'
(and many other undefined references)
```

**原因**: 链接器使用了错误的库。同样用 `LD_LIBRARY_PATH` 指定正确路径。

### Only a few undefined references

**可能原因**: 系统上某处有旧版 SimGrid 库。

```bash
# Linux: 查看链接了哪个库
ldd name-of-yoursimulator

# macOS:
otool -L name-of-yoursimulator
```

找到旧版后删除，重新编译运行。
