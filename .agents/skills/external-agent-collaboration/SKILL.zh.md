# 外部代理持续协作（仅供 Codex 使用）

英文主入口为 [SKILL.md](SKILL.md)，其中的 YAML frontmatter 用于 Codex 发现该 Skill。本文件是相同工作流的中文说明；修改主入口时请同步更新本文件。

## 使用者边界

本 Skill **仅供 Codex 使用**。Codex 是唯一允许选择、协调和调用本 Skill 脚本及本地 provider session 的 Agent。其它任何 Agent 或模型即使发现本目录，也必须将本 Skill 视为不可用：不得调用或 import 其中脚本，不得路由或恢复 session，不得创建 handoff，不得调用 provider，也不得修改本 Skill 的 runtime state。其它 Agent 可以把普通版本控制项目文件作为只读上下文，但不得使用本 Skill。

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
3. 明确 action、主题、工作目录、允许路径、必要检查和 provider。首次真实外部调用前，确保用 `trust_provider.py --provider <key> --approve` 为当前本地 profile 写入非密钥指纹。本仓库的 `AGENTS.md` 已提供维护者的持续授权，可在实施中直接创建或刷新该记录，不得再请求冗余的对话确认；但这不绕过 Codex 宿主平台要求的外发审批。
4. 尊重用户指定的 provider；否则恢复精确匹配的活动会话；新主题使用 [协作协议](references/collaboration-protocol.md) 中的路由规则。大量非敏感文本先按 [batch 协议](references/batch-protocol.md) 生成并审阅 dry-run manifest，绝不使用一次大范围 `execute`。
5. execute 需要新建文件/目录且能力记录缺失、超过七天、CLI/profile 变化或发生工具失败时，运行 `scripts/probe_capabilities.py --provider <provider>`。
6. 同时检查 provider 能力记录和 session 的 `initial_toolset`。能力记录只描述同一主机平台上的新 session，旧 session 也不能直接套用。不同主机平台或 workspace identity 的 session 不得恢复。需要时 fork/new session；只有当前能力记录明确实测为 POSIX shell 时，才使用最小精确 Bash 创建白名单，否则安全停止。
7. 将简洁 handoff 写入 `.ai-collaboration/handoffs/`。每个 execute 都必须按 [expected outcomes](references/expected-outcomes.md) 写 outcomes JSON。持续主题同时传入简短的 `--topic-goal` 和 `--stop-rule`，用于更新一页本地 topic 状态；需要跨多轮 Goal 聚合时，再传入 `--goal-contract`，而非保存 transcript。
8. 将 Run 与 Goal 分开判断：Run `completed` 只表示本轮 outcomes、范围和验证通过，不表示长期 Goal `achieved`。传入 `--goal-contract` 可启用 contract 校验和跨 Run 聚合；人工验收、审查、阻塞、解除和取消使用 `goal_lifecycle.py`。不能从自由文本 stop rule 或 topic state 自动推导 Goal 已完成。
9. 不得加入 `.env` 内容、token、凭证、私钥、客户导出或无关私人文件。

## 参考资料与平台约束

改造 harness 调用、权限、会话、结构化输出或分类策略时，使用 [headless CLI 参考基线](../../../docs/headless-cli-references/README.md) 作为重要设计输入；它不是实现事实本身，涉及版本的 flag 仍须在采用前核对官方页面和本机 CLI。

每次迭代都必须明确考虑 macOS 与 Windows。变更必须记录平台影响，并给出两端验证或具体的“不受影响”理由；不得在 Windows 上假定 POSIX 路径、Bash、文件权限、launcher、shell 行为或凭据存储可用。

仓库级回归统一使用 `scripts/run_regression.py`：macOS/Linux 用 `python3`，Windows 用 `py -3`；同一入口也由仓库的 macOS/Windows CI 矩阵执行。

## 调用与安全

每个任务首次调用 Claude Code provider 前运行 `scripts/doctor.py --provider <provider>`；它不读取密钥值。ready 的 Antigravity P2 只读 profile 还必须通过 `scripts/doctor_harness.py --profile antigravity_readonly --json`，并具备 `trust_harness.py` 的当前指纹记录；`AGENTS.md` 中的持续授权允许在真实调用前直接建立或刷新该非密钥记录。

