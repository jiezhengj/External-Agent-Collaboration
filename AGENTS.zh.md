# 项目协作规则

本项目对非简单仓库任务使用 `external-agent-collaboration` Skill，通过本地配置的 provider profile 协调持续的外部协作者会话。其元数据匹配恢复协作主题、用户要求独立/第二模型评审、全仓/关联模块/多文件工作或边界明确的独立实施时，Skill 可以隐式触发；每次外部调用仍必须对应用户请求或一次明确的 Codex 协作决策。禁止递归调用或自动辩论循环。

- 将每个 session 绑定到主题、provider、model profile 和工作目录；只用明确 session ID 恢复。
- 不切换 CC Switch 的全局当前 provider。
- runner 不传顶层 `--model`；provider 内部模型 alias 只由隔离的 Claude Code/CC Switch profile 负责。
- 自动选择的新主题在健康且合格的 provider 间公平轮换。跨 provider 最多只对已归类的可用性故障兜底一次；任务、契约、outcome 或范围失败不得切换。
- 真实 provider 调用必须有 `trusted-providers.local.json` 中仍有效的用户批准记录；profile 配置变化会使记录失效。该项目内信任门不绕过 Codex 宿主平台的最终外发审批。
- 不向外部模型发送密钥、`.env` 内容、凭证、客户数据、私钥或无关私人文件。
- 外部文件修改只允许在授权范围内进行；禁止提交、推送、部署、发布、修改 Git 历史、全局安装和破坏性基础设施操作。
- 对代码、Shell、高风险事实或架构结果，检查变更和相关验证；对低风险草稿可保留协作者的独立观点。
- 将稳定背景、当前状态和确认决策维护在 `.ai-collaboration/`，不要只依赖 session transcript。
