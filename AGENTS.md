# 仓库约定

- 中文注释与文档，对外品牌为 Continue。
- 仅从登记上游的正式 Release 构建，完整 SHA 固定；不得把 nightly 标成稳定版。
- 本地与 Actions 共用 scripts/core_release.py；YAML 只编排。
- 新行为先写测试并确认失败；通过 mise exec -- 运行 Python/CMake 命令。
- 不覆盖发布、不 force push、不保存凭据；发布前必须收齐三个目标并验包。
- 原生 ABI 冒烟不能称为 ROM/渲染/音频/性能验证。
