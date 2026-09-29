# Unity受控候选核心（新增材质垂直切片，未获Unity验收）

## 2026-09-30私有入口与分发布局（当前）

当前门控仅接受`CandidateSession`独占的私有传输回调；不再观察共享TransportManager连接，不再把候选dispatch暴露于全局工具发现。默认能力仍关闭，导入/窗口/重载不启动连接或自批。每次新连接需受信本地引导提供端点、bearer和证书pin；该引导与GUI尚未完成。

固定上游传输通过`distribution/materialize_owned_transport.py`生成候选专用唯一类型，放在`Editor/OwnedTransport`，asmref绑定固定上游Editor程序集以复用internal helpers，原上游文件与类型不覆盖。主候选与传输已按不同程序集编译，并经实际SDK/TLS调用完成读取/材质门控回读。生成布局、上游hash、许可证、稳定meta和禁止覆盖目标均已核验；**不等于Unity实际导入asmref、Mono或资产导入副作用验收**。

新编译联合67唯一ID通过，源码不漂移、精确ID集吻合、无ResourceWarning、自有构建/进程清理通过。Unity API、原生C#操作和本地人审是明确替身；不得冒真实Editor。当前汇总`evidence/additive-owned-parent-acceptance.json`；父级有限验证，无独立批准。

## 父级runtime原待接入协议（2026-09-28，历史）

**旧 `vrchat_agent_dispatch` / CandidateGate / protocol=1 完全保持只读与精确stop。不要扩宽其schema。** 新独立原生命令 **`vrchat_agent_material_dispatch`**，由 `VrchatAgentMaterialDispatch.HandleCommand` 接收：

```json
{"protocol":1,"kind":"prepare|execute|status|stop","project_id":"既有project hash","client_id":"SDK导出会话身份","connection_id":"原生连接ID","task_id":"非空任务ID","plan_id":"prepare时空串，其余为Unity返回ID","body":{}}
```

- 顶层恰好上述8个字段。身份沿用既有 `CandidateSession.LiveConnection` / `CoplayProjectIdentity`，未添加认证；不接受工具参数伪造身份。新的可信连接适配归父级。
- `prepare.body` 恰好：`source` 精确 `Assets/*.mat` 原件路径；`candidate` 不同的精确 `Assets/*.mat`；`operations` 唯一非空字符串数组，来自 `copy,edit,reference`；`references` 为 `{ "renderer":"GlobalObjectId字符串", "slot":0 }` 数组（最多32）；`ttl_seconds` 数字 `(0,900]`。
- 新候选必须不存在，列入 `copy`；已有候选仅能从本次进程内同project/client/task的保留journal与精确postimage证明来源，且不再列入 `copy`。可新prepare扩展明确引用范围，再本地批准一次，不重新复制头像/候选。
- 有 `reference` 必须有非空references；没有该操作references必须空。候选文件授权不绑定具体属性/值；没有贴图本体写权限。
- `execute.body` 恰好 `{ "action":"copy|edit|reference", "arguments":{...} }`：
  - `copy` arguments `{}`。
  - `edit` arguments 恰好 `{ "property":"真实Shader属性名", "value":0.6 }`。安全值：有限float/bool、2–4有限数字数组、**精确已有Assets贴图路径**。拒绝任意对象/find/method指令、stringified JSON、代码、导入、任意字段反射。无需属性/数值再次批准。
  - `reference` arguments 恰好 `{ "renderer":"已批准GlobalObjectId", "slot":0 }`；材质固定为清单candidate，不接受临时新宿主或新材质。
