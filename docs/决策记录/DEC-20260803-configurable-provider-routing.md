# DEC-20260803-configurable-provider-routing

- 状态：in_progress（P0-P3 已实现；双平台运行证据待完成）
- 日期：2026-08-03
- 受影响主文档：产品需求文档、技术方案文档、实施计划文档、测试用例文档、迭代记录
- 关联专题：[TOPIC-20260729-provider-routing-failover](../专题/2026-07-29-provider-routing-failover/README.md)

## 上下文

Provider 自动选择原本只在 `provider_routing.py` 中实现公平轮换。profile 只描述 endpoint、隔离配置目录、launcher 和认证，无法通过配置表达固定 provider 或调用比例；batch worker 还可能与主 runner 形成不同的路由实现。

## 决策

在现有 `providers.shared.json`、`providers.local.json` 和平台 local 文件顶层增加非敏感 `routing` 对象：

- 支持 `fair_round_robin`、`fixed`、`weighted_round_robin` 三种确定性策略；缺少 `routing` 保持旧公平轮换兼容。
- 选择优先级为显式 session > 显式 provider > active session > task override > default policy > 兼容性 fair。
- routing 不进入 provider trust fingerprint，不绕过 profile readiness、health、权限、outcome 或 session 隔离。
- fixed provider 在调用前不可用时 fail-closed；真实 availability failure 仍最多执行一次独立 fallback。
- cursor 与 weighted state 只写入 ignored `provider-metrics.json`；状态损坏只重建策略状态，不删除 events、session 或 health。
- 主 runner、batch worker 和诊断命令共用同一 loader/resolver；Antigravity 不进入 DeepSeek/MiMo provider pool。

## 已实施证据

- `profile_support.py`：schema validator、shared/local/platform overlay merge、legacy flat ambiguity guard。
- `provider_routing.py`：fair/fixed/smooth weighted algorithms、policy/candidate state key、旧 cursor 兼容和 state rebuild。
- `collaborate.py`、`batch_worker.py`：主链与 batch 统一使用 routing resolver。
- `doctor.py --routing --json`：只输出脱敏策略和 provider key。
- `test_routing_config.py`、`test_provider_routing.py`、`test_collaborate_routing.py` 和全量 `run_regression.py`：macOS 本地通过。

## 未完成与验收门槛

GitHub Actions 已配置 `macos-latest`/`windows-latest` 矩阵，但当前环境没有 Windows/`py -3`，尚未取得 Windows 主机或 CI 运行证据；在此证据产生前，本决策保持 `in_progress`，不能把专题标记为最终 accepted。

## 回滚

删除或恢复顶层 `routing` 即回到 fair default；旧 `round_robin_cursor`、session、health、trust 和事件保留。不得删除用户 local profile、token 或通过 destructive Git 操作回滚。
