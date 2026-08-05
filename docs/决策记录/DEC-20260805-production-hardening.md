# DEC-20260805：生产加固的跨项目、施工交接与验收边界

## 决策

1. `external-agent-collaboration` 继续保持 Codex-only；其它 Agent/模型即使发现目录也不得调用、import、路由或修改 Skill runtime。
2. Skill 源仓库承担 shared provider/trust/health/metrics 与中央脱敏 bad-case；目标项目承担 handoff、topic、goal、construction 和 outputs。目标路径通过 `WorkspaceContext` 显式解析，不再由业务层固定根目录推断。
3. Claude Code execute 每次通过临时 `--settings` 安装 Skill-owned `PreToolUse` hook，hook 使用标准库 Python bridge 调用 ScopeGuard；缺失或协议异常 fail-closed。Antigravity 仍只允许明确的只读独立审查角色。
4. Luna 只能修改 Codex 明确授权的普通项目文件，并以 Stage Report 交接；Codex runner 独立生成 manifest/evidence/checkpoint，Codex Review Gate、acknowledgement 和 accepted marker 决定 WP 是否可推进。
5. 第 18 节的每一项 criterion 进入专题目录下唯一的 `goal-contract.json`；Goal 只能在全部 required criteria 有独立证据时 achieved。

## 当前证据

- 本机回归 53/53；标准库 coverage gate 通过 80% 总量与 90% 核心模块门槛；GitHub Actions run `30980028521` 已以提交 `1f56dde` 通过 macOS/Windows × Python 3.10/3.13 四矩阵及 coverage 必需检查。
- macOS sibling fixture 真实 Antigravity read-only smoke 成功，response contract 有效、summary 包含 `AGY_CROSS_PROJECT_OK`、workspace hash 前后一致。
- Windows 原生 fake/回归已由 CI 覆盖；Windows 真实 provider smoke、完整 trace coverage gate 与 8 个 accepted WP packet 仍 pending。

## 隐私与回滚

凭据、local profile、完整 provider response、bad-case、logs、outputs 和 acceptance runtime 不进入 Git；发布前对准确 staged diff 做 token/private-key/绝对用户路径扫描。执行失败或 outcome/contract 失败时必须恢复本次变更；恢复失败必须进入 terminal `rollback_failed`，不得静默报告成功。