- `status.body` `{}`；task_id必须非空；plan_id可空查询能力，或精确旧/现plan查询该SDK会话/原连接/task的journal。仅输出该匹配身份记录，不用新连接查旧连接。
- `stop.body` `{}`，**精确task/plan/client/connection**。迟到stop不得撤新计划；不回退，未执行步骤拒绝。同步在途到安全点完成后返回 `status=stopped_after_safe_point` / `grant_active=false` 与实际变更。父级idle/cancel/DELETE逻辑须追踪这是独立route的plan，不要误发旧reader入口。
- 无远程approve/renew/withdraw。人审仍为Unity一次批准ID/digest；本地能力上限默认为关闭。停止保留journal，本地明确撤回单步骤先核postimage，候选复制件保留不自动删；场景保存只由用户。
- 原生SuccessResponse/ErrorResponse，关键字段均在 `data`。prepare成功 `pending,plan_id,digest`；execute `status,grant_active,transaction,readback`。transaction有 `id,action,outcome(changed|unchanged|unknown),before,after,changed,side_effects,direct_target`；发生原生失败也必须保留并转发这份data，不把外层wrapper当底层成功。超时不得重试写，先status/本地核现场。
- 父级应注册独立受控MCP工具，硬编码此command并严格schema；不要放开泛用manage_asset/manage_material、batch、菜单/代码或原生Python可能刷新的preflight。runtime目前**尚未接入本新route**，不能据C#编译称链路完成。

实现/测试正在本任务中增补。下方旧只读报告为历史基线，不能将“所有写入仍拒绝”套用到新增独立命令，也不能将旧有限审查批准继承给新文件。

# Unity只读最终门控候选（历史基线）

本轮不再是空目录：`package/Editor/Core/CandidateGate.cs`、`CandidateSession.cs`、`CandidateWindow.cs` 已实现并用本地.NET 8真实编译执行。**尚不是完整产品，也不是Unity实机编译/验收结论。所有写入仍拒绝。**

## 复用点与行为

- 仅两个已审原生命令/action：材质信息、动画控制器信息。Unity侧经 `CommandRegistry.GetHandler` 调用同步原生handler，而非复制reader；该API先拒绝异步handler。本轮用GetHandler是为同步最终检查，不使用可异步/批处理的通用invoke路径。
- 原生 `SuccessResponse` / `ErrorResponse` 用于线格式；测试直接编译固定上游 `Helpers/Response.cs`，Unity外层Dispatcher封装另由跨语言fixture核对。
- 能力默认关闭，不持久保存批准。按SDK客户端分清单，绑定工程、原生连接、任务、路径、操作、有限期限；远程无approve。Unity本地界面显示清单和SHA-256摘要，用同一个ID/摘要批准；旧界面不能批准新清单。
- 准备、批准、执行前与执行后核对目标证据。停止/过期/能力撤销/连接变化/编译导入/退出/Play Mode或reload清理计划，不回滚文件。不允许模型通过重新连接恢复批准。
- 从 `TransportManager.GetClient(Http)` 读取实际WebSocketTransportClient.State，而非manager缓存GetState，也不使用可持久化/自动生成的ProjectIdentityUtility.GetOrCreateSessionId。核对实际端点为所选loopback的 `/hub/plugin`。该适配仅观察用户已有的原生manager连接，不启动/停止连接；自有启动器尚待整合。
- 编辑器update/reload/quit事件只做撤权/观察，导入/打开窗口不会启动进程、连接、改EditorPrefs或批准。

## 证据当前上限（不得据此放开写）

目标和.meta原始磁盘SHA、Unity导入依赖hash、目标所有子资产EditorJsonUtility序列化hash纳入证据；有尺寸/对象数量上限，拒绝目标路径reparse。实际磁盘变化无需先Refresh便能阻断；测试替身中的未保存对象变化也可阻断。

**仍未完成**：未导入的间接依赖磁盘变化、依赖对象未保存内存、完整Windows句柄/junction/硬链接与TOCTOU证明、场景/引用宿主级证据。这里不是文件系统沙箱，不承诺安全修改；未解决前写入继续关闭。AssetDatabase实际懒加载/序列化行为及插件回调仍需Unity实测。测试用默认string依赖hash和伪Object不等于真实项目证据。

