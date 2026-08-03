# DEC-20260729-provider-routing-failover

- 状态：accepted and implemented
- 日期：2026-07-29
- 受影响主文档：产品需求文档、技术方案文档、实施计划文档、测试用例文档、迭代记录
- 专题入口：[TOPIC-20260729-provider-routing-failover](../专题/2026-07-29-provider-routing-failover/README.md)

## 上下文

Claude Code 是 provider 内的 harness，而不是 Flash/Base/Pro 的跨 provider 路由器。原 runner 强制 `--model opus`，且任意非零退出都会尝试另一 provider，既覆盖了 profile 的内部模型选择，也会把实现或验收失败误当成可用性故障。

## 决策

Codex 只选择 provider：健康的外部可委派新主题按持久化 cursor 公平轮换；用户指定和健康的精确 session 优先。runner 不传 `--model`，由每份隔离的 CC Switch/Claude Code profile 决定内部模型 alias。provider health 仅记录 failure kind、次数与 retry time；只对可识别的 availability failure 冷却并最多跨 provider 调用一次。

Claude Code 内部子代理不作为 Codex 的独立路由、脱敏、探测或周期验证目标。外部调用前的最小非敏感 handoff 是本架构的 egress 边界；真实外发还要求 `trusted-providers.local.json` 中存在与当前非密钥 profile 指纹相符的本地 trust record。维护者已授权的实施自动建立或刷新该非密钥记录。

## 备选方案

1. Codex 在 Flash/Base/Pro 间逐轮切换：破坏 provider 内部模型策略与持续 session 稳定性。
2. 以公开模型宣传或少量人工评分固定偏向某 provider：缺乏本 harness 的可迁移证据。
3. 任何失败都切换 provider：会掩盖任务、契约、outcome 与安全范围错误，并增加无效调用。

## 后果与证据

新增 `provider_health.py`、`test_provider_health.py`、`trust_provider.py` 与 provider trust 回归，并修改 runner、路由器、profile 示例与双语规则。后续已在同一决策边界内将正常路由策略配置化为 shared/local/platform local 顶层 `routing`，支持 fair/fixed/weighted 三种确定性策略；旧 fair cursor、health/failover、session 优先级和不传 `--model` 语义保持兼容。当前 macOS fake/local 回归通过，Windows CI/主机运行和新的真实 provider 调用仍未完成。
