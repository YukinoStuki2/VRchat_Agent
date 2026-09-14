using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.PackageManager;
using UnityEngine;
using UnityEngine.Profiling;
using UnityEngine.SceneManagement;

namespace Yukino.VRChatReadonlyMcp.Editor
{
    internal sealed class OutputBudget
    {
        internal const int MaxStringLength = 512;
        private int remaining;
        private int emitted;
        private int omittedAtLeast;

        internal OutputBudget(int maxItems)
        {
            remaining = Mathf.Clamp(maxItems, 1, 2000);
        }

        internal bool Truncated { get; private set; }

        internal JToken LimitToken(JToken token)
        {
            if (token == null) token = JValue.CreateNull();
            if (remaining <= 0)
            {
                Truncated = true;
                omittedAtLeast++;
                return null;
            }
            remaining--;
            emitted++;
            if (token.Type == JTokenType.Null) return JValue.CreateNull();
            JObject sourceObject = token as JObject;
            if (sourceObject != null)
            {
                JObject limitedObject = new JObject();
                foreach (JProperty property in sourceObject.Properties())
                {
                    JToken child = LimitToken(property.Value);
                    if (child == null) break;
                    limitedObject[property.Name] = child;
                }
                return limitedObject;
            }
            JArray sourceArray = token as JArray;
            if (sourceArray != null)
            {
                JArray limitedArray = new JArray();
                foreach (JToken item in sourceArray)
                {
                    JToken child = LimitToken(item);
                    if (child == null) break;
                    limitedArray.Add(child);
                }
                return limitedArray;
            }
            if (token.Type == JTokenType.String)
            {
                string value = token.ToString();
                if (value.Length > MaxStringLength)
                {
                    Truncated = true;
                    omittedAtLeast += value.Length - MaxStringLength;
                    value = value.Substring(0, MaxStringLength - 1) + "…";
                }
                return new JValue(value);
            }
            return token.DeepClone();
        }

        internal JObject Metadata(int requestedItems)
        {
            return new JObject
            {
                ["requested_node_limit"] = requestedItems,
                ["emitted_nodes"] = emitted,
                ["max_string_length"] = MaxStringLength,
                ["truncated"] = Truncated,
                ["omitted_nodes_or_characters_at_least"] = omittedAtLeast
            };
        }

        internal static string LimitString(string value)
        {
            string safe = value ?? "";
            return safe.Length <= MaxStringLength ? safe : safe.Substring(0, MaxStringLength - 1) + "…";
        }
    }

    internal static class ReadOnlyResponse
    {
        public static object Ok(string message, JToken data, int maxItems)
        {
            int limit = Mathf.Clamp(maxItems, 1, 2000);
            OutputBudget budget = new OutputBudget(limit);
            JToken limitedData = budget.LimitToken(data) ?? new JObject();
            JObject bridgeData = limitedData as JObject ?? new JObject { ["result"] = limitedData };
            bridgeData["read_only"] = true;
            bridgeData["mutated"] = false;
            bridgeData["response_budget"] = budget.Metadata(limit);
            return new JObject
            {
                ["success"] = true,
                ["message"] = OutputBudget.LimitString(message ?? "Read-only query completed."),
                ["read_only"] = true,
                ["mutated"] = false,
                ["data"] = bridgeData,
                ["response_budget"] = budget.Metadata(limit)
            };
        }

        public static object Error(string code, string message, JToken data = null)
        {
            const int errorLimit = 100;
            OutputBudget budget = new OutputBudget(errorLimit);
            JToken limitedData = budget.LimitToken(data ?? JValue.CreateNull()) ?? JValue.CreateNull();
            return new JObject
            {
                ["success"] = false,
                ["error"] = new JObject
                {
                    ["code"] = OutputBudget.LimitString(code ?? "query_failed"),
                    ["message"] = OutputBudget.LimitString(message ?? "Read-only query failed.")
                },
                ["read_only"] = true,
                ["mutated"] = false,
                ["data"] = limitedData,
                ["response_budget"] = budget.Metadata(errorLimit)
            };
        }
    }

    internal static class RoParams
    {
        public static string String(JObject p, string name, string fallback = "")
        {
            if (p == null || p[name] == null || p[name].Type == JTokenType.Null) return OutputBudget.LimitString(fallback);
            return OutputBudget.LimitString(p[name].ToString().Trim());
        }

        public static int Int(JObject p, string name, int fallback, int min, int max)
        {
            int value;
            if (p == null || p[name] == null || !int.TryParse(p[name].ToString(), out value)) value = fallback;
            return Mathf.Clamp(value, min, max);
        }

        public static bool Bool(JObject p, string name, bool fallback)
        {
            bool value;
            if (p == null || p[name] == null || !bool.TryParse(p[name].ToString(), out value)) return fallback;
            return value;
        }
    }

    internal sealed class TargetResolution
    {
        public GameObject GameObject;
        public JObject Error;
    }

    internal static class VrchatRoCommon
    {
        internal const int AmbiguousCandidateLimit = 20;
        internal const string DescriptorType = "VRC.SDK3.Avatars.Components.VRCAvatarDescriptor";
        internal const string PhysBoneType = "VRC.SDK3.Dynamics.PhysBone.Components.VRCPhysBone";
        internal const string PhysBoneColliderType = "VRC.SDK3.Dynamics.PhysBone.Components.VRCPhysBoneCollider";
        internal const string ContactSenderType = "VRC.SDK3.Dynamics.Contact.Components.VRCContactSender";
        internal const string ContactReceiverType = "VRC.SDK3.Dynamics.Contact.Components.VRCContactReceiver";

        internal static JObject EditorGate()
        {
            if (EditorApplication.isCompiling)
                return (JObject)ReadOnlyResponse.Error("editor_compiling", "Unity is compiling; retry after the domain reload completes.");
            if (EditorApplication.isUpdating)
                return (JObject)ReadOnlyResponse.Error("editor_updating", "Unity is updating assets; retry when the editor is ready.");
            return null;
        }

        internal static IEnumerable<GameObject> AllSceneObjects()
        {
            for (int s = 0; s < SceneManager.sceneCount; s++)
            {
                Scene scene = SceneManager.GetSceneAt(s);
                if (!scene.IsValid() || !scene.isLoaded) continue;
                foreach (GameObject root in scene.GetRootGameObjects())
                {
                    foreach (GameObject item in Traverse(root)) yield return item;
                }
            }
        }

        internal static IEnumerable<GameObject> Traverse(GameObject root)
        {
            if (root == null) yield break;
            Stack<Transform> stack = new Stack<Transform>();
            stack.Push(root.transform);
            while (stack.Count > 0)
            {
                Transform current = stack.Pop();
                if (current == null) continue;
                yield return current.gameObject;
                for (int i = current.childCount - 1; i >= 0; i--) stack.Push(current.GetChild(i));
            }
        }

        internal static string HierarchyPath(GameObject go, bool includeScene = false)
        {
            if (go == null) return "";
            Stack<string> names = new Stack<string>();
            Transform current = go.transform;
            while (current != null)
            {
                names.Push(current.name);
                current = current.parent;
            }
            string path = string.Join("/", names.ToArray());
            if (includeScene && go.scene.IsValid()) return go.scene.name + "/" + path;
            return path;
        }

