# ALCOM 安装与更新：Yukino VRChat Agent

> **本页是 VPM 分发说明，不是 Unity 实机验收证明。** 受控编辑仍为预览版；首次只在临时工程验收。安装/更新软件从不代表给 Agent 开启修改权限。

## 添加到 ALCOM：只需配置一次

打开 **ALCOM → 软件包仓库 / Packages → 添加仓库 / Add Repository**，粘贴：

```text
https://raw.githubusercontent.com/YukinoStuki2/VRchat_Agent/vpm/index.json
```

预览确认仓库名 **Yukino VRChat Agent — ALCOM / VPM**、ID `com.yukino.vrchat-agent.vpm`，确认后添加。不同ALCOM语言/版本的按钮文案可能略有不同。VCC也可在设置→Packages→Add Repository添加同一URL。

这是JSON仓库地址，不是Git仓库地址或ZIP地址；不要填到Unity的Add package from git URL里。

之后进入目标工程的 **Manage Project / 管理项目**：

| 包 | VPM版本 | 用途 |
|---|---|---|
| VRChat Read-Only MCP Diagnostics | `0.1.2` | 只读诊断；不依赖编辑包 |
| VRChat Agent — Managed BlendShape Editing (Preview) | `0.1.0-preview.2` | 可选受控编辑；会依赖并安装只读包 `0.1.2` |
| Yukino Agent Connection Manager (Preview) | `0.1.0-preview.2` | Windows Unity 菜单连接管理；依赖前两包代码，但不授权编辑 |

**看不到编辑包时**：开启ALCOM的“显示预发行软件包 / Show Prerelease Packages”，再刷新仓库。只想使用只读诊断就不要开启或安装编辑包。预览版不会冒充稳定版。

## 首次安装：基础依赖只需另外处理一次

本仓库只提供我们自己的工具包，**不重新发布、自动安装或升级 Coplay MCP、Unity、VRChat SDK**。

必须先在Unity Package Manager → Add package from git URL 安装官方固定依赖：

```text
https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0
```

工程的 `Packages/manifest.json` 中要保留这个Git依赖。工具包的普通UPM依赖仍包含Coplay `10.2.0` 与 Unity Newtonsoft `3.0.2`；**VPM不会替你从Unity注册表找到未发布在该注册表的Coplay**。已安装匹配版本就不要再装一份。依赖/编译出错立即停止，不开放任意脚本工具补救。

## 已用Git URL或本地磁盘安装过我们的包

先保存并备份工程，只在副本/临时工程做第一次迁移：

1. 关闭Managed Editing权限窗口；停止本次专用受限入口和隧道。
2. 若已装受控编辑包，先通过Unity Package Manager **Remove**其旧Git/本地引用，再移除我们的旧只读包引用。
3. **只移除 `com.yukino.vrchat-managed-editing` 和 `com.yukino.vrchat-readonly-mcp` 的旧包引用**。不删除模型、场景、Assets目录，不移除Coplay、SDK或其他插件。
4. 关闭Unity编辑器，避免编辑器正在导入/编译时由外部管理器更换包。
5. 在ALCOM刷新目标项目并安装所需包。选择受控编辑包会带上只读依赖；不需要编辑就只装只读包。
6. 重新打开Unity，检查Console无新增编译错误、工具注册和默认关闭状态。确认同名包没有重复来源。

本包不设置 `legacyFolders`、`legacyFiles` 或 `legacyPackages`，**不会扫描并自动删除旧Assets或其它包**。若曾手动复制同名C#到Assets，不要盲删；先查清来源并备份。

## 以后更新

- ALCOM刷新仓库后，在对应包上选择新版本并点更新；不要为此更新整个工程的全部依赖。
- 更新前保存/备份并关闭Unity和本次连接，更新后检查编译与默认关闭。
- 只读和编辑包独立版本；相同版本的已发布ZIP/哈希不会替换，旧版继续保留。
- 新版编辑包如需不同只读版本，由明确的VPM依赖关系提示/解决。
- 包版本回退只能回退代码，**不会恢复已经改过的模型权重**；模型仍使用Undo、精确恢复或工程备份。

## Unity 菜单一键连接（可选新预览包）

在 ALCOM 显示预发行版本后，安装 **Yukino Agent Connection Manager (Preview)**。菜单 **Tools → Yukino → Agent Connection Manager**。

