# 决策记录

这里存放有长期取舍价值的短决策记录。主文档保持当前有效规则；决策记录说明为何采用某种规则、替代方案、影响范围和废止关系。

有独立讨论和实施周期的优化材料归入 `docs/专题/`，不与 DEC 混放。DEC 可链接专题入口；专题入口再链接对应 DEC、当前规范和实施证据。

命名：`DEC-YYYYMMDD-<slug>.md`。

每条记录至少包含：状态（proposed/accepted/superseded）、日期、上下文、决策、备选方案、后果、受影响主文档、实现/测试证据和后续替代记录（如有）。

- [DEC-20260729-provider-routing-failover](DEC-20260729-provider-routing-failover.md)：公平 provider 轮换、可用性熔断，以及 CC Switch 内部模型职责。
- [DEC-20260730-provider-token-config-files](DEC-20260730-provider-token-config-files.md)：配置文件直接 token、平台 local profile 与系统凭据库非默认原则。
