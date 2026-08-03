# 协作协议

## 路由

1. `route_harness.py` 先按精确 session、用户指定、handoff 敏感性、任务角色、当前 profile/trust/launcher readiness 与 workspace/platform identity 选择 harness。
2. Antigravity 只在新主题/无历史、无敏感、明确独立审查、第二方案、反方意见或风险清单的 read-only `consult`/`critique` 中自动选择；已有 Antigravity session 只能 read-only `continue`。未就绪时报告 `antigravity_not_ready` 并交回 Codex，不得静默改投 Claude Code。
3. 选定 Claude Code 后，用户指定 provider 优先；否则存在完全匹配的 active session 时恢复它；新主题读取 `providers.*.json` 顶层 routing，按 `task_type:mode` 命中 override/default，缺少配置时使用兼容性的 `fair_round_robin`。支持 `fixed` 和确定性的 `weighted_round_robin`；`provider_metrics.json` 只保存脱敏 cursor/weighted state 与审计元数据，不按质量分打破平局。
4. 仅当自动选择的 Claude Code provider 出现已归类的 billing、authentication、endpoint、rate-limit、transport 或 server 可用性故障时，可故障转移一次；用户明确指定 provider 时不自动替换。任务、契约、outcome、超范围或实现失败不允许切换，也不触发跨 harness 替换。

Skill 是否被隐式选中先由 `SKILL.md` 的触发元数据决定；任务分类只在选中后决定是否允许实际委派。`.ai-collaboration/provider-health.json` 只保存 failure kind、次数和 retry time，不保存 prompt、文件正文、token、URL query 或原始 stderr。billing/authentication/endpoint/configuration 冷却 24 小时；暂时故障按 5 分钟、15 分钟、1 小时、6 小时递增。无后台探测；到期后由下一次原本允许的调用恢复尝试。

在首次真实外发前，Codex 在维护者的持续授权下运行 `trust_provider.py --provider <key> --approve`。该命令在 ignored 的 `trusted-providers.local.json` 写入 provider key 与当前 profile 的非密钥 fingerprint；runner 只接受仍匹配的记录。profile 的 endpoint、模型映射、配置目录或非密钥环境变化时，记录自动失效并由 Codex 在下一次已授权实施中刷新。它用于区分“本机 Claude Code harness”与当前配置的 provider egress，但不能绕过 Codex 宿主平台的最终审批。

Provider token 的默认载体是用户管理、Git 忽略的配置文件。可使用通用 `providers.local.json`，或为 macOS/Windows 分别使用 platform local profile；token 可直接写入对应文件。不得要求 Keychain、Credential Manager 或环境变量，也不得将 token 写入 Git、handoff、输出、日志或外部提示词。

Antigravity 是自动但严格受限的只读独立审查角色：先运行 `doctor_harness.py --profile antigravity_readonly --json`，用户完成一次交互登录后，Codex 用 `trust_harness.py --profile antigravity_readonly --approve` 记录非密钥 profile fingerprint，才可由 `route_harness.py` 自动进入 `consult_antigravity.py`。它固定 `plan`，只接受标准结构化 contract，不允许 execute、draft、命令、outcome、fork 或 `--dangerously-skip-permissions`，不会加入 DeepSeek/MiMo 轮换。诊断明确不验证登录，真实 smoke 才能验证 cached authentication。

## 参考资料与双平台纪律

[Headless CLI reference baseline](../../../../docs/headless-cli-references/README.md) 是调用协议演进的重要依据。其页面转换稿只用于设计比对；任何版本相关 flag、权限语义或输出字段在实施前必须以官方页面与本机 CLI 为准。

后续 Agent 的每次实现和文档迭代都须同时考虑 macOS 与 Windows。对路径、launcher、shell、权限、认证、本地 profile、session/capability 记录和验证命令，必须记录双端影响并覆盖两端测试，或说明其为何不受影响。不得以 macOS/POSIX 成功替代 Windows 验证。

## 能力探测

将实际完成的新建文件操作作为能力证据，而不是依赖模型描述。探测使用 ephemeral session，在 `capability-lab/<provider>/<timestamp>/` 中运行，结果写入 `.ai-collaboration/provider-capabilities.json`。

在以下时机探测：首次需要新建文件/目录的 execute；能力记录超过七天；Claude CLI 版本、非密钥 profile 指纹或主机平台变化；或外部协作者报告缺少工具。不要在每次普通任务、只读任务或每次 session 恢复前探测。

