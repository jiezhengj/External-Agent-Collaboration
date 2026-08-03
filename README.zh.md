# 外部代理持续协作

[English README](README.en.md) · [项目索引](README.md)

## 项目初衷

这个仓库用于说明并承载一个项目级协作流程：由 Codex 通过本地 headless CLI harness 协调持续的外部编码协作者。Claude Code 是当前已实现的项目协作者 harness；Antigravity 已有独立、受控的只读 adapter，并会自动处理新主题、无敏感、明确要求独立审查的任务。Codex 始终面向用户：接收请求、判断是否值得委派、检查结果并反馈。外部模型只是在明确边界内参与的协作者。

这个 Skill **仅供 Codex 使用**。其它任何 Agent 或模型即使发现本目录，也必须将其视为不可用：不得调用或 import 其中脚本，不得路由或恢复 session，不得创建 handoff，不得调用 provider，也不得修改 runtime state。

项目想解决的问题很具体：长期本地工作不能只靠一次性调用外部模型。需要把 provider 和会话分开、保留项目背景、限制文件修改范围，并验证实际发生了什么。

这里不绑定某一家模型服务商。使用者自行在本地配置正在使用的 provider、模型映射和非敏感 routing policy；MiMo 和 DeepSeek 只是最初本地环境中的示例，并不是本项目的固定依赖。缺少 routing 时保持可持久化公平轮换，也可配置 `fixed` 或确定性的 `weighted_round_robin`；运行指标仅用于审计和日后经明确决策启用的学习路由。

## 具体需求

1. **统一入口与主动触发。** 用户只与 Codex 协作。全局可发现时，Skill 会主动匹配恢复协作主题、用户要求独立/第二模型评审、全仓/关联模块/多文件工作，以及边界明确的独立实施；仅在本地 provider 已配置且后续分类允许时引入外部协作者。简单问答、常规评审和小型单文件修改由 Codex 直接处理。
2. **独立的持续会话。** 一个会话绑定主题、provider、模型 profile 和工作目录。恢复必须使用已保存的 session ID，不能使用含义不明确的“最近会话”。
3. **按任务决定是否委派。** 调用前按任务类型、工作模式、风险、上下文规模和工具需求分类。小任务由 Codex 直接完成；当前信息、连接器、图片、表格、幻灯片、PDF 和最终格式化办公文件走 Codex 原生工具。
4. **可配置路由与可用性兜底。** 新主题按 shared/local 顶层 routing policy 选择健康 provider；缺少配置时公平轮换，也可固定 provider 或按整数权重确定性轮换。provider 的余额、认证、端点或暂时服务故障才会熔断并至多切换另一家一次。
5. **受控的外部修改。** 实施交接必须写明允许路径、禁止路径、允许命令、验收检查和预期产物。
6. **机器检查完成性。** 模型说“完成”不等于完成。预期结果可要求文件存在、包含或等于指定内容、满足受限 JSON Schema、变更数量在范围内，或通过显式批准的验证命令。
7. **按能力处理新建文件。** 新会话实测到的 `Write` 能力，与旧会话创建时的工具集分开处理。旧会话缺工具时优先创建可追溯 fork；精确 Shell 兜底只在必要时使用。
8. **一次独立审查。** 高风险实施可由另一 provider 做一次只读 critique。审查者不会自动再次调用执行者，不产生辩论循环。
9. **持久化本地状态。** 项目背景、决策、交接、输出、会话、能力、路由指标和归档写入本地协作目录，而不是只存在于聊天记录。
10. **Harness 隔离与双平台纪律。** harness、provider/账号目标、模型 profile、会话、权限语义、health 和能力记录彼此独立。任何后续变更都须同时考虑 macOS 与 Windows，并提供验证或明确的不受影响理由。

## 实现内容

项目级 Skill 包含以下部分：

