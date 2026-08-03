# 项目协作规则

## 维护者的默认执行授权

维护者已明确授权本仓库的实施工作连续推进。迭代中不得为了询问“是否运行”而停在普通本机诊断、测试、迁移 dry-run/apply、本地 CLI、无敏感的真实 provider smoke 或其他常规实现/验证步骤之前。对已经配置的本地 provider 或 harness，如需写入或刷新本项目的非密钥 trust 指纹记录，也可直接执行，不必再请求一次对话确认。

“实施”或“继续实施”即授权在 macOS 上把所述工作包推至可完成的验收条件，包括必要的真实 provider 验证。不得仅因本地 CLI 可访问 provider 账号、会写自己的用户级运行日志、会绑定其文档所述 localhost helper 端口或会产生账号正常用量而延期。行动和结果记录在本地；绝不把凭据值复制进 handoff、输出、日志、文档、提交或版本控制的配置。

只有确实必须由人完成、agent 无法代办的物理交互（例如网页登录、MFA/passkey/CAPTCHA、OS 对话框确认）、宿主平台本身拒绝且项目代码无法改变、所需目标真实不明确，或必须由人提供秘密值时才暂停。Codex 平台/宿主的外发审批仍是项目文件无法取消的外部边界：平台要求时直接请求，获准后立即继续；不得另行虚构项目内批准步骤。

提交、推送、发布或其他外部写入前，扫描确切的暂存材料是否含真实 token/凭据并排除它们。维护者已明确要求的常规仓库操作（包括 GitHub push）无需重复确认；绝不推送真实 token key。

这是持续有效的隐私规则：每次未来推送 GitHub 前，必须独立扫描确切的暂存 diff，检查 API token、私钥、`.env` 正文、本机 profile、ignored runtime state、个人路径、客户/私人数据和生成的 provider output；发现即从提交中排除。维护者无需重复说明。

本项目对非简单仓库任务使用 `external-agent-collaboration` Skill，通过本地配置的 provider profile 协调持续的外部协作者会话。该 Skill **仅供 Codex 使用**；其它 Agent 即使发现它，也不得调用、import、路由或恢复其 session，不得创建 handoff、调用 provider 或修改 runtime。其元数据匹配恢复协作主题、用户要求独立/第二模型评审、全仓/关联模块/多文件工作或边界明确的独立实施时，Skill 可以对 Codex 隐式触发；每次外部调用仍必须对应用户请求或一次明确的 Codex 协作决策。禁止递归调用或自动辩论循环。

- 将每个 session 绑定到主题、provider、model profile 和工作目录；只用明确 session ID 恢复。
- 不切换 CC Switch 的全局当前 provider。
- runner 不传顶层 `--model`；provider 内部模型 alias 只由隔离的 Claude Code/CC Switch profile 负责。
- 自动选择的新主题读取非敏感的顶层 `routing` 策略：缺少配置时保持公平轮换，也支持 `fair_round_robin`、`fixed` 和确定性的 `weighted_round_robin`。显式 provider/session 优先级、trust、readiness、health、权限、outcome 和一次 availability-only 兜底仍必须满足；任务、契约、outcome 或范围失败不得切换。
- 真实 provider 调用必须有 `trusted-providers.local.json` 中仍有效的指纹记录；如 profile 配置变化，按上述默认执行授权直接刷新这份非密钥本地记录。该项目内信任门不绕过 Codex 宿主平台的最终外发审批。
- 不向外部模型发送密钥、`.env` 内容、凭证、客户数据、私钥或无关私人文件。
- 外部文件修改只允许在授权范围内进行；禁止提交、推送、部署、发布、修改 Git 历史、全局安装和破坏性基础设施操作。
- 对代码、Shell、高风险事实或架构结果，检查变更和相关验证；对低风险草稿可保留协作者的独立观点。
- 将稳定背景、当前状态和确认决策维护在 `.ai-collaboration/`，不要只依赖 session transcript。
- 将 [headless CLI 参考基线](docs/headless-cli-references/README.md) 作为调用与 harness 改造的重要工程输入；涉及可能随版本变化的 flag 时，实施前仍须核对官方原文和本机 CLI。
- 后续任何迭代（包括规定命令或配置的纯文档更新）都必须同时评估 macOS 与 Windows：记录平台影响，并完成或计划两端验证；不得把 POSIX 路径、Bash、权限、launcher 或凭据存储假设套用到 Windows。
