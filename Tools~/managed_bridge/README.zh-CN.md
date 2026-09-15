# Windows 本地受限 MCP 前端（Phase 1 候选）

`bridge.py` 是**可直接运行、仅使用 Python 标准库**的 HTTP 传输边界，不是 Hermes 的 `tools.include` 配置，也不会在 Unity 中开启任何权限。源对象修改权限、租约、精确前值检查及回滚仍完全由 Unity 扩展负责。本阶段未连接真实 Unity，未修改 Hermes 配置，未安装持久服务或发布。

## 必须满足的拓扑

```text
Agent 主机 127.0.0.1:28082
      │ SSH 只转发 18082
      ▼
Windows 127.0.0.1:18082/mcp  bridge.py
      │ 固定本地 POST /mcp；内部会话清理 DELETE /mcp
      ▼
Windows 127.0.0.1:18081/mcp  原始 Coplay 通用上游
```

**先人工断开旧的 `28080 -> Windows 18081` 隧道，包括自动重连任务、SSH multiplex 控制连接及其他仍指向 18081 的转发，再切换。** 只启动前端不会关闭旧隧道、不会自动保护已经能访问通用上游的客户端。18081 永不转发、永不对外监听。具备 Windows shell、修改前端源码或另建 18081 隧道能力的主体不在此边界的威胁模型中。

### Windows 启动（Python 3.11 或更新版本）

在本目录运行：

```powershell
py -3 bridge.py --upstream http://127.0.0.1:18081/mcp --listen 127.0.0.1 --port 18082
```

三个参数均为必填且只接受上面的字面值；不接受 localhost、0.0.0.0、任意端口、路径、URL、额外参数或参数缩写。Ctrl+C 退出。没有服务安装器，不读取 `.env`，不读取/转发调用者 Authorization、X-API-Key、X-Unity-Instance 或任意路由头。当前版本不提供需凭据的远程上游模式。`http.client.HTTPConnection` 只连接固定数字回环 IP，不读取环境代理、不会跟随 30x、不会发起 DNS 查询。

### SSH（部署说明，不由本次实现执行）

若 Agent 主机可 SSH 到 Windows，在 Agent 主机建立：

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:28082:127.0.0.1:18082 WINDOWS_USER@WINDOWS_HOST
```

若 Windows 只能反向连接 Agent 主机，在 Windows 建立：

```powershell
ssh -N -o ExitOnForwardFailure=yes -R 127.0.0.1:28082:127.0.0.1:18082 AGENT_USER@AGENT_HOST
```

选择其中一种；Agent 端 MCP URL 为 `http://127.0.0.1:28082/mcp`。SSH 服务端保持 `GatewayPorts no`，仅给专用账户所需转发权限，不授予通用 shell/任意转发；具体 SSH 账户限制需运维另审。前端接受 Host 为数字 `127.0.0.1` 加可选本地隧道端口，拒绝域名 Host 和**任何 Origin 头**，只服务非浏览器客户端。

## 上游注册前提：不提供通用包装器降级

上游必须已由本地操作者在**目标项目范围**注册并对当前会话直接公布以下 12+5 个名称：

```text
vrchat_ro_project_inventory
vrchat_ro_avatar_inspect
vrchat_ro_renderer_mesh
vrchat_ro_blendshapes
vrchat_ro_materials
vrchat_ro_animator
vrchat_ro_expressions
vrchat_ro_dynamics
vrchat_ro_modular_stack
vrchat_ro_performance
vrchat_ro_outfit_compatibility
vrchat_ro_validate
vrchat_me_status
vrchat_me_plan
vrchat_me_preview
vrchat_me_apply
vrchat_me_rollback
```

Coplay v10.2.0 的 `custom_tool_service.py` 支持真实命名工具处理器，同时存在 `execute_custom_tool` 通用包装器；本实现**只使用真实精确名称**。若你的 Coplay 组合只公布包装器、缺少上述任何工具、出现重复同名工具、分页或不支持的 schema，`tools/list` 返回 502，工具调用保持关闭；不推断、不自动注册、不开放通用包装器、不调用 `manage_tools`，也不自动切换 Unity 实例。

前端禁止 caller 提供 `unity_instance`（包括 camelCase 变体）、端口或任意上游路由。部署时需确保 Coplay 默认会话解析到唯一预期 Unity 项目，并本地核对 `mcpforunity://project/info`；多实例选择、项目固定身份的额外校验尚未集成。**精确名称与 schema 不是插件代码来源证明**，必须信任并审计本地 Coplay/Unity 工具注册来源。不能让不受信任项目注册同名工具。

