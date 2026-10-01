#if UNITY_EDITOR
using System.IO;
using Newtonsoft.Json;
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
            LoadTaskRecords(Gate);
            EditorApplication.update+=Gate.Observe;
            EditorApplication.quitting+=()=>{Revoke();SessionState.EraseString(RecordKey);};
            AssemblyReloadEvents.beforeAssemblyReload+=SaveTaskRecords;
            EditorApplication.playModeStateChanged+=_=>Revoke();
        }
        static string RecordKey=>"Yukino.VRChatAgent.material-tasks.v1."+CoplayProjectIdentity.GetProjectHash();
        // Unity SessionState survives a domain reload, not an Editor restart. It stores
        // only task metadata/postimages; never credentials, live grants or Undo objects.
        static void LoadTaskRecords(MaterialCandidateGate target)
        {
            string raw=SessionState.GetString(RecordKey,"");SessionState.EraseString(RecordKey);
            if(raw.Length==0)return;
            try
            {
                if(raw.Length>4*1024*1024)throw new InvalidDataException();
                using(var text=new StringReader(raw))using(var reader=new JsonTextReader(text){MaxDepth=16})
                {
                    var records=JArray.Load(reader,new JsonLoadSettings{DuplicatePropertyNameHandling=DuplicatePropertyNameHandling.Error});
                    if(reader.Read() || !target.ImportTaskRecords(records))throw new InvalidDataException();
                }
            }
            catch{target.StopAll("任务记录无效；未恢复任何授权");}
        }
        static void SaveTaskRecords()
        {
            Revoke();SessionState.EraseString(RecordKey);
            try{SessionState.SetString(RecordKey,Gate.ExportTaskRecords().ToString(Formatting.None));}
            catch{Gate.StopAll("任务记录未保存；授权已撤销");}
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
                bool recovery=plan["recovery_record_id"]?.Type==JTokenType.String;
                EditorGUI.BeginDisabledGroup((bool)plan["approved"] || recovery);
                if(GUILayout.Button("批准此材质清单"))Gate.Approve((string)plan["plan_id"],(string)plan["digest"]);
                EditorGUI.EndDisabledGroup();
                if(recovery)
                {
                    EditorGUILayout.HelpBox("历史记录只证明候选来源，不是权限。请核对上方新认证主体/会话及本任务范围；此按钮重新批准新绑定，不沿用旧授权、不重放旧步骤。证据变化拒绝恢复。",MessageType.Warning);
                    EditorGUILayout.LabelField("待核验任务记录",(string)plan["recovery_record_id"]);
                    foreach(JObject record in Gate.ExportTaskRecords())
                        if((string)record["record_id"]==(string)plan["recovery_record_id"])
                            EditorGUILayout.LabelField("记录的原认证主体 / 会话",(string)record["client_id"]);
                    if(GUILayout.Button("核验记录并重新批准此绑定 "+(string)plan["plan_id"]))
                        Gate.RecoverPending((string)plan["plan_id"],(string)plan["digest"],(string)plan["recovery_record_id"],(string)plan["recovery_digest"]);
                }
                EditorGUILayout.LabelField("暂停状态", (bool)plan["paused"] ? "已暂停；期限不延长" : "未暂停");
                EditorGUI.BeginDisabledGroup(!(bool)plan["approved"]);
                if ((bool)plan["paused"])
                {
                    if (GUILayout.Button("核验后继续原清单")) Gate.Resume((string)plan["plan_id"], (string)plan["digest"]);
                }
                else if (GUILayout.Button("暂停此清单（不回退）")) Gate.Pause((string)plan["plan_id"], (string)plan["digest"]);
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
