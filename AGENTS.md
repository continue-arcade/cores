# 仓库约定

- 中文注释与文档，对外品牌为 Continue。
- 二进制供应默认预编译优先，源码构建兜底；允许固定摘要的官方快照，如实标注实际版本与来源。
- 自动检查优先跟随正式发布；快照检查按版本/可识别 revision 判断，同版本同 revision 的例行重建跳过，只有包体变化先保留候选。
- 本地与 Actions 共用 scripts/core_release.py；YAML 只编排。
- 新行为先写测试并确认失败；通过 mise exec -- 运行 Python/CMake 命令。
- 不覆盖发布、不 force push、不保存凭据；发布前必须收齐三个目标并验包。
- 原生 ABI 冒烟不能称为 ROM/渲染/音频/性能验证。
