# 可安装候选开发合同（本地、尚非交付）

用户在“先完成候选、再本人用ALCOM安装验收”的答复后明确“继续”。继续隔离开发并准备测试版；不含提交/推送/公网索引更新、现用安装升级、真实工程/头像修改、Hermes/Codex配置修改。P0与P0.2工件冻结只读。此目录的中间实现不得冒称全部功能或可安装交付。

## 2026-09-28后续授权

用户要求继续到可通过ALCOM安装验收，并经单独确认允许独立候选分支提交/推送及GitHub Actions。仅候选代码与测试；不得改主分支、现有版本或公网VPM索引。正式发布仍单独确认。前文不含提交/推送的限制在此有限范围内被后续授权替代。允许隔离依赖取得和CI测试所需网络，不读写真实Unity/头像或Hermes/Codex运行配置。

## 复用与边界

- 原生固定CoplayDev `30d22075093d1d35dfb0091c1c7550e9ad948577`，源 `/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0`。不得改原树。
- 在 `native/` 自有副本复用原生Server，按共同发送出口最小补丁；不是第二套MCP协议或逐个重写reader。
- Unity包 `package/` 为新的 `com.yukino.vrchat-agent` 候选，不覆盖旧包。复用原生CommandRegistry.GetHandler的sync-only已审操作（已读固定源码：该API在执行前拒绝异步handler）；通过自有C#最终检查入口执行。无需为了最终门控先分发整套C#上游分叉。
- 仅本项目受控MCP路径受保证，非管理员/本地终端沙箱；不能留下同一受控服务REST/资源/自定义工具/批处理绕过。旧直连隧道和旧插件不得由此自动清理，安装切换须显式验证。
- 人审先采用Q41允许的Unity一次核对批准。远程只有prepare/status/stop；没有approve/renew/unlock工具。模型提交清单不等于批准。聊天原生绑定未验证，不能假称已支持。
- 默认所有能力关闭，用户本地勾选为上限。准备清单必须先开本地读取能力，批准具体清单一次；不能靠导入包自动启动、自动同意或回退。
- 读复用已核原生命令。写操作须各自证实范围/副作用；未知操作显示不支持且拒绝，不能为了全绿放开。材质候选内权限是文件级，不逐字段批准，引用宿主另批，用户保存场景。未实现项留在总清单，不把小范围门控冒称完整候选。

## Python↔Unity v1合同

共同发送出口只发送一个命令 `vrchat_agent_dispatch`，params严格为：

```json
{"protocol":1,"kind":"status|prepare|execute|stop","project_id":"native-project-hash","client_id":"server-derived SDK session identity","connection_id":"native registry connection id","task_id":"exact task id","plan_id":"Unity returned plan id or empty","body":{}}
```

- project固定由本地启动参数指定并与原生registry核对；不能只按显示名或取第一个实例。
- client_id来自SDK真实session_id，禁止从工具参数提供。Hermes/Codex会话不同，不复用批准。
- connection_id来自原生registry。在所有await后核对当前实例/连接，重连不可沿用旧plan。
- MCP工具 `agent_status` 参数无；`agent_prepare(task_id, operations, targets, ttl_seconds)`；`agent_stop(task_id)`。approve不注册。
- prepare.body：`operations`为命令/action对象数组，`targets`为精确工程相对路径数组，`ttl_seconds`有限正数且最多900。Unity自己读取相关证据、生成不可变清单、plan_id/digest，返回pending；不会接受调用者给定revision或approved。
- execute.body：`command`、`params`，原生handler负责翻译工具入参；发送快照与检查快照一致。Python将每个SDK session与其当前plan/task绑定，prepare替换先撤销旧映射，失败不能沿用旧plan。Unity读取计划绑定再次检查，并核对本地能力、有效期、当前工程/连接/证据和串行状态。
- status.body空；返回中国用户可读状态、有限公开标识、支持操作及待批/已批状态；不输出凭据、完整日志或任意路径。
- stop仅撤权/拒绝新调用；不自动undo或删除候选。正在执行的动作明确在途；返回后核对状态。
- SDK确认结束的会话须先关闭本地授权，再向原连接的精确plan发送stop；迟到stop不得误撤新计划。Unity无确认、prepare身份未知或清理超时只报告未确认，不以SDK DELETE 200代替Unity状态；原始TCP断线、真实客户端按钮和停止动作的实现/验收分开记账。
- Unity扩展返回原生SuccessResponse/ErrorResponse，重要字段放data内，符合上游线格式。
- 所有返回数据需要保留原生错误语义；wrapper success envelope不能把底层success=false变成功。


