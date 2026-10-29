# NES、SNES、PSP Core 正式来源核对（2026-10-30）

本文只记录官方 Release、固定源码和构建入口研究，不更改发布代码，不下载游戏 ROM，不发布 Cart。查询使用 GitHub 官方 API、Release 页面及固定 tag 的源码；临时工作目录为 `/tmp/continue-core-research.O5MKLD`。构建命令中的源目录均指临时独立 checkout。

## 建议固定的来源

| 平台 | 仓库 / 正式 Release | 固定 commit SHA | ABI 名称 / 预期版本 | 建议 |
| --- | --- | --- | --- | --- |
| NES | [SourMesen/Mesen 0.9.9](https://github.com/SourMesen/Mesen/releases/tag/0.9.9) | `f3a18bed018fa853627e0e15d02a3f2ba4960222` | `Mesen` / `0.9.9` | 正式源码包含 Libretro；上游已归档且明确不再支持此版本，须记录维护风险 |
| SNES | [bsnes-emu/bsnes v115](https://github.com/bsnes-emu/bsnes/releases/tag/v115) | `8e80d2f8a43e34a82931e25143b279e5fbcfaedc` | `bsnes` / `115` | GPLv3-only；避免 Snes9x 非商业限制 |
| PSP | [hrydgard/ppsspp v1.20.4](https://github.com/hrydgard/ppsspp/releases/tag/v1.20.4) | `fa50bb1976065c4f8b1b47af227d367fe9771555` | `PPSSPP` / 正常保留 tag 时 `v1.20.4` | 正式源码含 CMake 与 Make 入口，必须递归固定子模块并携带 assets |

查询时三者均为 `draft=false`、`prerelease=false`，发布时间依次为 2020-02-01、2020-03-20、2026-05-16。可复核 [Mesen API](https://api.github.com/repos/SourMesen/Mesen/releases/latest)、[bsnes API](https://api.github.com/repos/bsnes-emu/bsnes/releases/latest)、[PPSSPP API](https://api.github.com/repos/hrydgard/ppsspp/releases/latest)。最新状态具有时效性，登记后应按完整 SHA 构建。

PPSSPP 的 `v1.20.4` 是 annotated tag，tag 对象为 `3a31057b7e44270b4d5cef8c31b6559d51802a3b`；实际代码 commit 是表中的 `fa50…`，不可混用。固定 checkout 仍应保留原始 tag ref，供上游版本生成器读取。

## NES：Mesen 0.9.9

正式源码的入口是 [Libretro/Makefile](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/Libretro/Makefile)、[Makefile.common](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/Libretro/Makefile.common) 和 [Libretro.vcxproj](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/Libretro/Libretro.vcxproj)。无需 Mono/.NET GUI、SDL 或系统游戏数据库来构建 Libretro target。发布前仍须检查实际动态依赖。

### 三目标命令

```sh
# macos-arm64：默认 ARCHFLAGS 是 i386+x86_64，必须覆盖。
mise exec -- make -C Libretro -j4 \
  platform=osx ARCHFLAGS='-arch arm64' CC=clang CXX=clang++
# 输出：Libretro/mesen_libretro.dylib

# linux-x86_64：在原生 x86_64 Linux runner。
mise exec -- make -C Libretro -j4 platform=unix CC=gcc CXX=g++
# 输出：Libretro/mesen_libretro.so
```

Windows 建议直接使用源码现成的 `Libretro|x64` MSBuild 配置。该配置已经选择 `RuntimeLibrary=MultiThreaded`（/MT），`TargetName=mesen_libretro`；项目默认工具集 v142，可用 VS2022 的 v143 覆盖。传入绝对 `OutDir` / `IntDir` 可消除 `SolutionDir` 隐式值的不确定性：

```powershell
msbuild Libretro/Libretro.vcxproj /m /t:Build `
  /p:Configuration=Libretro /p:Platform=x64 /p:PlatformToolset=v143 `
  /p:OutDir=C:\build\mesen-out\ /p:IntDir=C:\build\mesen-obj\
# 输出：C:\build\mesen-out\mesen_libretro.dll
```

Make 的 `ARCHFLAGS` 同时传入编译和链接，ARM64 路径不需要改源码。固定源码中 [CRC32.cpp](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/Utilities/CRC32.cpp) 已考虑 `__aarch64__` 字节序，不能仅凭发布于 Apple Silicon 之前便判定不支持。

本次在 Apple Silicon 本机按上述命令实际完成编译，`file` 回读为 `Mach-O 64-bit dynamically linked shared library arm64`；`otool -L` 仅列系统 `libSystem.B.dylib`、`libc++.1.dylib`。此证据只确认编译、文件架构和动态依赖清单。随后 ctypes 加载停在本机 dyld 文件验证 `fcntl`，未获得 ABI 回读；不应将此轮编译称为 Core 运行、游戏、音频或渲染验收。

### 版本、资源和许可证

[retro_get_system_info](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/Libretro/libretro.cpp) 使用 `EmulationSettings::GetMesenVersionString()`；[EmulationSettings.cpp](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/Core/EmulationSettings.cpp) 的三段版本为 0、9、9，因此预期字符串恰为 `0.9.9`。

普通 NES 卡带无需额外 BIOS。FDS 路径在上述 `libretro.cpp` 中读取用户 system 目录的 `disksys.rom`；这是特定内容的外部固件需求，不能随 Cart 下载或混入包。游戏数据库来自 `Libretro/MesenDB.inc`，编译进入代码；不要将桌面 GUI 目录视为必需资源。

[LICENSE](https://github.com/SourMesen/Mesen/blob/f3a18bed018fa853627e0e15d02a3f2ba4960222/LICENSE) 为 GPLv3，打包需保留许可和相应源码取得方式，并汇总所编入第三方代码的 notices。[官方 Release 页面](https://github.com/SourMesen/Mesen/releases/tag/0.9.9) 明确标注该版本已不再受支持；这是正式 Release 约束下的可用历史来源，不能描述为当前活跃维护分支。

### 为什么不选 Nestopia / FCEUX / Mesen2

| 候选 | 官方核对结果 |
| --- | --- |
| `libretro/nestopia` | [Releases API](https://api.github.com/repos/libretro/nestopia/releases) 与 [Tags API](https://api.github.com/repos/libretro/nestopia/tags) 查询均为空数组。虽有 Libretro 构建入口，但不能满足仅正式 Release 的规则 |
| `0ldsk00l/nestopia` | 最新 [2.0.0](https://github.com/0ldsk00l/nestopia/releases/tag/2.0.0)，commit `7b5c87d8dc3c817211545449683d1fcd897324ca`。[README](https://github.com/0ldsk00l/nestopia/blob/7b5c87d8dc3c817211545449683d1fcd897324ca/README.md) 指向 Jolly Good 的另一套接口，当前只保留 legacy Win32；检查 1.52.1、1.53.2、2.0.0 的完整 tree 都没有 Libretro 构建入口 |
| `TASEmulators/fceux` | [正式 fceux-2.7.0](https://github.com/TASEmulators/fceux/releases/tag/fceux-2.7.0) 的 [完整 tree](https://api.github.com/repos/TASEmulators/fceux/git/trees/fceux-2.7.0?recursive=1) 中 `src/drivers/libretro` 仅有预编译 `fceux_libretro.so`，不能据此从该 Release 源码重建三个目标 |
| `SourMesen/Mesen2` | [2.1.1](https://github.com/SourMesen/Mesen2/releases/tag/2.1.1) 正式源码 tree 无 Libretro 入口，不能以 Mesen2 的版本标记 Mesen1 Core |

## SNES：bsnes v115

正式源码已有 [bsnes/target-libretro/GNUmakefile](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/bsnes/target-libretro/GNUmakefile)，由 [bsnes/GNUmakefile](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/bsnes/GNUmakefile) 的 `target=libretro` 选择。它不是 CMake 项目；Windows 也不应凭空套用 MSBuild。

```sh
# macos-arm64：本次已在独立 checkout 编译成功。
mise exec -- make -C bsnes -j4 target=libretro binary=library \
  local=false platform=macos compiler='clang++ -arch arm64'
# 输出：bsnes/out/bsnes_libretro.dylib

# linux-x86_64：原生 Linux x86_64 runner。
mise exec -- make -C bsnes -j4 target=libretro binary=library \
  local=false platform=linux compiler=g++
# 输出：bsnes/out/bsnes_libretro.so

# windows-x86_64：MSYS2 的 x86_64 MinGW GCC / GNU make。
mise exec -- make -C bsnes -j4 target=libretro binary=library \
  local=false platform=windows compiler=g++
# 输出：bsnes/out/bsnes_libretro.dll
```

`binary=library` 防止应用 target 的链接设置进入 Core；`local=false` 避免根 Makefile 注入 `-march=native`，从而避免将 CI CPU 指令集当成用户机器最低要求。必须使用相互隔离的 source/build 目录，因为对象文件直接写入源码内 `obj/`，跨架构重用会混入旧对象。

[nall/GNUmakefile](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/nall/GNUmakefile) 在 Linux/Windows 启用 OpenMP；target 链接中还有显式 `-lgomp`。Windows GCC 路径同时带 `-static -static-libgcc -static-libstdc++`，最终是否完全静态包含 OpenMP/pthread 仍以 PE 导入表为准。Linux 应检查 `libgomp.so.1`、`libstdc++.so.6`、glibc 最低版本，不能因只有一个 `.so` 就宣称无运行依赖。macOS 的 nall 规则跳过 OpenMP，链接系统 libc++ / objc，无需 Homebrew libomp。

ARM64 的协程实现位于 [libco/aarch64.c](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/libco/aarch64.c)，[libco.c](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/libco/libco.c) 根据 `__aarch64__` 自动选择。其 Clang 路径调用 `mprotect` 将静态机器码设为可执行，macOS hardened runtime / 最终宿主权限仍需真实调用链验收。此次编译产物 `file` 确认为 arm64，`otool -L` 仅列系统 libc++ / objc / libSystem；ABI 加载验证未完成，原因同前。

[emulator.hpp](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/bsnes/emulator/emulator.hpp) 将 `Emulator::Version` 固定为 `115`，[libretro.cpp](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/bsnes/target-libretro/libretro.cpp) 原样用于 `library_version`。因此 Cart 的来源 tag 为 `v115`，ABI 预期为 `115`，两者应分别登记。

普通 SNES 内容没有类似 PPSSPP 的完整 assets 目录需求；[program.cpp](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/bsnes/target-libretro/program.cpp) 与 [resources.hpp](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/bsnes/target-libretro/resources.hpp) 内嵌 boards / IPL 资源。Super Game Boy 的额外 BIOS 与 MSU-1 的 `.msu`、音轨属于特定内容需求，不应打包用户游戏或第三方固件；本次不扩大到这些子功能。

[LICENSE.txt](https://github.com/bsnes-emu/bsnes/blob/8e80d2f8a43e34a82931e25143b279e5fbcfaedc/LICENSE.txt) 明确为 GPL 第 3 版且仅该版本。需连同实际编入的 SameBoy / libco 等 notices 一起保留。

### Snes9x 排除依据

[snes9xgit/snes9x 1.63](https://github.com/snes9xgit/snes9x/releases/tag/1.63) 是正式 Release，完整 commit `921f9f7b83660eb44ad263022a57a4a029057c37`，含 `libretro/Makefile`、`libretro/libretro-win32.vcxproj` 的 x64 配置，没有 Libretro CMake 入口；技术上可构建。

但 [固定 LICENSE](https://github.com/snes9xgit/snes9x/blob/921f9f7b83660eb44ad263022a57a4a029057c37/LICENSE) 明确仅授予非商业用途，并把商业产品推广列入需先取得许可的情形，因此本轮不作为 Continue 默认分发来源。其 [ABI 版本实现](https://github.com/snes9xgit/snes9x/blob/921f9f7b83660eb44ad263022a57a4a029057c37/libretro/libretro.cpp) 为 `VERSION GIT_VERSION`，默认 Make 会追加空格和 short SHA，亦非恰好 `1.63`。

## PSP：PPSSPP v1.20.4

### Checkout 与固定子模块

```sh
git clone --no-checkout https://github.com/hrydgard/ppsspp.git ppsspp
git -C ppsspp fetch --depth=1 origin tag v1.20.4
git -C ppsspp checkout --detach fa50bb1976065c4f8b1b47af227d367fe9771555
git -C ppsspp submodule update --init --recursive
git -C ppsspp rev-parse HEAD
git -C ppsspp submodule status --recursive
git -C ppsspp describe --always
```

不要使用 `submodule update --remote`；`.gitmodules` 中即使声明 `branch=bundled` / `branch=ppsspp`，普通 update 仍使用主仓库记录的 gitlink SHA。[固定 tree](https://api.github.com/repos/hrydgard/ppsspp/git/trees/fa50bb1976065c4f8b1b47af227d367fe9771555?recursive=1) 与 [.gitmodules](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/.gitmodules) 是权威来源。所有递归子模块都应写入构建 provenance；不能只记录顶层 SHA。

顶层直接 gitlink 如下（嵌套子模块仍以递归 readback 补全）：

| 路径 | 固定 SHA |
| --- | --- |
| `libretro/libretro-common` | `76a3d54feb0ee0ce9d59b90aa24694f3782063d3` |
| `ffmpeg` | `1e3b4965632f60b1d85360261d1b9dd45444bc71` |
| `ext/armips` | `a8d71f0f279eb0d30ecf6af51473b66ae0cf8e8d` |
| `ext/glslang` | `50e0708ec3a5c16020c4f845c654b80b8edb80bd` |
| `ext/SPIRV-Cross` | `4212eef67ed0ca048cb726a6767185504e7695e5` |
| `ext/cpu_features` | `fd4ffc1632db7b4e763bd28ffa6fc9d761cf3587` |
| `ext/rapidjson` | `73063f5002612c6bf64fe24f851cd5cc0d83eef9` |
| `ext/miniupnp` | `27d13ca9beeb5541f5fbf11959dced03dac39972` |
| `ext/zstd` | `f8745da6ff1ad1e7bab384bd1f9d742439278e99` |
| `ext/rcheevos` | `ebfe8ca1bf944358e27200d66964fcb4e00e2487` |
| `ext/naett` | `5f695cfa9fcbf30668a4d3ac4b4abf1cd89a1302` |
| `ext/libchdr` | `8bba7745d758627258b315997a860039244cedaf` |
| `ext/lua` | `7648485f14e8e5ee45e8e39b1eb4d3206dbd405a` |
| `ext/freetype` | `063ed27f481f0bcd3962fd468e1546739d7d285a` |
| `ext/nanosvg` | `478dbb8f7ed11c3d9b20b3986a8ee2283f483ef7` |
| `ext/aemu_postoffice` | `530fee545c27ffb8524a8f496cbbcfdb687fe8c5` |
| `ext/OpenXR-SDK` | `be392bf6949adeeabad5082aa79d12aacbda781f` |
| `ext/libadrenotools` | `8fae8ce254dfc1344527e05301e43f37dea2df80` |
| `ext/discord-rpc` | `963aa9f3e5ce81a4682c6ca3d136cddda614db33` |
| `SDL/macOS` | `c387d93ab5910b5a6be78b4840a5bbbc452f3ac8` |
| `assets/debugger` | `9776332f720c854ef26f325a0cf9e32c02115a9c` |
| `ios/MoltenVK` | `0bf904d2d1d159eb95bdefcd8432eee79ee1da14` |
| `pspautotests` | `4374348477b425f48f99c8fd58a853c439f78acd` |

### CMake 入口与两 Unix 目标

[根 CMakeLists.txt](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/CMakeLists.txt) 接受 `LIBRETRO=ON`，并在 [libretro/CMakeLists.txt](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/libretro/CMakeLists.txt) 定义 `ppsspp_libretro` SHARED target，去掉默认 `lib` 前缀。

以下是按源码推导的待 CI 验证命令；本次没有递归下载 PPSSPP 的全部依赖并完成编译，不应当作成功构建记录：

```sh
# macos-arm64：保留 bundled FFmpeg；USE_SYSTEM_LIBSDL2=ON 使 Core 配置
# 不强制要求 standalone 所用的 SDL2.framework（此 find_package 非 REQUIRED）。
mise exec -- cmake -S . -B build/macos-arm64 -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DLIBRETRO=ON -DHEADLESS=OFF -DUNITTEST=OFF -DATLAS_TOOL=OFF \
  -DUSING_QT_UI=OFF -DUSE_DISCORD=OFF -DUSE_SYSTEM_LIBSDL2=ON \
  -DUSE_SYSTEM_FFMPEG=OFF -DUSE_SYSTEM_LIBPNG=OFF \
  -DUSE_SYSTEM_ZSTD=OFF -DUSE_SYSTEM_LIBCHDR=OFF
mise exec -- cmake --build build/macos-arm64 --target ppsspp_libretro --parallel 4
# 输出：build/macos-arm64/ppsspp_libretro.dylib

# linux-x86_64：原生 runner，带 OpenGL 开发包；禁用宿主窗口 WSI 的发现。
mise exec -- cmake -S . -B build/linux-x86_64 -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON \
  -DHEADLESS=OFF -DUNITTEST=OFF -DATLAS_TOOL=OFF -DUSING_QT_UI=OFF \
  -DUSE_DISCORD=OFF -DUSING_X11_VULKAN=OFF -DUSE_WAYLAND_WSI=OFF \
  -DUSE_SYSTEM_FFMPEG=OFF -DUSE_SYSTEM_LIBPNG=OFF \
  -DUSE_SYSTEM_ZSTD=OFF -DUSE_SYSTEM_LIBCHDR=OFF
mise exec -- cmake --build build/linux-x86_64 --target ppsspp_libretro --parallel 4
# 输出：build/linux-x86_64/ppsspp_libretro.so
```

源码要求 C++17、CMake ≥3.16、C/C++/ASM 工具链、Git、完整子模块；可用 Ninja。`USE_FFMPEG` 默认 ON，内置 FFmpeg 的平台路径分别为 `ffmpeg/macosx/universal`、`ffmpeg/linux/x86_64`。`OpenGL` 是 REQUIRED；Linux 通常需 Mesa/OpenGL 开发包，线程与 dl 等仍是系统依赖。根 CMake 在 macOS Libretro ARM64 分支自行设置 deployment target 为 10.14，这个值早于 Apple Silicon 首版；应检查最终 Mach-O `LC_BUILD_VERSION`，不能据配置数字承诺 ARM64 支持到 10.14。

FFmpeg 子模块含平台预编译静态库。若要求每个依赖也必须从源码重建，需要另行按该固定子模块内平台 build 脚本构建；直接使用它们必须在 provenance 中明确记为上游随源码提供的静态库，不能宣称全部依赖均由本轮 CI 重新编译。[FindFFmpeg.cmake](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/cmake/Modules/FindFFmpeg.cmake) 也指出静态 FFmpeg 的额外依赖由调用者负责。最终以 `otool -L` / `readelf -d` 检查实际依赖，不可把 runner 上能找到的 Homebrew `.dylib` 或 Ubuntu `.so` 隐式带入用户环境。

### Windows：优先官方 Make + MSVC 路径

[libretro/README_WINDOWS.txt](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/libretro/README_WINDOWS.txt) 的官方路径是 MSYS GNU make 加 `windows_msvc2019_desktop_x64`，并明确说明此名字在 VS2022 也适用。它会调用 `VSWhere.sh` 和注册表发现 VS / Windows SDK，必须保留 MSYS 的 `bash`、`cygpath`、GNU make 以及 Windows `cmd`、`reg`。

```sh
# MSYS shell；使用 VS 的 cl/link，不用 MinGW g++。
mise exec -- make -C libretro -j4 \
  platform=windows_msvc2019_desktop_x64 DEBUG=0 \
  CPUOPTS='-O2 -DNDEBUG -MT'
# 输出：libretro/ppsspp_libretro.dll
```

`CPUOPTS` 是 [Makefile](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/libretro/Makefile) 最终加入 C/C++ flags 的变量。显式覆盖为 `-O2 -DNDEBUG -MT` 可固定 Release 和静态 CRT，并保留 Makefile 的其余平台、include、定义及链接设置。不要直接覆盖 `CXXFLAGS` 丢失全部上游默认值。

固定 [FFmpeg tree](https://api.github.com/repos/hrydgard/ppsspp-ffmpeg/git/trees/1e3b4965632f60b1d85360261d1b9dd45444bc71?recursive=1) 已有 `Windows/x86_64/lib/{avcodec,avformat,avutil,swresample,swscale}.lib` 和 headers；[windows_x64-build.sh](https://github.com/hrydgard/ppsspp-ffmpeg/blob/1e3b4965632f60b1d85360261d1b9dd45444bc71/windows_x64-build.sh) 明确选择 MSVC、`--enable-static --disable-shared` 及 `--extra-cflags="-MT ..."`，与此配置一致。使用这些现成库时仍应检查 PE 导入表，不能仅以脚本文字宣称所有 CRT 依赖均已移除。

不建议未经验证直接采用 CMake + `CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`：该固定版根 CMake MSVC 分支无条件加入 `/NODEFAULTLIB:"libcmt.lib"`，会与静态 CRT 意图冲突。官方 Make 路径没有这项 CMake 设置，能避免为首版新增上游 patch。默认 MinGW 路径在官方 README 已提示 D3D11 链接问题，也不是首选。

### assets 的布局、必需范围与失败含义

[Libretro 官方安装文档](https://docs.libretro.com/library/ppsspp/#setup-required) 要求把 assets 文件部署到 frontend 的 system 目录下 `PPSSPP/`。固定版 [libretro.cpp](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/libretro/libretro.cpp) 在 `retro_init` 获取 `RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY`，追加 `PPSSPP` 并将该目录注册到 VFS；`flash0Directory` 指向 `PPSSPP/flash0`。

正确布局：

```text
<system>/PPSSPP/compat.ini
<system>/PPSSPP/flash0/font/*.pgf
<system>/PPSSPP/ppge_atlas.zim
<system>/PPSSPP/ppge_atlas.meta
<system>/PPSSPP/lang/...
<system>/PPSSPP/shaders/...
```

应从**同一固定源码**的整个 `assets/` 目录打包为可验证的资源树，并保留路径、SHA-256 与 notices；资源展开后直接位于 `PPSSPP/`，不是 `PPSSPP/assets/`。完整复制策略比未经测试裁剪资源更稳，`assets/debugger` 若保留也必须初始化其固定子模块。

具体缺失影响应准确表述：

- `compat.ini`：固定 `retro_init` 检测其缺失并发出 Core system files missing 警告；[Compatibility.cpp](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/Core/Compatibility.cpp) 读取游戏兼容补丁。缺失不意味着所有游戏立即拒绝启动，而是缺少按游戏修复，不能交付为完整运行包。
- `flash0/font/`：提供 HLE 字体；[sceFont.cpp](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/Core/HLE/sceFont.cpp) 从 flash0 路径读取字体。缺失会破坏依赖系统字体的内容，应作为资源完整性门禁。
- `ppge_atlas.zim` / `.meta`：[PPGeDraw.cpp](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/Core/Util/PPGeDraw.cpp) 加载失败时不会绘制 PPGe 部分；存档等 PSP 系统对话框因此不完整。
- `lang/`、`shaders/`、font atlas、兼容设置和其他 assets：完整包一起保留，避免未来启用的对话框、着色器或系统功能只有库文件而无资源。

PPSSPP 是 HLE 模拟器，Libretro 官方文档说明无需 PSP BIOS。资源来自该官方源码树，不应下载 Sony 固件或游戏 ROM 来补齐。

### ABI 版本和许可

`retro_get_system_info.library_version` 直接使用 `PPSSPP_GIT_VERSION`。[git-version.cmake](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/git-version.cmake) 和 [Makefile.common](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/libretro/Makefile.common) 均调用 `git describe --always`。本次固定 tag checkout 实测该命令输出 `v1.20.4`；若丢失 `.git`、tag ref、已有 `PPSSPP_GIT_VERSION_NO_UPDATE=1` 或从别的 commit 构建，就可能得到 `unknown` / short SHA / 其他字符串。因此来源版本、Cart 版本、ABI 版本分别登记，并将预期 `v1.20.4` 做实际产物回读。

[README](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/README.md) 表明 GPL 2.0 及后续版本，[LICENSE.TXT](https://github.com/hrydgard/ppsspp/blob/fa50bb1976065c4f8b1b47af227d367fe9771555/LICENSE.TXT) 还含 PSPSDK BSD notice。FFmpeg、fonts、glslang、SPIRV-Cross、zstd、libretro-common 等各有许可，不能用一个 PPSSPP `LICENSE.TXT` 代替所有实际编入代码和资源的 notices。发布材料应保留完整对应源码与构建配方；具体产品许可组合仍以实际链接和分发方式审查。

## 此轮证据边界

- 已完成：官方正式 Release 与完整 commit 固定；主要入口源码读取；PPSSPP 直接 gitlink 清单；Mesen、bsnes 在独立源码目录的 macOS ARM64 实际编译与文件架构回读。
- 未完成：Windows / Linux 三目标 CI 成功证据；PPSSPP 完整编译；最终 Cart 资源展开路径的宿主集成；动态依赖门禁；ABI 原生冒烟；游戏、渲染、音频、存档与性能验收。
- Mesen / bsnes 临时 ctypes 加载遭遇本机 dyld 文件验证阻塞，未将它误记为 ABI 通过。不要把正式 tag、源码构建成功或已有共享库当成这些运行验收的替代证据。
