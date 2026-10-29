# NES / SNES / PSP Core 扩展进度

2026-10-30（Asia/Shanghai）。这是实际构建进度记录，不代表未完成目标已经发布。

## 固定来源

- NES：SourMesen/Mesen 0.9.9，f3a18bed018fa853627e0e15d02a3f2ba4960222，资源版本0.9.9。
- SNES：bsnes-emu/bsnes v115，8e80d2f8a43e34a82931e25143b279e5fbcfaedc，资源版本115.0.0（原生ABI字符串115）。Snes9x非商业许可，未采用。
- PSP：hrydgard/ppsspp v1.20.4，fa50bb1976065c4f8b1b47af227d367fe9771555，资源版本1.20.4；固定递归子模块和assets。
- 各自首个Cart版本0.1.0-smoke.1，独立tag前缀mesen/、bsnes/、ppsspp/，三目标macOS/aarch64、Windows/x86_64、Linux/x86_64。

## 实现

流水线已通用化：registry选择、每Core正式tag规则、独立账本、构建适配、包内身份/目标/运行资源摘要、对应源码含固定子模块。PPSSPP assets部署为资源内system/PPSSPP；manifest声明相对system目录。生产入口仍是check/prepare/build/verify/publish。

当前26项测试通过，包括原mGBA回归、独立Core身份、版本规范化、错Core输入锁拒绝、PPSSPP资源缺失与篡改拒绝、递归子模块源码归档。

## 实际CI与修复

- 40938510591：第一轮all。发现同一个run的多个可复用工作流都上传input-lock同名工件，Windows日志显示拿到PPSSPP输入；在发布前取消，未发布新Core。现工件名带Core前缀，build/verify/publish另校验显式请求Core。
- 40940098653：隔离工件后的all。Mesen与bsnes macOS原生构建/ABI通过；Mesen Linux也通过。bsnes GCC需显式stdexcept，Mesen Windows直接构建Libretro项目会缺Core/Utilities/SevenZip静态库。该轮PPSSPP三个目标仍运行中，等待真实结果。
- 40940897482：bsnes补头文件但误作用于C单元，失败。已改仅compiler.cpp追加-x c++ -std=c++17 -include stdexcept。
- 40940905843：Mesen先构建静态库后，Utilities在新MSVC不再传递包含chrono，失败。已只为Utilities的C++编译设置/FIchrono，保留SevenZip C单元。
- 最新适配代码commit8f16598；当前bsnes单独重跑：[40941537627](https://github.com/continue-arcade/cores/actions/runs/40941537627)。
- 当前Mesen单独重跑：[40941545363](https://github.com/continue-arcade/cores/actions/runs/40941545363)。
- PPSSPP的Windows依赖门禁实测需Windows系统IPHLPAPI.DLL，已明确列入允许系统库，仍拒绝VCRUNTIME/MSVCP等未随包依赖。

后续需要等待三个Core完整三目标与immutable发布成功，再验证external Station与正式Core API安装/重复安装/卸载和PPSSPP运行资源完整性。产品仓库scripts/verify-core-cart-release.py已扩展运行资源逐文件校验；不改其他并行产品工作。
