"""Source-boundary checks only: these do NOT compile or execute Unity.

Run: python3 -m unittest discover -s Tests~ -p test_preview_ui.py -v
Unity behavior is covered separately by the supplied pending EditMode tests.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EDITOR = ROOT / "Packages~" / "com.yukino.vrchat-managed-editing" / "Editor"


class PreviewUiBoundaryTests(unittest.TestCase):
    def source(self, filename):
        path = EDITOR / filename
        self.assertTrue(path.is_file(), f"Missing implementation: {path.name}")
        return path.read_text(encoding="utf-8")

    def test_local_window_grants_are_ephemeral_and_explicit(self):
        text = self.source("ManagedWindow.cs")
        for forbidden in ("EditorPrefs", "SessionState", "McpForUnityTool", "AssetDatabase.Save", "SaveScene("):
            self.assertNotIn(forbidden, text)
        for required in ("CheckpointAcknowledged", "TransportAcknowledged", "OnDisable", "ManagedSession.Revoke()", "ManagedSession.GrantLocally(", "DisplayDialog", "LastApplySummary"):
            self.assertIn(required, text)
        self.assertIn("StringComparer.Ordinal", text)
        self.assertIn("128", text)

    def test_preview_is_bound_to_current_plan_and_source_snapshot(self):
        session = self.source("ManagedSession.cs")
        plan = session[session.index("internal static JObject Plan("):session.index("private static Pending RequirePlan(")]
        self.assertIn("FacePreview.Clear();", plan, "plan B must discard preview A")
        self.assertLess(plan.index("FacePreview.Clear();"), plan.index("pending = new Pending"))
        self.assertIn("FacePreview.Build(Target, p.Deltas, p.Id, p.WeightState)", session)
        self.assertIn("internal static bool PreviewIsCurrent()", session)
        bound = session[session.index("internal static bool PreviewIsCurrent()"):session.index("internal static JObject Preview(")]
        for term in ("FacePreview.PlanId", "FacePreview.SourceState", "pending.Id", "pending.WeightState", "RequirePlan(", "Gate.Demand(", "Revoke();"):
            self.assertIn(term, bound)
        self.assertIn("ManagedSession.PreviewIsCurrent()", self.source("ManagedWindow.cs"))
        status = session[session.index("internal static JObject Status()"):session.index("internal static JObject Plan(")]
        self.assertIn("bool previewReady = PreviewIsCurrent();", status)
        self.assertIn('["preview_ready"] = previewReady', status)
        self.assertLess(status.index("PreviewIsCurrent()"), status.index('["active"] = Gate.Active'))
        preview = self.source("FacePreview.cs")
        self.assertIn("PlanId = planId; SourceState = sourceState;", preview)
        clear = preview[preview.index("internal static void Clear()") :]
        self.assertIn("PlanId = null; SourceState = null;", clear)
        apply = session[session.index("internal static JObject Apply("):session.index("internal static JObject Rollback(")]
        self.assertIn("FacePreview.Clear();", apply)

    def test_stale_plan_and_preview_failure_close_and_clear_consistently(self):
        session = self.source("ManagedSession.cs")
        require = session[session.index("private static Pending RequirePlan("):session.index("internal static JObject Preview(")]
        self.assertRegex(require, r"catch\s*\{\s*Revoke\(\);\s*throw;")
        preview = session[session.index("internal static JObject Preview("):session.index("internal static JObject Apply(")]
        self.assertRegex(preview, r"try\s*\{[\s\S]+FacePreview.Build[\s\S]+FacePreview.Capture[\s\S]+catch\s*\{\s*Revoke\(\);\s*throw;")
        tick = session[session.index("private static void Tick()"):session.index("private static void Ready()")]
        self.assertIn("WeightState(Target)", tick)

    def test_shape_cache_compares_exact_ordered_names_not_only_mesh_and_count(self):
        text = self.source("ManagedWindow.cs")
        refresh = text[text.index("private void RefreshNames()"):text.index("private void OnGUI()")]
        self.assertIn("NamesMatch(current, names)", refresh)
        self.assertIn("internal static bool NamesMatch(", text)
        compare = text[text.index("internal static bool NamesMatch("):text.index("private void RefreshNames()")]
        self.assertIn("GetBlendShapeName(i)", compare)
        self.assertIn("cached[i]", compare)
        self.assertIn("StringComparison.Ordinal", compare)
        self.assertIn("10000", compare)
        self.assertLess(refresh.index("NamesMatch("), refresh.index("ResetDraft()"))
        self.assertIn("nameCounts.Clear();", refresh)

    def test_preview_mutation_is_owned_and_resources_are_released(self):
        text = self.source("FacePreview.cs")
        for forbidden in ("Object.Instantiate(", "PrefabUtility.InstantiatePrefab(",
                          "AssetDatabase.", "File.Write", "SaveScene(", "Undo."):
            self.assertNotIn(forbidden, text)
        self.assertNotRegex(text, r"source\.[\w.]+\s*=(?!=)")
        receivers = re.findall(r"(\w+)\.SetBlendShapeWeight\(", text)
        self.assertTrue(receivers, "Preview must bake real proposed weights")
        self.assertEqual(set(receivers), {"tempRenderer"})
        self.assertIn("new GameObject(", text)
        self.assertIn("HideFlags.HideAndDontSave", text)
        self.assertLess(text.index("preview.AddSingleGO(temporary)"),
                        text.index("temporary.AddComponent<SkinnedMeshRenderer>()"))
        self.assertIn("tempRenderer.bones = source.bones", text)
        self.assertIn("tempRenderer.rootBone = source.rootBone", text)
        self.assertIn("tempRenderer.BakeMesh(beforeMesh, false)", text)
        self.assertIn("tempRenderer.BakeMesh(afterMesh, false)", text)
        self.assertIn("new Material(sharedMaterials[i])", text)
        self.assertIn("preview.DrawMesh(", text)
        self.assertIn("preview.Render(false, false)", text)
        self.assertIn("Object.DestroyImmediate(temporary)", text)
        self.assertIn("oldPreview.Cleanup()", text)
        self.assertIn("DestroyOwned(oldBefore", text)
        self.assertIn("DestroyOwned(oldAfter", text)
        self.assertIn("DestroyOwned(material", text)
        self.assertIn("RenderTexture.ReleaseTemporary(readback)", text)
        self.assertIn("Object.DestroyImmediate(pixels)", text)
        self.assertRegex(text, r"finally\s*\{\s*RenderTexture.active = previousActive;")
        self.assertIn("pixels.EncodeToPNG()", text)
        self.assertIn("CaptureSize = 384", text)
        self.assertIn("EditorGUIUtility.pixelsPerPoint", text)
        self.assertIn("MaxVertices", text)
        self.assertIn("MaxIndices", text)
        self.assertIn("MaxMaterials", text)
        self.assertIn("MaxBlendShapeVertexSamples", text)
        self.assertIn("StringComparer.Ordinal", text)
        self.assertIn("source.transform.InverseTransformPoint(head.position)", text)


if __name__ == "__main__":
    unittest.main()
