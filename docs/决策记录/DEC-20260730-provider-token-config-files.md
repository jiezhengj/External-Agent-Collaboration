# DEC-20260730-provider-token-config-files

状态：accepted
日期：2026-07-30

## 上下文

项目起始实现使用 Git 忽略的 `providers.local.json` 直接保存 provider token。后续跨平台兼容性工作曾将环境变量、macOS Keychain 和 Windows Credential Manager 作为推荐迁移方向，但这改变了用户已明确选择的工作方式：token 应可直接在配置文件中查看、编辑并由用户的私有同步方案管理。

## 决策

Git 忽略的配置文件是 provider token 的默认且唯一要求载体。

- 支持通用 `providers.local.json`。
- 支持并推荐平台专属 `providers.local.macos.json` 与 `providers.local.windows.json`，以容纳不同的 launcher、配置目录和直接 `auth_token`。
- 用户自行决定是否同步这些私有文件；项目不假定或限制其同步机制。
- 不要求、不默认使用、也不自动迁移至环境变量、Keychain、Credential Manager 或其他系统凭据库。

无论用户怎样同步配置，token 都不得写入 Git、handoff、输出、日志、测试 fixture 或外部提示词。

## 备选方案

1. 环境变量：易于进程注入，但不符合用户直接编辑配置文件的偏好。
2. macOS Keychain + Windows Credential Manager：系统级存储能力强，但增加平台差异、迁移步骤和不可见状态。
3. 单份无凭据 portable profile：可减少路径差异，但不能满足用户直接管理 token 的需求。

## 后果

加载器必须优先支持平台 local profile 的直接 token；诊断、信任 fingerprint、示例和测试以该模式为基线。旧系统凭据适配仅可作为显式兼容能力，不得成为文档推荐或自动行为。

## 受影响文档与证据

- [产品需求文档](../产品需求文档.md)
- [技术方案文档](../技术方案文档.md)
- [实施计划文档](../实施计划文档.md)
- [测试用例文档](../测试用例文档.md)
- [迭代记录](../迭代记录.md)

后续以平台 local profile 回归与脱敏检查作为实现证据。

macOS 接手步骤与 Windows 当前状态见 [Provider 配置文件与 macOS 迁移交接专题](../专题/2026-07-30-provider-config-files/README.md)。
