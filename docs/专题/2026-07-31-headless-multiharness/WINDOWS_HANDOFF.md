# Windows Codex 接手：Headless multi-harness 验收

## 目标

Windows 真机证据已完成：Claude Code adapter 的全量回归、真实 schema/session smoke，以及 Antigravity P2 fake/live smoke 均已通过。P3 已在 macOS/Windows 受控实验及 macOS isolated full-auto 实验中失败，因此 AGY 当前固定只读；P4 自动 role router 仍未启动。本文件保留为可复跑验收入口。

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

P3 已完成足以固定产品结论的诊断：除第 5.1 节这一次 Windows isolated evidence-parity 复现外，未来 AGY CLI/agent 更新后才可再通过同一 isolated P3 契约重新验证；P4 需要基准证据和新 DEC。永远不要提前把 Antigravity 加进 DeepSeek/MiMo 的公平轮换。

## 5.1 达到 macOS 当前证据进度：Windows isolated full-auto 对照

除本节外，Windows 已具备与 macOS 相同的 Claude Code、路由、P2 Antigravity 只读、fake launcher 和本地回归证据。macOS 另有一项 **disposable isolated full-auto** 实验：即使 effective permission mode 为 `always-proceed`、`write_to_file` 可用，AGY 仍未写入唯一目标。Windows 尚未运行这项完全相同的隔离对照；它是 Windows Codex 达到 macOS 当前证据进度的唯一剩余实机工作。

这不是重新尝试让 AGY 加入 execute 路由，也不是修改 settings、扩大路径 allowlist 或在主工作树传 `--dangerously-skip-permissions`。它只在一个临时目录运行，项目工作树不会被交给 AGY。请先拉取当前 `main`，完成第 1–2 节的 profile/本地回归检查；若 CLI、profile 或 trust fingerprint 自上次 Windows smoke 后发生变化，第 1、3、4 节的最小 smoke 也要按当前状态重跑。

Windows 的 Git 忽略 `.ai-collaboration\harness-profiles.local.json` 若尚未定义 `antigravity_local_full_auto`，在其 `profiles` 对象中加入下列**非密钥** profile，再运行下面的 trust 命令。它只为 disposable executor 提供实验开关；不是普通 AGY execute profile，也不得写入版本控制：

```json
"antigravity_local_full_auto": {
  "harness": "antigravity",
  "launcher": "agy",
  "mode": "accept-edits",
  "execution_scope": {
    "allowed_paths": [".ai-collaboration/capability-lab/agy-isolated-p3/"],
    "allowed_commands": []
  },
  "dangerously_skip_permissions": true
}
```

先创建一个 **Git 忽略** 的 pending source，避免误用已含 `P3 controlled execute accepted` 的历史 tracked artefact 而产生“未写入也匹配”的假阳性：

```powershell
$target = '.ai-collaboration\capability-lab\agy-isolated-p3\pending.md'
$handoff = '.ai-collaboration\handoffs\windows-agy-isolated-p3.md'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
[System.IO.File]::WriteAllText((Join-Path (Get-Location) $target), "P3 pending`n", $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path (Get-Location) $handoff), @"
This is a non-sensitive isolated Windows P3 diagnostic. Edit only the declared target in the disposable project copy. Replace its entire content with exactly the requested text. Do not use shell and do not change any other file.
"@, $utf8NoBom)