本地普通进程不鉴别为某个真人/客户端；真正信任边界仍需安全安装切换和可信连接流程。其他原生服务/旧直连通道不会因本包自动关闭。SDK断线即时撤权、允许的编译暂停续接、全操作目录和候选内修改仍待实现。

## 本地测试分类

- UC001：缺失core RED→GREEN；UC002–UC011：first-green characterization；UC012：准备期间本地撤权反例RED→GREEN；UC013：原生异常文字泄露RED→GREEN；UC014：不匹配操作/目标类型RED→GREEN。
- UA001：缺失Unity适配RED→GREEN；UA002–005为后续characterization；UA006中文窗口缺失RED→GREEN；UA007旧界面清单不误批新清单characterization。
- `CoreTests.csproj` 编译纯核；`AdapterTests.csproj` 编译真实候选适配/窗口＋明确Unity/原生handler替身＋真实上游Response。都使用`--disable-build-servers -p:UseSharedCompilation=false`。
- 初期原始命令/结果在`evidence/unity-*.json`，当时21个唯一ID（UC001–014、UA001–007），不是21项真人/Unity验收；最新接管结果见下节。
- `WirePeer.cs` 为后续真实SDK跨语言测试的显式Unity替身；证据和本地批准是fixture，不属于package，不得当启动器。

## UR001–003修复与父级接管

初次独立复核`deleg_57611ad6`不批准，报告与反例未覆盖。修复子任务`deleg_2344b2c0`已落盘代码，但以HTTP429中断，不能把子任务本身记为完成。父级检查真实文件、原始RED和上游调用链后完成复跑与收尾：

- UR001：`CoplayProjectIdentity`为固定上游的极窄反射桥，在`typeof(CommandRegistry).Assembly`定位真实internal类型的`GetProjectHash`；不复制hash算法、不调用持久session方法、不修改上游可见性、不使用friend程序集。缺失/不兼容返回空并拒绝绑定。实际固定身份源码与Response在独立程序集编译；三个纯字符串路径下桥/原 getter一致，UI/门控一致、错误工程拒绝。**反射仍需真实Unity验证，不是升级兼容保证。**
- UR002：原生失败只输出固定`native_read_failed`及拒绝结构，撤销计划；丢弃原始异常/stackTrace/message。
- UR003：`NativeReadContract`只校验上述两种原生读取的成功数据形状，不重写reader。异常标记、未知输出或部分异常数据拒绝且撤权，不伪造成功。合法texture名称以`<error:`开头时保守拒绝，因为无法与原生异常标记区别。
- 原`AdapterStubs`默认成功对象`{fixture_only:true}`不符合原生返回，最终验证会拒绝。父级保留失败及原替身快照，只将默认fixture替换成原生`material/shader/properties`形状；`AdapterCases`等五个原断言源码hash不变。UF008保留对旧未知形状的拒绝断言，不通过放宽输出闸门掩盖问题。

最新可重复命令：`python3 -B Candidate~/tests/verify_unity.py <新的证据标签>`。只调用已安装.NET/SDK、关闭还原源与审计网络、使用临时HOME/构建树，不改原csproj/上游。测试runner验证准确ID集合和正常退出后PID/进程组消失。

`evidence/unity-parent-final-isolated-clean.json`：**48个唯一ID通过**，UC001–014、UA001–007、UF001–024、UR002–003、WI001。UF017/018每种材质类型是子例，三种identity路径是重复，均不重复计数；UR001跨程序集build另记，不凑到测试数里。`evidence/unity-fix-result.json`为父级接管报告，不是独立批准。688份固定上游文件hash未变。清理了中断子任务的360份自有生成构建文件，源/测试/历史失败证据未删。

**修后独立批准仍待完成，完整产品仍不通过。** 未加入受控写、可信peer、依赖证据或Windows能力；不因这些局部修复要求用户安装。
