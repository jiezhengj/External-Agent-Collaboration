# 可配置 Provider 路由策略：技术设计与实施计划

- 状态：in progress；P0-P3 已实施，P4 双平台/真实验证待完成
- 所属专题：[Provider 路由、故障切换与 Claude Code 模型职责](README.md)
- 编写日期：2026-08-03
- 适用平台：macOS、Windows
- 目标版本：`routing schema v1`、provider router compatibility release

本文把当前写死在代码中的 Provider 选择策略抽离为非敏感配置，并给出可直接执行的实施顺序、兼容策略、状态迁移、测试矩阵和回滚方案。当前源码已实现 P0-P3：缺少 routing 时保持旧公平轮换；存在 routing 时按配置选择策略。P4 的 Windows CI/主机运行和最小真实 smoke 仍是发布门槛。

## 1. 决策摘要

### 1.1 要解决的问题

当前 `DeepSeek` 与 `MiMo` 的自动选择策略集中在 `provider_routing.py` 的 `choose_provider()` 中。provider profile 配置只定义 endpoint、模型映射、隔离配置目录和认证方式，不定义路由策略。因此：

- 修改公平轮换、固定 provider 或权重比例必须修改代码；
- `--provider deepseek` / `--provider mimo` 只能做单次命令覆盖，不能表达项目默认策略；
- `provider-metrics.json` 中的 cursor 是运行状态，不是用户可编辑的策略配置；
- `provider-health.json` 是可用性状态，也不应与路由偏好混在一起。

### 1.2 总体决策

新增一个非敏感的顶层 `routing` 配置对象，放在现有 `providers.shared.json` / local profile 文档旁边，并保持缺省兼容：

1. 缺少 `routing` 时，自动使用当前公平轮换；
2. 用户显式指定 provider 的优先级最高；
3. 已有精确 active session 仍优先恢复绑定的 provider；
4. 配置策略只决定“正常选择谁”，不绕过 trust、profile readiness、health、权限和 outcome 安全边界；
5. availability failure 的一次性故障切换仍是独立的安全策略，不由普通权重配置关闭；
6. cursor 和加权算法状态继续写入 ignored runtime，而不写入版本化配置；
7. provider 内部的 Flash/Base/Pro/FABLE/OPUS/SONNET/HAIKU/SUBAGENT 映射仍由隔离的 CC Switch/Claude Code profile 负责，不能写成 Codex 的平级路由 provider。

### 1.3 第一版支持的策略

第一版只支持确定性策略，不引入随机数、不引入质量自学习：

|策略|用途|是否需要状态|第一版行为|
|---|---|---:|---|
|`fair_round_robin`|保持现有默认行为|是|在健康候选中按稳定排序和持久化 cursor 轮换|
|`fixed`|固定一个正常情况下的主选 provider|否|目标 provider 健康且 ready 时选择它；调用过程中发生 availability failure 仍可执行一次现有 failover|
|`weighted_round_robin`|按整数权重控制长期调用比例|是|使用确定性的 smooth weighted round-robin，健康候选变化时重新建立候选状态|

质量分、耗时、成本和用户采纳数据继续用于审计。要让它们改变自动路由，必须另立决策记录、定义最小样本、冷启动和防止反馈回路的规则，不纳入本次 MVP。

## 2. 当前实现基线与改动边界

### 2.1 当前路由入口

当前入口链路如下：

```text
route_harness.py
  -> 选择 harness
  -> collaborate.py
       -> profiles() / trusted_profiles()
       -> provider health 过滤
       -> select_provider()
            -> 用户指定 provider
            -> 精确 active session
            -> provider_routing.choose_provider()
       -> ClaudeCodeAdapter
            -> 隔离 CLAUDE_CONFIG_DIR
            -> provider environment
            -> 不传 runner-level --model
```

相关实现位置：

- `scripts/provider_routing.py`：当前公平选择和指标 cursor；
- `scripts/profile_support.py`：shared、local、platform local profile 合并；
- `scripts/collaborate.py`：用户指定、session 恢复、health 筛选、一次 failover 和 runner 主流程；
- `scripts/batch_worker.py`：当前直接调用 provider router 的批处理 worker；
- `scripts/route_harness.py`：先选 Claude Code 或 Antigravity harness，不应把 Antigravity 加入 DeepSeek/MiMo provider 池。

