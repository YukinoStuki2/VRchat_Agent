// Run ONLY in a disposable Unity 2022.3 test project, not the avatar authoring scene.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Yukino.VRChatManagedEditing.Tests
{
    public sealed class ManagedSmokeTests
    {
        [Test]
        public void ErrorReply_ReportsRevocationAndUnknownSourceMutation()
        {
            try
            {
                ManagedSession.Gate.Grant("fixture", "mesh", new[] { "eye" }, EditCapability.Apply, 30);
                var reply = (JObject)ManagedReply.Run(() => {
                    ManagedSession.Revoke();
                    throw new InvalidOperationException("Write failed; permissions closed.");
                });
                Assert.False((bool)reply["success"]);
                Assert.True((bool)reply["data"]["permission_changed"]);
                Assert.False((bool)reply["data"]["active"]);
                Assert.AreEqual(JTokenType.Null, reply["data"]["mutated"].Type);
            }
            finally { ManagedSession.Revoke(); }
        }

        [Test]
        public void ArgumentErrorWithoutRevocation_ReportsUnchangedActivePermission()
        {
            try
            {
                ManagedSession.Gate.Grant("fixture", "mesh", new[] { "eye" }, EditCapability.Preview, 30);
                var reply = (JObject)ManagedReply.Run(() => { throw new ArgumentException("Invalid input."); });
                Assert.False((bool)reply["data"]["permission_changed"]);
                Assert.True((bool)reply["data"]["active"]);
                Assert.False((bool)reply["data"]["mutated"]);
            }
            finally { ManagedSession.Revoke(); }
        }

        [Test]
        public void ShapeCache_SameMeshAndCountRejectRenamesAndReordering()
        {
            var mesh = new Mesh();
            var delta = new Vector3[3];
            try
            {
                mesh.vertices = new[] { Vector3.zero, Vector3.right, Vector3.up };
                mesh.AddBlendShapeFrame("eye", 100, delta, delta, delta);
                mesh.AddBlendShapeFrame("mouth", 100, delta, delta, delta);
                var names = new[] { "eye", "mouth" };
                Assert.True(ManagedWindow.NamesMatch(mesh, names));
                mesh.ClearBlendShapes();
                mesh.AddBlendShapeFrame("mouth", 100, delta, delta, delta);
                mesh.AddBlendShapeFrame("eye", 100, delta, delta, delta);
                Assert.False(ManagedWindow.NamesMatch(mesh, names));
                Assert.True(ManagedWindow.NamesMatch(mesh, new[] { "mouth", "eye" }));
                mesh.ClearBlendShapes();
                mesh.AddBlendShapeFrame("Eye", 100, delta, delta, delta);
                mesh.AddBlendShapeFrame("mouth", 100, delta, delta, delta);
                Assert.False(ManagedWindow.NamesMatch(mesh, names));
            }
            finally { UnityEngine.Object.DestroyImmediate(mesh); }
        }

        [Test]
        public void MeshBoundary_RejectsTransientAndGeneratedNativeAssets()
        {
            var mesh = new Mesh { name = "ManagedEditing-Untracked" };
            string path = "Assets/ManagedEditing-Test-" + Guid.NewGuid().ToString("N") + ".asset";
            try
            {
                Assert.AreEqual("UNTRACKED_MESH", Assert.Throws<GateDeniedException>(() => ManagedSession.ValidateMeshAsset(mesh)).Code);
                mesh.vertices = new[] { Vector3.zero, Vector3.right, Vector3.up };
                AssetDatabase.CreateAsset(mesh, path);
                AssetDatabase.SaveAssets();
                Assert.AreEqual("UNTRACKED_MESH", Assert.Throws<GateDeniedException>(() => ManagedSession.ValidateMeshAsset(mesh)).Code);
                // Same instance/count and changed geometry must never become a supported source.
                mesh.vertices = new[] { Vector3.forward, Vector3.right, Vector3.up };
                Assert.Throws<GateDeniedException>(() => ManagedSession.ValidateMeshAsset(mesh));
            }
            finally
            {
                AssetDatabase.DeleteAsset(path);
                if (mesh != null && !EditorUtility.IsPersistent(mesh)) UnityEngine.Object.DestroyImmediate(mesh);
                ManagedSession.Revoke();
            }
        }

        [Test]
        public void AssetImportNotification_ClosesExistingLease()
        {
            try
            {
                ManagedSession.Gate.Grant("fixture", "mesh", new[] { "eye" }, EditCapability.Preview, 30);
                ManagedSession.AssetsChanged();
                Assert.False(ManagedSession.Gate.Active);
                Assert.AreEqual("", ManagedSession.PendingPlanId);
                Assert.False(FacePreview.Ready);
            }
            finally { ManagedSession.Revoke(); }
        }

        [Test]
        public void SwitchingLoadedActiveScenes_RevokesOldLease()
        {
            Scene original = SceneManager.GetActiveScene();
            Scene a = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            Scene b = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            try
            {
                Assert.True(SceneManager.SetActiveScene(a));
                ManagedSession.Gate.Grant("fixture", "mesh", new[] { "eye" }, EditCapability.Apply, 30);
                string lease = ManagedSession.Gate.LeaseId;
                Assert.True(SceneManager.SetActiveScene(b));
                Assert.False(ManagedSession.Gate.Active);
                Assert.Throws<GateDeniedException>(() => ManagedSession.Gate.Demand("fixture", "mesh", new[] { "eye" }, EditCapability.Apply, lease));
                Assert.False((bool)((JObject)VrchatMeApply.HandleCommand(new JObject { ["plan_id"] = Guid.NewGuid().ToString("N") }))["success"]);
            }
            finally
            {
                ManagedSession.Revoke();
                SceneManager.SetActiveScene(original);
                EditorSceneManager.CloseScene(b, true); EditorSceneManager.CloseScene(a, true);
            }
        }

        [Test]
        public void NewAuthoringScene_RevokesButPreviewSceneDoesNot()
        {
            Scene original = SceneManager.GetActiveScene();
            Scene created = default, preview = default;
            try
            {
                ManagedSession.Gate.Grant("fixture", "mesh", new[] { "eye" }, EditCapability.Preview, 30);
                preview = EditorSceneManager.NewPreviewScene();
                Assert.True(ManagedSession.Gate.Active);
                EditorSceneManager.ClosePreviewScene(preview); preview = default;
                Assert.True(ManagedSession.Gate.Active);
                created = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
                Assert.False(ManagedSession.Gate.Active);
            }
            finally
            {
                ManagedSession.Revoke();
                if (preview.IsValid()) EditorSceneManager.ClosePreviewScene(preview);
                SceneManager.SetActiveScene(original);
                if (created.IsValid()) EditorSceneManager.CloseScene(created, true);
            }
        }

        [Test]
        public void RemoteSurfaceCannotGrant_UnknownApplyLeavesGateClosed()
        {
            ManagedSession.Revoke();
            JObject r = (JObject)VrchatMeApply.HandleCommand(new JObject { ["plan_id"] = Guid.NewGuid().ToString("N") });
            Assert.False((bool)r["success"]);
            Assert.False(ManagedSession.Gate.Active);
        }

        [Test]
        public void ExpiredLease_DoesNotReviveWhenClockMovesBack()
        {
            double time = 10;
            var gate = new GatePolicy(() => time);
            gate.Grant("fixture", "mesh", new[] { "eye" }, EditCapability.Preview | EditCapability.Apply, 3);
            string lease = gate.LeaseId;
            time = 13;
            Assert.Throws<GateDeniedException>(() => gate.Demand("fixture", "mesh", new[] { "eye" }, EditCapability.Apply, lease));
            time = 11;
            Assert.False(gate.Active);
        }

        [Test]
        public void UnknownBatchName_RejectsWholePlanAndRetainsNonzeroBaseline()
        {
            var weights = new Dictionary<string, float> { ["mouth_default"] = 100, ["eye"] = 12 };
            Assert.Throws<GateDeniedException>(() => DeltaPolicy.ValidateChanges(weights,
                new[] { new ShapeEdit("eye", 40), new ShapeEdit("ey", 50) }));
            Assert.AreEqual(100, weights["mouth_default"]);
            Assert.AreEqual(12, weights["eye"]);
        }

        [Test]
        public void RollbackChecksAfterValues_RefusesManualEdits()
        {
            var deltas = new[] { new ShapeDelta("eye", 12, 40) };
            Assert.Throws<GateDeniedException>(() => DeltaPolicy.ValidateCurrent(deltas,
                new Dictionary<string, float> { ["eye"] = 41 }, true));
        }

        [Test]
        public void Preview_BakesOnlyOwnedObjects_LeavesSourceWeightAndMeshUntouched()
        {
            var go = new GameObject("ManagedEditing-Test-Only");
            var mesh = new Mesh { name = "ManagedEditing-Test-Mesh" };
            Material material = null;
            try
            {
                mesh.vertices = new[] { Vector3.zero, Vector3.right, Vector3.up };
                mesh.triangles = new[] { 0, 1, 2 };
                mesh.RecalculateNormals(); mesh.RecalculateBounds();
                mesh.AddBlendShapeFrame("eye", 100, new[] { Vector3.zero, Vector3.zero, Vector3.forward }, new Vector3[3], new Vector3[3]);
                var renderer = go.AddComponent<SkinnedMeshRenderer>();
                renderer.sharedMesh = mesh;
                var shader = Shader.Find("Standard") ?? Shader.Find("Unlit/Color");
                Assert.NotNull(shader, "Test project requires a basic built-in material shader.");
                material = new Material(shader); renderer.sharedMaterials = new[] { material };
                renderer.SetBlendShapeWeight(0, 12);
                string planId = Guid.NewGuid().ToString("N");
                FacePreview.Build(renderer, new[] { new ShapeDelta("eye", 12, 40) }, planId, "source-snapshot");
                Assert.True(FacePreview.Ready);
                Assert.AreEqual(planId, FacePreview.PlanId);
                Assert.AreEqual("source-snapshot", FacePreview.SourceState);
                Assert.AreEqual(12, renderer.GetBlendShapeWeight(0));
                Assert.AreSame(mesh, renderer.sharedMesh);
                Assert.AreSame(material, renderer.sharedMaterials[0]);
            }
            finally
            {
                FacePreview.Clear();
                UnityEngine.Object.DestroyImmediate(go);
                UnityEngine.Object.DestroyImmediate(mesh);
                if (material != null) UnityEngine.Object.DestroyImmediate(material);
            }
            Assert.False(FacePreview.Ready);
            Assert.IsNull(FacePreview.PlanId);
            Assert.IsNull(FacePreview.SourceState);
        }
    }
}
