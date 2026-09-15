# 纯 C# Gate / BlendShape Delta 核心测试

## 已实际验证

- SDK：本机 `.NET SDK 8.0.408`，运行时 `8.0.15`。
- `net8.0` 自定义 C# runner 直接链接包内同一个 `GatePolicy.cs`，无 NuGet 包依赖，`LangVersion=9.0`，警告视为错误。
- 最终执行输出：`RESULT 15 tests, 0 failures`，退出码 `0`。
- 同一核心额外编译为 `netstandard2.1` / C# 9：`0 Warning(s)`、`0 Error(s)`，退出码 `0`。此检查不等于 Unity Editor 编译或集成测试。
- `evidence/runs.jsonl` 保存真实命令、UTC 时间、退出码、完整 stdout/stderr 与当轮核心/测试/项目源码 SHA-256。首次完成时共 **33 条记录**：15 个按顺序 RED→GREEN 的行为切片；第 14 切片在 GREEN 前另保留一次测试 fixture 修正后的 RED；最后一次完整回归和一次兼容性编译。每个 RED 都是真正编译后执行的 C# 测试失败，而不是缺 SDK 或编译失败。
- 首次完成时核心 SHA-256：`256f8333a5bea2386269b1719fbb3f46daf4077d130216c28aef4f59b531151f`。

没有运行 Unity Editor、Unity adapter/UI、传输层或真实 Avatar 写入；没有发布、提交或推送。

## 复现命令

在 `/home/ubuntu/VRchat_Agent-managed-work`：

```sh
python3 Tests~/core/run.py regression
python3 Tests~/core/run.py compatibility --compat
# 可选：只运行名称中包含该字符串的测试；无匹配时退出 2。
python3 Tests~/core/run.py focused "Compare-and-restore"
```

Runner 原样返回 dotnet 退出码，并向 `evidence/runs.jsonl` 追加实际结果。默认 SDK 路径是 `/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet`；其他机器可设置 `DOTNET=/path/to/dotnet`（或 `DOTNET=dotnet`）。`NuGet.Config` 清空 package sources，项目不依赖第三方测试框架。

直接执行 C#：

```sh
/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet run --project Tests~/core/CoreTests.csproj --configuration Release
/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet build Tests~/core/compatibility/CoreCompatibility.csproj --configuration Release --nologo
```

## 精确 API

全部类型位于 `namespace Yukino.VRChatManagedEditing`，类型均为 **internal**；以下构造函数、属性和方法是该 internal 类型的 public 成员。没有 Unity 类型或 SDK 依赖。

```csharp
[Flags]
internal enum EditCapability { None = 0, Preview = 1, Apply = 2 }

internal sealed class GateDeniedException : Exception
{
    public string Code { get; }
    public GateDeniedException(string code, string message);
}

internal sealed class GatePolicy
{
    public GatePolicy(Func<double> clock);
    public string LeaseId { get; private set; }
    public bool Active { get; }
    public string TargetKey { get; private set; }
    public string MeshKey { get; private set; }
    public IReadOnlyCollection<string> Names { get; private set; }
    public EditCapability Capabilities { get; private set; }
    public double RemainingSeconds { get; }
    public int RemainingWrites { get; }
    public void Grant(string targetKey, string meshKey, IEnumerable<string> names,
        EditCapability caps, double ttlSeconds, int writeBudget = 30);
    public void Demand(string targetKey, string meshKey, IEnumerable<string> names,
        EditCapability capability, string leaseId);
    public void ConsumeWrite();
    public void Revoke();
}

internal readonly struct ShapeEdit
{
    public ShapeEdit(string name, float weight);
    public string Name { get; }
    public float Weight { get; }
}

internal readonly struct ShapeDelta
{
    public ShapeDelta(string name, float before, float after);
    public string Name { get; }
    public float Before { get; }
    public float After { get; }
}

internal static class DeltaPolicy
{
    public static List<ShapeDelta> ValidateChanges(
        IDictionary<string, float> current, IEnumerable<ShapeEdit> edits);
    public static void ValidateCurrent(IEnumerable<ShapeDelta> deltas,
        IDictionary<string, float> current, bool rollback = false);
}
```

## 集成语义与边界