## 协议与拒绝策略

- 仅 `POST /mcp`。原始请求目标也须精确匹配；拒绝批次、别名、大小写/Unicode近似名称、查询串、`//mcp`、`/mcp/`、任意其他路由。GET、DELETE、PUT、PATCH、CONNECT、WebSocket、hub、`/api/command`、工具注册/管理不转发。
- 仅 JSON-RPC `initialize`、`notifications/initialized`、`notifications/cancelled`、`ping`、`tools/list`、`tools/call`、`resources/list`、`resources/read`。不支持 prompts、sampling、roots、subscriptions、任务接口或 JSON-RPC 客户端响应。
- 严格 `application/json`；必需单一 Content-Length，拒绝 Transfer-Encoding、重复关键头、重复 JSON key、NaN/Infinity、未知外层字段。
- 仅实现 MCP `2025-03-26`、`2025-06-18`。客户端报价为其他日期版本（实测 SDK 为 `2025-11-25`）时，向上游报价已审计的 `2025-06-18`；上游可选择两个已审计版本之一。前端如实返回并保存最终版本，后续请求须携带相同 `MCP-Protocol-Version`，拒绝上游选择其他版本。不启用新方法/任务/回调。仅兼容并移除 SDK 自动附加的空 `_meta: {}`；非空 metadata 仍拒绝。
- 每次初始化生成随机 256-bit 前端会话 bearer token，与上游 token 不同；上游 token 不返回给客户端。会话不可凭客户端名称共享；未知、过期、另一前端实例的 token 拒绝。持有同一个合法 token 的客户端被视为同一会话，**token 不是独立用户身份认证**，安全依赖 SSH/主机访问隔离。
- 32 个总名额同时覆盖前端映射、在途初始化、待清理/未确认清理债务，300 秒空闲 TTL。周期及每请求只淘汰非忙会话；每会话一条在途请求，其余立即 503，不排队。其他会话不被慢初始化或后台清理阻塞；全局最多 16 个 HTTP worker，加一条有界清理线程。
- 初始化之后必须发送 initialized，再成功读取完整、合法的 `tools/list` 才能 tools/call。列表仅返回 17 个名称、收紧后的结构化输入 schema、自有描述和明确注解。status/plan 是只读；preview/apply/rollback 是修改操作，不能只根据前缀猜测。
- 输入 schema 只支持本文件实现的有限 JSON Schema 子集（object/array/基本类型、anyOf、enum、required、数值/长度/数量约束）。拒绝 `$ref` 等未审计关键字；移除上游描述/默认值/额外元数据，封闭 object 的额外参数。名称必须精确 snake_case，禁止实例/传输/执行选择器。未知字段不会传给 Coplay 的参数归一化中间件。
- 资源仅为 `mcpforunity://project/info`、`mcpforunity://editor/state`、`mcpforunity://instances`；列表过滤，读取时请求和返回 URI 必须一致，不开放任意 resource/template dispatcher。
- JSON 或 SSE 上游响应均转换为单个有限 JSON-RPC 响应，严格匹配响应 ID/类型。SSE 仅丢弃固定 advisory 通知；server-initiated request、endpoint redirect 事件、错误形状一律拒绝。首个匹配响应后关闭上游流，不建立 GET 长连接。
- 所有 tools/call 结果必须为合法文本 content 数组，可附加对象型 structuredContent、布尔 isError；未知字段、嵌入资源、资源链接、audio 及上游原生 image 一律拒绝。只有本地 preview 转换能产生 image。错误返回短 502，并明确提示 mutation may have executed，绝不重试写入。
- TTL 到期及正常关闭（Ctrl+C/context 退出）只对本进程初始化取得的精确上游会话发送内部 DELETE；客户端 DELETE、任意 URL/会话选择器仍不开放。DELETE 返回 200/204 后以同一会话只读 ping 验证 404；DELETE 本身 404 也确认已不存在。每个会话只尝试一次 DELETE，不重试未确认的删除，不调用工具或修改 Unity 数据/租约。
- 初始化响应损坏时，若已收到唯一合法上游 token，也纳入同样的精确清理；丢失、重复或不可信 token 不猜测 DELETE，而保留未知分配债务。清理失败、超时、405、假成功等保留名额，达到总上限后初始化返回 503（cleanup unresolved），不继续累积上游会话；固定无敏感数据的 WARNING 提醒操作者。无新增 health/task/resource 方法。
- 清理名额只在确认会话不存在后释放。债务只在内存中；异常进程终止无法执行清理，**不得以自动重启绕过上限**，重启前须本地核对/清理上游。此边界不声称能清理不支持 DELETE 或未返回 token 的上游；故障用例验证的是有界拒绝，不是假称已删除。

