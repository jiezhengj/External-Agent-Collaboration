# 外部代理协作的 Token 与成本优化方案

## 1. 目标、边界与衡量口径

目标是在不降低任务验收质量的前提下，减少 Codex 为理解大本地材料、追踪长任务和读取重复结果所消耗的上下文；同时避免把节省的 Codex token 无限制地转移成更高的外部 token 和费用。

本方案分别记录四类指标，禁止只用“token 少了”做结论：

|指标|含义|优化方向|
|---|---|---|
|`codex_input_tokens`|进入 Codex 的用户、工具和文件内容|优先降低，尤其是工具返回的长文本。|
|`external_input_tokens` / `external_output_tokens`|外部 CLI/provider 消耗|控制重复读取和无用长输出。|
|`total_cost_usd`|所有可获得的实际费用|不能因迁移上下文而被掩盖。|
|质量|outcomes、测试、人工评分、采纳、返工|质量不下降是任何节省的前提。|

不追求把所有文件交给外部协作者，也不试图用 token 上限替代正确性验证。当前信息、连接器、富媒体/办公成品、敏感资料和简单任务仍保持原有原生或直接路径。

## 2. 当前实现的优势与缺口

现有执行器已经使外部协作者能够直接读取工作区文件；若 Codex 只传递简短 handoff，原文不必进入 Codex。expected outcomes、路径限制和本地验证也能让 Codex 用较小的状态结果判断任务是否成功。

但当前仍有四个 token 风险：

1. handoff 全文会直接拼入外部 prompt，未设置字节或 token 上限；
2. 外部 CLI 的完整 JSON result 被打印为执行器标准输出，长回答可能回流到 Codex；
3. 没有大文档的清单、分片、断点、汇总和按需读取协议；
4. 没有以“预计回传量相对输入量”为条件的硬路由规则。

因此，本方案先控制返回通道，再建设批处理；不先解决返回通道就不应把大规模材料自动委派。

## 3. 设计原则

- **材料留在磁盘，结论以索引返回。** 外部协作者读取本地路径，Codex 默认只接收 run ID、状态、统计、异常和少量抽样路径。
- **完整原始结果可留存，但不自动注入 Codex。** 原始 provider JSON 放到本地 ignored output；读取它必须是 Codex 的显式按需动作。
- **批次是可恢复的工作单元。** 每一批独立输入清单、输出 schema、校验状态和重试次数；不得把全部材料和全部结果堆入一个会话。
- **由验收而不是摘要决定成功。** 短返回只用于协调；文件、schema、测试和抽样检查继续承担质量证据。
- **按不确定性使用第二协作者。** 对异常批次、结论冲突或高风险样本审查；不让第二个协作者重读全部材料。
- **路由前估算回流比。** 只有预期回传显著小于待读材料且可落盘验证时，才把长材料任务交给外部协作者。

## 4. 返回通道：第一优先级

### 4.1 新的返回模式

为 `collaborate.py` 增加 `--return-mode`，默认 `compact`：

|模式|返回给 Codex|本地保存|
|---|---|---|
|`compact`（默认）|`run_id`、status、provider、变更路径、outcomes、固定长度 summary、风险计数和 output 文件路径|完整 CLI JSON 与完整文本。|
|`structured`|通过 schema 校验的小 JSON；每个字段设字符数/数组长度上限|完整 CLI JSON。|
|`file_only`|仅状态、路径与内容哈希；适合批处理 worker|完整结果与业务产物。|
|`debug`|完整 provider result；仅用户/ Codex 明确指定时使用|同上。|

`compact` 的总返回上限建议为 8 KiB；若外部结果超过限制，执行器保存完整结果，只返回截断标志、哈希与输出路径。截断不是成功或失败；outcomes 仍照常执行。

### 4.2 外部最终答复契约

在 prompt 中要求外部协作者将最终答复限制为固定 schema：

