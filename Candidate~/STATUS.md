# 当前状态：2026-10-10 五项独审修复已闭环，进入自动化与 Windows 验证

- 原完整独审发现的 F01–F05 已修复；增量独立复核 `evidence/independent-fixes-20261009/review/verdict.json` 为 passed=true、findings=[]，主Agent已读回报告并核对修复源码/冻结输入。不是重新全量独审，也不是实机产品放行。
- 技术汇总 `evidence/independent-fixes-20261009/technical-closeout.json`：74个唯一Python(file,method)通过；DG001–015/DA001及UC001–015、EG001–004、PS001–008分组通过。Unity API仍是替身，编译门仅末次source-inputs清单摘要漂移，实际编译输入均当前。
- 当前精确插件载荷已通过未修改宿主的正常隔离安装：safe、零发现、逐文件读回一致、未启用；安装/测试自有清理确认。368项分发源码摘要匹配。原失败及修前备份保留。
- 用户现要求集中完成自动化与真实Windows验证。仅候选分支/Actions有限授权；禁止改main、历史版本、现用VPM索引、Hermes配置及真实Unity/头像工程。开始本轮时本地与远程HEAD均为9cce76f5b172ac4f45a8599249ba82a045ea6f96；该提交的历史CI成功不覆盖当前未提交修复。
- 本段是审后状态文档更新，不重签此前663输入冻结。当前Windows/便携工件、Unity/Mono、真实客户端以及VPM/ALCOM仍须分别验收；后续结果单列 `evidence/windows-automation-20261010/`。

## 历史增量：2026-10-09 Hermes 正常扫描安装兼容验证通过（仅隔离环境）

- 本轮按用户明确请求，仅改候选 `clients/INSTALL.md` 的 SSH 安全说明措辞与 `clients/hermes_gateway.py` 的身份读取，并追加对应网关测试；不改 Hermes、现用配置、SSH 策略或 Unity。
- 说明保留全部部署限制。网关改用 Hermes `SessionSource.to_dict()` 取身份，防止空 profile 被省略后变成默认身份；机器人、profile 路由拒绝及宿主授权继续检查原对象。
- `evidence/installer-compat-20261009-red.json` 保留原两条扫描发现与新接口缺失的 RED；`-green.json` 为10项网关契约通过；`-comparison.json` 对修改前备份和当前代码运行272个真实 SessionSource 输入/停止命令组合，授权决定和分发结果无差异。平台发送/网关授权仍是替身，无模型调用。
- `evidence/installer-compat-20261009-install.json`：当前未修改的宿主原生 `cmd_install(force=False, enable=False)` 在临时 HOME 正常安装成功，扫描 safe/零发现，安装后逐文件读回匹配，未启用，临时根已删除；所监测宿主源码/扫描器/现用配置 hash 未变。测试自有进程树和 socket 清理通过。仅本机精确源码插件安装，不是现用 QQ 网关激活或跨机部署。
- 两处原有扫描阻塞在本次候选上已解除；下方旧“正常扫描安装未完成”描述仅保留历史。旧整代报告不覆盖本轮网关改动，尚不能称完整产品通过；独审、Windows/便携工件、真实Unity与VPM/ALCOM门槛仍未闭环。本轮没有提交、推送、发布或操作真实头像工程，也未启动全量回归/CI。

## 前一代集成状态：2026-10-08 本地插件信任前提下的实时效果读取

- 资产search/get_info、Prefab get_info/get_hierarchy、非缓存测试发现EditMode/PlayMode已接通实际Session、UI、runtime工具/能力目录与客户端清单；工程级测试作业观测保留。默认均不授予效果或任务权限。
- 本地两步认可工程插件是明确选定的信任前提，不是完整代码审查、执行映像证明或插件沙箱，不能阻止插件内部未知回调。源会话clarify message 107467已回读，见`evidence/project-plugin-trust-original-response-20261008.json`。旧严格来源阻断仅作为历史，不再误列为当前未实现项。
- 信任、独立效果开关、精确任务批准分离；停止等待清理前撤销信任，停止中不能再认可；观察到包/连接/程序集库存变化即失效，恢复旧值不恢复授权。清理未知的SessionState拒绝标记不能由重新勾选清除。
- 生产Session使用随包资产/Prefab读取器和异步发现Job；独立效果回执、原owner清理、迟到结果丢弃继续生效。传输等待Task结果，不把Task序列化成完成回执。
- 验证边界：Linux/.NET与声明的Unity/NUnit/UI替身；原生Hermes/Codex协议测试无模型调用，审批和Unity数据仍是fixture。不是Unity/Mono/Windows/human接受或正常安装。
- 本代整体验证以`evidence/plugin-live-20261009-strict-checkpoint.json`为准；文件不存在或passed不为true时，不得称全量通过。preflight的280方法通过但源码变化与旧C#失败引用使聚合失败，原报告保留。
- 未完成门槛：完整独立审查（旧429后未获重派）、原生Hermes正常扫描安装、精确源码Windows/便携工件、真实Unity/域重载/UI、VPM安装升级卸载及完整后的ALCOM/人审。没有提交、推送、发布或真实头像工程执行许可；不修改Hermes、不绕扫描。

# 以下为历史记录（不覆盖上方当前状态）

# 当前候选状态：2026-10-08 测试发现异步核心，尚未交付

- Prefab修复冻结已通过，但不覆盖之后新增的发现代码。发现reader已25项、独立异步gate已10项专项通过，均为Linux/.NET加明确Unity/NUnit替身，不是Unity验收。
- 新实现复用固定原生非缓存发现器和收集器，受控自有订阅/迭代器清理；默认关闭、精确模式清单、本地批准、异步票据、撤权与失败回执。返回字段/预算不完整即拒绝，不把未确认清理写为成功，不自动重试。
- 本轮包括原生MoveNext内部可能清理抛错的保守失败边界：再次Dispose未抛错不证明前次清理成功。未知清理使当前gate锁闭；跨gate/reload债务保持及实际Session/UI/runtime适配仍未实现。
- 源码载荷已包含发现reader且不注册工具；可信来源尚缺，实际入口仍关闭。计划以`discovery-20261008-core-frozen`做全套同源回归，当前这段文字不声明该轮通过；最终以同名checkpoint JSON为准。
- 完整独立审查、正常安装、Unity/Mono/Windows/VPM/ALCOM均仍欠。未改Hermes本体/配置/扫描，未操作真实头像工程，未提交/推送/发布。

# 历史检查点：2026-10-08 冷启动基线首轮验证，尚未达到Unity接入门槛

- 批准证据更正：历史状态曾写为用户明确选择冷启动方向，但当前保存的clarify原始结果仅为asked，不能据此证明具体选择或扩大权限。只继续已授权候选与隔离验证；不重启现用工程、不开真实执行、不重派审查、不修改宿主。
- 实验：`loaded-code-identity-20261008-cold-byte-boundary.json`的NI001–NI004及两个预期充分性反例通过；`cold-lease-20261008-final.json`的CB001/CB002通过。含真实.NET加载器/动态方法和Linux租约，不是Unity/Windows。原始失败报告均保留。
- 关键边界：同一份已核字节直接交给加载器的合成路径可用，但磁盘hash+MVID、程序集库存或仅inode租约均不足以认证整个Editor；路径替换可保留旧租约。固定Unity参考源码显示依赖InitializeOnLoad先于本候选，窗口/静态构造并非前置拦截点。
- 完整可行性报告及来源：`evidence/cold-start-context-feasibility-20261008.md`，源码pin：`cold-start-upstream-pins-20261008.json`。目前没有验证真实Unity进程前来源绑定，不能填写complete=true或接资产入口。其余UI/Session/runtime、Prefab/发现、独立审查/正常安装/实机/VPM/ALCOM缺口仍在。
- 本轮未改产品生产字节；原owner-frozen验证仍属于原源码，不把新实验计入265方法。源表/旧证据逐hash核验、diff检查通过；本轮实验清理确认。未提交、推送或发布。

# 最新证据：2026-10-08 无加载上下文仍欠可靠来源绑定

- `evidence/loaded-code-identity-20261008-final.json`：Linux/.NET 8真实loader/动态方法实验NI001–003及两个预期充分性反例通过，非Unity/Mono/独立审查。磁盘路径+MVID不能证明当前执行字节，程序集库存不变也可有新动态回调。详见`evidence/no-load-context-provenance-20261008.md`。
- 本轮仅新增evidence，未改生产实现；owner-frozen产品结果仍绑定原源码。进程树/临时根清理均确认，失败实验保留；不得填complete=true绕过provider。
- 尚需明确是否采用显式冷启动可信基线流程；重启本身不证明安全，不自动授权执行。此时未作新的用户流程决定，所有四类实时目标保留，未知回调继续拒绝。

# 最新检查点：2026-10-08 受控审查导入API与异步暂存已验证，实际资产入口仍关闭

- 最终证据：`evidence/asset-review-20261008-owner-frozen-checkpoint.json`。265个独立进程运行时方法通过，LC006另由同代C#编译组执行；C#主组82、Editor编排7、AR001–008、RC001–005、AG001–007、实际随包资产BA001–015分别通过，交叠测试不求和。
- 本轮主汇总`asset-review-20261008-owner-frozen-all.json`直接passed=true；已修复制runner的旧C#报告引用，228共同源逐hash相符。源码运行期间未变；所有逐方法原始结果、警告、清理和源绑定再次核验。不是独立源码审查。
- 产品内部API：`EditorOwnerProcess.CaptureReviewAsync`实际启动固定helper，复用解释器预检；选定文件走私有stdin，stdout有界，非零退出/stderr/超限/超时/取消拒绝。Linux实际进程验证，Windows本轮尚未实机。`AssetCallbackReview.StageCapturedLocalAsync`等待前撤权，迟到/撤销/替换/fault/cancel不恢复记录；成功只暂存。
- 新RED→GREEN：父身份入口、输入阻塞期限、异步暂存方法、C#实际启动接缝，以及Editor消息循环暂停导致清理续体停滞。进程生命周期worker不调用Unity API；核心仍要求Editor线程及续体。Linux父进程死亡且输入写端保持打开的实际测试首次GREEN；故障fixture逐PID消失。详见`asset-import-owner-20261008-boundary.md`。
- **API不是UI/Session接入完成**：真实工程无加载可信上下文、已加载代码/依赖/回调覆盖与来源核验仍缺；本地文件选择、确认展示、取消/域重载事件调用、资产Session/runtime/catalog与客户端接入仍缺。没有加入空上下文放行或MCP批准接口，资产入口保持关闭。
- 清理：本轮4个最终父PID均缺席；受控连接跟踪9后代/3监听无残留，临时诊断后端/构建根清除。载荷hash有效，diff检查通过。状态文档在冻结后追加，不改生产字节。
- 独立审查仍因旧429未完成、未获重派许可；正常原生安装扫描仍阻断、误报仅本地；真实Unity/Mono/Windows/VPM及完整后ALCOM仍待。Prefab/发现仍仅行为刻画，不冒称产品实现。无Hermes/固定上游/真实工程/现用配置修改，无提交/推送/发布。

# 最新检查点：2026-10-08 本地审查文件导入切片通过，实际入口仍关闭

- 当前最终复核：`evidence/asset-review-20261008-import-checkpoint.json`；同源262个运行时唯一(file, method)、82项C#主组、Editor7方法、AR001–007（含实际私有管道）、AG001–007、BA001–015及原生资产/作业专项分别通过，不求和。
- `import-final-all.json`本身保留passed=false：262方法均通过且源码未变，但汇总脚本沿用旧`import-frozen`的C#报告，源绑定拒绝。独立的机械复核脚本`verify-import-final-20261008.py`重新验证每条方法回执/清理及**同代import-final**的LC006与226共同源hash；先实测拒绝旧报告，再通过当前报告。不是重新执行262方法，也不是独立源码审查，未篡改原失败记录。下次复制runner须把unity_path绑定当前LABEL。
- 新增`diagnostics/asset_review.py`复用稳定同描述符/HANDLE读取，单次限制只能收紧；实际文件→私有管道→C#核心暂存已组合测试。导入先撤旧权限，拒绝编码/超限/替换/占用/异常，读取不落盘、不脱敏改写、不批准；StageCapturedLocal和StageLocal重入替换已RED→GREEN，失败清除嵌套已确认记录。
- 扩大回归初次7失败保留：6项需要真实固定诊断后端；现用临时搬迁副本组装固定Node/npm后端测试，不添加生产fallback。Windows ACL测试将平台替身错误延伸到外部keeper已修局部边界，非内核验收。另修测试自身CLI提前EOF的管道关闭并新增DC008。旧261→新增清理用例后262。
- 清理逐项回读通过：262方法、三最终父PID缺席、真实owned9后代/3监听无残留，诊断打包临时副本和构建根均清除。载荷源码摘要有效，diff检查通过。此处状态文档追加发生在冻结结束后，不改生产字节。
- 附加行为刻画：固定上游Prefab PF001–009、测试发现ND001–007通过且纯读反例复现；逐方法原样提取、Unity API替身，非完整原生编译/真实Unity。Prefab可成功但缺组件/Variant信息；发现实际30秒超时返回空表且晚到回调仍可能存在，外层超时不取消底层工作。证据`native-prefab-effects-20261008-first.json`、`native-discovery-effects-20261008-first.json`。
- **尚未完成**：真实工程无加载可信上下文采集、Editor受控导入进程/UI、本地来源核验、Session/runtime/catalog与两客户端接入；Prefab/异步发现产品授权与实现。资产实际入口继续关闭，不把导入记录等同安全审核，未知回调仍拒绝。
- 独立审查429后未重派；正常安装扫描仍阻断，误报仅本地；真实Unity/Mono/Windows/VPM/完整后ALCOM仍待。未改Hermes、固定上游或真实头像工程，无提交/推送/发布。没有留后台自治任务。

# 最新检查点：2026-10-08 本地审查记录核心冻结回归通过，真实入口仍关闭

