# 完整候选验收账本

用户目标不变：先完成完整实现、自动化与VPM准备，再由本人用ALCOM安装独立测试工程验收。未实现项不是“只待实机验收”。**当前仍没有可安装交付或产品批准。**

## Hermes 会话绑定适配器（候选源码，未安装）

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