```json
{
  "summary": "最多 1,200 字符",
  "changed_files": ["最多 50 项"],
  "commands_run": ["最多 20 项"],
  "validation": [{"name": "...", "status": "passed|failed"}],
  "risks": ["最多 10 项"],
  "output_index": "project-relative path"
}
```

执行器对返回 schema/长度做本地校验。未满足时记录 `result_contract_failed`，但不覆盖已有的文件 outcomes；Codex 只收到紧凑错误说明与原始输出路径。

### 4.3 读取策略

Codex 默认不得自动打开 `.ai-collaboration/outputs/<run>.json`。只有出现以下条件才按需读取：outcome 失败、风险标记、用户要求原文、抽样复核、调试 provider 兼容性。大文件使用行号/JSON pointer/分页读取，不能整份重新塞入上下文。

## 5. 大批文档流水线

### 5.1 适用条件

适用于大量、非敏感、可在本地读取的文本/结构化文档，且每份文档可以产生较小的结构化结论，例如分类、字段提取、风险项、重复检测或索引。最终 `.docx`、PPT、表格和 PDF 成品仍走原生工具。

不适用于每份文档都需要 Codex 人工逐字审阅、资料不能发送给外部 provider、或任务没有可验证的单篇输出 schema 的场景。

### 5.2 四阶段协议

```text
清单与采样
  → 分片 worker
  → 本地 reducer
  → Codex 例外处理与抽样复核
```

1. **清单与采样**：本地 scanner 只生成路径、大小、hash、类型、敏感路径标记和可选分片 ID；先抽样验证解析规则和质量，不直接跑全量。
2. **分片 worker**：每批按可配置的“估计 token/文件数/字节数”上限执行。worker 只读取本批 manifest，写 `batch-<id>.jsonl`，每行含 source hash、schema version、status、短结论、证据位置和错误码。
3. **本地 reducer**：不调用模型地聚合数量、失败、重复 hash、字段完整率和异常清单，写 `index.json` 与 `summary.json`。
4. **Codex 例外处理**：Codex 只接收 reducer 的紧凑摘要。对失败、低置信度、冲突和随机样本按需打开结果或发起一次独立审查。

### 5.3 断点与幂等

- 单篇结果键为 `source_relative_path + source_hash + extraction_schema_version`；未变化文件跳过。
- 已完成 batch 不能因为重新启动而重新处理；失败批次单独重试，并保留失败原因。
- provider/session 变化只影响尚未处理批次；不得混淆已完成结果的 schema 版本。
- 每批返回 `file_only` 或 `structured`，不得在终端逐篇打印内容。

### 5.4 10,000 × 1 MB 示例

10 GB 输入不能使用当前 `execute` 的全项目快照模式。应使用只读 `document_batch` action：先建立 manifest，按估计 token 切成小批；worker 输出结构化 JSONL；reducer 输出总数、失败数、异常路径和抽样路径。若需要修改文档，应把写操作拆为小范围、可快照的独立 execute 批次，不能对 10 GB 根目录做一次快照。

## 6. 按工况的策略

|工况|默认路径|最小回传|质量措施|不应做的事|
|---|---|---|---|---|
|简单问答、短改写|Codex direct|无外部回传|直接检查|为求一致而外包。|
|实时事实、连接器、富媒体成品|Codex native|原生工具结果|来源/渲染验证|交给 CLI 记忆回答。|
|多文件代码修复|外部 execute|变更路径、tests、风险、outcomes|测试、diff 抽样、高风险时一次 critique|把完整源码/完整 CLI result 回传。|
|大型代码库理解|外部 consult 或 batch index|模块地图、依赖边、问题清单|抽样打开模块和关键证据|每轮重新通读整个仓库。|
|大量文本/数据文档|document_batch|总统计、异常、索引路径|schema、hash、抽样、失败重试|一次会话读完并逐篇输出。|
|长持续主题|持续 session + 状态摘要|delta、决策、未决项|归档/摘要版本化|每轮把历史 transcript 全量交接。|
|高风险执行|execute + 条件 critique|审查结论和证据路径|测试、outcomes、异常优先审查|两家完整重读所有材料。|
|创作多候选|有限候选并落盘|候选标题、差异、路径|用户/ Codex 选择|把所有草稿全文重复发回。|