### 2.2 必须保持不变的行为

- `--provider <key>` 仍然覆盖自动路由；用户明确指定 provider 时不能静默替换；
- `--session-key <key>` 和完全匹配的 active session 仍绑定原 provider；
- 不跨 provider 复用 Claude Code session ID；
- profile 的认证、endpoint、隔离 `CLAUDE_CONFIG_DIR` 和内部模型环境映射不改变；
- runner 不增加 `--model`；
- trust fingerprint 不把路由偏好当成 provider 凭据或 profile 身份；
- health cooldown 只阻止不可用 provider 被正常调用；
- 只有 billing、authentication、endpoint、rate-limit、transport、server 等可用性失败，才允许一次自动 failover；
- response contract、expected outcomes、验证、范围检查、权限拒绝和实现失败不能触发跨 provider 重试；
- Claude Code 与 Antigravity 仍是不同 harness，Antigravity 不进入本配置的 provider pool。

## 3. 配置设计

### 3.1 配置放置位置

推荐在现有 provider 配置文档的顶层增加 `routing`，而不是新建一套平行的秘密配置系统：

```text
.ai-collaboration/
  providers.shared.json                 # 版本控制；provider 定义 + 非敏感 routing 默认值
  providers.local.json                  # ignored；兼容旧通用 profile，可覆盖 routing
  providers.local.macos.json            # ignored；macOS profile，可覆盖 routing
  providers.local.windows.json          # ignored；Windows profile，可覆盖 routing
```

路由策略本身不含 token，因此可以放在共享文件中。local 文件允许覆盖策略，是为了支持不同机器或个人工作流，但不允许把凭据、绝对用户目录或完整 CLI 输出放进 `routing`。

若后续策略规模显著扩大，再考虑独立的 `routing.shared.json`；本次不引入新文件类型，避免 bootstrap、迁移工具和文档再增加一套配置入口。

### 3.2 推荐 schema

```json
{
  "schema_version": 1,
  "routing": {
    "schema_version": 1,
    "default": {
      "strategy": "fair_round_robin"
    },
    "task_overrides": {
      "code:execute": {
        "strategy": "weighted_round_robin",
        "weights": {
          "deepseek": 2,
          "mimo": 1
        }
      },
      "research:analyze": {
        "strategy": "fixed",
        "provider": "mimo"
      }
    }
  },
  "providers": {
    "deepseek": {
      "config_dir_relative_to_home": ".claude-deepseek",
      "launcher": "claude",
      "environment": {
        "ANTHROPIC_BASE_URL": "https://provider.example/anthropic",
        "ANTHROPIC_MODEL": "provider-model"
      }
    },
    "mimo": {
      "config_dir_relative_to_home": ".claude-mimo",
      "launcher": "claude",
      "environment": {
        "ANTHROPIC_BASE_URL": "https://provider.example/anthropic",
        "ANTHROPIC_MODEL": "provider-model"
      }
    }
  }
}
```

字段定义：

|字段|类型|必需|说明|
|---|---|---:|---|
|`routing.schema_version`|正整数|否|缺省按 `1` 解析；不支持的版本在调用前拒绝|
|`routing.default.strategy`|枚举|是（有 `routing` 时）|`fair_round_robin`、`fixed` 或 `weighted_round_robin`|
|`routing.default.provider`|字符串|仅 `fixed`|必须是配置中的 provider key|
|`routing.default.weights`|对象|仅 `weighted_round_robin`|provider key 到正整数权重|
|`routing.task_overrides`|对象|否|键为精确的 `task_type:mode`，值使用同一 policy schema|
|`providers`|对象|是|现有 provider profile 定义|

### 3.3 配置合并顺序

路由配置沿用现有 profile 的平台覆盖原则，但以明确的深合并规则处理：

```text
shared.routing
  -> shared.routing.platform_overrides[host_platform]（如启用）
  -> providers.local.json.routing
  -> providers.local.<host_platform>.json.routing
```

合并规则：

