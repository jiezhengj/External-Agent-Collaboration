# 专题索引

专题用于承载一次有明确问题、基线和后续实施的讨论，不替代任何主文档。一个专题目录的入口页必须说明它基于什么事实、现在处于什么状态、哪些当前文档已吸收其结论，以及到哪里查看实现与验证证据。

|专题|状态|讨论基线|入口|
|---|---|---|---|
|协作效能优化|已实现（P0/P1/P2/P3）|`14a8985` 的已实现协作 harness|[2026-07-29-协作效能优化](2026-07-29-协作效能优化/README.md)|
|Provider 路由、故障切换与 Claude Code 模型职责|P0-P3 配置化实现与 macOS fake/local 回归完成；Windows CI/主机运行证据待完成|当前 provider profile、session/router 实现与 2026-07-29 讨论结论|[2026-07-29-provider-routing-failover](2026-07-29-provider-routing-failover/README.md)|
|Provider 配置文件与 macOS 迁移交接|Windows、macOS 迁移、一次真实只读 smoke 与旧通用 profile 清理已完成|2026-07-30 配置文件直接 token 决定、两端本地验证与 2026-07-31 DeepSeek smoke|[2026-07-30-provider-config-files](2026-07-30-provider-config-files/README.md)|
|Headless multi-harness architecture|P0/P1/P2 已完成 macOS/Windows 验收；AGY P3 execute 已诊断为不可用，固定只读|Claude Code、Antigravity 官方 headless 参考与 2026-07-31 架构决策及 P3 isolated evidence|[专题入口](2026-07-31-headless-multiharness/README.md) · [Windows Codex 接手](2026-07-31-headless-multiharness/WINDOWS_HANDOFF.md)|

目录命名：`YYYY-MM-DD-<slug>/`。目录内至少包含 `README.md`；较长的方案、调研或验收材料放在同一目录，避免与当前规范并列为孤立顶层文件。
