# DEC-20260803-configurable-provider-routing

- 状态：accepted（实现、双平台 CI 与健康 provider 真实验证完成；MiMo billing 为外部运行条件）
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

## 验收结果与外部运行条件

- GitHub Actions run `30791528761` 的 `macos-latest` 与 `windows-latest` 均通过，覆盖新增缓冲 relay、终态 billing 归一化、Windows 适配器测试夹具和统一 34 脚本回归入口。
- DeepSeek 真实只读 smoke `1785738096-02d58477` 通过：`stream-json` 终态、精确响应、零项目变更。
- 自动路由真实 smoke `1785738286-26ba6796` 在 MiMo cooldown 后选择 DeepSeek 并通过，route basis 为配置的 `fair_round_robin`，健康候选数为 1。
- MiMo 真实 smoke 已到达正确模型调用链，但 provider 返回账户余额不足；runner 已将终态归一化为 `billing` 并写入 24 小时 cooldown。账户充值/更换有效余额属于外部运行条件，不在代码实施范围内。

## 回滚

删除或恢复顶层 `routing` 即回到 fair default；旧 `round_robin_cursor`、session、health、trust 和事件保留。不得删除用户 local profile、token 或通过 destructive Git 操作回滚。
