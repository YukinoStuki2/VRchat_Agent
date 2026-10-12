# Hermes 优先预览：Coplay 自动依赖修正版

包 `com.yukino.vrchat-agent@0.2.0-preview.2`。此版本只修复 ALCOM/VPM 首次安装缺少 Coplay 的分发问题，不改变 Agent 功能源码、运行时或 Hermes 插件。仍是独立工程验收用预览，不是稳定发行；既有功能审查为主审非独审，Windows 专项暂缓，真实 Unity/模型尚未验收。

## 添加修正版预览源

在 ALCOM 软件包仓库页面添加：

`https://github.com/YukinoStuki2/VRchat_Agent/releases/download/hermes-preview-0.2.0-preview.2/index.json`

仓库名：**Yukino VRChat Agent — Hermes 预览（自动依赖）**。它与旧预览源 ID 不同，可以并存；旧地址固定在 preview.1，不会自己出现本次修复。开启“显示预发行软件包”。

## 新工程安装／缺依赖报错修复

1. 使用独立 Windows x64 测试工程或自己已备份的副本；保留当前受支持的 Unity/VRChat SDK，不升级整套工程。本包声明 Unity 2022.3。
2. 关闭 Unity。在 ALCOM 安装本包 **0.2.0-preview.2**；已装 preview.1 的测试工程直接更新，不必卸载模型或清空 Library。
3. 安装确认清单应同时包含 **MCP for Unity 10.2.0**。确认后 ALCOM 自动下载并安装依赖，再打开 Unity。不需要手动添加 Coplay Git URL，不需要为这条依赖安装本机 Git。
4. 如果清单没有 Coplay 或下载失败，先停留在 ALCOM 解决，不要带着不完整安装继续开工程。该方案不是隐藏依赖错误：它在 Unity 启动前实际补齐包。
5. Unity 自带模块、Newtonsoft JSON **3.0.2** 和 Test Framework **1.1.31** 仍由 Unity UPM 解析，需能访问对应包源。版本冲突先停下核对，不盲目升级／降级。
6. 重新打开 Unity，先检查 Console 和 **Tools → VRChat Agent → 候选权限与清单**。不清除错误、不自动保存场景，先不要启用写入。

## 已有 Coplay 的工程：先看安装变更清单

- 本依赖固定为 **10.2.0**，不会自动追随上游最新版。保留上游包 ID、代码和 `.meta` GUID；不是另造一个重名程序集。
- Git／磁盘／手动嵌入安装不等于 VPM 已管理。已有这些安装，或使用其他 Coplay 版本／自改内容的工程，**不要直接确认迁移或替换**；先记录版本、来源、备份并核对。本修复优先支持原本没有 Coplay 的新工程。
- 尤其 Git 引用仍存在时，VPM 的同名嵌入包会优先于它被 Unity 使用；不是“两份都加载”，也不是旧 Git 设置已删除。不要把清单不变当作有效代码版本不变。
- 不混装旧 `com.yukino.vrchat-readonly-mcp`、`com.yukino.vrchat-managed-editing`、`com.yukino.vrchat-agent-launcher`；本候选不删除它们。

## 范围与前置

- 本次没有新增 Unity 后台安装器、自动重试安装、自动连接或默认编辑权限。Coplay 10.2.0 上游自身的 Editor 初始化行为原样保留，不能把我们的权限门当作上游插件的全局沙箱。不要另开 Coplay 的直接 AI 控制通道来绕过本地权限。
- Windows 仍需微软官方 Visual C++ v14 **x64** 运行库：<https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist>。由本人安装，本包不附带系统 DLL／安装器。
- Hermes 插件仍为本 Release 附带的 `vrchat-agent-hermes-0.2.0-preview.1.zip`，字节与前版相同，不由 ALCOM 安装到服务器。遵循内含 INSTALL.md 正常扫描安装、默认关闭；本次不改现用 Hermes。
- 图片出口仍限 Linux pidfd＋HTTPS Chat＋静态内存 Bearer＋已识别原生直连 HTTPX；不支持的代理、凭据池、Responses/Codex OAuth 等保持拒绝。真实模型调用另行确认。
- 新工程依赖安装、版本锁及文件完整性用官方 vrc-get 实际验证；这不等于 Windows ALCOM GUI、Unity 编译／重载或真实模型验收。

## Coplay 来源和许可证

Coplay 源码固定于上游 v10.2.0 对应提交：

`30d22075093d1d35dfb0091c1c7550e9ad948577`

来源：<https://github.com/CoplayDev/unity-mcp/tree/30d22075093d1d35dfb0091c1c7550e9ad948577/MCPForUnity>

这是 Yukino 为依赖安装制作的 **非官方 VPM 分发**，不冒称上游发布或背书。原始包文件除 `package.json` 分发字段外均保持字节不变；包内新增上游 MIT LICENSE 和分发说明，保留原作者信息及 GUID。`coplay-provenance.json` 记录来源归档、原始和分发成员摘要；`SHA256SUMS.json` 记录 Release 资产摘要。

## 卸载与未验收项

先本地停止连接、关闭 Unity，再由 ALCOM 查看并确认移除计划。Coplay 是依赖包，ALCOM/VPM 可能随主包清理不再使用的依赖；已有独立用途的工程必须先检查计划。不会自动恢复已修改 Avatar、删除备份或保存场景。

只新增独立分支、标签和非 latest 预览 Release。旧源、旧版本、main 不变。真实 Unity 首次导入、编译和窗口仍需操作者实测，不将包管理器成功当作完整产品验收。
