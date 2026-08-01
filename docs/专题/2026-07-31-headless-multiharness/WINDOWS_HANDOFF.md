# Windows Codex 接手：Headless multi-harness 验收

## 目标

Windows 真机证据已完成：Claude Code adapter 的全量回归、真实 schema/session smoke，以及 Antigravity P2 fake/live smoke 均已通过。P2 之后仍禁止启动 Antigravity execute 或自动角色路由（P3/P4）。本文件保留为可复跑验收入口。

Windows Codex 应直接运行本机诊断、测试、fingerprint trust 刷新和无敏感真实 smoke；只有网页登录、MFA/passkey/CAPTCHA、OS 对话框、缺少本机配置或宿主拒绝 CLI 进程时才需要人处理。Git 操作前不得提交或推送 token、`.env`、local profile、outputs、logs 或 snapshots。

## 已完成基线

- Claude runner 不传顶层 `--model`；DeepSeek/MiMo 的内部模型映射由隔离 CC Switch profile 负责。
- Claude Code 新主题只在健康 DeepSeek/MiMo 间公平轮换；Antigravity 不参与轮换，也尚未自动路由。
- `ClaudeCodeAdapter` 已支持 native `--json-schema`、`structured_output`、精确 `--resume` 与 opt-in `--stream-diagnostics`。
- `AntigravityAdapter` 只允许 `consult`/`critique` + `--mode plan`，保存 `conversation_id`，不使用 `--dangerously-skip-permissions`。
- macOS 已完成两套真实 smoke。不得复制或恢复 macOS 的 session、trust、capability 或 profile 到 Windows。

背景见 [专题入口](README.md)、[技术方案](../../技术方案文档.md)、[实施计划](../../实施计划文档.md)、[测试用例](../../测试用例文档.md) 与 [迭代记录](../../迭代记录.md)。

## 1. Windows 准备

Windows local profile 必须是 Git 忽略文件；不要把 token 写进本文件。运行：

```powershell
py -3 .agents\skills\external-agent-collaboration\scripts\bootstrap.py --check
py -3 .agents\skills\external-agent-collaboration\scripts\doctor.py --provider deepseek --json
py -3 .agents\skills\external-agent-collaboration\scripts\doctor.py --provider mimo --json
py -3 .agents\skills\external-agent-collaboration\scripts\trust_provider.py --provider deepseek --approve
py -3 .agents\skills\external-agent-collaboration\scripts\trust_provider.py --provider mimo --approve
claude --help
agy --help
```

`agy` 使用网页/OAuth cached login；若未登录，仅该交互式登录需要人完成。其 profile 必须是 Git 忽略的 `.ai-collaboration/harness-profiles.local.json`，并至少含 `harness: antigravity`、`launcher: agy`、`mode: plan`。

## 2. 完整 Windows 本地回归

```powershell
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP 'ext-agent-pycache'
Get-ChildItem .agents\skills\external-agent-collaboration\scripts\test_*.py | Sort-Object Name | ForEach-Object {
  py -3 $_.FullName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
py -3 -m py_compile .agents\skills\external-agent-collaboration\scripts\stream_diagnostics.py .agents\skills\external-agent-collaboration\scripts\claude_code_adapter.py .agents\skills\external-agent-collaboration\scripts\antigravity_adapter.py .agents\skills\external-agent-collaboration\scripts\collaborate.py
git diff --check
```

已验收：Windows 全量回归通过（23 项）。若 `.cmd` fake launcher、路径、编码或 platform/session isolation 后续失败，修复并补回归，不能以 macOS 成功替代 Windows 证据。

## 3. Claude Code 真实 schema + resume smoke

```powershell
py -3 .agents\skills\external-agent-collaboration\scripts\collaborate.py --action consult --provider deepseek --topic windows-claude-code-schema-smoke --handoff docs\专题\2026-07-31-headless-multiharness\windows-claude-schema-smoke.md --working-directory . --timeout 180 --return-mode structured --stream-diagnostics --task-type planning --mode analyze --topic-goal 'Verify Windows Claude Code stream schema output without project access.' --stop-rule 'Complete Windows schema and session-resume smoke.'
```

