# VRChat Agent 未发布候选源码

此目录不是可安装成品，不要直接添加到真实Unity工程。完整实现、客户端接线、独立审查、运行时分发及集中验收尚未完成。

目标布局：Editor为候选程序集；OwnedTransport子目录的asmref仅将独立传输类型加入固定Coplay程序集；Runtime~包含受控sidecar源码与SDK修订，不交给Unity importer编译。打开窗口/导入本包不会启动服务或授予任务权限。

固定Coplay来源： https://github.com/CoplayDev/unity-mcp/tree/30d22075093d1d35dfb0091c1c7550e9ad948577 ，包版本10.2.0。这里不自动安装或更新它，不升级Unity/VRChat SDK，不移除旧包或工程文件。

已提供固定便携Python的构建及验真流程，但完整安装包尚未发布；入口不会启动时联网安装依赖；账号、令牌、JWT私钥不写文件。停止/撤权不自动回退用户资产。真实Unity/Mono的导入、窗口和生命周期尚未验收。


## Windows 前置运行库

Windows x64 候选要求预先安装微软官方 **Visual C++ v14 Redistributable（x64，当前受支持版本）**。
下载与安装说明：https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
由用户从微软官方页面手动安装；本包不附带安装器，不自动下载、不静默安装，也不修改已有系统运行库。

构建时先校验固定 Python 归档内 `vcruntime140.dll`、`vcruntime140_1.dll` 的原始哈希，
再仅从本次新建的运行时副本排除它们；保留 Python 与第三方依赖许可正文。
最终完整载荷再次拒绝这两种 DLL，避免依赖安装把它们带回。
因此本包不是完全免前置条件的便携发行。系统缺少兼容的 x64 运行库时，Python 启动或探测可能失败；
应先按官方说明安装，再手动重试连接，不会回退到系统 Python 或自行补装 DLL。
这只解决所列 DLL 的随包分发边界，不代表其他依赖许可、真实 Unity 或完整产品已获批准。

## 原生能力目录

客户端调用 `agent_catalog(offset=0, limit=12)` 后使用返回的 `next_offset` 逐页读取；目录来自固定版本的随包源码，运行时核验来源摘要。目录不访问Unity、不创建任务或授予权限。中文名称、原始工具/action与尚未接通的状态均保留，不能把“目录可见”解释为“操作已允许”。

本地面板的“展开原生操作目录”显示同一目录。已接通的只读操作复用真实能力开关；未接通操作保持灰色且拒绝，不提供假开关。当前通用只读覆盖仍不完整。

## 任务重载与重新绑定

同一连接内短暂停顿仍使用“暂停/继续”，保持原计划及到期时间。编译重载、断线或停止后旧授权失效，不自动连接、不自动继续写入。

已经成功复制/修改的材质候选会保留本次Editor会话内的任务记录；记录只包含任务范围和最后核验的证据，不包含凭据、活动授权或可跨重载使用的Undo对象。退出Editor即清除；失败的修改不作为可恢复成功点。

重连后重新启用所需的本地操作开关，让客户端以原任务ID提交同一原件/候选和引用范围的新清单（不要再复制已存在候选）。面板显示历史记录与新的认证主体/会话；点击“核验记录并重新批准此绑定”。系统重新检查候选、原件、依赖、引用和当前连接，任一变化则拒绝，保留现场。旧步骤不会重放；新文件/引用不借旧记录扩大权限。读取任务直接重新提交清单并审批，不继承旧读授权。

记录摘要仅作一致性检查，不是签名或真人身份凭据。重载后的明确撤回不复用已失效的Undo对象；不会为恢复而覆盖用户后改内容。当前自动测试包含内核外的C#门控和Unity API替身、Linux原生客户端，仍需真实Editor验收。

## 本地 Codex 开发入口（未做真实Editor验收）

在权限面板勾选本轮Codex，填写官方原生 `codex.exe` 绝对路径（当前验真版本 `0.159.2`，不接受npm的.cmd包装器）。门控连接成功后才启动独立可见控制台；导入/打开窗口不会启动。关闭控制台会结束本轮连接，若同时启用Hermes也会一起关闭。

