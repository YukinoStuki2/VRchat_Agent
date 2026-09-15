using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Yukino.VRChatManagedEditing;

internal static class Program
{
    private static readonly List<(string Name, Action Run)> Tests = new List<(string, Action)>
    {
        ("Gate starts closed with a complete internal API", DefaultClosed),
        ("Grant snapshots exact scope and creates a new generation", GrantSnapshot),
        ("Demand enforces lease, target, mesh, exact subset and capability", DemandScope),
        ("Invalid grants preserve the complete previous lease", InvalidGrantAtomic),
        ("Expiry closes permanently at the exact deadline", Expiry),
        ("Untrustworthy clocks fail closed without revival", ClockFailure),
        ("Source write budget does not charge or disable preview", WriteBudget),
        ("Revocation clears authority and old leases never authorize regrant", Revocation),
        ("Demand rechecks authority after enumerating input", DemandFinalCheck),
        ("Delta planning preserves finite original weights without source mutation", DeltaBaseline),
        ("Invalid edit anywhere rejects the entire read-only plan", DeltaValidation),
        ("Delta lookup never inherits a case-insensitive dictionary comparer", DeltaOrdinal),
        ("Compare-and-restore rejects manual changes using exact floats", CompareAndRestore),
        ("Current-state validation rejects malformed or nonfinite delta batches", CurrentValidation),
        ("Current comparison observes changes made while enumerating deltas", CompareAfterEnumeration),
    };

    private static int Main(string[] args)
    {
        var selected = Tests.Where(t => args.Length == 0 || t.Name.Contains(args[0], StringComparison.Ordinal)).ToList();
        if (selected.Count == 0) { Console.Error.WriteLine("No matching tests"); return 2; }
        int failures = 0;
        foreach (var test in selected)
        {
            try { test.Run(); Console.WriteLine("PASS " + test.Name); }
            catch (Exception error) { failures++; Console.WriteLine("FAIL " + test.Name + ": " + error.GetBaseException().Message); }
        }
        Console.WriteLine("RESULT " + selected.Count + " tests, " + failures + " failures");
        return failures == 0 ? 0 : 1;
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void Equal<T>(T expected, T actual, string message = "Values differ")
    {
        Assert(EqualityComparer<T>.Default.Equals(expected, actual), message + ": expected " + expected + ", actual " + actual);
    }

    private static void DefaultClosed()
    {
        var type = typeof(Program).Assembly.GetType("Yukino.VRChatManagedEditing.GatePolicy");
        Assert(type != null, "GatePolicy type is missing");
        Assert(type.IsNotPublic, "GatePolicy must remain internal");
        var gate = Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            null, new object[] { (Func<double>)(() => 10d) }, null);
        foreach (var name in new[] { "LeaseId", "Active", "TargetKey", "MeshKey", "Names", "Capabilities", "RemainingSeconds", "RemainingWrites" })
            Assert(type.GetProperty(name) != null, "Missing read-only property " + name);
        foreach (var name in new[] { "Grant", "Demand", "ConsumeWrite", "Revoke" })
            Assert(type.GetMethod(name) != null, "Missing method " + name);
        Equal(false, (bool)type.GetProperty("Active").GetValue(gate));
        Equal(0, (int)type.GetProperty("RemainingWrites").GetValue(gate));
        Equal(0d, (double)type.GetProperty("RemainingSeconds").GetValue(gate));
        Equal(0, ((System.Collections.ICollection)type.GetProperty("Names").GetValue(gate)).Count);
    }