已验收：首次调用为 `status: completed`、`result_contract_failed: false`，有完整 response contract 且项目文件无变更；恢复调用的 route basis 为 `explicit_session_key`。如需重跑，再只恢复刚创建的 Windows session：

```powershell
$session = (Get-Content .ai-collaboration\sessions.json -Raw | ConvertFrom-Json).sessions | Where-Object { $_.topic -eq 'windows-claude-code-schema-smoke' -and $_.harness -eq 'claude_code' -and $_.status -eq 'active' } | Select-Object -Last 1
if ($null -eq $session) { throw 'Windows Claude smoke session was not registered.' }
py -3 .agents\skills\external-agent-collaboration\scripts\collaborate.py --action continue --provider deepseek --session-key $session.key --topic windows-claude-code-schema-smoke --handoff docs\专题\2026-07-31-headless-multiharness\windows-claude-schema-smoke.md --working-directory . --timeout 180 --return-mode structured --stream-diagnostics --task-type planning --mode analyze --topic-goal 'Verify Windows Claude Code stream schema output without project access.' --stop-rule 'Complete Windows schema and session-resume smoke.'
```

第二次 route basis 必须为 `explicit_session_key`。`permission_denials -> blocked_by_permission` 由 fake launcher 回归覆盖；不要为制造拒绝修改全局 CC Switch。

## 4. Antigravity P2 Windows smoke

```powershell
py -3 .agents\skills\external-agent-collaboration\scripts\doctor_harness.py --profile antigravity_readonly --json
py -3 .agents\skills\external-agent-collaboration\scripts\trust_harness.py --profile antigravity_readonly --approve
py -3 .agents\skills\external-agent-collaboration\scripts\consult_antigravity.py --action consult --topic windows-antigravity-p2-smoke --handoff docs\专题\2026-07-31-headless-multiharness\windows-antigravity-p2-smoke.md --profile antigravity_readonly --working-directory . --timeout 180
```

已验收：`status: completed`、`harness: antigravity`、`result_contract_failed: false`，已注册独立 conversation/session，且项目文件无变更。若 `agy` 后续无法写用户日志或绑定 localhost，记录为宿主运行态问题；不得使用 `--dangerously-skip-permissions`，也不得伪装为认证/schema 成功。

## 5. 收口

已将 Windows 结果写入 [迭代记录](../../迭代记录.md)。不得记录 token、完整 stderr、prompt 或 provider 输出。已更新专题入口；P2 已具备双平台证据。

之后才可规划 P3/P4：P3 先定义 Antigravity settings allowlist、可写路径、命令边界、软拒绝与回滚；P4 需要基准证据和新 DEC。永远不要提前把 Antigravity 加进 DeepSeek/MiMo 的公平轮换。

## 6. P3 Windows 实测问题日志（2026-08-01，供 macOS 接手）

**当前结论：P3 尚未通过，不能标记为 complete。** 本节只记录可复现的、脱敏后的诊断信息；未记录 token、原始 prompt、模型全文或 stderr 内容。所有尝试均未使用 `--dangerously-skip-permissions`，且没有产生范围外写入。

### 6.1 已完成的受控执行准备

- 新增独立的本地 profile `antigravity_execute`：`mode` 为 `accept-edits`，执行范围只允许 `docs/专题/2026-07-31-headless-multiharness/p3-smoke/`，允许命令列表为空。
- `harness_profile_support.py` 已要求 `accept-edits` profile 必须同时声明非空的 `allowed_paths` 与 `allowed_commands`；`antigravity_adapter.py` 已按 profile 传递 `--mode accept-edits`。
- 新增 `execute_antigravity.py` 受控执行器：执行前建检查点与清单，执行后检查变更路径和预期结果；违反范围、响应无效或结果不符合预期时恢复变更。
- 本地 trust record 已为 `antigravity_execute` 刷新；`doctor_harness.py --profile antigravity_execute --json` 返回 `ok: true` 且 `profile_trusted: true`。
- Windows 的 Antigravity CLI 设置中只加入了 P3 目标目录的单条文件写入 allow 规则，没有加入 shell 权限或跳过权限规则。随后补入当前项目工作区的 trusted-workspace 记录。

