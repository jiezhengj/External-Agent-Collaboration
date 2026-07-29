# 外部代理持续协作（中文镜像）

英文主入口为 [SKILL.md](SKILL.md)，其中的 YAML frontmatter 用于 Codex 发现该 Skill。本文件是相同工作流的中文说明；修改主入口时请同步更新本文件。

## 隐式触发范围

全局可发现时，Codex 先依据 `SKILL.md` 的 `description` 决定是否选中本 Skill；`classify_task.py` 只在选中后才决定是否真的发起外部调用，不能替代前一阶段。

对以下非简单仓库任务主动选中：恢复外部协作者主题；用户要求独立或第二模型评审；请求覆盖整个仓库、关联模块或多个文件；或有明确边界的独立实施能显著改善结果。普通问答、常规评审和小型单文件修改不应选中。本项目必须已有可用的本地 provider 配置。

## 协作动作

每个用户请求只进行一次清晰的交接与返回。Codex 始终面向用户；本地配置的外部 provider 是持续协作者，而不是一次性子进程。

- `consult`：获取独立的只读分析。
- `continue`：恢复匹配的持续主题会话。
- `draft`：在共享工作区产出文本或规划草稿。
- `critique`：不改文件地评估现有方案或产物。
- `execute`：修改文件，并且只运行明确允许的验证命令。

当前网页事实、已连接账户数据、图片、幻灯片、表格、PDF 或最终格式化办公产物应使用 Codex 原生工具。不要为了获得一致意见而外包简单任务。

## 准备交接

1. 存在时读取 `.ai-collaboration/project-context.md` 和 `decisions.md`；继续某个主题时，只定位并读取 `.ai-collaboration/topics/` 中对应的一页状态，不默认加载 runtime output 或 transcript。
2. 写入不含敏感内容的请求文件，运行 `scripts/classify_task.py`，并阅读 [任务分类说明](references/task-classification.md)。结果为 `prohibited` 时停止；结果为 `native_codex` 时使用原生工具；只有 `external_agent` 或已记录的合理覆盖才继续。
3. 明确 action、主题、工作目录、允许路径、必要检查和 provider。
4. 尊重用户指定的 provider；否则恢复精确匹配的活动会话；新主题使用 [协作协议](references/collaboration-protocol.md) 中的路由规则。大量非敏感文本先按 [batch 协议](references/batch-protocol.md) 生成并审阅 dry-run manifest，绝不使用一次大范围 `execute`。
5. execute 需要新建文件/目录且能力记录缺失、超过七天、CLI/profile 变化或发生工具失败时，运行 `scripts/probe_capabilities.py --provider <provider>`。
6. 同时检查 provider 能力记录和 session 的 `initial_toolset`。新 session 的能力不能直接套用给旧 session。需要时 fork/new session；只有实测原生创建不可用时，才使用最小精确 Bash 创建白名单。
7. 将简洁 handoff 写入 `.ai-collaboration/handoffs/`。每个 execute 都必须按 [expected outcomes](references/expected-outcomes.md) 写 outcomes JSON。持续主题同时传入简短的 `--topic-goal` 和 `--stop-rule`，用于更新一页本地 topic 状态，而非保存 transcript。
8. 不得加入 `.env` 内容、token、凭证、私钥、客户导出或无关私人文件。

## 调用与安全

每个任务首次调用某 provider 前运行 `scripts/doctor.py --provider <provider>`；它不读取密钥值。`collaborate.py` 默认 `--return-mode compact`，stdout 至多返回 8 KiB 的 run/status/outcomes、受限摘要和本地 output 路径；完整 CLI JSON 只保留在 ignored 的 `.ai-collaboration/outputs/`。最外层严格匹配的 ` ```json ` fence 会在合约校验前剥离；若结果仍不合约但内容可用，不自动重复同一 consult，而是消费受限结果或按明确路径检查本地 output。需要受限 JSON 时用 `structured`，worker 用 `file_only`，仅排障时显式用 `debug`。execute 必须传入允许路径、expected outcomes、必要的 `--allow-command` 和 outcomes 使用的精确 `--validation-command`。

不要切换 CC Switch 全局 provider。执行器使用 `.ai-collaboration/providers.local.json` 中该 provider 的隔离 `CLAUDE_CONFIG_DIR`。

会话绑定主题、provider、model profile 和工作目录；仅用保存的 `session_id` 恢复，绝不使用 CLI `--continue`。provider、model profile、工作目录或持续主题发生变化时新建会话；分支方案使用独立 fork。

外部协作者只能修改允许路径，不能提交、推送、合并、部署、发布、改写 Git 历史、全局安装、访问密钥或运行未批准命令。脚本检测到的越界修改即使模型报告成功也不能视为成功。

高风险 execute 完成后，Codex 检查验证结果，再可运行 `scripts/review_execution.py --run-id <run_id> --provider <different-provider-key>` 做一次只读独立审查；不得自动回调执行者。完成 run 的质量/采纳结果可用 `scripts/assess_run.py` 按 run ID 写入匿名指标。

## 向用户报告

说明 provider、action、会话连续性、主要贡献、变更文件、Codex 执行的验证和未解决风险。默认只使用 compact envelope；只有失败、抽样、审计、调试或用户明确要求时，才按 run 路径读取完整本地 output。不要因为 CLI harness 是 Claude Code 就把底层模型称为 Claude。
