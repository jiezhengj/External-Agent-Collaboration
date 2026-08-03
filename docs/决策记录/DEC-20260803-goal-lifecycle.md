# DEC-20260803-goal-lifecycle

- 状态：accepted（规范与核心 runtime 已实现）；双平台完整回归 pending
- 日期：2026-08-03
- 受影响主文档：产品需求文档、技术方案文档、实施计划文档、测试用例文档、协作协议、expected outcomes、协作效能方案、Skill README
- 关联专题：[TOPIC-20260729-collaboration-efficiency](../专题/2026-07-29-协作效能优化/README.md)

## 上下文

当前执行器已经可以用 machine-readable expected outcomes、范围检查和验证命令判断一次 `execute` 是否 `completed`。但多轮主题只有自由文本 `--topic-goal`、`--stop-rule` 和一页 topic state，没有 Goal 条件清单、跨 Run 聚合、终态转换或关闭证据，因此不能无歧义判断一个长期目标是否已经达到。

## 决策

将 Run 与 Goal 分开建模：

- Run 表示一次 `consult`、`critique`、`draft` 或 `execute` 尝试，使用 `completed`、`failed`、`needs_review`、`blocked_by_permission` 等运行态。
- Goal 表示跨一轮或多轮 Run 的用户目标，使用 `active`、`achieved`、`blocked`、`failed`、`cancelled` 五种状态。
- `completed` 只表示本轮 Run 的机器条件通过，不等于 Goal `achieved`。
- Goal 必须把每个必需条件映射到可验证 evidence；自由文本 Goal 与 stop rule 只能作为说明，不能单独触发成功或关闭。
- Goal 只有进入 `achieved`、`blocked`、`failed` 或 `cancelled` 后才允许结束；缺失条件、未知证据和未决 review 一律保持 `active`。
- 必须的用户验收、独立审查和 macOS/Windows 验证纳入 Goal completion policy；不适用的平台必须有明确理由和证据。

本决策已固化并实现 Goal runtime 核心：runner 校验 contract、聚合 Run evidence，`goal_lifecycle.py` 处理人工决策和终态操作。Codex 仍不得把 topic state 的 `completed` 或单次 Run 的 `completed` 直接报告为 Goal 已达成；双平台完整回归完成前，Goal runtime 不算最终验收完成。

## 备选方案

1. 继续使用自由文本 stop rule：实现成本低，但不同执行者会对“完成”“足够好”和“可以结束”产生不同解释。
2. 让模型自行声明 Goal 完成：不可审计，且会重新引入“模型说完成但产物或验证缺失”的问题。
3. 只增加一个 `completed` 字段：无法区分单次 Run 成功、Goal 达成、暂时阻塞和永久失败。

## 后果与实施

- 现有 expected outcomes、范围检查和验证命令继续作为 Run 层基础。
- 已新增 Goal schema、criterion 聚合器、状态转换、关闭记录和手工决策 CLI；仍需在 macOS 与 Windows 执行完整 Goal 回归。
- TC-84 至 TC-93 已有 macOS 本地逻辑覆盖；未取得 Windows 运行证据前，不得把它们全部标记为通过。
