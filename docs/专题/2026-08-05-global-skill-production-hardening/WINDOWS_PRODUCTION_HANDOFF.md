# WP-7：Windows 原生生产验收接手文档

本文件供 Windows 上的 Codex 接手当前 Goal。它不是新的设计入口，也不授权 Luna 或其它 Agent 调用本 Skill。接手者必须在原生 Windows PowerShell 中执行，不使用 WSL、Git Bash 或 macOS session/runtime。

## 当前状态

- Goal：`global-skill-production-hardening-v2`，保持 `active`。
- 已 accepted：WP-0 至 WP-6，最新 packet 为 `CP-011-WP-6` / `RV-011`。
- macOS：53 个回归脚本、privacy gate、coverage gate 已通过；此前 GitHub Actions Windows fake/回归矩阵已通过。
- 未完成：Windows 本地回归、Windows Claude provider smoke、Windows Antigravity 跨项目只读 smoke、Windows 相关 Goal criteria、WP-7 最终 review packet、最终发布扫描与推送后的 CI 复验。

## 1. 拉取与隐私检查

在仓库根目录：

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
```

不得提交或上传 `.ai-collaboration` 运行态、`providers.local.windows.json`、trust/profile、outputs、logs、snapshots、token、`.env` 或个人绝对路径。完成修改后只扫描准确 staged diff。

## 2. Windows 本地准备

```powershell
py -3 .agents\skills\external-agent-collaboration\scripts\bootstrap.py --check
py -3 .agents\skills\external-agent-collaboration\scripts\doctor.py --routing --json
```

如果本机 profile 不存在，从公开模板复制后只在 Git 忽略的文件中配置真实 token；不要复制 macOS profile、session、capability 或 trust：

```powershell
$profile = '.ai-collaboration\providers.local.windows.json'
if (-not (Test-Path $profile)) {
  Copy-Item '.ai-collaboration\providers.local.windows.example.json' $profile
}
py -3 .agents\skills\external-agent-collaboration\scripts\doctor.py --provider deepseek --json
py -3 .agents\skills\external-agent-collaboration\scripts\doctor.py --provider mimo --json
py -3 .agents\skills\external-agent-collaboration\scripts\trust_provider.py --provider deepseek --approve
py -3 .agents\skills\external-agent-collaboration\scripts\trust_provider.py --provider mimo --approve
```

若账号余额不足，记录为 `billing`/availability failure；不能把它写成 Windows 代码失败，也不能无限重试。

## 3. 必做 Windows 验证

```powershell
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP 'ext-agent-pycache'
py -3 .agents\skills\external-agent-collaboration\scripts\run_regression.py
py -3 .agents\skills\external-agent-collaboration\scripts\quality_gate.py --privacy
py -3 .agents\skills\external-agent-collaboration\scripts\coverage_gate.py --check
git diff --check
```

必须记录：回归脚本总数、privacy/coverage 结果、Python 版本、Git revision；不得记录 credential、完整 provider response 或 stderr。

## 4. Windows 真实 provider smoke

### 4.1 Claude provider smoke

仅使用无敏感 handoff、新 topic 和 `structured` return mode。可复用 `docs\专题\2026-07-31-headless-multiharness\windows-claude-schema-smoke.md`，但不能恢复 macOS session：

```powershell
py -3 .agents\skills\external-agent-collaboration\scripts\collaborate.py `
  --action consult `
  --provider auto `
  --topic windows-production-hardening-smoke-20260805 `
  --handoff docs\专题\2026-07-31-headless-multiharness\windows-claude-schema-smoke.md `
  --working-directory . `
  --timeout 180 `
  --return-mode structured `
  --stream-diagnostics `
  --task-type planning `
  --mode analyze `
  --topic-goal 'Verify Windows configured provider routing without project access.' `
  --stop-rule 'Complete one non-sensitive Windows provider smoke.'