- `default` 是对象级覆盖；local 文件提供 `strategy` 时覆盖 shared 默认；
- `task_overrides` 按 task key 合并，local 对某一个 task key 的字段覆盖 shared 同一 key；
- `weights` 按 provider key 合并，但最终必须重新校验所有值；
- 不允许用 `null` 隐式删除策略；需要删除一个 override 时使用显式 `disabled: true`，或在后续 schema 中定义删除语义；MVP 先不支持删除，避免平台文件差异难以诊断；
- provider profile 的合并规则保持现有 `environment` 字段深合并，其余字段覆盖。

如果只想在当前机器临时使用某家 provider，应优先使用命令行 `--provider`，不要为了临时实验修改共享策略。

### 3.4 校验规则

配置加载和 provider 调用必须分为两步：先完整解析并校验，再进行 trust/health/CLI 调用。以下任一项失败都应返回本地诊断，不得静默回退到另一策略：

- `routing` 不是对象；
- `schema_version` 不支持；
- `strategy` 不在允许枚举中；
- `fixed.provider` 不是非空字符串；
- `weights` 不是对象，权重不是正整数，或权重总和超过实现上限；
- `task_overrides` 的 key 不是已知 `task_type:mode`，或值不是 policy 对象；
- `fixed` / `weighted_round_robin` 引用了不存在的 provider；
- 配置只剩零权重或没有任何可用候选；
- platform overlay 解析后产生冲突且无法确定性合并。

建议第一版将单个权重限制在 `1..100`，总权重限制在 `1..1000`。这足以表达常见的 70/30、2/1、5/3/2，同时避免生成过大状态或误配置造成整数异常。

### 3.5 策略选择优先级

对一次 Claude Code 调用，最终顺序为：

```text
显式 session key
  > 用户显式 provider
  > 同主题唯一 active session
  > task_overrides[task_type:mode]
  > routing.default
  > fair_round_robin（缺省兼容）
```

在 policy 得出主选 provider 后，再执行：

```text
trust/profile readiness
  -> provider health/cooldown
  -> primary provider invocation
  -> availability-only one-time failover（必要时）
```

这意味着配置不能绕过显式 session、trust、health、权限或完成性检查。

## 4. 路由算法设计

### 4.1 `fair_round_robin`

保持现有可观察语义：

1. 候选 provider 先按 provider key 稳定排序；
2. 使用 `task_type:mode` 作为逻辑桶；
3. 从持久化 cursor 位置选择一个 provider；
4. 选择成功后 cursor 加一；
5. provider health 已打开时不加入当前候选；
6. 用户指定、session 恢复和 failover 不改变普通新主题的优先级规则。

未来实现中不要把 provider 名称排序解释成质量排序。排序只用于保证相同状态下的确定性起点。

### 4.2 `fixed`

`fixed` 表示正常新主题的固定主选：

- 目标 provider 已配置、已信任、profile ready 且未处于 health cooldown 时直接选择；
- 目标 provider 在调用前已经处于 cooldown 时，不静默改用另一家，返回 `fixed_provider_unavailable` 和可操作的冷却信息；
- 目标 provider 在本次真实调用中返回可识别 availability failure 时，沿用现有一次性 failover，备用 provider 不复用原 session ID；
- 用户显式指定另一 provider 时，配置 fixed 不得覆盖用户选择；
- `fixed` 不影响 Claude Code 内部模型映射，也不携带 `--model`。

这样既能表达“平时固定用 MiMo”，又不把固定偏好误变成无限重试或绕过可用性保护。

### 4.3 `weighted_round_robin`

第一版采用确定性的 smooth weighted round-robin：

```text
for each eligible provider:
    current[provider] += configured_weight[provider]

selected = provider with maximum current[provider]
tie-break = stable provider key ordering
current[selected] -= sum(configured_weight)
```

性质：

- 不使用随机数；
- 长期调用比例接近配置权重；
- 短窗口内不会因为随机抖动产生不可复现结果；
- 每个 `task_type:mode + policy fingerprint + candidate signature` 使用独立状态；
- provider 暂时不健康时，只在当前选择中排除；重新恢复后的状态策略要有测试覆盖；
- failover 不复用主选择的权重策略，而使用独立的 availability fallback 规则，避免权重配置阻止可用性恢复。

如果后续需要“每三次严格两次 DeepSeek、一 次 MiMo”的周期序列，可在不改变配置 schema 的情况下替换算法实现，并保留策略名称和状态迁移规则。