## 同连接本地暂停/继续

读取及材质清单可由本地窗口暂停，并在同一有效连接内核验后继续。
暂停保持原plan_id/digest/task/client/connection、清单、当前证据及原到期时间，
不延长期限，不回退文件，也不释放材质工程单写占用。暂停不是撤权：只有
已批准清单可暂停/继续；普通Approve不能解暂停。本地点击在同步安全点生效，
门控忙时拒绝本地切换，停止/能力撤销仍可先撤权。

继续调用已有Current+Capture/Verify：目标/候选、依赖、宿主、能力、工程、
连接、期限或回调中撤权不一致即撤销原清单，保留现场。重载、断线、退出、
StopAll、到期仍清除授权；**本节不实现跨重载/重连的任务续接**。

合法暂停清单的execute返回success=false/error=plan_paused，data严格包含
status=paused、reason=plan_paused、当前plan_id。Python仅在这份精确拒绝且
原映射仍有效时保留它；调用仍是错误/未执行，不伪装成功。其他失败保持原
撤权语义。没有新增MCP pause/resume/approve/renew工具或Unity远程kind。


## 显式实时 Console 读取

`read_console/get`复用固定原生Python wrapper与C# handler，目标必须显式包含`Console`，
不伪装成资产文件。权限默认关闭；展开原生目录勾选后仍须批准精确任务。
只接受`action=get`、`format=json`、整数`page_size` 1–100；可选有限types、
整数cursor、filter_text和布尔include_stacktrace。clear、count、类型转换和未知字段拒绝。
同一约束在原生发送出口及Unity最终门控分别执行，停止/会话退出沿用精确撤权。

Console属于连接/工程绑定的实时诊断流；日志追加不会撤权，内容不承诺冻结。
原生分页的total在truncated=true时仅为下界；nextCursor可能受实时变动影响，
不能把分页遍历当作全工程日志的原子快照。数据形状/长度/游标不符合固定原生
合同即拒绝并撤权。它不批准任何清空、刷新、执行、保存或其他读取范围。

## 场景查找的类型解析限制

`find_gameobjects`保留固定原生by_name/by_tag/by_layer/by_path/by_id；
`by_component`在Python和Unity最终门控都拒绝，包括普通名称和程序集限定名称。
固定原生UnityTypeResolver可能调用Type.GetType及程序集回调，不属于纯只读保证。
RT036、NS018和真实双客户端拒绝用例覆盖此边界；NS018同时用固定原生解析器验证风险对照。
没有因此改写上游读器、开放通用反射或降低Scenes授权要求。

## 所有权

并行实现只可写各自目录：
- Unity任务：`package/Editor/`、`tests/unity-core/`、`evidence/unity-*`、`UNITY.md`。
- runtime任务：`runtime/`、`native/`、`tests/test_runtime*`、`evidence/runtime-*`、`RUNTIME.md`。
- filesystem任务：`diagnostics/`、`tests/test_diagnostics*`、`evidence/diagnostics-*`、`DIAGNOSTICS.md`。
- 父任务：范围/验收/打包/整合；不覆盖正在写的子任务文件。

## 验证纪律

TDD垂直小步RED→GREEN；已有复用first-green按characterization记账。只用本机fixture；无真实配置/凭据、网络安装、常驻服务、Unity/头像操作、提交发布。现成Python `/home/ubuntu/.cache/uv/archive-v0/7z4PORN2YM2xSubx/bin/python`，跨SDK客户端 `/home/ubuntu/.hermes/hermes-agent/venv/bin/python`，.NET `/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet`。构建禁止后台compiler server（UseSharedCompilation=false/--disable-build-servers）。Python用-B、隔离临时HOME；保留原始输出、输入hash与准确计数，验证自有进程/fixture清理。真实SDK/原生链路、C#纯核/.NET替身、Windows内核、Unity实机四层分别记账。服务429停止不重试、不切账号/备用。总体验收尚未通过，先报告确切缺口而非做“看起来可安装”的空壳。
