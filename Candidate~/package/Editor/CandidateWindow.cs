using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgent
{
    public sealed class CandidateWindow : EditorWindow
    {
        Vector2 scroll;
        string python = ""; // Local window only; never persists credentials or client configuration.
        [MenuItem("Tools/VRChat Agent/候选权限与清单")]
        static void Open() { GetWindow<CandidateWindow>("候选权限与清单"); }
        void OnInspectorUpdate() { Repaint(); }
        void OnGUI()
        {
            var gate = CandidateSession.Gate;
            EditorGUILayout.HelpBox("开发候选，尚未完成实机验收。这里只控制本项目受控MCP入口，不限制本地终端。导入/打开窗口不会启动服务或批准任务。", MessageType.Warning);
            EditorGUILayout.LabelField("当前工程", CoplayProjectIdentity.GetProjectHash());
            EditorGUILayout.LabelField("本地连接", CandidateSession.LocalOwnerReady ? "门控已就绪，客户端另行绑定" : CandidateSession.LocalOwnerStatus);
            EditorGUI.BeginDisabledGroup(CandidateSession.HasLocalOwner);
            python = EditorGUILayout.TextField("本机Python 3.11绝对路径", python);
            if (GUILayout.Button("启动本地受控连接")) StartLocal();
            EditorGUI.EndDisabledGroup();
            EditorGUI.BeginDisabledGroup(!CandidateSession.HasLocalOwner);
            if (GUILayout.Button("停止连接并撤权（不回退）")) StopLocal();
            EditorGUI.EndDisabledGroup();
            Capability("材质信息读取", "manage_material", "get_material_info");
            Capability("控制器信息读取", "manage_animation", "controller_get_info");
            EditorGUILayout.HelpBox("旧v1入口保持只读。候选材质写走下方独立入口；删除、全量刷新/导入、场景保存、包操作、任意执行仍拒绝。", MessageType.Info);
            if (GUILayout.Button("撤销全部任务权限（不回退文件）"))
            {
                gate.StopAll("本地已撤销全部任务；不回退文件");
#if UNITY_EDITOR
                MaterialCandidateSession.Gate.StopAll("本地全部撤权；不回退文件");
#endif
            }
            EditorGUILayout.LabelField("状态", gate.LastReason);
            scroll = EditorGUILayout.BeginScrollView(scroll);
            JArray displayed = gate.LocalPlans();
            foreach (JObject plan in displayed)
            {
                EditorGUILayout.Space();
                EditorGUILayout.LabelField("客户端会话", (string)plan["client_id"]);
                EditorGUILayout.LabelField("连接", (string)plan["connection_id"]);
                EditorGUILayout.LabelField("任务", (string)plan["task_id"]);
                EditorGUILayout.LabelField("清单ID", (string)plan["plan_id"]);
                EditorGUILayout.LabelField("清单摘要", (string)plan["digest"]);
                EditorGUILayout.LabelField("剩余秒数", ((double)plan["seconds_left"]).ToString("F0"));
                foreach (JObject op in (JArray)plan["manifest"]["operations"])
                    EditorGUILayout.LabelField("操作", (string)op["command"] + " / " + (string)op["action"]);
                foreach (JToken target in (JArray)plan["manifest"]["targets"])
                    EditorGUILayout.LabelField("精确目标", (string)target);
                bool approved = (bool)plan["approved"];
                EditorGUILayout.LabelField("批准状态", approved ? "已批准" : "等待主人在本地核对");
                EditorGUI.BeginDisabledGroup(approved);
                if (GUILayout.Button("批准此清单"))
                    gate.Approve((string)plan["plan_id"], (string)plan["digest"]);
                EditorGUI.EndDisabledGroup();
            }
#if UNITY_EDITOR
            MaterialCandidateSession.Draw();
#endif
            EditorGUILayout.EndScrollView();
        }
        async void StartLocal()
        {
            try { await CandidateSession.StartLocalOwnerAsync(python); }
            catch { CandidateSession.Gate.StopAll("本地连接启动失败，未批准任务"); }
            Repaint();
        }
        async void StopLocal()
        {
            try { await CandidateSession.StopLocalOwnerAsync(); }
            catch { CandidateSession.Gate.StopAll("连接清理未确认"); }
            Repaint();
        }
        static void Capability(string chinese, string command, string action)
        {
            var gate = CandidateSession.Gate;
            bool current = gate.Allows(command, action);
            bool selected = EditorGUILayout.ToggleLeft(chinese + "  " + command + "/" + action, current);
            if (current != selected) gate.SetCapability(command, action, selected);
        }
    }
}
