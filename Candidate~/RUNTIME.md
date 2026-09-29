# 候选运行入口：当前有限实现

## 认证CLI与所有者运行配置（2026-09-30）

实际CLI仅接受本地所有者环境引导，TLS和三类签名角色有限期；不提供匿名回退。`owner_bootstrap.py`、`owned_probe.py`和`launcher/owned_run.py`已接通实际子进程与SDK，查STATUS最新证据。环境字段不是远程批准，不承诺同UID恶意进程隔离；单次对象消费不是进程间重放防御。真实Unity/客户端凭据交付仍未完成。


仅 `runtime/` + `native/` 的只读纵向路径，**不是完整候选，不供真实工程使用**。本文不验收Unity C#最终门控、本地人审UI、受控写入、Windows、侧车管理或VPM安装交付；其他并行任务的状态以各自证据为准，不能由Python测试代替。

## 2026-09-30当前认证私有入口增量

下方只读/自报连接描述属于历史阶段。当前 `CandidateJWTVerifier` 为有限每轮身份政策，MCP与Unity角色分离；`UnityIngress`限制一次准入、工程匹配、消息归属、重复注册和过期，并在await断线清理前撤权。实际部署的所有者可信引导尚未完成，不能仅持有bearer就自称受信sidecar或某个客户端品牌。

真实原生reader曾按匿名project索引查询而找不到认证user_id连接。已在共同原生出口增加owned resolver，复用Runtime admitted generation和最终dispatch guard；禁止走匿名fallback、全局discovery/reload重试。UA114覆盖两个原生reader，原取消/失败测试只迁移等待拦截点到`Runtime.connection`，原断言AST保持不变。

真实SDK/TLS/上游C#传输→CandidateGate/MaterialCandidateGate→本地替身人审/原生handler/磁盘回读均已执行；拒未批、跨session、停止后写，停止保留已改候选，原件不变。当前runtime 68/68与67项C#联合结果有重叠，不相加。证据与尚未完成项见`STATUS.md`及`evidence/additive-owned-parent-acceptance.json`。未把开发CLI变成已经完成的安全安装入口。

## 早期实际复用和实现（历史）

- 固定CoplayDev提交 `30d22075093d1d35dfb0091c1c7550e9ad948577` 的Server源码副本；原树、P0/P0.2不改。
- 原生 `manage_animation` / `manage_material` 函数直接注册为FastMCP工具，不复制reader；只放行 `controller_get_info` / `get_material_info` 的精确path参数。
- 原生PluginHub共同出口变换为v1 `vrchat_agent_dispatch`。未知工具/action、额外参数、无SDK上下文、过期/替换计划、断线重连拒绝。没有approve/renew或自定义透传工具。
- project由启动参数固定；client由SDK session派生；connection由原生registry派生。**registry身份是本地peer自报身份，不是密码学实例证明**。候选仅限同一可信本地用户边界，不能当管理员/本地终端沙箱。
- PluginHub接收出口复用固定原生 `models.unity_response.normalize_unity_response`，将 `{status:"success",result:{success:...,data:...}}` 归一化后再判定成功；内层 `success=false` 不会被外层success覆盖，control与reader共用。
- prepare仅接受Unity返回pending，停止在最初等待/最终等待期间均不能恢复计划。完整reader中间件边界对原生返回失败、路由异常和服务端协程取消撤销当前映射，按plan对象身份比较，旧请求不能误删新计划；不执行undo。**RR003历史超时保留，不计通过。新增CC001/002真实SDK刻画已证明本地asyncio task.cancel不发送MCP撤销，已排队读取可继续且映射仍保留；显式Client.cancel发送实际request_id时能在路由等待期中止并清理运行时映射。这不证明真实客户端停止按钮已接好，也不是已确认的Unity侧即时撤权。**
- 运行入口 `/mcp` 与原生 **`/hub/plugin`**；保留 `/hub` 作为既有fixture兼容别名，两条WS路由使用同一PluginHub及同一入口策略。固定 `WebSocketTransportClient.BuildWebSocketUri` 的路径是 `/hub/plugin`，旧 `/hub` 测试不代表实际Unity路径。无原生REST/批处理/远程批准路由；裸原生main已禁用。CLI固定127.0.0.1、显式project/port、不启遥测、不改客户端配置。
- 共同ASGI HTTP/WS入口只接受一个精确Host：`127.0.0.1:<实际监听端口>` 或 `localhost:<实际监听端口>`（默认80可省略端口）；不接受后缀、错端口、重复/缺失Host或forwarded-host替代。当前没有浏览器UI，**所有带Origin的请求均拒绝**，包括本机同源、空值和`null`；无Origin的原生SDK/Unity客户端允许。不是CORS，不是本地peer身份认证，也不阻挡可自行构造请求的本地进程。
- `python -B Candidate~/runtime --project <native-project-hash> --port <unused-loopback-port>` 是开发入口，需已有固定依赖环境；不是面向用户的已完成启动器。导入包不会自动启动。