- 当前最终证据：`evidence/asset-review-20261008-record-checkpoint.json`。完整当前源码冻结`asset-review-20261008-record-frozen`完成：212运行时方法、82项C#主组、Editor 7方法、记录AR001–005、资产Gate AG001–007、资产读取/回执BA001–015、原生资产NA001–006及job NJ001–010分别通过，不能求和当独立总数。
- 全部冻结输入无变化，212方法资源清理逐项核验；受控连接9后代/3监听无残留，临时目录和三个后台父PID已缺席。源码载荷摘要有效，git diff --check通过。仅此状态记录是在冻结后追加，不改生产代码。
- 本轮落地：实际载荷包含AssetObservation与AssetCallbackReview；search/info加载前后重校验GUID/path。记录暂存不授权、严格校验、上下文/时钟漂移失效、重入撤销不复活；与真实Gate组合验证确认记录不自动开能力或批准任务。
- 仍缺实际无加载上下文采集/可信本地审查文件导入/UI，再接Session/runtime/catalog。已选记录流程不是实际评估结果。记录digest不验证审核者身份，complete字段不能独自证明回调覆盖，禁止用测试上下文代替真实工程。
- 当前实际资产入口仍拒绝；Prefab与测试发现未完成。独立源码审查、正常扫描安装、真实Unity/Windows/VPM/ALCOM验收仍欠。未改Hermes、未操作真实工程、未提交推送发布。
- 合同/边界说明：`evidence/asset-review-record-contract-20261008.md`、`evidence/asset-callback-review-boundary-20261008.md`；用户流程选择凭据：`evidence/asset-review-record-workflow-20261008.json`。未经另批不重派独立审查。

# 当前实施：2026-10-08 本地审查记录核心新增，准备重新冻结

- 用户选定“可核验的本地审查记录，再单独批准任务”，精确记录在`evidence/asset-review-record-workflow-20261008.json`；不是现实执行许可/独立审查重派许可。
- 新增`package/Editor/Core/AssetCallbackReview.cs`：本地暂存无赋权、确认精确摘要、严格JSON/schema/上下文/未知回调/到期校验；代码/依赖/工程/回调变化、时钟回退/异常、采集时撤销都失效不复活。AR001–004逐项RED→GREEN，AR005与真实gate组合首次characterization通过（记录不会自动打开能力/批准任务）。
- 回调上下文提供者/实际代码审核/真人UI仍为替身；digest不是签名或审核者身份。该类没有MCP注册或文件导入，更没有实现自动代码安全评估；真实Session仍不接入它，入口拒绝。
- 新增类实际载荷SP012已RED→GREEN，12方法载荷测试通过；集成Core/Adapter等专项通过。现准备新冻结`asset-review-20261008-record-frozen`；先前receipt-frozen的212/82/Editor结论不覆盖此生产增量。
- 下一步仍是可信、无副作用的本地上下文采集与审查文件加载/UI绑定；未知动态回调不能靠complete字段/确认框冒充评估。其后再接runtime/catalog。

# 最新检查点：2026-10-08 资产回执/身份重校验局部验收

- 本地成功证据：`evidence/asset-effects-20261008-receipt-checkpoint.json`。212方法、82项C#主组、Editor 7方法、资产gate 7项、资产预算/回执/组合15项、原生资产6项及原生job 10项分别通过；范围有重叠，不求和冒称总覆盖。
- 生产代码与`asset-effects-20261008-receipt-frozen`一致。冻结之后只有额外测试脚本`tests/verify_owned_transport.py`更正程序集扫描归属；该脚本及真实受控连接单独重建/执行通过，不能说整树原封不动。9后代/3监听清理、全部212方法资源清理、三后台父PID缺席及owned临时目录移除已核验。
- 保留失败证据：曾误将`gates editor`传给verify_editor_wire（参数拒绝，改用ec成功）；owned构建曾误把ScopedAssets编入候选assembly（按asmref修测试排除，独立实际资产源码编译仍保留）。未修改生产代码迁就测试。
- 当前资产加载实际入口仍关闭。回调评估来源、Session/UI/runtime/catalog尚未完成；下一信任边界详见`evidence/asset-callback-review-boundary-20261008.md`。未知回调仍拒绝，不用确认框/测试字符串冒充评估；不能承诺同进程隔离或总工作量上限。
- 仍非独立审查/真实Unity/Windows/VPM/ALCOM验收；未改Hermes、未操作真实工程、未安装、未提交推送发布。

# 当前实施：2026-10-08 资产回执进入实际载荷，准备最新冻结

- 回执适配器 `package/Editor/AssetObservation.cs` 已纳入 `distribution/source-inputs.json`；SP012先失败再通过，完整source-payload 12方法通过。未注册新MCP工具或开启权限。
- 资产当前预算/安全专项 BA001–BA015 通过，包含真实候选Gate＋实际AssetObservation＋实际随包原生衍生读取器的组合；Unity API、回调及受审上下文仍为替身。BA013最初把被拒绝撤销的pending计划用于approve，改为依现有规则重新prepare；并非生产缺陷修复。
- BA014、BA015先复现GUID/path在加载期间变化仍被接受，再修复search逐项加载前后/Info加载前后的双向身份重校验。生成器与实际文件及清单摘要同步；GetAssetInfo/GetAssetData/AssetExists固定原生方法正文未改。
- 最新局部证据：`native-asset-effects-20261008-info-guid-green.json`；`runtime-checked-20261008-asset-receipt-payload-green.json`。准备冻结标签 `asset-effects-20261008-receipt-frozen`；旧212结果不能证明该版本全绿。
- 真正缺口：Session的可信回调评估来源、UI评估/许可、runtime/catalog接入尚未完成。Gate的review是可信本地适配器接口，不是自动安全判定；当前Session仍使用无资产review的构造器，真实入口保持拒绝。
- 未评估回调不能凭通用勾选、模型自报或单一字符串变成可信；不得复用会LoadAllAssets的Evidence路径，也不能用路径或结果过滤承诺副作用隔离。
- 无真实工程执行/安装、无Hermes修改、无提交推送发布。独立审查/扫描/Unity/Windows/VPM/ALCOM门槛不变。

# 当前实施：2026-10-08 资产读取器与授权核心局部通过，真实接入仍关闭

- 候选设计与实现许可记录：`evidence/asset-effects-20261008-approval.json`。真实工程执行另批；不修改Hermes或已安装上游，不自动信任未知回调。
- 原BA007已先复现再修复：同次FindAssets结果在分页加载前检查全部GUID解析路径，拒绝越界、重复（含大小写别名）和缺失。BA008回调失败脱敏并披露可能已有作用。实际包内`package/Editor/ScopedAssets/`九项BA001–009通过；BA009为实际gate+实际读取器组合，Unity API/评估凭据仍是替身。
- 核心沿用CandidateGate新增默认关闭的独立回调许可、精确单操作/单目标effect清单及风险说明，trusted review与effect reader缺一拒绝；普通Evidence/registry不会用于新资产操作。AG001/006实际RED→GREEN，AG002–005/007是已有防线首次通过的characterization，不冒称均曾失败。七项覆盖未批/未知上下文/参数、暂停撤权过期/变化/拒绝重载、迟到结果及调用票据归零。原五参数构造保留，支持反射调用者。
- Session仍使用无asset适配器的旧构造，UI/runtime/catalog未开放资产操作。可信无加载上下文评估实现、审查绑定、本地UI、实际receipt/结果验证和MCP链仍待，不能写成“功能已实现只待实机”。不把资产路径当回调沙箱，不用快照替代。
- 新附加reader沿用asmref归属单独编译；一般adapter测试从本程序集glob排除其源，专用原生测试逐字节核对重生成结果后直接编译**实际包内源**。不是删除编译覆盖，也不是Unity/Mono验收。SP012加入真实载荷清单，载荷12项曾通过；核心后改已更新输入hash，等待本轮新全量冻结。
- 先前job的211/82/EC7结果绑定旧源码。当前C#授权/连续性/重载/Adapter专项通过；新212方法+主C#/Editor冻结将使用`asset-effects-20261008-core-frozen`证据，未得结果前不宣称全绿。
- 独立审查仍无完整结论，429后未重派；原生扫描安装仍拒绝，报告仅本地。完整候选/Windows/便携/VPM/ALCOM门槛不变。无提交、推送、发布或真实工程修改。

# 历史调查：2026-10-08 资产原生行为已量测，回调授权范围待确认

- 最新补充入口：`evidence/asset-effects-20261008-characterization-checkpoint.json`；job本地集成成功见下节。新增仅3个测试文件，未修改生产派发、宿主或真实Unity。
- `native-asset-effects-20261008-first.json`：原生ManageAsset整文件SHA与固定提交核对后，逐字节抽取SearchAssets/GetAssetInfo/AssetExists/GetAssetData；Unity API及回调为明确替身。不是完整ManageAsset编译/真实Editor执行。NA001–006六项通过，另保留`PAGE_LOAD_BUDGET_VIOLATED`预期失败反例。
- 实测原生每页1项先加载3匹配项；无效目录改为全工程并加载范围外资产；分别分页重查可重复行且重复加载。禁preview仍加载；合成回调已产生影响后，原生可返回失败，错误不等于零效果。路径限制不是同进程第三方回调沙箱。
- 所有8个构建/执行子过程自然退出及owner清理通过、构建根缺席、源码前后一致、无编译/资源告警。此前211/82/EC7生产字节不变，仅STATUS更新；这3项新测试不追计旧冻结覆盖。
- 下一步需确认资产候选的回调信任许可范围；未获新范围前保留原关闭状态，不把“读取目录”写成“只影响目录”，也不以快照替代。独立审查/正常扫描安装/实机/完整候选交付门槛不变。

# 本地集成验证：2026-10-08 工程级作业维护已本地接通，整轮回归恢复通过

- 当前入口：`evidence/job-effects-20261008-local-closeout.json`。工程级job维护默认关闭，真实执行仍须本地批准；四类实时目标不删减。已接gate、原生receipt adapter、session/UI、runtime、目录、客户端白名单及真实源码载荷。
- 原211方法冻结仅NP006旧“工具必须不存在”断言失败；已先复现，再改成验证“入口可见但未授权拒绝、零原生查询/焦点调用/后台任务”。没有放松生产门控。旧失败和修复前备份保留。
- 新冻结`job-effects-20261008-np-fixed-all.json`：211/211唯一(file, method)通过；LC006另由新编译C#门控通过，217共享源摘要吻合；运行前后源码不变。C#主组82通过；EffectGate/JobObservation/Adapter专项及EC001–007另列通过，不能跨套件相加冒充产品覆盖。
- `job-effects-20261008-native-protocol.json`：真实原生Hermes MCP engine与Codex app-server，NJE001/002分别验证工程维护默认拒绝、独立effect清单/本地fixture批准、回执、暂停/恢复、跨客户端拒绝、停止后拒绝。job数据/回执和人审是明确替身；不是真实Unity/安装/模型循环验收，完整原生manager另有独立行为测试。
- 原生两客户端各创建/DELETE确认2会话；11后代、1监听无残留，临时目录缺席、秘密扫描/ResourceWarning检查通过。211方法逐项cleanup回执、C#构建清理、Editor自然进程树退出均通过；终态无测试入口进程。
- 原生作业维护错误/丢失回执会撤权并披露`effects_may_have_occurred=true`，无自动重试/回退；回执不宣称零副作用。未真实启用工程维护/启动测试/抢焦点。
- 余下资产加载、Prefab生命周期、异步测试发现仍未实现；独立审查429后未重派，扫描误报只本地且未绕过。真实Unity/Mono/UI、当前精确Windows/便携工件、正常安装、VPM/独立ALCOM仍待。
- 仍为本地未提交候选，HEAD `9cce76f5b172ac4f45a8599249ba82a045ea6f96`；无提交/推送/发布、无Hermes宿主或真实头像工程修改。此段更新在冻结结束后，仅状态文档变化，不冒称文档包含在先前冻结中。

# 历史验证：2026-10-07 23:24 作业观测越出单job范围，设计需改审

- 当前入口：`evidence/live-effects-20261007-2324-checkpoint.json`。用户要求继续后，主Agent完成有界原生行为验证；没有新增生产派发/能力开关或真实工程执行。
- 新增可复跑测试5文件。完整固定原生TestJobManager/TestRunStatus/GetTestJob及解析器直接编译，未切片/改原生；NJ001–010十项characterization通过。另保留预期失败的`single-job-scope-red`：查已结束A触发类恢复，会将不同的过期B标失败；查不存在的ID也会触发恢复。不是修复后的绿灯。
- 原生查询超时会维护当前状态并序列化工程作业集合，实测内存12项→SessionState保留10项，删除的持久化条目包含未查询历史作业；SessionState写失败被捕获，仍可返回success=true。故原设计“仅指定job维护”不能直接接入，需另行决定工程级维护授权/失败回执边界，不能悄然扩大范围。
- 实际原生Python包装器NP001–006六项通过：不长轮询也会调度后台焦点nudge；测试专用模块局部禁用接缝可阻断焦点/路径查找/后台任务且保留单次查询。没有将测试补丁安装到产品；候选仍不暴露get_test_job。传输和OS焦点为替身。
- C#与Python测试源执行前后hash一致，原生固定文件hash核对通过；自有构建/临时HOME/子进程与测试后台任务均清理。Python保留一条asyncio慢任务调试提示，无ResourceWarning；不冒称完全无诊断输出。
- 新测试不算进旧177/81且未接全量CI。核对旧回归冻结578项仍仅既知STATUS/owned测试驱动变化，生产源码没变；本轮新增测试单独列hash。完整候选未实现/未批准，不用快照或删功能换交付。
- 无提交/推送/发布，无Hermes/固定上游/真实头像修改；429审查未重派，误报仍只留本地。Unity/Windows/正常安装/独立复核/VPM/ALCOM门槛不变。

# 历史调查：2026-10-07 官方原样安装复核，仍被阻断