### 6.2 受控 smoke 的预期

受控 smoke 唯一允许创建/覆盖的目标为：

`docs/专题/2026-07-31-headless-multiharness/p3-smoke/accepted.md`

其预期文件内容为：

```text
P3 controlled execute accepted
```

执行器同时要求结构化响应满足既有 schema。任何非目标变更、目标文件内容不匹配或结构化响应无效都会触发失败处理；验证到的范围外变更会被恢复。

### 6.3 Windows 运行时间线

| 次序 | 运行标识/方式 | 可观察结果 |
| --- | --- | --- |
| 1 | 前台运行，45 秒外层超时 | 外层退出码 `124`（transport/等待超时）；目标文件不存在。此时未获得可记录的运行结果。 |
| 2 | `1785563318-acc61f23` | 执行器记录 `status: failed`；`permission_state: allowed`；结构化响应有效；`changed_files: []`；预期文件比对为 false。 |
| 3 | 加强“必须使用文件写入工具、仅文本回复即失败”的同一 smoke，前台 55 秒 | 外层退出码 `124`；目标文件仍不存在。 |
| 4 | `1785564168-bca55b00`，隐藏后台、180 秒上限 | 完成但失败；目标文件未创建。使用后台方式只是绕过宿主对单次前台等待时长的限制，不改变 CLI 参数或权限范围。 |
| 5 | `1785564377-4ec91dc7`，补入 trusted workspace 后的隐藏后台复测 | 完成但失败；目标文件仍未创建。`permission_state` 仍为 `allowed`，未观察到范围外文件。 |

所有后台尝试的 stderr 文件长度为 0；为避免记录敏感或无关模型内容，未持久化原始 stdout/stderr 或模型回复，仅保存执行器的受限状态摘要。

### 6.4 目前的故障判断

Windows 上的现象不是已知的 token、profile trust、allow-path 或 workspace trust 拒绝：profile doctor 通过，受控路径 allow 规则存在，workspace 已由未信任修正为信任，执行器也收到 `permission_state: allowed` 和有效结构化回复。

但 `agy` headless 调用在 `accept-edits` 下始终没有实际调用文件写入能力，导致零文件变更、预期结果失败。现有证据不足以断定是 Windows CLI/model 的工具可用性、headless 模式语义，还是 settings 字段/工作区信任的精确格式差异；P3 应保持阻塞状态，不能通过放宽为全局权限或使用危险跳过参数来掩盖问题。

另有一项独立的 Windows 兼容性修复：Python 适配器使用 `subprocess.run(..., text=True)` 时继承 GBK 解码，曾因 UTF-8 CLI 输出触发 `UnicodeDecodeError`。Claude Code 与 Antigravity 适配器现在显式使用 `encoding="utf-8", errors="replace"`，并增加非 ASCII 输出回归测试。macOS 默认 UTF-8 环境通常不会暴露该问题，仍请保留该显式处理以保证跨平台一致性。

### 6.5 请 macOS 接手时比较的项目

1. 在 macOS 上确认安装版本和 `agy --help` 中与 headless、`--mode accept-edits`、JSON schema 相关的实际参数；不要仅依赖旧文档。
2. 对比 macOS 的 Antigravity settings 中工作区信任和 permissions 的实际 JSON 形状，特别是 trusted workspace 是否需要不同字段或规范化路径。
3. 用本节完全相同的单文件、无 shell、无危险跳过 smoke 运行一次，并只记录：是否调用写入工具、最终目标文件是否匹配、范围外变更数、结构化响应是否有效和权限状态。
4. 若 macOS 成功，请记录 Windows 与 macOS 的 CLI 版本、profile 生效方式、settings 关键字段名与运行模式差异，并据此提出最小 Windows 修复；不要扩大 allowlist。
5. 若 macOS 同样失败，应将问题归类为 CLI/headless 执行语义或模型工具路由问题，并在官方参考与可观察的初始化/工具可用性信息中继续定位。
