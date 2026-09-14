using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Yukino.VRChatReadonlyMcp.Editor
{
    [McpForUnityTool("vrchat_ro_project_inventory", Description = "Read-only inventory of loaded scenes, avatar roots, packages, and VRChat authoring integrations.", AutoRegister = true, Group = "core")]
    public static class VrchatRoProjectInventory
    {
        public sealed class Parameters
        {
            [ToolParameter("Maximum rows per section (1-500).", Required = false, DefaultValue = "100")]
            public int max_items { get; set; }
            [ToolParameter("Reserved hierarchy depth bound (0-12).", Required = false, DefaultValue = "4")]
            public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            int maxItems = RoParams.Int(parameters, "max_items", 100, 1, 500);
            List<JObject> sceneRows = new List<JObject>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                Scene scene = SceneManager.GetSceneAt(i);
                if (!scene.IsValid()) continue;
                sceneRows.Add(new JObject
                {
                    ["name"] = scene.name,
                    ["path"] = scene.path,
                    ["loaded"] = scene.isLoaded,
                    ["root_count"] = scene.isLoaded ? scene.rootCount : 0,
                    ["is_active"] = scene == SceneManager.GetActiveScene(),
                    ["is_preview_or_generated"] = scene.name.IndexOf("___NDMF Preview___", StringComparison.OrdinalIgnoreCase) >= 0
                });
            }
            JArray scenes = new JArray(sceneRows.Take(maxItems));
            JArray avatars = new JArray(VrchatRoCommon.FindAvatarRoots().Take(maxItems).Select(root =>
            {
                JObject row = VrchatRoCommon.Identity(root);
                row["descriptor_type"] = VrchatRoCommon.DescriptorType;
                return row;
            }));
            JObject data = new JObject
            {
                ["unity_version"] = Application.unityVersion,
                ["project_directory_name"] = Path.GetFileName(Path.GetDirectoryName(Application.dataPath)),
                ["player_product_name"] = Application.productName,
                ["project_assets_path"] = Application.dataPath,
                ["active_scene"] = SceneManager.GetActiveScene().name,
                ["scene_count"] = SceneManager.sceneCount,
                ["scenes_returned"] = scenes.Count,
                ["scenes_truncated"] = sceneRows.Count > scenes.Count,
                ["scenes"] = scenes,
                ["avatar_roots"] = avatars,
                ["avatar_roots_truncated"] = VrchatRoCommon.FindAvatarRoots().Skip(maxItems).Any(),
                ["packages"] = VrchatRoCommon.PackageRows(maxItems),
                ["integrations"] = VrchatRoCommon.IntegrationFlags(),
                ["max_depth"] = RoParams.Int(parameters, "max_depth", 4, 0, 12)
            };
            return ReadOnlyResponse.Ok("Project inventory collected without changing editor or project state.", data, maxItems);
        }
    }

    [McpForUnityTool("vrchat_ro_avatar_inspect", Description = "Read-only VRChat avatar root, descriptor, humanoid bone, component, and body/face candidate inspection.", AutoRegister = true, Group = "core")]
    public static class VrchatRoAvatarInspect
    {
        public sealed class Parameters
        {
            [ToolParameter("Unique object name or exact hierarchy path; optional when exactly one avatar root exists.", Required = false)]
            public string target { get; set; }
            [ToolParameter("Exact Scene/Root/Child or Root/Child path.", Required = false)]
            public string hierarchy_path { get; set; }
            [ToolParameter("Exact Unity GameObject instance ID.", Required = false)]
            public int instance_id { get; set; }
            [ToolParameter("Maximum components/bones/properties returned (1-500).", Required = false, DefaultValue = "150")]
            public int max_items { get; set; }
            [ToolParameter("Maximum serialized inspection depth (0-8).", Required = false, DefaultValue = "2")]
            public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters, true);
            if (resolved.Error != null) return resolved.Error;
            GameObject root = resolved.GameObject;
            int maxItems = RoParams.Int(parameters, "max_items", 150, 1, 500);
            int maxDepth = RoParams.Int(parameters, "max_depth", 2, 0, 8);
            Component descriptor = VrchatRoCommon.FindDescriptor(root);
            Animator animator = root.GetComponent<Animator>();
            JArray bones = new JArray();
            if (animator != null && animator.isHuman)
            {
                foreach (HumanBodyBones bone in Enum.GetValues(typeof(HumanBodyBones)))
                {
                    if (bone == HumanBodyBones.LastBone || bones.Count >= maxItems) continue;
                    Transform transform = animator.GetBoneTransform(bone);
                    bones.Add(new JObject
                    {
                        ["human_bone"] = bone.ToString(),
                        ["assigned"] = transform != null,
                        ["hierarchy_path"] = transform != null ? VrchatRoCommon.HierarchyPath(transform.gameObject, true) : ""
                    });
                }
            }
            int missingScripts = root.GetComponentsInChildren<Component>(true).Count(component => component == null);
            JObject data = new JObject
            {
                ["target"] = VrchatRoCommon.Identity(root),
                ["descriptor_found"] = descriptor != null,
                ["descriptor"] = descriptor != null ? new JObject
                {
                    ["type"] = VrchatRoCommon.FullName(descriptor),
                    ["instance_id"] = descriptor.GetInstanceID(),
                    ["properties"] = VrchatRoCommon.ShallowSerialized(descriptor, maxItems, maxDepth)
                } : null,
                ["animator"] = animator != null ? new JObject
                {
                    ["enabled"] = animator.enabled,
                    ["is_human"] = animator.isHuman,
                    ["avatar"] = VrchatRoCommon.ObjectRef(animator.avatar),
                    ["runtime_controller"] = VrchatRoCommon.ObjectRef(animator.runtimeAnimatorController),
                    ["apply_root_motion"] = animator.applyRootMotion
                } : null,
                ["humanoid_bones"] = bones,
                ["components_on_root"] = VrchatRoCommon.Components(root, maxItems),
                ["descendant_component_count"] = root.GetComponentsInChildren<Component>(true).Length,
                ["missing_script_count"] = missingScripts,
                ["anatomy"] = VrchatRoCommon.Anatomy(root, maxItems),
                ["integrations"] = VrchatRoCommon.IntegrationFlags(root),
                ["max_depth"] = maxDepth
            };
            return ReadOnlyResponse.Ok("Avatar inspected read-only; body/face results are evidence-based heuristics.", data, maxItems);
        }
    }

    [McpForUnityTool("vrchat_ro_renderer_mesh", Description = "Read-only renderer and mesh inventory with paths, shared material slots, bounds, bones, BlendShapes, and triangle counts.", AutoRegister = true, Group = "core")]
    public static class VrchatRoRendererMesh
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar or subtree target.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Maximum renderers returned (1-500).", Required = false, DefaultValue = "150")] public int max_items { get; set; }
            [ToolParameter("Reserved hierarchy depth bound (0-12).", Required = false, DefaultValue = "6")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 150, 1, 500);
            Renderer[] renderers = resolved.GameObject.GetComponentsInChildren<Renderer>(true);
            JArray rows = new JArray();
            foreach (Renderer renderer in renderers.Take(maxItems)) rows.Add(RendererRow(renderer, maxItems));
            JObject data = new JObject
            {
                ["target"] = VrchatRoCommon.Identity(resolved.GameObject),
                ["renderer_count"] = renderers.Length,
                ["truncated"] = renderers.Length > maxItems,
                ["renderers"] = rows,
                ["anatomy"] = VrchatRoCommon.Anatomy(resolved.GameObject, maxItems),
                ["max_depth"] = RoParams.Int(parameters, "max_depth", 6, 0, 12)
            };
            return ReadOnlyResponse.Ok("Renderer and mesh inventory collected from shared assets only.", data, maxItems);
        }

        private static JObject RendererRow(Renderer renderer, int maxItems)
        {
            Mesh mesh = null;
            SkinnedMeshRenderer smr = renderer as SkinnedMeshRenderer;
            MeshFilter filter = renderer.GetComponent<MeshFilter>();
            if (smr != null) mesh = smr.sharedMesh;
            else if (filter != null) mesh = filter.sharedMesh;
            Material[] shared = renderer.sharedMaterials ?? new Material[0];
            JObject row = new JObject
            {
                ["path"] = VrchatRoCommon.HierarchyPath(renderer.gameObject, true),
                ["renderer_type"] = renderer.GetType().FullName,
                ["enabled"] = renderer.enabled,
                ["active_in_hierarchy"] = renderer.gameObject.activeInHierarchy,
                ["bounds"] = VrchatRoCommon.BoundsJson(renderer.bounds),
                ["material_slot_count"] = shared.Length,
                ["material_slots_truncated"] = shared.Length > maxItems,
                ["material_slots"] = new JArray(shared.Take(maxItems).Select((material, index) => new JObject
                {
                    ["slot"] = index,
                    ["material"] = VrchatRoCommon.ObjectRef(material),
                    ["shader"] = material != null && material.shader != null ? material.shader.name : ""
                })),
                ["mesh"] = mesh != null ? new JObject
                {
                    ["name"] = mesh.name,
                    ["asset_path"] = AssetDatabase.GetAssetPath(mesh) ?? "",
                    ["vertex_count"] = mesh.vertexCount,
                    ["triangle_count"] = VrchatRoCommon.TriangleCount(mesh),
                    ["submesh_count"] = mesh.subMeshCount,
                    ["blendshape_count"] = mesh.blendShapeCount,
                    ["bounds"] = VrchatRoCommon.BoundsJson(mesh.bounds),
                    ["is_readable"] = mesh.isReadable
                } : null
            };
            if (smr != null)
            {
                row["root_bone"] = smr.rootBone != null ? VrchatRoCommon.HierarchyPath(smr.rootBone.gameObject, true) : "";
                row["bone_count"] = smr.bones != null ? smr.bones.Length : 0;
                row["quality"] = smr.quality.ToString();
                row["update_when_offscreen"] = smr.updateWhenOffscreen;
            }
            return row;
        }
    }

    [McpForUnityTool("vrchat_ro_blendshapes", Description = "Read-only BlendShape inventory and current weights across all SkinnedMeshRenderers, with face/body candidate evidence.", AutoRegister = true, Group = "core")]
    public static class VrchatRoBlendshapes
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar or subtree target.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Optional case-insensitive BlendShape name filter.", Required = false)] public string query { get; set; }
            [ToolParameter("Maximum BlendShape rows returned (1-2000).", Required = false, DefaultValue = "500")] public int max_items { get; set; }
            [ToolParameter("Reserved hierarchy depth bound (0-12).", Required = false, DefaultValue = "6")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 500, 1, 2000);
            string query = RoParams.String(parameters, "query");
            JArray renderers = new JArray();
            int totalShapes = 0;
            int emitted = 0;
            foreach (SkinnedMeshRenderer smr in resolved.GameObject.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                Mesh mesh = smr.sharedMesh;
                if (mesh == null || mesh.blendShapeCount == 0) continue;
                JArray shapes = new JArray();
                for (int i = 0; i < mesh.blendShapeCount; i++)
                {
                    string name = mesh.GetBlendShapeName(i) ?? "";
                    if (!string.IsNullOrEmpty(query) && name.IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0) continue;
                    totalShapes++;
                    if (emitted >= maxItems) continue;
                    shapes.Add(new JObject
                    {
                        ["index"] = i,
                        ["name"] = name,
                        ["weight"] = smr.GetBlendShapeWeight(i),
                        ["frame_count"] = mesh.GetBlendShapeFrameCount(i),
                        ["looks_like_viseme"] = name.StartsWith("vrc.v_", StringComparison.OrdinalIgnoreCase) || name.StartsWith("Viseme_", StringComparison.OrdinalIgnoreCase) || name.StartsWith("Fcl_", StringComparison.OrdinalIgnoreCase)
                    });
                    emitted++;
                }
                if (shapes.Count > 0)
                {
                    renderers.Add(new JObject
                    {
                        ["path"] = VrchatRoCommon.HierarchyPath(smr.gameObject, true),
                        ["mesh"] = VrchatRoCommon.ObjectRef(mesh),
                        ["blendshape_count_on_mesh"] = mesh.blendShapeCount,
                        ["returned"] = shapes.Count,
                        ["shapes"] = shapes
                    });
                }
            }
            JObject data = new JObject
            {
                ["target"] = VrchatRoCommon.Identity(resolved.GameObject),
                ["query"] = query,
                ["matched_blendshape_count"] = totalShapes,
                ["returned_blendshape_count"] = emitted,
                ["truncated"] = totalShapes > emitted,
                ["renderers"] = renderers,
                ["anatomy"] = VrchatRoCommon.Anatomy(resolved.GameObject, maxItems),
                ["weight_domain_note"] = "Unity BlendShape weights are normally 0..100; do not confuse them with VRChat expression float parameters (-1..1).",
                ["max_depth"] = RoParams.Int(parameters, "max_depth", 6, 0, 12)
            };
            return ReadOnlyResponse.Ok("BlendShapes and current weights inspected without previewing or changing values.", data, maxItems);
        }
    }
}
