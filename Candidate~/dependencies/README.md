# 隔离 MCP SDK 候选补丁

仅候选源码，不是全局安装或完成的VPM依赖包。未修改现有Hermes、uv缓存或任何已安装SDK。

## 来源与最小差异

- 已有隔离环境的 `mcp 1.29.1`，111个包文件逐项核对安装分发的 `RECORD` SHA-256。来源记录：`mcp-source.json`。这是本机已安装分发的完整性核对，不冒称重新从公开源下载验证。
- 原MIT许可证与分发元数据保存在 `mcp-1.29.1/LICENSE`、`UPSTREAM-METADATA`。
- 候选保留111个包文件，仅 `mcp/server/streamable_http.py` 两个位置有差异：POST SSE和GET SSE的响应结束路径增加 `finally`，同步关闭自己分配的两端内存流。正常EOF、异常和取消均走关闭；不改消息内容、session终止、认证/校验或重连语义。
- 同一SDK的 `_replay_events` 已有双方流的 `finally` 关闭模式，直接遵循已有所有权设计，没有另造运输层或全局monkeypatch。
- 补丁 `mcp-sse-cleanup.patch`；修后hash为 `mcp-candidate.json`。已从未改安装源复制到一次性目录，`git apply --check`及应用通过，逐项对比重建的111文件hash一致，临时目录已移除。

## 如何选择候选依赖

开发CLI `runtime/__main__.py` 在导入FastMCP前，将该目录放入自己的 `sys.path`。应用工厂核对已载入HTTP transport来源；若进程已经载入外部SDK，拒绝创建应用并返回固定 `candidate_sdk_required`，不混合热替换已载入模块。

直接运行测试使用固定Python及 `tests/verify_runtime.py LABEL FILE MODE [FILTER ...]`。它复用现有有界证据runner，明确把候选SDK及tests路径传入子进程，记录源码hash、唯一测试ID、超时、清理；新增将 `ResourceWarning` 列入失败门槛。`tests/verify_unity.py`也使用相同依赖并将资源警告视为失败。原始旧报告及旧runner不改写。

仍需已安装的固定FastMCP 3.4.7、sse-starlette 3.4.8、AnyIO 4.14.2等依赖；本目录不是完整离线Python分发。最终启动器、版本锁定和VPM打包仍未整合，禁止将它当作可独立安装包。

## 已验证与限制

- SC001：真实HTTP，连续三个SDK会话结束后，实际分配的发送/接收内存流全部显式关闭；GC不产生ResourceWarning。
- SC002：误用原版SDK时，候选HTTP应用拒绝启动。
- SC003：真实HTTP POST半途关闭，原session仍可继续调用；结束后内存流全部关闭，不把单条HTTP断开误判为会话撤权。
- CLI、Host/Origin、原33项runtime回归、两项取消刻画及57项C#/HTTP/WS联合验证另有完整日志。重复执行不重复计数。
- 初次多个uvicorn server在同一测试进程依次启动曾超时；sse-starlette的全局AppStatus会在前一server关闭后延迟变为退出，已用独立最小观测验证。测试现在每case一个进程、每进程三个session，符合当前一侧车一server生命周期。**没有宣称修复第三方多server进程复用**，也不通过重置全局标志伪装为可用。
- 这是特定SSE资源所有权缺陷的修复，不等于整个SDK无泄漏、不等于真实Unity/客户端或完整候选验收。事件重放、新依赖版本、SDK升级和多server生命周期不在此次验收范围。