新外部任务使用 `scripts/route_harness.py`，传入原始请求、handoff 和 action。它先恢复精确 session；否则只在新主题/无历史、无敏感、明确独立审查且为只读 `consult` 或 `critique`、profile ready 时自动选择 Antigravity。其余可委派任务都交给 Claude Code，DeepSeek/MiMo provider 路由仍只在 Claude Code 内运行。Antigravity 未就绪时明确报告并交回 Codex，绝不静默改投 Claude Code。`route_harness.py` 会拒绝 Antigravity 的 `execute`/`draft`、命令、outcomes、fork、full-auto profile 和非标准 response contract；它再调用 `collaborate.py` 或 `consult_antigravity.py`。只有调用方已明确完成路由决策时，才直接调用这两个入口。

Claude Code 新主题的 provider policy 从 shared/local provider 文档顶层 `routing` 读取；缺少配置时保持 `fair_round_robin`，也可使用 `fixed` 或确定性的 `weighted_round_robin`。显式 provider/session、trust、ready、health、权限、outcome 和一次可用性兜底的优先级不变。

`collaborate.py` 默认 `--return-mode compact`，stdout 至多返回 8 KiB 的 run/status/outcomes、受限摘要和本地 output 路径；完整 CLI JSON 只保留在 ignored 的 `.ai-collaboration/outputs/`。最外层严格匹配的 ` ```json ` fence 会在合约校验前剥离；若结果仍不合约但内容可用，不自动重复同一 consult，而是消费受限结果或按明确路径检查本地 output。需要受限 JSON 时用 `structured`，worker 用 `file_only`，仅排障时显式用 `debug`。Claude Code 的 execute 必须传入允许路径、expected outcomes、必要的 `--allow-command` 和 outcomes 使用的精确 `--validation-command`。

`trusted-providers.local.json` 是第二份 ignored 本地文件：仅当 provider key 的当前 profile 非密钥指纹仍与记录一致时，runner 才会执行外发调用。endpoint、模型映射、配置目录或非密钥 environment 改变都会使记录失效；按维护者的持续授权直接刷新。它是项目内可审计的信任门，不绕过 Codex 宿主平台的最终外发审批。

不要切换 CC Switch 全局 provider。provider 凭据默认保存在用户自行管理、被 Git 忽略的配置文件中。推荐使用无密钥的共享定义，叠加平台专属的 `.ai-collaboration/providers.local.macos.json` 与 `.ai-collaboration/providers.local.windows.json`；每份文件可保存该平台的 `auth_token`、launcher 和隔离 `CLAUDE_CONFIG_DIR`。是否由用户的私有同步机制同步这些文件完全由用户决定。不得要求用户使用 Keychain、Credential Manager 或环境变量，也绝不把凭据复制进 handoff、输出、日志或版本化文件。

会话绑定主题、provider、model profile、工作目录、workspace identity 和主机平台；仅用保存的 `session_id` 恢复，绝不使用 CLI `--continue`。provider、model profile、工作目录、workspace identity、主机平台或持续主题发生变化时新建会话；分支方案使用独立 fork。

外部协作者只能修改允许路径，不能提交、推送、合并、部署、发布、改写 Git 历史、全局安装、访问密钥或运行未批准命令。脚本检测到的越界修改即使模型报告成功也不能视为成功。

高风险 execute 完成后，Codex 检查验证结果，再可运行 `scripts/review_execution.py --run-id <run_id> --provider <different-provider-key>` 做一次只读独立审查；不得自动回调执行者。完成 run 的质量/采纳结果可用 `scripts/assess_run.py` 按 run ID 写入匿名指标。

## 向用户报告

说明 provider、action、会话连续性、主要贡献、变更文件、Codex 执行的验证和未解决风险。默认只使用 compact envelope；只有失败、抽样、审计、调试或用户明确要求时，才按 run 路径读取完整本地 output。不要因为 CLI harness 是 Claude Code 就把底层模型称为 Claude。