客户端采用独立临时CODEX_HOME，不导入现用auth.json/配置；登录由用户在该原生控制台完成。`ephemeral`登录保存、禁用历史持久化/插件及受控MCP目录通过CLI覆盖固定；启动不附带提示，不自动发起模型轮次。关闭后账号不保留，重新启动需单独登录。本轮bearer只通过新进程环境交付且从原生终端的默认子环境排除，不写argv/配置/日志；公开证书可写私有临时目录。原生终端不属于MCP硬隔离，仍必须遵守项目AGENTS.md。自定义CA是附加信任，不宣称独占pin。

停止先撤销Unity任务权限，再结束本轮客户端/Job并清理临时profile，最后结束运行时；缺少客户端清理回执不算成功。进程崩溃时Job负责后代退出，但非秘密配置目录的崩溃后磁盘清理不冒称已保证。此入口仍需Windows原生Codex、Unity UI与用户登录完整验收；开发fixture不代替上述验收。

## 受限核心API元数据（本地测试，待实机验收）

`unity_reflect/get_type|get_member|search`复用固定上游读取/格式化方法，
`Editor/ScopedReflection/`是VRchat_Agent自己的独立命名附加类型，asmref加入固定Coplay程序集。
不覆盖已安装的Coplay文件，不修改全局UnityTypeResolver、Hermes源码或安全扫描器。
变换来源、输入hash、固定类型名单见该目录`PROVENANCE.json`，许可证正文一同保留。

必须本地勾选具体操作并批准`ApiMetadata`。仅查询`unity-engine-core-v1`集合：
Object、Component、GameObject、Transform、Animator、RuntimeAnimatorController、AnimationClip、
Material、Shader、SkinnedMeshRenderer、Vector3、Quaternion、Color，均为UnityEngine命名空间。
`class_name`接受集合成员的精确全名或短名；`member_name`为规范标识符，
`search`须显式`scope=unity`及非空规范`query`。拒绝程序集限定名、泛型语法和额外参数。
不读取对象实时值、不调用getter/方法、不查询项目/插件类型，不进行扩展方法发现。

返回`candidate_scope`明确标识类型集合以及`all_loaded_types=false`、
`extension_methods_included=false`。范围外类型/成员的`found=false`仅指本候选范围内没有结果，
绝不证明该API在整个工程/Unity中不存在；空扩展方法列表也不表示工程没有扩展方法。
原生读取主体保留，但通用上游反射入口仍被候选门控拒绝。
本地.NET回调对照测试和Unity API替身不替代真实Unity/Mono、UI和不同SDK/插件组合验收。

## 三类实时效果读取：默认关闭的候选入口

已接入资产`manage_asset/search,get_info`、Prefab `manage_prefabs/get_info,get_hierarchy`和非缓存测试发现`get_tests`（精确`EditMode`/`PlayMode`）。这不是纯只读或插件沙箱：加载/清理与发现可能触发工程插件回调，无法保证阻止内部未知回调，也不能承诺观察全部作用。

本地顺序为：核对当前工程并两步确认信任其插件 → 单独打开对应效果开关和具体操作能力 → 客户端提交含effects的精确任务清单 → 本地核对并批准。任何一步都不代替其他步骤，MCP没有认可插件/批准任务接口。连接、打开窗口或查看目录均不会自动授予这些权限。

- 资产：目标`AssetReads/Assets/...`；effect为`asset_load_callbacks`版本1。预览必须显式关闭；search明确页码/页大小，返回是实时页面而非快照。禁止刷新/全工程无效目录回退/写分支。
- Prefab：目标`PrefabReads/Assets/*.prefab`；info要求资产effect；hierarchy还需`prefab_contents_callbacks`版本1。仅卸载本次创建的临时内容，不保存或打开Stage。
- 发现：目标`TestDiscovery/EditMode`或`TestDiscovery/PlayMode`；effect为`test_discovery_callbacks`版本1。不启动测试、不维护作业、不抢焦点；有迭代/结果预算和30秒观测期限，但不能强停阻塞中的插件回调。
- 停止先撤销信任及任务，不自动回退作用；观察到连接/包/程序集库存变化要求重新本地核对，库存摘要不是执行代码证明。清理不确定会保留Editor会话拒绝标记，重连/新门控/重新勾选不能擦除它；界面不提供重置绕过。

当前发现附加源码固定于Unity Test Framework 1.1.31，候选显式声明依赖和Editor程序集引用；不宣称已兼容其他版本，也不自动修改真实工程来解决依赖冲突。真实Unity/Mono编译、域重载、UI、平台和VPM安装验收仍是交付前门槛。
