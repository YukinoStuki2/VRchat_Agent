# Hermes 候选插件接入说明（开发候选，未安装）

本目录是 Linux Hermes 宿主插件源码，不是完整 VRChat Agent 安装包，也不代表 ALCOM 验收通过。
导入或加载插件不监听、不连接 Unity、不授予任务权限；宿主无需修改 Hermes 核心。

## 安装与信任边界

- `distribution/hermes_plugin.py:collect(root)` 返回插件文件及 `SHA256SUMS.json`，供经批准的打包器使用；自身不写安装目录、不启用、不发布。
- 将审核后的整个插件目录放入**指定 profile**的 `plugins/vrchat-agent-candidate/`，保留相对导入布局；不设置全局 PYTHONPATH。
- 通过 Hermes 原生插件配置显式启用。只编辑目标 profile；不要覆盖其现有模型、其他插件或凭据。当前工程没有自动安装/激活现用网关。
- 当前接收器仅支持 Linux `SO_PEERCRED`。接收目录须归运行 Hermes 的 UID 所有、权限0700；socket 使用0600。不复用/删除已占用或不安全路径。启动 chmod 失败会关闭自己的监听并清理自己的 socket。
- 一个接收器仅服务一个 `(platform,user,profile)` 身份；可指定同一用户的多个精确聊天/线程。不同用户必须使用隔离 profile/UID/接收器，不能共享待认领列表。
- 该 UID 的进程及 SSH 登录策略是受信任边界，不抵抗同 UID 恶意进程。SSH身份、平台身份和工程任务批准是不同层，不得互相代替。

配置形状如下，所有占位符均需由本地管理员核实替换；不在聊天中输入密码、私钥或 bearer：

```yaml
plugins:
  enabled: [vrchat-agent-candidate]  # 合并到已有列表，不能覆盖其他插件
  entries:
    vrchat-agent-candidate:
      settings:
        socket: /absolute/private-0700-directory/receiver.sock
        owners:
          - platform: actual-platform-id
            user: actual-user-id
            chat: actual-private-chat-id
            profile: null
            thread: null
        include: [agent_status, agent_stop]  # 最小只读诊断；不默认扩大到所有工具
```

身份以宿主事件字段精确匹配；平台授权检查同时必须通过。仅DM、拒绝机器人和被拒绝的profile路由。
需要材质/原生操作时，由本地管理员核对当前操作目录后逐个增加 `include`；聊天或模型不能修改此列表。

## SSH部署前置条件（不是自动配置脚本）

远端管理员需提供固定 `vrchat-agent-handoff` SSH subsystem，执行固定绝对路径的 Hermes Python 与
本插件 `hermes_handoff_relay.py`，传入固定绝对 socket 路径。relay只收发管道协议，不接受远程脚本/任意路径。
管理员必须审查 SSH 服务端及每把操作者公钥的授权策略：仅可信操作者密钥；禁密码、交互shell/任意exec、PTY、agent/X11转发；
只允许所需的远端 **127.0.0.1** 监听端口，`GatewayPorts no`。既有 SSH 服务、用户和信任文件不由插件修改。
同 UID 连接验证不证明已经配置这些限制；真实跨机部署仍需单独验收。

本机预先核实主机指纹并配置 SSH agent/系统可信密钥；启动使用 BatchMode、StrictHostKeyChecking 和固定子系统。
不得在命令行、配置文件或日志中填写本轮短期凭据。凭据由 Unity owner 内存经私有管道和 SSH stdin 交付。
管理机回环转发端口不是公网监听，也不是工程原始HTTP authority；两者会分别固定核对。

## 手动操作

1. 在已配置的私聊输入 `/vrc 开始`，最长开放一小时。尚未授权任何任务。
2. Unity窗口手动允许本轮 Hermes，填写SSH主机、受限用户、SSH端口、管理机回环端口，启动本地受控连接。
3. `/vrc 列表` 查看工程与连接编号；`/vrc 绑定 编号` 建立全新的专用AIAgent。不热改普通聊天会话。
4. `/vrc 问 内容` 使用该专用会话。仅连接不授予编辑；任务清单及精确目标仍须Unity本地批准。
5. `/vrc 停止` 撤销并关闭本聊天绑定，不回退文件。`/stop`、`/new`、`/reset` 也会在普通命令分发前撤销本聊天绑定。
6. `/vrc 关闭` 关闭接收入口；若其他聊天仍有绑定会拒绝。插件卸载也先撤权再清理。

失联、到期、停止或清理失败均不自动重连/重试/恢复权限。清理失败须本地检查；客户端删除回执不证明在途操作没有执行。
任务记录/跨重载续接仍未交付。本地Codex只有协议兼容测试和角色选择，用户入口仍未交付。

## 已验证范围与复现

- `hermes_gateway_contracts.py`：真实插件管理器、加载/发现/显式启用/卸载；平台授权与发送使用替身。
- `hermes_chat_contracts.py`：真实注册表加agent/协议替身的聊天所有权和撤销。
- `hermes_handoff_contracts.py`：Linux Unix socket、内存协议、真实回环SSH及失败清理。
- `verify_native_clients.py --approved-tasks --hermes-handoff --hermes-chat --hermes-ssh`：真实OpenSSH、搬迁后的插件、原生AIAgent执行器及官方Codex；仅fixture消息，不请求模型。
- 上述不是Windows原生客户端、实际平台消息、真实Unity Editor、真人点击或公网跨机验收。
- 测试隔离HOME及凭据环境，完成后核对MCP DELETE、进程/端口/临时目录清理和秘密扫描。不得在现用profile运行fixture。

底层接口说明保留于 `README.md`；历史描述按各自切片范围理解，不当作当前完整产品结论。
