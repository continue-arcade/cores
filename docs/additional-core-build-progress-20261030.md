# NES / SNES / PSP Core 扩展进度

2026-10-30（Asia/Shanghai）。三个 Core 的三平台构建、不可变发布和本机正式 Rust API 安装验收均已完成。

## 固定来源

- NES：SourMesen/Mesen 0.9.9，f3a18bed018fa853627e0e15d02a3f2ba4960222，资源版本0.9.9。
- SNES：bsnes-emu/bsnes v115，8e80d2f8a43e34a82931e25143b279e5fbcfaedc，资源版本115.0.0（原生ABI字符串115）。Snes9x非商业许可，未采用。
- PSP：hrydgard/ppsspp v1.20.4，fa50bb1976065c4f8b1b47af227d367fe9771555，资源版本1.20.4；固定递归子模块和assets。
- 各自首个Cart版本0.1.0-smoke.1，独立tag前缀mesen/、bsnes/、ppsspp/，三目标macOS/aarch64、Windows/x86_64、Linux/x86_64。

## 实现

流水线已通用化：registry选择、每Core正式tag规则、独立账本、构建适配、包内身份/目标/运行资源摘要、对应源码含固定子模块。PPSSPP assets部署为资源内system/PPSSPP；manifest声明相对system目录。生产入口仍是check/prepare/build/verify/publish。

当前36项测试通过，包括原mGBA回归、独立Core身份、版本规范化、错Core输入锁拒绝、PPSSPP资源缺失与篡改拒绝、递归子模块源码归档。

## 实际CI与修复

- 40938510591：第一轮all。发现同一个run的多个可复用工作流都上传input-lock同名工件，Windows日志显示拿到PPSSPP输入；在发布前取消，未发布新Core。现工件名带Core前缀，build/verify/publish另校验显式请求Core。
- 40940098653：隔离工件后的all。Mesen与bsnes macOS原生构建/ABI通过；Mesen Linux也通过。bsnes GCC需显式stdexcept，Mesen Windows直接构建Libretro项目会缺Core/Utilities/SevenZip静态库。该轮 PPSSPP 三个原生目标后来全部通过。
- 40940897482：bsnes补头文件但误作用于C单元，失败。已改仅compiler.cpp追加-x c++ -std=c++17 -include stdexcept。
- 40940905843：Mesen先构建静态库后，Utilities在新MSVC不再传递包含chrono，失败。已只为Utilities的C++编译设置/FIchrono，保留SevenZip C单元。
- Mesen 最终三平台构建与发布成功：[40941545363](https://github.com/continue-arcade/cores/actions/runs/40941545363)，配方 8f16598。
- bsnes 最终三平台构建与发布成功：[40943514569](https://github.com/continue-arcade/cores/actions/runs/40943514569)，配方 182cf34。Windows 静态链接修复包含显式 libgomp 包与其 runtime 许可。
- PPSSPP 最终成功：[40942026941](https://github.com/continue-arcade/cores/actions/runs/40942026941)，配方 32b6017。长构建期间 main 前进后，发布旧工作流 SHA 遇到 GitHub workflow-scope 403；创建固定历史配方引用后仅重跑 publisher 成功，没有重新构建。未来 prepare 在构建前创建不可移动的配方引用。
- PPSSPP的Windows依赖门禁实测需Windows系统IPHLPAPI.DLL，已明确列入允许系统库，仍拒绝VCRUNTIME/MSVCP等未随包依赖。

## 已发布与安装验收

Mesen、bsnes、PPSSPP 的 `0.1.0-smoke.1` 均为 immutable prerelease，各有三个目标 Cart、报告、完整对应源码与校验材料。
隔离 external Station 从 GitHub 导入并签名；正式 Rust API 完成三者的安装、重复安装、卸载及用户数据保持。PPSSPP 实际校验 189 个运行资源文件。默认本机 Station 也已登记三者，签名身份保持；外链模式长期保存包数为零。
原生 ABI 检查与安装成功不等于宿主已激活 Core；未验证真实 ROM、图像、声音、输入、性能或全游戏兼容。

## 同日供应策略调整

用户明确允许结合现成构建，默认切为 `auto`：官方预编译优先、源码兜底；另提供 `prebuilt` 和 `source`。正式版本仍为日常自动更新主线；人工 `inspect-prebuilt` 按实际版本、可识别 revision 与二进制摘要区分更新、例行重建和候选，不追 nightly 日期。
macOS mGBA 的真实包实测版本 `0.11-212-7a12d6d`，识别 revision `7a12d6d`；重复观察为 `unchanged`。快照资源版本明确带 `snapshot`，正式参考源码不冒充实际二进制源码。已公开的四个源码 Cart 保持原发布，不覆盖或重打。
产品侧完整证据见 `docs/forge/additional-core-carts-verification-20261030.md`；本生产仓库与产品工作区分别维护。