- 补充证据：`evidence/native-install-followup-20261007.json`，承接下方22:07检查点；本轮未改生产代码，未重复已通过的整轮回归。
- 固定官方Hermes提交`84692b7d7499c4536d71a56e8ddbe59abd329103`，未修改的plugin-guard-v9对原样候选插件仍判DANGEROUS；原生cmd_install退出1、未安装。仅`INSTALL.md:40`的SSH安全要求触发critical ssh_backdoor，文档降级明确不适用于该规则。故不能声称升级官方新版即可解决。
- 没有force、改扫描开关、确认回调或核心补丁；参考源码和所核宿主文件hash未变，临时安装HOME已移除。只有只读参考checkout保留，没有启动服务。
- 上游报告草稿为`evidence/official-hermes-84692b7d-upstream-report-draft.md`，未提交；不得自行公开私人源码。
- 静态复核测试能力：原生测试发现调用异步RetrieveTestList并QueuePlayerLoopUpdate；原生GetJob在超时分支会更新作业并写SessionState。未在真实Unity执行，不能把这些操作作为无副作用读取放开。四类安全hold依旧是未实现，不是测试已通过。
- 当前候选无新提交、推送、发布；独立审查仍无结论。安装方式及有副作用原生操作的产品取舍未解决前，不要求用户ALCOM装半成品。

# 历史核验：2026-10-07 22:07 本地回归收尾，完整候选仍被阻断

- 唯一续接入口：`evidence/candidate-closeout-20261007-2207-checkpoint.json`。本节优先于后文历史记录；不是安装/发布批准。
- 受限`unity_reflect`已整合为自有附加类型，限13个核心UnityEngine类型、独立ApiMetadata批准。通用反射仍关；固定上游/宿主源码不改。原生双客户端`scoped-reflection-20261007-native.json`已通过，真实Unity/API/人审仍未验收。
- 完整运行时177个唯一file+TestCase.method通过；C#主组81通过，EC7另列，不相加。新工具导致的3组旧精确列表遗漏已补齐，断言未放宽；原始失败保留。
- `verify_owned_transport.py`修复测试替身重复Application声明、-I本地helper导入、旧fixture未显式选择Hermes的问题；生产clients=()不变。最终Editor→owner→runtime与owned门控读写均通过，未批/异会话拒绝、stop不回退、磁盘回读及清理均有实证。Editor最后跟踪9后代/3监听无残留；不是Unity/Mono域重载实机。
- 便携包真实搬迁通过，原生双客户端协议通过。checkpoint逐报告回读源码：产品字节均吻合，迟到测试专属修改明确列出；未把旧报告伪装成新全树冻结。源码组装693载荷项有效，不等于VPM包。
- 原生`cmd_install`在临时HOME执行，扫描DANGEROUS拒绝（INSTALL.md:40安全说明、hermes_gateway.py:63中等级命中）；未安装，临时根清理、Hermes安装器/扫描文件hash未变。没有删说明、改扫描开关、patch宿主或动现用配置。
- 经用户允许的新独立审查`deleg_b0a3cb43`再次HTTP429，无报告/结论；不重派、不切号，不能把主Agent回归替代独立批准。
- 12能力族最新账本：7受限实现、4安全hold（资产/Prefab枚举、测试发现/任务观测）、1仅目录；read_implementation_complete=false。未实现不改记“仅待实机”。
- HEAD仍`9cce76f5b172ac4f45a8599249ba82a045ea6f96`，候选分支`candidate-alcom-20260928`，本轮无提交/推送/发布/新Actions。main、现用索引、Hermes/QQ、真实头像工程未改。独立复核、原生扫描安装、当前精确Windows、剩余能力、完整VPM/ALCOM门槛仍未通过；没有后台自治续作。

# 历史核验：2026-10-07 脚本/Shader/clip已整合；反射原生路径有回调阻断

- 最新检查点：`Candidate~/evidence/clip-reconciled-20261007183953-checkpoint.json`（STATUS路径相对仓库根）。完整Candidate仍未交付。
- 本轮两次C#整体回归通过，最新 `unity-parent-clip-reconciled-20261007183953-current-frozen.json` 为81主组PASS；ST001–009等分组单列，不能相加冒充全产品。所有命令、精确IDs、源码不变、无告警、构建根清理通过。上一轮73PASS失败已被修复后新证据替代，旧失败保留。
- 最新真实Hermes/Codex协议回归 `clip-reconciled-20261007183953-native-current-frozen.json` 通过，NSRC001/002、NCL001/002与既有任务全过；各2会话创建/DELETE确认，9后代/1监听无残留，无秘密或资源告警。仍是net8+文件/Unity API/本地批准fixture，无模型、真实Editor/人审/正常安装批准。
- 反射对照 `reflection-boundary-clip-reconciled-20261007183953-native-risk-fixture-fixed.json`：未改固定原生reader，实际CLR中get_type、缺失get_member、search各触发1次缺失依赖解析回调；目标静态构造/getter/方法计数均0。元数据不等于getter调用，但已加载也不等于无回调。保持unity_reflect关闭，类型元数据尚未集成，下一步需评估最小原生解析/缓存范围适配，不可只做返回后检查。
- 12方法族逐项账本 `clip-reconciled-20261007183953-capability-reconciliation.json`：6已有受限实现、4安全hold、1反射/包信息部分阻塞、1纯目录。明确区分安全拒绝和缺实现，read_implementation_complete=false。
- 修复目录生成丢失4条既有安全说明的问题，增加完整生成回读一致性断言；OC1、catalog2、SP9、VP30逐套实跑通过。321项源码输入摘要更新并保留原清单备份，源组装成功不等于冻结批准或VPM。
- 插件载荷与旧官方扫描拒绝时逐文件SHA一致，INSTALL.md:40仍触发ssh_backdoor；没有删除安全说明、改扫描器/开关或现用配置。正常安装未验收。
- HEAD仍9cce76f5b172ac4f45a8599249ba82a045ea6f96，candidate-alcom-20260928；本轮无提交/推送/发布，无main/索引/Hermes/QQ/真实头像修改。真实Unity、完整独立复核、新精确Windows、正常扫描安装、VPM/ALCOM仍欠。旧429不重派/切号。

# 完整候选验收账本

## 2026-10-07 当前入口：源码只读已本地整合，继续双客户端及B2/B3

- 上一轮 `native-source-20261007164155`：受限manage_script/read、get_sha→manage_script/get_sha、manage_shader/read已接Python/C#、UI、目录和客户端工具白名单；默认关闭，须精确文件/任务批准。正文/大小/参数/响应门控不开放写、刷新、正则查找或任意文件。
- 最新 `unity-parent-native-source-20261007164155-integrated-fixtures-fixed.json`：81主组、ST001–007另列通过，所有命令成功、精确ID、源码不变、构建目录清理、无ResourceWarning。首轮17主组/测试依赖编译失败保留；-I本地模块导入已修。
- RT037–040为新增来源读取/别名用例，RT036仍为组件类型解析拒绝。上一轮早期日志RT036–038与后续重命名不可混算。完整runtime、33表面回归、目录/载荷和VP消费者通过均有独立报告，非全产品冻结。
- 实际Editor编排已有EC7、CE4/ER4/RW3/EP6及私有传输测试；真实Unity/API/本地批准依然有替身，不冒称实机。源码读取当前尚欠真实双客户端调用与新Windows文件身份/竞态审查；普通FileStream与路径检查不是硬链接/祖先竞态沙箱。
- 剩余B2/B3：clip信息、已加载类型元数据；其余方法族按账本明确hold原因，不以catalog行数冒全实现。完整独立复核、精确Windows、正常扫描安装、VPM/独立ALCOM仍欠。旧429不重派、不切号。
- HEAD仍9cce76f5b172ac4f45a8599249ba82a045ea6f96，仅本地候选修改；未新提交/推送/发布；main/现用索引/Hermes/QQ/真实头像工程不动。当前用户继续开发，非后台自动续作。

## 2026-10-07 当前续接：C#字节/私有通道已验，VP009已修，完整Editor编排仍欠

- 检查点 `Candidate~/evidence/editor-relay-20261007143309-checkpoint.json`；HEAD仍9cce76f，未提交/推送/发布。
- 上轮RW3、Linux EP6（含netstandard2.1参考编译）、81 C#、28 PI/OS/OC通过并已回读；不是Unity/Windows实机。C#通道尚未接实际EditorOwnerProcess。
- 完整VP旧27项因VP009过时字符串断言失败，原报告保留；本轮改为执行实际PC001–014接收断言及缺失/重复/额外负例，完整27项通过。
- 主Agent续接Editor→owner真实控制与重载调度；默认关闭及异常撤权不放宽。其余合同/复核/Windows/扫描安装/VPM与独立ALCOM仍未完成。


用户目标不变：先完成完整实现、自动化与VPM准备，再由本人用ALCOM安装独立测试工程验收。未实现项不是“只待实机验收”。**当前仍没有可安装交付或产品批准。**

## 2026-10-06 owner／运行时私有控制已接通，Editor 编排仍未完成

- 最新入口 `evidence/owner-control-20261006081623-checkpoint.json`。HEAD 仍 `9cce76f5b172ac4f45a8599249ba82a045ea6f96`，仅本地未提交；没有新推送、Windows Actions、发布、main／现用索引或现用 Hermes／QQ 改动。
- 新增 `runtime/reload_control.py` 和 `launcher/reload_owner.py`：原批准摘要不重写，核对完整 read/material cohort；OS 保持的精确 parent/child＋内核对端确认后才传字节；arm／reattach／commit；取消、EOF、超时、错误绑定、已停止任务拒绝，失败清空私有状态；没有远程 approve/resume 工具或授权落盘。
- 已接到 `create_owned_run(enable_reload=True)`、实际 runtime CLI、监督器和 probe。默认仍关闭，Editor 入口尚未启用。probe 在经本地控制确认且有界的交接期不伪报 ready；先排空旧 probe，commit 后重新核验。transport 可空闲到原 run 期限（上限 3600 秒），单次权限交接仍受原批准期限及最多 60 秒限制，不续期。
- OC001–015 包括取消冻结时迟到结果、私有字节过期、worker 取消后 join、真实 OS 通道重附与重复交接、真实受控子进程、伪造 bootstrap 拒绝。OC014 运行实际 CLI＋TLS＋SDK，会话 ID 保持且精确 DELETE200；Unity 批准、证据和 WebSocket peer 仍是 fixture，不是实际 Editor／编译。
- 本轮 167 个逐方法 Python 通过，C# 主组 81 通过（另列 RH9／PC14／WU12／NS18）；源码执行前后稳定，构建／临时根清理。之后只有 OS006 将超限负例 61 改为 3601：首轮 peer 因过期负例等待而超时，原失败保留；修正后的 28 个 PI／OS／OC 逐方法全部通过且源码不变、自然进程树退出／清理／临时 HOME 删除均通过。不能简单求和，各组有重合。
- OC014 初次宽入口虽 exit0，但 SDK 打印 session termination failed；未接受为正常生命周期通过。改为先精确 DELETE，再断开 fixture／停止，最终显式断言 200 和同 session。VP015–025 通过；新 peer verifier 精确逐方法，CI 消费已更新，尚非实际新 Actions。
- 分发摘要已更新；source collect() 确认新模块进入 585 个源码载荷项，不是可安装 VPM／portable build。新 Windows 分支未实测、完整独立复核缺失，旧 429 没有重派或切号。
- 余项仍包括 C# gate 真实字节与本地控制联合、Editor→owner 私有通道／计划内重载编排、其他 B2/B3、正常扫描客户端安装、完整冻结独立复核与 VPM／独立 ALCOM。未实现不标“仅待真人验收”。
- 本节为测试后的状态记账，不是新的可执行源码。

## 2026-10-05 冻结屏障与交易历史本地整合（未独立批准、未提交）

- 当前HEAD仍 `9cce76f5b172ac4f45a8599249ba82a045ea6f96`；本轮为本地未提交修改。旧提交三路Windows已通过；不覆盖本轮源码。未推送/发布/main或现用索引变更。
- 当前证据入口 `evidence/reload-integrated-20261005101950-checkpoint.json`：105个逐方法Python全通过，另经fresh WirePeer编译执行LC006；交叉回读194个公共源码摘要一致。C#主组81、独立PC001–014 / WU001–012 / NS001–018精确集合通过，5项VP015–019消费门槛通过；组间有重合，不加总成独立测试总数。
- 首轮102方法在LC006缺fresh DLL时失败，原证据完整保留。新入口明确把LC006交给fresh C# verifier，未跳过。RL001–014避免与PR暂停测试重名，新增finally/notify_stop在途窗口和两个独立probe拒绝条件。独立 `-I` 入口缺fixture导入已复现并修，14项实际通过。
- runtime仅实现本地、同连接/同SDK session的冻结/解冻屏障；冻结拒绝执行、不续期/重放，断线/停止仍撤权，probe拒绝伪就绪。**尚无跨域owner保活/认证重附/授权迁移，绝非自动编译续接完成。**
- 材质交易历史与live journal/Checkpoint分开：保留原交易及连接/任务/撤回结果，导入零授权且不参与候选provenance；旧记录明确无撤回检查点，新交易仍能建立可撤回检查点。原128交易上限包含历史；导入有界/原子/拒重复，SessionState重复属性/尾部内容/过深JSON拒绝，退出清除。保存失败保留固定告警给下一域，非静默丢失。
- PC011/PC012、历史持久化/UI/保存失败均有首RED后GREEN；PC013/PC014和补充分支为first-green characterization，不谎称先红。实际Unity域重载、Mono/Windows/真人未验收；WU是API doubles。
- 六文件屏障旧有限审查 `deleg_16626dab` 通过；新增测试/CI的 `deleg_98c24069` 遇HTTP429中断，无结论，不重派/切号。后续C#history和CI PC集合变化尚无独立审查。整轮本地通过不能替代独立批准。
- 正常扫描安装、B2/B3、跨域续接全链路、完整源码冻结复核及VPM/独立ALCOM仍未完成。没有改现用Hermes/QQ/扫描器/真实头像工程；没有后台自治续作。
- 本段状态文档为测试结束后的记账更新，非可执行源码变更；测试报告保留运行时原始before/after摘要。

