using System;
using System.Collections.Generic;
using System.Linq;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace Yukino.VRChatReadonlyMcp.Editor
{
    [McpForUnityTool("vrchat_ro_materials", Description = "Read-only shared material, shader, property, texture, keyword, and usage inspection. Never instantiates renderer materials.", AutoRegister = true, Group = "core")]
    public static class VrchatRoMaterials
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar or subtree target.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Optional case-insensitive material or shader filter.", Required = false)] public string query { get; set; }
            [ToolParameter("Maximum material/property rows returned (1-1000).", Required = false, DefaultValue = "250")] public int max_items { get; set; }
            [ToolParameter("Reserved hierarchy depth bound (0-12).", Required = false, DefaultValue = "4")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 250, 1, 1000);
            string query = RoParams.String(parameters, "query");
            Dictionary<Material, List<string>> usage = new Dictionary<Material, List<string>>();
            foreach (Renderer renderer in resolved.GameObject.GetComponentsInChildren<Renderer>(true))
            {
                foreach (Material material in renderer.sharedMaterials ?? new Material[0])
                {
                    if (material == null) continue;
                    List<string> paths;
                    if (!usage.TryGetValue(material, out paths))
                    {
                        paths = new List<string>();
                        usage.Add(material, paths);
                    }
                    paths.Add(VrchatRoCommon.HierarchyPath(renderer.gameObject, true));
                }
            }
            JArray rows = new JArray();
            int emittedProperties = 0;
            int matchingMaterials = 0;
            foreach (KeyValuePair<Material, List<string>> item in usage.OrderBy(x => AssetDatabase.GetAssetPath(x.Key)).ThenBy(x => x.Key.name))
            {
                Material material = item.Key;
                string shaderName = material.shader != null ? material.shader.name : "";
                if (!string.IsNullOrEmpty(query) && material.name.IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0 && shaderName.IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0) continue;
                matchingMaterials++;
                if (rows.Count >= maxItems) continue;
                JArray properties = new JArray();
                if (material.shader != null)
                {
                    int propertyCount = ShaderUtil.GetPropertyCount(material.shader);
                    for (int i = 0; i < propertyCount && emittedProperties < maxItems; i++)
                    {
                        string name = ShaderUtil.GetPropertyName(material.shader, i);
                        ShaderUtil.ShaderPropertyType type = ShaderUtil.GetPropertyType(material.shader, i);
                        JToken value = MaterialValue(material, name, type);
                        properties.Add(new JObject
                        {
                            ["name"] = name,
                            ["description"] = ShaderUtil.GetPropertyDescription(material.shader, i),
                            ["type"] = type.ToString(),
                            ["value"] = value
                        });
                        emittedProperties++;
                    }
                }
                rows.Add(new JObject
                {
                    ["name"] = material.name,
                    ["asset_path"] = AssetDatabase.GetAssetPath(material) ?? "",
                    ["shader"] = shaderName,
                    ["render_queue"] = material.renderQueue,
                    ["gpu_instancing"] = material.enableInstancing,
                    ["double_sided_gi"] = material.doubleSidedGI,
                    ["keyword_count"] = (material.shaderKeywords ?? new string[0]).Length,
                    ["keywords"] = new JArray((material.shaderKeywords ?? new string[0]).Take(maxItems)),
                    ["used_by"] = new JArray(item.Value.Distinct().Take(Math.Min(maxItems, 50))),
                    ["properties"] = properties
                });
            }
            return ReadOnlyResponse.Ok("Shared materials inspected without creating per-renderer material instances.", new JObject
            {
                ["target"] = VrchatRoCommon.Identity(resolved.GameObject),
                ["matching_material_count"] = matchingMaterials,
                ["returned_material_count"] = rows.Count,
                ["truncated"] = matchingMaterials > rows.Count || emittedProperties >= maxItems,
                ["materials"] = rows,
                ["lilToon"] = usage.Keys.Any(m => m != null && m.shader != null && m.shader.name.IndexOf("lilToon", StringComparison.OrdinalIgnoreCase) >= 0),
                ["max_depth"] = RoParams.Int(parameters, "max_depth", 4, 0, 12)
            }, maxItems);
        }

        private static JToken MaterialValue(Material material, string property, ShaderUtil.ShaderPropertyType type)
        {
            try
            {
                switch (type)
                {
                    case ShaderUtil.ShaderPropertyType.Color: return VrchatRoCommon.ColorJson(material.GetColor(property));
                    case ShaderUtil.ShaderPropertyType.Vector: return VrchatRoCommon.Vector4Json(material.GetVector(property));
                    case ShaderUtil.ShaderPropertyType.Float:
                    case ShaderUtil.ShaderPropertyType.Range: return material.GetFloat(property);
                    case ShaderUtil.ShaderPropertyType.TexEnv:
                        Texture texture = material.GetTexture(property);
                        return new JObject
                        {
                            ["texture"] = VrchatRoCommon.ObjectRef(texture),
                            ["offset"] = VrchatRoCommon.Vector2Json(material.GetTextureOffset(property)),
                            ["scale"] = VrchatRoCommon.Vector2Json(material.GetTextureScale(property))
                        };
                    case ShaderUtil.ShaderPropertyType.Int: return material.GetInt(property);
                    default: return JValue.CreateNull();
                }
            }
            catch (Exception ex)
            {
                return new JObject { ["read_error"] = ex.GetType().Name + ": " + ex.Message };
            }
        }
    }

    [McpForUnityTool("vrchat_ro_animator", Description = "Read-only Animator and AnimatorController graph inspection including parameters, layers, states, transitions, Blend Trees, masks, and Write Defaults.", AutoRegister = true, Group = "core")]
    public static class VrchatRoAnimator
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar or subtree target.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Maximum states/transitions per controller (1-1000).", Required = false, DefaultValue = "300")] public int max_items { get; set; }
            [ToolParameter("Maximum nested state-machine/Blend Tree depth (0-12).", Required = false, DefaultValue = "5")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 300, 1, 1000);
            int maxDepth = RoParams.Int(parameters, "max_depth", 5, 0, 12);
            JArray animators = new JArray();
            foreach (Animator animator in resolved.GameObject.GetComponentsInChildren<Animator>(true).Take(maxItems))
            {
                AnimatorController controller = animator.runtimeAnimatorController as AnimatorController;
                JObject row = new JObject
                {
                    ["path"] = VrchatRoCommon.HierarchyPath(animator.gameObject, true),
                    ["enabled"] = animator.enabled,
                    ["is_human"] = animator.isHuman,
                    ["avatar"] = VrchatRoCommon.ObjectRef(animator.avatar),
                    ["runtime_controller"] = VrchatRoCommon.ObjectRef(animator.runtimeAnimatorController)
                };
                if (controller != null) row["controller_graph"] = Controller(controller, maxItems, maxDepth);
                else if (animator.runtimeAnimatorController != null) row["controller_note"] = "Runtime controller is not a directly inspectable AnimatorController (possibly an override controller).";
                animators.Add(row);
            }
            Component descriptor = VrchatRoCommon.FindDescriptor(resolved.GameObject);
            AnimatorController fx = VrchatRoCommon.FxController(descriptor);
            return ReadOnlyResponse.Ok("Animator graphs inspected without evaluating, previewing, or changing controller state.", new JObject
            {
                ["target"] = VrchatRoCommon.Identity(resolved.GameObject),
                ["animators"] = animators,
                ["fx_controller"] = VrchatRoCommon.ObjectRef(fx),
                ["write_defaults"] = VrchatRoCommon.WriteDefaults(fx, maxItems, maxDepth)
            }, maxItems);
        }

        private static JObject Controller(AnimatorController controller, int maxItems, int maxDepth)
        {
            JArray parameters = new JArray(controller.parameters.Take(maxItems).Select(p => new JObject
            {
                ["name"] = p.name,
                ["type"] = p.type.ToString(),
                ["default_bool"] = p.defaultBool,
                ["default_int"] = p.defaultInt,
                ["default_float"] = p.defaultFloat
            }));
            JArray layers = new JArray();
            int emitted = 0;
            int emittedTransitions = 0;
            int visitedMachineNodes = 0;
            int traversedGraphEntries = 0;
            bool graphTraversalTruncated = controller.layers.Length > maxItems;
            HashSet<AnimatorStateMachine> visitedMachines = new HashSet<AnimatorStateMachine>();
            foreach (AnimatorControllerLayer layer in controller.layers.Take(maxItems))
            {
                JArray states = new JArray();
                AppendStateMachine(layer.stateMachine, states, "", 0, maxDepth, maxItems, visitedMachines, ref visitedMachineNodes, ref traversedGraphEntries, ref emitted, ref emittedTransitions, ref graphTraversalTruncated);
                layers.Add(new JObject
                {
                    ["name"] = layer.name,
                    ["default_weight"] = layer.defaultWeight,
                    ["blending_mode"] = layer.blendingMode.ToString(),
                    ["avatar_mask"] = VrchatRoCommon.ObjectRef(layer.avatarMask),
                    ["state_count_returned"] = states.Count,
                    ["states"] = states
                });
            }
            return new JObject
            {
                ["asset"] = VrchatRoCommon.ObjectRef(controller),
                ["parameters"] = parameters,
                ["layers"] = layers,
                ["state_machine_nodes_visited"] = visitedMachineNodes,
                ["graph_entries_traversed"] = traversedGraphEntries,
                ["analysis_complete"] = !graphTraversalTruncated,
                ["truncated"] = graphTraversalTruncated
            };
        }

        private static void AppendStateMachine(AnimatorStateMachine machine, JArray output, string prefix, int depth, int maxDepth, int maxItems, HashSet<AnimatorStateMachine> visitedMachines, ref int visitedMachineNodes, ref int traversedGraphEntries, ref int emitted, ref int emittedTransitions, ref bool graphTraversalTruncated)
        {
            if (machine == null) return;
            if (depth > maxDepth)
            {
                graphTraversalTruncated = true;
                return;
            }
            if (visitedMachines.Contains(machine)) return;
            if (visitedMachineNodes >= maxItems || emitted >= maxItems)
            {
                graphTraversalTruncated = true;
                return;
            }
            visitedMachines.Add(machine);
            visitedMachineNodes++;
            foreach (ChildAnimatorState child in machine.states)
            {
                if (traversedGraphEntries >= maxItems)
                {
                    graphTraversalTruncated = true;
                    break;
                }
                traversedGraphEntries++;
                if (child.state == null) continue;
                if (emitted >= maxItems)
                {
                    graphTraversalTruncated = true;
                    break;
                }
                AnimatorState state = child.state;
                JArray transitions = new JArray();
                int transitionAllowance = Math.Max(0, maxItems - emittedTransitions);
                if (state.transitions.Length > transitionAllowance) graphTraversalTruncated = true;
                foreach (AnimatorStateTransition transition in state.transitions.Take(transitionAllowance))
                {
                    if (transition.conditions.Length > maxItems) graphTraversalTruncated = true;
                    transitions.Add(new JObject
                    {
                        ["destination"] = transition.destinationState != null ? transition.destinationState.name : transition.destinationStateMachine != null ? transition.destinationStateMachine.name : transition.isExit ? "Exit" : "",
                        ["has_exit_time"] = transition.hasExitTime,
                        ["exit_time"] = transition.exitTime,
                        ["duration"] = transition.duration,
                        ["condition_count"] = transition.conditions.Length,
                        ["conditions"] = new JArray(transition.conditions.Take(maxItems).Select(c => new JObject
                        {
                            ["parameter"] = c.parameter,
                            ["mode"] = c.mode.ToString(),
                            ["threshold"] = c.threshold
                        }))
                    });
                    emittedTransitions++;
                }
                bool directBlendTree = false;
                BlendTree blendTree = state.motion as BlendTree;
                if (blendTree != null)
                {
                    bool blendAnalysisComplete;
                    directBlendTree = VrchatRoCommon.ContainsDirectBlendTree(blendTree, maxDepth, maxItems, out blendAnalysisComplete);
                    if (!blendAnalysisComplete) graphTraversalTruncated = true;
                }
                int behaviourCount = state.behaviours.Count(b => b != null);
                if (behaviourCount > maxItems) graphTraversalTruncated = true;
                output.Add(new JObject
                {
                    ["path"] = prefix + state.name,
                    ["write_defaults"] = state.writeDefaultValues,
                    ["motion"] = VrchatRoCommon.ObjectRef(state.motion),
                    ["motion_type"] = state.motion != null ? state.motion.GetType().Name : "None",
                    ["direct_blend_tree"] = directBlendTree,
                    ["speed"] = state.speed,
                    ["transitions"] = transitions,
                    ["behaviour_count"] = behaviourCount,
                    ["behaviours"] = new JArray(state.behaviours.Where(b => b != null).Take(maxItems).Select(b => b.GetType().FullName))
                });
                emitted++;
            }
            foreach (ChildAnimatorStateMachine child in machine.stateMachines)
            {
                if (traversedGraphEntries >= maxItems)
                {
                    graphTraversalTruncated = true;
                    break;
                }
                traversedGraphEntries++;
                if (child.stateMachine == null) continue;
                AppendStateMachine(child.stateMachine, output, prefix + child.stateMachine.name + "/", depth + 1, maxDepth, maxItems, visitedMachines, ref visitedMachineNodes, ref traversedGraphEntries, ref emitted, ref emittedTransitions, ref graphTraversalTruncated);
            }
        }
    }

    [McpForUnityTool("vrchat_ro_expressions", Description = "Read-only VRChat Expression Parameters, menu tree, parameter usage, undefined references, synced-bit budget, and FX Write Defaults analysis.", AutoRegister = true, Group = "core")]
    public static class VrchatRoExpressions
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar root; optional when exactly one descriptor exists.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Maximum parameters/menu rows (1-1000).", Required = false, DefaultValue = "300")] public int max_items { get; set; }
            [ToolParameter("Maximum submenu recursion depth (0-12).", Required = false, DefaultValue = "8")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters, true);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 300, 1, 1000);
            int maxDepth = RoParams.Int(parameters, "max_depth", 8, 0, 12);
            JObject analysis = VrchatRoCommon.ExpressionAnalysis(resolved.GameObject, maxItems, maxDepth);
            analysis["target"] = VrchatRoCommon.Identity(resolved.GameObject);
            analysis["budget_note"] = "256 synced bits is a documentation snapshot; verify the current official VRChat limit before editing. Unused detection is advisory, not permission to remove a parameter.";
            return ReadOnlyResponse.Ok("Expressions analyzed without editing parameters, menus, or Animator Controllers.", analysis, maxItems);
        }
    }
}