    private static void GrantSnapshot()
    {
        var gate = new GatePolicy(() => 10d);
        var input = new List<string> { "Smile", "smile" };
        gate.Grant("renderer:1", "mesh:1", input, EditCapability.Preview | EditCapability.Apply, 30);
        Assert(gate.Active, "A valid local grant must open the gate");
        Equal("renderer:1", gate.TargetKey);
        Equal("mesh:1", gate.MeshKey);
        Equal(EditCapability.Preview | EditCapability.Apply, gate.Capabilities);
        Equal(30d, gate.RemainingSeconds);
        Equal(30, gate.RemainingWrites);
        Assert(Guid.TryParse(gate.LeaseId, out var id) && id != Guid.Empty, "Lease must be a GUID");
        string first = gate.LeaseId;
        input.Clear();
        Equal(2, gate.Names.Count, "Caller cannot mutate granted names");
        Assert(gate.Names.Contains("Smile") && gate.Names.Contains("smile"), "Names must preserve ordinal case");
        var mutable = gate.Names as ICollection<string>;
        Assert(mutable == null || mutable.IsReadOnly, "Names must not expose a mutable collection");
        gate.Grant("renderer:2", "mesh:2", new[] { "Blink" }, EditCapability.Preview, 1, 1);
        Assert(gate.LeaseId != first, "Every grant must replace the generation");
        Equal(1, gate.Names.Count);
    }

    private static GateDeniedException Denied(Action action, string code = null)
    {
        try { action(); }
        catch (GateDeniedException error)
        {
            Assert(!string.IsNullOrWhiteSpace(error.Code), "Denial needs a stable code");
            if (code != null) Equal(code, error.Code);
            return error;
        }
        throw new Exception("Expected GateDeniedException");
    }

