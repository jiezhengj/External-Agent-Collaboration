# DEC-20260731-headless-multiharness

状态：accepted
日期：2026-07-31

## 上下文

项目当前通过 Claude Code headless CLI 连接 DeepSeek/MiMo 的隔离 profile。官方 Claude Code 与 Antigravity headless 文档表明，两种 CLI 都具有非交互、JSON/stream 输出、schema、会话和权限语义，但其认证、会话标识、权限拒绝和模型设定不可假定相同。

## 决策

1. 将 Claude Code 和 Antigravity 建模为独立 **harness**，不把 Antigravity 作为 Claude Code provider 或现有 provider router 的第三个候选。
2. 先优化现有 Claude Code：采用原生 JSON Schema output，封装 adapter，保留 `dontAsk`、精确工具白名单、`--resume`、隔离 CC Switch profile，以及 runner 不传 `--model` 的边界。
3. Antigravity 依次经过通用 adapter/state、read-only fake/live 双平台验证、受控 execute 验证；P2 通过后，**只有任务明确要求独立评审、第二方案、反证或风险清单**，并且它是新主题、无既有会话、非敏感、只读时，才自动选择 Antigravity。新主题/新会话本身不构成选择理由；它不是普通项目协作的通用执行器。
4. Claude Code 的默认角色是“项目协作者”：恢复 Claude Code 会话、受限文件修改、需要其已验证的 CC Switch plugin/MCP 或一般新项目协作时均选择它；其内部 DeepSeek/MiMo provider 池继续公平轮换。Antigravity 不参加该池，也不与 Claude Code 公平轮换。
5. 分类器按 session 连续性、用户指定、已验证能力/权限、所需输出契约、风险、任务角色与平台可用性选择 harness；不依据未经对照验证的“模型擅长领域”固化分配。用户明确指定的 harness 优先。
6. 后续 Agent 的所有迭代必须以 [headless CLI 参考基线](../headless-cli-references/README.md) 为重要输入，并同时考虑 macOS 与 Windows，记录验证或不受影响理由。

## 备选方案

1. 将 Antigravity 直接加入 DeepSeek/MiMo 公平轮换：拒绝。它混淆 harness 与 provider，且没有权限/质量/成本的同口径基线。
2. 按主观模型印象直接分配代码、研究或文档：拒绝。没有本项目可复核的比较证据，容易固化不可审计偏见。
3. 仅保持 Claude Code、不留 abstraction：拒绝。会使第二 CLI 的 session、权限与错误语义侵入现有 runner，增加跨平台风险。

## 后果

- session、trust、health、capability 和 metrics 必须增加 harness/profile/platform 边界；不同 harness 绝不恢复彼此 session。
- Antigravity 在 P2 前不进入自动路由；P2 后仅承担已定义的独立只读评审角色。当前 profile 已配置、指纹已信任且宿主允许 egress 时，Codex 可直接运行最小真实调用；不可用时回到 Codex 直接处理/诊断，不静默改作 Claude Code 的同类任务。
- `--dangerously-skip-permissions` 不得用于主工作树自动执行；仅维护者显式启用、trusted 的 disposable isolated experiment 可使用它。软拒绝即使进程退出 0 也必须为 `blocked_by_permission`。
- 每一实施阶段都须有 macOS + Windows fake launcher/本地回归；当前平台已配置、已信任的 profile 直接运行最小真实 smoke。

## 实施结果更新（2026-08-01）

- P0、P1、P2 均已取得 macOS 与 Windows 证据；Antigravity 的已验证自动角色是 P2 只读独立评审。
- P3 的主工作树受控实验及 macOS/Windows disposable full-auto 实验均未满足唯一目标文件的写入 outcome；两端 full-auto 对照均证明 `write_to_file` 可用且 effective mode 为 `always-proceed`，因此不再归因于 Windows 或 settings allowlist。
- 在新的 CLI/agent 版本以同一 isolated P3 契约取得成功证据前，Antigravity 不进入 execute 路由；Claude Code 是唯一自动项目 execute harness。

## 受影响文档与证据

- [产品需求文档](../产品需求文档.md)
- [技术方案文档](../技术方案文档.md)
- [实施计划文档](../实施计划文档.md)
- [测试用例文档](../测试用例文档.md)
- [Headless CLI reference baseline](../headless-cli-references/README.md)
- [专题入口](../专题/2026-07-31-headless-multiharness/README.md)