能力档案是可自动更新的运行数据；不要让外部模型自动改写 `SKILL.md`、`AGENTS.md`、安全策略或 provider 配置。能力记录代表同一主机平台上的新建 ephemeral session；不同平台的记录一律失效。持续 session 还需检查 `sessions.json` 的 `initial_toolset`，因为恢复会话可能保留创建时的工具集合。只有档案明确记录 POSIX shell 时才允许 Bash 创建兜底；否则使用原生 Write、fork/new session 或停止。

## Handoff 必填内容

- 当前目标和完成定义；
- 与本轮直接相关的背景、已确认决策和文件路径；
- action、允许路径、禁止路径与允许命令；
- 需要运行的校验与 machine-readable expected outcomes；
- 输出位置、未决问题和禁止行为。

## 回传与最小状态

`collaborate.py` 默认 `--return-mode compact`：stdout 最多返回 8 KiB 的 run/status/outcomes、受限摘要、变更索引和 local output 路径；完整 CLI JSON 仅写入 ignored 的 `outputs/`。`structured` 只接受 `summary`、`changed_files`、`commands_run`、`validation_results`、`risks`、`uncertainty` 六字段的受限 JSON；不合约时记录 `result_contract_failed`，但不取代 execute 的机器 outcomes。`file_only` 只返回索引与 hash；`debug` 才返回完整 record。

bootstrap 创建但不覆盖 `project-context.md`、`decisions.md` 与 `topics/`。每个非 ephemeral run 只更新对应主题的一页状态：目标、范围、状态、下一步、证据路径和 stop rule。不得写入完整 handoff、模型推理、聊天或完整 provider 输出。

## 结束状态

- `completed`：机器 expected outcomes、范围检查和规定校验均通过。
- `needs_review`：越界变更已恢复、校验失败或关键结论尚未核验。
- `failed`：CLI、profile、超时、协议或 expected outcome 错误；执行器恢复该次任务改动。
- `blocked_by_permission`：`dontAsk` 拒绝了一项未预批准操作；不会在非交互 runner 中等待人工终端审批。

## Goal 与 Run 的边界

以上状态是单次 Run 状态，不是长期 Goal 状态。`completed` 只表示本轮 machine outcomes、范围检查和规定校验通过；它不能直接表示 Goal 已达成。一个 Goal 必须有带唯一 ID 的 required criteria、completion policy、stop policy 和 evidence 索引，并由跨 Run 的聚合规则判断。

Goal 的状态只有：

- `active`：仍有 required criterion 未通过，或存在待复核、待用户验收或待证据补齐事项。
- `achieved`：全部 required criteria 通过，必需验证、review 和 user acceptance 完成，证据齐全且没有未解决的强制风险。
- `blocked`：下一步依赖人工权限、外部状态或用户决策，当前没有安全替代路径；必须记录 blocker、责任方和解除条件。
- `failed`：required criterion 已确认不可满足，或达到明确的不可继续/重试上限。
- `cancelled`：用户明确取消。

只有 `achieved`、`blocked`、`failed` 和 `cancelled` 是 Goal 终态；`needs_review`、单次 `failed` 和 `blocked_by_permission` 仍需由上层决定是继续、解除阻塞、重试还是结束。criterion、evidence、平台验证或验收结论缺失时，不得将 Goal 标为 `achieved`。macOS/Windows 均列为 required 时，两端必须分别有通过证据；`not_applicable` 必须有明确理由和证据。

当前 runner 只有在传入 `--goal-contract` 时才启用 Goal schema 校验和自动聚合；`--topic-goal`、`--stop-rule` 和 topic state 仍只是持久化说明。Goal runtime 不会把 Run `completed` 或 topic state 的 `completed` 自动解释为 Goal `achieved`。

## 一次性独立审查

高风险代码、架构或事实任务可在 execute 完成后调用 `review_execution.py`。脚本只允许另一 provider 对已完成的 run 做一次只读 critique，并将结果写到 `reviews/`；不允许该 critique 自动回传给执行者或触发下一轮调用。

## 禁止项

不得发送密钥、个人敏感数据或不相关资料；不得递归调用任何代理；不得依赖“最近 session”；不得通过 CC Switch 改全局 provider；不得把单个协作者输出当作高风险事实的唯一证据。