## 7. 路由与预算规则

分类器增加以下输入和输出：

```json
{
  "estimated_input_bytes": 0,
  "estimated_return_bytes": 0,
  "return_ratio": 0.0,
  "batchable": false,
  "recommended_return_mode": "compact",
  "token_policy": "direct | delegate | batch | native | reject"
}
```

决策规则：

1. `native_codex`、`prohibited` 和小任务保持原规则。
2. 预计输入小且回传比高于阈值（建议 0.2）时，直接由 Codex 处理或要求缩小任务。
3. 预计输入大、回传比低于阈值且有结构化输出 schema 时，使用 `delegate` 或 `batch`。
4. 超过 execute 快照上限的任务禁止单次 execute；只读 batch 或拆分为独立小范围 execute。
5. provider 选择在预算允许范围内再比较质量、完成率、耗时和成本；质量样本不足时不因为理论低价而全量倾斜。
6. 高风险第二审查只在 outcomes 失败、风险评分超过阈值、抽样不一致或用户明确要求时启动。

预算不是硬编码模型 token 参数。执行器首先控制 handoff、返回、批大小和重试次数；provider 的实际 token/费用作为事后指标并用于下一次路由。

## 8. 可观测性与验收

新增 `token-metrics.json`，仅记录元数据：run ID、task type、action、文件数、输入字节估算、handoff 字节数、外部 result 字节数、返回给 Codex的字节数、return mode、批次状态、外部 usage/cost（可获得时）、outcomes、人工质量、返工。不得记录原文、prompt、token 或业务结论。

核心验收指标：

- 在同一质量阈值下，`compact` 模式的 Codex 工具返回字节数相较当前完整 result 至少下降 90%。
- 批处理任务中，Codex 不读取源文档总量的 1%；只读取异常和抽样结果。
- batch 中断恢复不重复处理 source hash 未变化的文件。
- 任何截断、schema 失败或 provider 错误都可定位完整本地输出，但不会自动把完整输出回传给 Codex。
- 高风险任务的测试/outcomes/抽样通过率不低于当前基线；若降低，停止扩大自动委派。

## 9. 实施顺序

### P0：防止结果回流（先做）

1. 增加 `return_mode`、紧凑 result schema 和长度限制。
2. 将完整 CLI JSON 从标准输出移到 ignored output 文件；标准输出只返回紧凑 envelope。
3. 增加 `--debug-full-result` 显式开关。
4. 为 handoff 与最终答复增加大小记录和测试。

### P1：建立批处理基础

1. 新增 manifest scanner、batch plan 和 JSONL result schema。
2. 新增本地 reducer、hash 幂等和失败清单。
3. 为只读 `document_batch` 增加 action；拒绝超过快照上限的单次 execute。
4. 提供小样本 dry-run 与质量抽样命令。

### P2：让路由考虑回流与成本

1. 扩展分类结果和 provider metrics。
2. 实现 return ratio、批量建议、预算上限和异常优先 review。
3. 用真实但非敏感的小规模数据校准分片阈值，不写死某一家模型能力。

### P3：长期优化

1. 基于已验证摘要生成/归档 session compact context。
2. 建立检索索引，使 Codex 和外部协作者按路径/段落按需读取。
3. 用采纳、返工、成本和质量数据复盘路由，而不是只追求 token 最小。

## 10. 风险与停止条件

- 若短返回使 Codex 无法独立验证关键结论，扩大返回 schema 或要求证据路径，而不是恢复全文回传。
- 若外部 token/费用增加超过 Codex 节约的价值，收紧委派范围或改为 direct/native。
- 若批处理抽样质量不达标，停止全量，修正 schema/prompt 后重新从小样本验证。
- 若材料含敏感信息、客户导出或无法安全发送的内容，禁止 batch 外部处理；不以 token 优化为理由绕过安全边界。
