using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatManagedEditing
{
    internal sealed class ManagedWindow : EditorWindow
    {
        internal static bool IsLocalWindowOpen { get; private set; }
        internal static bool TransportAcknowledged { get; private set; }
        internal static bool CheckpointAcknowledged { get; private set; }
        private SkinnedMeshRenderer selectedRenderer;
        private Mesh listedMesh;
        private string[] names = new string[0];
        private HashSet<string> selectedNames = new HashSet<string>(StringComparer.Ordinal);
        private Dictionary<string, int> nameCounts = new Dictionary<string, int>(StringComparer.Ordinal);
        private string filter = "", notice = "";
        private Vector2 scroll;
        private int page, seconds = 300, writes = 10;
        private bool allowPreview, allowApply, hadLease;
        private const int PageSize = 48;

        [MenuItem("Window/VRChat Agent/Managed Editing")]
        private static void Open() { GetWindow<ManagedWindow>("VRChat Managed Editing"); }
        private void OnEnable()
        {
            IsLocalWindowOpen = true;
            TransportAcknowledged = false; CheckpointAcknowledged = false;
            allowPreview = false; allowApply = false; hadLease = false;
            selectedRenderer = null; listedMesh = null; names = new string[0];
            selectedNames = new HashSet<string>(StringComparer.Ordinal);
            nameCounts = new Dictionary<string, int>(StringComparer.Ordinal);
            ManagedSession.Revoke(); minSize = new Vector2(470, 450);
        }
        private void OnDisable()
        {
            IsLocalWindowOpen = false;
            TransportAcknowledged = false; CheckpointAcknowledged = false;
            allowPreview = false; allowApply = false;
            ManagedSession.Revoke();
        }
        private void OnInspectorUpdate() { Repaint(); }
        private void Run(Action action)
        {
            try { action(); notice = "操作已完成；源场景不会自动保存。"; }
            catch (Exception e) { notice = "已停止：" + e.Message; }
        }
        private void ResetDraft()
        {
            ManagedSession.Revoke(); allowPreview = false; allowApply = false; CheckpointAcknowledged = false;
            selectedNames.Clear(); page = 0; hadLease = false;
        }
        internal static bool NamesMatch(Mesh mesh, IReadOnlyList<string> cached)
        {
            if (mesh == null) return cached.Count == 0;
            if (mesh.blendShapeCount > 10000 || mesh.blendShapeCount != cached.Count) return false;
            // The ordered snapshot is the signature: same reference/count is insufficient.
            for (int i = 0; i < cached.Count; i++)
                if (!string.Equals(mesh.GetBlendShapeName(i), cached[i], StringComparison.Ordinal)) return false;
            return true;
        }
        private void RefreshNames()
        {
            Mesh current = selectedRenderer == null ? null : selectedRenderer.sharedMesh;
            if (listedMesh == current && NamesMatch(current, names)) return;
            ResetDraft(); listedMesh = current; nameCounts.Clear();
            if (current == null || current.blendShapeCount > 10000) { names = new string[0]; return; }
            names = new string[current.blendShapeCount];
            for (int i = 0; i < names.Length; i++)
            {
                string name = current.GetBlendShapeName(i); names[i] = name;
                nameCounts[name] = nameCounts.TryGetValue(name, out int count) ? count + 1 : 1;
            }
        }
        private void OnGUI()
        {
            bool active = ManagedSession.Gate.Active;
            if (hadLease && !active) { allowPreview = false; allowApply = false; CheckpointAcknowledged = false; }
            hadLease = active;
            EditorGUILayout.LabelField("受控捏脸 · 候选版 / Managed BlendShape Editing", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox("默认无权修改。授权只在本窗口内临时生效；关闭、重载、换场景或到期会锁定。Apply只改场景实例，不自动保存。", MessageType.Info);
            EditorGUILayout.LabelField(active ? "已授权 / ACTIVE — " + ManagedSession.Gate.RemainingSeconds.ToString("F0") + "s，剩余写入 " + ManagedSession.Gate.RemainingWrites : "已锁定 / CLOSED", EditorStyles.boldLabel);
            if (GUILayout.Button("立即锁定并关闭隔离预览 / Revoke"))
            {
                Run(() => ManagedSession.Revoke()); allowPreview = false; allowApply = false; CheckpointAcknowledged = false; active = false; hadLease = false;
            }
            scroll = EditorGUILayout.BeginScrollView(scroll);
            using (new EditorGUI.DisabledScope(active))
            {
                EditorGUI.BeginChangeCheck();
                var chosen = (SkinnedMeshRenderer)EditorGUILayout.ObjectField("明确源 Renderer", selectedRenderer, typeof(SkinnedMeshRenderer), true);
                if (EditorGUI.EndChangeCheck()) { ResetDraft(); selectedRenderer = chosen; listedMesh = null; }
                RefreshNames();
                filter = EditorGUILayout.TextField("形态名称筛选", filter);
                int[] visible = Enumerable.Range(0, names.Length).Where(i => names[i].IndexOf(filter, StringComparison.OrdinalIgnoreCase) >= 0).ToArray();
                page = Mathf.Clamp(page, 0, Math.Max(0, (visible.Length - 1) / PageSize));
                EditorGUILayout.LabelField("已明确勾选 " + selectedNames.Count + "/128；匹配 " + visible.Length + " 项");
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button("上一页")) page = Mathf.Max(0, page - 1);
                EditorGUILayout.LabelField("第 " + (page + 1) + " 页", GUILayout.Width(90));
                if (GUILayout.Button("下一页")) page = Math.Min(Math.Max(0, (visible.Length - 1) / PageSize), page + 1);
                EditorGUILayout.EndHorizontal();
                foreach (int i in visible.Skip(page * PageSize).Take(PageSize))
                {
                    string name = names[i]; bool valid = !string.IsNullOrWhiteSpace(name) && nameCounts[name] == 1;
                    using (new EditorGUI.DisabledScope(!valid))
                    {
                        bool old = selectedNames.Contains(name);
                        string suffix = valid && selectedRenderer != null ? "   [" + selectedRenderer.GetBlendShapeWeight(i).ToString("G6") + "]" : " [名称重复/不可授权]";
                        bool next = EditorGUILayout.ToggleLeft(name + suffix, old);
                        if (next && !old)
                        {
                            if (selectedNames.Count >= 128) notice = "一次最多授权128个精确名称，请缩小范围。";
                            else selectedNames.Add(name);
                        }
                        else if (!next && old) selectedNames.Remove(name);
                    }
                }
                if (selectedNames.Count > 0) EditorGUILayout.HelpBox("完整范围（包含被筛选隐藏的项）：\n" + string.Join("\n", selectedNames.OrderBy(x => x, StringComparer.Ordinal)), MessageType.None);
                allowPreview = EditorGUILayout.ToggleLeft("允许隔离预览 / Preview（不修改源Renderer）", allowPreview);
                allowApply = EditorGUILayout.ToggleLeft("允许应用及精确恢复 / Apply（会修改源Renderer）", allowApply);
                seconds = EditorGUILayout.IntSlider("授权秒数", seconds, 1, 900);
                writes = EditorGUILayout.IntSlider("源写事务额度", writes, 1, 100);
                TransportAcknowledged = EditorGUILayout.ToggleLeft("本人已确认只转发受限入口，原始MCP直通隧道已关闭", TransportAcknowledged);
                CheckpointAcknowledged = EditorGUILayout.ToggleLeft("本人已保存场景并建立可回滚备份（插件不会自动备份）", CheckpointAcknowledged);
                EditorGUILayout.HelpBox("上方是本人的确认，不是插件自动验证。没有受限入口时，原MCP的脚本/组件写工具仍可绕过开关。", MessageType.Warning);
                using (new EditorGUI.DisabledScope(selectedRenderer == null || selectedNames.Count == 0 || (!allowPreview && !allowApply) || !TransportAcknowledged || (allowApply && !CheckpointAcknowledged)))
                {
                    if (GUILayout.Button("由本人开启这一范围 / Grant locally"))
                    {
                        string target = selectedRenderer == null ? "(none)" : selectedRenderer.name;
                        if (EditorUtility.DisplayDialog("临时授权确认", target + "\n精确形态数：" + selectedNames.Count + "\nPreview=" + allowPreview + "，Apply=" + allowApply + "\n" + seconds + "秒，最多" + writes + "次源写入。\n请核对上方完整范围；不会自动保存或上传。", "开启", "取消"))
                            Run(() => { ManagedSession.GrantLocally(selectedRenderer, selectedNames.ToArray(), allowPreview, allowApply, seconds, writes); hadLease = true; });
                    }
                }
            }
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("最近方案", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(ManagedSession.CurrentPlanSummary, MessageType.None);
            using (new EditorGUI.DisabledScope(!ManagedSession.Gate.Active || string.IsNullOrEmpty(ManagedSession.PendingPlanId)))
            {
                if (GUILayout.Button("预览此方案")) Run(() => ManagedSession.Preview(ManagedSession.PendingPlanId, false));
                if (GUILayout.Button("应用此方案到源Renderer"))
                    if (EditorUtility.DisplayDialog("应用已列出的方案", ManagedSession.CurrentPlanSummary + "\n\n本操作将修改源Renderer，仍会检查Apply权限。", "应用", "取消"))
                        Run(() => ManagedSession.Apply(ManagedSession.PendingPlanId));
            }
            if (ManagedSession.PreviewIsCurrent())
            {
                FacePreview.Yaw = EditorGUILayout.Slider("镜头左右角度", FacePreview.Yaw, -180, 180);
                FacePreview.Pitch = EditorGUILayout.Slider("镜头俯仰", FacePreview.Pitch, -85, 85);
                FacePreview.Zoom = EditorGUILayout.Slider("镜头放大", FacePreview.Zoom, 0.1f, 10);
                FacePreview.Focus = EditorGUILayout.Vector3Field("镜头焦点（仅预览）", FacePreview.Focus);
                EditorGUILayout.LabelField("原始 / Before                                      方案 / After");
                Rect space = GUILayoutUtility.GetRect(100, 240, GUILayout.ExpandWidth(true));
                try
                {
                    float half = (space.width - 8) * 0.5f;
                    FacePreview.Draw(new Rect(space.x, space.y, half, space.height), false);
                    FacePreview.Draw(new Rect(space.x + half + 8, space.y, half, space.height), true);
                }
                catch (Exception e) { notice = "预览停止：" + e.Message; ManagedSession.Revoke(); }
            }
            if (!string.IsNullOrEmpty(ManagedSession.LastApplyId))
            {
                EditorGUILayout.HelpBox("最后一笔受控源修改：\n" + ManagedSession.LastApplySummary, MessageType.Info);
                if (GUILayout.Button("本人恢复上次修改（无需重新授权；冲突时拒绝）"))
                    if (EditorUtility.DisplayDialog("恢复明确的上一笔修改", ManagedSession.LastApplySummary + "\n\n只恢复上面列出的目标；不覆盖后来的人工修改。", "恢复", "取消"))
                        Run(() => ManagedSession.RollbackLocally());
            }
            if (!string.IsNullOrEmpty(notice)) EditorGUILayout.HelpBox(notice, MessageType.Info);
            EditorGUILayout.EndScrollView();
        }
    }
}