## 验证分层

`tests/test_runtime.py` 使用真实FastMCP Client/Server、原生handler/transport/PluginHub；仅Unity peer是明确替身。
`tests/test_runtime_http.py` 真正启动CLI进程，在本机临时端口经HTTP SDK与原生WebSocket交互；RF010使用固定原生 `/hub/plugin`，RT011单独保留旧 `/hub` 兼容性覆盖。Unity peer仍是替身，响应改用原生status/result线格式。测试关闭SDK连接、socket和进程，校验无监听/PID及临时HOME残留。

`tests/test_runtime_fixes.py` 覆盖内层失败、完整原生调用失败/异常、服务端边界取消、对象身份保护和ASGI异常头；取消测试显式使用Context替身进入真实Runtime/原生reader/route，不等同RR003的SDK客户端取消传播。`tests/test_runtime_http_fixes.py` 用真实loopback HTTP及WS分别检查Host/Origin，两条WS路径均覆盖；仅为服务端接受/拒绝验证，不声称真实浏览器攻击复现。

首轮最小修复证据写 `evidence/runtime-fix*`。原审查报告/反例/RR003错误保持不变；`runtime-fix-original-files.json` 保存修前源码及测试，原有断言保留。`runtime-fix-result.json` 列出RED/GREEN、精确用例ID、命令、输入hash及限制；旧runtime证据记录历史，不因本轮通过而改写。修后`deleg_3d996c88`独立复跑33项全过、审前后hash一致且未找到新候选缺陷，但汇总工具NameError使其报告明确不批准；报告保留，不由父级改成passed。随后父级六组33项再次通过，准确ID/进程组清理与同审查版本hash核对在`evidence/runtime-parent-takeover-regression.json`。修后独立批准仍待。

所有日志保存在 `evidence/runtime-*.json`。RT001/002是缺失功能RED→GREEN；RT003–006、RT010–013有明确RED→GREEN；RT007–009为现有约束characterization（RT007/009曾有测试变量错误，修正后重跑，不能把错误计通过）。RT012落实“任何原生失败需重提计划”后，RT002显式重新prepare而不是沿用未批准计划；其失败/成功/停止断言保留。

纯本机测试通过不代表Unity能力开关、最终执行前证据、C#序列化/导入、Windows内核、真人批准或真实项目闭环通过。所有修改能力继续关闭。独立复核以单独结果为准，不能由本文件自批。

## 2026-09-28失联/取消增量（父级验证，非完整批准）

复用MCP 1.29.1原生 `session_idle_timeout=60`，通过FastMCP lifespan启动后、服务开始前设置真实manager，不手写心跳协议。没有任何MCP请求的会话在60秒后过期，即使客户端未DELETE也清除计划并精确stop；正常HTTP响应结束不是会话终止。SDK ping可延长session，但不延长任务授权TTL。该期限是上限回收策略，不能宣称TCP断线瞬时可知；真实客户端停止按钮仍待验。

读取在途被取消时，以invocation保留刚撤销的精确plan，在middleware finally内有界stop；不等session退出后才通知，避免其已丢失映射。PluginHub原生disconnect/同工程eviction新增同步撤权hook，只撤对应connection，未收到Unity回执必须为未确认，不在新连接恢复旧plan。

`evidence/runtime-idle-result.json` 聚合准确ID、红绿/回归和清理。新增IDLE001/002、DCON001/002有失败→通过；IDLE003为原生ping/独立TTL characterization。RF006旧no-event断言与新增必须发送stop冲突，已保留旧文件和原失败；只改为恰好一个匹配client/plan的stop断言，不放开读取/重试。57项C#联合检查待Unity并行修改冻结后复跑；这不冒充该模块独立审查或完整产品批准。

## SDK会话结束撤权增量（历史）

