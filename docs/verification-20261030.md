# 2026-10-30 发布流水线验证记录

## 已观察到的证据

- 首批 12 个行为测试在脚本不存在时全部以断言失败；实现后通过。
- macOS 自身 install name 误判作为真实构建发现的问题，新增两个回归测试先失败后修正；共 14 项通过。
- 再补全目标集合、来源归档和持久全发布报告的集成覆盖，共 15 项通过。
- 独立 review 的三个 P2（源码归档绑定/结构身份、准备后的配方变更、独立 Cart 版本序列）分别补失败测试，修正后共 18 项通过。
- 固定 Python 3.12.9、CMake 3.31.6 安装后，`mise run test` 通过且无资源泄漏警告。
- 本机 `macos-aarch64`，配方 commit `8303715e5de9faeb18661ff13779d232462db6fb`，正式源码 SHA `26b7884bc25a5933960f3cdcd98bac1ae14d42e2` 原生编译并打包成功。
- libretro 25 个标准入口可解析，API 1，library_name `mGBA`，library_version `0.10.5`，支持扩展 `gba|gb|gbc|sgb`。
- 实际动态依赖仅 Foundation.framework 和 libSystem.B.dylib；自身 install name 单独识别，不放宽外部依赖白名单。
- 本机包 436361 字节，SHA-256 `93fd94d3f2cd92c701ee203d2532ae1089559056d536d0ff7d3811e9b1084b4b`。
- 本机二进制 SHA-256 `18059e2edaccf4fc7e10504f26a2b5fd2bf70d29c0a1e61c4918c7f6b0f3775c`。
- 对应源码归档 14344744 字节；原始源文件不作修改。
- `continue-arcade/cores` 已公开创建，immutable-releases API 返回 `enabled:true`、`enforced_by_owner:false`。

## 实际差异与处理

本机初次准备输入时 GitHub 匿名 API 被限流，命令明确失败；没有伪装成无更新。
随后通过当前 `gh` 登录凭据注入子进程 GH_TOKEN 重试成功，未将凭据写入文件。
本机首次依赖检查误把 `otool -L` 的首项 LC_ID_DYLIB 当成外部依赖；改为先读取 `otool -D` 自身标识，外部库仍必须属于系统目录。

GitHub macOS runner 标签按当前官方文档使用 `macos-15`（arm64），脚本仍检查真实本机架构并显式设置 CMake arm64。
Windows 通过 Visual Studio Developer Shell 取得原生编译与 dumpbin 工具，仅将工具路径/SDK 字段写入 job 环境，不导出整个环境。

## 原生验证范围

独立 review 与三平台流水线现已完成，真实发布结果见文末。
本机成功只证明架构、动态依赖、ABI 入口和包结构；没有进行真实 ROM、图像、音频、输入、性能或设备验证。

## GitHub 三平台首轮差异

工作流 https://github.com/continue-arcade/cores/actions/runs/40928260405 的 macOS 与 Linux 构建通过；Windows 在 CMake configure 阶段失败，未创建公开 Release。
上游 0.10.5 CMakeLists.txt:746 对 Windows 普通 library 路径要求 epoxy，即使 BUILD_SHARED/STATIC 为 OFF 仍触发。
本仓只构建 mgba_libretro，因此按上游已提供的 SKIP_LIBRARY=ON 跳过普通 library 路径；保持所有原生 ABI、目标和完整性检查。

第二轮 https://github.com/continue-arcade/cores/actions/runs/40928616783 三平台编译、原生 ABI 与依赖检查全部通过。Windows DLL 仅依赖 KERNEL32.dll；Linux 仅 libm/libc/loader。
汇总验证正确拒绝 Windows 源码归档与另外两目标不一致，未创建 Release。
下载三个实际归档比较：3017 个成员和 commit pax 一致，Windows 有 1517 个文本因全局 core.autocrlf=true 变为 CRLF（连 git archive 也受影响）。
将上游 checkout 的仓库级 autocrlf=false/eol=lf 固定，归档命令额外显式覆盖这两个配置，确保采用 Git blob 原始换行；不修改上游任何源码。
增加真实 Git 仓库回归测试：本地 autocrlf=true 时，生成归档必须仍为最初提交的 LF 字节。该测试先失败再实现，19 项通过。

## 最终真实发布结果

- 成功工作流：https://github.com/continue-arcade/cores/actions/runs/40929193047
- 不可变试发布：https://github.com/continue-arcade/cores/releases/tag/mgba/v0.1.0-smoke.1
- 配方 commit：`7f119ec`，正式 Core 0.10.5，完整 SHA `26b7884bc25a5933960f3cdcd98bac1ae14d42e2`。
- Release API：draft=false、prerelease=true、immutable=true，10 个资产。Draft 收齐才公开，没有覆盖任何已发布包。
- 三平台 build、原生 ABI、依赖、Cart 验包与来源归档对账全部成功。源码归档统一 SHA-256 `8159bdab2bc318ece0cfec5a8c7e26ce76e0ea97eeac3b66084e62670582384d`，14344744 字节。
- 发布后 `check mgba` 成功返回 `update:false`、`candidate:null`。

| 目标 | Cart 字节数 | SHA-256 |
| --- | ---: | --- |
| macos-aarch64 | 435254 | `1254ddc40299d260c753d6bdb68f265220eb653f646a9f3a6da1e3171b6d451a` |
| windows-x86_64 | 523433 | `75a09fd3828e06d03fa9323d4d3d6363e2128362dc376c18dad926b85f0c410f` |
| linux-x86_64 | 584165 | `5692fd03cfed91d8364ba514f1f71c93f141b9a8c294cb66bd7a166357154b01` |

Linux 实际最高符号需求 **GLIBC_2.38**，要求 **glibc >= 2.38**，只依赖 libm、libc 和系统 loader。不声称通用 Linux 或更老 glibc 兼容。
Windows 静态 CRT，dumpbin 唯一动态依赖 **KERNEL32.dll**，无 VCRUNTIME/MSVCP 依赖。
macOS arm64 仅依赖 **Foundation.framework** 与 **libSystem.B.dylib**；部署目标 11.0，没有在旧版 macOS 真机验收。

上述只是源码/原生 ABI/包装/分发证据。实际 ROM、图像、音频、输入、性能和设备兼容仍未验证；矩阵保持三个既定目标。

## 发布后再次运行的零发布验证

工作流 https://github.com/continue-arcade/cores/actions/runs/40929847081 成功完成：check=success，build=skipped，publish=skipped。
check 使用持久公开 release-report.json 并审计上游 tag，输出 update=false；没有构建包，没有创建或改写 Release。
此验证在源代码与工具链流程保持可执行的情况下证明：仅重新运行、runner 更新或当天 nightly 变化不会触发重复发布。

已另行将公开 Release 全部 10 个资产下载到隔离目录 `/Volumes/GM9000/continue-cores-release-smoke1`，通过固定 `verify` 命令独立完成三平台包与统一源码归档复核。
最终本地 `mise run test`：19 项通过，`git diff --check` 通过。发布后的文档补充没有改变任何 `.cart`、报告、源码归档或校验资产。
