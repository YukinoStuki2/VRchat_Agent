# 完整候选验收账本

用户目标不变：先完成完整实现、自动化与VPM准备，再由本人用ALCOM安装独立测试工程验收。未实现项不是“只待实机验收”。**当前仍没有可安装交付或产品批准。**

## 源码载荷与许可证增量（2026-09-30，优先于下方历史）

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