### 4.4 候选 provider 的定义

正常路由候选必须同时满足：

- 出现在已加载的 provider profiles；
- 有当前匹配的 trusted profile fingerprint；
- profile readiness 检查通过；
- 未处于 provider health cooldown；
- 没有被当前 policy 的 weight 排除。

对于 failover，仍使用现有的另一健康 provider 集合，而不是只使用当前 primary policy 中的 provider。这样即使 fixed/weighted 主策略配置错误或过窄，也不会破坏一次可用性兜底。

## 5. 运行时状态与迁移

### 5.1 状态分层

|文件|职责|本次是否改变|
|---|---|---|
|`providers.*.json`|静态 provider profile 和 routing policy|新增 `routing` 读取/校验|
|`trusted-providers.local.json`|当前非敏感 profile fingerprint 信任门|不改变；不纳入 routing policy|
|`provider-health.json`|availability cooldown、失败类别、重试时间|不改变；继续独立于 policy|
|`provider-metrics.json`|事件审计、质量/采纳指标、路由状态|增加策略命名空间和 weighted state|
|`sessions.json` / `topics.json`|session 与 topic 绑定|不改变；policy 变更不迁移已有 session|
|`topics/<topic>.md`|活跃主题一页状态|不写入完整配置或模型输出|

### 5.2 `provider-metrics.json` 状态设计

保留现有字段以兼容旧 runtime，并新增逻辑状态：

```json
{
  "schema_version": 2,
  "round_robin_cursor": {
    "code:execute": 4
  },
  "routing_state": {
    "fair_round_robin|code:execute|candidate-hash": {
      "cursor": 4
    },
    "weighted_round_robin|code:execute|policy-hash|candidate-hash": {
      "current_weights": {
        "deepseek": 1,
        "mimo": -1
      }
    }
  },
  "events": []
}
```

实现约束：

- `policy-hash` 和 `candidate-hash` 只由策略类型、provider key、权重、task key 等非敏感值计算；不得包含 token、endpoint query、绝对用户路径或 prompt；
- 旧 `round_robin_cursor` 在缺少 `routing_state` 时继续作为默认 fair cursor 使用；
- 首次写入新 schema 时可惰性迁移，不要求一次性改写所有旧 runtime；
- policy、权重或候选集合变化时使用新的 state key，避免新旧策略共享 cursor；
- 状态损坏时只丢失 cursor 并从确定性初始状态重建，不阻断配置加载；
- 事件仍只保留允许的脱敏元数据。

### 5.3 session 连续性

策略配置变化不迁移旧 session：

- 已有 active session 仍按其绑定 provider 恢复；
- 新主题使用新 policy；
- provider failover 必须新建目标 provider session；
- 不把 `model_profile` 从一个 provider 改写成另一个 provider；
- 如果用户希望在同一主题采用新策略，应显式 archive/新建 session 或通过新的 topic 触发，不由配置热变更暗中迁移。

### 5.4 配置变更与 trust fingerprint

路由策略不是 provider profile 身份，不应让普通权重调整使 provider trust 失效。只有 endpoint、认证方式、模型映射、配置目录、launcher 或受 fingerprint 保护的非敏感环境变化时，才刷新 trust record。

配置 loader 可以在诊断输出中显示当前策略名称和来源文件，但不能显示 token、完整 local profile 或绝对私有路径。

## 6. 代码实施设计

### 6.1 `profile_support.py`

新增独立的 routing loader/validator，避免继续让 `provider_map()` 默默忽略顶层字段：

- `routing_config(data, source_name)`：提取顶层 `routing`；
- `validate_routing_policy(policy, provider_keys)`：校验 schema、策略、权重和 provider 引用；
- `merge_routing(base, overlay, platform)`：按约定做对象级、task override 和 weights 合并；
- `load_routing(control_root)`：按 shared、platform override、local、platform local 顺序返回已解析配置；
- `load_profiles(control_root)` 保持现有调用兼容，不把 routing 混入 provider map；
- legacy flat local profile 仍可加载，但如果无法区分顶层 provider key 与 `routing`，返回明确迁移诊断，不猜测。

### 6.2 `provider_routing.py`

