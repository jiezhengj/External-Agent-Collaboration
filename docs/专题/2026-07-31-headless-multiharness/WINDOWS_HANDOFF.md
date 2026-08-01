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
