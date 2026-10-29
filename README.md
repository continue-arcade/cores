# Continue Core 生产仓库

从 mGBA 官方**正式 Release 的完整源码 SHA**构建 Continue Arcade 使用的 libretro Core Cart。
本仓库独立运行，Python 只使用标准库，不读取 Continue 产品私有仓库。

首次试运行：Core **0.10.5**，SHA `26b7884bc25a5933960f3cdcd98bac1ae14d42e2`；
Cart **0.1.0-smoke.1**，GitHub tag `mgba/v0.1.0-smoke.1`，作为 prerelease 公开。
Cart ID 为 `org.continue.core.mgba`，资源 ID 为 `org.continue.resource.core.mgba`。
目标为 `macos/aarch64`、`windows/x86_64`、`linux/x86_64`。

## 固定入口

```sh
mise install
mise run test
mise run core-release -- check mgba
mise run core-release -- prepare mgba 0.10.5 --cart-version 0.1.0-smoke.1
mise run core-release -- build input-lock.json macos-aarch64 --output dist
# 三个原生平台分别构建后，将输出合并，再执行：
mise run core-release -- verify dist
mise run core-release -- publish dist
```

`prepare` 要求配方已提交；`build` 与 `publish` 都要求 tracked 工作区干净，checkout 与锁中的配方 commit 一致，
并逐项核对脚本、登记、mise 配置和工作流的实际 SHA-256 与提交内容。
每次使用新输出目录，已有包与工作目录不静默替换。
`check` 无新正式版时以 0 退出，输出 `update:false`；API、限流、网络或解析失败非零退出。
只读取 `mgba-emu/mgba` 的正式 Release，排除 draft、prerelease 和不匹配三段稳定版号的 tag。
与已公开 `release-report.json` 比较，所有已采用 tag 都审计是否移动；不依赖 Actions cache。
长时间未运行时只构建最新未采用正式版，不补发已过时的版本。
Cart 使用独立序列：首次 smoke 映射在 registry 明确登记；之后从全部已发布 Cart 的 SemVer 最大值推进。
最大值若为 prerelease，下一次采用同一基础版本的正式版；最大值若为正式版，则 patch 加一。
例如 smoke 0.1.0-smoke.1 → 0.1.0，人工维护发布 0.1.9 后的新 Core → 0.1.10；不会因上游版本较小而降级或撞号。
人工修正打包可显式 `prepare --cart-version` 使用新的 Cart 版本，不会由定时任务自动触发。

## 构建与证据

登记输入见 `registry/mgba.json`，启用 `BUILD_LIBRETRO=ON`，关闭 Qt/SDL 与外部可选依赖。
本配方针对未压缩 ROM，不承诺归档、PNG、调试器等被禁用的功能。
mGBA 源码包含其嵌入第三方实现，Release 的对应源码归档保留所有原始源文件、版权与许可。
每包含 mGBA MPL-2.0 `LICENSE`、对应源码获取说明 `SOURCE.md`、实际构建报告。
Release 同时附完整 `git archive` 源码，方便获取精确对应源码和第三方许可。
源码归档 SHA-256 与大小由每个原生构建写入其包内外报告，汇总时必须全部一致。
验收会实际读取 tar.gz，核对安全路径、文件类型、git archive 全局 commit 标识、version.cmake 的 Core 版本及必需源码/许可文件。
本仓自己的脚本采用 MIT，不改变 mGBA 和其第三方许可。

CMake/Python 版本由 mise 固定。Windows 使用 VS 2022 x64、静态 MSVC runtime；
Linux 使用 Ubuntu 24.04 gcc-13；macOS 使用 macos-15 arm64 与系统 SDK，部署目标 11.0。
GitHub 托管 runner 镜像与系统编译器可能更新，不承诺二进制逐字节可复现；
每个实际输出记录 runner 镜像、完整 CMake cache、编译器版本、SDK、动态依赖与二进制摘要。
禁用可选第三方系统库，依赖检查只允许系统库。构建环境变化本身不触发发布。

各原生 runner 检查架构，加载动态库，解析全部标准 libretro 入口并查询 API/库版本。
这属于原生 ABI 冒烟，**尚不证明实际 ROM、图像、音频、输入、性能或设备兼容**。
首轮 Linux/x86_64 的实测最高符号需求为 **GLIBC_2.38**，要求 **glibc >= 2.38**，不代表兼容所有 Linux 发行版。
Windows/x86_64 使用静态 CRT，dumpbin 实测仅依赖 **KERNEL32.dll**，无 VCRUNTIME/MSVCP 运行库依赖。
macOS/aarch64 实测仅依赖 **Foundation.framework** 和 **libSystem.B.dylib**；部署目标 11.0 不代替旧系统真实运行验证。

## Actions 与不可变发布

同一 workflow 由每日 schedule 或 workflow_dispatch 触发：check → prepare → 三目标 matrix → verify → publish。
上游其他仓库的 `release` 事件不会自动触发本仓库；这里不依赖跨仓 `on: release`。
工作流的第三方 Actions 均固定完整 commit；构建 job 仅 contents:read，发布 job 为 contents:write。
仓库首次设置必须启用 GitHub immutable releases，再启用正式发布：

```sh
gh api --method PUT repos/continue-arcade/cores/immutable-releases
gh api repos/continue-arcade/cores/immutable-releases
```

发布从 Draft 开始，全部包、逐包报告、全发布报告、对应源码和 SHA256SUMS 收齐后才公开。
已公开 Release 拒绝再次写入；Draft 恢复只接受 GitHub 返回摘要完全一致的已有资产，禁止 --clobber。
一个目标失败就不会执行发布 job；后补平台必须提升 Cart 版本。
GitHub immutable 功能锁定公开 tag 和资产，脚本还检查发布响应的 immutable 状态。
本地使用已登录 `gh` 的凭据通过 `GH_TOKEN` 环境变量传入；凭据不得写入配置、源码或日志。

## 首轮已发布

[试发布 Cart 0.1.0-smoke.1](https://github.com/continue-arcade/cores/releases/tag/mgba/v0.1.0-smoke.1) 已公开，prerelease=true、immutable=true，共 10 个资产。
[三平台成功工作流](https://github.com/continue-arcade/cores/actions/runs/40929193047)，构建配方 commit `7f119ec`。
发布后本地检测返回 `update:false`；完整实际构建差异与验证范围见 [验证记录](docs/verification-20261030.md)。
