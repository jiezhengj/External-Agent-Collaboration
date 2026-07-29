# 协作协议

## 路由

1. 用户指定 provider 时使用指定 provider。
2. 存在完全匹配的 active session 时恢复它。
3. 新主题优先使用本地 `provider_metrics.json` 的同类任务记录；无足够样本时在已配置 provider 间轮换。
4. 仅当自动选择的 provider 出现认证、端点或协议错误时，可故障转移一次；用户明确指定 provider 时不自动替换。

Skill 是否被隐式选中先由 `SKILL.md` 的触发元数据决定；任务分类只在选中后决定是否允许实际委派。可委派的新主题按 `task_type:mode` 查 `provider-metrics.json`：少于三条同类样本时轮换；样本足够后质量优先、完成率和耗时为次级条件。记录只含匿名运行元数据，不能保存提示词或文件正文。

## 能力探测

将实际完成的新建文件操作作为能力证据，而不是依赖模型描述。探测使用 ephemeral session，在 `capability-lab/<provider>/<timestamp>/` 中运行，结果写入 `.ai-collaboration/provider-capabilities.json`。

在以下时机探测：首次需要新建文件/目录的 execute；能力记录超过七天；Claude CLI 版本或非密钥 profile 指纹变化；或外部协作者报告缺少工具。不要在每次普通任务、只读任务或每次 session 恢复前探测。

能力档案是可自动更新的运行数据；不要让外部模型自动改写 `SKILL.md`、`AGENTS.md`、安全策略或 provider 配置。能力记录代表新建 ephemeral session；持续 session 还需检查 `sessions.json` 的 `initial_toolset`，因为恢复会话可能保留创建时的工具集合。

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

## 一次性独立审查

高风险代码、架构或事实任务可在 execute 完成后调用 `review_execution.py`。脚本只允许另一 provider 对已完成的 run 做一次只读 critique，并将结果写到 `reviews/`；不允许该 critique 自动回传给执行者或触发下一轮调用。

## 禁止项

不得发送密钥、个人敏感数据或不相关资料；不得递归调用任何代理；不得依赖“最近 session”；不得通过 CC Switch 改全局 provider；不得把单个协作者输出当作高风险事实的唯一证据。
