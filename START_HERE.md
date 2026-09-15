# 从这里开始：受控捏脸候选版

**这是临时工程验收用候选源码，不是已在真实模型中验证的正式版。**
本包默认不授权；不会自行更改Hermes配置、隧道、模型、场景保存或VRChat上传。

## ZIP目录怎么选

- 根目录 `package.json` / `Editor/`：原只读v0.1.1，保持不变。
- **`Packages~/com.yukino.vrchat-managed-editing/package.json`**：本次可选编辑扩展，安装时选这个文件。
- `Tools~/managed_bridge/`：Windows本地受限入口，运行 `bridge.py`。不是Unity脚本，不要拖进Assets。
- `Tests~/Unity/`：临时项目的EditMode测试源码，不会随包自动运行。
- `Tests~/UNITY_ACCEPTANCE.md`：必须在真实Unity逐项验收的清单。
- `VERIFICATION.md`：哪些本地检查真实跑过、哪些没跑。
- `MANIFEST.json`：ZIP内各文件SHA256校验记录。

## 先验收，再碰原模型

1. 创建可丢弃的Unity **2022.3**临时工程；验证期间尽量只开这一个Unity实例，不让服务落到另一个工程。
2. 在 Package Manager 安装基础插件：
   `https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0`
3. 安装原只读扩展：
   `https://github.com/YukinoStuki2/VRchat_Agent.git#v0.1.1`
   若仓库读取不便，可用本ZIP根目录的 `package.json` 从磁盘安装同一只读源码；不要重复安装两份。
4. 将ZIP解压到长期保留的固定目录，通过 **Add package from disk** 选择
   **`Packages~/com.yukino.vrchat-managed-editing/package.json`**。
5. 等待编译。发现新错误时停止，把Console原文提供给巧克力；不要开放任意脚本工具来绕过问题。
6. 菜单应出现 **Window → VRChat Agent → Managed Editing**。打开后仍应显示 **CLOSED**。先不要开启Apply。
7. 启动基础MCP，保持原端口Windows回环 `127.0.0.1:18081`，服务需 `--project-scoped-tools`；Rescan后应直接注册12个只读＋5个受控名称。
8. 在Windows PowerShell切换到解压目录的 `Tools~/managed_bridge/`，运行：
   ```powershell
   py -3 bridge.py --upstream http://127.0.0.1:18081/mcp --listen 127.0.0.1 --port 18082
   ```
   Python需3.11或更新版本；该入口只用标准库。若缺Python，不要猜测运行成功，先安装/确认本机版本。
9. **关闭旧的直通原MCP隧道**，再按入口README建立到18082的新隧道；不能把两条同时留着。不要自行断开其它用途的SSH会话。两端都必须loopback，MCP不得直接公网暴露。
10. 工具握手、目标项目、拒绝通用写工具及只读状态验收后，先只开启**Preview**，测试隔离预览不改变源场景。
11. 临时模型完成应用/回读/Undo/精确恢复后，再备份真实工程并单独授权真实模型。原工程有未保存变化时先由本人处理，不让Agent替你保存。

受限入口使用管理机回环 `28082`；旧直通 `28080→18081` 必须关闭。原Hermes配置暂时仍是旧只读连接，不会由ZIP自动修改；切换配置应在主人完成本机安装及拓扑确认后再执行。

## 权限用法

- 主人拖入明确的源 `SkinnedMeshRenderer`，逐项选择BlendShape。
- `Preview`允许隔离预览；`Apply`允许源场景权重修改与受控精确恢复，二者独立。
- 先设置短授权时长和有限写次数，再按本地确认按钮。
- 巧克力只能提出精确方案；不能替主人勾权限、自动续期或扩大范围。
- 满意后也不会自动保存；场景保存、Prefab源覆盖、动画资产编辑、上传均不在本阶段权限内。
- 关闭开关会阻止新的源写入，不会自动把主人已接受的修改撤回。恢复由本人明确选择或在有效Apply范围内执行。
- 一次只支持一个源Renderer；眼睛/牙齿/睫毛分散多个Renderer的联动留后续阶段。

## 当前不该做的事

- 不要直接在唯一的正式模型上进行第一轮写入验收。
- 不要把受限入口和仍可访问的原始MCP直通通道并存。
- 不要以本地C#策略测试通过，推断Unity渲染、Undo、Prefab及运行态已通过。
- 不要因只有通用 `execute_custom_tool` 而开放它；当前入口会拒绝缺失直接命名工具的上游。
- 不要把只读包与编辑包混淆；原v0.1.1无需替换。

遇超时/断线先读状态，不自动重放写请求。全部临时测试结束后关闭受限入口和本次专用隧道，核对无监听/测试进程残留。