- 复用FastMCP stateful proxy使用的SDK `session._exit_stack` 回调机制；这是固定依赖的私有适配点，缺少该机制时拒绝绑定，不靠工具参数或loopback自认可信客户端。
- 固定FastMCP 3.4.7会等在途handler完成才走session退出回调。因此ASGI只观察**经过原SDK验证、返回200的DELETE /mcp**，先同步关闭当前会话的映射/准备，再有界通知Unity。错误Host/Origin/协议/会话的DELETE无撤权副作用。不自行实现MCP删除协议，也不把HTTP200当Unity确认。
- `notify_stop`复用同一PluginHub和v1门控出口，只发送原project/client/connection/task/plan；没有新批准工具。取消屏蔽和2秒截止只用于撤权清理；不重试、不切实例、不回滚。仅Unity原生`success=true`且`data.status=stopped`才记录确认。其他情况保留有界收据并输出中文未确认警告。
- 若session结束时prepare尚未给出plan_id，先本地撤权并报告身份未知；收到合法的迟到pending结果再精确stop，不重建映射。不发送空plan_id冒充成功撤权；永不返回/迟到超时仍未确认，不能声称Unity立即停止。
- C# stop只允许在task/plan完整匹配后删除；旧停止请求被拒绝时不误删替换计划。LC006经过真实SDK HTTP→原生WS→重新编译C#门控，并回读其本地清单为空。Unity运行、证据、原生读handler和人审仍是fixture。
- 当前证据 `runtime-lifecycle-result.json`：LC001–007/CLC001–002新增9项包含在57项联合验证；原六组33项回归和CC001/002复跑通过。RF006/007的Context shim现在使用真实SDK session，旧断言未变。没有新的独立批准。
- **剩余边界**：原始TCP连接掉线不等于Streamable HTTP session结束；无DELETE崩溃/心跳过期、真实Hermes/Codex停止UI、协议取消的Unity端完整闭环未接通。SDK session容量/闲置回收尚非完整产品设计。当前不提供真实工程使用。
- **当时的资源警告**：真实HTTP用例触发SDK SSE内存流的ResourceWarning；dependency-only复现不导入候选仍出现4次，见`runtime-lifecycle-sdk-warning-repro.py/.json`和allocation trace。该旧证据保留；后续修复见下文。自有PID/端口/临时目录清理与内存流警告是两件事，不能写“整个SDK无泄漏”。

## 隔离SDK资源修复

`dependencies/README.md`记录来源、最小补丁与选择方式。MCP 1.29.1的POST/GET SSE只在部分异常分支关闭接收流，正常完成和取消缺少终结所有权；同SDK replay分支已存在finally关闭模式。候选副本仅补两个finally的公共同步close，不改变MCP协议或授权，不改现有安装库，不全局monkeypatch、不抑制警告。

开发CLI显式优先候选依赖；`create_app`若发现已导入的transport来自别处则拒绝。直接验证必须通过`tests/verify_runtime.py`或在新进程导入前选择对应依赖。完整发行的依赖锁定和启动器仍待整合，不允许拿这个源码目录替代可安装交付。

本轮父级`runtime-sdk-result.json`核95唯一ID全部通过，已捕获日志未出现ResourceWarning，其中原57＋33＋CC2以外只有SC001–003三个新增ID。注意SC002成功子进程stderr未透传且未显式启用ResourceWarning，不能据外层空列表宣称该子进程告警已全量检查。真实CLI/HTTP/WS/C#回读重新验证；测试进程/进程组/临时build清理通过。SC001/SC002保留先RED，SC003为修后补充characterization；最终测试跑原版SDK仍能复现12/18个未关闭流。

独立审查`deleg_1aaab1f7`已通过，仅覆盖SDK增量，见`evidence/runtime-sdk-independent-review.json`和父级整合核验`evidence/runtime-sdk-review-acceptance.json`。独立SC001–004四项通过，新增SC004在真实SDK/ASGI层验证GET取消、流关闭和同session重新订阅通知；不冒称网络HTTP或Unity验收。与父级95项去重后共96个用例，不代表96项全部独立复跑；冻结实现及安装库hash吻合，清理核验通过。SC002告警覆盖限制不阻断本次SSE结论，但保留明确边界，不为此修改已审冻结源码。

另保留一次多server同进程测试超时；最小观测证实SSE库的全局AppStatus晚到退出会污染下一server，因此测试每个server生命周期用独立进程，每次内部重复三个session。这是当前一侧车一server边界，不是对第三方多server复用的修复。Windows/真实Unity/客户端仍未验收。
