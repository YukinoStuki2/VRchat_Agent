using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;

namespace Yukino.VRChatManagedEditing
{
    internal readonly struct ShapeEdit
    {
        public string Name { get; }
        public float Weight { get; }
        public ShapeEdit(string name, float weight) { Name = name; Weight = weight; }
    }

    internal readonly struct ShapeDelta
    {
        public string Name { get; }
        public float Before { get; }
        public float After { get; }
        public ShapeDelta(string name, float before, float after) { Name = name; Before = before; After = after; }
    }

    // Pure preflight only: never changes source dictionaries or Unity objects.
    // The adapter must validate the entire batch before performing its first write.
    internal static class DeltaPolicy
    {
        public static List<ShapeDelta> ValidateChanges(IDictionary<string, float> current, IEnumerable<ShapeEdit> edits)
        {
            if (current == null) throw new GateDeniedException("invalid_current", "Current weights are required.");
            // Never trust a caller's dictionary comparer to enforce exact names.
            var baseline = new Dictionary<string, float>(current, StringComparer.Ordinal);
            if (edits == null) throw new GateDeniedException("invalid_changes", "Requested edits are required.");
            var result = new List<ShapeDelta>();
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var edit in edits)
            {
                if (result.Count >= 128 || string.IsNullOrWhiteSpace(edit.Name) || !seen.Add(edit.Name))
                    throw new GateDeniedException("invalid_changes", "Edits must have unique exact names and be limited to 128.");
                if (!Finite(edit.Weight) || edit.Weight < 0 || edit.Weight > 100)
                    throw new GateDeniedException("invalid_weight", "Requested weights must be finite and within 0..100.");
                float before;
                if (!baseline.TryGetValue(edit.Name, out before))
                    throw new GateDeniedException("unknown_shape", "An exact requested BlendShape does not exist.");
                if (!Finite(before)) throw new GateDeniedException("invalid_baseline", "Original weights must be finite.");
                result.Add(new ShapeDelta(edit.Name, before, edit.Weight));
            }
            if (result.Count == 0) throw new GateDeniedException("invalid_changes", "At least one edit is required.");
            return result;
        }

        private static bool Finite(float value) { return !float.IsNaN(value) && !float.IsInfinity(value); }

