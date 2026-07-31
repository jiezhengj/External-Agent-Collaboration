# Provider 配置文件与 macOS 迁移交接

## 目的

让在 macOS 上打开同一项目的 Codex 能在不依赖当前聊天记录的情况下，继续完成 provider 配置迁移。本文不包含 token、endpoint 值或任何可用于认证的内容。

## 已确认的配置原则

- 默认且唯一要求的 token 载体是用户管理、Git 忽略的配置文件。
- 支持通用 `.ai-collaboration/providers.local.json`，也支持平台文件 `providers.local.macos.json` 与 `providers.local.windows.json`。
- 平台文件可直接包含对应平台的 `auth_token`、launcher 与 `CLAUDE_CONFIG_DIR`。
- 用户决定自己的私有同步机制是否同步这些文件；项目不要求 Keychain、Credential Manager 或环境变量。
- token 不得写入 Git、handoff、输出、日志、测试 fixture 或外部提示词。

当前有效决定见 [DEC-20260730-provider-token-config-files](../../决策记录/DEC-20260730-provider-token-config-files.md)。

## Windows 已完成状态

- Windows platform profile `.ai-collaboration/providers.local.windows.json` 已生成，并直接保存两个 provider 的 token；其内容不应在聊天、日志或 Git 中展示。
- `providers.shared.json` 已生成且不含 token。
- `doctor.py --provider mimo --json` 与 `doctor.py --provider deepseek --json` 已在 Windows 返回 `ok: true`。
- 18 项本地回归已通过；未发起真实 provider 调用。
- 旧通用 `providers.local.json` 仍保留直接 token，作为 macOS 迁移前的安全来源。不得在 macOS 迁移完成前清理或覆盖它。
- 历史上曾由迁移脚本写入两项 Windows 用户环境变量；用户要求恢复后它们已恢复，但当前配置运行不依赖它们。不得删除、修改或引用它们，除非用户另有明确指示。

## macOS 接手步骤

1. 先确认项目及用户的私有配置同步已完成；不要读取或打印任何配置文件中的 token。
2. 在项目根目录运行：

   ```bash
   python3 .agents/skills/external-agent-collaboration/scripts/migrate_portable_profiles.py --apply
   ```

   此命令只把旧通用 local profile 中的直接 token 复制到 `.ai-collaboration/providers.local.macos.json`，并创建所需的隔离配置目录；若旧配置中的 launcher 或 `config_dir` 明确属于 macOS，也一并保留到 macOS profile。它不会把 macOS 路径复制到 Windows，也不得改用 Keychain、环境变量或其他凭据库。
3. 仅做本地诊断：

   ```bash
   python3 .agents/skills/external-agent-collaboration/scripts/doctor.py --provider mimo --json
   python3 .agents/skills/external-agent-collaboration/scripts/doctor.py --provider deepseek --json
   ```

4. 运行本地回归与文档差异检查。不要发起真实 provider 调用，除非用户在 macOS 上重新明确授权。
5. 将成功/失败与不含 token 的证据写入 `docs/迭代记录.md`。只有用户明确要求，并确认两端配置均可用后，才可运行 `migrate_portable_profiles.py --cleanup-legacy` 清理旧通用 profile。

## macOS 接手结果（2026-07-31）

- 已在 macOS 执行 `migrate_portable_profiles.py --apply`：DeepSeek、MiMo 均已迁移到 macOS 平台 local profile，并已初始化各自隔离配置目录；命令输出未包含 token。
- 两个 provider 的 `doctor.py --json` 均返回 `ok: true`。`migrate_runtime.py` 的只读检查未发现跨平台不兼容 session。
- 全部 18 项本地 Python 回归、脚本编译检查和 `git diff --check` 均通过；其中测试 fixture 已改为按当前平台生成路径、日期和 foreign-host 样本，不再把 macOS 假设为 Windows 回归前提。
- 随后经用户明确授权，已重新批准当前 macOS profile 的 DeepSeek、MiMo 非密钥 fingerprint，并完成一项真实、只读的 DeepSeek smoke：公平轮换自动选择 DeepSeek，未传 runner `--model`，无工具调用、权限拒绝或项目文件变更。CC Switch profile 的实际用量同时记录了 Flash 与 Pro，证明内部模型映射仍由 profile 决定。
- smoke 的核心短语已返回，但 provider 额外附加了解释和 JSON，因此 result contract 未严格匹配；runner 将其保留为已完成的单次调用，不自动重试。
- 已按用户明确指令执行 `--cleanup-legacy`：旧通用 profile 的直接 token 已清空，私有备份已创建。两端 platform overlay 保留；今后以各自平台 local profile 为唯一直接 token 来源。

## 给下一位 Codex 的提示

macOS 迁移、真实只读 smoke 和旧通用 profile 清理均已完成。后续接手者不得将已清空的通用 profile 当作凭据来源；真实 provider egress 仍只适用于当前已获批准的配置 fingerprint，也不要改变“配置文件直接 token”原则。

## 关联文档与证据

- [产品需求文档](../../产品需求文档.md)
- [技术方案文档](../../技术方案文档.md)
- [实施计划文档](../../实施计划文档.md)
- [测试用例文档](../../测试用例文档.md)
- [迭代记录](../../迭代记录.md)
- [配置文件原则 DEC](../../决策记录/DEC-20260730-provider-token-config-files.md)
