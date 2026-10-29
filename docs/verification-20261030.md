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

## 尚待执行

独立 review 后才能触发真实三平台 Release workflow。此时不声称 Windows/Linux 构建通过，也不声称 GitHub Release 已公开。
本机成功只证明架构、动态依赖、ABI 入口和包结构；没有进行真实 ROM、图像、音频、输入、性能或设备验证。