- 首次填写本机 Python 3.11+、uvx、OpenSSH 路径及服务器信息；密钥/ssh-agent与主机指纹需本机预先配置。
- 点击一键连接后依次启动固定版基础 MCP、Unity Connect、受限 Bridge 和 SSH；有明确停止、失败清理和端口冲突检查。
- 连接窗口关闭或退出会取消恢复；默认重编译后手动连接。新版可勾选默认关闭的同工程恢复选项，等待清理和空闲后仅恢复连接，权限不恢复。更新前先断开并关闭 Unity。
- **ALCOM 安装/更新本身仍不启动任何服务或隧道，不修改 Hermes，也不开放模型修改权限。** 本包将桥接脚本一起更新，只有 Unity 本地按钮能启动。
- 完整首次配置、安全边界和验收限制：[启动器 README](Packages~/com.yukino.vrchat-agent-launcher/README.md)。Windows / Unity 实机结果与管理机测试严格分开，尚未验收的能力不得当作稳定版。

## 保留手工启动方式（不安装连接管理包）

只安装原只读/受控编辑包时，Windows Bridge 和 SSH 仍需单独启动。下面是首批 VPM 分发的历史说明：

本轮VPM只改分发元数据与README，C#及.meta不变。受控入口与 `managed-v0.1.0-preview.1` 同一版本兼容。源码可从这个固定快照下载：

https://github.com/YukinoStuki2/VRchat_Agent/archive/refs/tags/vpm-0.1.0.zip

其中 `Tools~/managed_bridge/README.zh-CN.md` 是入口说明。**关闭旧28080→18081直通通路后才允许切换受限入口**，且首次仅开Preview；不得同时保留可绕过开关的通用MCP连接。

## 本轮验证范围

- VPM ZIP无额外顶层目录；包身份、SemVer、依赖、许可证、.meta和源码字节检查。
- 版本索引保留旧版本，ZIP下载指向固定Git标签，带 `zipSHA256`。
- 使用官方 `vrc-get 1.9.2` 在隔离HOME/XDG与**合成测试工程**验证仓库、安装、依赖、升级和校验；不运行Unity/C#。
- Windows ALCOM点击流程、Unity2022.3完整编译、真实模型、渲染/Undo仍待操作者验收。
- Git `main`、`v0.1.1`、`managed-v0.1.0-preview.1` 保持原样；不是把候选版宣布为正式模型编辑能力。

## 版本记录

### 连接管理预览 `0.1.0-preview.2`

新增默认关闭的导入/重编译后同工程连接恢复，等待清理与空闲、限时单次尝试，手动断开/关窗/退出取消，编辑权限永不恢复。修正临时无实例/读取超时误报 `PROJECT_CHANGED`。旧 `preview.1` ZIP、索引记录和标签保留不变。

### 连接管理预览 `0.1.0-preview.1`

新增独立 `com.yukino.vrchat-agent-launcher`，通过 `VPM~/build_launcher.py` 从独立审核清单追加，不重建或替换前两包。窗口、监督程序和固定受限 Bridge 同包更新。基础 Coplay 仍使用官方来源。

### VPM首批分发

- 只读 `0.1.2`：来自 `v0.1.1` 已审查只读源码，仅适配VPM元数据/README。
- 编辑 `0.1.0-preview.2`：来自 `managed-v0.1.0-preview.1` 已审查候选源码，仅适配VPM元数据/README并声明只读包依赖。
- Coplay继续使用官方Git版本，本轮不重新打包第三方基础插件。
- 仓库索引使用GitHub Raw公开静态托管，不需要GitHub账户、Token或安装器管理员权限。GitHub网络不可达时ALCOM也可能下载失败；不会静默切换不可信镜像。

## 发布者维护说明

1. 在独立分支完成新源码审查与本地测试，取得新的源码SHA256清单。
2. 为新包递增SemVer，并为分发设**全新的**Git标签；修改 `VPM~/build_repository.py` 的固定版本/标签参数。
3. `python3 'VPM~/build_repository.py' --output .`：保存旧版本索引，仅追加新版本；同版本内容/哈希变化会拒绝。
4. 运行 `python3 'Tests~/test_vpm_distribution.py' -v`，检查生成ZIP、依赖解析和安全边界，独立复审通过后再发布。
5. 先推送新资产标签并确认下载，再更新 `vpm` 索引分支；索引不得提前指向不存在的ZIP。保留所有旧标签/资产。
6. 从公开URL用隔离vrc-get重新添加仓库、安装、比对哈希，最后验证用户安装说明。

官方参考：[VPM包格式](https://vcc.docs.vrchat.com/vpm/packages)、[自建仓库索引](https://vcc.docs.vrchat.com/guides/create-listing)、[ALCOM](https://vrc-get.anatawa12.com/en/alcom)。
