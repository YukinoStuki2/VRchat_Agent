# Hermes 优先预览：ALCOM 安装与验收

本源与旧版 VPM 源独立，包名为 `com.yukino.vrchat-agent`，版本 `0.2.0-preview.1`。不是旧的 Connection Manager。这是供隔离工程验收的预览包，不是稳定发行；主审非独审，Windows 专项暂缓，真实 Unity/模型尚未验收。

## 添加预览源

在 ALCOM 的软件包仓库页面选择添加仓库，粘贴：

`https://github.com/YukinoStuki2/VRchat_Agent/releases/download/hermes-preview-0.2.0-preview.1/index.json`

确认仓库名 **Yukino VRChat Agent — Hermes 优先预览**。开启“显示预发行软件包”，然后进入独立测试工程的管理页面，选择 **Yukino VRChat Agent（Hermes 优先预览）**，版本 **0.2.0-preview.1**。

## 首次安装顺序

1. 使用独立 Windows x64 测试工程或自己已备份的副本；不要直接在现用 Avatar 工程尝试。保留项目当前受支持的 Unity/VRChat SDK，不为安装本包升级整套工程。本包声明 Unity 2022.3。
2. 在 Unity Package Manager 中先安装官方固定 Coplay 包：`https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0`。已有匹配版本不重复安装；其他版本先停止核对，不能盲目覆盖。
3. 当前候选还依赖 Unity Newtonsoft JSON **3.0.2** 和 Unity Test Framework **1.1.31**。若工程版本冲突，先停止并记录，不擅自升级/降级已有依赖。ALCOM 的包文件安装通过不等于 Unity 已解析这些 UPM 依赖。
4. Windows 应具备微软官方 Visual C++ v14 **x64** 运行库：`https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist`。缺失时由本人从微软安装；本包不附带 DLL，也不自动安装系统组件。
5. 关闭 Unity。在 ALCOM 添加上述源、启用预发行显示、安装本包。不要同时安装旧 `com.yukino.vrchat-readonly-mcp`、`com.yukino.vrchat-managed-editing`、`com.yukino.vrchat-agent-launcher` 来混用两条接入路径。本候选不会删除它们；建议用无这些旧包的新工程测试。
6. 重新打开 Unity，先只检查导入/Console 与权限窗口默认关闭。不启用任意写入；编译错误保留原文，不清 Console，不自动回退或删除模型。

## 验收范围

- 本包安装、更新和打开窗口不会自动启动连接或批准任务。四类实时读取、单文件修改及每张图片预览均仍受本地开关/插件信任/任务批准约束。
- 真实 Unity 的编译、域重载、界面、撤回，以及 Windows ALCOM 点击操作，须由操作者实际验收。Linux 上的 vrc-get 分发检查不是这些结果。
- Hermes 插件另见同一 Release 的 `vrchat-agent-hermes-0.2.0-preview.1.zip`，不由 ALCOM 安装到服务器。插件按内含 INSTALL.md 正常扫描安装，保持默认关闭。本次分发不会更改现用 Hermes。
- 当前图片出口只支持 Linux pidfd＋HTTPS Chat＋静态内存 Bearer＋已识别原生直连 HTTPX；代理、凭据池、Responses/Codex OAuth 等拒绝，不会静默换路。真实模型调用另行确认。
- 功能是包内明确支持的子集，不是上游全部能力。未开放操作会拒绝；不保存场景、不上传 Avatar、不授予任意代码执行。

## 版本、来源与退出

- SHA256SUMS.json 和 index.json 随 Release 提供；同版本文件不覆盖。
- 此 Git 分支仅承载预览分发输入和工作流；当前候选源码在包内 Editor/ 与 Runtime~/ 中。不会用分支自动生成的 Source code ZIP 冒充 Unity 安装包。
- Runtime 字节复用固定 `14aea85f6703e8aa48270c79ead29fa18ce1e0ab` 的已核开发载荷。新增分发工作流不运行 Windows 测试、Unity 或模型。
- 若需要卸载，先本地停止连接、关闭 Unity，再由 ALCOM 移除此候选包。卸载代码不等于恢复已修改资产；备份和精确撤回保持原策略，不自动清除。