## 2026-10-05 审查修复冻结（非完整产品批准）

- 冻结标签 `readonly-reconciled-20261005043037`：122个唯一Python方法通过；81个C#主组用例通过，原生NS001–018和独立WU001–012另列，不混入主组。
- 整个 `find_gameobjects/by_component` 在Python和Unity最终门控关闭，保留另外五种模式；公开描述与门控已同步，RT036防止描述回归。
- 首轮52文件审查发现S1和L1–L3；S1已有十文件专项复核，本次八文件CI/文案/摘要增量独立复核通过。仅为各自限定范围，不代替完整产品审查。
- 真实Hermes/Codex原生MCP、聊天/交付/同机真实SSH链路、搬迁和最小导出通过；正常DELETE逐端均确认，报告无残留进程/端口和临时根；固定源摘要一致。Unity仍为fixture，不是实机或真人批准。
- VP017–019已纳入122方法的完整冻结入口；CI完整24文件原生输入闭包、WriteUnity工程引用和WU001–012精确集合修复已核验。Linux本地workflow字节回放不等于Windows或真实下载验收。
- 原样插件在现用扫描器被拒；另用官方固定提交 `439334127f012e1ee0685acd5dba288e459af0ec` 的原样v9扫描器隔离复验，仍因`INSTALL.md:40`的`ssh_backdoor`匹配被dangerous拒绝。仅扫描，未安装；未改现用Hermes/QQ/安装器/扫描开关，也未删安全说明。
- 最新精确提交的Windows验证、其余读取族、计划内编译续接、原样安装、VPM生命周期和独立ALCOM仍未完成。此记录不是可安装交付声明。

## 2026-10-05 菜单与已安装包信息（本地四路冻结通过）

- `get_menu_items`复用固定原生resource facade；严格无客户端参数，原生内部仅`refresh=true,search=""`。TypeCache菜单元数据刷新不是AssetDatabase刷新，不执行菜单；独立EditorMetadata操作批准，保留原生失败可回旧缓存/空列表的限制。RT034/NS016/UA019覆盖。
- 菜单冻结`menu-metadata-integrated-20261005030919`通过：117唯一Python、80主组唯一C#/协议、另组NS001–016，真实双客户端NMN001/002与搬迁通过；后续以包信息整合的新冻结覆盖当前源码。
- `manage_packages/get_package_info`复用固定原生Python函数和C#读器；显式ProjectMetadata操作，只准规范已安装包名，拒绝版本/URL/路径、别名、多余参数；不开放Client.List/Search/Resolve、包写入/轮询/注册表。输出包括本地resolved_path，依赖计数/名称/版本及字节预算逐项校验；不是全部包清单。参数范围不支持任意Git版本字符串。
- 包切片RT035/NS017/UA020的首次失败和修正结果保留；C#原生方法按整文件pin原样抽取，未执行分支抛错，API仍为替身。`package-info-integrated-20261005032156`：118唯一Python、81主组唯一C#/协议、另组NS001–017；真实双客户端NPK001/002及菜单/既有完整回归、portable搬迁均通过。
- 四报告536/194/440/496条源码映射全部与回读时当前字节一致；两端各2个会话正常DELETE200，运行时会话空，跟踪35后代/5监听无残留，临时根清理。见`evidence/package-info-integrated-20261005032156-checkpoint.json`。
- 本节时HEAD仍`b0528443ed7b82a4e98610869126e34366659a29`，无新增提交/推送/发布。完整方法族、编译续接、当前源码Windows、扫描允许的实际安装、完整冻结独立复核及VPM/ALCOM仍缺；后续变更不得沿用本冻结作为新源码通过证明。

## 2026-10-05 编辑器元数据切片（本地四路通过，非完整交付）

- 新接入固定上游get_selection/get_windows/get_active_tool/get_prefab_stage；独立EditorMetadata开关/清单、严格无参，选择摘要不授权对象内容，窗口读取不聚焦，不打开Prefab Stage、不调用自定义工具getter。
- 原生返回形状/空值及选择计数、窗口数量有界；窗口原生异常跳过保留，不能宣称完整窗口清单。目录/本地UI/双客户端allowlist/输出合同/分发载荷均同步；首次目录顺序不一致失败保留，已对齐生成器和运行验证器，不放宽检查。
- 四路冻结`editor-metadata-integrated-20261004184703`：116唯一Python方法、79唯一主组C#/协议，另组NS001–015；真实双客户端NEM001/002及既有整轮通过，两端各两个session正常DELETE200，运行时session空、跟踪后代/监听/临时根无残留。portable搬迁passed且清理通过。
- 各报告源码映射（534/192/438/494条）在回读时与当前字节逐一吻合。报告范围不同不互作替代；后续源修改不继承该冻结批准。见`evidence/editor-metadata-integrated-20261004184703-checkpoint.json`。
- HEAD仍`b0528443ed7b82a4e98610869126e34366659a29`，仅本地候选，无新增提交/推送/发布。完整冻结独立复核、新Windows/真实Unity/真人、编译续接、其余方法族、扫描允许的实际安装与VPM/ALCOM均未完成。

## 2026-10-05 工程元数据切片（本地验收；未完整交付）

- 原生get_project_info/get_tags/get_layers以工具facade接入独立ProjectMetadata范围；参数必须为空、独立能力勾选及任务批准，工程绝对路径披露，本地输出合同有界。不是全包清单，也不继承Scenes/资产权限。
- SDK union返回result包裹、原生错误模型丢弃暂停data已定向处理：只保留同请求已核对精确plan的暂停回执；异计划/错误撤权，不伪装成功。RT031/032通过。
- Python `project-metadata-reconciled-20261005020610-all.json`为114个唯一方法全部通过；C#/协议`unity-parent-project-metadata-reconciled-20261005020610.json`为78个唯一主集合、另组NS001–014，源码不变、目录清理。此后仅测试驱动/CI修改；NPC001–004及16项验证器另验。
- 新增NPC004复现合法拒绝structuredContent=null导致测试TypeError，修正驱动不改产品拒绝语义。原始失败位置独立保留，清理错误不再掩盖定位证据。历史一次Codex DELETE超时仍保留，不归因于读取业务。
- `project-metadata-native-fixed-20261005022752-native.json`整轮passed，NMD001/002及既有回归、两端各2次正常DELETE200、源码不变、38跟踪后代/5监听无残留、运行时session空和临时根删除。配套portable已在最终驱动上重跑passed，临时根删除。
- 无真实Unity/真人、Windows新冻结或独立批准；无新增提交/推送/发布。HEAD仍b0528443ed7b82a4e98610869126e34366659a29。完整项目缺口未由本切片抵销。

## 2026-10-04 对象/Animator读取及原生关闭整合（历史切片）

- 关闭阻塞已解决：脱敏观察证实Codex空闲卸载与服务端60秒回收相撞；stdio控制EOF必须先触发原生关闭，再等精确DELETE。固定版本源码核对、NPC001–003以及真实双客户端整轮均通过；未延长服务端TTL、未接受404、未以强制清理代替正常关闭。
- 固定原生`get_gameobject`对象摘要（含原生世界/局部Transform）与`get_gameobject_components`组件类型/ID分页已按资源工具适配接入；明确不开放任意组件getter/属性反射。独立本地开关/清单批准、当前Scene/Prefab Stage输入输出核验、容量、UI和两端工具目录已同步。
- 固定原生`manage_animation/animator_get_info|animator_get_parameter`已接入：仅当前场景的精确GameObject ID；参数名显式有界。拒绝查名、资产、控制器变更、播放/赋值/设置参数及隐式刷新。C#上游reader原样编译测试；Unity API仍为测试替身，不是实机。
- `animator-reconciled-20261004142115-all.json`：112个唯一Python方法全部通过，源码前后不变。`unity-parent-animator-integrated-20261004141536.json`：77个主集合唯一C#/协议ID通过，NS001–013、Console/continuity/binding另列；精确集合一致，自有构建目录删除。不可把分组求和当作产品验收。
- `animator-reconciled-portable-20261004142753-portable.json`：已同步最终两份测试驱动后重新搬迁通过、源码/载荷不变、临时根删除，6个跟踪后代/2个监听无残留。`animator-reconciled-20261004142115-native.json`：真实Hermes/Codex两端NI001/NI002及NA/NP/NR等完整回归通过，各2个会话创建/正常DELETE200，Unity撤权确认、运行时会话空、临时根删除，35个跟踪后代/5个监听无残留。同机SSH与fixture消息不是跨机可信交付、model turn或真实Unity。
- 首轮Python旧精确集合、C#测试替身、Unity `-I`路径误用、native驱动`args`覆盖及其启动错误全部保留；新标签修正复跑，不删除断言、不把启动成功或中途NI通过当整轮成功。
- 原样Hermes候选插件仍被安装扫描判为dangerous（安全说明和source.profile命中）；普通/强制安装均拒绝。未删安全说明、改扫描规则/开关/安装器，未写入现用插件或配置。
- 验证索引：`evidence/animator-integration-checkpoint-20261004.json`。仍为本地dirty候选，HEAD `b0528443ed7b82a4e98610869126e34366659a29`；没有本轮新增提交/推送/发布。其余原生读取、计划内编译续接、诊断clock精确提交Windows验证、不绕扫描的实际安装、完整冻结独立复核和VPM/ALCOM仍未完成。下方关闭失败为历史，不应重复续作。

## 2026-10-04 查找接入及客户端关闭阻塞（历史快照，已由上节替代）

- 本地候选新增 `find_gameobjects`：复用固定上游，显式参数/页长/当前场景及Prefab Stage范围门控；精确ID及结果ID拒绝资产、组件、其他场景。分页仅限返回量，仍先遍历匹配项。尚不是通用读取方法族全部完成。
- 已修 Codex 候选独立配置未列入新工具、WirePeer分页输出与原生 `nextCursor` 契约不符；载荷清单的launcher摘要已同步。现用Codex/Hermes/QQ配置未改。
- 首轮 find-read-20261004114343：运行时88项、C#/协议74唯一ID（另列NS组）、便携通过；这些是该轮源码证据，不是后来所有修改的冻结批准。查找真实双客户端后续NF001/NF002已到达通过点，但整轮仍在NA006关闭环节失败。
- 关闭测试新增NPC001/NPC002：unsubscribe响应不是DELETE回执，缺失/失败回执保持失败。仅延后stdin关闭、以及按固定版本空闲卸载等待的尝试均未让整轮通过。`find-native-idle-unload-60s.json`为超时失败，不能把60秒/75秒预算当成有效修复；暂停新增原生客户端试跑，待拿到会话/线程关闭关联证据再继续。不能删除精确DELETE断言或将强制安全清理冒充原生正常关闭。
- 最新本地校验 `find-close-local-green-20261004121655.json`：Codex配置7项、关闭测试2项、目录1项、便携验证器16项共26项通过；先前UA范围11→13的验证器断言过期失败保留，已同步精确集合并要求UA012/013及NPC001/002。
- 最新搬迁 `find-close-portable-20261004121750.json` passed=true，源码和载荷稳定、临时根清理，6个跟踪后代/2个监听无残留。该结果不覆盖真实Codex正常关闭。
- 失败原生轮已实证运行时会话为空、临时根删除、19个跟踪后代/3个监听无残留；这是安全清理成功，不是关闭功能验收。全部原始失败证据保留。
- 本地HEAD为 `b0528443ed7b82a4e98610869126e34366659a29`；clock/validate/find及本轮修改仍在dirty候选，未新提交/推送，未独立冻结批准/最新Windows精确提交验收。其余原生读取、编译续接、安装整合、VPM/ALCOM仍未闭合；main及现用索引/真实头像工程未动。

## 原生场景层级（已实现，本轮冻结联验进行中）

- 复用固定上游`get_hierarchy`单层分页/子节点/Transform摘要；明确页长1–100、游标0–1000000和非零int32父ID，拒绝名称/路径及其他参数。不刷新、不加载/保存。
- 本地最终执行前使用原生ID解析并核验当前场景/Prefab Stage、有效已加载、非持久化GameObject；拒绝资产对象、其他场景、组件及消失对象。未另建生产层级读取器。
- RT022红绿、RT023参数拒绝；原生精确方法NS005–007红绿、UA011父对象门控红绿。后续冻结/分发/双客户端/Windows结果尚待归档，不能先宣告验收。Unity API仍为测试夹具，实机另验。

## 场景元数据只读（已完成开发验证，不是完整候选/实机批准）

- 实现`f968ba4`：Linux逐方法回归82项、C#既有联合71个唯一ID及独立NS001–004、离线搬迁组合均通过；原失败/中断报告保留。Windows依赖`37111966872`、便携`37111966860`、内核`37111966861`均成功，工件匹配官方digest并核对提交字节，依赖/便携输入分别344/531份；NS001–004和RT015–021均实际执行，非仅YAML出现。
- 原生客户端首轮发现子进程测试允许列表漏列`manage_scene`，修正该测试入口后真实Hermes/Codex均通过NE001/NE002及原NA/NP/NR/Console回归；临时目录、SDK会话、跟踪后代/监听无残留。生产能力未因此扩大，Windows原生客户端、真实Unity/真人仍未验收。
- 当前只完成三种场景元数据读取。下一步层级、对象/组件及其他通用原生只读仍未完成；不把本切片作为整个reads或产品完成。

- 新增原生`manage_scene/get_active|get_build_settings|get_loaded_scenes`，明确`Scenes`实时工程范围；只接收action。本地中文目录开关和清单批准、最终C#门控、原生输出合同及Codex独立工具列表已接入。不是层级、对象/组件或资产搜索的完成声明。
- 原生Python前置会查询editor_state并可能refresh/compile；候选仅替换该模块前置为当前请求/原计划核验，实际读取仍是原生wrapper/handler。最终Unity LiveConnection在编译、更新、Playmode时拒绝；未开放状态旁路、加载/保存/自动修复或任意执行。
- RT019先因范围未支持失败，再因原生前置失败撤权复现，修后通过；RT020/RT021为初次通过的拒绝与不查询/刷新characterization。NS001–004编译固定上游的原样parser/dispatch/reader方法；未走方法为抛错替身、Unity API替身，**不是完整上游文件编译或真实Unity验收**。UA010已复现本地适配器将Scenes误当文件，增加实时范围证据；本轮冻结/双客户端/分发/Windows结果见上方；这仍不是Unity实机验收。

