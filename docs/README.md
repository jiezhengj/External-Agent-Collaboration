# 文档索引

`docs/` 按职责而非创建时间组织：顶层是当前有效规范；`专题/` 保存有明确起止和上下文的讨论/实施专题；`决策记录/` 保存需要长期解释取舍的短记录；`迭代记录.md` 保存已经发生的变更和验证。

## 当前有效规范

`external-agent-collaboration` Skill 是 Codex-only 能力：其它 Agent 可以阅读版本控制中的项目文档，但不得调用其脚本、provider、session 或 runtime。

- [产品需求文档](产品需求文档.md)：当前产品目标、范围与规则。
- [技术方案文档](技术方案文档.md)：当前架构、实现边界与待实施技术设计。
- [外部 Agent 协作技能架构图](技能架构图.md)：产品分工、harness 路由、运行态和执行边界的 Mermaid 图解。
- [实施计划文档](实施计划文档.md)：当前工作包、优先级和完成条件。
- [测试用例文档](测试用例文档.md)：当前验收范围和已执行结果。

## 工程参考基线

- [Headless CLI reference baseline](headless-cli-references/README.md)：Claude Code 与 Antigravity CLI 的官方页面转换稿。它们是 invocation、权限、结构化输出、会话和跨平台测试设计的重要参考；采用具体 flag 前仍须核对官方原文和本机 CLI。

所有后续 Agent 的实现、文档和测试迭代必须同时评估 macOS 与 Windows：记录平台影响，提供两端验证，或说明为何不受影响。不得以 POSIX 路径、shell、权限或凭据假设替代 Windows 验证。

## 专题与历史

- [专题索引](专题/README.md)：按专题查看讨论基线、实施状态和证据。
- [全局 Skill 生产加固、跨项目调用与失败案例闭环](专题/2026-08-05-global-skill-production-hardening/README.md)：面向 Luna 级施工者的详细实施契约，覆盖跨项目根目录解耦、失败 ledger、持续 Goal、多 Run/Codex Review Gate、范围与回滚、触发优化和 macOS/Windows 验收。
- [决策记录索引](决策记录/README.md)：查看重大取舍及其废止关系。
- [迭代记录](迭代记录.md)：查看实际改动和验证。

顶层不直接放置缺少上下文的专题方案。每个专题必须有入口页；入口页是该专题的唯一导航和状态页。
