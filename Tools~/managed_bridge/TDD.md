# TDD 实施记录

下表记录本任务工具实际运行过的 RED 首个失败原因；每次修改生产代码后均运行该时点完整 unittest 集合并获得 GREEN，再推进下一条切片。不是捏造运行日志：完整 RED/GREEN 工具输出保留在父任务会话，本文件只记录可查的摘要。

|切片|观察到的 RED|
|---|---|
|真实 HTTP 初始化→通知→ping|`runnable bridge module is missing`|
|精确工具列表及全部17个调用|输出多出 `execute_custom_tool/manage_tools/unlock`|
|客户端绕过阻断|非法工具/方法/路径返回200；批次还到达上游|
|会话边界/协商/TTL|构造器缺少 `session_ttl`，通过测试断言确认特性尚未实现|
|schema 和参数校验|未读合法工具列表即 tools/call 返回200，期望409|
|精确资源流量|resources/list 返回400，尚未实现|
|SSE→有限JSON|SSE 初始化返回400|
|代理/重定向/字节和时间限制|缺少 `max_request_bytes` 限制|
|preview 图片转换|原生 image blocks 是空列表|
|CLI|无参数运行竟返回0，未实施固定参数入口|
|慢客户端/worker饱和|缺少 `client_timeout`|
|跨会话并发|慢 initialize 阻塞已有会话 ping 约0.35秒|
|投毒工具目录|含 unlock/execute_custom_tool 的 enum 仍返回200|
|原始路由字面值|`//mcp` 被 stdlib 归一化为 `/mcp`，返回200|
|上游重复会话|返回400而非502；应标记上游协议错误|

所有 listener/context、线程和 subprocess 测试都有 finally 清理；最终结果请以 `test-results.json` 的实测摘要及 unittest stdout 为准。测试 fake upstream 是明示的测试夹具，不代表真实 Unity 已通过。

## 独立审查后的定向修复

只修复四项已报告 bridge 缺陷；未改 Unity/Hermes 配置，未扩展方法或工具列表。

|切片|本轮实际观察到的 RED → GREEN|
|---|---|
|真实已安装 SDK 握手|ClientSession `MCPError: Request rejected`；日期协商修复后仍失败，实际报文揭示 SDK 的空 `_meta: {}`。只接纳并移除空对象后，真实 SDK 成功。两个已审计返回版本均验证。|
|nullable anyOf object|`options:{target:'Avatar'}` 返回400而非200；修复 composition 外层空 properties 的二次拒绝，保留分支 unknown-key/类型/required 检查。|
|所有工具 content 验证|初次矩阵204项失败；原先错误 content/类型/资源/图片会透传200或缺少不确定写警告。增加全工具验证及标量 envelope 警告回归后通过。|
|TTL/正常关闭精确 DELETE|等待 fixture active_sessions 清空超时；加入内部单工作线程 DELETE + 精确 ping/404 验证后，6轮 TTL 和关闭清理通过。|
|清理失败有界债务|405/500/假成功/重定向/超限/超时后新初始化仍返回200；纳入总名额后503并保留债务，WARNING不含 token，正常关闭不重复 DELETE。|
|失败初始化已分配会话|损坏 JSON/未审计版本留下 active session；提早捕获唯一 token 并清理后通过。未知 token 原先继续请求上游，现保留名额并拒绝猜测删除。|
|清理生命周期回归|慢初始化在通知前即404，以及端口占用掩盖成 AttributeError；登记时重置 idle 时钟、未启动线程不 join 后通过。忙请求不被 TTL 删除。|

最终 suite 的实际计数、退出码及输出见 `test-results.json`。正常路径验证零上游会话、零映射/债务、无新线程及监听残留；故障 fixture 故意保留未清理会话，以验证安全拒绝，不把该结果写成“已清理”。Windows/Coplay/Unity、租约/回滚、真实渲染及独立复审仍未完成。