将路由职责集中在一个模块：

- 定义 policy 数据结构和策略常量；
- `resolve_policy(config, task_type, mode)`：task override 优先，否则 default，否则 fair；
- 候选集由 `collaborate.py` / `batch_worker.py` 在进入 resolver 前统一应用 provider trust、readiness 和 health 过滤；`provider_routing.py` 只接收已经过安全筛选的候选 provider，不重复读取凭据或 health 状态；
- `choose_fair(...)`、`choose_fixed(...)`、`choose_weighted(...)`：实现三个策略；
- `choose_provider(...)`：保留旧调用签名的兼容包装，默认调用 fair，逐步把新调用迁到显式 policy 参数；
- `route_basis` 增加可审计值，例如 `configured_fixed`、`configured_weighted_rotation`、`configured_default_fair_rotation`；
- failover 选择单独使用 `availability_failover` basis，不把用户的 primary policy 误记录成 failover policy。

### 6.3 `collaborate.py`

主流程修改为：

1. 加载 profiles、routing config、trust、metrics、health；
2. 在任何 provider CLI 调用前校验 routing config；
3. `select_provider()` 接收 routing config；
4. 保持显式 session、用户指定 provider 和 exact active session 的优先级；
5. 新主题只把 policy 交给 `provider_routing`；
6. 初始 profile readiness failure 仍只在 auto 模式走现有 configuration availability 处理；
7. CLI availability failure 的一次 failover 仍使用独立的 fallback candidate 规则；
8. 将 `route_basis`、policy 名称、task key、candidate count 写入 compact log，但不写完整配置、credential 或 prompt。

### 6.4 `batch_worker.py`

实施前的批处理 worker 曾直接调用 fair `choose_provider()`，会造成“普通调用按配置、batch 仍按公平轮换”的隐性分叉。当前实现已改为使用同一 routing config resolver，并由 `select_provider()` 统一覆盖：

- `--provider auto` 使用当前 routing default 或 `data:analyze` override；
- `--provider <key>` 仍然是显式覆盖；
- batch worker 不自行实现第二套路由算法；
- batch 的 provider health 和错误记录沿用主 runner 规则，或明确保持 read-only worker 的现有边界并在文档中说明。

### 6.5 `route_harness.py` 与 Antigravity

`route_harness.py` 的 provider policy 不应参与 harness 选择：

- harness router 先决定 Claude Code / Antigravity；
- 只有进入 Claude Code project-collaborator role 后，才读取 DeepSeek/MiMo routing；
- Antigravity 的 profile、conversation、trust、health 和 policy 状态继续独立；
- 不新增“把 Antigravity 作为 weighted provider”的配置语义。

## 7. 命令行与诊断行为

### 7.1 保留现有单次覆盖

不新增必须学习的复杂 CLI 参数。现有用法继续有效：

```text
--provider deepseek   # 当前调用固定指定 DeepSeek
--provider mimo       # 当前调用固定指定 MiMo
--provider auto        # 使用配置策略
```

如果未来需要调试某一个 policy，可以增加只读诊断命令，而不是增加会改变生产状态的 runner 参数：

```text
doctor.py --routing --json
```

该命令只显示：配置来源、解析后的策略名、task override 是否命中、候选 provider key、校验错误类别和当前 health 摘要；不得打印认证字段。

### 7.2 错误类别

建议新增或统一以下本地诊断类别：

- `routing_config_invalid`：JSON/schema/策略不合法；
- `routing_provider_unknown`：策略引用不存在 provider；
- `fixed_provider_unavailable`：fixed provider 在调用前处于 cooldown 或 profile 不 ready；
- `routing_no_healthy_candidate`：策略经过 health/trust 筛选后无候选；
- `routing_state_rebuilt`：runtime state 损坏后恢复初始状态，不作为 provider failure；
- `availability_failover`：真实可用性故障后发生一次切换。

配置错误不是 provider availability failure，不得自动换 provider 重试。

## 8. 兼容、迁移和回滚

### 8.1 向后兼容

旧配置无需修改即可运行：

- `routing` 缺失等价于 `default.strategy = fair_round_robin`；
- 旧 `provider-metrics.json` 的 `round_robin_cursor` 继续可读；
- 旧 session、topic、health、capability 和 trust record 不迁移 provider；
- 旧 CLI 命令和 `--provider` 语义不变；
- 旧 batch manifest 不需要重建。