## 限制与不确定写入

| 项目 | 上限 |
|---|---:|
| 客户端请求体 | 65,536 bytes |
| 接收请求头+体绝对截止 | 5 秒 |
| 上游连接 socket timeout | 15 秒 |
| 上游已连接请求/响应绝对截止 | 15 秒 |
| 上游累计响应/SSE 字节 | 8 MiB |
| 最终 JSON 响应 | 4 MiB |
| 内部清理响应体 | 4,096 bytes |
| 每个清理连接/已连接请求绝对截止 | 分别 1 秒 |
| 图片 | 最多 2 张 PNG，每张 decoded **严格小于 1 MiB**、宽高各 1–512 |

连接阶段与已连接阶段分别有截止，因此最坏网络阶段可能接近两段截止之和；不进行自动重试。出现 502/504、客户端断开或响应超限，**不表示 Unity 未执行操作**。先检查 status/Unity 和事务归属，再由操作者决定；绝不盲目重试 apply/rollback。`notifications/cancelled` 只在会话不忙时转发，不提供抢占在途写入的安全保证。

### 原生预览图片

仅精确 `vrchat_me_preview` 的 `data.preview_images` 会转换为 MCP `type:image,mimeType:image/png,data:...`。支持 before/after 两个唯一标签；严格 base64、PNG signature、IHDR 长度及尺寸检查，任何图片无效则返回短错误，不泄漏原始大 JSON。图片 base64 从文本和 structuredContent 中移除，保留标签、尺寸、字节数与其他预览元数据。非 preview 工具不做该转换。

当前检查**不是完整 PNG 解码器**，不验证全部 PNG chunk/像素内容；不宣称图片视觉正确。真实 Unity 渲染、Windows 运行兼容性和 Hermes 原生视觉接受仍待人工 smoke test。

## 测试与安全验收

```powershell
py -3 -m unittest discover -s . -p test_bridge.py -v
```

Linux 开发验证：

```sh
python3 -m unittest discover -s . -p test_bridge.py -v
python3 -m py_compile bridge.py test_bridge.py
```

可选真实 SDK 回归单独运行（不把 fixture 称为 Unity）：

```sh
PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m unittest test_sdk_handshake -v
```

该用例使用已安装 ClientSession/HTTP transport，自发发送 SDK 握手；分别验证两个协商版本、17 tools、3 resources、status 和正常退出后的精确会话清理。SDK 的 frontend terminate-on-close 关闭，客户端 DELETE 并未开放。标准库 suite 与该可选 suite 可各自独立运行。

关闭时先等待已有 HTTP worker，再等待最多 32 个清理名额；每个名额至多 DELETE 和一次只读验证，各自有连接及已连接截止。因此关闭有界但故障时可能较慢（默认清理阶段上界为 `32 × 2 × (1 + 1)` 秒）；不强杀清理线程，也不宣称异常退出已清理。

测试使用真实回环 TCP/HTTP 临时假上游和前端，不只调用 validator；逐条功能按 RED→GREEN 实施，包含 SSE、所有工具和 URI、写入绕过、代理/重定向、会话隔离/超时、schema 投毒、图片、worker 饱和与缺失 Content-Length。CLI 子进程 smoke 只对未知会话发 ping，**不连接固定 18081 上游**，退出后回收进程。若 18082 已有监听，测试跳过该 smoke，不终止既有服务；发布验收不能把 skip 当作通过。

`_Server` 的可变端口/限制构造器是 Python 测试 seam；正式 CLI 不开放这些覆盖。父任务仍须独立源码审查、Windows/Coplay/Unity 联调、撤销/回滚及视觉核验，不能仅凭本地 Python 通过就称为生产可用。

### 核对的上游源定义

- [Coplay v10.2.0 custom_tool_service.py](https://github.com/CoplayDev/unity-mcp/blob/v10.2.0/Server/src/services/custom_tool_service.py)
- [Unity 实例中间件](https://github.com/CoplayDev/unity-mcp/blob/v10.2.0/Server/src/transport/unity_instance_middleware.py)
- [project/info](https://github.com/CoplayDev/unity-mcp/blob/v10.2.0/Server/src/services/resources/project_info.py)、[editor/state](https://github.com/CoplayDev/unity-mcp/blob/v10.2.0/Server/src/services/resources/editor_state.py)、[instances](https://github.com/CoplayDev/unity-mcp/blob/v10.2.0/Server/src/services/resources/unity_instances.py)
