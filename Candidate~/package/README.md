# VRChat Agent 未发布候选源码

此目录不是可安装成品，不要直接添加到真实Unity工程。完整实现、客户端接线、独立审查、运行时分发及集中验收尚未完成。

目标布局：Editor为候选程序集；OwnedTransport子目录的asmref仅将独立传输类型加入固定Coplay程序集；Runtime~包含受控sidecar源码与SDK修订，不交给Unity importer编译。打开窗口/导入本包不会启动服务或授予任务权限。

固定Coplay来源： https://github.com/CoplayDev/unity-mcp/tree/30d22075093d1d35dfb0091c1c7550e9ad948577 ，包版本10.2.0。这里不自动安装或更新它，不升级Unity/VRChat SDK，不移除旧包或工程文件。

Python的预配置环境/便携发行仍待完成，入口不会启动时联网安装依赖；账号、令牌、JWT私钥不写文件。停止/撤权不自动回退用户资产。真实Unity/Mono的导入、窗口和生命周期尚未验收。
