# VRChat Agent：受控 BlendShape 编辑候选包

**阶段一候选版 `0.1.0-preview.1`。不是已在你的 Unity 工程中验收的正式版。**

这是可选编辑扩展，不替换 `com.yukino.vrchat-readonly-mcp`。原只读工具继续只读。
当前仅支持一个明确选中的 `SkinnedMeshRenderer`；多个脸部/睫毛/牙齿 Renderer 的联动和材质、服装、动画等类别留到后续分阶段实现。

## 开关到底限制什么

本地 Unity 菜单 `Window → VRChat Agent → Managed Editing`：

- 选择场景中的具体 Renderer，再逐项勾选精确 BlendShape 名称；不能仅因为物体叫 Body 就把整个身体授权。
- `Preview` 和 `Apply` 分开，默认关闭。预览只创建隔离临时对象和图像；应用修改原场景实例的 BlendShape 权重。
- 授权时长上限15分钟、写入次数上限100；默认短期额度由面板显示，不提供无限授权。
- 开启 Apply 前，本人确认已保存并建立可恢复备份；场景已有未保存修改时拒绝开启。
- 关闭面板、脚本重载、进入/退出播放、场景新建/开启/关闭/保存、已加载场景间切换活动场景、到期后锁定（自身隔离预览场景除外）。Agent 没有解锁/续期/授权接口。
- 计划到期时间最多120秒。旧授权的计划无效。每次操作仍同步核对对象、Mesh、权限和原值。
- 权限关闭不等于撤销已接受的源模型修改；不会偷偷把主人刚调好的脸清零。隔离预览会清理；源修改需本人明确 Undo 或恢复。

## 必须同时部署受限入口

**不能只安装本包，然后继续把原始 Coplay 通用 MCP 端口转发给 Agent。**
原始服务仍有组件、脚本等通用写入口，能够绕过本包的授权检查。Hermes 的工具名单只是额外过滤，不是该问题的完整安全边界。

部署目标：

```text
Hermes → SSH反向隧道 → Windows 127.0.0.1:18082 受限入口
                                      ↓
                      Windows 127.0.0.1:18081 原始Unity MCP
```

仓库/交付包 `Tools~/managed_bridge/` 中提供单独前端程序及说明。**原始18081只保留Windows本机回环，旧的直通隧道必须先关闭，不能同时留下另一条直通转发。**
前端不允许任意执行、通用组件/文件修改、批处理、菜单执行、测试运行或上传。权限仍由每个编辑器中的本地面板决定。

面板的部署与备份勾选是本人的确认，不是插件已经自动验证网络/备份。启用前应实际检查隧道目标、上游可达路径和拒绝测试。具备Windows本机管理员/任意代码执行权限的程序不在这个防误操作边界内。

## 候选包安装（先用临时测试工程）

1. 使用与原工程匹配的 Unity `2022.3`，准备临时空白测试工程。不要把首轮测试直接放在唯一的原模型工程里。
2. **先安装两个固定依赖，再安装可选编辑包**：Coplay `https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0`，然后原只读包 `https://github.com/YukinoStuki2/VRchat_Agent.git#v0.1.1`。新建临时工程不能跳过只读包；受限入口要求12项只读工具和5项受控工具，共17个精确名称。
3. 下载交付ZIP并解压到长期固定目录。在 Package Manager 选择 **Add package from disk**，选ZIP内的 `Packages~/com.yukino.vrchat-managed-editing/package.json`。不要复制C#到Assets，不要选择ZIP或根目录只读包的package.json。
4. 等待编译；如有错误，停止这里并提供Console原文。不要先放开通用写工具以“修复”。
5. MCP服务使用 `--project-scoped-tools`，Rescan 后应出现固定5项：
   `vrchat_me_status`、`vrchat_me_plan`、`vrchat_me_preview`、`vrchat_me_apply`、`vrchat_me_rollback`。
6. 按受限入口README启动前端、替换隧道并验收拒绝路径，再考虑将这5项加入Hermes明确名单。安装本包本身不会改Hermes配置、开监听或授权。
7. 本地小模型测试通过后，再备份真实工程，安装同一候选包，并由主人选择范围。

现有根包及已发布的v0.1.1保持不变。`Packages~` 使用Unity忽略目录隔离可选包；本阶段不覆盖原标签，不宣称已经GitHub发布。

## 实际工作流

1. 主人选源 Renderer、选形态，先只开 Preview；Agent读状态并给出精确名称/权重方案。
2. `plan` 只存内存中的方案和原值，不改源模型。
3. `preview` 在独立视图给出前后对照，支持近景/角度调整；可由受限入口把PNG转换为MCP原生图像，不将Base64作为大段文字喂给模型。
4. 满意后由主人保存/备份并开启Apply；新授权后重新生成方案（旧计划失效），Agent只能在新范围内应用。
5. 修改后立即逐项回读；Unity可用Undo撤销。工具不会自动保存场景、覆盖Prefab资产或创建动画文件。
6. `rollback`只恢复上一次本工具修改的精确字段，需要当前Apply授权；主人在本地面板可在授权关闭后主动恢复。若某个受影响字段已被手动改变，则整批拒绝恢复，避免覆盖人工编辑。

权重首版允许0–100；恢复原值不是归零，原本非零甚至范围外的原值会保留在恢复快照中。变更不修改Mesh本体，不能创造原模型不存在的脸型/拓扑。静态捏脸还可能被Animator、眨眼、口型、MA/NDMF等覆盖，需后续运行态验收，而不是擅自修改这些系统。

## 验收范围与限制

### Mesh 支持边界（刻意收窄，不是通用几何编辑）

仅接受 `Assets/` 或 `Packages/` 内由 `ModelImporter` 导入的、无隐藏标志且未脏的持久化 Mesh 子资产。运行时/临时Mesh、生成的 `.asset` Mesh、自定义导入器输出、脏Mesh/模型/导入器均拒绝；不能为了绕过拒绝把动态Mesh存成资产。源仍必须是已保存场景中的明确Renderer实例。

授权、计划、预览、应用及恢复检查身份、依赖哈希、`GetDirtyCount` 和导入版本；任何资产导入/删除/移动通知均保守撤权、清除计划/预览，并使旧恢复快照失效。闲时最多每0.5秒检查一次，每次操作同步检查，不逐帧扫描顶点、bindposes或数百形态的位移数组。

**This identity/version check is not a full native mesh content hash.** 支持范围要求导入资产在授权期间保持不可变。未被Unity脏标记/导入事件跟踪的本地任意C#/原生代码原地改写几何不受检测保证，属于可信本地操作者边界之外，不可宣称已防御。运行此类工具前必须 **revoke first**；完成后恢复/重新导入磁盘上的权威模型，再重新授权。不能只清除脏标记后继续用旧计划。原始MCP端口仍不得直通Agent。本限制及拒绝路径仍需在临时Unity工程实测。

见交付包 `VERIFICATION.md` 的实际执行结果。管理机可执行纯C#策略测试、Python真实本地HTTP边界测试、C#语法/源码边界检查；**这些不替代Unity API类型检查、渲染、Undo和Prefab序列化实测。**

`Tests~/Unity` 是供临时工程运行的EditMode测试源码（需Unity Test Framework），没有自动运行。正式授权原模型前还应完成 `UNITY_ACCEPTANCE.md`。

预览只显示所选Renderer，不自动克隆整个角色，也不运行角色脚本。不应把它理解为完整VRChat运行画面。中断后重新读状态，不盲目重放写请求。