py -3 .agents\skills\external-agent-collaboration\scripts\doctor_harness.py --profile antigravity_local_full_auto --json
py -3 .agents\skills\external-agent-collaboration\scripts\trust_harness.py --profile antigravity_local_full_auto --approve
py -3 .agents\skills\external-agent-collaboration\scripts\execute_antigravity_isolated.py --profile antigravity_local_full_auto --handoff $handoff --target $target --expected 'P3 controlled execute accepted' --timeout 180
```

预期当前版本返回 exit code `3`，并在 ignored `.ai-collaboration\outputs\isolated-*.json` 留下脱敏 record：`target_before` 必须是 `P3 pending`，`tool_diagnostics.permission_mode` 应为 `always-proceed`，`tool_diagnostics.write_tool_available` 为 true，`target_matched` 为 false，`non_target_changed_paths` 为空。随后运行 `git status --short`，确认没有 tracked 项目文件变化；不得提交该运行态 record。

若这次在 Windows 意外 `target_matched: true`，也**不得**直接启用 AGY execute：记录 Windows CLI 版本、profile fingerprint、record 中的无内容诊断字段和 Git revision，然后在 macOS 用同一 fresh pending source 重现；只有跨平台成功、完整回归和新的 DEC 都成立后才可重新评估 P3。若仍如预期失败，则记录结果并停止 AGY execute 相关工作；产品结论保持“AGY P2 只读，Claude Code 为唯一自动 execute harness”。

## 6. P3 Windows 实测问题日志（2026-08-01，历史诊断）

**当前结论：P3 尚未通过，不能标记为 complete。** 本节保留 6.10 之前的可复现、脱敏诊断；未记录 token、原始 prompt、模型全文或 stderr 内容。这里所说的“所有尝试均未使用 `--dangerously-skip-permissions`”只适用于这些早期 controlled-execute 尝试，不包括后续 isolated full-auto 对照。

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

### 6.5 已完成的 macOS 对照项目（历史）

1. 在 macOS 上确认安装版本和 `agy --help` 中与 headless、`--mode accept-edits`、JSON schema 相关的实际参数；不要仅依赖旧文档。
2. 对比 macOS 的 Antigravity settings 中工作区信任和 permissions 的实际 JSON 形状，特别是 trusted workspace 是否需要不同字段或规范化路径。
3. 用本节完全相同的单文件、无 shell、无危险跳过 smoke 运行一次，并只记录：是否调用写入工具、最终目标文件是否匹配、范围外变更数、结构化响应是否有效和权限状态。
4. 若 macOS 成功，请记录 Windows 与 macOS 的 CLI 版本、profile 生效方式、settings 关键字段名与运行模式差异，并据此提出最小 Windows 修复；不要扩大 allowlist。
5. 若 macOS 同样失败，应将问题归类为 CLI/headless 执行语义或模型工具路由问题，并在官方参考与可观察的初始化/工具可用性信息中继续定位。

### 6.6 macOS 对照的校正与建议（2026-08-01，已完成）

先校正一个容易造成误判的前提：现有 macOS 的成功证据是 P2 的 `--mode plan`、无工具、只读 schema smoke，**不是** P3 的 `--mode accept-edits` 写入成功。因此它只能证明 macOS 的登录、headless JSON/schema 和只读 conversation 可用，不能作为 Windows P3 “同链路已成功”的对照结论。

macOS 本机 `agy --help` 已确认当前 CLI 暴露 `--mode accept-edits`、`--output-format stream-json` 与 `--json-schema`；`antigravity_execute` 的本地 profile doctor/trust 也可通过。这些是 P3 的前置条件，不是写入能力证据。

当前执行器的 `permission_state: allowed` 同样需要谨慎解释：它只表示终态为 `SUCCESS` 且最终 JSON/stderr 没出现 permission/approval 标记；它**不**表示 `write_to_file` 已被实际调用、也不表示该工具已获明确许可。因此 Windows 的“allowed + changed_files=[]”应暂定为“未观察到拒绝”，而非“写入权限已证明”。

下一轮两端都应使用同一份更可诊断的 smoke，而不是仅强化自然语言提示：

1. 将目标改为预先存在、内容为 `P3 pending` 的受控文件，再要求只把它覆盖为 `P3 controlled execute accepted`。这样把“是否自动创建父目录”从变量中移除；失败回滚后文件必须恢复为 `P3 pending`。
2. 为 P3 执行器增加 opt-in `stream-json` 诊断，只持久化无内容字段：`init` 是否列出 `write_to_file`、有效 permission mode、步骤类型计数、是否观察到写入工具事件、permission signal count、terminal status 和目标/范围检查结果。不得保存 prompt、模型文本、路径之外的文件内容或原始 events。
3. 将 `permission_state` 拆成“terminal permitted/blocked”和“write tool observed/not observed”；只有后者为 observed 才能称写入路径被验证。相同 `SUCCESS` 但没有写入工具事件时，应报告 `no_write_attempt`，而不是 `allowed`。
4. 先在 macOS 跑一次该精简 smoke，再在 Windows 运行完全相同的 profile mode、目标文件、schema 和 timeout。记录 CLI 版本、`init.tools` 是否含写入工具、effective permission mode、工具步骤计数、目标匹配和范围外变更数。两端结果才构成可归因对照。
5. 若 macOS 的 init 中无 `write_to_file`，或两端均有该工具但始终无写入步骤，则问题在 agent/tool routing 或 headless execute 语义，而不是 Windows allowlist；若 macOS 有写入而 Windows 没有，再只比较 CLI 版本和 settings/workspace trust 的规范化字段，提出最小 Windows 修复。

P3 不应以 `--dangerously-skip-permissions` 或扩大到全局 allowlist 来“通过”。目的不是绕开权限，而是拿到能够说明工具为何没有被调用的跨平台证据。

### 6.7 macOS 同契约实测结果（2026-08-01）

macOS 已完成与本节相同边界的真实对照，结果**复现** Windows P3 失败，而不是成功：

- 无文件工具的 `agy -p "Reply exactly PING." --output-format json --mode plan` 返回 `SUCCESS` 和精确 `PING`，证明当前交互登录、headless CLI 和基础网络路径可用。
- `antigravity_execute` 的 profile doctor/trust 均为 `ok: true`；当前 `agy --help` 明确列出 `--mode accept-edits`。
- 以预先存在的、内容为 `P3 pending` 的唯一受控文件运行 P3 execute 后，run `1785565844-ef7bfc83` 记录为 `status: failed`、结构化 contract 有效、`permission_state: allowed`、`changed_files: []`；两个 outcome 均失败，目标文件保持 `P3 pending`，没有范围外变更。

这排除了“Windows 特有的 CLI 登录、accept-edits flag 缺失、目标目录创建或单纯 workspace trust 格式差异”作为首要解释。当前最可信的共同问题是：headless `accept-edits` run 没有让 agent 调用写入工具，而现有 JSON terminal 解析又不能区别“工具未尝试”与“工具已许可”。P3 继续 blocked；下一项实现应是 6.6 的无内容 stream diagnostics，而不是放宽 Windows 权限。

### 6.8 macOS 第二次复测：软拒绝与记录完整性（2026-08-01）

以同一 profile、同一预先存在目标、同一无 shell 范围再次触发 P3 后，目标仍为 `P3 pending`。最新受限状态记录为 `status: blocked_by_permission`、`permission_state: blocked_by_permission`、`changed_files: []`，且没有可用 structured output。它进一步证明 P3 不是 macOS 已成功、Windows 单独失败的情形；两端都不能把当前 `accept-edits` headless 行为视为已验证的文件写入能力。

本次还发现记录 topic 与调用方传入的 topic 不一致。P3 runner 的下一轮回归应断言：每次输出 record 的 `topic`、`harness_profile`、working-directory identity 与实际 argv 一致；任何不一致都必须在调用后立即失败，而不能作为平台行为证据。完成这项 record-integrity 修复后，再用 6.6 的 stream-json 无内容诊断复跑 macOS 与 Windows。

### 6.10 isolated full-auto 结论（2026-08-01）

macOS 以 disposable 临时项目运行 full-auto；临时项目只包含 P3 目标文件和脱敏 handoff。run `isolated-1785568585-dfd9fc5d` 的 effective mode 为 `always-proceed`，`write_to_file` 可用、12 次工具调用、没有范围外文件变更，但目标仍未匹配。故障不依赖主工作树、settings 预授权或 Windows。当前 AGY headless 保留 P2 read-only；P3 只能在未来 CLI/agent 更新后以同一实验重新验证。

### 6.9 macOS stream-json 诊断结论（2026-08-01，已被 6.10 的 full-auto 实验部分取代）

方案 2 已在 macOS 实测。run `1785566527-4aa04f1d` 的无内容诊断显示：`init.tools` 包含 `write_to_file`，但 effective `permission_mode` 是 `request-review`；共观察到 2 个 `tool` 步骤和 2 个 permission signal，最终 terminal `SUCCESS` 仍被归一化为 `blocked_by_permission`，目标文件没有变更。没有 API retry 或 plugin/MCP failure。

这项中间诊断曾把根因暂时收敛为 `accept-edits` 的权限策略。后续 6.10 在 isolated `always-proceed` 下仍未写入目标，已经排除“只差 settings 精确 allow 规则”的解释；不再继续堆积路径 allowlist 或调整 settings。当前有效结论是 AGY 仅保留 P2 read-only，未来只在 CLI/agent 更新后重跑同一 isolated P3 实验。