## Console / 诊断前轮最终结果

- `3d0ae40`已提交推送。Console原生双客户端/SSH通过，运行时79项、C#既有70个唯一ID、Linux独立诊断24项分别通过，非跨组累加。
- Windows依赖`37108626071`绑定`958b0fc`成功；Windows便携`37110061329`绑定`3d0ae40`成功。公开工件严格校验官方SHA-256，源码before/after并逐字节比对各自git提交后接受；不把不同提交混称一个冻结批准。
- Windows本地诊断DW001–003均执行成功：detached拒绝、标准输入不能覆盖本地否决、本地批准后真实stdio读取及EOF清理。真实控制台/模拟操作者，不是Windows原生Codex或真人验收；强杀磁盘生命周期、完整安装入口仍未完成。完整候选/最终独立复核/VPM/ALCOM仍缺。

## Console 原生只读整合（此前过程记录）

- 显式Console范围、双侧get参数门控、原生输出合同及中文目录开关已接入；clear仍拒绝。复用固定上游Python/C# reader，不是第二套日志读取实现。实时日志不承诺快照，truncated的total只作下界。
- Linux原生Hermes/Codex各自批准、分页、跨会话拒绝、停止/拒清空已实际执行；编译C#运行真实上游反射handler，Unity LogEntries与本地批准仍是fixture。原NA/NP/NR回归随同执行，没有模型请求或真实工程操作。
- Console实现 `7cfa2a7` 已推候选分支。分发清单绑定实际实现字节；搬迁Python/Node组合入口发现Console但无权时拒绝get/clear。同机真实OpenSSH＋原生Hermes/Codex端到端夹具也通过，非跨机/真人/真实Unity。
- 诊断退出缺陷已在隐藏目录转发上确定性复现：Visibility隐藏资源/模板/提示词却仍查询后端；本地middleware直接返回空目录，外层会话/快照有效性检查不变。修后20轮、100个Node子进程均exit0；搬迁组合再核其他会话及撤权后的目录查询均拒绝、不启动后端。初次非零退出和RED证据保留。
- 新标签 `console-reconciled-20261003075408` 的78个逐方法回归全部通过，便携组合通过且源码/载荷稳定、运行根清理。旧重复标签一轮被验证器拒绝（没有实际运行这些用例），不能算回归通过或78个功能缺陷；每个历史原始失败报告仍保留。
- Windows首轮 `37107109282` / `37107109299` 分别因漏改工具数与UA测试编号集合失败；本地已改为完整工具集合/新增编号合同，VP14与SP9通过。该提交内核CI成功；新修订Windows CI及最终独立批准仍待，不与旧提交证据混为全绿。无VPM/ALCOM交付。

## 自包含诊断分发（当前增量）

- 实现 `f374a9eb1a6e82470246dc9e65f33e77e009b7e1`、验证器修正 `bfc7b1787b0a835381a969ae85dc5c98a4e5f16f` 已推候选分支；独立Node/filesystem及Python组合构建、搬迁、默认相对入口、真实SDK读取/拒写/越界/撤权/篡改拒绝在Linux和Windows完成。固定Node22.23.1及106包npm锁；缺失bundle禁止系统Node/实验目录fallback。
- Windows组合run `36970356598`，内核/依赖证据分别绑定实现commit；官方artifact digest、完整before/after与git原始字节、后端及许可证payload hash已回读。父级证据 `evidence/diagnostic-combined-windows-acceptance.json`、`diagnostic-implementation-ci-readback.json`。7项HANDLE内核与6项Job归属测试分组通过，不跨组累计。
- 初次组合失败保留：Linux错误纳入Windows专属控制台测试，改显式平台选择；Windows TEMP 8.3别名比较失败，仅规范化测试自建输出，不放宽生产路径策略。诊断完整旧套件在搬迁backend上Linux复跑，PTY仅为模拟操作者；模块式导入与执行顺序等父级验收修正不冒充生产缺陷。
- `diagnostic-batch-cleanup.json`核本批记录51个本地PID均消失、组合临时根清理；源码导出树与构建证据保留。尚缺Windows本地审批控制台全链/强杀磁盘清理/完整客户端安装入口，不能称独立诊断整体验收。仍无VPM候选ZIP、ALCOM入口或最终独立批准。

## Hermes 固定目标连接（候选源码，未安装）

- `clients/hermes_connection.py` 接收可信宿主已交付的内存凭据，固定 `127.0.0.1` HTTPS `/mcp`，独占单叶证书信任并核对输入pin，禁CA授权/环境代理/重定向/SDK流重试与续传。复用安装Hermes的MCP SDK与HTTP库，而非修改原生MCPServerTask的全局行为；原binding/conversation直接复用它的peer接口。
- 单任务持有SDK生命周期，初始化与目录回合完成后才准入；HTTP会话ID固定，空会话/换ID拒绝。到期主动关闭，重复取消等待精确清理，DELETE失败不再按SDK静默返回冒称清理成功。旧绑定会因peer.session清空而拒绝调用，不自动注销仍由宿主持有的agent快照，不自动停止模型turn。
- HE001–HE014真实SDK＋HTTP替身通过；HT001–HT008真实TLS/原生AIAgent执行器＋fixture消息通过，含错证书、错bearer、污染代理环境与闲置到期。修复前RED保留：输入准入、到期、路由/重试、会话替换、DELETE失败、初始化未完成即ready、连续取消、HTTP构造异常、无状态会话、307携合法MCP正文和CA授权。HE011/HE012首次通过的characterization单列。
- 实现 `19800be5c0864420c788df9dc8fd078884b8dfba` 已推送候选分支并读回。617份冻结输入与提交原字节一致；HE14/HT8、HC11/HA15/HN5/HB5/HS4/HR6/NA6/NP4、直接兼容和打包4/布局6分组通过，不跨组累计。12份冻结报告归档，测试临时HOME、源码导出树、跟踪进程/端口/会话均核验清理。
- Windows CI `36832384400` success；artifact `11147721439` 原ZIP匹配官方digest后读回：490源码与提交及运行前后一致，便携28回归、PS4/ECP2通过，74份wheel报告对应锁、99份许可证正文匹配清单hash，下载归档及运行临时根清理通过。三个宿主模块仅Windows语法编译，HE/HT仍为Linux证据，不冒称Windows Hermes。
- 本轮总证据 `evidence/hermes-connection-parent-acceptance.json` 与 `hermes-connection-frozen-source/`。保留首次RED和测试清单误用MCP1模块名的失败；按实际MCP2模块改正清单后原生复测通过，没有因此修改生产连接逻辑或放宽断言。官方下载401后仅用公开镜像，须与官方digest严格相同；父级读回曾漏写许可证texts/层级，核对实际目录后完成校验。
- 不改变现用Hermes/QQ、Unity工程或权限门控，不发送模型请求。可信跨机交付、用户绑定/网关激活、真实项目身份/人审、重载续接、独立复核与完整VPM/ALCOM仍未实现/验收。父级审阅不是独立批准；没有安装ZIP或发布。

## Hermes 新会话构造（候选源码，未安装）

- 新增 `clients/hermes_conversation.py`：以原生AIAgent构造、enabled_toolsets与随机运行时session_id装入当前绑定；保留原生搜索/描述/调用入口。构造返回前核对工具与身份、深复制schema，不热改已有agent或继承历史授权。
- 构造失败仍关闭部分实例；取消时先撤绑定，再等待迟到构造结果和原生close；连续取消不能丢弃清理。close使用本入口生成的精确身份，不因构造异常误清理其他会话。宿主仍须提供已认证独占peer与可信模型配置、协调在途turn；本模块不解决可信凭据交付/网关安装，也不能强杀卡死线程。
- 新HC001–HC011合同以真实registry/原生schema装配加确定性agent/peer替身验证；HN001–HN005以真实AIAgent构造和执行器/TLS验证双会话搜索/描述/调用隔离、旁置observer与精确关闭。工具消息由fixture直接提供，没有model turn。源模块不打入Unity Runtime~。
- RED/诊断保留：连续取消提前返回、异常构造close身份及其他构造合同已复现后修正；搜索首轮错误用原始工具名而非实际description，改用现存Unity描述词，未放宽目录/调用隔离。初始原生构造尝试4次模型上下文元数据探测，测试守卫在DNS前拦截；隔离HOME显式非秘密context_length后实际0次外连尝试，现用配置未动。
- 实现 `bec0aa235029b0aaa5b6e9f44ca843314d6fd1bb` 已推送读回；615份冻结输入与提交原字节一致。HC11/HN5、原HA15/HB5/HR6/HS4/NA6/NP4与直接兼容、打包4/源码布局6分别通过，非跨组求总数。Windows CI `36827276510` success，artifact `11146016332` 先匹配官方digest再读回：488源码与提交/运行前后一致，便携28回归及PS4/ECP2通过，74份wheel报告对应锁、99份许可证正文匹配清单hash；新增两个宿主模块仅做Windows语法编译，不是Windows Hermes。
- 证据 `evidence/hermes-construction-parent-acceptance.json` 与 `hermes-construction-frozen-source/`；13份冻结报告逐字节归档，冻结树、临时HOME及跟踪进程/端口/会话清理通过。公开artifact官方下载401后使用公开镜像，仅接受与GitHub官方digest完全一致的原ZIP。不修改现用Hermes/QQ/Unity，父级静态审阅不等于独立批准；仍无安装ZIP/发布、真实Unity/VPM/ALCOM验收或共享网关激活。

## Hermes 会话绑定适配器（上一切片，未安装）

- `clients/hermes_binding.py` 为新增宿主侧模块，不是只增加测试：复用原生MCP连接、schema转换与注册表CAS，提供按可信运行时 `session_id` 和随机连接代次隔离的工具快照；模型参数/任务ID不能代替会话身份。停止仅撤自己仍持有的条目，旧快照/旧回调不能转接到新连接。
- 不接收凭据、不启动客户端、不改现用Hermes/QQ配置。宿主必须提供已认证的独占连接，并在新会话构造时安装快照；**可信凭据交付及实际网关会话构造仍未实现**。模块不混入Unity的Runtime~载荷。
- 冻结源码HA合同15项、HB真实分发/TLS5场景、原HR6/HS4/NA6/NP4与直接兼容全部通过，分组不相加。打包门槛4/源码布局6通过；秘密扫描、各会话创建/DELETE、后代/端口/临时home清理通过。首轮原生发现Hermes的slotted对象不能被weakref，以HA014先RED后修正为弱Binding所有权表；HA015复现并修正注册清理异常时仍须停止对端。原失败保留。实现 `05d07300b2793812792a74969822b00928e070c9` 已推送读回；Windows便携CI `36822081110` success，artifact `11143479153`匹配官方digest；486份输入与提交/运行前后一致，便携28项、PS4/ECP2通过，74份wheel报告对应锁和99份许可证清单hash回读。Windows新增宿主模块只做语法编译，不把Linux HA/HB当作Windows覆盖。
- 本阶段记录 `evidence/hermes-binding-parent-acceptance.json`；冻结证据已逐字节归档，冻结树/临时home及跟踪后代/监听/会话清理核验完成。下载官方artifact返回401后，仅对公开仓库使用镜像，原ZIP先核官方digest再解析；没有索取/保存新凭据。
- 契约与复现见 `clients/README.md`；本阶段不自授独立批准，不等于真实Editor/模型turn/Windows Hermes/完整Candidate/VPM/ALCOM，不生成安装ZIP。

## 本地客户端角色选择（当前）

- 实现 `8d897118614a96a16e7b5e07c4ca996eb02c8731` 已推送候选分支并远端读回。窗口新增独立 Hermes/Codex 开关，初始均关闭；启动时固定选择，已有 owner 时禁改。默认只签发 Unity 与内部只读 probe 凭据，未选用户角色不签发且服务端不接受。角色列表严格、不可变、拒绝非法值/重复/旧格式，不新增远程批准或选择接口。
- 私有启动配置与回执升级到版本2，C#在连接前精确核对角色列表；缺少、旧版本、错序、重复或扩大选择均拒绝。现有调用方默认不开放用户角色；原生互通测试显式选择两者。测试CS003/CS009证明即使持有同一运行有效签名的未选角色令牌，验证器与真实TLS HTTP仍拒绝。CS007实际编译生产C#启动/回执路径，测试owner为合成进程；不是Unity真人点击验收。
- 冻结运行时 **113/113**，其中新增Python选择测试 **9项**，不重复相加。原C# **67个唯一ID**、身份绑定 **7项**、暂停门控 **5项**、C#选择 **CS007** 分组通过。Linux真实Hermes/Codex原NA **6场景**、NP **4场景**及无Unity兼容模式复测通过；未运行模型turn或登录，未修改真实客户端配置。
- Windows `36764250414`、便携 `36764250401`、内核 `36764250512` 均success且绑定实现提交。新增Python选择9项和C# CS007、原认证/绑定各7项、暂停门控/响应分类各5项通过；内核进程归属6项、HANDLE诊断7项分别通过。依赖与便携CI分别 **311/483** 份去重输入前后及当前提交字节一致；四个artifact ZIP先匹配GitHub官方digest再读回。Windows仍未覆盖真实双客户端或Unity Editor。
- 便携回归Linux **29** / Windows **28**，每端原包内选择器4项/启停2项通过。每端 **74** 个依赖归档核对锁定hash，并将Linux **85** / Windows **99** 份许可证正文与精确wheel原文或固定上游补充文件逐字节比较；许可证清单中的独立验证标志原本为false，未把清单完整误当归档核验，而是另行完成此项。
- 运行时逐方法清理、C#子进程/进程组/构建目录、原生会话/后代/监听、便携运行目录和本轮源码导出树已核验清理；源码报告逐字节归档。RED/成功证据均保留。父级产物读取中曾误用路径/字段和分组ID，已按实际schema核验；没有因此修改生产门槛或测试断言。总记录 `evidence/client-selection-parent-acceptance.json`。
- **仅完成本地角色准入，不是可信凭据交付或软件品牌认证。** 仍缺用户可用的分别绑定/凭据交付、跨重载/重连安全任务续接、真实Unity/真人批准、Windows真实客户端、最终独立复核及完整Candidate/VPM/ALCOM。没有安装ZIP、正式发布、main或公网VPM索引改动。