        internal static TargetResolution ResolveTarget(JObject p, bool descriptorPreferred = false)
        {
            int instanceId = RoParams.Int(p, "instance_id", 0, int.MinValue, int.MaxValue);
            string hierarchyPath = RoParams.String(p, "hierarchy_path");
            string target = RoParams.String(p, "target");

            if (instanceId != 0)
            {
                GameObject byId = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
                if (byId != null && byId.scene.IsValid()) return new TargetResolution { GameObject = byId };
                return FailResolution("target_not_found", "No scene GameObject has the requested instance_id.");
            }

            string exactPath = !string.IsNullOrEmpty(hierarchyPath) ? hierarchyPath : (target.Contains("/") ? target : "");
            if (!string.IsNullOrEmpty(exactPath))
            {
                List<GameObject> pathMatches = AllSceneObjects()
                    .Where(go => string.Equals(HierarchyPath(go), exactPath, StringComparison.Ordinal)
                        || string.Equals(HierarchyPath(go, true), exactPath, StringComparison.Ordinal))
                    .ToList();
                if (pathMatches.Count == 1) return new TargetResolution { GameObject = pathMatches[0] };
                if (pathMatches.Count > 1) return Ambiguous(pathMatches);
                return FailResolution("target_not_found", "No loaded scene object matches hierarchy_path '" + exactPath + "'.");
            }

            if (!string.IsNullOrEmpty(target))
            {
                List<GameObject> named = AllSceneObjects()
                    .Where(go => string.Equals(go.name, target, StringComparison.Ordinal))
                    .ToList();
                if (named.Count == 1) return new TargetResolution { GameObject = named[0] };
                if (named.Count > 1) return Ambiguous(named);
                return FailResolution("target_not_found", "No loaded scene object has exact name '" + target + "'.");
            }

            if (descriptorPreferred)
            {
                List<GameObject> avatars = FindAvatarRoots().ToList();
                if (avatars.Count == 1) return new TargetResolution { GameObject = avatars[0] };
                if (avatars.Count > 1) return Ambiguous(avatars, "Multiple avatar roots exist; provide hierarchy_path or instance_id.");
                return FailResolution("avatar_not_found", "No VRCAvatarDescriptor was found in loaded scenes.");
            }

            return FailResolution("target_required", "Provide target, hierarchy_path, or instance_id.");
        }

        private static TargetResolution FailResolution(string code, string message)
        {
            return new TargetResolution { Error = (JObject)ReadOnlyResponse.Error(code, message) };
        }

        private static TargetResolution Ambiguous(List<GameObject> matches, string message = null)
        {
            JArray candidates = new JArray(matches.Take(AmbiguousCandidateLimit).Select(go => new JObject
            {
                ["name"] = go.name,
                ["instance_id"] = go.GetInstanceID(),
                ["hierarchy_path"] = HierarchyPath(go, true)
            }));
            return new TargetResolution
            {
                Error = (JObject)ReadOnlyResponse.Error(
                    "ambiguous_target",
                    message ?? "The target name is ambiguous; use hierarchy_path or instance_id.",
                    new JObject
                    {
                        ["candidate_count"] = matches.Count,
                        ["returned"] = candidates.Count,
                        ["truncated"] = matches.Count > candidates.Count,
                        ["candidates"] = candidates
                    })
            };
        }

        internal static IEnumerable<GameObject> FindAvatarRoots()
        {
            foreach (GameObject go in AllSceneObjects())
            {
                if (GetComponentByFullName(go, DescriptorType) != null) yield return go;
            }
        }

        internal static Component FindDescriptor(GameObject root)
        {
            if (root == null) return null;
            Component direct = GetComponentByFullName(root, DescriptorType);
            if (direct != null) return direct;
            foreach (Component component in root.GetComponentsInChildren<Component>(true))
            {
                if (component != null && FullName(component) == DescriptorType) return component;
            }
            return null;
        }

