# 预编译优先路径的实际验收

2026-10-30（Asia/Shanghai），实现配方 `90c57575b4066155cc78ff27e7ccae1a20aea5e2`。

`inspect-prebuilt mgba` 从官方 macOS/aarch64 Buildbot 下载并实际加载动态库，检查全部标准 Libretro 入口和 API 1；库名 mGBA，版本 `0.11-212-7a12d6d`，revision 提示 `7a12d6d`。重复观察得到 `unchanged`，未把 ZIP 日期作为更新。

之后使用正式 `prepare mgba 0.10.5 --cart-version 0.2.0-preview.1 --supply prebuilt` 固定三个目标 ZIP/动态库摘要，再执行 `build ... macos-aarch64`，原生架构、依赖、ABI、库名与版本检查通过，直接封装 Cart，没有进入 Core 源码构建。

| 内容 | 实测 |
| --- | --- |
| 官方入口 | `https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/mgba_libretro.dylib.zip` |
| ZIP SHA-256 | `68e4413aa2899349826d1ed67fc8b1f092e24119e8accade6cd4c101900cb5ba` |
| 动态库 SHA-256 | `54ae92e80b012013f6d777fb3158b9f925be22c97896049b8549614d7514f505` |
| 资源版本 | `0.11.0-snapshot.7a12d6d` |
| Cart SHA-256 | `7531c228cfcef5b5db984a6e6ba04eacd73d6698b374a63955fffada833000a7` |
| Cart 大小 | 472170 字节 |
| 包内原始动态库字节 | 与官方 ZIP 中 payload 一致 |
| 依赖 | Foundation、CoreFoundation、libSystem |
| 发布 | 仅本地预览，没有公开发布或替换既有 Cart |

`SOURCE.md` 和 manifest 明确为预编译快照；正式 0.10.5 与完整 SHA 是触发/兜底及许可参考，不声称它就是实际二进制的源码。没有附伪称对应的正式源码归档，未知编译器保留未知。

[全 Core CI 40950911613](https://github.com/continue-arcade/cores/actions/runs/40950911613) 已成功：mGBA、Mesen、bsnes、PPSSPP 四个 check 成功，无新正式版本，四个 build 和 publish 均 skipped。四个 check 中各自复跑全部 36 项脚本测试通过。

预编译新路径实测仅覆盖 macOS/aarch64。本次没有新正式版本，未触发 Windows/Linux 的预编译原生检查，也没有对本地预览包额外做 Station 完整安装验收。四个既有 Core 的源码发布仍保留其原始三平台证据，三个新增 Core 的 external Station 安装/重复安装/卸载与 PPSSPP 189 个运行文件校验已在产品仓库记录。
