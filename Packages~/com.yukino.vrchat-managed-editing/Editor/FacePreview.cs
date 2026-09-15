using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Yukino.VRChatManagedEditing
{
    // Only owned temporary objects are mutated; the source renderer/mesh/materials are read-only.
    internal static class FacePreview
    {
        private const int CaptureSize = 384;
        private const int MaxVertices = 500000, MaxIndices = 3000000, MaxMaterials = 32;
        private const long MaxBlendShapeVertexSamples = 128000000;
        private static PreviewRenderUtility preview;
        private static Mesh beforeMesh, afterMesh;
        private static Material[] materials;
        internal static string PlanId { get; private set; }
        internal static string SourceState { get; private set; }
        internal static bool Ready => preview != null && beforeMesh != null && afterMesh != null;
        internal static float Yaw = 180, Pitch = 0, Zoom = 1;
        internal static Vector3 Focus;
        private static float radius = 1;

        internal static void Build(SkinnedMeshRenderer source, IReadOnlyList<ShapeDelta> deltas, string planId, string sourceState)
        {
            Clear();
            if (string.IsNullOrEmpty(planId) || string.IsNullOrEmpty(sourceState)) throw new ArgumentException("Preview must be bound to a plan and source snapshot.");
            if (source == null || source.sharedMesh == null || deltas == null || deltas.Count == 0) throw new ArgumentException("Preview source and exact deltas are required.");
            Mesh mesh = source.sharedMesh;
            if (mesh.vertexCount <= 0 || mesh.vertexCount > MaxVertices || mesh.subMeshCount > MaxMaterials ||
                (long)mesh.vertexCount * mesh.blendShapeCount > MaxBlendShapeVertexSamples) throw new ArgumentException("Preview geometry budget exceeded.");
            ulong indices = 0;
            for (int i = 0; i < mesh.subMeshCount; i++) indices += mesh.GetIndexCount(i);
            if (indices > MaxIndices || source.bones.Length > 1024) throw new ArgumentException("Preview indices/bones budget exceeded.");
            Material[] sharedMaterials = source.sharedMaterials;
            if (sharedMaterials.Length == 0 || sharedMaterials.Length > MaxMaterials || sharedMaterials.Length < mesh.subMeshCount || sharedMaterials.Any(m => m == null))
                throw new ArgumentException("Preview requires valid bounded material slots for every submesh.");
            Matrix4x4 approximated = Matrix4x4.TRS(source.transform.position, source.transform.rotation, source.transform.lossyScale);
            Matrix4x4 actualTransform = source.transform.localToWorldMatrix;
            for (int i = 0; i < 16; i++)
                if (float.IsNaN(actualTransform[i]) || float.IsInfinity(actualTransform[i]) || Mathf.Abs(approximated[i] - actualTransform[i]) > 0.0001f)
                    throw new ArgumentException("Sheared/non-TRS renderer hierarchy is unsupported by this preview; no source was changed.");
            var current = new Dictionary<string, float>(StringComparer.Ordinal);
            foreach (ShapeDelta delta in deltas)
            {
                int index = mesh.GetBlendShapeIndex(delta.Name);
                if (index < 0 || current.ContainsKey(delta.Name)) throw new ArgumentException("Preview requires unique exact existing shape names.");
                current.Add(delta.Name, source.GetBlendShapeWeight(index));
            }
            DeltaPolicy.ValidateCurrent(deltas, current);
            GameObject temporary = null;
            try
            {
                preview = new PreviewRenderUtility();
                temporary = new GameObject("VRChat Agent - isolated renderer") { hideFlags = HideFlags.HideAndDontSave };
                preview.AddSingleGO(temporary);
                temporary.transform.SetPositionAndRotation(source.transform.position, source.transform.rotation);
                temporary.transform.localScale = source.transform.lossyScale;
                var tempRenderer = temporary.AddComponent<SkinnedMeshRenderer>();
                tempRenderer.hideFlags = HideFlags.HideAndDontSave;
                tempRenderer.sharedMesh = mesh;
                tempRenderer.bones = source.bones;
                tempRenderer.rootBone = source.rootBone;
                tempRenderer.quality = source.quality;
                tempRenderer.localBounds = source.localBounds;
                tempRenderer.updateWhenOffscreen = true;
                for (int i = 0; i < mesh.blendShapeCount; i++)
                {
                    float weight = source.GetBlendShapeWeight(i);
                    if (float.IsNaN(weight) || float.IsInfinity(weight)) throw new ArgumentException("Source contains a non-finite BlendShape weight.");
                    tempRenderer.SetBlendShapeWeight(i, weight);
                }
                beforeMesh = new Mesh { name = "Managed preview before", hideFlags = HideFlags.HideAndDontSave };
                afterMesh = new Mesh { name = "Managed preview after", hideFlags = HideFlags.HideAndDontSave };
                tempRenderer.BakeMesh(beforeMesh, false);
                foreach (ShapeDelta delta in deltas) tempRenderer.SetBlendShapeWeight(mesh.GetBlendShapeIndex(delta.Name), delta.After);
                tempRenderer.BakeMesh(afterMesh, false);
                beforeMesh.RecalculateBounds(); afterMesh.RecalculateBounds();
                materials = new Material[sharedMaterials.Length];
                for (int i = 0; i < materials.Length; i++) materials[i] = new Material(sharedMaterials[i]) { hideFlags = HideFlags.HideAndDontSave };
                Focus = beforeMesh.bounds.center;
                radius = Mathf.Max(0.03f, beforeMesh.bounds.extents.magnitude);
                Animator animator = source.GetComponentInParent<Animator>();
                Transform head = animator != null && animator.isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
                if (head != null) { Focus = source.transform.InverseTransformPoint(head.position); radius = Mathf.Max(0.03f, radius * 0.15f); }
                Yaw = 180; Pitch = 0; Zoom = 1;
                preview.camera.fieldOfView = 30;
                preview.camera.clearFlags = CameraClearFlags.Color;
                preview.camera.backgroundColor = new Color(0.13f, 0.14f, 0.16f, 1);
                preview.ambientColor = new Color(0.55f, 0.55f, 0.55f, 1);
                preview.lights[0].intensity = 1.1f;
                preview.lights[0].transform.rotation = Quaternion.Euler(35, 35, 0);
                preview.lights[1].intensity = 0.7f;
                preview.lights[1].transform.rotation = Quaternion.Euler(340, 215, 0);
                PlanId = planId; SourceState = sourceState;
            }
            catch { Clear(); throw; }
            finally { if (temporary != null) Object.DestroyImmediate(temporary); }
        }

        private static Texture Render(Rect area, bool after)
        {
            if (!Ready) throw new InvalidOperationException("No isolated preview exists.");
            float dpi = Mathf.Max(1, EditorGUIUtility.pixelsPerPoint);
            // Bound GPU render targets even if the user stretches the Editor window.
            var rect = new Rect(0, 0, Mathf.Clamp(area.width, 16, 512 / dpi), Mathf.Clamp(area.height, 16, 512 / dpi));
            preview.BeginPreview(rect, GUIStyle.none);
            try
            {
                preview.camera.aspect = rect.width / rect.height;
                preview.camera.nearClipPlane = Mathf.Max(0.001f, radius * 0.01f);
                preview.camera.farClipPlane = Mathf.Max(10, radius * 40);
                preview.camera.transform.position = Focus + Quaternion.Euler(Pitch, Yaw, 0) * Vector3.forward * radius * 3.8f / Mathf.Clamp(Zoom, 0.1f, 10);
                preview.camera.transform.LookAt(Focus);
                Mesh mesh = after ? afterMesh : beforeMesh;
                for (int i = 0; i < mesh.subMeshCount; i++) preview.DrawMesh(mesh, Matrix4x4.identity, materials[i], i);
                preview.Render(false, false);
            }
            catch { preview.EndPreview(); throw; }
            return preview.EndPreview();
        }
        internal static void Draw(Rect area, bool after)
        {
            if (!Ready) { EditorGUI.HelpBox(area, "暂无预览 / No preview", MessageType.Info); return; }
            if (Event.current.type != EventType.Repaint) return;
            Texture texture = Render(area, after);
            GUI.DrawTexture(area, texture, ScaleMode.ScaleToFit, false);
        }
        internal static byte[] Capture(bool after)
        {
            RenderTexture previousActive = RenderTexture.active;
            RenderTexture readback = null;
            Texture2D pixels = null;
            try
            {
                float logicalSize = CaptureSize / Mathf.Max(1, EditorGUIUtility.pixelsPerPoint);
                Texture rendered = Render(new Rect(0, 0, logicalSize, logicalSize), after);
                readback = RenderTexture.GetTemporary(CaptureSize, CaptureSize, 0, RenderTextureFormat.ARGB32);
                Graphics.Blit(rendered, readback);
                RenderTexture.active = readback;
                pixels = new Texture2D(CaptureSize, CaptureSize, TextureFormat.RGBA32, false) { hideFlags = HideFlags.HideAndDontSave };
                pixels.ReadPixels(new Rect(0, 0, CaptureSize, CaptureSize), 0, 0); pixels.Apply(false, false);
                return pixels.EncodeToPNG();
            }
            finally
            {
                RenderTexture.active = previousActive;
                if (readback != null) RenderTexture.ReleaseTemporary(readback);
                if (pixels != null) Object.DestroyImmediate(pixels);
            }
        }
        private static void DestroyOwned(Object value) { if (value != null) Object.DestroyImmediate(value); }
        internal static void Clear()
        {
            PreviewRenderUtility oldPreview = preview; Mesh oldBefore = beforeMesh, oldAfter = afterMesh;
            Material[] oldMaterials = materials;
            preview = null; beforeMesh = null; afterMesh = null; materials = null;
            PlanId = null; SourceState = null;
            try { if (oldPreview != null) oldPreview.Cleanup(); }
            finally
            {
                try { DestroyOwned(oldBefore); }
                finally
                {
                    try { DestroyOwned(oldAfter); }
                    finally { if (oldMaterials != null) foreach (Material material in oldMaterials) DestroyOwned(material); }
                }
            }
        }
    }
}