        internal static Component GetComponentByFullName(GameObject go, string fullName)
        {
            if (go == null) return null;
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component != null && FullName(component) == fullName) return component;
            }
            return null;
        }

        internal static string FullName(Component component)
        {
            return component == null || component.GetType() == null ? "" : (component.GetType().FullName ?? component.GetType().Name);
        }

        internal static bool IsPreviewOrGenerated(GameObject go)
        {
            if (go == null) return false;
            string sceneName = go.scene.IsValid() ? go.scene.name : "";
            string path = HierarchyPath(go, true);
            return sceneName.IndexOf("___NDMF Preview___", StringComparison.OrdinalIgnoreCase) >= 0
                || path.IndexOf("NDMF Preview", StringComparison.OrdinalIgnoreCase) >= 0
                || path.IndexOf("Generated", StringComparison.OrdinalIgnoreCase) >= 0
                || path.IndexOf("Preview Clone", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        internal static JObject Identity(GameObject go)
        {
            return new JObject
            {
                ["name"] = go != null ? go.name : "",
                ["instance_id"] = go != null ? go.GetInstanceID() : 0,
                ["hierarchy_path"] = go != null ? HierarchyPath(go, true) : "",
                ["scene"] = go != null && go.scene.IsValid() ? go.scene.name : "",
                ["active_self"] = go != null && go.activeSelf,
                ["active_in_hierarchy"] = go != null && go.activeInHierarchy,
                ["is_preview_or_generated"] = IsPreviewOrGenerated(go)
            };
        }

        internal static JArray Components(GameObject go, int maxItems)
        {
            JArray result = new JArray();
            if (go == null) return result;
            foreach (Component component in go.GetComponents<Component>().Take(maxItems))
            {
                if (component == null)
                {
                    result.Add(new JObject { ["missing_script"] = true });
                    continue;
                }
                JObject row = new JObject
                {
                    ["type"] = FullName(component),
                    ["instance_id"] = component.GetInstanceID()
                };
                Behaviour behaviour = component as Behaviour;
                Renderer renderer = component as Renderer;
                Collider collider = component as Collider;
                if (behaviour != null) row["enabled"] = behaviour.enabled;
                else if (renderer != null) row["enabled"] = renderer.enabled;
                else if (collider != null) row["enabled"] = collider.enabled;
                result.Add(row);
            }
            return result;
        }

        internal static JArray ShallowSerialized(UnityEngine.Object obj, int maxItems, int maxDepth = 1)
        {
            JArray output = new JArray();
            if (obj == null) return output;
            maxDepth = Mathf.Clamp(maxDepth, 0, 8);
            try
            {
                SerializedObject so = new SerializedObject(obj);
                SerializedProperty iterator = so.GetIterator();
                int count = 0;
                bool enterChildren = true;
                while (iterator.NextVisible(enterChildren) && count < maxItems)
                {
                    enterChildren = iterator.depth < maxDepth;
                    if (iterator.depth > maxDepth || iterator.propertyPath == "m_Script") continue;
                    JToken value;
                    if (!TryReadProperty(iterator, out value)) continue;
                    output.Add(new JObject
                    {
                        ["path"] = iterator.propertyPath,
                        ["type"] = iterator.propertyType.ToString(),
                        ["value"] = value
                    });
                    count++;
                }
            }
            catch (Exception ex)
            {
                output.Add(new JObject { ["read_error"] = ex.GetType().Name + ": " + ex.Message });
            }
            return output;
        }

        private static bool TryReadProperty(SerializedProperty p, out JToken value)
        {
            value = JValue.CreateNull();
            switch (p.propertyType)
            {
                case SerializedPropertyType.Integer: value = p.longValue; return true;
                case SerializedPropertyType.Boolean: value = p.boolValue; return true;
                case SerializedPropertyType.Float: value = p.doubleValue; return true;
                case SerializedPropertyType.String: value = p.stringValue ?? ""; return true;
                case SerializedPropertyType.Color: value = ColorJson(p.colorValue); return true;
                case SerializedPropertyType.ObjectReference:
                    UnityEngine.Object reference = p.objectReferenceValue;
                    value = reference == null ? JValue.CreateNull() : new JObject
                    {
                        ["name"] = reference.name,
                        ["type"] = reference.GetType().FullName,
                        ["instance_id"] = reference.GetInstanceID(),
                        ["asset_path"] = AssetDatabase.GetAssetPath(reference) ?? ""
                    };
                    return true;
                case SerializedPropertyType.LayerMask: value = p.intValue; return true;
                case SerializedPropertyType.Enum: value = p.enumDisplayNames != null && p.enumValueIndex >= 0 && p.enumValueIndex < p.enumDisplayNames.Length ? p.enumDisplayNames[p.enumValueIndex] : p.enumValueIndex.ToString(CultureInfo.InvariantCulture); return true;
                case SerializedPropertyType.Vector2: value = Vector2Json(p.vector2Value); return true;
                case SerializedPropertyType.Vector3: value = Vector3Json(p.vector3Value); return true;
                case SerializedPropertyType.Vector4: value = Vector4Json(p.vector4Value); return true;
                case SerializedPropertyType.Rect: value = new JObject { ["x"] = p.rectValue.x, ["y"] = p.rectValue.y, ["width"] = p.rectValue.width, ["height"] = p.rectValue.height }; return true;
                case SerializedPropertyType.Bounds: value = BoundsJson(p.boundsValue); return true;
                case SerializedPropertyType.Quaternion: Quaternion q = p.quaternionValue; value = new JObject { ["x"] = q.x, ["y"] = q.y, ["z"] = q.z, ["w"] = q.w }; return true;
                default: return false;
            }
        }

        internal static JObject Vector2Json(Vector2 v) { return new JObject { ["x"] = v.x, ["y"] = v.y }; }
        internal static JObject Vector3Json(Vector3 v) { return new JObject { ["x"] = v.x, ["y"] = v.y, ["z"] = v.z }; }
        internal static JObject Vector4Json(Vector4 v) { return new JObject { ["x"] = v.x, ["y"] = v.y, ["z"] = v.z, ["w"] = v.w }; }
        internal static JObject ColorJson(Color c) { return new JObject { ["r"] = c.r, ["g"] = c.g, ["b"] = c.b, ["a"] = c.a }; }
        internal static JObject BoundsJson(Bounds b) { return new JObject { ["center"] = Vector3Json(b.center), ["size"] = Vector3Json(b.size) }; }

        internal static bool IsMeshReadWriteEnabled(Mesh mesh)
        {
            if (mesh == null) return true;
            string path = AssetDatabase.GetAssetPath(mesh);
            if (!string.IsNullOrEmpty(path))
            {
                ModelImporter modelImporter = AssetImporter.GetAtPath(path) as ModelImporter;
                if (modelImporter != null) return modelImporter.isReadable;
            }
            return mesh.isReadable;
        }

        internal static long TriangleCount(Mesh mesh)
        {
            if (mesh == null) return 0;
            long count = 0;
            for (int i = 0; i < mesh.subMeshCount; i++)
            {
                if (mesh.GetTopology(i) == MeshTopology.Triangles) count += (long)mesh.GetIndexCount(i) / 3L;
            }
            return count;
        }

        internal static IEnumerable<Material> UniqueSharedMaterials(GameObject root)
        {
            HashSet<Material> seen = new HashSet<Material>();
            if (root == null) yield break;
            foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                Material[] materials = renderer.sharedMaterials;
                if (materials == null) continue;
                foreach (Material material in materials)
                {
                    if (material != null && seen.Add(material)) yield return material;
                }
            }
        }

        internal static JObject Anatomy(GameObject root, int maxItems = 100)
        {
            SkinnedMeshRenderer[] smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            Animator animator = root.GetComponent<Animator>();
            List<JObject> candidates = new List<JObject>();
            foreach (SkinnedMeshRenderer smr in smrs)
            {
                if (smr == null || smr.sharedMesh == null) continue;
                int diversity = BoneRegionDiversity(smr.bones, animator);
                int visemes = VisemeCount(smr.sharedMesh);
                bool nonBody = HasAny(smr.name, new[] { "Hair", "Face", "Eye", "Teeth", "Tongue", "Ear", "Cloth", "Costume", "Accessory", "Acc_" });
                bool faceName = HasAny(smr.name, new[] { "Face", "Head", "Kao", "顔" });
                bool nonFace = HasAny(smr.name, new[] { "Hair", "Eye", "Teeth", "Tongue", "Ear", "Hat", "Helmet", "Glasses", "Mask", "Horn", "Accessory", "Acc_" });
                int bodyScore = diversity * 100 + Mathf.Min(smr.sharedMesh.vertexCount / 1000, 50) + (!nonBody ? 20 : -50);
                int faceScore = visemes * 20 + smr.sharedMesh.blendShapeCount + (faceName ? 30 : 0) + (diversity <= 2 ? 20 : -50) + (nonFace ? -80 : 0);
                candidates.Add(new JObject
                {
                    ["path"] = HierarchyPath(smr.gameObject, true),
                    ["vertex_count"] = smr.sharedMesh.vertexCount,
                    ["blendshape_count"] = smr.sharedMesh.blendShapeCount,
                    ["bone_region_diversity"] = diversity,
                    ["viseme_count"] = visemes,
                    ["body_score"] = bodyScore,
                    ["face_score"] = faceScore,
                    ["body_candidate"] = false,
                    ["face_candidate"] = false
                });
            }
            JObject body = candidates.OrderByDescending(x => (int)x["body_score"]).FirstOrDefault();
            JObject face = candidates.OrderByDescending(x => (int)x["face_score"]).FirstOrDefault();
            if (face == body && face != null && (int)face["viseme_count"] < 3 && candidates.Count > 1)
                face = candidates.Where(x => x != body).OrderByDescending(x => (int)x["face_score"]).FirstOrDefault();
            if (body != null) body["body_candidate"] = true;
            if (face != null) face["face_candidate"] = true;
            bool sameRenderer = body != null && face == body;
            return new JObject
            {
                ["body_candidate"] = body != null ? body.DeepClone() : JValue.CreateNull(),
                ["face_candidate"] = face != null ? face.DeepClone() : JValue.CreateNull(),
                ["same_renderer_body_face"] = sameRenderer,
                ["combined_body_face_possible"] = sameRenderer,
                ["heuristic_only"] = true,
                ["candidate_count"] = candidates.Count,
                ["candidates_truncated"] = candidates.Count > maxItems,
                ["candidates"] = new JArray(candidates.Take(maxItems))
            };
        }

        internal static int VisemeCount(Mesh mesh)
        {
            if (mesh == null) return 0;
            int count = 0;
            string[] prefixes = { "vrc.v_", "Viseme_", "Fcl_" };
            for (int i = 0; i < mesh.blendShapeCount; i++)
            {
                string name = mesh.GetBlendShapeName(i) ?? "";
                if (prefixes.Any(p => name.StartsWith(p, StringComparison.OrdinalIgnoreCase))) count++;
            }
            return count;
        }

        internal static int BoneRegionDiversity(Transform[] smrBones, Animator animator)
        {
            if (smrBones == null || animator == null || !animator.isHuman) return 0;
            Dictionary<Transform, int> regions = new Dictionary<Transform, int>();
            AddRegion(regions, animator, 0, HumanBodyBones.Head, HumanBodyBones.Neck, HumanBodyBones.Jaw, HumanBodyBones.LeftEye, HumanBodyBones.RightEye);
            AddRegion(regions, animator, 1, HumanBodyBones.Spine, HumanBodyBones.Chest, HumanBodyBones.UpperChest);
            AddRegion(regions, animator, 2, HumanBodyBones.Hips);
            AddRegion(regions, animator, 3, HumanBodyBones.LeftShoulder, HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand);
            AddRegion(regions, animator, 4, HumanBodyBones.RightShoulder, HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand);
            AddRegion(regions, animator, 5, HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot, HumanBodyBones.LeftToes);
            AddRegion(regions, animator, 6, HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot, HumanBodyBones.RightToes);
            HashSet<int> found = new HashSet<int>();
            foreach (Transform bone in smrBones)
            {
                int region;
                if (bone != null && regions.TryGetValue(bone, out region)) found.Add(region);
            }
            return found.Count;
        }

        private static void AddRegion(Dictionary<Transform, int> map, Animator animator, int region, params HumanBodyBones[] bones)
        {
            foreach (HumanBodyBones humanBone in bones)
            {
                Transform transform = animator.GetBoneTransform(humanBone);
                if (transform != null && !map.ContainsKey(transform)) map.Add(transform, region);
            }
        }

        private static bool HasAny(string input, IEnumerable<string> words)
        {
            string value = input ?? "";
            return words.Any(word => value.IndexOf(word, StringComparison.OrdinalIgnoreCase) >= 0);
        }

        internal static AnimatorController FxController(Component descriptor)
        {
            if (descriptor == null) return null;
            SerializedObject so = new SerializedObject(descriptor);
            SerializedProperty layers = so.FindProperty("baseAnimationLayers");
            if (layers == null || !layers.isArray) return null;
            for (int i = 0; i < layers.arraySize; i++)
            {
                SerializedProperty layer = layers.GetArrayElementAtIndex(i);
                SerializedProperty type = layer.FindPropertyRelative("type");
                SerializedProperty controller = layer.FindPropertyRelative("animatorController");
                if (type != null && type.intValue == 5 && controller != null)
                    return controller.objectReferenceValue as AnimatorController;
            }
            return null;
        }

        internal static UnityEngine.Object DescriptorReference(Component descriptor, params string[] names)
        {
            if (descriptor == null) return null;
            SerializedObject so = new SerializedObject(descriptor);
            foreach (string name in names)
            {
                SerializedProperty p = so.FindProperty(name);
                if (p != null && p.propertyType == SerializedPropertyType.ObjectReference && p.objectReferenceValue != null)
                    return p.objectReferenceValue;
            }
            return null;
        }

        internal static JObject ExpressionAnalysis(GameObject root, int maxItems, int maxDepth)
        {
            Component descriptor = FindDescriptor(root);
            if (descriptor == null) return new JObject { ["descriptor_found"] = false };
            UnityEngine.Object parametersObject = DescriptorReference(descriptor, "expressionParameters");
            UnityEngine.Object menuObject = DescriptorReference(descriptor, "expressionsMenu");
            Dictionary<string, JObject> defined = new Dictionary<string, JObject>(StringComparer.Ordinal);
            int syncedBits = 0;
            int totalDefined = 0;
            if (parametersObject != null)
            {
                SerializedObject pso = new SerializedObject(parametersObject);
                SerializedProperty parameters = pso.FindProperty("parameters");
                if (parameters != null && parameters.isArray)
                {
                    totalDefined = parameters.arraySize;
                    for (int i = 0; i < parameters.arraySize; i++)
                    {
                        SerializedProperty item = parameters.GetArrayElementAtIndex(i);
                        string name = ChildString(item, "name");
                        if (string.IsNullOrEmpty(name)) continue;
                        int valueType = ChildInt(item, "valueType", -1);
                        bool synced = ChildBool(item, "networkSynced", true);
                        int cost = synced ? (valueType == 2 ? 1 : 8) : 0;
                        syncedBits += cost;
                        defined[name] = new JObject
                        {
                            ["name"] = name,
                            ["value_type"] = valueType == 0 ? "Int" : valueType == 1 ? "Float" : valueType == 2 ? "Bool" : "Unknown",
                            ["default_value"] = ChildFloat(item, "defaultValue", 0f),
                            ["saved"] = ChildBool(item, "saved", false),
                            ["network_synced"] = synced,
                            ["bit_cost"] = cost
                        };
                    }
                }
            }

            HashSet<string> menuParameters = new HashSet<string>(StringComparer.Ordinal);
            JArray menuTree = new JArray();
            HashSet<int> visitedMenus = new HashSet<int>();
            int emittedMenuRows = 0;
            bool menuTraversalTruncated = false;
            bool menuOutputTruncated = false;
            if (menuObject != null)
                ReadMenu(menuObject, 0, maxDepth, maxItems, menuParameters, menuTree, visitedMenus, ref emittedMenuRows, ref menuTraversalTruncated, ref menuOutputTruncated);

            HashSet<string> animatorParameters = new HashSet<string>(StringComparer.Ordinal);
            AnimatorController fx = FxController(descriptor);
            if (fx != null)
            {
                foreach (AnimatorControllerParameter parameter in fx.parameters) animatorParameters.Add(parameter.name);
            }

            JObject wd = WriteDefaults(fx, maxItems, maxDepth);
            bool writeDefaultsComplete = wd["analysis_complete"] == null || (bool)wd["analysis_complete"];
            bool analysisComplete = !menuTraversalTruncated && writeDefaultsComplete;
            string[] undefined = analysisComplete
                ? menuParameters.Where(name => !defined.ContainsKey(name)).OrderBy(name => name).Take(maxItems).ToArray()
                : new string[0];
            string[] unused = analysisComplete
                ? defined.Keys.Where(name => !menuParameters.Contains(name) && !animatorParameters.Contains(name) && !IsBuiltInParameter(name)).OrderBy(name => name).Take(maxItems).ToArray()
                : new string[0];
            return new JObject
            {
                ["descriptor_found"] = true,
                ["analysis_complete"] = analysisComplete,
                ["menu_truncated"] = menuTraversalTruncated,
                ["menu_output_truncated"] = menuOutputTruncated,
                ["expression_parameters_asset"] = ObjectRef(parametersObject),
                ["expressions_menu_asset"] = ObjectRef(menuObject),
                ["parameter_count"] = totalDefined,
                ["parameters_truncated"] = defined.Count > maxItems,
                ["parameters"] = new JArray(defined.Values.Take(maxItems)),
                ["synced_bits"] = syncedBits,
                ["synced_budget_reference"] = 256,
                ["menu_parameters"] = new JArray(menuParameters.OrderBy(x => x).Take(maxItems)),
                ["animator_parameters"] = new JArray(animatorParameters.OrderBy(x => x).Take(maxItems)),
                ["undefined_menu_parameters"] = analysisComplete ? new JArray(undefined) : null,
                ["unused_parameters"] = analysisComplete ? new JArray(unused) : null,
                ["unused_is_heuristic"] = true,
                ["menu_tree"] = menuTree,
                ["write_defaults"] = wd
            };
        }

        private static void ReadMenu(
            UnityEngine.Object menu,
            int depth,
            int maxDepth,
            int maxItems,
            HashSet<string> parameterNames,
            JArray tree,
            HashSet<int> visited,
            ref int emittedRows,
            ref bool menuTraversalTruncated,
            ref bool menuOutputTruncated)
        {
            if (menu == null) return;
            if (depth > maxDepth || visited.Count >= 4096)
            {
                menuTraversalTruncated = true;
                return;
            }
            if (!visited.Add(menu.GetInstanceID())) return;

            JObject node = null;
            JArray controlRows = null;
            if (emittedRows < maxItems)
            {
                node = new JObject
                {
                    ["name"] = menu.name,
                    ["asset_path"] = AssetDatabase.GetAssetPath(menu) ?? "",
                    ["depth"] = depth,
                    ["controls"] = new JArray()
                };
                tree.Add(node);
                controlRows = (JArray)node["controls"];
            }
            else
            {
                menuOutputTruncated = true;
            }

            SerializedObject so = new SerializedObject(menu);
            SerializedProperty controls = so.FindProperty("controls");
            if (controls == null || !controls.isArray) return;
            for (int i = 0; i < controls.arraySize; i++)
            {
                SerializedProperty control = controls.GetArrayElementAtIndex(i);
                string parameter = NestedString(control, "parameter", "name");
                if (!string.IsNullOrEmpty(parameter)) parameterNames.Add(parameter);
                JArray subParameters = new JArray();
                SerializedProperty subs = control.FindPropertyRelative("subParameters");
                if (subs != null && subs.isArray)
                {
                    for (int j = 0; j < subs.arraySize; j++)
                    {
                        string subName = ChildString(subs.GetArrayElementAtIndex(j), "name");
                        if (!string.IsNullOrEmpty(subName))
                        {
                            parameterNames.Add(subName);
                            if (subParameters.Count < maxItems) subParameters.Add(subName);
                            else menuOutputTruncated = true;
                        }
                    }
                }
                UnityEngine.Object submenu = ChildObject(control, "subMenu");
                if (controlRows != null && emittedRows < maxItems)
                {
                    controlRows.Add(new JObject
                    {
                        ["name"] = ChildString(control, "name"),
                        ["type"] = ChildInt(control, "type", -1),
                        ["parameter"] = parameter,
                        ["sub_parameters"] = subParameters,
                        ["submenu"] = ObjectRef(submenu)
                    });
                    emittedRows++;
                }
                else
                {
                    menuOutputTruncated = true;
                }
                if (submenu != null)
                    ReadMenu(submenu, depth + 1, maxDepth, maxItems, parameterNames, tree, visited, ref emittedRows, ref menuTraversalTruncated, ref menuOutputTruncated);
            }
        }

        internal static JObject WriteDefaults(AnimatorController controller, int maxItems, int maxDepth)
        {
            if (controller == null) return new JObject { ["controller_found"] = false, ["analysis_complete"] = true };
            JArray layers = new JArray();
            int totalOn = 0;
            int totalOff = 0;
            int directBlendTrees = 0;
            int visitedStateNodes = 0;
            int traversedStateGraphEntries = 0;
            int visitedBlendNodes = 0;
            int traversedBlendEdges = 0;
            bool traversalTruncated = false;
            HashSet<AnimatorStateMachine> visitedMachines = new HashSet<AnimatorStateMachine>();
            Dictionary<BlendTree, bool> blendCache = new Dictionary<BlendTree, bool>();
            int layerCount = 0;
            foreach (AnimatorControllerLayer layer in controller.layers)
            {
                if (layerCount >= maxItems || visitedStateNodes >= maxItems)
                {
                    traversalTruncated = true;
                    break;
                }
                layerCount++;
                List<AnimatorState> states = new List<AnimatorState>();
                CollectStates(layer.stateMachine, 0, maxDepth, maxItems, visitedMachines, states, ref visitedStateNodes, ref traversedStateGraphEntries, ref traversalTruncated);
                int on = 0;
                int off = 0;
                int direct = 0;
                foreach (AnimatorState state in states)
                {
                    if (state.writeDefaultValues) on++; else off++;
                    BlendTree tree = state.motion as BlendTree;
                    if (tree == null) continue;
                    bool treeComplete;
                    if (ContainsDirectBlendTree(tree, 0, maxDepth, maxItems, blendCache, new HashSet<BlendTree>(), ref visitedBlendNodes, ref traversedBlendEdges, out treeComplete)) direct++;
                    if (!treeComplete) traversalTruncated = true;
                }
                totalOn += on;
                totalOff += off;
                directBlendTrees += direct;
                layers.Add(new JObject
                {
                    ["name"] = layer.name,
                    ["wd_on"] = on,
                    ["wd_off"] = off,
                    ["mixed"] = on > 0 && off > 0,
                    ["direct_blend_trees"] = direct,
                    ["counts_partial"] = traversalTruncated
                });
            }
            return new JObject
            {
                ["controller_found"] = true,
                ["controller"] = ObjectRef(controller),
                ["wd_on"] = totalOn,
                ["wd_off"] = totalOff,
                ["mixed"] = totalOn > 0 && totalOff > 0,
                ["direct_blend_trees"] = directBlendTrees,
                ["analysis_complete"] = !traversalTruncated,
                ["traversal_truncated"] = traversalTruncated,
                ["visited_state_nodes"] = visitedStateNodes,
                ["traversed_state_graph_entries"] = traversedStateGraphEntries,
                ["visited_blend_tree_nodes"] = visitedBlendNodes,
                ["traversed_blend_tree_edges"] = traversedBlendEdges,
                ["layers"] = layers,
                ["note"] = "Direct Blend Trees and additive layers require deliberate exception-aware review; mixed counts alone are not an automatic fix instruction."
            };
        }

        private static void CollectStates(
            AnimatorStateMachine machine,
            int depth,
            int maxDepth,
            int maxNodes,
            HashSet<AnimatorStateMachine> visited,
            List<AnimatorState> output,
            ref int visitedNodes,
            ref int traversedGraphEntries,
            ref bool traversalTruncated)
        {
            if (machine == null) return;
            if (depth > maxDepth || visitedNodes >= maxNodes)
            {
                traversalTruncated = true;
                return;
            }
            if (!visited.Add(machine)) return;
            visitedNodes++;
            foreach (ChildAnimatorState child in machine.states)
            {
                if (traversedGraphEntries >= maxNodes)
                {
                    traversalTruncated = true;
                    return;
                }
                traversedGraphEntries++;
                if (child.state == null) continue;
                if (visitedNodes >= maxNodes)
                {
                    traversalTruncated = true;
                    return;
                }
                visitedNodes++;
                output.Add(child.state);
            }
            ChildAnimatorStateMachine[] nestedMachines = machine.stateMachines;
            for (int i = 0; i < nestedMachines.Length; i++)
            {
                if (traversedGraphEntries >= maxNodes)
                {
                    traversalTruncated = true;
                    return;
                }
                traversedGraphEntries++;
                CollectStates(nestedMachines[i].stateMachine, depth + 1, maxDepth, maxNodes, visited, output, ref visitedNodes, ref traversedGraphEntries, ref traversalTruncated);
                if (visitedNodes >= maxNodes && i + 1 < nestedMachines.Length)
                {
                    traversalTruncated = true;
                    return;
                }
            }
        }

        internal static bool ContainsDirectBlendTree(BlendTree tree, int maxDepth, int maxNodes, out bool analysisComplete)
        {
            int visitedNodes = 0;
            int traversedEdges = 0;
            Dictionary<BlendTree, bool> cache = new Dictionary<BlendTree, bool>();
            bool found = ContainsDirectBlendTree(tree, 0, maxDepth, maxNodes, cache, new HashSet<BlendTree>(), ref visitedNodes, ref traversedEdges, out analysisComplete);
            return found;
        }

        private static bool ContainsDirectBlendTree(
            BlendTree tree,
            int depth,
            int maxDepth,
            int maxNodes,
            Dictionary<BlendTree, bool> cache,
            HashSet<BlendTree> active,
            ref int visitedNodes,
            ref int traversedEdges,
            out bool analysisComplete)
        {
            analysisComplete = true;
            if (tree == null) return false;
            bool cached;
            if (cache.TryGetValue(tree, out cached)) return cached;
            if (active.Contains(tree)) return false;
            if (depth > maxDepth || visitedNodes >= maxNodes)
            {
                analysisComplete = false;
                return false;
            }
            visitedNodes++;
            active.Add(tree);
            bool found = tree.blendType == BlendTreeType.Direct;
            bool complete = true;
            if (!found)
            {
                foreach (ChildMotion child in tree.children)
                {
                    if (traversedEdges >= maxNodes)
                    {
                        complete = false;
                        break;
                    }
                    traversedEdges++;
                    BlendTree nested = child.motion as BlendTree;
                    if (nested == null) continue;
                    bool childComplete;
                    if (ContainsDirectBlendTree(nested, depth + 1, maxDepth, maxNodes, cache, active, ref visitedNodes, ref traversedEdges, out childComplete)) found = true;
                    if (!childComplete) complete = false;
                    if (found) break;
                }
            }
            active.Remove(tree);
            analysisComplete = complete;
            if (complete) cache[tree] = found;
            return found;
        }

        internal static JObject ObjectRef(UnityEngine.Object obj)
        {
            if (obj == null) return null;
            return new JObject
            {
                ["name"] = obj.name,
                ["type"] = obj.GetType().FullName,
                ["instance_id"] = obj.GetInstanceID(),
                ["asset_path"] = AssetDatabase.GetAssetPath(obj) ?? ""
            };
        }

        internal static string ChildString(SerializedProperty parent, string name)
        {
            SerializedProperty child = parent != null ? parent.FindPropertyRelative(name) : null;
            return child != null ? (child.stringValue ?? "") : "";
        }

        internal static int ChildInt(SerializedProperty parent, string name, int fallback)
        {
            SerializedProperty child = parent != null ? parent.FindPropertyRelative(name) : null;
            return child != null ? child.intValue : fallback;
        }

        internal static float ChildFloat(SerializedProperty parent, string name, float fallback)
        {
            SerializedProperty child = parent != null ? parent.FindPropertyRelative(name) : null;
            return child != null ? child.floatValue : fallback;
        }

        internal static bool ChildBool(SerializedProperty parent, string name, bool fallback)
        {
            SerializedProperty child = parent != null ? parent.FindPropertyRelative(name) : null;
            return child != null ? child.boolValue : fallback;
        }

        internal static UnityEngine.Object ChildObject(SerializedProperty parent, string name)
        {
            SerializedProperty child = parent != null ? parent.FindPropertyRelative(name) : null;
            return child != null ? child.objectReferenceValue : null;
        }

        internal static string NestedString(SerializedProperty parent, string objectName, string fieldName)
        {
            SerializedProperty nested = parent != null ? parent.FindPropertyRelative(objectName) : null;
            return ChildString(nested, fieldName);
        }

        internal static bool IsBuiltInParameter(string name)
        {
            string[] builtIns = {
                "IsLocal", "Viseme", "Voice", "GestureLeft", "GestureRight", "GestureLeftWeight", "GestureRightWeight",
                "AngularY", "VelocityX", "VelocityY", "VelocityZ", "Upright", "Grounded", "Seated", "AFK", "TrackingType",
                "VRMode", "MuteSelf", "InStation", "Earmuffs", "IsOnFriendsList", "AvatarVersion", "ScaleModified",
                "ScaleFactor", "ScaleFactorInverse", "EyeHeightAsMeters", "EyeHeightAsPercent", "IsAnimatorEnabled"
            };
            return builtIns.Contains(name);
        }

        internal static JObject Performance(GameObject root)
        {
            SkinnedMeshRenderer[] skinned = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            MeshRenderer[] basicMeshes = root.GetComponentsInChildren<MeshRenderer>(true);
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            long triangles = 0;
            HashSet<Mesh> unreadableMeshAssets = new HashSet<Mesh>();
            int materialSlots = 0;
            HashSet<Texture> textures = new HashSet<Texture>();
            HashSet<Transform> bones = new HashSet<Transform>();
            foreach (SkinnedMeshRenderer smr in skinned)
            {
                Mesh mesh = smr.sharedMesh;
                triangles += TriangleCount(mesh);
                if (mesh != null && !IsMeshReadWriteEnabled(mesh)) unreadableMeshAssets.Add(mesh);
                foreach (Transform bone in smr.bones ?? new Transform[0]) if (bone != null) bones.Add(bone);
            }
            foreach (MeshRenderer renderer in basicMeshes)
            {
                MeshFilter filter = renderer.GetComponent<MeshFilter>();
                Mesh mesh = filter != null ? filter.sharedMesh : null;
                triangles += TriangleCount(mesh);
                if (mesh != null && !IsMeshReadWriteEnabled(mesh)) unreadableMeshAssets.Add(mesh);
            }
            foreach (Renderer renderer in renderers)
            {
                Material[] mats = renderer.sharedMaterials;
                materialSlots += mats != null ? mats.Length : 0;
                CollectTextures(mats, textures);
            }
            long textureBytes = 0;
            foreach (Texture texture in textures) if (texture != null) textureBytes += Profiler.GetRuntimeMemorySizeLong(texture);

            Component[] all = root.GetComponentsInChildren<Component>(true);
            int physBones = all.Count(c => FullName(c) == PhysBoneType);
            int physBoneColliders = all.Count(c => FullName(c) == PhysBoneColliderType);
            int contacts = all.Count(c => FullName(c) == ContactSenderType || (FullName(c) == ContactReceiverType && !IsLocalOnlyContactReceiver(c)));
            int vrcConstraints = all.Count(IsVrcConstraint);
            int unityConstraints = all.Count(c => c is UnityEngine.Animations.IConstraint && !IsVrcConstraint(c));
            int constraintCount = vrcConstraints + unityConstraints;
            int constraintDepth = 0;
            int missingScripts = all.Count(c => c == null);
            int affectedTransforms = 0;
            int collisionChecks = 0;
            foreach (Component pb in all.Where(c => FullName(c) == PhysBoneType))
            {
                int affected = PhysBoneAffectedTransforms(pb);
                affectedTransforms += affected;
                SerializedObject so = new SerializedObject(pb);
                SerializedProperty colliders = so.FindProperty("colliders");
                collisionChecks += affected * (colliders != null && colliders.isArray ? colliders.arraySize : 0);
            }

            Bounds combined = new Bounds(root.transform.position, Vector3.zero);
            bool hasBounds = false;
            foreach (Renderer renderer in renderers)
            {
                if (renderer is TrailRenderer || renderer is LineRenderer) continue;
                if (!hasBounds) { combined = renderer.bounds; hasBounds = true; }
                else combined.Encapsulate(renderer.bounds);
            }

            ParticleSystem[] particleSystems = root.GetComponentsInChildren<ParticleSystem>(true);
            int totalParticlesActive = 0;
            long meshParticleActivePolys = 0;
            bool particleTrailsEnabled = false;
            bool particleCollisionEnabled = false;
            foreach (ParticleSystem system in particleSystems)
            {
                int maxParticles = system.main.maxParticles;
                totalParticlesActive += maxParticles;
                particleTrailsEnabled |= system.trails.enabled;
                particleCollisionEnabled |= system.collision.enabled;
                ParticleSystemRenderer renderer = system.GetComponent<ParticleSystemRenderer>();
                if (renderer != null && renderer.renderMode == ParticleSystemRenderMode.Mesh)
                {
                    int meshCount = Math.Max(0, renderer.meshCount);
                    Mesh[] particleMeshes = new Mesh[meshCount];
                    int written = meshCount > 0 ? renderer.GetMeshes(particleMeshes) : 0;
                    long maximumMeshTriangles = 0;
                    foreach (Mesh mesh in particleMeshes.Take(written))
                    {
                        maximumMeshTriangles = Math.Max(maximumMeshTriangles, TriangleCount(mesh));
                        if (mesh != null && !IsMeshReadWriteEnabled(mesh)) unreadableMeshAssets.Add(mesh);
                    }
                    meshParticleActivePolys += maximumMeshTriangles * (long)maxParticles;
                }
            }

            int unreadableMeshes = unreadableMeshAssets.Count;

            Cloth[] cloths = root.GetComponentsInChildren<Cloth>(true);
            int totalClothVertices = 0;
            foreach (Cloth cloth in cloths)
            {
                SkinnedMeshRenderer renderer = cloth.GetComponent<SkinnedMeshRenderer>();
                if (renderer != null && renderer.sharedMesh != null) totalClothVertices += renderer.sharedMesh.vertexCount;
            }

            int raycasts = all.Count(c => FullName(c) == "VRC.SDK3.Avatars.Components.VRCRaycast");
            JArray unavailableCategories = new JArray(
                "constraint_depth_exact",
                "sdk_texture_memory_exact",
                "multi_mesh_particle_distribution_exact",
                "particle_material_slot_serialization_parity");
            bool analysisComplete = unavailableCategories.Count == 0;
            JObject metrics = new JObject
            {
                ["triangles"] = triangles,
                ["unreadable_meshes"] = unreadableMeshes,
                ["texture_memory_bytes_runtime_estimate"] = textureBytes,
                ["texture_memory_mb_runtime_estimate"] = Math.Round(textureBytes / 1048576d, 2),
                ["skinned_meshes"] = skinned.Length,
                ["basic_meshes"] = basicMeshes.Length,
                ["material_slots"] = materialSlots,
                ["unique_materials"] = UniqueSharedMaterials(root).Count(),
                ["unique_textures"] = textures.Count,
                ["bones"] = bones.Count,
                ["physbone_components"] = physBones,
                ["physbone_affected_transforms_estimate"] = affectedTransforms,
                ["physbone_colliders"] = physBoneColliders,
                ["physbone_collision_checks_estimate"] = collisionChecks,
                ["contacts"] = contacts,
                ["vrc_constraints"] = vrcConstraints,
                ["unity_constraints"] = unityConstraints,
                ["constraint_count"] = constraintCount,
                ["constraint_depth"] = constraintDepth,
                ["animators"] = root.GetComponentsInChildren<Animator>(true).Length,
                ["lights"] = root.GetComponentsInChildren<Light>(true).Length,
                ["particle_systems"] = particleSystems.Length,
                ["total_particles_active"] = totalParticlesActive,
                ["mesh_particle_active_polys"] = meshParticleActivePolys,
                ["particle_trails_enabled"] = particleTrailsEnabled,
                ["particle_collision_enabled"] = particleCollisionEnabled,
                ["trail_renderers"] = root.GetComponentsInChildren<TrailRenderer>(true).Length,
                ["line_renderers"] = root.GetComponentsInChildren<LineRenderer>(true).Length,
                ["raycasts"] = raycasts,
                ["cloth_components"] = cloths.Length,
                ["total_cloth_vertices"] = totalClothVertices,
                ["audio_sources"] = root.GetComponentsInChildren<AudioSource>(true).Length,
                ["physics_colliders"] = root.GetComponentsInChildren<Collider>(true).Length,
                ["rigidbodies"] = root.GetComponentsInChildren<Rigidbody>(true).Length,
                ["missing_scripts"] = missingScripts,
                ["bounds"] = hasBounds ? BoundsJson(combined) : null,
                ["bounds_size"] = hasBounds ? Vector3Json(combined.size) : null
            };
            return new JObject
            {
                ["metrics"] = metrics,
                ["analysis_complete"] = analysisComplete,
                ["unavailable_categories"] = unavailableCategories,
                ["pc_rank_estimate"] = EstimatePcRank(metrics, analysisComplete, unavailableCategories),
                ["quest_readiness"] = QuestReadiness(metrics),
                ["mesh_read_write_rule"] = unreadableMeshes > 0 ? "Mesh Read/Write Disabled: VRChat forces the avatar performance rank to Very Poor." : "No unreadable rendered mesh was detected.",
                ["threshold_snapshot"] = "VRChat official documentation checked 2026-09-03; verify current official limits before modifying content.",
                ["static_analysis_only"] = true
            };
        }

        private static bool IsLocalOnlyContactReceiver(Component component)
        {
            bool isReceiver = FullName(component) == ContactReceiverType;
            if (!isReceiver) return false;
            try
            {
                SerializedObject so = new SerializedObject(component);
                SerializedProperty property = so.FindProperty("localOnly");
                return property != null && property.propertyType == SerializedPropertyType.Boolean && property.boolValue;
            }
            catch
            {
                return false;
            }
        }

        private static bool IsVrcConstraint(Component component)
        {
            if (component == null) return false;
            Type type = component.GetType();
            string fullName = type.FullName ?? type.Name;
            if (fullName.StartsWith("VRC.SDK3.Dynamics.Constraint.Components.VRC", StringComparison.Ordinal)) return true;
            return type.GetInterfaces().Any(i => (i.FullName ?? i.Name) == "VRC.SDKBase.Validation.Performance.IVRCConstraint");
        }

        private static void CollectTextures(Material[] materials, HashSet<Texture> textures)
        {
            if (materials == null) return;
            foreach (Material material in materials)
            {
                if (material == null || material.shader == null) continue;
                int count = ShaderUtil.GetPropertyCount(material.shader);
                for (int i = 0; i < count; i++)
                {
                    if (ShaderUtil.GetPropertyType(material.shader, i) != ShaderUtil.ShaderPropertyType.TexEnv) continue;
                    Texture texture = material.GetTexture(ShaderUtil.GetPropertyName(material.shader, i));
                    if (texture != null) textures.Add(texture);
                }
            }
        }

        private static JObject EstimatePcRank(JObject metrics, bool analysisComplete, JArray unavailableCategories)
        {
            int worst = 0;
            worst = Math.Max(worst, Rank((long)metrics["triangles"], new long[] { 32000, 70000, 70000, 70000 }));
            worst = Math.Max(worst, Rank((long)Math.Ceiling((double)metrics["texture_memory_mb_runtime_estimate"]), new long[] { 40, 75, 110, 150 }));
            worst = Math.Max(worst, Rank((long)metrics["skinned_meshes"], new long[] { 1, 2, 8, 16 }));
            worst = Math.Max(worst, Rank((long)metrics["basic_meshes"], new long[] { 4, 8, 16, 24 }));
            worst = Math.Max(worst, Rank((long)metrics["material_slots"], new long[] { 4, 8, 16, 32 }));
            worst = Math.Max(worst, Rank((long)metrics["physbone_components"], new long[] { 4, 8, 16, 32 }));
            worst = Math.Max(worst, Rank((long)metrics["physbone_affected_transforms_estimate"], new long[] { 16, 64, 128, 256 }));
            worst = Math.Max(worst, Rank((long)metrics["physbone_colliders"], new long[] { 4, 8, 16, 32 }));
            worst = Math.Max(worst, Rank((long)metrics["physbone_collision_checks_estimate"], new long[] { 32, 128, 256, 512 }));
            worst = Math.Max(worst, Rank((long)metrics["contacts"], new long[] { 8, 16, 24, 32 }));
            worst = Math.Max(worst, Rank((long)metrics["constraint_count"], new long[] { 100, 250, 300, 350 }));
            worst = Math.Max(worst, Rank((long)metrics["constraint_depth"], new long[] { 20, 50, 80, 100 }));
            worst = Math.Max(worst, Rank((long)metrics["animators"], new long[] { 1, 4, 16, 32 }));
            worst = Math.Max(worst, Rank((long)metrics["bones"], new long[] { 75, 150, 256, 400 }));
            worst = Math.Max(worst, Rank((long)metrics["lights"], new long[] { 0, 0, 0, 1 }));
            worst = Math.Max(worst, Rank((long)metrics["particle_systems"], new long[] { 0, 4, 8, 16 }));
            worst = Math.Max(worst, Rank((long)metrics["total_particles_active"], new long[] { 0, 300, 1000, 2500 }));
            worst = Math.Max(worst, Rank((long)metrics["mesh_particle_active_polys"], new long[] { 0, 1000, 2000, 5000 }));
            worst = Math.Max(worst, BoolRank((bool)metrics["particle_trails_enabled"], new bool[] { false, false, true, true }));
            worst = Math.Max(worst, BoolRank((bool)metrics["particle_collision_enabled"], new bool[] { false, false, true, true }));
            worst = Math.Max(worst, Rank((long)metrics["trail_renderers"], new long[] { 1, 2, 4, 8 }));
            worst = Math.Max(worst, Rank((long)metrics["line_renderers"], new long[] { 1, 2, 4, 8 }));
            worst = Math.Max(worst, Rank((long)metrics["raycasts"], new long[] { 1, 4, 8, 15 }));
            worst = Math.Max(worst, Rank((long)metrics["cloth_components"], new long[] { 0, 1, 1, 1 }));
            worst = Math.Max(worst, Rank((long)metrics["total_cloth_vertices"], new long[] { 0, 50, 100, 200 }));
            worst = Math.Max(worst, Rank((long)metrics["physics_colliders"], new long[] { 0, 1, 8, 8 }));
            worst = Math.Max(worst, Rank((long)metrics["rigidbodies"], new long[] { 0, 1, 8, 8 }));
            worst = Math.Max(worst, Rank((long)metrics["audio_sources"], new long[] { 1, 4, 8, 8 }));
            JToken sizeToken = metrics["bounds_size"];
            if (sizeToken is JObject) worst = Math.Max(worst, BoundsRank((JObject)sizeToken));
            string[] rankNames = { "Excellent", "Good", "Medium", "Poor", "Very Poor" };
            int unreadable = (int)metrics["unreadable_meshes"];
            return new JObject
            {
                ["rank"] = analysisComplete ? rankNames[Mathf.Clamp(worst, 0, rankNames.Length - 1)] : null,
                ["measured_metrics_worst_rank"] = rankNames[Mathf.Clamp(worst, 0, rankNames.Length - 1)],
                ["not_an_official_rank_bound"] = "This is only the worst rank among measured/estimated categories. Omitted categories can make the SDK rank worse.",
                ["forced_rank"] = unreadable > 0 ? "Very Poor" : null,
                ["forced_reason"] = unreadable > 0 ? "Mesh Read/Write Disabled" : null,
                ["analysis_complete"] = analysisComplete,
                ["unavailable_categories"] = unavailableCategories.DeepClone(),
                ["advisory_only"] = true
            };
        }

        private static int Rank(long value, long[] thresholds)
        {
            for (int i = 0; i < thresholds.Length; i++) if (value <= thresholds[i]) return i;
            return thresholds.Length;
        }

        private static int BoolRank(bool value, bool[] thresholds)
        {
            for (int i = 0; i < thresholds.Length; i++) if (!value || thresholds[i]) return i;
            return thresholds.Length;
        }

        private static int BoundsRank(JObject size)
        {
            double x = Math.Abs((double)size["x"]);
            double y = Math.Abs((double)size["y"]);
            double z = Math.Abs((double)size["z"]);
            Vector3[] limits =
            {
                new Vector3(2.5f, 2.5f, 2.5f),
                new Vector3(4f, 4f, 4f),
                new Vector3(5f, 6f, 5f),
                new Vector3(5f, 6f, 5f)
            };
            for (int i = 0; i < limits.Length; i++)
                if (x <= limits[i].x && y <= limits[i].y && z <= limits[i].z) return i;
            return limits.Length;
        }

        private static JObject QuestReadiness(JObject metrics)
        {
            JArray issues = new JArray();
            bool analysisComplete = false;
            if ((long)metrics["triangles"] > 20000) issues.Add("Triangles exceed the current mobile Poor threshold reference (20,000).");
            if ((double)metrics["texture_memory_mb_runtime_estimate"] > 40d) issues.Add("Estimated texture memory exceeds the current mobile Poor threshold reference (40 MB).");
            if ((int)metrics["skinned_meshes"] > 2) issues.Add("Skinned meshes exceed the current mobile Poor threshold reference (2).");
            if ((int)metrics["basic_meshes"] > 2) issues.Add("Basic meshes exceed the current mobile Poor threshold reference (2).");
            if ((int)metrics["material_slots"] > 4) issues.Add("Material slots exceed the current mobile Poor threshold reference (4).");
            if ((int)metrics["animators"] > 2) issues.Add("Animators exceed the current mobile Poor threshold reference (2).");
            if ((int)metrics["bones"] > 150) issues.Add("Bones exceed the current mobile Poor threshold reference (150).");
            if ((int)metrics["physbone_components"] > 8) issues.Add("PhysBones exceed the current mobile Poor threshold reference (8).");
            if ((int)metrics["physbone_affected_transforms_estimate"] > 64) issues.Add("PhysBone affected transforms exceed the current mobile Poor threshold reference (64).");
            if ((int)metrics["physbone_colliders"] > 16) issues.Add("PhysBone colliders exceed the current mobile Poor threshold reference (16).");
            if ((int)metrics["physbone_collision_checks_estimate"] > 64) issues.Add("PhysBone collision checks exceed the current mobile Poor threshold reference (64).");
            if ((int)metrics["contacts"] > 16) issues.Add("Contacts exceed the current mobile Poor threshold reference (16).");
            if ((int)metrics["constraint_count"] > 150) issues.Add("Constraints exceed the current mobile Poor threshold reference (150).");
            if ((int)metrics["constraint_depth"] > 50) issues.Add("Constraint depth exceeds the current mobile Poor threshold reference (50).");
            if ((int)metrics["particle_systems"] > 2) issues.Add("Particle systems exceed the current mobile Poor threshold reference (2).");
            if ((int)metrics["total_particles_active"] > 200) issues.Add("Total active particles exceed the current mobile Poor threshold reference (200).");
            if ((long)metrics["mesh_particle_active_polys"] > 400) issues.Add("Mesh particle active polygons exceed the current mobile Poor threshold reference (400).");

            if ((int)metrics["trail_renderers"] > 1) issues.Add("Trail renderers exceed the current mobile Poor threshold reference (1).");
            if ((int)metrics["line_renderers"] > 1) issues.Add("Line renderers exceed the current mobile Poor threshold reference (1).");
            if ((int)metrics["raycasts"] > 8) issues.Add("Raycasts exceed the current mobile Poor threshold reference (8).");
            if ((int)metrics["unreadable_meshes"] > 0) issues.Add("At least one rendered mesh has Read/Write disabled, forcing Very Poor.");
            return new JObject
            {
                ["advisory_only"] = true,
                ["analysis_complete"] = analysisComplete,
                ["ready_for_mobile_poor_or_better"] = issues.Count == 0 && analysisComplete,
                ["issues"] = issues,
                ["poor_only_categories"] = new JArray(new string[]
                {
                    (bool)metrics["particle_trails_enabled"] ? "particle_trails_enabled" : null,
                    (bool)metrics["particle_collision_enabled"] ? "particle_collision_enabled" : null
                }.Where(value => !string.IsNullOrEmpty(value))),
                ["unavailable_categories"] = new JArray("constraint_depth_exact", "sdk_texture_memory_exact", "multi_mesh_particle_distribution_exact", "particle_material_slot_serialization_parity", "mobile_shader_compatibility", "built_bundle_size"),
                ["requires_mobile_shader_and_build_size_check"] = true
            };
        }

        internal static int PhysBoneAffectedTransforms(Component component)
        {
            if (component == null) return 0;
            SerializedObject so = new SerializedObject(component);
            SerializedProperty rootProperty = so.FindProperty("rootTransform");
            Transform root = rootProperty != null ? rootProperty.objectReferenceValue as Transform : null;
            if (root == null) root = component.transform;
            HashSet<Transform> exclusions = new HashSet<Transform>();
            SerializedProperty exclusionProperty = so.FindProperty("exclusions");
            if (exclusionProperty != null && exclusionProperty.isArray)
            {
                for (int i = 0; i < exclusionProperty.arraySize; i++)
                {
                    Transform excluded = exclusionProperty.GetArrayElementAtIndex(i).objectReferenceValue as Transform;
                    if (excluded != null) exclusions.Add(excluded);
                }
            }
            return CountTransforms(root, exclusions);
        }

        private static int CountTransforms(Transform root, HashSet<Transform> exclusions)
        {
            if (root == null || exclusions.Contains(root)) return 0;
            int count = 1;
            for (int i = 0; i < root.childCount; i++) count += CountTransforms(root.GetChild(i), exclusions);
            return count;
        }

        internal static IEnumerable<UnityEditor.PackageManager.PackageInfo> RegisteredPackages()
        {
            UnityEditor.PackageManager.PackageInfo[] packages = UnityEditor.PackageManager.PackageInfo.GetAllRegisteredPackages();
            return packages ?? new UnityEditor.PackageManager.PackageInfo[0];
        }

        internal static JArray PackageRows(int maxItems)
        {
            return new JArray(RegisteredPackages().OrderBy(p => p.name).Take(maxItems).Select(p => new JObject
            {
                ["name"] = p.name,
                ["version"] = p.version,
                ["source"] = p.source.ToString()
            }));
        }

        internal static JObject IntegrationFlags(GameObject root = null)
        {
            List<string> types = new List<string>();
            if (root != null)
                types.AddRange(root.GetComponentsInChildren<Component>(true).Where(c => c != null).Select(FullName));
            HashSet<string> packages = new HashSet<string>(RegisteredPackages().Select(p => p.name), StringComparer.OrdinalIgnoreCase);
            IEnumerable<Material> materials = root != null ? UniqueSharedMaterials(root) : Enumerable.Empty<Material>();
            return new JObject
            {
                ["VRChat SDK"] = types.Any(t => t.StartsWith("VRC.", StringComparison.Ordinal)) || packages.Any(p => p.IndexOf("vrchat", StringComparison.OrdinalIgnoreCase) >= 0),
                ["ModularAvatar"] = types.Any(t => t.IndexOf("ModularAvatar", StringComparison.OrdinalIgnoreCase) >= 0) || packages.Contains("nadena.dev.modular-avatar"),
                ["nadena.dev.ndmf"] = types.Any(t => t.IndexOf("nadena.dev.ndmf", StringComparison.OrdinalIgnoreCase) >= 0) || packages.Contains("nadena.dev.ndmf"),
                ["VRCFury"] = types.Any(t => t.IndexOf("VRCFury", StringComparison.OrdinalIgnoreCase) >= 0) || packages.Any(p => p.IndexOf("vrcfury", StringComparison.OrdinalIgnoreCase) >= 0),
                ["FaceEmo"] = types.Any(t => t.IndexOf("FaceEmo", StringComparison.OrdinalIgnoreCase) >= 0) || packages.Any(p => p.IndexOf("face-emo", StringComparison.OrdinalIgnoreCase) >= 0),
                ["AvatarOptimizer"] = types.Any(t => t.IndexOf("AvatarOptimizer", StringComparison.OrdinalIgnoreCase) >= 0) || packages.Any(p => p.IndexOf("avatar-optimizer", StringComparison.OrdinalIgnoreCase) >= 0),
                ["lilToon"] = materials.Any(m => m != null && m.shader != null && m.shader.name.IndexOf("lilToon", StringComparison.OrdinalIgnoreCase) >= 0) || packages.Any(p => p.IndexOf("liltoon", StringComparison.OrdinalIgnoreCase) >= 0)
            };
        }

        internal static string NormalizeBoneName(string name)
        {
            if (string.IsNullOrEmpty(name)) return "";
            string value = name.ToLowerInvariant();
            string[] remove = { "j_bip_", "bip_", "bone", "joint", "mixamorig:", "armature", "_l", "_r", ".l", ".r", "left", "right", " " };
            foreach (string token in remove) value = value.Replace(token, "");
            return new string(value.Where(char.IsLetterOrDigit).ToArray());
        }
    }
}
