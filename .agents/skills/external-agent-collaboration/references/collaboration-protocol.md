# 协作协议

## 路由

1. 用户指定 provider 时使用指定 provider。
2. 存在完全匹配的 active session 时恢复它。
3. 新主题在健康且合格的 provider 间使用 `task_type:mode` 的持久化 cursor 公平轮换；`provider_metrics.json` 只记录审计元数据，不在当前 starter policy 中打破平局。
4. 仅当自动选择的 provider 出现已归类的 billing、authentication、endpoint、rate-limit、transport 或 server 可用性故障时，可故障转移一次；用户明确指定 provider 时不自动替换。任务、契约、outcome、超范围或实现失败不允许切换。

Skill 是否被隐式选中先由 `SKILL.md` 的触发元数据决定；任务分类只在选中后决定是否允许实际委派。`.ai-collaboration/provider-health.json` 只保存 failure kind、次数和 retry time，不保存 prompt、文件正文、token、URL query 或原始 stderr。billing/authentication/endpoint/configuration 冷却 24 小时；暂时故障按 5 分钟、15 分钟、1 小时、6 小时递增。无后台探测；到期后由下一次原本允许的调用恢复尝试。

在首次真实外发前，用户必须运行 `trust_provider.py --provider <key> --approve`。该命令在 ignored 的 `trusted-providers.local.json` 写入 provider key 与当前 profile 的非密钥 fingerprint；runner 只接受仍匹配的记录。profile 的 endpoint、模型映射、配置目录或非密钥环境变化时，记录自动失效。它用于区分“本机 Claude Code harness”与“已获用户批准的 provider egress”，但不能绕过 Codex 宿主平台的最终审批。

Provider token 的默认载体是用户管理、Git 忽略的配置文件。可使用通用 `providers.local.json`，或为 macOS/Windows 分别使用 platform local profile；token 可直接写入对应文件。不得要求 Keychain、Credential Manager 或环境变量，也不得将 token 写入 Git、handoff、输出、日志或外部提示词。

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

## 一次性独立审查

高风险代码、架构或事实任务可在 execute 完成后调用 `review_execution.py`。脚本只允许另一 provider 对已完成的 run 做一次只读 critique，并将结果写到 `reviews/`；不允许该 critique 自动回传给执行者或触发下一轮调用。

## 禁止项

不得发送密钥、个人敏感数据或不相关资料；不得递归调用任何代理；不得依赖“最近 session”；不得通过 CC Switch 改全局 provider；不得把单个协作者输出当作高风险事实的唯一证据。
