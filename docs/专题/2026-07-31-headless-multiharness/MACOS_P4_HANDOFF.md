# macOS P4 read-only role-router smoke

## 目标

已完成 macOS 的 P4 实机证据：公共 `route_harness.py` 在新主题、无敏感、明确独立审查的请求中自动选择已就绪的 `antigravity_readonly` profile。该 smoke 只读，不验证也不开放 AGY execute；保留以下命令供 profile/CLI 更新后复跑。

## 前置条件

- 使用当前项目与当前 macOS 的 Git 忽略 local profile；不要复制 Windows session、trust、输出或配置。
- 当前 `agy` 已完成缓存登录；profile 已指向 `mode: plan`，且没有 `dangerously_skip_permissions`。

## 运行

在项目根目录创建 Git 忽略 handoff 后运行：

```sh
handoff='.ai-collaboration/handoffs/macos-p4-antigravity-auto-smoke.md'
mkdir -p .ai-collaboration/handoffs
printf '%s\n' 'Return the required response-contract object. This is a non-sensitive macOS P4 automatic Antigravity routing smoke. Do not edit files, run commands, access local configuration or credentials, invoke subagents, commit, push, install, deploy, or publish. In `summary`, state exactly that this is a non-sensitive macOS P4 automatic Antigravity routing smoke. Leave all arrays empty and set `uncertainty` to `None.`' > "$handoff"

python3 .agents/skills/external-agent-collaboration/scripts/doctor_harness.py --profile antigravity_readonly --json
python3 .agents/skills/external-agent-collaboration/scripts/trust_harness.py --profile antigravity_readonly --approve
python3 .agents/skills/external-agent-collaboration/scripts/route_harness.py \
  --action critique \
  --request '请做一次独立风险审查' \
  --topic macos-p4-antigravity-auto-smoke \
  --handoff "$handoff" \
  --working-directory . \
  --task-type planning \
  --mode critique \
  --timeout 180 \
  --return-mode compact \
  --topic-goal 'Verify automatic read-only Antigravity routing on macOS.' \
  --stop-rule 'Complete one non-sensitive automatic Antigravity critique without project file changes.'
```

## 通过条件

输出必须为 `status: completed`、`harness: antigravity`、`routing.basis: explicit_independent_review`、`result_contract_failed: false`，并且项目 tracked 文件无变化。只记录 run ID、状态、harness、routing basis 和 Git revision；不得记录 token、prompt、模型全文、原始 stderr 或 local profile 内容。

## 已执行结果（2026-08-01）

run `1785590735-1988157e` 已通过：`status=completed`、`harness=antigravity`、`routing.basis=explicit_independent_review`、structured contract valid，且项目 tracked 文件无变化。此前两个非最终输入变体分别出现未结构化结果与无结果记录；使用本文件中与 P2 已验证格式一致的 response-contract handoff 后通过。该证据完成 P4 的 macOS/Windows runtime 验收，不改变 AGY 仅只读、Claude Code 唯一自动 execute 的规则。

若 profile/launcher/trust 未就绪，router 必须报告 `antigravity_not_ready` 并交回 Codex 直接处理；不得静默改送 Claude Code、调用 AGY execute 或修改 settings。若返回 permission/contract/CLI failure，不跨 harness 自动重试；修复后使用新 topic 复跑。
