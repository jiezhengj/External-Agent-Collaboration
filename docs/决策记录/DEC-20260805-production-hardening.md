# DEC-20260805：生产加固的跨项目、施工交接与验收边界

## 决策

1. `external-agent-collaboration` 继续保持 Codex-only；其它 Agent/模型即使发现目录也不得调用、import、路由或修改 Skill runtime。
2. Skill 源仓库承担 shared provider/trust/health/metrics 与中央脱敏 bad-case；目标项目承担 handoff、topic、goal、construction 和 outputs。目标路径通过 `WorkspaceContext` 显式解析，不再由业务层固定根目录推断。
3. Claude Code execute 每次通过临时 `--settings` 安装 Skill-owned `PreToolUse` hook，hook 使用标准库 Python bridge 调用 ScopeGuard；缺失或协议异常 fail-closed。Antigravity 仍只允许明确的只读独立审查角色。
4. Luna 只能修改 Codex 明确授权的普通项目文件，并以 Stage Report 交接；Codex runner 独立生成 manifest/evidence/checkpoint，Codex Review Gate、acknowledgement 和 accepted marker 决定 WP 是否可推进。
5. 第 18 节的每一项 criterion 进入专题目录下唯一的 `goal-contract.json`；Goal 只能在全部 required criteria 有独立证据时 achieved。

## 当前证据

- 本机回归 53/53；标准库 coverage gate 通过 80% 总量与 90% 核心模块门槛；GitHub Actions run `30984221787` 已以提交 `b67d129` 通过 macOS/Windows × Python 3.10/3.13 四矩阵及 coverage 必需检查。
- macOS sibling fixture 真实 Antigravity read-only smoke 成功，response contract 有效、summary 包含 `AGY_CROSS_PROJECT_OK`、workspace hash 前后一致。
- Windows 原生 fake/回归已由 CI 覆盖；本机 53/53 回归、privacy gate、coverage gate 通过；WP-0 至 WP-6 已有最新 accepted checkpoint/review/ack packet。Windows Claude provider smoke、Antigravity 跨项目只读 smoke、WP-7 最终 packet 和最终发布复验仍 pending。

## 2026-08-05 阶段收口补充

- construction protocol 现在只允许 Codex runner 通过受控的内部 runtime path 写入 `.ai-collaboration` 输入；普通项目相对路径仍拒绝越界。
- workspace manifest 忽略 Python 生成缓存，避免无关 `__pycache__`/`.pyc` 令 checkpoint 失效。
- checkpoint 的 `goal_contract_sha256` 绑定到实际契约文件字节哈希；契约新增 `wp0_checkpoint`/`review_wp0` 至 `wp7_checkpoint`/`review_wp7` 的逐阶段 criterion。
- 这次阶段收口不是 Goal 完成。Windows 原生验证完成前，Goal 保持 `active`，且不写入 `wp7_windows`、`cross_project_real_readonly_windows` 等 passed decision。

## 隐私与回滚

凭据、local profile、完整 provider response、bad-case、logs、outputs 和 acceptance runtime 不进入 Git；发布前对准确 staged diff 做 token/private-key/绝对用户路径扫描。执行失败或 outcome/contract 失败时必须恢复本次变更；恢复失败必须进入 terminal `rollback_failed`，不得静默报告成功。