|部分|职责|
| --- | --- |
|任务分类器|决定直接处理、Codex 原生处理、外部协作或禁止交接。|
|Provider 路由器|恢复持续会话，按顶层 routing policy 选择健康 provider；维护本地 cursor、weighted state 和可用性冷却。|
|协作执行器|以隔离 provider 配置调用本地 CLI，并施加受限权限。|
|结果验证器|检查真实文件和命令；对越界或不合格变更进行恢复。|
|能力探测器|需要新建文件或能力记录过期时，实测新会话工具。|
|主题/会话登记|记录主题绑定、fork、活动/归档状态和产物引用。|
|独立审查器|请求与执行者不同的 provider 进行一次受限 critique。|
|指标记录器|保存路由元数据，不保存提示词、token 或文件正文。|
|Harness adapter|归一化每种 CLI 的调用、会话标识、权限拒绝、输出与失败语义，不混淆不同 harness。|

## Headless CLI 参考基线与路线图

[参考基线](docs/headless-cli-references/README.md) 保存了用于本工程设计的 Claude Code 与 Antigravity 官方 headless 页面。它是重要工程输入，不证明某个选项已经安装、启用或安全；采用版本相关 flag 前仍须核对官方页面和本机 CLI help。

Claude Code 原生 JSON Schema adapter、通用 state 边界与 Antigravity 显式只读 adapter 均已完成本地 fake 测试和双平台最小真实 smoke。已配置且当前 fingerprint 已信任的本机 harness 可直接运行最小真实验证；只有网页登录/MFA 等真实交互才需要人处理。Antigravity 不是第三个 Claude Code provider，也不进入当前 DeepSeek/MiMo 自动轮换。只有任务**明确要求**独立评审、第二方案、反证或风险清单，且同时是新主题、无既有会话、非敏感、只读时才选择它；新主题本身绝不触发 Antigravity。AGY headless 自动 execute 已在 full-auto 隔离实验中验证失败，普通项目协作和所有自动 execute 仍由 Claude Code 承担。

## Fork 后快速开始

当前路径的前置条件：Python 3.10+，以及可在本机运行的 Claude Code CLI。Antigravity 在其 adapter 被明确启用前不是前置条件。Fork 或克隆仓库后，先初始化仅限本地的运行文件：

```bash
# macOS / Linux
python3 .agents/skills/external-agent-collaboration/scripts/bootstrap.py --init

# Windows PowerShell 或命令提示符
py -3 .agents/skills/external-agent-collaboration/scripts/bootstrap.py --init
```

该命令会创建运行目录，并确保存在可同步的 `.ai-collaboration/providers.shared.json`。共享文件只保存不含 token 的 provider 定义、相对主目录配置目录和逻辑启动器；它不读取、输出或发送任何凭证。

编辑共享 profile 后，再分别维护 `.ai-collaboration/providers.local.macos.json` 与 `.ai-collaboration/providers.local.windows.json`：每份平台文件可直接保存该平台的 `auth_token`、launcher 和隔离 `CLAUDE_CONFIG_DIR`。这些文件被 Git 忽略；是否由你的私有同步工具同步由你决定。项目不要求使用环境变量、macOS Keychain 或 Windows Credential Manager。随后可在不显示密钥的情况下检查某一 provider：

```bash
# macOS / Linux
python3 .agents/skills/external-agent-collaboration/scripts/doctor.py --provider <provider-key> --json

# Windows PowerShell 或命令提示符
py -3 .agents/skills/external-agent-collaboration/scripts/doctor.py --provider <provider-key> --json
```

通过诊断不等于宿主平台的外发审批。在已授权的实施中，Codex 会在首次调用前于本机写入与当前非密钥 profile 指纹绑定的记录：

```bash
python3 .agents/skills/external-agent-collaboration/scripts/trust_provider.py --provider <provider-key> --approve
```

profile 的 endpoint、模型映射、配置目录或非密钥环境改变后，记录自动失效；Codex 会在下一次已授权实施中刷新。该机制不读取或打印凭证，也不绕过 Codex 宿主的最终外发审批。

配置文件直接 token 是本项目认可的默认方式。旧版通用 `providers.local.json` 可继续使用；需要分别维护平台路径时，将对应 profile 放入 `providers.local.macos.json` 或 `providers.local.windows.json`。不要运行将 token 迁移至环境变量或 OS 凭据库的工具，除非你日后主动改变这一原则。

使用 `bootstrap.py --check` 只检查文件和目录是否就绪；它刻意不验证凭证值。

要改变新主题的正常路由，只需在 `providers.shared.json` 或当前平台 local 文件增加非敏感配置，例如固定使用 MiMo：

