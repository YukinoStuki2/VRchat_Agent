# VRChat Agent 0.2.0-preview.3：修复 Unity 启动时的 CS7036

`CandidateDiscoveryJob.cs` 现在兼容 Unity Test Framework 已知的零参、单参、双参测试发现构造函数，不要求降级 Unity、VRChat SDK 或测试框架。Coplay 10.2.0 依赖、运行时、权限和场景文件均不变。已做针对性 C# 编译和回归；未在用户的真实 Windows Unity 工程验收。

关闭 Unity，在 VCC 的项目管理页面更新 `com.yukino.vrchat-agent` 到 `0.2.0-preview.3`（需显示预发行版本），然后重新打开。长期订阅地址：`https://raw.githubusercontent.com/YukinoStuki2/VRchat_Agent/vpm/index.json`。如果之前只订阅了 URL 带 `releases/download/.../index.json` 的固定预览源，添加上述长期地址一次即可；不必卸载旧包或手动替换脚本。

以下如有旧版本说明，仅供查阅；后续更新以上述长期订阅地址为准。
