# 项目协作规则

本项目使用 `external-agent-collaboration` Skill，通过本地配置的 provider profile 协调持续的外部协作者会话。Skill 可以隐式触发，但每次外部调用必须对应用户请求或一次明确的 Codex 协作决策；禁止递归调用或自动辩论循环。

- 将每个 session 绑定到主题、provider、model profile 和工作目录；只用明确 session ID 恢复。
- 不切换 CC Switch 的全局当前 provider。
- 不向外部模型发送密钥、`.env` 内容、凭证、客户数据、私钥或无关私人文件。
- 外部文件修改只允许在授权范围内进行；禁止提交、推送、部署、发布、修改 Git 历史、全局安装和破坏性基础设施操作。
- 对代码、Shell、高风险事实或架构结果，检查变更和相关验证；对低风险草稿可保留协作者的独立观点。
- 将稳定背景、当前状态和确认决策维护在 `.ai-collaboration/`，不要只依赖 session transcript。