### 8.2 配置升级步骤

1. 先发布只读 validator 和测试，不改变默认路由；
2. 在 public shared example 中加入注释等价的示例字段；JSON 本身不放注释，使用同目录 Markdown 说明；
3. 用户可只增加 `routing.default.strategy`，不必填写完整 providers；
4. 当配置为空、损坏或未知版本时 fail-closed，并给出修复路径；
5. 观察至少一轮 macOS/Windows fake 路由和真实最小 read-only smoke 后，再允许 weighted/fixed 成为推荐配置；
6. 若出现问题，删除 `routing` 对象即可回到 fair default，不需恢复 provider profile 或删除 session。

### 8.3 回滚策略

分三层回滚：

- 配置回滚：删除或恢复 `routing`，自动回到 fair；
- 代码回滚：恢复 router policy adapter，保留旧 `choose_provider()` 兼容 wrapper；
- runtime 回滚：保留 `provider-metrics.json` 的旧 cursor 和事件，无法解析的新 `routing_state` 只清除状态，不删除 metrics event、session 或 health。

不使用 destructive `git reset`，不删除用户 local profile，不回滚 provider token，不修改全局 CC Switch 状态。

## 9. 测试设计

### 9.1 配置加载测试

在 `test_profile_support.py` 或新增 `test_routing_config.py` 覆盖：

- 缺少 `routing` 自动默认 fair；
- shared routing 能正常读取；
- local routing 覆盖 shared default；
- task override 按精确 `task_type:mode` 命中；
- macOS 与 Windows platform overlay 合并结果一致；
- weights 深合并后重新校验；
- 未知策略、未知 provider、零/负/小数/超大权重、未知 schema version 被拒绝；
- legacy flat provider profile 的兼容与歧义诊断；
- routing 配置不进入 provider trust fingerprint。

### 9.2 路由算法测试

扩展 `test_provider_routing.py`：

- 缺省 fair 的前两次选择与现有测试一致；
- fair 每个 task key 使用独立 cursor；
- fixed 只选择指定 provider；
- fixed provider 不在候选时返回明确错误；
- weighted `2:1` 在多个窗口的计数比例正确；
- 相同输入、相同状态得到完全相同序列；
- provider 候选排序改变不改变稳定 tie-break 语义；
- policy hash 或 candidate signature 改变时不污染旧 cursor；
- 状态损坏时重建且不丢事件；
- route basis 能区分 configured policy 和 availability failover。

### 9.3 主 runner 与 session 测试

扩展 `test_provider_health.py`、`test_session_lifecycle.py`、`test_harness_state.py`：

- 显式 provider 覆盖 routing；
- exact session 覆盖 routing；
- fixed 正常调用后仍可在 availability failure 时一次性 failover；
- fixed provider pre-call cooldown 不静默转到另一家；
- task/outcome/contract/scope/permission failure 不触发 failover；
- failover 不复用源 session ID；
- policy 变化不迁移旧 session；
- health/trust/capability 仍只绑定 Claude Code provider profile 和平台身份。

### 9.4 batch 与 harness 测试

- `test_batch_worker.py` 验证 auto batch 遵守 `data:analyze` policy；
- `--provider` 显式覆盖 batch routing；
- `test_route_harness.py` 验证 Antigravity 不进入 provider policy；
- batch、Claude Code、Antigravity 三条路径不会各自复制一套策略算法。

### 9.5 双平台验收

macOS：

```bash
python3 .agents/skills/external-agent-collaboration/scripts/test_profile_support.py
python3 .agents/skills/external-agent-collaboration/scripts/test_provider_routing.py
python3 .agents/skills/external-agent-collaboration/scripts/test_provider_health.py
python3 .agents/skills/external-agent-collaboration/scripts/test_batch_worker.py
python3 -m compileall .agents/skills/external-agent-collaboration/scripts
```

Windows PowerShell：

```powershell
py -3 .agents/skills/external-agent-collaboration/scripts/test_profile_support.py
py -3 .agents/skills/external-agent-collaboration/scripts/test_provider_routing.py
py -3 .agents/skills/external-agent-collaboration/scripts/test_provider_health.py
py -3 .agents/skills/external-agent-collaboration/scripts/test_batch_worker.py
py -3 -m compileall .agents/skills/external-agent-collaboration/scripts
```

