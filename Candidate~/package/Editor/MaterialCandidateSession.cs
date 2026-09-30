#if UNITY_EDITOR
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
namespace Yukino.VRChatAgent
{
    [InitializeOnLoad]
    internal static class MaterialCandidateSession
    {
        internal static readonly MaterialCandidateGate Gate=new MaterialCandidateGate(
            ()=>EditorApplication.timeSinceStartup,CoplayProjectIdentity.GetProjectHash,CandidateSession.LiveConnection,new UnityMaterialCandidateBackend());
        static MaterialCandidateSession()
        {
            EditorApplication.update+=Gate.Observe;
            EditorApplication.quitting+=Revoke;
            AssemblyReloadEvents.beforeAssemblyReload+=Revoke;
            EditorApplication.playModeStateChanged+=_=>Revoke();
        }
        static void Revoke()=>Gate.StopAll("编辑器生命周期已撤权，不回退");
        internal static void Draw()
        {
            EditorGUILayout.Space();EditorGUILayout.LabelField("候选材质修改",Gate.LastReason);
            EditorGUILayout.HelpBox("文件级Shader参数调整；原件不动。引用宿主需列入清单。未知资产回调/非Assets依赖拒绝。只保存候选材质；场景由本人保存。撤权不撤回。",MessageType.Warning);
            Capability("copy","复制具体材质候选（原生 manage_asset/duplicate）");
            Capability("edit","候选内自由Shader参数/既有贴图引用（manage_material/set_material_shader_property）");
            Capability("reference","明确宿主与槽位切换（manage_material/assign_material_to_renderer）");
            foreach(JObject plan in Gate.LocalPlans())
            {
                EditorGUILayout.LabelField("认证主体 / MCP会话",(string)plan["client_id"]);EditorGUILayout.LabelField("任务",(string)plan["task_id"]);
                EditorGUILayout.LabelField("材质清单ID",(string)plan["plan_id"]);EditorGUILayout.LabelField("材质清单摘要",(string)plan["digest"]);
                EditorGUILayout.LabelField("材质完整清单",plan["manifest"].ToString());
                EditorGUI.BeginDisabledGroup((bool)plan["approved"]);
                if(GUILayout.Button("批准此材质清单"))Gate.Approve((string)plan["plan_id"],(string)plan["digest"]);
                EditorGUI.EndDisabledGroup();
            }
            foreach(JObject row in Gate.LocalTransactions())
            {
                var tx=row["transaction"];EditorGUILayout.LabelField("修改报告",tx.ToString());
                EditorGUILayout.HelpBox("撤回仅作用于此步骤直接改动，先核postimage。复制产生的候选保留，不自动删除；按反向步骤撤回。重载后本轮内存撤回记录不保留。",MessageType.Info);
                EditorGUI.BeginDisabledGroup((bool)row["withdrawn"] || (string)tx["action"]=="copy");
                if(GUILayout.Button("明确撤回此步骤 "+(string)tx["id"]))Gate.Withdraw((string)tx["id"]);
                EditorGUI.EndDisabledGroup();
            }
        }
        static void Capability(string operation,string chinese)
        {bool current=Gate.Allows(operation);bool next=EditorGUILayout.ToggleLeft(chinese,current);if(next!=current)Gate.SetCapability(operation,next);}
    }
    // Not an alias of vrchat_agent_dispatch; runtime must explicitly gate this route.
    // No global discovery or dispatch; compatibility calls always fail closed.
    public static class VrchatAgentMaterialDispatch
    {
        public static object HandleCommand(JObject parameters)
        {
            return new ErrorResponse("owned_connection_required");
        }
    }
}
#endif
