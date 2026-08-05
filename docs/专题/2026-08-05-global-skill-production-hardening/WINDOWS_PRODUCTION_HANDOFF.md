# WP-7：Windows 原生生产验收接手文档

本文件供 Windows 上的 Codex 接手当前 Goal。它不是新的设计入口，也不授权 Luna 或其它 Agent 调用本 Skill。接手者必须在原生 Windows PowerShell 中执行，不使用 WSL、Git Bash 或 macOS session/runtime。

## 当前状态

- Goal：`global-skill-production-hardening-v2`，保持 `active`。
- 已 accepted：WP-0 至 WP-6，最新 packet 为 `CP-011-WP-6` / `RV-011`。
- macOS：53 个回归脚本、privacy gate、coverage gate 已通过；此前 GitHub Actions Windows fake/回归矩阵已通过。
- 未完成：Windows 本地回归、Windows 真实 provider smoke、Windows 相关 Goal criteria、WP-7 最终 review packet、最终发布扫描与推送后的 CI 复验。

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

## 5. 回写 Goal 与 WP-7 packet

Windows Codex 先把本文件中的命令结果写入 ignored `.ai-collaboration` handoff/evidence，再由 Codex runner 独立生成 WP-7 Stage Report、checkpoint、review 和 acknowledgement。只有以下证据齐全后，才可把对应 criterion 标为 `passed`：

1. Windows 本地回归、privacy、coverage 与真实 provider smoke；
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
changed_file_count: <number>
next_action: <one bounded action>
```

不得把原始 token、profile 正文、完整 prompt、完整模型输出、个人绝对路径或客户数据放入 handoff、日志、Git 或聊天。