## 同连接本地暂停/继续（历史）

- 实现 `86b3fd8241572feced526e784ebcdb343d38aa77`，测试/CI修订 `6e4bcd006419e576d71d4262a7635391bf3e39aa` 已推送候选分支并远端读回。复用已有两类门控的计划、锁、证据和期限，仅新增本地窗口按精确ID/digest暂停/继续；无远程pause/resume/approve/renew入口，无自动启动/重连或用户配置修改。
- **暂停保留原task/plan/digest/client/connection及绝对到期时间**。读取/材质执行返回明确 `plan_paused` 错误且不调用原生操作。运行时只为仍有效的精确暂停回执保留映射，其他失败照常撤权。继续复用定点证据/能力/身份核验；候选、原件、依赖、工程、连接、期限变化或核验中撤权即撤销。StopAll/SDK退出/重载仍销毁授权；材质暂停不释放工程单写锁、不回退、不延长TTL，Approve不能代替Resume。
- PC001/PC002分别完成缺少本地Pause的编译RED→GREEN；真实Hermes/Codex最初被旧Python失败路径销毁暂停计划，保留RED并修正精确回执分类。PC003–PC005为原有失败关闭边界的characterization。PR005本地按钮源码RED→GREEN及既有UA006的实际按钮回调替身覆盖；窗口含完整任务/清单且点击旧行不得批准新行，**仍非Unity真人点击验收**。
- 最终冻结运行时 **104/104**（包含PR001–PR005，不与其再相加）；原C# **67个唯一ID**、SDK绑定 **7项**、新PC **5项**各自通过。已有材质WC/WU/WN **17/10/1项**通过。真实Linux原生客户端NA **6场景**及新增NP **4场景**分别通过，NP覆盖Hermes/Codex各自读取与材质的暂停拒绝/原计划继续；原无Unity兼容模式另行通过。
- 便携回归 Linux **29** / Windows **28**；Windows `36760968646` 与 `36760969017` 均success且绑定测试修订。原认证/绑定各7项、新PC/PR各5项通过；两组 **308/481** 份去重输入前后与精确提交字节一致。公开artifact镜像ZIP均先匹配GitHub官方digest再读取；没有凭据补录。Windows本轮仍不包含真实Hermes/Codex或Unity Editor。
- 失败保留：首次运行时103/104，BL001对端连接前超时；固定工程ID碰撞可重现 `PROJECT_BUSY`→同类超时，改为每进程隔离工程ID后同一占锁复现实验及最终整轮通过，生产lease不变。原失败缺少监督器receipt，**不声称其唯一原因已证实**。首次Windows `36760393719` 的CB007启动readline超时保留；原握手时限未放宽，最终原测试通过但初次计时根因仍未定。额外PR默认cp1252解码失败在Linux仿真再现，显式UTF-8后通过；CI新增暂停检查独立执行，不再被前项失败遮住。
- 最终原生测试跟踪 **6个后代/1个监听**，无残留，双方MCP会话创建/DELETE对应、计划空；令牌/私钥标记扫描通过。运行时逐项进程组/临时home、C#构建、便携运行根和本轮3个源码导出树均已核验清理；证据先逐字节归档，原失败不覆盖。总记录 `evidence/continuity-parent-acceptance.json`。
- **仍缺**：可信操作员到客户端凭据交付、用户可用分别绑定、跨重载/重连的安全任务续接、真实Unity/真人批准/完整原生模型链、Windows真实客户端、最终独立复核和完整Candidate/VPM/ALCOM。以上只完成同连接本地暂停，不缩减总体验收；没有安装ZIP、正式发布或main/公网VPM修改。

## 真实客户端执行已批准任务的开发验证（历史）

- 测试实现 `e0979f73baaf574124e454c3c3d8bdd604bb1c1f` 已推送候选分支并远端读回。复用生产门控及既有TLS/会话/进程清理机制，本轮只改测试驱动和说明，**没有修改生产授权逻辑、真实客户端配置或Unity工程**。安装载荷不包含测试驱动。
- `tests/verify_native_clients.py --approved-tasks` 在Linux同时使用真实Hermes MCP引擎与固定官方Codex app-server；新编译net8读取/材质门控，隔离文件后端，测试驱动单独持有本地批准管道。NA001–NA006 **6个场景**全部通过：分别批准、跨客户端隔离、真实调用后的显式停止、旧授权复用拒绝、候选不回退/原件不变、两客户端实际DELETE撤销各自两类计划。签名凭据由测试驱动发给指定子进程，**不是面向用户的可信交付实现**。
- 原有材质门控为**每工程一个写任务**。早期测试错误假设可双写，正确收到 `project_write_busy`；测试改为验证不能抢占/跨客户端停止，前者停止后后者新批清单接手，未扩大生产权限。新读/材质计划均重新批准，**不冒称已实现保留任务授权的暂停/重载续接**。
- 精确冻结 **373份源码输入**及原生客户端/.NET/上游Response.cs字节；新场景6项、原无Unity兼容模式、原C# **67个唯一ID**、SDK绑定 **7项**分别通过。原材质组WC/WU/WN分别 **17/10/1项**，源码载荷/打包关闭门槛分别 **6/4项**通过；不跨组求总数，不把旧99项运行时或Linux便携结果算成新增复测。
- Windows run `36756325692` 与 `36756325458`均success且绑定上述commit。认证/绑定各7项、便携28项通过；分别303/478份CI输入前后与对应提交字节一致。直接下载401后使用公开镜像，两个ZIP均严格匹配GitHub官方artifact digest再解包，未发送凭据或放宽校验。**Windows没有运行此次真实双客户端6场景**，不与Linux原生证据混淆。
- Linux最终原生测试跟踪到6个后代、1监听，最终无残留；两条MCP会话分别创建/DELETE成功，运行时会话与计划清空。子进程输出/隔离home令牌与私钥标记扫描通过。编译临时目录、运行home及本轮冻结导出树已移除并核验，成功/失败证据保留；Windows记录临时构建/venv与便携根目录清理成功。证据 `evidence/native-approved-parent-acceptance.json`。
- **仍未完成**：可信操作员到客户端的凭据交付、用户可用的真实分别绑定、保留任务身份的暂停/续接、真实Unity/人审/完整SDK链路、Windows真实客户端、最终独立复核及完整Candidate/VPM/ALCOM。角色名不证明软件身份；真实原生调用＋fixture批准不等于真人/Editor验收。没有安装ZIP/正式发布，main/历史发布/公网VPM索引未改。

## 签名主体进入本地批准清单（历史）

- 实现 `0cf96826bae91a9b65f2d422c38f07b9b86b8675`：Unity清单原有 `client_id` 现在由验签后的主体和SDK具体会话组成规范JSON二元组，来自认证请求上下文，不来自模型参数/自报名称。绑定后的同一SDK会话换主体立即拒绝；未认证上下文不缓存会话。沿用现有本地清单批准，不增设重复审批或字段级许可。
- 原生读取与材质计划均保存该身份，SDK请求上下文消失后的DELETE/取消撤权仍使用原身份。编译门控联测验证A/B分别批准，B无法继承A权限或停A的材质计划；A退出只撤销A的两类计划，B已批读取继续可用，候选材质字节不回退、原件不变。**后端文件、Unity API和本地人审均是声明的测试fixture，不是实机或本人操作。**
- CB001–CB005各有RED→GREEN；CB006/CB007为后续隔离及端到端characterization。冻结父级运行时 **99/99**、原C#核心/协议 **67个唯一ID**、新增身份组 **7/7**分别通过，不相加。`tests/verify_unity.py <新证据标签>`新编译门控并逐方法新进程运行身份组，不允许复用旧DLL或跳过。
- 验证/CI修订 `4b7e239f43b3007e72e3724b04b378f1a07c39d7`：Windows run `36753002229`全程通过，认证7项、新身份7项、新编译两类真实C#门控联测及既有入口/TLS/监督器回归通过；**303份唯一输入**前后/提交字节一致，临时构建及venv已清理。
- 默认便携搬迁回归Linux **29项**、Windows **28项**，每端4选择器/2启停通过；Windows run `36753002276`全程成功，CI **477份输入**前后及提交一致。每端74份wheel精确匹配锁；Linux85/Windows99份许可证正文逐字节hash回读通过。没有把开发目录当作安装ZIP。
- 新冻结树真实Hermes MCP引擎/官方Codex原生协议兼容复测通过；各自创建/DELETE一条会话，4个观测后代、1监听和临时home均清理；仍是无模型/无登录/无已批准Unity任务的兼容性测试，不改变其证据边界。未改现用客户端配置或真实Unity工程。
- 首轮Windows `36752269377`失败保留：父级扩充CI文件清单误改嵌入测试argv，另外C#测试夹具主动Abort可能抛OperationCanceledException。分别恢复精确argv、只在显式本地closing状态处理取消；未削弱生产门控/退出断言。Linux便携首轮错误选用研究用full归档，被install-only哈希门槛正确拒绝；改用既定install-only锁定字节后通过，未改锁值。父级读证据时的路径/JSON结构错误已纠正，不伪称每次尝试都通过。
- 证据 `evidence/client-identity-final-parent-acceptance.json`。测试临时目录及两份Git导出树已移除并实际检查；完整成功/失败报告保留。子代理仍暂停，父级冻结验证不自授独立批准。
- **仍未完成**：面向用户的可信凭据交付、真实客户端明确分别绑定与已批准任务停止/暂停续接、完整安装包、最终独立复核、真实Unity/VPM/ALCOM。这里补齐的是已验签主体到清单/撤权的传播，不是客户端品牌证明；角色名及持令牌均不证明软件身份。候选分支开发不等于发布，main/历史发布/公网VPM索引未改。

## 原生客户端兼容性与内部探针增量（历史）

- 生产增量 `eaaad18d111ec7e3db60e1ec800221116e7e9321`：内部就绪探针改用独立 `probe:<run>`，不再持Hermes角色令牌。已签发有限身份仅发现/调用`agent_status`；prepare、stop、材质/原生入口在派发前拒绝，Unity audience拒绝该角色。RI005、AU006、AU007保留RED/GREEN。
- 冻结父级runtime **99/99**、新编译C#核心/协议 **67个唯一ID**通过，分别280/159份输入前后及当前生产字节一致。各组不相加；C#使用Unity API替身，不是Editor/Mono验收。
- 原生验证器 `422c20caab267fa96b2d01253afbc9717242ce8e`：实际安装Hermes MCP引擎和固定官方Codex0.159.2 app-server分别执行认证工具调用，未连接Unity时拒绝；无批准计划的stop只返回本地停止且`unity_confirmed:false`。两客户端各创建/成功DELETE一条独立会话；runtime会话清空，3个观测后代/1监听、临时home均清理；359份Candidate输入和原生入口字节稳定，输出/临时文件未发现生成令牌或私钥。未调用模型、登录账号、改现用客户端配置。Hermes整体agent工具暴露与完整依赖锁未在这里验证。
- 原冻结native轮捕获3个残留Git后代，失败并安全清理，未覆写为通过。取证定位到Codex默认插件同步对`openai/plugins.git`的ls-remote链。仅测试home显式关闭原生`features.plugins`后，三次带取证复测和最终Git树复测通过；这是缩小测试无关活动，不是修复/批准上游默认插件生命周期。
- 同一生产增量的默认便携搬迁回归：Linux **29项**、Windows **28项**，每端选择器4项及C#启停2项通过。Windows最终run `36741024583`、476份受检文件前后/提交一致；Linux453份冻结输入一致。各端74份实际wheel精确匹配锁，85/99份许可证正文分别回读hash；源码/搬迁载荷/清理均核对。
- Windows认证组首轮run `36740421526`在AU006出现`ASGI callable returned without completing response`并超时，保留失败及清理产物。CI改为相同7方法各在新进程有界运行，不减少断言、不跳过；`85078c5a8c9e5d30d13bbd70d4a32941d59794e5`的run `36741472151`全程通过，7项认证、身份5、TLS5、入口6、监督器4、Editor入口8、C#2等均通过；294份源前后/提交一致、venv及构建清理。未证明原共享进程失败的全部内部根因，不称已修复SDK。
- 证据：`evidence/native-clients-final-parent-acceptance.json`；接口/来源/重放边界见`CLIENTS.md`。候选分支已推送读回，main、历史发布和公网VPM索引不动。
- **仍未实现/验收**：可信客户端凭据交付和显式分别绑定，真实批准任务的双客户端停止/撤权，任务暂停续接、完整安装包、独立复核、真实Unity/VPM/ALCOM验收。Codex自定义CA是附加信任而非独占证书固定；令牌角色也不是客户端品牌证明。没有生成安装ZIP或对当前产品自授批准。

## 默认便携入口增量（实现 `5ef9b5d`，历史）