    private static void DemandScope()
    {
        var gate = new GatePolicy(() => 10d);
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, null), "gate_closed");
        gate.Grant("r", "m", new[] { "Smile", "Blink" }, EditCapability.Preview, 60);
        string lease = gate.LeaseId;
        gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Preview, lease);
        Denied(() => gate.Demand("R", "m", new[] { "Smile" }, EditCapability.Preview, lease), "scope_mismatch");
        Denied(() => gate.Demand("r", "M", new[] { "Smile" }, EditCapability.Preview, lease), "scope_mismatch");
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Preview, lease + " "), "lease_mismatch");
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Preview, null), "lease_mismatch");
        Denied(() => gate.Demand("r", "m", new[] { "smile" }, EditCapability.Preview, lease), "scope_mismatch");
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, lease), "capability_denied");
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.None, lease), "invalid_capability");
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, (EditCapability)4, lease), "invalid_capability");
        Denied(() => gate.Demand("r", "m", new[] { "Smile", "Smile" }, EditCapability.Preview, lease), "invalid_names");
        Denied(() => gate.Demand("r", "m", Array.Empty<string>(), EditCapability.Preview, lease), "invalid_names");
        Denied(() => gate.Demand("r", "m", null, EditCapability.Preview, lease), "invalid_names");
        Denied(() => gate.Demand("r", "m", new[] { " " }, EditCapability.Preview, lease), "invalid_names");
        Equal(30, gate.RemainingWrites, "Demand must not consume source writes");
        Assert(gate.Active, "A bad request must not grant or mutate scope");
    }

    private static void InvalidGrantAtomic()
    {
        var gate = new GatePolicy(() => 10d);
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 900, 100);
        string lease = gate.LeaseId;
        var invalid = new List<Action>();
        foreach (var value in new[] { 0d, -1d, 0.999d, 900.001d, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            invalid.Add(() => gate.Grant("new", "new", new[] { "Blink" }, EditCapability.Preview, value));
        foreach (var value in new[] { 0, -1, 101 })
            invalid.Add(() => gate.Grant("new", "new", new[] { "Blink" }, EditCapability.Preview, 10, value));
        foreach (var value in new[] { null, "", " ", "\t" })
        {
            invalid.Add(() => gate.Grant(value, "new", new[] { "Blink" }, EditCapability.Preview, 10));
            invalid.Add(() => gate.Grant("new", value, new[] { "Blink" }, EditCapability.Preview, 10));
        }
        foreach (var value in new[] { EditCapability.None, (EditCapability)4, (EditCapability)7, (EditCapability)(-1) })
            invalid.Add(() => gate.Grant("new", "new", new[] { "Blink" }, value, 10));
        foreach (var names in new IEnumerable<string>[] { null, Array.Empty<string>(), new[] { "" }, new[] { " " }, new[] { "Blink", "Blink" }, Enumerable.Range(0, 129).Select(i => "Shape" + i) })
            invalid.Add(() => gate.Grant("new", "new", names, EditCapability.Preview, 10));
        foreach (var action in invalid)
        {
            Denied(action);
            Equal(lease, gate.LeaseId, "Invalid grant changed generation");
            Equal("r", gate.TargetKey);
            Equal("m", gate.MeshKey);
            Equal(EditCapability.Apply, gate.Capabilities);
            Equal(900d, gate.RemainingSeconds);
            Equal(100, gate.RemainingWrites);
            Assert(gate.Names.SequenceEqual(new[] { "Smile" }), "Invalid grant changed names");
        }
        try { gate.Grant("new", "new", BrokenNames(), EditCapability.Apply, 10); throw new Exception("Expected iterator failure"); }
        catch (InvalidOperationException) { Equal(lease, gate.LeaseId); }
        gate.Grant(" r ", " m ", Enumerable.Range(0, 128).Select(i => "Shape" + i), EditCapability.Apply, 1, 1);
        Equal(" r ", gate.TargetKey, "Do not trim identifiers");
        Equal(128, gate.Names.Count);
    }

    private static IEnumerable<string> BrokenNames()
    {
        yield return "Blink";
        throw new InvalidOperationException("Input enumeration failed");
    }

    private static void Expiry()
    {
        double now = 10;
        var gate = new GatePolicy(() => now);
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 5);
        string lease = gate.LeaseId;
        now = 14.5;
        Equal(0.5d, gate.RemainingSeconds);
        Assert(gate.Active, "Unexpired lease must be active");
        now = 15;
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, lease), "gate_closed");
        Equal(false, gate.Active);
        Equal(0d, gate.RemainingSeconds);
        Equal(0, gate.RemainingWrites);
        now = 12;
        Equal(false, gate.Active, "Expired lease revived after time went backward");
        now = 20;
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 1);
        Assert(gate.Active && gate.LeaseId != lease, "Explicit fresh grant should reopen a new generation");
        now = 22;
        Equal(0, gate.RemainingWrites, "Budget property must observe expiry");
        Equal(false, gate.Active);
    }

    private static void ClockFailure()
    {
        foreach (double bad in new[] { 9d, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
        {
            double now = 10;
            var gate = new GatePolicy(() => now);
            gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10);
            string lease = gate.LeaseId;
            now = bad;
            Equal(false, gate.Active, "Backward or nonfinite clock must close");
            now = 11;
            Equal(false, gate.Active, "Clock recovery must not revive the old lease");
            Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, lease));
        }
        bool fail = false;
        var broken = new GatePolicy(() => fail ? throw new InvalidOperationException("clock unavailable") : 10d);
        broken.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10);
        fail = true;
        Equal(false, broken.Active, "A throwing clock must not leak active state");
        Denied(() => broken.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10), "clock_invalid");
        foreach (double bad in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity, double.MaxValue })
        {
            var gate = new GatePolicy(() => bad);
            Denied(() => gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10), "clock_invalid");
            Equal(false, gate.Active);
        }
        double tick = 20;
        var regression = new GatePolicy(() => tick);
        regression.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10);
        tick = 19;
        Denied(() => regression.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10), "clock_invalid");
        Equal(false, regression.Active);
        try { new GatePolicy(null); throw new Exception("Null clock accepted"); }
        catch (ArgumentNullException) { }
    }

    private static void WriteBudget()
    {
        double now = 10;
        var gate = new GatePolicy(() => now);
        Denied(() => gate.ConsumeWrite(), "gate_closed");
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Preview | EditCapability.Apply, 10, 2);
        string lease = gate.LeaseId;
        for (int i = 0; i < 5; i++)
            gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Preview, lease);
        Equal(2, gate.RemainingWrites);
        gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, lease);
        gate.ConsumeWrite(); // Source apply.
        Equal(1, gate.RemainingWrites);
        gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, lease);
        gate.ConsumeWrite(); // Source compare-and-restore rollback is also one write.
        Equal(0, gate.RemainingWrites);
        Denied(() => gate.ConsumeWrite(), "write_budget_exhausted");
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, lease), "write_budget_exhausted");
        gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Preview, lease);
        Assert(gate.Active, "Exhausting source writes must not disable authorized preview");
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Preview, 10);
        Denied(() => gate.ConsumeWrite(), "capability_denied");
        Equal(30, gate.RemainingWrites);
        now = 20;
        Denied(() => gate.ConsumeWrite(), "gate_closed");
    }

    private static void Revocation()
    {
        double now = 10;
        var gate = new GatePolicy(() => now);
        gate.Revoke();
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10);
        string old = gate.LeaseId;
        gate.Revoke();
        gate.Revoke();
        Assert(!gate.Active, "Revoked gate remained active");
        Equal(null, gate.LeaseId);
        Equal(null, gate.TargetKey);
        Equal(null, gate.MeshKey);
        Equal(0, gate.Names.Count);
        Equal(EditCapability.None, gate.Capabilities);
        Equal(0d, gate.RemainingSeconds);
        Equal(0, gate.RemainingWrites);
        Denied(() => gate.ConsumeWrite(), "gate_closed");
        now = 11;
        Assert(!gate.Active, "Revocation revived without local authorization");
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 10);
        Denied(() => gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, old), "lease_mismatch");
        gate.Demand("r", "m", new[] { "Smile" }, EditCapability.Apply, gate.LeaseId);
    }

    private static IEnumerable<string> NamesWithAction(Action action)
    {
        yield return "Smile";
        action();
    }

    private static void DemandFinalCheck()
    {
        double now = 10;
        var gate = new GatePolicy(() => now);
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 1);
        string lease = gate.LeaseId;
        Denied(() => gate.Demand("r", "m", NamesWithAction(() => now = 11), EditCapability.Apply, lease), "gate_closed");
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 1);
        lease = gate.LeaseId;
        Denied(() => gate.Demand("r", "m", NamesWithAction(gate.Revoke), EditCapability.Apply, lease), "gate_closed");
        gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 1);
        lease = gate.LeaseId;
        Denied(() => gate.Demand("r", "m", NamesWithAction(() => gate.Grant("r", "m", new[] { "Smile" }, EditCapability.Apply, 1)), EditCapability.Apply, lease), "lease_mismatch");
    }

    private static void DeltaBaseline()
    {
        var assembly = typeof(Program).Assembly;
        var editType = assembly.GetType("Yukino.VRChatManagedEditing.ShapeEdit");
        var deltaType = assembly.GetType("Yukino.VRChatManagedEditing.ShapeDelta");
        var policy = assembly.GetType("Yukino.VRChatManagedEditing.DeltaPolicy");
        Assert(editType != null && deltaType != null && policy != null, "Delta policy API is missing");
        Assert(editType.IsNotPublic && deltaType.IsNotPublic && policy.IsNotPublic, "Core types must remain internal");
        foreach (var property in deltaType.GetProperties()) Assert(!property.CanWrite, "Delta values must be immutable");
        foreach (var property in editType.GetProperties()) Assert(!property.CanWrite, "Edit values must be immutable");
        Assert(policy.GetMethod("ValidateCurrent") != null, "Missing compare-and-restore API");
        var edits = Array.CreateInstance(editType, 2);
        edits.SetValue(Activator.CreateInstance(editType, new object[] { "Smile", 45f }), 0);
        edits.SetValue(Activator.CreateInstance(editType, new object[] { "Blink", 0f }), 1);
        var current = new Dictionary<string, float> { ["Smile"] = -25f, ["Blink"] = 140f, ["Untouched"] = 73f };
        var result = ((System.Collections.IEnumerable)policy.GetMethod("ValidateChanges").Invoke(null, new object[] { current, edits })).Cast<object>().ToList();
        Equal(2, result.Count);
        Equal("Smile", (string)deltaType.GetProperty("Name").GetValue(result[0]));
        Equal(-25f, (float)deltaType.GetProperty("Before").GetValue(result[0]));
        Equal(45f, (float)deltaType.GetProperty("After").GetValue(result[0]));
        Equal(140f, (float)deltaType.GetProperty("Before").GetValue(result[1]));
        Equal(0f, (float)deltaType.GetProperty("After").GetValue(result[1]));
        Equal(-25f, current["Smile"]);
        Equal(140f, current["Blink"]);
        Equal(73f, current["Untouched"]);
    }

    private static void DeltaValidation()
    {
        var source = new Dictionary<string, float> { ["Smile"] = -20, ["Blink"] = 125 };
        var current = new System.Collections.ObjectModel.ReadOnlyDictionary<string, float>(source);
        foreach (float bad in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity, -float.Epsilon, 100.00001f })
            Denied(() => DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit("Smile", 20), new ShapeEdit("Blink", bad) }), "invalid_weight");
        foreach (var edits in new IEnumerable<ShapeEdit>[]
        {
            null, Array.Empty<ShapeEdit>(), new[] { default(ShapeEdit) },
            new[] { new ShapeEdit("", 0) }, new[] { new ShapeEdit(" ", 0) },
            new[] { new ShapeEdit("Smile", 5), new ShapeEdit("Smile", 6) }
        }) Denied(() => DeltaPolicy.ValidateChanges(current, edits), "invalid_changes");
        Denied(() => DeltaPolicy.ValidateChanges(null, new[] { new ShapeEdit("Smile", 0) }), "invalid_current");
        Denied(() => DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit("Smile", 20), new ShapeEdit("Missing", 0) }), "unknown_shape");
        foreach (float bad in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity })
        {
            source["Blink"] = bad;
            Denied(() => DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit("Smile", 20), new ShapeEdit("Blink", 0) }), "invalid_baseline");
            Equal(-20f, source["Smile"], "Rejected plan wrote an earlier valid item");
            Equal(bad, source["Blink"]);
        }
        source["Blink"] = 125;
        var limits = new Dictionary<string, float>();
        for (int i = 0; i < 129; i++) limits.Add("Shape" + i, i - 50);
        var all = limits.Keys.Select(name => new ShapeEdit(name, 100)).ToArray();
        Denied(() => DeltaPolicy.ValidateChanges(limits, all), "invalid_changes");
        Equal(128, DeltaPolicy.ValidateChanges(limits, all.Take(128)).Count);
        var bounds = DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit("Smile", 0), new ShapeEdit("Blink", 100) });
        Equal(0f, bounds[0].After);
        Equal(100f, bounds[1].After);
        Equal(-20f, source["Smile"]);
        Equal(125f, source["Blink"]);
    }

    private static void DeltaOrdinal()
    {
        var current = new Dictionary<string, float>(StringComparer.OrdinalIgnoreCase) { ["Smile"] = 20 };
        Denied(() => DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit("smile", 30) }), "unknown_shape");
        Denied(() => DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit(" Smile", 30) }), "unknown_shape");
        var exact = new Dictionary<string, float>(StringComparer.Ordinal) { ["Smile"] = 20, ["smile"] = 40, [" Smile "] = -7 };
        var result = DeltaPolicy.ValidateChanges(exact, new[] { new ShapeEdit("Smile", 30), new ShapeEdit("smile", 50), new ShapeEdit(" Smile ", 60) });
        Equal(3, result.Count);
        Equal(20f, result[0].Before);
        Equal(40f, result[1].Before);
        Equal(" Smile ", result[2].Name, "Do not normalize names");
        Equal(-7f, result[2].Before);
    }

    private static void CompareAndRestore()
    {
        var source = new Dictionary<string, float> { ["Smile"] = -25, ["Blink"] = 140, ["Untouched"] = 12 };
        var current = new System.Collections.ObjectModel.ReadOnlyDictionary<string, float>(source);
        var deltas = DeltaPolicy.ValidateChanges(current, new[] { new ShapeEdit("Smile", 45), new ShapeEdit("Blink", 60) });
        DeltaPolicy.ValidateCurrent(deltas, current);
        Equal(-25f, source["Smile"], "Preflight must not perform writes");
        source["Blink"] = MathF.BitIncrement(140f);
        Denied(() => DeltaPolicy.ValidateCurrent(deltas, current), "state_conflict");
        Equal(-25f, source["Smile"], "Failure on a later entry must not write an earlier one");
        source["Smile"] = 45;
        source["Blink"] = 60;
        source["Untouched"] = 81;
        DeltaPolicy.ValidateCurrent(deltas, current, rollback: true);
        Equal(45f, source["Smile"], "Rollback preflight must not perform writes");
        source["Blink"] = MathF.BitIncrement(60f);
        Denied(() => DeltaPolicy.ValidateCurrent(deltas, current, rollback: true), "state_conflict");
        Equal(MathF.BitIncrement(60f), source["Blink"], "Manual edit must remain untouched");
        source.Remove("Blink");
        Denied(() => DeltaPolicy.ValidateCurrent(deltas, current, rollback: true), "unknown_shape");
        var ignoreCase = new Dictionary<string, float>(StringComparer.OrdinalIgnoreCase) { ["smile"] = 45 };
        Denied(() => DeltaPolicy.ValidateCurrent(deltas.Take(1), ignoreCase, rollback: true), "unknown_shape");
    }

    private static void CurrentValidation()
    {
        var current = new Dictionary<string, float> { ["Smile"] = 20, ["Blink"] = 30 };
        var valid = new ShapeDelta("Smile", 20, 20);
        foreach (var deltas in new IEnumerable<ShapeDelta>[]
        {
            null, Array.Empty<ShapeDelta>(), new[] { default(ShapeDelta) },
            new[] { new ShapeDelta(" ", 20, 30) }, new[] { valid, valid }
        }) Denied(() => DeltaPolicy.ValidateCurrent(deltas, current), "invalid_changes");
        Denied(() => DeltaPolicy.ValidateCurrent(new[] { valid }, null), "invalid_current");
        foreach (float bad in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity })
        {
            Denied(() => DeltaPolicy.ValidateCurrent(new[] { valid, new ShapeDelta("Blink", bad, 30) }, current, rollback: true), "invalid_baseline");
            Denied(() => DeltaPolicy.ValidateCurrent(new[] { valid, new ShapeDelta("Blink", 30, bad) }, current), "invalid_weight");
            current["Blink"] = bad;
            Denied(() => DeltaPolicy.ValidateCurrent(new[] { valid, new ShapeDelta("Blink", 30, 40) }, current), "invalid_baseline");
            current["Blink"] = 30;
        }
        foreach (float bad in new[] { -1f, 101f })
            Denied(() => DeltaPolicy.ValidateCurrent(new[] { new ShapeDelta("Smile", 20, bad) }, current), "invalid_weight");
        var large = Enumerable.Range(0, 129).Select(i => new ShapeDelta("Shape" + i, -1, 100)).ToList();
        var weights = large.ToDictionary(delta => delta.Name, delta => delta.Before);
        Denied(() => DeltaPolicy.ValidateCurrent(large, weights), "invalid_changes");
        DeltaPolicy.ValidateCurrent(large.Take(128), weights);
        current["Smile"] = 40;
        DeltaPolicy.ValidateCurrent(new[] { new ShapeDelta("Smile", -1000, 40) }, current, rollback: true);
        DeltaPolicy.ValidateCurrent(new[] { new ShapeDelta("Smile", 1000, 40) }, current, rollback: true);
        Equal(40f, current["Smile"]);
        Equal(30f, current["Blink"]);
    }

    private static IEnumerable<ShapeDelta> DeltasWithAction(Action action)
    {
        yield return new ShapeDelta("Smile", 20, 40);
        action();
    }

    private static void CompareAfterEnumeration()
    {
        var current = new Dictionary<string, float> { ["Smile"] = 20 };
        Denied(() => DeltaPolicy.ValidateCurrent(DeltasWithAction(() => current["Smile"] = 21), current), "state_conflict");
        Equal(21f, current["Smile"]);
        current["Smile"] = 40;
        Denied(() => DeltaPolicy.ValidateCurrent(DeltasWithAction(() => current["Smile"] = 41), current, rollback: true), "state_conflict");
        Equal(41f, current["Smile"]);
    }

}