```

成功证据必须同时满足：`status=completed`、`result_contract_failed=false`、`changed_file_count=0`、`restored_violations=[]`，并且输出只包含脱敏摘要。若 provider 为 billing failure，保留失败 ledger 的脱敏记录，禁止切换全局 provider、传 runner-level `--model` 或跨 harness 自动重试。

### 4.2 Antigravity 跨项目只读 smoke（必做）

4.1 只证明 Windows Claude/provider 路径；它不能替代 `cross_project_real_readonly_windows`。必须再执行一次真实的 Windows Antigravity 只读路由。该调用只能由 Windows Codex 发起；Luna、Claude Code 或其它 Agent 不得调用、导入、转发或修改本 Skill。

先创建一个不含项目私密数据的临时目标目录和 handoff。不要把当前仓库的 `.ai-collaboration`、profile、trust、session 或 output 复制到该目录：

```powershell
$fixture = Join-Path $env:TEMP 'ext-agent-windows-antigravity-fixture'
$handoffDir = Join-Path $fixture '.ai-collaboration\handoffs'
New-Item -ItemType Directory -Force -Path $handoffDir | Out-Null
$handoff = Join-Path $handoffDir 'windows-antigravity-readonly.md'
@'
Return one JSON object only, with exactly this shape:
{"summary":"AGY_CROSS_PROJECT_OK","changed_files":[],"commands_run":[],"validation_results":[],"risks":[],"uncertainty":"None."}
Do not edit files, run commands, invoke subagents, access secrets, or return any other text.
'@ | Set-Content -Path $handoff -Encoding utf8 -NoNewline
```

从本仓库根目录执行真实路由；`--project-root` 和 `--working-directory` 必须都指向临时目标目录，不能指向 Skill 仓库根目录，也不能使用 WSL/Git Bash：

```powershell
py -3 .agents\skills\external-agent-collaboration\scripts\route_harness.py `
  --action critique `
  --harness antigravity `
  --antigravity-profile antigravity_readonly `
  --request 'Run one non-sensitive cross-project read-only Windows smoke. Return the exact JSON contract from the handoff.' `
  --topic windows-cross-project-antigravity-smoke-20260805 `
  --handoff $handoff `
  --working-directory $fixture `
  --project-root $fixture `
  --task-type document `
  --mode critique `
  --timeout 240 `
  --return-mode structured `
  --response-contract standard `
  --topic-goal 'Verify the real Windows Antigravity read-only cross-project route and unchanged target workspace.' `
  --stop-rule 'Complete exactly one read-only Windows Antigravity smoke and stop.'
```

该 smoke 只有在以下条件全部满足时才算通过：返回记录 `host_platform=windows`、`harness=antigravity`、`status=completed`、标准 response contract 有效；结构化结果的 `summary` 精确为 `AGY_CROSS_PROJECT_OK`，`changed_files=[]`、`commands_run=[]`、`risks=[]`、`uncertainty="None."`；目标目录前后 hash 相同；没有新增目标文件、Skill shared output 正文、秘密或个人绝对路径。只读调用失败时保留脱敏失败 ledger，不得把 Claude smoke 或 CI fake smoke 冒充为通过。

## 5. 回写 Goal 与 WP-7 packet

Windows Codex 先把本文件中的命令结果写入 ignored `.ai-collaboration` handoff/evidence，再由 Codex runner 独立生成 WP-7 Stage Report、checkpoint、review 和 acknowledgement。只有以下证据齐全后，才可把对应 criterion 标为 `passed`：

1. Windows 本地回归、privacy、coverage、Claude provider smoke 与 Antigravity 跨项目只读 smoke；
2. macOS 既有 evidence 未过期，且本次变更后的完整 CI 四矩阵通过；
3. `construction_wp_review_gates_accepted_8_of_8`、`current_docs_synchronized`、`staged_privacy_scan_zero_findings` 等最终 criterion 有独立证据；
4. `goal_lifecycle validate/show` 显示所有 required criteria passed 后，才可由 Codex 关闭 Goal。未满足时保持 `active`，不要将 Windows pending criterion 改成 passed。

## 6. 停止条件与回传格式

遇到真实 Windows 缺少登录/MFA、宿主拒绝、CLI 不可用或 provider 余额不足时，不修改安全边界。回传一个脱敏 handoff，至少包含：

```text
platform: windows-native
revision: <git revision>
python: <version>
regression: <passed count or failed test name>
privacy_gate: pass/fail
coverage_gate: pass/fail
provider_smoke: completed | billing | unavailable | contract_failed
antigravity_smoke: completed | unavailable | contract_failed
changed_file_count: <number>
next_action: <one bounded action>
```

不得把原始 token、profile 正文、完整 prompt、完整模型输出、个人绝对路径或客户数据放入 handoff、日志、Git 或聊天。