- 本地窗口默认选择随包固定Python，不再要求用户填写解释器路径。外部Python仅在明确勾选“开发测试”后使用，选项/凭据不持久化。缺包、错误平台或入口校验失败不会搜索PATH/回退外部Python，也不会自动创建连接或批准任务。
- builder在依赖/许可成功后写入固定格式`Runtime~/portable-launch.json`；启动前C#核对Linux/Windows x64、Python3.11.16、解释器/两个引导文件的字节hash，拒绝重复/未知字段、额外路径、缺失/变化、超限和既有链接/junction祖先。**只是入口完整性**：清单未签名、不扫描所有依赖、不是对抗能替换包的本地进程，也不保证hash到exec原子身份；见`PORTABLE.md`。
- 同一实现提交`5ef9b5d5f62c35baf5dc0c5c43cba5d77898dbba`：实际搬迁载荷后，C#仅接收包目录并走默认解析，Linux28/28、Windows27/27相关Python回归通过，每端ECP001/ECP002启停/Dispose通过、PS001–PS004固定路径/描述/入口字节/链接拒绝通过。Windows CI`36734831866`成功，473份文件前后/提交一致；Linux451份冻结输入与提交一致。各组不相加。
- 编译后的核心/协议67个唯一ID回归通过，源码稳定；源载荷UI替身实测默认模式拒绝typed外部Python、显式开发模式可启动/停止/重载，9后代/3监听清理。真实便携链路Linux另有6后代/2监听清理，不混合计数。测试临时目录与导出源码树已删除并实际检查。
- 一次并行源UI回归退出3且外层clean=false，安全清理完成；未记录到精确拒绝分类，不能确定根因。待其他测试退出后同一源码隔离重跑通过。原失败及`-I`漏加测试辅助模块路径的调用错误均保留。不是“所有尝试都通过”。父级证据`evidence/portable-entry-final-parent-acceptance.json`。
- 新builder用例PP009、选择器PS001/PS002与默认UI行为有RED→GREEN；哈希/链接补充用例属于通过后的characterization，不冒称都独立复现。小组回归：便携9、driver4、源码布局6、许可5、原打包器4通过；仍无新独立批准。
- **仍未完成**：最终安装包整合、真实Hermes/Codex分别绑定与停止、任务暂停续接、最终独立复核、真实Candidate VPM/Unity/ALCOM验收。没有生成安装ZIP；候选分支开发不等于发布，不改main、历史发布、公网VPM索引或真实客户端配置。

## 便携运行时增量（实现 `87a0b1d`，历史）

- 已实现并实际运行**便携开发运行目录**：固定 Astral PBS `20260929` / CPython `3.11.16`，Linux GNU x64 / Windows x64，归档hash、对应完整发行的元数据与每平台19份许可证原字节绑定。不是空白操作系统/所有Unity版本保证；Linux glibc、Windows vcruntime前置与最终分发合规仍需产品层审查。细节见 `PORTABLE.md`。
- 同一实现提交 `87a0b1d5d84cb403cd22b88eef250b6ea5171b64`：从独立Git树构建并搬迁后，Linux **28/28**、Windows **27/27**实际Python身份/引导/所有者/TLS回归通过；每端实际C#私有管道/TLS/MCP启停和Dispose **ECP001/ECP002**通过。Unity wire仍为synthetic fixture，不是Unity Editor/Mono或客户端品牌身份验收。各测试组不相加。
- Windows Actions `36731626511`成功；471份完整受检文件前后及提交字节一致。Linux434份冻结输入对同一提交一致；载荷分别9419/9094份前后不变。Linux外层跟踪6个后代/2个监听，均消失；Windows子进程/监听用既有C#回读断言，不能冒称有Linux相同外层pidfd证据。任务临时目录及本地检出目录已实际清理。
- 每端74个实际wheel的版本/hash逐项匹配活动锁。Linux因在线600秒下载超时，改为经过官方URL/hash校验的wheelhouse，通过pip原生`--no-index --find-links --require-hashes`离线安装；报告必须是该精确目录的非软链接wheel并再次核对字节。Windows在线官方PyPI安装通过。缓存公共wheel留作构建复用，不给运行时继承代理或凭据。
- 当前解释器内实际wheel许可证正文Linux85份、Windows99份已再次回读hash核对，每端额外19份Python发行许可证保留。收集器的“未独立验证最终再分发”标志不被父级清单改写。
- 修正Windows NuGet编译夹具环境：只给编译步骤必要系统路径，把APPDATA/LOCALAPPDATA限定在任务临时profile，不改变runtime环境白名单。失败后先执行TemporaryDirectory退出再记录实际清理，原异常继续上抛。编译超时保留部分日志，不放宽90秒门槛。7+1便携边界、4个driver、6个布局、5个许可、4个原打包器检查分别通过。
- 先前Windows短路径fixture错误、NuGet缺路径、90秒编译超时与Linux在线超时均保留。编译重跑通过不证明已解释原超时原因；不把历史失败覆写成绿色。接受记录 `evidence/portable-final-parent-acceptance.json`，只属父级分层验证，未获新增独立批准。
- **仍未完成**：把便携目录整合为最终可安装Candidate及默认选择入口、真实Hermes/Codex各自绑定/停止闭环、任务暂停续接与完整约定能力、最终独立复核、真实Candidate VPM操作与Unity/ALCOM验收。没有生成安装ZIP，main/历史发布/公网VPM索引及真实客户端配置未改。

## 源码载荷与许可证增量（2026-09-30，历史）

- `package/package.json`、候选Editor程序集定义、README/LICENSE/第三方说明已创建；此前“manifest尚不存在”的描述是旧阶段。`distribution/assemble_source.py`按309份固定输入哈希在内存组装658份源码/meta文件：真实Editor、`Runtime~/launcher`、runtime、diagnostics、固定native和修订SDK；原有GUID不改，新GUID确定性生成。不包含测试/日志/凭据，不联网安装、不生成ZIP、不签发批准。
- 5项源码布局检查通过：实际入口路径/许可证存在、重复GUID拒绝、大小写别名拒绝、确定性meta及独立批准门槛、源码漂移/软链接拒绝。沿用打包器4项回归通过。源码布局不等于完整运行时发行或Unity importer验收。
- 跨语言验证已把指向工作树的Runtime~软链接换成实际复制的组装载荷：真实C#进程私有管道→Python→TLS/SDK→门控及显式窗口控制器链通过；658份载荷前后不变，外层跟踪9个后代/3个监听均消失。Unity API和人审仍是fixture，不冒实机验收。
- `distribution/license_inventory.py`只读取当前平台锁定版本，逐份核对已安装wheel的RECORD，保留所有识别到的LICENSE/NOTICE和声明文件；漏声明文件、正文漂移、补充许可版本/hash/路径错误拒绝。5项检查通过。Linux74个有效依赖已收集85份正文记录；这不是Windows清单或CPython许可验收。
- `fastmcp-slim 3.4.7`的官方wheel与sdist未带许可证正文。补充的Apache-2.0 LICENSE固定于上游提交`758397efa66e2cedac95ada540001bc44a95a646`，上游slim pyproject与官方sdist逐字节一致；来源/正文hash随`distribution/license-supplements.json`记录。不是凭包名/表达式猜许可证。
- 本轮实现提交`6cc16d5030d4f36f39dee63c024f031029acff07`，授权候选分支。Windows Actions `36624382991`通过：许可证5项、编辑器入口8项、实际C#2项及原身份/TLS/监督器回归均通过；292份源文件前后/提交hash一致。74个Windows依赖的99份许可证/NOTICE正文已回读核对，pip原生报告的74个实际wheel版本/hash均属于锁中对应条目。接受记录`evidence/licenses-parent-acceptance.json`；这层补充验证不修改收集器本身的边界标志。无新独立批准。
- **仍未完成**：便携CPython及目标平台完整依赖发行/二进制来源整合、真实Hermes/Codex分别接入及停止闭环、任务暂停/续接和完整约定功能、独立复核、真实Candidate VPM/Unity/ALCOM验收。源码组装器不提供降低`build_candidate.py`门槛的入口。

## 编辑器所有者增量（2026-09-30，历史）

- `evidence/editor-owner-final-parent-acceptance.json` 核对父级runtime **96/96**、新编译C# **67个唯一ID**、实际C#→私有管道→Python→TLS/SDK→门控链。各组不相加；源码前后稳定。Unity API、原生业务handler与人审仍为声明的替身，不是Unity/Mono或完整产品批准。
- Windows固定提交 `2782d9291bf4236d0434468f1d3ee6be5cf91d47`，Actions `36620572994`：编辑器入口8项、实际C# owner 2项全部通过，288份文件的前后/提交字节hash一致，临时venv与C#构建目录均已删除。CPython 3.11 Windows venv redirector先只读解析，再直接调用实际解释器并使用CPython本身的venv hint；严格子PID/父PID检查未放宽。不是跨版本Python保证。
- Linux重载的孤儿runtime先由外层pidfd/监听检查复现；修复为撤权后关闭私有stdin并有界等待所有者自行清理，Linux不以直接Kill伪装成功。最终外层跟踪9个后代、3个监听，均清理；测试结束另查未发现候选runtime/launcher残留。此为正常停止/Dispose/父退出范围，不增加Linux监督器SIGKILL等价Windows Job保证。
- 本地窗口显式启动/停止已接实际所有者控制器；打开/导入/重绘不启动，连接不授予任务，停止不回退文件。编辑器生命周期先撤权，清理不确认则保留阻断，不自动重连。测试使用Unity API替身；真实窗口导入、重载与Mono仍待集中验收。
- 初次95/96回归因并行fixture共用工程标识触发正确的 `PROJECT_BUSY`；双进程已复现，再只隔离合成测试标识后96/96通过。生产工程互斥未改。早期Windows重定向/预检失败、残留清理失败及纠正记录均保留，不覆写为通过。
- 本轮补齐候选分支的开发源码快照、测试与复现入口，仍不是可安装工件。`package/package.json`当前**尚不存在**，便携运行时、完整manifest/LICENSE/meta清单未完成；不借合成VPM包或源码快照冒充Candidate安装包。
- **仍未完成**：真实Hermes/Codex分别绑定与停止闭环、任务暂停/连续性验证和完整约定能力、完整分发、最终独立复核、真实Candidate VPM操作及Unity/ALCOM。子代理仍暂停，父级测试不自授独立批准。main、历史发布和公网VPM索引不改。

## 启动与认证增量（2026-09-30，历史）

最终核验：`evidence/bootstrap-owner-final-parent-acceptance.json`，当前源码runtime88/88、新编译核心/协议67唯一ID、Windows run36604908865对应commit2c17f70身份4/TLS5/入口6/监督器4全部通过、零skip；281份Windows源hash前后/本地一致，venv清理。实际受监督C#门控联调、probe成功DELETE、进程/线程/监听清理通过。各组重叠不相加；这是父级有限验证，不是完整产品批准。

- `runtime/__main__.py`不再开放匿名开发服务。`owner_bootstrap`为本地所有者生成单次运行配置；子进程只收到公钥策略和内存TLS材料，不收到客户端Bearer或JWT签名私钥。配置绑定工程/端口/有限期限，拒绝重复JSON键、未知字段、错类型、过期/错工程/错误私钥，先校验再监听；到期自行退出。`take_environment`单次消费不等于操作系统防重放，环境持有本身也不证明进程/品牌身份。
- `launcher/owned_run.py`复用既有受限监督器及真实OS进程所有权实现。监督器创建runtime子进程；探针先核对TLS身份再通过SDK读取受控Unity状态，之后任一连接丢失撤销ready，不发现/接管既有服务、不重连。显式停止先确认探测session的DELETE，再结束runtime。进程清理/探针结束/SDK删除分别报告，不推导全产品远端撤权。
- 每轮Hermes/Codex/Unity角色独立、签名私钥内存签发后不落盘；TLS加载实际采用Windows受限命名管道或Linux sealed memfd，**没有使用已获窄例外的私钥文件路径**。Windows真实内核权限/异进程拒绝/超时取消/骤停清理5项通过；Linux6项通过。4项身份测试通过。
- Windows哈希锁已在干净venv真实安装74个适用依赖并读回版本、pip check与import通过；不再仅dry-run。但便携Python分发、全部LICENSE/NOTICE仍缺。具体证据 `evidence/memory-tls-parent-acceptance.json`、`evidence/windows-bootstrap-parent-acceptance.json`，晚于这些文件的源码须看最新接受记录。
- 实际受限监督器→真实runtime子进程→SDK→固定上游独立C#传输→真实两类门控→候选材质磁盘回读已通过；Unity API、handler副作用、人审仍是声明的替身，不是Unity Editor/Mono验收。证据`evidence/owned-transport-supervised-readiness-final.json`。
- 有限源码已推授权候选分支`candidate-alcom-20260928`，本次最新提交`2c17f7083a711852800dda0ee35b1c76bf3dbfc5`；包括固定native和MCP SDK源/许可及启动链，并非完整源码包。C#候选布局与部分父级runner/文档仍本地。未改main/标签/发布/VPM索引、现用安装或真实客户端配置。
- 原bootstrap-freeze 86/88失败、C#59个通过ID但整体失败、Windows首次2/6失败，以及ready迟到清理反例全部保留。旧匿名wire测试只迁移到`tests/runtime_fixture_entry.py`、原断言AST不变；产品入口不开放fixture开关。LC001–007现逐方法新进程执行，避免第三方全局SSE退出状态影响下一server；七个原方法、全部断言保留，新编译gate仍用于LC006。不是忽略失败或静默skip。
- **未完成**：Unity本地受信IPC/密钥交付和编辑器生命周期、真实Hermes/Codex入口及停止按钮、GUI/暂停/精确续接、完整许可证/manifest/可安装Candidate、真实VPM操作/ALCOM/Unity实机、最终独立复核。没有子代理或新增独立批准。

## 当前状态（2026-09-30，以下旧章节只作历史证据）

