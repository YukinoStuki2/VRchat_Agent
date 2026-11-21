## 0.2.0-preview.4 · 修复资产读取脚本的 CS1061 与 Runtime~ 目录警告

- `CandidateScopedAssets.cs` 引入 Coplay 10.2.0 实际提供 `GetInstanceIDCompat` 的命名空间；保留原方法、权限检查和实例 ID 的兼容行为。
- 不再分发 `Runtime~.meta`。保留 `Runtime~/` 内的启动器、Python 和运行文件，不要手动删除该目录。
- 继续依赖 MCP for Unity 10.2.0；保留 preview.3 的测试发现修复。不修改工程 `Assets/` 下第三方插件，包括 HierarchyDecorator。
- VCC：关闭 Unity，在现有长期源更新 **Yukino VRChat Agent**，然后重新打开工程。本次未在用户的 Windows Unity Editor 中验收。
