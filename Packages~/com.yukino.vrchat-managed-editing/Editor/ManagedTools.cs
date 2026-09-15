using System;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatManagedEditing
{
    // No grant/unlock/extend operation is registered. Authority is local UI only.
    internal static class ManagedReply
    {
        internal static object Run(Func<JObject> action)
        {
            bool wasActive = ManagedSession.Gate.Active;
            string previousLease = ManagedSession.Gate.LeaseId;
            JObject reply;
            try { reply = action(); }
            catch (GateDeniedException e) { reply = Error(e.Code, e.Message, false); }
            catch (ArgumentException e) { reply = Error("INVALID_ARGUMENT", e.Message, false); }
            catch (Newtonsoft.Json.JsonException) { reply = Error("INVALID_JSON", "Use a bounded JSON array of exact name/value objects.", false); }
            catch (Exception e)
            {
                // Never claim a generic failure proves zero mutation. Caller must inspect.
                reply = Error("EDITOR_FAILURE", e.GetType().Name + ": " + e.Message, null);
            }
            bool active = ManagedSession.Gate.Active;
            var data = (JObject)reply["data"];
            data["permission_changed"] = wasActive != active || previousLease != ManagedSession.Gate.LeaseId;
            data["active"] = active;
            return reply;
        }
        private static JObject Error(string code, string message, bool? mutated)
        {
            if (message.Length > 600) message = message.Substring(0, 600);
            return new JObject { ["success"] = false, ["error"] = code, ["message"] = message,
                ["data"] = new JObject { ["code"] = code, ["mutated"] = mutated.HasValue ? new JValue(mutated.Value) : JValue.CreateNull(),
                    ["recovery"] = "Inspect status and Unity. Never retry an uncertain write blindly." } };
        }
    }

    [McpForUnityTool("vrchat_me_status", Description = "Inspect local operator-granted BlendShape scope and pending transaction. Does not grant authority.", AutoRegister = true, Group = "core")]
    public static class VrchatMeStatus
    {
        public sealed class Parameters { }
        public static object HandleCommand(JObject parameters) { return ManagedReply.Run(() => ManagedSession.Status()); }
    }

    [McpForUnityTool("vrchat_me_plan", Description = "Plan exact BlendShape values on the locally selected renderer without scene writes. Unknown names and partial batches are rejected.", AutoRegister = true, Group = "core")]
    public static class VrchatMePlan
    {
        public sealed class Parameters
        {
            [ToolParameter("JSON array of exact {name: string, value: number} objects, maximum 128. Values 0-100. No fuzzy matching.", Required = true)]
            public string changes_json { get; set; }
        }
        public static object HandleCommand(JObject parameters) { return ManagedReply.Run(() => ManagedSession.Plan(parameters)); }
    }

    [McpForUnityTool("vrchat_me_preview", Description = "Render isolated before/after BlendShape images. Requires local Preview permission; never changes source weights or saves assets.", AutoRegister = true, Group = "core")]
    public static class VrchatMePreview
    {
        public sealed class Parameters
        {
            [ToolParameter("Exact pending plan ID.", Required = true)] public string plan_id { get; set; }
            [ToolParameter("Include bounded PNG images for the restrictive bridge to return as native MCP images.", Required = false, DefaultValue = "false")]
            public bool include_images { get; set; }
        }
        public static object HandleCommand(JObject parameters)
        {
            return ManagedReply.Run(() => {
                ManagedSession.OnlyKeys(parameters, "plan_id", "include_images");
                JToken images = parameters["include_images"];
                if (images != null && images.Type != JTokenType.Boolean) throw new ArgumentException("include_images must be boolean.");
                return ManagedSession.Preview(ManagedSession.RequireId(parameters, "plan_id"), (bool?)images ?? false);
            });
        }
    }

    [McpForUnityTool("vrchat_me_apply", Description = "Apply one exact pending plan within local Apply permission. Checks mesh, grant, expiry, and every before-value before any mutation. Does not save scene or prefab.", AutoRegister = true, Group = "core")]
    public static class VrchatMeApply
    {
        public sealed class Parameters { [ToolParameter("Exact pending plan ID.", Required = true)] public string plan_id { get; set; } }
        public static object HandleCommand(JObject parameters)
        {
            return ManagedReply.Run(() => { ManagedSession.OnlyKeys(parameters, "plan_id"); return ManagedSession.Apply(ManagedSession.RequireId(parameters, "plan_id")); });
        }
    }

    [McpForUnityTool("vrchat_me_rollback", Description = "Restore only the last package-owned change, refusing manually changed fields. Requires current local Apply permission. No global undo/reset.", AutoRegister = true, Group = "core")]
    public static class VrchatMeRollback
    {
        public sealed class Parameters { [ToolParameter("Exact last apply ID from status or apply result.", Required = true)] public string apply_id { get; set; } }
        public static object HandleCommand(JObject parameters)
        {
            return ManagedReply.Run(() => { ManagedSession.OnlyKeys(parameters, "apply_id"); return ManagedSession.Rollback(ManagedSession.RequireId(parameters, "apply_id")); });
        }
    }
}
