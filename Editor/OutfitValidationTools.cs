using System;
using System.Collections.Generic;
using System.Linq;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Yukino.VRChatReadonlyMcp.Editor
{
    [McpForUnityTool("vrchat_ro_outfit_compatibility", Description = "Read-only heuristic comparison of outfit and avatar bones, armature scale, bounds, renderers, and mapping confidence. Does not fit, retarget, bake, or change weights.", AutoRegister = true, Group = "core")]
    public static class VrchatRoOutfitCompatibility
    {
        public sealed class Parameters
        {
            [ToolParameter("Unique avatar root name or exact path.", Required = false)] public string avatar_target { get; set; }
            [ToolParameter("Exact avatar hierarchy path.", Required = false)] public string avatar_hierarchy_path { get; set; }
            [ToolParameter("Unique outfit root name or exact path.", Required = false)] public string outfit_target { get; set; }
            [ToolParameter("Exact outfit hierarchy path.", Required = false)] public string outfit_hierarchy_path { get; set; }
            [ToolParameter("Maximum bone mapping rows returned (1-1000).", Required = false, DefaultValue = "300")] public int max_items { get; set; }
            [ToolParameter("Reserved hierarchy depth bound (0-12).", Required = false, DefaultValue = "8")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution avatarResolution = ResolveSide(parameters, "avatar_target", "avatar_hierarchy_path");
            if (avatarResolution.Error != null) return avatarResolution.Error;
            TargetResolution outfitResolution = ResolveSide(parameters, "outfit_target", "outfit_hierarchy_path");
            if (outfitResolution.Error != null) return outfitResolution.Error;
            GameObject avatar = avatarResolution.GameObject;
            GameObject outfit = outfitResolution.GameObject;
            if (ReferenceEquals(avatar, outfit))
                return ReadOnlyResponse.Error("identical_targets", "Avatar and outfit targets must be different scene objects.");
            if (avatar.transform.IsChildOf(outfit.transform))
                return ReadOnlyResponse.Error("invalid_target_overlap", "The outfit target cannot contain the avatar target.");
            bool nestedOutfit = outfit.transform.IsChildOf(avatar.transform);
            int maxItems = RoParams.Int(parameters, "max_items", 300, 1, 1000);

            List<Transform> avatarBones = CollectReferencedBones(avatar, nestedOutfit ? outfit.transform : null);
            List<Transform> outfitBones = CollectReferencedBones(outfit, null);
            if (outfitBones.Count == 0) outfitBones = VrchatRoCommon.Traverse(outfit).Select(go => go.transform).ToList();
            Dictionary<string, List<Transform>> exactAvatar = avatarBones.GroupBy(b => b.name).ToDictionary(g => g.Key, g => g.ToList(), StringComparer.Ordinal);
            Dictionary<string, List<Transform>> caseAvatar = avatarBones.GroupBy(b => b.name, StringComparer.OrdinalIgnoreCase).ToDictionary(g => g.Key, g => g.ToList(), StringComparer.OrdinalIgnoreCase);
            Dictionary<string, List<Transform>> normalizedAvatar = avatarBones.GroupBy(b => VrchatRoCommon.NormalizeBoneName(b.name)).Where(g => !string.IsNullOrEmpty(g.Key)).ToDictionary(g => g.Key, g => g.ToList(), StringComparer.Ordinal);

            int exact = 0;
            int caseInsensitive = 0;
            int normalized = 0;
            int ambiguous = 0;
            int unmatched = 0;
            int sharedBoneReferences = 0;
            JArray mappings = new JArray();
            foreach (Transform bone in outfitBones)
            {
                string method = "unmatched";
                double confidence = 0d;
                List<Transform> rawCandidates = null;
                List<Transform> candidates = null;
                if (exactAvatar.TryGetValue(bone.name, out rawCandidates))
                {
                    method = "exact";
                    confidence = 1d;
                }
                else if (caseAvatar.TryGetValue(bone.name, out rawCandidates))
                {
                    method = "case_insensitive";
                    confidence = 0.9d;
                }
                else
                {
                    string key = VrchatRoCommon.NormalizeBoneName(bone.name);
                    if (!string.IsNullOrEmpty(key) && normalizedAvatar.TryGetValue(key, out rawCandidates))
                    {
                        method = "normalized_name";
                        confidence = 0.65d;
                    }
                }

                if (rawCandidates == null)
                {
                    unmatched++;
                }
                else
                {
                    bool sharedReference = rawCandidates.Any(candidate => ReferenceEquals(candidate, bone));
                    if (sharedReference) sharedBoneReferences++;
                    candidates = rawCandidates
                        .Where(candidate => candidate != bone && !ReferenceEquals(candidate, bone))
                        .ToList();
                    if (candidates.Count == 0)
                    {
                        method = sharedReference ? "shared_reference_excluded" : "unmatched";
                        confidence = 0d;
                        unmatched++;
                    }
                    else if (candidates.Count > 1)
                    {
                        method += "_ambiguous";
                        confidence = Math.Min(confidence, 0.4d);
                        ambiguous++;
                    }
                    else if (candidates.Count == 1)
                    {
                        if (method == "exact") exact++;
                        else if (method == "case_insensitive") caseInsensitive++;
                        else if (method == "normalized_name") normalized++;
                    }
                }
                if (mappings.Count < maxItems)
                {
                    mappings.Add(new JObject
                    {
                        ["outfit_bone"] = VrchatRoCommon.HierarchyPath(bone.gameObject, true),
                        ["method"] = method,
                        ["confidence"] = confidence,
                        ["avatar_candidates"] = new JArray((candidates ?? new List<Transform>()).Take(10).Select(candidate => VrchatRoCommon.HierarchyPath(candidate.gameObject, true)))
                    });
                }
            }
            int matched = exact + caseInsensitive + normalized;
            double compatibility = outfitBones.Count > 0 ? matched * 100d / outfitBones.Count : 0d;
            Bounds avatarBounds;
            Bounds outfitBounds;
            bool avatarHasBounds = CombinedBounds(avatar, nestedOutfit ? outfit.transform : null, out avatarBounds);
            bool outfitHasBounds = CombinedBounds(outfit, null, out outfitBounds);
            double heightRatio = avatarHasBounds && outfitHasBounds && avatarBounds.size.y > 0.0001f ? outfitBounds.size.y / avatarBounds.size.y : 0d;

            JArray concerns = new JArray();
            if (VrchatRoCommon.IsPreviewOrGenerated(outfit)) concerns.Add("Outfit target appears to be preview/generated output rather than an authoring source.");
            if (compatibility < 50d) concerns.Add("Low name-based bone compatibility; manual mapping and likely external fitting work are required.");
            else if (compatibility < 80d) concerns.Add("Moderate name-based compatibility; inspect every ambiguous and unmatched bone.");
            if (heightRatio > 0d && (heightRatio < 0.8d || heightRatio > 1.2d)) concerns.Add("Renderer-bounds height differs by more than 20%; this is only a scale clue, not an automatic scale instruction.");
            if (ambiguous > 0) concerns.Add("Some bone names map to multiple avatar candidates; no automatic choice is safe.");
            if (sharedBoneReferences > 0) concerns.Add("Some outfit bones already reference transforms in the avatar armature; those self-mappings were excluded from compatibility scoring.");

            return ReadOnlyResponse.Ok("Outfit compatibility estimated without retargeting, baking meshes, modifying transforms, or changing weights.", new JObject
            {
                ["avatar"] = VrchatRoCommon.Identity(avatar),
                ["outfit"] = VrchatRoCommon.Identity(outfit),
                ["avatar_bone_count"] = avatarBones.Count,
                ["outfit_bone_count"] = outfitBones.Count,
                ["exact_matches"] = exact,
                ["case_insensitive_matches"] = caseInsensitive,
                ["normalized_name_matches"] = normalized,
                ["ambiguous_matches"] = ambiguous,
                ["shared_bone_references"] = sharedBoneReferences,
                ["unmatched"] = unmatched,
                ["compatibility_percent_heuristic"] = Math.Round(compatibility, 1),
                ["avatar_bounds"] = avatarHasBounds ? VrchatRoCommon.BoundsJson(avatarBounds) : null,
                ["outfit_bounds"] = outfitHasBounds ? VrchatRoCommon.BoundsJson(outfitBounds) : null,
                ["renderer_bounds_height_ratio"] = Math.Round(heightRatio, 4),
                ["mappings"] = mappings,
                ["truncated"] = outfitBones.Count > mappings.Count,
                ["concerns"] = concerns,
                ["decision_note"] = "Name and bounds analysis cannot prove skinning compatibility, bind-pose compatibility, clipping, or visual fit."
            }, maxItems);
        }

        private static TargetResolution ResolveSide(JObject source, string targetName, string pathName)
        {
            JObject translated = new JObject
            {
                ["target"] = RoParams.String(source, targetName),
                ["hierarchy_path"] = RoParams.String(source, pathName)
            };
            return VrchatRoCommon.ResolveTarget(translated);
        }

        private static List<Transform> CollectReferencedBones(GameObject root, Transform excludedSubtree)
        {
            HashSet<Transform> bones = new HashSet<Transform>();
            foreach (SkinnedMeshRenderer smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (IsInSubtree(smr.transform, excludedSubtree)) continue;
                foreach (Transform bone in smr.bones ?? new Transform[0])
                    if (bone != null && !IsInSubtree(bone, excludedSubtree)) bones.Add(bone);
                if (smr.rootBone != null && !IsInSubtree(smr.rootBone, excludedSubtree)) bones.Add(smr.rootBone);
            }
            Animator animator = root.GetComponent<Animator>();
            if (animator != null && animator.isHuman)
            {
                foreach (HumanBodyBones humanBone in Enum.GetValues(typeof(HumanBodyBones)))
                {
                    if (humanBone == HumanBodyBones.LastBone) continue;
                    Transform bone = animator.GetBoneTransform(humanBone);
                    if (bone != null && !IsInSubtree(bone, excludedSubtree)) bones.Add(bone);
                }
            }
            return bones.OrderBy(b => VrchatRoCommon.HierarchyPath(b.gameObject, true)).ToList();
        }

        private static bool IsInSubtree(Transform candidate, Transform subtree)
        {
            return candidate != null && subtree != null && (candidate == subtree || candidate.IsChildOf(subtree));
        }

        private static bool CombinedBounds(GameObject root, Transform excludedSubtree, out Bounds result)
        {
            result = new Bounds(root.transform.position, Vector3.zero);
            bool found = false;
            foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                if (IsInSubtree(renderer.transform, excludedSubtree)) continue;
                if (!found) { result = renderer.bounds; found = true; }
                else result.Encapsulate(renderer.bounds);
            }
            return found;
        }
    }

    [McpForUnityTool("vrchat_ro_validate", Description = "Read-only consolidated VRChat avatar validation covering target identity, descriptor, humanoid rig, missing scripts, parameters, menus, Write Defaults, packages, performance, and generated-source risks.", AutoRegister = true, Group = "core")]
    public static class VrchatRoValidate
    {
        public sealed class Parameters
        {
            [ToolParameter("Avatar root; optional when exactly one descriptor exists.", Required = false)] public string target { get; set; }
            [ToolParameter("Exact hierarchy path.", Required = false)] public string hierarchy_path { get; set; }
            [ToolParameter("Exact instance ID.", Required = false)] public int instance_id { get; set; }
            [ToolParameter("Maximum diagnostic rows (1-1000).", Required = false, DefaultValue = "400")] public int max_items { get; set; }
            [ToolParameter("Maximum menu/property recursion depth (0-12).", Required = false, DefaultValue = "8")] public int max_depth { get; set; }
        }

        public static object HandleCommand(JObject parameters)
        {
            JObject gate = VrchatRoCommon.EditorGate();
            if (gate != null) return gate;
            TargetResolution resolved = VrchatRoCommon.ResolveTarget(parameters, true);
            if (resolved.Error != null) return resolved.Error;
            int maxItems = RoParams.Int(parameters, "max_items", 400, 1, 1000);
            int maxDepth = RoParams.Int(parameters, "max_depth", 8, 0, 12);
            GameObject root = resolved.GameObject;
            JArray errors = new JArray();
            JArray warnings = new JArray();
            JArray information = new JArray();

            Component descriptor = VrchatRoCommon.FindDescriptor(root);
            if (descriptor == null) errors.Add("VRCAvatarDescriptor is missing under the target root.");
            else information.Add("VRCAvatarDescriptor found at " + VrchatRoCommon.HierarchyPath(descriptor.gameObject, true) + ".");

            Animator animator = root.GetComponent<Animator>();
            if (animator == null) errors.Add("Animator is missing on the target root.");
            else if (!animator.isHuman) warnings.Add("Animator is not humanoid; verify that a generic avatar is intentional.");
            else information.Add("Humanoid Animator detected.");

            int missingScripts = root.GetComponentsInChildren<Component>(true).Count(c => c == null);
            if (missingScripts > 0) errors.Add(missingScripts + " missing script component slot(s) detected.");

            if (VrchatRoCommon.IsPreviewOrGenerated(root)) errors.Add("Target appears to be an NDMF/generated preview rather than an authoring source.");

            JObject expressions = VrchatRoCommon.ExpressionAnalysis(root, maxItems, maxDepth);
            int syncedBits = expressions["synced_bits"] != null ? (int)expressions["synced_bits"] : 0;
            if (syncedBits > 256) errors.Add("Synchronized Expression Parameter budget exceeds the 256-bit documentation snapshot.");
            else if (syncedBits > 230) warnings.Add("Synchronized Expression Parameter budget is above 90% of the 256-bit documentation snapshot.");
            bool expressionAnalysisComplete = expressions["analysis_complete"] != null && (bool)expressions["analysis_complete"];
            if (!expressionAnalysisComplete)
            {
                warnings.Add("expression_analysis_incomplete");
                information.Add("Menu usage traversal was incomplete, so undefined/unused parameter conclusions are withheld.");
            }
            else
            {
                JArray undefined = expressions["undefined_menu_parameters"] as JArray;
                if (undefined != null && undefined.Count > 0) errors.Add(undefined.Count + " menu parameter reference(s) are undefined.");
                JArray unused = expressions["unused_parameters"] as JArray;
                if (unused != null && unused.Count > 0) information.Add(unused.Count + " parameter(s) appear unused by current menu/FX inspection; this is advisory only.");
            }
            JObject wd = expressions["write_defaults"] as JObject;
            if (wd != null && wd["mixed"] != null && (bool)wd["mixed"])
                warnings.Add("FX controller contains mixed Write Defaults. Review Direct Blend Tree/additive exceptions before changing anything.");

            JObject performance = VrchatRoCommon.Performance(root);
            bool performanceAnalysisComplete = performance["analysis_complete"] != null && (bool)performance["analysis_complete"];
            if (!performanceAnalysisComplete)
            {
                warnings.Add("performance_analysis_incomplete");
                information.Add("Exact SDK parity is unavailable for one or more performance categories; no formal clean rank is claimed.");
            }
            JObject metrics = performance["metrics"] as JObject;
            if (metrics != null)
            {
                if ((int)metrics["unreadable_meshes"] > 0) errors.Add("mesh_read_write_disabled");
                if ((long)metrics["triangles"] > 70000) warnings.Add("Triangle count exceeds the current PC Poor threshold snapshot (70,000).");
                if ((int)metrics["lights"] > 0) warnings.Add("Avatar contains Light components; VRChat recommends avoiding avatar lights.");
                if ((int)metrics["unity_constraints"] > 0) warnings.Add("Unity constraint components are present; review migration to VRChat constraints.");
            }

            JObject integrations = VrchatRoCommon.IntegrationFlags(root);
            if (integrations["VRChat SDK"] != null && !(bool)integrations["VRChat SDK"])
                errors.Add("VRChat SDK was not detected from project packages or avatar components.");

            JObject summary = new JObject
            {
                ["error_count"] = errors.Count,
                ["warning_count"] = warnings.Count,
                ["info_count"] = information.Count,
                ["status"] = errors.Count > 0 ? "errors" : warnings.Count > 0 ? "warnings" : "no_static_issues_detected"
            };
            return ReadOnlyResponse.Ok("Static validation completed; no SDK build, NDMF bake, Play Mode, or upload was run.", new JObject
            {
                ["target"] = VrchatRoCommon.Identity(root),
                ["summary"] = summary,
                ["errors"] = errors,
                ["warnings"] = warnings,
                ["information"] = information,
                ["anatomy"] = VrchatRoCommon.Anatomy(root, maxItems),
                ["expressions"] = expressions,
                ["performance"] = performance,
                ["integrations"] = integrations,
                ["validation_scope"] = "Static read-only helper. It does not replace VRChat SDK validation, NDMF build validation, Build & Test, or visual review."
            }, maxItems);
        }
    }
}