- 父级已接通认证私有传输到真实 `CandidateGate` / `MaterialCandidateGate`。全局工具发现不再注册两个候选入口，保留的兼容方法固定拒绝；全局原生连接在线也不能代替自有连接。启动失败、连接变化、撤权、清理未完成、reload迟到回调均按独占连接边界拒绝。
- 真实SDK→认证入口→固定上游C#传输→门控→原生读取/候选材质复制修改/磁盘回读通过；未批、跨会话、撤权后拒绝，原件不变，停止不回退。Unity API、原生C#业务handler、人审仍是测试替身，**不是Unity编辑器验收**。
- 认证 `user_id` registry 与匿名project索引不同的问题已通过真实原生reader复现并修复；自有路由直接检查已准入连接，不借全局发现、匿名登记或重连绕过。StopAsync与断线ForceStop竞争的空引用已修复。
- `distribution/materialize_owned_transport.py` 从固定上游+已记录补丁可复现生成独立 `CandidateOwnedWebSocketTransportClient` 与只覆盖本子目录的asmref。原上游类型/文件不改；新类型无公开发现式构造器。包内生成源/许可证/meta/来源信息已与重建逐字节一致。跨程序集编译和真实TLS链路通过，但asmref实际Unity导入与Mono仍须验收。
- 当前冻结证据 `evidence/additive-owned-parent-acceptance.json`：runtime 68/68；新编译C#核心/协议67唯一ID；分发布局4项；真实传输与真实门控TLS链路分别通过。各组有重叠，**不相加**。核对当前hash、完整告警日志、自有PID、socket/session和临时build清理。原源码漂移失败、旧路由fixture失败全部保留，不由新绿覆盖。
- 没有新委派/独立批准。本轮增量只在本地候选，未新提交或推送。先前Windows内核有限证据不扩大到本轮Unity/引导实现。
- **未完成**：所有者启动的可信sidecar引导、一次性TLS私钥权限/加载即删/异常退出清理、真实客户端和GUI/暂停续接整合、Windows依赖实装、完整源码独立复核、完整许可证/manifest与真实Candidate打包/VPM操作、ALCOM安装。`package/package.json`尚未形成完整产品manifest；这里不是可安装包。没有修改真实工程、客户端配置、main、发布或VPM索引。

## 先前续接状态（2026-09-29，历史记录）

- 已使用授权的 `candidate-alcom-20260928` 分支运行有限 Windows CI；不是发布，不修改 main、历史标签或 VPM 索引。此前“未提交/未推送”仅适用于历史阶段。
- Windows进程所有权 W001–W004 有真实内核证据，见 `evidence/candidate-windows-ci-acceptance.json`；该证据不覆盖 HANDLE取证、进程创建到Job分配之前的崩溃窗口或完整启动器。
- 启动器B1的有限独立复核已完成：L001–L026通过，原None反例零spawn，55个受保护文件hash吻合；见 `evidence/launcher-b1-resume-parent-acceptance.json`。不等于完整launcher批准。
- 真实Windows第三次诊断CI（run `36461636092`，commit `512f9a2e2031fd4877cc23d5cba4db365ff37176`）7/7通过、0skip；产物digest、源码hash、HANDLE/fixture清理已父级核验，见 `evidence/diagnostics-windows-parent-acceptance.json`。仅规范化runner自建fixture并加入正对照，生产别名规则未放宽。旧两次3过4错保留，不计为通过。用户暂停subagent后由父级推进，该fixture增量没有独立批准。
- Linux同长度并发修改已复现：30次改写有15次完整stat身份未变。采用原生F_RDLCK租约拒已有writer/mmap、读取期间写入及不支持的信号/平台环境；主线程同步读取结束释放，非多文件事务快照。34项回归通过，原6项快照和新增6项租约各重复10轮通过；证据 `diagnostics-linux-parent-race-probe.json`、`diagnostics-linux-lease-regression.json`、`diagnostics-linux-lease-repeat.json`。本地源码未获独立批准，Windows上述run仍对应修改前snapshot哈希，不冒充当前全源码冻结验收。
- 材质候选修改已有实现与Linux .NET替身验证，不再是“未实现”；真实Unity入口来路仍未可信绑定，不允许把它当现用工具启用。
- JWT与MCP会话归属增量已跑真实HTTP测试；认证模式下未接好认证的Unity WS入口继续关闭。可信sidecar身份、Unity私有入口及真实客户端绑定仍缺。
- 原生操作中文目录属于描述与审计索引，不授予权限。未知或未审操作不能因目录存在就启用。
- Python哈希锁、干净Linux依赖安装、真实vrc-get合成包五项操作已验证，见 [DISTRIBUTION.md](DISTRIBUTION.md)；没有真实Candidate包或ALCOM验收。
- 本轮已有runtime的55项回归均有通过证据，LC006经原fresh-build入口补跑；另57项C#核心/协议fixture通过，与runtime有重叠不相加。父级汇总 `evidence/resume-parent-regression-acceptance.json` 核对源码、清理及告警；初次漏传新编译C#组件的失败保留，不等于实际Unity工程验收。

## 历史状态表（早期快照，保留证据演进）

| 功能/层次 | 当前状态 | 尚缺内容/阻断 |
|---|---|---|
| P0/P0.2实验 | 已交付，冻结 | 非可安装产品 |
| 成熟MCP复用与v1线格式 | 固定来源，真实SDK/HTTP/WS→编译C#核心WI001通过 | Unity、人审、证据和原生C#读取handler仍为fixture |
| 原生Python入口 | 首轮33项修复后，本轮加入会话结束撤权；六组33个旧唯一用例再次通过 | 新实现尚无独立批准；旧审查汇总NameError不批准结论保留，不继承到新hash |
| 工程/SDK会话隔离 | 有当前只读操作约束 | registry身份自报、可信实例/真实客户端绑定尚缺；loopback不等于认证 |
| Unity本地能力、中文清单与最终门控 | UR001/002/003修复保留；本轮修复旧stop误撤新计划，联合fresh build/生命周期验证57唯一ID通过（含原48） | 新实现尚无独立批准；不等于Windows/Unity编译验收 |
| Unity证据 | 有目标磁盘/.meta/序列化内存及导入依赖hash | 未导入依赖磁盘/依赖内存/引用宿主证据、Windows句柄/junction/TOCTOU、真实懒加载副作用缺失 |
| 停止/取消/SDK会话结束 | 已实现SDK exit/成功DELETE→本地撤权→精确stop；迟到prepare补撤、错误/超时明确未确认；7个LC+2个CLC用例通过，含编译C#核心回读 | 意外TCP断线/无DELETE的崩溃、真实客户端停止按钮、协议cancel→Unity完整闭环仍缺。CC001/002原语义不变；RR003历史超时不计通过 |
| SDK资源清理 | 隔离MCP 1.29.1的POST/GET SSE清理增量已获有限独立批准，SC001–004四项独立通过；父级57项联合/33项回归/2项取消刻画通过 | 非完整SDK/产品无泄漏声明；SC002子进程告警未全量检查。第三方多server进程全局退出状态未修，一侧车一server |
| 任务/编译暂停续接 | **未实现** | 连续性验证、主动停止/意外断线区分 |
| 受控候选内修改 | **未实现，继续拒绝** | 各操作副作用、候选/原件/引用宿主范围、撤回与用户后改保护 |
| Unity失效独立只读取证 | Linux快照6+SDK/stdio3+隐藏writer/真实时钟过期2，共11唯一测试本轮父级通过；24个Node后端正常退出、PID/进程组消失 | 独立报告写入后429中断，不按完成批准；Windows、操作者预览确认、异常退出清理未实现 |
| Hermes主用/Codex备用 | **未接入真实客户端** | 身份/停止/审批闭环；Codex终端不受MCP闸门限制 |
| 受限启动管理 | **未整合** | 复用按需启动、Windows Job Object及清理能力，去除旧Bridge耦合 |
| ALCOM/VPM | **未生成**；打包器4项fixture检查通过 | 真实包/依赖/许可/源码hash/安装升级卸载验证仍缺；无可安装交付 |
| Windows/Unity/真人验收 | **未执行** | 完整候选后再集中验收 |
| 公网发布/现用升级 | **未授权、未执行** | 后续另批 |

## 最新SDK资源增量（有限独立审查已通过，非全产品批准）

- `evidence/runtime-sdk-result.json`：95个唯一ID＝57联合＋33原runtime＋2取消刻画＋3资源/依赖选择测试；程序核对集合不重叠。各轮重复执行不重复计数。
- `dependencies/mcp-1.29.1/`：111个包文件核原分发RECORD；仅一个文件、两处finally关闭有差异。许可证/元数据保留，补丁与逐文件hash齐备，临时目录重建111文件吻合。现有安装库未变。
- 开发CLI在自身进程选择隔离SDK；应用工厂拒绝已载入外部SDK，避免“测试用了修版、真正启动仍用旧版”。测试入口`tests/verify_runtime.py`复用原有界runner；联合验证也把ResourceWarning升级为失败条件。
- SC001先以12个未关闭接收流失败，补丁后全部关闭；SC003正常关闭半途POST后原session可继续用。重跑原版SDK仍分别发现12/18个未关闭流，不通过压警告造绿。
- 初次多server同进程聚合测试超时已保留；单独观测证实SSE全局退出标志延迟污染后续server。测试按一server一进程隔离，每进程3个session；未宣称解决第三方多server复用。
- `deleg_1aaab1f7`已完成且有限审查通过，见`evidence/runtime-sdk-independent-review.json`；独立实跑SC001–003，另加唯一补充用例SC004。SC004使用真实SDK/ASGI而非网络HTTP，证明取消GET后、session关闭前请求所属流已关闭，同session重建GET仍可收到通知，再断开亦能清理；不等于真实客户端停止或异常掉线撤权。
- 父级整合核验见`evidence/runtime-sdk-review-acceptance.json`：原始结果均exit0、无超时/失败/跳过，286个审查源文件hash与当前吻合，113个已安装文件hash吻合，记录的PID/进程组和临时HOME已消失。95个父级ID与4个独立ID有3个重合，合并为96个唯一用例，并非96项全部独立复跑；初次整合因短ID/完整方法名直接比较失败，修正为保留原名及显式映射后核对，失败记录保留。
- 告警口径收紧：SC002成功子进程stderr未透传且未显式启用ResourceWarning，空外层告警列表不能证明该子进程全部告警已检查。SC001/SC003/SC004均有直接流关闭断言；此限制不阻断本次SSE修复结论。父级旧报告保留为审查前快照，不改写成独立报告。完整功能缺口仍以上表为准。

## 前次生命周期增量（历史，非独立批准）

- `evidence/runtime-lifecycle-result.json`：新增9个唯一ID；它们已包含在57项联合验证内，不重复累加。原Python33项和CC001/002另外复跑通过。
- `evidence/unity-parent-lifecycle-final.json`：所有构建/运行exit0、准确ID集合匹配、源码前后hash一致、PID/进程组/临时构建目录消失；`clean_warning_free_run=false`。
- 保留LC001/002/003/005、CLC001的RED。六组回归首轮RF006/007使用的旧Context替身缺少SDK session，补入prepare创建的真实session，所有断言AST未变；重跑33项通过。CC脚本首次模块导入命令不适配，修正运行命令后2项通过；错误记录保留。
- `evidence/runtime-lifecycle-sdk-warning-repro.json`：完全不导入候选的真实FastMCP/SDK HTTP最小复现，观察到4个未关闭内存接收流；监听关闭、server task结束。此为资源警告定位，不是通过验收。
- 未改原native补丁/来源、P0/P0.2、现用安装或真实工程；未派子代理、未提交发布。

## 先前接管的可核验产物（历史，不覆盖新hash）

- `evidence/unity-fix-result.json`：父级接管UR001–003的报告，`local_repair_verified=true`，`independent_approval=false`，`full_product_accepted=false`。
- `evidence/unity-parent-final-isolated-clean.json`：48个唯一ID，UC001–014/UA001–007/UF001–024/UR002–003/WI001；UR001跨程序集build另记。多类型材质/三个身份路径不重复计数。所有build和运行退出0，源码未漂移、自有PID/进程组/临时构建目录消失。
- `evidence/runtime-parent-takeover-regression.json`：六组共33个唯一测试，审查版本源码hash核对无差异，所有运行的PID/组/临时HOME清理通过。
- `evidence/diagnostics-parent-takeover-final.json`：11个唯一测试，固定真实Node stdio后端；隐藏writer的四种调用是同一个测试的子例。
- `evidence/unity-parent-interrupted-build-cleanup.json`：中断子任务360份自有生成构建文件的清单及清理。源码、旧失败证据、原测试、原上游均保留。随后不依赖该缓存的fresh build通过。
- `evidence/native-runtime-verified-current.json`：此前已完成的137文件原生副本/补丁重建验证，本轮未修改native；仅src/main.py和src/transport/plugin_hub.py相对固定基线有差异。

## 不覆盖历史、不混同批准

- 初次Unity独立审查`deleg_57611ad6`的UR001跨程序集CS0122、UR002失败异常泄露、UR003成功数据夹带异常反例仍保留。修复子任务`deleg_2344b2c0`以429中断，父级是接管完成验证，不把failed改成completed。
- 诊断`deleg_fbd8c142`文件中的passed:true和未遇429是写报告时的状态，之后429通知优先；未把中断批次当完成批准。父级实跑11项是父级验证，不伪装独立结论。
- Python`deleg_3d996c88`33项独立运行通过，但审查汇总工具NameError导致它明确不批准。保留原报告；未用父级结论冒充独立批准。
- 服务错误/工具错误不算测试通过；历史harness错误、失败和强制终止也不会被后来的成功抹去。框架错误实际写有“after 1 retries”，不能声称此前绝对零重试；本轮只派新的SDK有限审查，未重试历史失败任务、未切换账户或备用线路。
- 无后台自治续作调度。整个候选仍不通过，不提供安装包；当前有限审查状态见最新增量。

## 2026-10-03：层级复核修正与诊断寿命增量

- 层级读取两项独立审查阻塞已本地修复：Windows执行门槛改为精确RT015–RT024方法/ID集合；C#最终清单容量与Python一致为7，NS008覆盖完整组合及拒绝/撤权。旧失败证据保留，修复不是新的独立批准。
- 快照寿命新增按需标准库清理进程。真实Linux宿主强杀、过期采集拒绝、守护失败撤权、封存后计时删除已验证；独立Node搬迁诊断28项通过。见DIAGNOSTICS.md中的机器崩溃/整体强杀限制。
- 当前增量进入重新冻结回归和独立复核；尚未提交、推送或得到其Windows CI。旧921eef1的Windows证据不覆盖本增量。完整Candidate、客户端安装、计划内编译续接、真实Unity/真人与ALCOM交付仍未完成。