- `Grant` **只允许 Unity 本地操作者调用**。internal API 本身不是传输安全边界；父层必须不暴露任何远程 grant/unlock/extend 路由。
- 初始关闭。每次成功 Grant 使用 `Guid.NewGuid()` 生成新代际。普通输入验证失败不改变旧授权；时钟倒退、非有限值、抛异常或无法表示截止时间会 fail closed。时钟恢复不会自动恢复失效授权；只能再次本地 Grant。
- TTL 为有限 `1..900` 秒；预算 `1..100`，默认 `30`。Names 必须非空、非空白、ordinal 唯一且最多 128 个。Target/Mesh 不允许空白；不修剪、不忽略大小写、不模糊匹配。未知能力和 `None` 拒绝。
- Names 是独立快照且只读，不暴露底层可变 List。初始/显式 Revoke 后 LeaseId、TargetKey、MeshKey 为 null；Names 为空、Capabilities=None。自然到期/时钟故障会关闭 Active，但可保留旧范围元数据用于诊断；元数据不是有效权限。
- `Demand` 验证完整名称子集及当前 lease/target/mesh/capability，不扣预算；在枚举输入后重新检查授权。任何包含 Apply 的 Demand 在预算耗尽后拒绝；仅 Preview 的 Demand 仍可成功。
- `ConsumeWrite` 要求当前有效 Apply 授权及剩余预算，每次源 Apply 或源 Rollback 事务调用一次，不对 Preview 调用。它不代替完整 `Demand`。适配器需先完成所有前置校验，然后在第一次源写入前消费预算；失败后不自动返还预算。
- `ValidateChanges` 不修改输入。只有请求的 After 受 `[0,100]` 限制；Before 只要求有限，可为负值或大于 100，绝不把原始值归零。任一未知名称、重复、非有限数、非法范围或超限会整体抛错，不返回部分计划。
- `ValidateCurrent` 对所有 delta 先检查结构/数值，再读取当前状态；Apply 精确比较 Before，Rollback 精确比较 After（C# float `==` 语义，无容差）。一个字段冲突就拒绝整个批次，未选字段不参与比较、不被覆盖。使用 ordinal 副本，不继承调用方字典的忽略大小写比较器。
- 普通策略拒绝抛出 `GateDeniedException(code, message)`。稳定 Code：`gate_closed`, `lease_mismatch`, `scope_mismatch`, `invalid_scope`, `invalid_names`, `invalid_capability`, `capability_denied`, `invalid_ttl`, `invalid_budget`, `clock_invalid`, `write_budget_exhausted`, `invalid_changes`, `invalid_current`, `unknown_shape`, `invalid_weight`, `invalid_baseline`, `state_conflict`。
- 配置错误 `new GatePolicy(null)` 抛 `ArgumentNullException`；调用方自定义枚举器自身抛出的异常会传播，核心不会执行源写入。不要把外部任意代码当作可信输入枚举器。
- 核心面向 **Unity 主线程串行调用**，不是跨线程锁或完整事务协调器。生命周期 Revoke、对象/mesh 身份、计划代际、最终前置检查、Undo、实际写入、事务日志、源回滚及 Preview 清理由父层实现。不得在检查与写入之间让出控制权、运行任意回调或并行修改目标。

## 覆盖的纵向行为切片

1. 默认关闭及完整 internal API。
2. 本地 Grant、精确名称快照与新代际。
3. Demand 的 lease、target、mesh、名称子集及能力约束。
4. 普通无效 Grant 原子拒绝（含边界值、重复/空名称、失败枚举）。
5. 截止时刻到期、剩余时间/预算及永不自动复活。
6. 倒退、非有限、抛异常和不可表示的时钟 fail closed。
7. 源写预算扣除、耗尽拒绝与 Preview 独立性。
8. Revoke 幂等清理及旧代际不能用于新授权。
9. Demand 枚举期间到期/撤销/替换授权后的最终复检。
10. Delta 保留非零、负数、超常范围原始权重且不写源。
11. 非法 edits 整批拒绝、有限值、上下限及 128 条边界。
12. 忽略大小写字典也不能绕过精确名称。
13. Apply/Rollback 精确比较，拒绝一 ULP 的人工变更。
14. ValidateCurrent 的非有限值、畸形/重复/超限批次验证。
15. Delta 枚举期间的人工修改不能被旧快照掩盖。
