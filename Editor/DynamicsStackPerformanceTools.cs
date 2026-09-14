using System;
using System.Collections.Generic;
using System.Linq;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatReadonlyMcp.Editor
{
    [McpForUnityTool("vrchat_ro_dynamics", Description = "Read-only PhysBone, collider, Contact, VRChat Constraint, and Unity Constraint inventory with bounded serialized diagnostics.", AutoRegister = true, Group = "core")]
    public static class VrchatRoDynamics
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar or subtree target.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Maximum component rows/properties returned (1-1000).", Required = false, DefaultValue = "300")] public int max_items { get; set; }
            [ToolParameter("Maximum property detail depth (0-8).", Required = false, DefaultValue = "2")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 300, 1, 1000);
            int maxDepth = RoParams.Int(parameters, "max_depth", 2, 0, 8);
            JArray rows = new JArray();
            Dictionary<string, int> counts = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (Component component in resolved.GameObject.GetComponentsInChildren<Component>(true))
            {
                if (component == null) continue;
                string fullName = VrchatRoCommon.FullName(component);
                string category = Category(component, fullName);
                if (category == null) continue;
                if (!counts.ContainsKey(category)) counts[category] = 0;
                counts[category]++;
                if (rows.Count >= maxItems) continue;
                JObject row = new JObject
                {
                    ["category"] = category,
                    ["type"] = fullName,
                    ["path"] = VrchatRoCommon.HierarchyPath(component.gameObject, true),
                    ["instance_id"] = component.GetInstanceID(),
                    ["properties"] = VrchatRoCommon.ShallowSerialized(component, Mathf.Clamp(maxItems / 10, 10, 50), maxDepth),
                    ["max_depth"] = maxDepth
                };
                if (fullName == VrchatRoCommon.PhysBoneType)
                    row["affected_transforms_estimate"] = VrchatRoCommon.PhysBoneAffectedTransforms(component);
                rows.Add(row);
            }
            JObject countObject = new JObject();
            foreach (KeyValuePair<string, int> entry in counts.OrderBy(x => x.Key)) countObject[entry.Key] = entry.Value;
            return ReadOnlyResponse.Ok("Avatar dynamics inspected without simulation, gizmo changes, Play Mode, or component edits.", new JObject
            {
                ["target"] = VrchatRoCommon.Identity(resolved.GameObject),
                ["counts"] = countObject,
                ["returned"] = rows.Count,
                ["truncated"] = counts.Values.Sum() > rows.Count,
                ["components"] = rows,
                ["permission_note"] = "PhysBone and Contact interaction permissions are reported from serialized state only; no interaction is simulated."
            }, maxItems);
        }

        private static string Category(Component component, string type)
        {
            if (type == VrchatRoCommon.PhysBoneType) return "physbone";
            if (type == VrchatRoCommon.PhysBoneColliderType) return "physbone_collider";
            if (type == VrchatRoCommon.ContactSenderType) return "contact_sender";
            if (type == VrchatRoCommon.ContactReceiverType) return "contact_receiver";
            if (type.IndexOf("VRC.SDK3.Dynamics.Constraint.Components.VRC", StringComparison.Ordinal) >= 0) return "vrc_constraint";
            if (component is UnityEngine.Animations.IConstraint) return "unity_constraint";
            return null;
        }
    }

    [McpForUnityTool("vrchat_ro_modular_stack", Description = "Read-only inventory of Modular Avatar, NDMF, VRCFury, FaceEmo, Avatar Optimizer, lilToon, and related source-vs-generated authoring clues.", AutoRegister = true, Group = "core")]
    public static class VrchatRoModularStack
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar or subtree target.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Maximum integration component rows (1-1000).", Required = false, DefaultValue = "300")] public int max_items { get; set; }
            [ToolParameter("Maximum shallow serialized property depth (0-8).", Required = false, DefaultValue = "2")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 300, 1, 1000);
            int maxDepth = RoParams.Int(parameters, "max_depth", 2, 0, 8);
            JArray rows = new JArray();
            int total = 0;
            foreach (Component component in resolved.GameObject.GetComponentsInChildren<Component>(true))
            {
                if (component == null) continue;
                string fullName = VrchatRoCommon.FullName(component);
                string family = Family(fullName);
                if (family == null) continue;
                total++;
                if (rows.Count >= maxItems) continue;
                rows.Add(new JObject
                {
                    ["family"] = family,
                    ["type"] = fullName,
                    ["path"] = VrchatRoCommon.HierarchyPath(component.gameObject, true),
                    ["instance_id"] = component.GetInstanceID(),
                    ["is_preview_or_generated"] = VrchatRoCommon.IsPreviewOrGenerated(component.gameObject),
                    ["properties"] = VrchatRoCommon.ShallowSerialized(component, Mathf.Clamp(maxItems / 10, 10, 50), maxDepth),
                    ["max_depth"] = maxDepth
                });
            }
            JArray liltoonMaterials = new JArray(VrchatRoCommon.UniqueSharedMaterials(resolved.GameObject)
                .Where(m => m.shader != null && m.shader.name.IndexOf("lilToon", StringComparison.OrdinalIgnoreCase) >= 0)
                .Take(maxItems)
                .Select(m => new JObject { ["material"] = VrchatRoCommon.ObjectRef(m), ["shader"] = m.shader.name }));
            return ReadOnlyResponse.Ok("Non-destructive authoring stack inventoried; generated/preview objects were not treated as editable sources.", new JObject
            {
                ["target"] = VrchatRoCommon.Identity(resolved.GameObject),
                ["integrations"] = VrchatRoCommon.IntegrationFlags(resolved.GameObject),
                ["component_count"] = total,
                ["components"] = rows,
                ["lilToon_materials"] = liltoonMaterials,
                ["truncated"] = total > rows.Count,
                ["source_warning"] = "Objects in ___NDMF Preview___ or marked generated are diagnostic output, not authoring source."
            }, maxItems);
        }

        private static string Family(string type)
        {
            if (type.IndexOf("ModularAvatar", StringComparison.OrdinalIgnoreCase) >= 0) return "ModularAvatar";
            if (type.IndexOf("nadena.dev.ndmf", StringComparison.OrdinalIgnoreCase) >= 0 || type.IndexOf("NDMF", StringComparison.OrdinalIgnoreCase) >= 0) return "nadena.dev.ndmf";
            if (type.IndexOf("VRCFury", StringComparison.OrdinalIgnoreCase) >= 0) return "VRCFury";
            if (type.IndexOf("FaceEmo", StringComparison.OrdinalIgnoreCase) >= 0) return "FaceEmo";
            if (type.IndexOf("AvatarOptimizer", StringComparison.OrdinalIgnoreCase) >= 0 || type.IndexOf("Anatawa12", StringComparison.OrdinalIgnoreCase) >= 0) return "AvatarOptimizer";
            if (type.StartsWith("VRC.", StringComparison.Ordinal)) return "VRChat SDK";
            return null;
        }
    }

    [McpForUnityTool("vrchat_ro_performance", Description = "Read-only VRChat avatar performance metric collection with advisory PC rank and Quest readiness snapshots.", AutoRegister = true, Group = "core")]
    public static class VrchatRoPerformance
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar root; optional when exactly one descriptor exists.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Reserved maximum detail rows (1-500).", Required = false, DefaultValue = "200")] public int max_items { get; set; }
            [ToolParameter("Reserved hierarchy depth bound (0-12).", Required = false, DefaultValue = "6")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters, true);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 200, 1, 500);
            JObject report = VrchatRoCommon.Performance(resolved.GameObject);
            report["target"] = VrchatRoCommon.Identity(resolved.GameObject);
            report["max_items"] = maxItems;
            report["max_depth"] = RoParams.Int(parameters, "max_depth", 6, 0, 12);
            report["official_docs"] = "https://creators.vrchat.com/avatars/avatar-performance-ranking-system/";
            return ReadOnlyResponse.Ok("Performance metrics calculated from current scene components and shared assets; no bake or build was run.", report, maxItems);
        }
    }
}
