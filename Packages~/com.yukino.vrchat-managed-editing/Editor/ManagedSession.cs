using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Yukino.VRChatManagedEditing
{
    // No EditorPrefs/SessionState/asset persistence: a domain reload starts locked.
    [InitializeOnLoad]
    internal static class ManagedSession
    {
        private sealed class Pending
        {
            internal string Id, Lease, TargetKey, MeshKey, WeightState;
            internal double Created;
            internal List<ShapeDelta> Deltas;
        }
        private sealed class Applied
        {
            internal string Id, PlanId, TargetKey, MeshKey;
            internal SkinnedMeshRenderer Renderer;
            internal List<ShapeDelta> Deltas;
            internal bool Restored;
        }
        private static readonly int MainThread = Thread.CurrentThread.ManagedThreadId;
        internal static GatePolicy Gate { get; } = new GatePolicy(() => EditorApplication.timeSinceStartup);
        internal static SkinnedMeshRenderer Target { get; private set; }
        private static Pending pending;
        private static Applied last;
        private static double nextIdentityCheck;
        private static long assetRevision;
        internal static string PendingPlanId => pending == null ? "" : pending.Id;
        internal static string LastApplyId => last == null || last.Restored ? "" : last.Id;
        internal static string LastApplySummary => last == null ? "No source apply" : last.Renderer == null ? "Previous target no longer exists" :
            last.Renderer.gameObject.scene.path + " / " + last.Renderer.name + "\n" + last.TargetKey + "\n" +
            string.Join("\n", last.Deltas.Select(d => d.Name + ": " + d.Before.ToString("R", CultureInfo.InvariantCulture) + " → " + d.After.ToString("R", CultureInfo.InvariantCulture)));
        internal static string CurrentPlanSummary => pending == null ? "No pending plan / 暂无方案" :
            string.Join("\n", pending.Deltas.Select(d => d.Name + ": " + d.Before.ToString("R", CultureInfo.InvariantCulture) + " → " + d.After.ToString("R", CultureInfo.InvariantCulture)));

        static ManagedSession()
        {
            AssemblyReloadEvents.beforeAssemblyReload += Revoke;
            EditorApplication.quitting += Revoke;
            EditorApplication.playModeStateChanged += _ => Revoke();
            EditorSceneManager.activeSceneChangedInEditMode += (previous, next) => { if (!EditorSceneManager.IsPreviewScene(previous) && !EditorSceneManager.IsPreviewScene(next)) Revoke(); };
            EditorSceneManager.newSceneCreated += (scene, setup, mode) => { if (!EditorSceneManager.IsPreviewScene(scene)) Revoke(); };
            EditorSceneManager.sceneOpened += (scene, mode) => { if (!EditorSceneManager.IsPreviewScene(scene)) Revoke(); };
            EditorSceneManager.sceneClosing += (scene, removing) => { if (!EditorSceneManager.IsPreviewScene(scene)) Revoke(); };
            EditorSceneManager.sceneSaving += (scene, path) => { if (!EditorSceneManager.IsPreviewScene(scene)) Revoke(); };
            EditorApplication.update += Tick;
        }
        internal static void AssetsChanged()
        {
            // Conservatively invalidate even a same-content reimport, including rollback snapshots.
            assetRevision++;
            Revoke();
        }
        private static void Tick()
        {
            if (!Gate.Active && (pending != null || FacePreview.Ready)) Revoke();
            if (Gate.Active && Target == null) Revoke();
            if (Target != null && Gate.Active && EditorApplication.timeSinceStartup >= nextIdentityCheck)
            {
                nextIdentityCheck = EditorApplication.timeSinceStartup + 0.5;
                try
                {
                    Ready(); ValidateSource(Target);
                    if (TargetKey(Target) != Gate.TargetKey || MeshKey(Target) != Gate.MeshKey) Revoke();
                    if (pending != null && (pending.WeightState != WeightState(Target) || EditorApplication.timeSinceStartup - pending.Created > 120)) Revoke();
                }
                catch (Exception) { Revoke(); }
            }
        }
        private static void Ready()
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread)
                throw Denied("MAIN_THREAD_REQUIRED", "Editor operations must run on Unity's main thread.");
            if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode || AnimationMode.InAnimationMode())
                throw Denied("EDITOR_BUSY", "Stop animation preview/play mode and wait for compilation/import before editing.");
        }
        private static GateDeniedException Denied(string code, string message) { return new GateDeniedException(code, message); }

        internal static void GrantLocally(SkinnedMeshRenderer target, IEnumerable<string> names, bool preview, bool apply, double seconds, int writes)
        {
            Revoke();
            Ready();
            if (!ManagedWindow.IsLocalWindowOpen || !ManagedWindow.TransportAcknowledged)
                throw Denied("LOCAL_OPERATOR_REQUIRED", "Open the local window and acknowledge the restrictive transport deployment first.");
            ValidateSource(target);
            if (apply && !ManagedWindow.CheckpointAcknowledged)
                throw Denied("CHECKPOINT_REQUIRED", "Confirm your saved, restorable checkpoint in the local operator panel first.");
            if (apply && target.gameObject.scene.isDirty)
                throw Denied("UNSAVED_BASELINE", "Source scene has existing unsaved changes. Save/checkpoint it yourself before granting Apply.");
            var selected = names == null ? new List<string>() : names.ToList();
            ReadWeights(target, selected); // Disambiguate exact source names BEFORE granting.
            EditCapability caps = (preview ? EditCapability.Preview : EditCapability.None) | (apply ? EditCapability.Apply : EditCapability.None);
            Gate.Grant(TargetKey(target), MeshKey(target), selected, caps, seconds, writes);
            Target = target;
        }
        internal static void Revoke()
        {
            Gate.Revoke();
            pending = null;
            try { FacePreview.Clear(); }
            catch (Exception e) { Debug.LogWarning("VRChat Managed Editing: preview cleanup failed: " + e.GetType().Name); }
            // Source edits are NOT silently undone. Local Undo / explicit exact rollback remains available.
        }
        private static void ValidateSource(SkinnedMeshRenderer renderer)
        {
            if (renderer == null || renderer.sharedMesh == null || EditorUtility.IsPersistent(renderer))
                throw Denied("INVALID_SOURCE", "Select a source SkinnedMeshRenderer in a saved scene, not a prefab/mesh asset.");
            Scene scene = renderer.gameObject.scene;
            if (!scene.IsValid() || !scene.isLoaded || string.IsNullOrEmpty(scene.path) || EditorSceneManager.IsPreviewScene(scene))
                throw Denied("INVALID_SCENE", "Preview/generated/unsaved scenes are not editing targets.");
            var stage = PrefabStageUtility.GetCurrentPrefabStage();
            if (stage != null && stage.scene == scene)
                throw Denied("PREFAB_STAGE_DENIED", "Edit a source scene instance, not Prefab Mode.");
            if (renderer.gameObject.hideFlags != HideFlags.None || renderer.hideFlags != HideFlags.None ||
                scene.name.IndexOf("NDMF Preview", StringComparison.OrdinalIgnoreCase) >= 0)
                throw Denied("GENERATED_SOURCE_DENIED", "Hidden/generated preview objects cannot be granted.");
            for (Transform t = renderer.transform; t != null; t = t.parent)
                if (t.gameObject.hideFlags != HideFlags.None)
                    throw Denied("GENERATED_SOURCE_DENIED", "A hidden/generated ancestor is not an authoring target.");
            ValidateMeshAsset(renderer.sharedMesh);
            if (renderer.sharedMesh.blendShapeCount == 0 || renderer.sharedMesh.blendShapeCount > 10000)
                throw Denied("MESH_LIMIT", "Mesh BlendShape inventory is empty or exceeds the inspection bound.");
        }
        internal static string ValidateMeshAsset(Mesh mesh)
        {
            string path = mesh == null ? "" : AssetDatabase.GetAssetPath(mesh);
            var importer = string.IsNullOrEmpty(path) ? null : AssetImporter.GetAtPath(path) as ModelImporter;
            if (mesh == null || !EditorUtility.IsPersistent(mesh) || mesh.hideFlags != HideFlags.None ||
                !AssetDatabase.IsSubAsset(mesh) || importer == null ||
                !(path.StartsWith("Assets/", StringComparison.Ordinal) || path.StartsWith("Packages/", StringComparison.Ordinal)))
            {
                Revoke();
                throw Denied("UNTRACKED_MESH", "Only immutable ModelImporter mesh subassets are supported; transient/generated/native mesh assets are denied.");
            }
            UnityEngine.Object mainAsset = AssetDatabase.LoadMainAssetAtPath(path);
            if (mainAsset == null || EditorUtility.IsDirty(mesh) || EditorUtility.IsDirty(importer) || EditorUtility.IsDirty(mainAsset))
            {
                Revoke();
                throw Denied("DIRTY_MESH", "Mesh/model/importer has unsaved changes. Revoke, restore/reimport the immutable asset, then grant afresh.");
            }
            return path;
        }
        private static string TargetKey(SkinnedMeshRenderer renderer)
        {
            return renderer.gameObject.scene.path + "|" + GlobalObjectId.GetGlobalObjectIdSlow(renderer) + "|" + renderer.GetInstanceID();
        }
        private static string MeshKey(SkinnedMeshRenderer renderer)
        {
            Mesh mesh = renderer.sharedMesh;
            var b = new StringBuilder();
            // Identity/version check, NOT a native geometry hash. See the immutable-asset trust boundary in README.
            string path = ValidateMeshAsset(mesh);
            var importer = AssetImporter.GetAtPath(path);
            b.Append(GlobalObjectId.GetGlobalObjectIdSlow(mesh)).Append('|').Append(mesh.GetInstanceID()).Append('|').Append(mesh.vertexCount).Append('|');
            b.Append(path).Append('|').Append(AssetDatabase.GetAssetDependencyHash(path)).Append('|').Append(assetRevision)
                .Append('|').Append(EditorUtility.GetDirtyCount(mesh)).Append('|').Append(EditorUtility.GetDirtyCount(importer))
                .Append('|').Append(EditorUtility.GetDirtyCount(AssetDatabase.LoadMainAssetAtPath(path)));
            for (int i = 0; i < mesh.blendShapeCount; i++) b.Append('|').Append(i).Append(':').Append(mesh.GetBlendShapeName(i)).Append(':').Append(mesh.GetBlendShapeFrameCount(i));
            return Digest(b.ToString());
        }
        private static string Digest(string value)
        {
            using (SHA256 hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-", "");
        }
        private static string WeightState(SkinnedMeshRenderer renderer)
        {
            var b = new StringBuilder();
            for (int i = 0; i < renderer.sharedMesh.blendShapeCount; i++) b.Append(renderer.GetBlendShapeWeight(i).ToString("R", CultureInfo.InvariantCulture)).Append(';');
            return Digest(b.ToString());
        }
        private static Dictionary<string, float> ReadWeights(SkinnedMeshRenderer renderer, IEnumerable<string> names)
        {
            var result = new Dictionary<string, float>(StringComparer.Ordinal);
            foreach (string name in names)
            {
                if (string.IsNullOrWhiteSpace(name) || name.Length > 256 || result.ContainsKey(name))
                    throw Denied("AMBIGUOUS_NAME", "Names must be exact, unique and at most 256 characters.");
                int index = renderer.sharedMesh.GetBlendShapeIndex(name);
                if (index < 0) throw Denied("UNKNOWN_SHAPE", "Requested shape does not exist: " + name);
                int occurrences = 0;
                for (int i = 0; i < renderer.sharedMesh.blendShapeCount; i++) if (renderer.sharedMesh.GetBlendShapeName(i) == name) occurrences++;
                if (occurrences != 1) throw Denied("AMBIGUOUS_NAME", "Mesh contains duplicate names; select an unambiguous shape.");
                result.Add(name, renderer.GetBlendShapeWeight(index));
            }
            return result;
        }
        internal static void OnlyKeys(JObject args, params string[] allowed)
        {
            if (args == null) throw new ArgumentException("Arguments must be an object.");
            var set = new HashSet<string>(allowed, StringComparer.Ordinal);
            if (args.Properties().Any(p => !set.Contains(p.Name))) throw new ArgumentException("Unknown argument fields are rejected.");
        }
        internal static string RequireId(JObject args, string key)
        {
            JToken token = args[key];
            if (token == null || token.Type != JTokenType.String || !Guid.TryParseExact((string)token, "N", out _))
                throw new ArgumentException(key + " must be an exact plan/apply ID.");
            return (string)token;
        }
        private static JObject Ok(string message, bool mutated, bool sourceMutated, JObject data)
        {
            data["mutated"] = mutated;
            data["source_mutated"] = sourceMutated;
            data["read_only"] = !mutated;
            data["permission_changed"] = false;
            data["saved"] = false;
            return new JObject { ["success"] = true, ["message"] = message, ["data"] = data };
        }
        private static JArray DeltaRows(IEnumerable<ShapeDelta> deltas)
        {
            return new JArray(deltas.Select(d => new JObject { ["name"] = d.Name, ["before"] = d.Before, ["after"] = d.After }));
        }
        internal static JObject Status()
        {
            Ready();
            bool previewReady = PreviewIsCurrent();
            return Ok("Local scope status; this call cannot grant permission.", false, false, new JObject {
                ["active"] = Gate.Active, ["lease_id"] = Gate.LeaseId, ["target"] = Target == null ? "" : TargetKey(Target),
                ["capabilities"] = Gate.Capabilities.ToString(), ["shape_names"] = new JArray(Gate.Names),
                ["remaining_seconds"] = Gate.RemainingSeconds, ["remaining_writes"] = Gate.RemainingWrites,
                ["pending_plan_id"] = PendingPlanId, ["last_apply_id"] = LastApplyId, ["last_apply_restored"] = last != null && last.Restored,
                ["preview_ready"] = previewReady, ["transport_acknowledged_locally"] = ManagedWindow.TransportAcknowledged,
                ["transport_verified_automatically"] = false, ["local_only_unlock"] = true });
        }
        internal static JObject Plan(JObject args)
        {
            Ready(); OnlyKeys(args, "changes_json"); ValidateSource(Target);
            if (!Gate.Active) throw Denied("LOCKED", "Choose target and grant a bounded scope in the local Unity panel first.");
            JToken token = args["changes_json"];
            if (token == null || token.Type != JTokenType.String || ((string)token).Length > 32768)
                throw new ArgumentException("changes_json must be a bounded JSON string.");
            JArray array = JArray.Parse((string)token, new JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });
            if (array.Count < 1 || array.Count > 128) throw new ArgumentException("Plan must contain 1-128 edits.");
            var edits = new List<ShapeEdit>();
            foreach (JToken item in array)
            {
                JObject row = item as JObject;
                OnlyKeys(row, "name", "value");
                if (row["name"] == null || row["name"].Type != JTokenType.String || row["value"] == null ||
                    (row["value"].Type != JTokenType.Integer && row["value"].Type != JTokenType.Float))
                    throw new ArgumentException("Each change must have string name and numeric value.");
                edits.Add(new ShapeEdit((string)row["name"], (float)row["value"]));
            }
            var deltas = DeltaPolicy.ValidateChanges(ReadWeights(Target, Gate.Names), edits);
            // Planning needs only preview OR apply scope; no mutation and no budget consumption.
            EditCapability capability = (Gate.Capabilities & EditCapability.Preview) != 0 ? EditCapability.Preview : EditCapability.Apply;
            Gate.Demand(TargetKey(Target), MeshKey(Target), deltas.Select(d => d.Name), capability, Gate.LeaseId);
            pending = null;
            try { FacePreview.Clear(); }
            catch { Revoke(); throw; }
            pending = new Pending { Id = Guid.NewGuid().ToString("N"), Lease = Gate.LeaseId, TargetKey = TargetKey(Target), MeshKey = MeshKey(Target),
                WeightState = WeightState(Target), Created = EditorApplication.timeSinceStartup, Deltas = deltas };
            return Ok("Plan created without scene edits. Preview/Apply require the corresponding local scope.", false, false,
                new JObject { ["plan_id"] = pending.Id, ["expires_in_seconds"] = Math.Min(120, Gate.RemainingSeconds), ["changes"] = DeltaRows(deltas) });
        }
        private static Pending RequirePlan(string id)
        {
            Ready();
            if (pending == null || pending.Id != id) throw Denied("UNKNOWN_PLAN", "Plan is no longer pending; inspect status and re-plan.");
            try
            {
                ValidateSource(Target);
                double age = EditorApplication.timeSinceStartup - pending.Created;
                if (age < 0 || age > 120) throw Denied("EXPIRED_PLAN", "Plan expired; re-read and re-plan.");
                if (pending.TargetKey != TargetKey(Target) || pending.MeshKey != MeshKey(Target)) throw Denied("STALE_TARGET", "Target or mesh changed.");
                if (pending.WeightState != WeightState(Target)) throw Denied("STALE_WEIGHTS", "Source weights changed since planning; do not overwrite them.");
                return pending;
            }
            catch { Revoke(); throw; }
        }
        internal static bool PreviewIsCurrent()
        {
            if (!FacePreview.Ready) return false;
            try
            {
                if (pending == null || FacePreview.PlanId != pending.Id || FacePreview.SourceState != pending.WeightState)
                    throw Denied("STALE_PREVIEW", "Preview is not bound to the current plan.");
                Pending p = RequirePlan(pending.Id);
                Gate.Demand(p.TargetKey, p.MeshKey, p.Deltas.Select(d => d.Name), EditCapability.Preview, p.Lease);
                return true;
            }
            catch { Revoke(); return false; }
        }
        internal static JObject Preview(string planId, bool includeImages)
        {
            Ready();
            try
            {
                Pending p = RequirePlan(planId);
                Gate.Demand(p.TargetKey, p.MeshKey, p.Deltas.Select(d => d.Name), EditCapability.Preview, p.Lease);
                DeltaPolicy.ValidateCurrent(p.Deltas, ReadWeights(Target, p.Deltas.Select(d => d.Name)));
                FacePreview.Build(Target, p.Deltas, p.Id, p.WeightState);
                if (!PreviewIsCurrent()) throw Denied("STALE_PREVIEW", "Source or permission changed during preview.");
                var data = new JObject { ["plan_id"] = p.Id, ["preview_ready"] = true, ["changes"] = DeltaRows(p.Deltas) };
                if (includeImages)
                {
                    var images = new JArray();
                    foreach (bool after in new[] { false, true })
                    {
                        byte[] png = FacePreview.Capture(after);
                        if (png == null || png.Length > 1024 * 1024) throw new InvalidOperationException("Preview image exceeded the fixed bound.");
                        images.Add(new JObject { ["label"] = after ? "after" : "before", ["mime_type"] = "image/png", ["data_base64"] = Convert.ToBase64String(png) });
                    }
                    data["preview_images"] = images;
                }
                return Ok("Isolated preview objects/images created; source weights and files unchanged.", true, false, data);
            }
            catch { Revoke(); throw; }
        }
        internal static JObject Apply(string planId)
        {
            Ready();
            if (last != null && last.PlanId == planId)
                return Ok("This plan was already applied; no write replayed. Inspect last_apply_restored.", false, false,
                    new JObject { ["apply_id"] = last.Id, ["already_applied"] = true, ["last_apply_restored"] = last.Restored });
            Pending p = RequirePlan(planId);
            Gate.Demand(p.TargetKey, p.MeshKey, p.Deltas.Select(d => d.Name), EditCapability.Apply, p.Lease);
            DeltaPolicy.ValidateCurrent(p.Deltas, ReadWeights(Target, p.Deltas.Select(d => d.Name)));
            Gate.ConsumeWrite();
            WriteTransaction(Target, p.Deltas, false);
            last = new Applied { Id = Guid.NewGuid().ToString("N"), PlanId = p.Id, TargetKey = p.TargetKey, MeshKey = p.MeshKey,
                Renderer = Target, Deltas = new List<ShapeDelta>(p.Deltas), Restored = false };
            pending = null;
            FacePreview.Clear();
            return Ok("Applied once; values read back. Scene/Prefab NOT saved. Use local Undo or exact rollback.", true, true,
                new JObject { ["apply_id"] = last.Id, ["plan_id"] = p.Id, ["target_key"] = p.TargetKey, ["changes"] = DeltaRows(p.Deltas) });
        }
        internal static JObject Rollback(string applyId)
        {
            Ready();
            if (last == null || last.Id != applyId) throw Denied("UNKNOWN_APPLY", "Only the exact last package-owned change may be restored.");
            if (last.Restored) return Ok("Already restored; no write replayed.", false, false, new JObject { ["apply_id"] = last.Id });
            ValidateSource(last.Renderer);
            Gate.Demand(TargetKey(last.Renderer), MeshKey(last.Renderer), last.Deltas.Select(d => d.Name), EditCapability.Apply, Gate.LeaseId);
            CheckLast();
            Gate.ConsumeWrite();
            return RestoreLast();
        }
        internal static JObject RollbackLocally()
        {
            Ready();
            if (!ManagedWindow.IsLocalWindowOpen) throw Denied("LOCAL_OPERATOR_REQUIRED", "Use the local operator window.");
            CheckLast();
            // Deliberately available after revocation only as an explicit local click.
            DeltaPolicy.ValidateCurrent(last.Deltas, ReadWeights(last.Renderer, last.Deltas.Select(d => d.Name)), true);
            return RestoreLast();
        }
        private static void CheckLast()
        {
            if (last == null || last.Restored) throw Denied("NO_RESTORABLE_CHANGE", "No unrestored managed change remains.");
            ValidateSource(last.Renderer);
            if (TargetKey(last.Renderer) != last.TargetKey || MeshKey(last.Renderer) != last.MeshKey) throw Denied("STALE_TARGET", "The original source/mesh changed; refusing rollback.");
            DeltaPolicy.ValidateCurrent(last.Deltas, ReadWeights(last.Renderer, last.Deltas.Select(d => d.Name)), true);
        }
        private static JObject RestoreLast()
        {
            WriteTransaction(last.Renderer, last.Deltas, true);
            last.Restored = true;
            pending = null;
            FacePreview.Clear();
            return Ok("Restored original values on unchanged package-owned fields only. Scene NOT saved.", true, true,
                new JObject { ["apply_id"] = last.Id, ["restored"] = true });
        }
        private static void WriteTransaction(SkinnedMeshRenderer renderer, IReadOnlyList<ShapeDelta> deltas, bool reverse)
        {
            // Entire batch validated before recording Undo. No fuzzy matching or clear-all reset.
            var original = ReadWeights(renderer, deltas.Select(d => d.Name));
            int group;
            Undo.IncrementCurrentGroup();
            group = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(reverse ? "VRChat Agent: restore BlendShapes" : "VRChat Agent: apply BlendShapes");
            Undo.RegisterCompleteObjectUndo(renderer, reverse ? "Restore BlendShapes" : "Apply BlendShapes");
            try
            {
                foreach (ShapeDelta delta in deltas)
                    renderer.SetBlendShapeWeight(renderer.sharedMesh.GetBlendShapeIndex(delta.Name), reverse ? delta.Before : delta.After);
                // Compare the entire affected projection, not a tool's success flag.
                var actual = ReadWeights(renderer, deltas.Select(d => d.Name));
                foreach (ShapeDelta delta in deltas)
                    if (!actual[delta.Name].Equals(reverse ? delta.Before : delta.After)) throw new InvalidOperationException("Unity weight readback mismatch.");
                if (PrefabUtility.IsPartOfPrefabInstance(renderer)) PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
                EditorSceneManager.MarkSceneDirty(renderer.gameObject.scene);
                Undo.CollapseUndoOperations(group);
                SceneView.RepaintAll();
            }
            catch (Exception cause)
            {
                try
                {
                    Undo.RevertAllDownToGroup(group);
                    var restored = ReadWeights(renderer, original.Keys);
                    if (original.Any(pair => !restored[pair.Key].Equals(pair.Value))) throw new InvalidOperationException("Rollback readback mismatch.");
                }
                catch (Exception)
                {
                    Revoke();
                    throw new InvalidOperationException("Write failed and recovery is uncertain. Permissions closed. Inspect Unity and restore your checkpoint; do not retry.");
                }
                Revoke();
                throw new InvalidOperationException("Write failed; affected values restored and permissions closed. Cause: " + cause.GetType().Name);
            }
            finally { Undo.IncrementCurrentGroup(); }
        }
    }

    internal sealed class ManagedMeshAssetChanges : AssetPostprocessor
    {
        private static void OnPostprocessAllAssets(string[] importedAssets, string[] deletedAssets, string[] movedAssets, string[] movedFromAssetPaths)
        {
            if (importedAssets.Length + deletedAssets.Length + movedAssets.Length + movedFromAssetPaths.Length > 0)
                ManagedSession.AssetsChanged();
        }
    }
}