Windows 不能以 Bash、POSIX 绝对路径或 macOS 的 `CLAUDE_CONFIG_DIR` 验证代替；应使用临时 Windows home、Windows platform local fixture 和 Python 解释器本身执行 schema/route 回归。策略 JSON 和算法语义是平台无关的，平台差异只在 profile 路径、launcher、shell 和本地认证诊断。

### 9.6 文档和敏感性检查

- `git diff --check`；
- 检查所有新增 JSON example 不含真实 token、绝对用户目录或 runtime output；
- `rg` 检查文档中的 `routing` schema、策略名和默认行为一致；
- 检查现有 README/AGENTS/PRD/技术方案没有把“规划中”写成“已实现”；
- 检查 `.ai-collaboration/` 清理后没有被 Git 误纳入版本控制。

## 10. 实施工作包与顺序

### P0：冻结设计和 fixtures

交付：

- 本文进入专题目录；
- `providers.shared.example.json` 增加最小 routing 示例；
- 定义 policy schema、错误类别和 state schema；
- 为 fair/fixed/weighted 准备本地 fake fixtures；
- 记录 macOS/Windows 影响。

门槛：旧配置未改变实际选择；fixture 不含 token。

### P1：配置 loader 与 validator

修改：

- `profile_support.py`；
- `test_profile_support.py`；
- `bootstrap.py`（仅在 example/初始化需要时）；
- `doctor.py`（加入 routing 诊断时）。

门槛：两端能够解析 shared/local/platform local，非法配置在 provider 调用前失败。

### P2：路由引擎和 runtime state

修改：

- `provider_routing.py`；
- `test_provider_routing.py`；
- `provider-metrics` 兼容读写；
- 必要的 compact route metadata。

门槛：三个策略 deterministic；旧 fair cursor 可继续工作；state 不含敏感数据。

### P3：主调用链和 batch 集成

修改：

- `collaborate.py`；
- `batch_worker.py`；
- health/session/failover 相关回归；
- 不修改 `route_harness.py` 的 harness/provider 边界。

门槛：显式 provider、session、health、一次 availability failover 和 outcome safety 全部保持原语义。

### P4：文档、跨平台和最小真实验证

同步：

- `README.md`、`README.zh.md`、`README.en.md`；
- `AGENTS.md`、`AGENTS.zh.md`；
- `docs/产品需求文档.md`；
- `docs/技术方案文档.md`；
- `docs/实施计划文档.md`；
- `docs/测试用例文档.md`；
- `docs/迭代记录.md`；
- 本专题入口和本设计文档。

验证：

- macOS 和 Windows fake/local 全量回归；
- 已配置且已信任 profile 的最小无敏感 read-only smoke，各平台最多一次，不把 smoke 当作策略质量结论；
- 真实 smoke 前检查最终 handoff，不读取或输出 credential。

### 10.1 建议提交拆分

为便于审查和回滚，建议拆成以下独立提交或等价变更批次：

1. `docs`: 本设计、示例和决策/专题导航；
2. `config`: loader、validator、fixtures；
3. `router`: policy algorithms、state、compatibility wrapper；
4. `integration`: collaborate、batch、diagnostics；
5. `tests`: 双平台回归和 acceptance matrix；
6. `docs`: 实施后把当前主文档和迭代记录改为已实现状态。

每批次都要做 `git diff --check`，实现批次还要跑对应 Python tests。不要把 ignored local profile、provider output、runtime logs、snapshot 或真实凭据放入任何提交。

## 11. 清理与本地运行态治理

`.ai-collaboration/` 不是 `docs/` 的替代品：

- `docs/` 是版本控制的项目事实、设计、决策、测试和实施历史；
- `.ai-collaboration/project-context.md`、`decisions.md`、`current-state.md`、topic state、session registry 是跨会话的本地控制面；
- `handoffs/`、`outputs/`、`logs/`、`snapshots/`、`batches/`、`reviews/` 是可重建的 runtime cache；
- `providers.local*`、trust、health、capability、metrics 是本机运行所需的 ignored state，不能按普通日志删除。

