using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Pure synchronous core. Only Unity-local UI calls Approve/SetCapability.
    // This is the managed MCP boundary, not a local-admin or terminal sandbox.
    public sealed class CandidateGate
    {
        sealed class Plan
        {
            internal string Id, Digest, Client, Connection, Project, Task;
            internal double Expires;
            internal bool Approved;
            internal JObject Manifest;
            internal Dictionary<string, string> Evidence;
        }
        readonly Func<double> clock;
        readonly Func<string> project, connection;
        readonly Func<string, string> evidence;
        readonly Func<string, JObject, JObject> native;
        readonly Dictionary<string, Plan> plans = new Dictionary<string, Plan>(StringComparer.Ordinal);
        readonly HashSet<string> capabilities = new HashSet<string>(StringComparer.Ordinal);
        readonly object sync = new object();
        bool busy;
        long generation;
        string observedProject, observedConnection;
        public string LastReason { get; private set; } = "默认关闭";

        public CandidateGate(Func<double> clock, Func<string> project, Func<string> connection,
            Func<string, string> evidence, Func<string, JObject, JObject> native)
        {
            this.clock = clock; this.project = project; this.connection = connection;
            this.evidence = evidence; this.native = native;
        }
        sealed class Denied : Exception { internal Denied(string code) : base(code) {} }
        static void Require(bool ok, string code) { if (!ok) throw new Denied(code); }
        static string Text(JToken token)
        {
            Require(token != null && token.Type == JTokenType.String, "invalid_string");
            string value = (string)token;
            Require(value.Length > 0 && value.Length <= 512 && value == value.Trim() && !value.Any(char.IsControl), "invalid_string");
            return value;
        }
        static void Keys(JObject value, params string[] keys)
        {
            Require(value != null && value.Count == keys.Length && value.Properties().All(p => keys.Contains(p.Name)), "unexpected_fields");
        }
        static string Op(string command, string action)
        {
            Require((command == "manage_material" && action == "get_material_info") ||
                (command == "manage_animation" && action == "controller_get_info"), "operation_not_supported");
            return command + "/" + action;
        }
        static string PathValue(JToken token)
        {
            string path = Text(token);
            Require(path.StartsWith("Assets/", StringComparison.Ordinal) && path.IndexOfAny(new[] { '\\', ':' }) < 0 &&
                path.Split('/').All(p => p.Length > 0 && p != "." && p != ".." && p == p.Trim()), "invalid_target");
            Require(path.EndsWith(".mat", StringComparison.Ordinal) || path.EndsWith(".controller", StringComparison.Ordinal), "invalid_target");
            return path;
        }
        static JObject Ok(JObject data) => new JObject { ["success"] = true, ["data"] = data };
        static JObject Error(string code) => new JObject { ["success"] = false, ["error"] = code,
            ["data"] = new JObject { ["status"] = "denied", ["reason"] = code, ["read_only"] = true } };
        public bool Allows(string command, string action)
        {
            lock (sync) return capabilities.Contains(Op(command, action));
        }
        public void SetCapability(string command, string action, bool allowed)
        {
            lock (sync)
            {
                string op = Op(command, action);
                if (allowed) capabilities.Add(op);
                else { capabilities.Remove(op); StopAll("本地能力已撤销"); }
            }
        }
        public void StopAll(string reason)
        {
            lock (sync) { generation++; plans.Clear(); LastReason = reason; }
        }
        public void Observe()
        {
            lock (sync)
            {
                string p = project(), c = connection();
                if (p != observedProject || c != observedConnection || string.IsNullOrEmpty(c))
                { generation++; plans.Clear(); observedProject = p; observedConnection = c; LastReason = "工程或连接变化，需重新批准"; }
                foreach (string key in plans.Where(x => x.Value.Expires <= clock()).Select(x => x.Key).ToArray()) plans.Remove(key);
            }
        }
        Dictionary<string, string> Capture(JObject manifest)
        {
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (JToken path in (JArray)manifest["targets"])
            {
                string value = evidence((string)path);
                Require(!string.IsNullOrEmpty(value), "evidence_unavailable");
                result.Add((string)path, value);
            }
            return result;
        }
        void Current(Plan plan, bool approved)
        {
            Observe();
            Require(plans.TryGetValue(plan.Client, out var current) && ReferenceEquals(current, plan), "plan_not_current");
            Require(plan.Project == project() && plan.Connection == connection(), "binding_changed");
            Require(!approved || plan.Approved, "local_approval_required");
            foreach (JObject op in (JArray)plan.Manifest["operations"])
                Require(capabilities.Contains(Op((string)op["command"], (string)op["action"])), "local_capability_disabled");
        }
        void VerifyEvidence(Plan plan)
        {
            var actual = Capture(plan.Manifest);
            Require(actual.Count == plan.Evidence.Count && actual.All(p => plan.Evidence.TryGetValue(p.Key, out var old) && old == p.Value), "relevant_evidence_changed");
            Current(plan, false); // A local callback may have revoked/replaced during capture.
        }
        public JArray LocalPlans()
        {
            lock (sync)
            {
                Observe();
                return new JArray(plans.Values.Select(p => new JObject {
                    ["plan_id"] = p.Id, ["digest"] = p.Digest, ["client_id"] = p.Client, ["task_id"] = p.Task,
                    ["connection_id"] = p.Connection, ["project_id"] = p.Project, ["approved"] = p.Approved,
                    ["seconds_left"] = Math.Max(0, p.Expires - clock()), ["manifest"] = p.Manifest.DeepClone() }));
            }
        }
        public bool Approve(string id, string digest)
        {
            lock (sync)
            {
                Plan plan = plans.Values.FirstOrDefault(p => p.Id == id);
                if (plan == null) return false;
                try
                {
                    Require(!busy && digest == plan.Digest, "approval_mismatch");
                    Current(plan, false); VerifyEvidence(plan); plan.Approved = true;
                    LastReason = "本地已批准；仅本任务、本连接、本清单"; return true;
                }
                catch { plans.Remove(plan.Client); LastReason = "批准失败，清单已撤销"; return false; }
            }
        }
        public JObject Dispatch(JObject request)
        {
            lock (sync)
            {
                string client = null;
                bool stopRequest = false;
                if (busy) return Error("execution_in_progress");
                busy = true;
                try
                {
                    Require(request != null && request.ToString(Formatting.None).Length <= 65536, "request_too_large");
                    var r = (JObject)request.DeepClone();
                    Keys(r, "protocol", "kind", "project_id", "client_id", "connection_id", "task_id", "plan_id", "body");
                    stopRequest = (string)r["kind"] == "stop";
                    Require(r["protocol"].Type == JTokenType.Integer && (int)r["protocol"] == 1, "unsupported_protocol");
                    Observe(); client = Text(r["client_id"]);
                    Require(Text(r["project_id"]) == project() && Text(r["connection_id"]) == connection(), "binding_changed");
                    string kind = Text(r["kind"]); var body = r["body"] as JObject;
                    if (kind == "status")
                    {
                        Keys(body); Require((string)r["plan_id"] == "" && (string)r["task_id"] == "", "unexpected_identity");
                        return Ok(new JObject { ["status"] = capabilities.Count == 0 ? "本地能力关闭" : "等待本地清单批准",
                            ["capabilities"] = new JArray(capabilities), ["read_only"] = true });
                    }
                    string task = Text(r["task_id"]);
                    if (kind == "prepare")
                    {
                        plans.Remove(client);
                        Require((string)r["plan_id"] == "", "unexpected_identity");
                        Keys(body, "operations", "targets", "ttl_seconds");
                        var ops = body["operations"] as JArray; var targets = body["targets"] as JArray;
                        Require(ops != null && ops.Count > 0 && ops.Count <= 2 && targets != null && targets.Count > 0 && targets.Count <= 64, "invalid_manifest");
                        var seen = new HashSet<string>(StringComparer.Ordinal);
                        foreach (JToken item in ops)
                        {
                            var op = item as JObject; Keys(op, "command", "action");
                            string key = Op(Text(op["command"]), Text(op["action"]));
                            Require(seen.Add(key) && capabilities.Contains(key), "local_capability_disabled");
                        }
                        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                        foreach (JToken token in targets)
                        {
                            string path = PathValue(token);
                            Require(paths.Add(path), "duplicate_target");
                            Require((path.EndsWith(".mat", StringComparison.Ordinal) && seen.Contains("manage_material/get_material_info")) ||
                                (path.EndsWith(".controller", StringComparison.Ordinal) && seen.Contains("manage_animation/controller_get_info")), "target_operation_mismatch");
                        }
                        Require(body["ttl_seconds"].Type == JTokenType.Float || body["ttl_seconds"].Type == JTokenType.Integer, "invalid_ttl");
                        double ttl = (double)body["ttl_seconds"];
                        Require(!double.IsNaN(ttl) && !double.IsInfinity(ttl) && ttl > 0 && ttl <= 900, "invalid_ttl");
                        Require(plans.Count < 128, "plan_capacity");
                        var plan = new Plan { Id = Guid.NewGuid().ToString("N"), Client = client, Project = project(), Connection = connection(),
                            Task = task, Expires = clock() + ttl, Manifest = (JObject)body.DeepClone() };
                        long startedGeneration = generation;
                        plan.Evidence = Capture(plan.Manifest);
                        Require(generation == startedGeneration && clock() < plan.Expires, "prepare_cancelled");
                        Require(plan.Project == project() && plan.Connection == connection(), "binding_changed");
                        var digestInput = new JObject { ["id"] = plan.Id, ["project"] = plan.Project, ["client"] = client,
                            ["connection"] = plan.Connection, ["task"] = task, ["manifest"] = plan.Manifest.DeepClone(),
                            ["evidence"] = JObject.FromObject(plan.Evidence) };
                        using (var hash = SHA256.Create()) plan.Digest = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(digestInput.ToString(Formatting.None)))).Replace("-", "").ToLowerInvariant();
                        plans[client] = plan; LastReason = "等待本地核对清单";
                        return Ok(new JObject { ["status"] = "pending", ["plan_id"] = plan.Id, ["digest"] = plan.Digest });
                    }
                    Require(plans.TryGetValue(client, out var active) && active.Task == task, "plan_not_current");
                    Require((string)r["plan_id"] == active.Id, "plan_mismatch");
                    if (kind == "stop") { Keys(body); plans.Remove(client); LastReason = "已停止，不回退文件"; return Ok(new JObject { ["status"] = "stopped" }); }
                    Require(kind == "execute", "unknown_kind");
                    Keys(body, "command", "params"); string command = Text(body["command"]);
                    var args = body["params"] as JObject;
                    string keyName = command == "manage_material" ? "materialPath" : "controllerPath";
                    Keys(args, "action", keyName); string action = Text(args["action"]); string target = PathValue(args[keyName]);
                    string operation = Op(command, action);
                    Require(((JArray)active.Manifest["operations"]).Cast<JObject>().Any(x => (string)x["command"] == command && (string)x["action"] == action) &&
                        ((JArray)active.Manifest["targets"]).Any(x => (string)x == target), "outside_plan");
                    Current(active, true); VerifyEvidence(active); Current(active, true);
                    JObject result = native(command, (JObject)args.DeepClone());
                    Require(result != null && result["success"]?.Type == JTokenType.Boolean, "native_result_invalid");
                    if ((bool)result["success"] != true) { plans.Remove(client); LastReason = "原生命令失败；已撤权，未自动回退"; return Error("native_read_failed"); }
                    VerifyEvidence(active); Current(active, true);
                    return result;
                }
                catch (Exception e)
                {
                    // Delayed lifecycle cleanup must never revoke a newer plan.
                    // Stop only removes the exact task/plan after validation above.
                    if (client != null && !stopRequest) plans.Remove(client);
                    LastReason = stopRequest ? "停止请求被拒绝" : "请求失败，需重新核对清单";
                    // No raw paths/Unity exception detail is sent remotely.
                    return Error(e is Denied ? e.Message : "local_validation_failed");
                }
                finally { busy = false; }
            }
        }
    }
}