        public static void ValidateCurrent(IEnumerable<ShapeDelta> deltas, IDictionary<string, float> current, bool rollback = false)
        {
            if (current == null) throw new GateDeniedException("invalid_current", "Current weights are required.");
            if (deltas == null) throw new GateDeniedException("invalid_changes", "Planned deltas are required.");
            var batch = new List<ShapeDelta>();
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var delta in deltas)
            {
                if (seen.Count >= 128 || string.IsNullOrWhiteSpace(delta.Name) || !seen.Add(delta.Name))
                    throw new GateDeniedException("invalid_changes", "Deltas must have unique exact names and be limited to 128.");
                if (!Finite(delta.Before)) throw new GateDeniedException("invalid_baseline", "Original weights must be finite.");
                if (!Finite(delta.After) || delta.After < 0 || delta.After > 100)
                    throw new GateDeniedException("invalid_weight", "Planned requested weights must be finite and within 0..100.");
                batch.Add(delta);
            }
            if (batch.Count == 0) throw new GateDeniedException("invalid_changes", "At least one delta is required.");
            // Finish potentially lazy input enumeration before reading current state.
            var snapshot = new Dictionary<string, float>(current, StringComparer.Ordinal);
            foreach (var delta in batch)
            {
                float actual;
                if (!snapshot.TryGetValue(delta.Name, out actual))
                    throw new GateDeniedException("unknown_shape", "An exact planned BlendShape no longer exists.");
                if (!Finite(actual)) throw new GateDeniedException("invalid_baseline", "Current weights must be finite.");
                float expected = rollback ? delta.After : delta.Before;
                if (actual != expected)
                    throw new GateDeniedException("state_conflict", "A planned field changed; manual edits will not be overwritten.");
            }
        }
    }

    [Flags]
    internal enum EditCapability { None = 0, Preview = 1, Apply = 2 }

    internal sealed class GateDeniedException : Exception
    {
        public string Code { get; }
        public GateDeniedException(string code, string message) : base(message) { Code = code; }
    }

    // In-memory policy for serialized Unity editor/main-thread calls, not a lock.
    // Grant is for the local operator only; transport must never expose it.
    // The host must Revoke on reload, play mode, scene changes and window close.
    internal sealed class GatePolicy
    {
        private readonly Func<double> clock;
        private bool active;
        private double expiresAt;
        private int remainingWrites;
        private double lastClock = double.NegativeInfinity;
        public GatePolicy(Func<double> clock) { this.clock = clock ?? throw new ArgumentNullException(nameof(clock)); }
        public string LeaseId { get; private set; }
        public bool Active { get { return Refresh(); } }
        public string TargetKey { get; private set; }
        public string MeshKey { get; private set; }
        public IReadOnlyCollection<string> Names { get; private set; } = new ReadOnlyCollection<string>(new List<string>());
        public EditCapability Capabilities { get; private set; }
        public double RemainingSeconds { get { double now; return Refresh(out now) ? expiresAt - now : 0; } }
        public int RemainingWrites { get { return Refresh() ? remainingWrites : 0; } }

        private bool TryReadClock(out double now)
        {
            now = 0;
            try { now = clock(); }
            catch (Exception) { active = false; return false; }
            if (double.IsNaN(now) || double.IsInfinity(now) || now < lastClock)
            {
                active = false;
                return false;
            }
            lastClock = now;
            return true;
        }

        private bool Refresh() { double now; return Refresh(out now); }
        private bool Refresh(out double now)
        {
            now = 0;
            if (!active) return false;
            if (!TryReadClock(out now)) return false;
            if (now >= expiresAt) active = false;
            return active;
        }

        public void Grant(string targetKey, string meshKey, IEnumerable<string> names,
            EditCapability caps, double ttlSeconds, int writeBudget = 30)
        {
            if (string.IsNullOrWhiteSpace(targetKey) || string.IsNullOrWhiteSpace(meshKey))
                throw new GateDeniedException("invalid_scope", "An exact target and source mesh are required.");
            ValidateCapability(caps);
            if (double.IsNaN(ttlSeconds) || double.IsInfinity(ttlSeconds) || ttlSeconds < 1 || ttlSeconds > 900)
                throw new GateDeniedException("invalid_ttl", "Lease duration must be finite and within 1..900 seconds.");
            if (writeBudget < 1 || writeBudget > 100)
                throw new GateDeniedException("invalid_budget", "Write budget must be within 1..100.");
            var snapshot = ValidateNames(names);
            double now;
            if (!TryReadClock(out now)) throw new GateDeniedException("clock_invalid", "A finite monotonic clock is required.");
            double deadline = now + ttlSeconds;
            if (double.IsInfinity(deadline) || deadline <= now)
            {
                active = false;
                throw new GateDeniedException("clock_invalid", "Clock cannot represent the requested deadline.");
            }
            // Prepare every value before publishing the new authorization state.
            var readOnlyNames = new ReadOnlyCollection<string>(snapshot);
            string newLeaseId = Guid.NewGuid().ToString("D");
            TargetKey = targetKey;
            MeshKey = meshKey;
            Names = readOnlyNames;
            Capabilities = caps;
            expiresAt = deadline;
            remainingWrites = writeBudget;
            LeaseId = newLeaseId;
            active = true;
        }
        public void Demand(string targetKey, string meshKey, IEnumerable<string> names,
            EditCapability capability, string leaseId)
        {
            if (!Active) throw new GateDeniedException("gate_closed", "No active local authorization.");
            var requested = ValidateNames(names);
            // Enumerating a caller-supplied sequence may take time or run callbacks.
            if (!Active) throw new GateDeniedException("gate_closed", "No active local authorization.");
            if (!string.Equals(LeaseId, leaseId, StringComparison.Ordinal))
                throw new GateDeniedException("lease_mismatch", "The lease generation has changed.");
            ValidateCapability(capability);
            if ((Capabilities & capability) != capability)
                throw new GateDeniedException("capability_denied", "The requested capability was not granted.");
            if ((capability & EditCapability.Apply) != 0 && remainingWrites <= 0)
                throw new GateDeniedException("write_budget_exhausted", "No source writes remain in this lease.");
            if (!string.Equals(TargetKey, targetKey, StringComparison.Ordinal) ||
                !string.Equals(MeshKey, meshKey, StringComparison.Ordinal))
                throw new GateDeniedException("scope_mismatch", "Target or source mesh differs from the local grant.");
            var allowed = new HashSet<string>(Names, StringComparer.Ordinal);
            foreach (var name in requested)
                if (!allowed.Contains(name))
                    throw new GateDeniedException("scope_mismatch", "A BlendShape name was not granted.");
        }

        private static void ValidateCapability(EditCapability capability)
        {
            if (capability == EditCapability.None || (capability & ~(EditCapability.Preview | EditCapability.Apply)) != 0)
                throw new GateDeniedException("invalid_capability", "Only Preview and Apply capabilities are valid.");
        }

        private static List<string> ValidateNames(IEnumerable<string> names)
        {
            if (names == null) throw new GateDeniedException("invalid_names", "BlendShape names are required.");
            var result = new List<string>();
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var name in names)
            {
                if (result.Count >= 128 || string.IsNullOrWhiteSpace(name) || !seen.Add(name))
                    throw new GateDeniedException("invalid_names", "Names must be exact, nonblank, unique and limited to 128.");
                result.Add(name);
            }
            if (result.Count == 0) throw new GateDeniedException("invalid_names", "Select at least one BlendShape.");
            return result;
        }
        // Call once for each source apply or rollback transaction, never for preview.
        // The adapter must Demand the complete scope before invoking this method.
        public void ConsumeWrite()
        {
            if (!Active) throw new GateDeniedException("gate_closed", "No active local authorization.");
            if ((Capabilities & EditCapability.Apply) == 0)
                throw new GateDeniedException("capability_denied", "Source writes were not granted.");
            if (remainingWrites <= 0)
                throw new GateDeniedException("write_budget_exhausted", "No source writes remain in this lease.");
            remainingWrites--;
        }
        public void Revoke()
        {
            active = false;
            LeaseId = null;
            TargetKey = null;
            MeshKey = null;
            Names = new ReadOnlyCollection<string>(new List<string>());
            Capabilities = EditCapability.None;
            remainingWrites = 0;
            expiresAt = 0;
        }
    }
}