清理原则：

1. 先归档已完成 session，保留 session key 和非敏感摘要；
2. 只删除已完成任务的 handoff、output、log、snapshot、batch 临时产物；
3. 若 topic state 引用 output，删除 output 前要移除失效 evidence 引用，或保留最小可验证索引；
4. 不读取、移动或删除 token-bearing local profile；
5. 不删除 `sessions.json`、`topics.json`、health、capability、metrics 等仍被脚本读取的控制状态；
6. 优先使用 `maintain_runtime.py --days N` 的 dry-run；apply 前记录候选数量和字节数；
7. macOS 和 Windows 都应由同一 Python 脚本按 mtime/目录规则清理，不依赖 `rm -rf`、Bash glob 或平台特定删除命令。

## 12. 验收矩阵

|维度|验收条件|证据|
|---|---|---|
|旧配置|没有 `routing` 时行为与当前 fair 完全一致|routing compatibility tests|
|fixed|健康时固定主选；pre-call cooldown 有明确诊断；真实 availability failure 最多一次 fallback|routing/health tests|
|weighted|确定性序列，长期比例符合整数权重，配置变化不污染旧 state|algorithm tests|
|显式优先级|用户 provider 和 exact session 始终优先|session/runner tests|
|安全|非法配置、未信任 profile、健康熔断、权限/outcome 失败不会触发错误重试|safety/failover tests|
|模型职责|runner 不传 `--model`；内部模型映射仍由 profile 管理|adapter regression|
|harness 隔离|Antigravity 不进入 DeepSeek/MiMo routing pool|harness router tests|
|状态隐私|metrics/state/logs 不包含 token、prompt、完整输出或私有路径|schema/redaction checks|
|macOS|Python 回归、profile path、launcher 和最小 smoke 通过|macOS report|
|Windows|PowerShell/Python 回归、Windows path/fixture 和最小 smoke 通过|Windows report|
|回滚|删除 `routing` 即回到 fair；旧 runtime/session 不需迁移|rollback test|

## 13. 风险和待确认项

### 13.1 权重是否表达“调用次数”还是“成本比例”

本设计中的权重只表达调用次数比例，不表达 token 成本、延迟或质量比例。若以后要做成本加权或质量路由，必须增加新的策略类型和单独的 evidence/DEC，不应复用 `weighted_round_robin` 造成语义混淆。

### 13.2 fixed provider 在 pre-call cooldown 时是否自动找备用

本设计选择 fail-closed：fixed 目标在调用前已知不可用时不静默切换；只有一次真实 availability failure 才触发现有 fallback。这样更符合“固定主选”的可观察性和用户预期。若业务需要“固定优先、健康时自动备用”，应新增明确的 `fixed_with_fallback`，不能改变 `fixed` 的含义。

### 13.3 platform-specific policy 是否长期需要

首版允许 local/platform local 覆盖，但共享配置仍是推荐入口。若 macOS 与 Windows 的策略逐渐分叉，应补充一份决策记录和配置诊断，显示生效来源，避免用户误以为两端使用同一策略。

### 13.4 质量学习路由不在本次范围

当前 metrics 只供审计。启用质量学习前，至少需要：每个 task bucket 的最小样本、冷启动规则、异常值处理、provider health 与质量失败的区分、人工采纳偏差、回滚开关和两端一致的评估报告。本设计不预先承诺该功能。

## 14. 完成定义

本专题的“配置化路由”只有在以下条件全部满足后，才能从 proposed 改为 accepted/implemented：

1. 配置 schema、默认 fair 兼容和错误语义已实现；
2. fixed、weighted、fair 三种策略均有本地确定性测试；
3. 主 runner、batch worker、health failover 和 session continuity 使用同一个 routing engine；
4. macOS 和 Windows 的配置加载、路径隔离和回归均有证据；
5. README、AGENTS、PRD、技术方案、实施计划、测试用例和迭代记录已同步；
6. 真实 provider smoke 只证明已配置路径可调用，不把一次调用解释成 provider 质量证明；
7. 本地 runtime 清理不会删除凭据、trust、health、capability、metrics 或未完成 session；
8. `git diff --check`、敏感扫描和完整相关测试通过。
