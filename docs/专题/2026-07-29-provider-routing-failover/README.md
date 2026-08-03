# 专题：Provider 路由、故障切换与 Claude Code 模型职责

- 标识：`TOPIC-20260729-provider-routing-failover`
- 状态：**本地实现与 fake/local 回归完成；未新增真实 provider 验证**
- 开始日期：2026-07-29
- 讨论基线：当前 `external-agent-collaboration` Skill、CC Switch 的 DeepSeek/MiMo 隔离配置，以及本机 Claude Code `2.1.220`
- 关联专题：[协作效能优化](../2026-07-29-协作效能优化/README.md)

## 这个专题解决什么

明确两层路由的职责：Codex 只选择 DeepSeek 或 MiMo 并管理 provider 级故障切换；Claude Code 在已经选定的 provider 内部使用 CC Switch 的模型映射。目标是在余额不足、认证失败或服务不可用时，避免反复无效调用，同时不把 Flash/Base 与 Pro 变成 Codex 的平级路由对象。

## 专题材料与当前规范

|用途|位置|使用规则|
|---|---|---|
|完整设计、状态机与验收|[方案](方案.md)|设计与已实施边界；当前规则以主文档和代码为准。|
|配置化路由技术设计与实施计划|[可配置 Provider 路由技术设计与实施计划](可配置Provider路由技术设计与实施计划.md)|配置化策略的 proposed 设计、兼容迁移、实施顺序、测试和双平台验收；尚未改变当前源码行为。|
|当前产品规则|[产品需求文档](../../产品需求文档.md)|实施后同步更新。|
|当前技术设计|[技术方案文档](../../技术方案文档.md)|实施后同步更新。|
|当前实施状态|[实施计划文档](../../实施计划文档.md)|实施任务与优先级以此为准。|
|当前验收范围|[测试用例文档](../../测试用例文档.md)|实施时补充并执行对应测试。|
|实际变更与验证|[迭代记录](../../迭代记录.md)|仅记录实际发生的变更和验证。|

## 讨论结论

1. 已实施：runner 不再向 Claude Code 传递 `--model opus`；provider 的默认主模型及 FABLE/OPUS/SONNET/HAIKU/SUBAGENT 映射由隔离的 CC Switch profile 决定。
2. Codex 的 provider 路由候选仍只有 `deepseek` 与 `mimo`，而不是 Flash/Base/Pro 等内部模型。
3. 已实施：provider 不可用时，Codex 以可解释、有限且带冷却期的跨 provider 故障切换兜底；不因为任务结果差、验收失败或越界修改而换 provider 重试。
4. 同主题跨 provider 切换必须新建目标 provider session，并以最小 topic state/handoff 续接；不得复用原 session ID。
5. 评分数据不足时，按预设的任务场景选择 provider；两家公开能力都覆盖、或不适合做厂商能力判断的场景，使用持久化的公平轮换，不以 provider 名称、厂商宣传或内部 Flash/Pro 名称打破平局。
6. Claude Code 是否创建子代理、如何选择子代理模型与工具，是其 provider 内部行为；Codex 不单独路由、再脱敏、探测或周期复验子代理，只保留对 Claude Code 主进程的既有安全边界。

已同步根 README 的中英文说明、`AGENTS.md` / `AGENTS.zh.md`、协议、主文档、决策记录、测试用例与迭代记录。验证证据见迭代记录；本轮没有新增真实 provider 调用。