```json
{"routing":{"schema_version":1,"default":{"strategy":"fixed","provider":"mimo"},"task_overrides":{}}}
```

也可将 `strategy` 改为 `weighted_round_robin` 并提供 `weights`。`doctor.py --routing --json` 可在不读取或输出凭证的情况下检查生效策略；删除 `routing` 即恢复公平轮换。

## 建议使用流程

1. 读取本地项目背景、当前状态和已确认决策。
2. 编写一份简短且不含敏感内容的 handoff，不复制整段聊天记录。
3. 分类任务；若内容敏感或禁止交接则停止。
4. 恢复精确会话、使用用户指定 provider，或按顶层 routing policy 在健康 provider 间选择；缺少配置时使用持久化 cursor 公平轮换。
5. 涉及文件修改时，声明尽可能小的允许路径和至少一项机器可检查的预期结果。
6. 使用隔离的本地 profile 运行外部协作者。
7. 在 Codex 中检查结果、变更路径、outcomes 和规定验证的实际输出。
8. 高风险任务最多增加一次独立只读审查。
9. 只有已有真实证据时，才更新匿名质量和采纳指标。

上述 `completed` 是单次 Run 的结果，不是持续 Goal 的自动完成信号。多轮任务可通过 `collaborate.py --goal-contract <project-relative-json>` 启用 Goal 聚合；状态写入 `.ai-collaboration/goals/<goal_id>.json`，人工验收、审查、阻塞和取消使用 `goal_lifecycle.py`。即使启用 Goal，也不能仅凭模型自述或自由文本 stop rule 宣布 `achieved`。

## 注意事项

- 绝不向外部 provider 发送 API token、`.env` 内容、密码、私钥、客户导出、生产数据或无关私人文件。
- 不用外部协作者处理实时网页事实、已登录连接器数据、部署、发布、Git 历史重写、全局安装或破坏性基础设施操作。
- 处理任务时不要切换全局 provider。每家 provider 应有独立本地 profile 和配置目录。
- 不从聊天文本推断成功；必须独立验证文件和命令。
- 不能把新会话能力探测的结果套用给旧会话。
- 日志和指标应保持最小化：记录运行元数据，不保存提示词、密钥或业务内容。
- provider 失败应是有边界的失败。仅识别为余额、认证、端点或暂时服务可用性故障时，才会对另一健康 provider 自动调用一次；实现失败、outcome 失败和越界修改不会触发切换。

## 配置原则

版本化的共享 profile 不得保存 token、绝对用户目录、平台专属启动器路径、会话 transcript、能力实验产物或含私人信息的运行日志。provider token 可直接保存在 Git 忽略的平台 local profile 中；是否同步这些私有配置文件由用户决定。无论存储方式如何，token 都不得进入 handoff、输出、日志、测试 fixture 或外部提示词。

每份 profile 只提供本地 CLI 所需内容：隔离配置目录、launcher、CC Switch/Claude Code 的环境模型映射、非密钥环境配置和本地认证。运行器不传 `--model`，因此不会覆盖 provider 内部的 FABLE/OPUS/SONNET/HAIKU/SUBAGENT 映射；它也不把 Flash/Base/Pro 当作跨 provider 路由对象。运行器只能将凭证注入子进程环境，不能写入 handoff 或输出记录。

## 维护方式

当流程落地或发生变更时，应同步更新 Skill 说明、测试、设计文档和本 README。新能力先通过本地回归测试，再视为可依赖。每项变更均要记录 macOS/Windows 影响并验证两端，或给出具体的不受影响理由。真实 provider 测试应使用最小、无敏感内容的任务，并有意识地执行，因为它会消耗已配置服务。

本地回归使用统一入口：macOS/Linux 执行 `python3 .agents/skills/external-agent-collaboration/scripts/run_regression.py`，Windows 执行 `py -3 .agents/skills/external-agent-collaboration/scripts/run_regression.py`。同一入口也由 `.github/workflows/cross-platform-regression.yml` 在两类主机上执行。

## 当前状态

项目级实现、测试、设计文档与中英文 README 均已纳入本仓库。provider 凭证和运行态协作数据刻意保留在本地，并由 Git 忽略。
