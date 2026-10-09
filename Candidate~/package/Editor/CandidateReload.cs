#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Compilation;
using MCPForUnity.Editor.Helpers;
namespace Yukino.VRChatAgent
{
    // Only a local, explicit compile button arms this one-shot. SessionState carries
    // routing metadata, never grants. Original owner supplies authenticated bytes.
    [InitializeOnLoad]
    internal static class CandidateReload
    {
        static string Key=>"Yukino.VRChatAgent.planned-reload.v1."+CoplayProjectIdentity.GetProjectHash();
        static JObject ticket;
        static JArray records,history;
        static double deadline,quietSince;
        static long generation;
        static bool busy,prepared,compilationSeen,waiting,windowVisible;
        internal static bool Pending=>busy||prepared||waiting;
        internal static bool PreserveHistory=>prepared&&compilationSeen&&ValidTime()&&!EditorApplication.isPlayingOrWillChangePlaymode;
        internal static string Status {get;private set;}="默认关闭；需本地批准一次编译";
        static CandidateReload()
        {
            EditorApplication.update+=Tick;
            CompilationPipeline.compilationStarted+=_=>{if(prepared)compilationSeen=true;else if(Pending)Cancel();};
            EditorApplication.quitting+=Cancel;
            EditorApplication.playModeStateChanged+=_=>Cancel();
            string raw=SessionState.GetString(Key,"");SessionState.EraseString(Key);
            if(raw.Length==0)return;
            try
            {
                var row=Parse(raw);
                if(row.Count!=3 || row["project"]?.Type!=JTokenType.String || (string)row["project"]!=CoplayProjectIdentity.GetProjectHash() || !(row["owner"] is JObject))throw new InvalidDataException();
                deadline=ReloadTransfer.Number(row["deadline"]);ticket=(JObject)row["owner"].DeepClone();
                if(!ValidTime() || deadline-EditorApplication.timeSinceStartup>60)throw new InvalidDataException();
                waiting=true;Status="等待编辑器安静后核验原owner；尚无任务权限";
            }
            catch{Clear();Status="续接记录无效；未启动或恢复权限";}
        }
        static JObject Parse(string raw)
        {
            if(System.Text.Encoding.UTF8.GetByteCount(raw)>4*1024*1024)throw new InvalidDataException();
            using(var text=new StringReader(raw))using(var reader=new JsonTextReader(text){MaxDepth=20})
            {var row=JObject.Load(reader,new JsonLoadSettings{DuplicatePropertyNameHandling=DuplicatePropertyNameHandling.Error});if(reader.Read())throw new InvalidDataException();return row;}
        }
        static bool ValidTime()=>!double.IsNaN(EditorApplication.timeSinceStartup)&&!double.IsInfinity(EditorApplication.timeSinceStartup)&&EditorApplication.timeSinceStartup<deadline;
        internal static void WindowVisible(bool value){windowVisible=value;if(!value)Cancel();}
        internal static void Clear()
        {
            generation++;SessionState.EraseString(Key);ticket=null;records=null;history=null;
            busy=prepared=compilationSeen=waiting=false;quietSince=0;
        }
        internal static void Cancel()
        {
            bool active=Pending;var route=ticket;Clear();
            if(!active)return;
            Status="本地停止/生命周期取消；不自动恢复，不回退文件";
            CandidateSession.Gate.StopAll(Status);MaterialCandidateSession.Gate.StopAll(Status);
            if(CandidateSession.LocalOwner==null && route!=null)
            {
                var owner=new EditorOwnerProcess();
                try
                {
                    owner.PrepareReloadCancellation(route,CoplayProjectIdentity.GetProjectHash(),CandidateSession.StopOwnedAsync);
                    if(!CandidateSession.AdoptReloadOwner(owner))throw new InvalidDataException();
                }
                catch{owner.Dispose();Status="续接已撤权；原owner清理未确认";return;}
            }
            _=CandidateSession.StopLocalOwnerAsync();
        }
        internal static async Task<bool> BeginAsync()
        {
            var owner=CandidateSession.LocalOwner;
            if(Pending || !windowVisible || owner==null || !owner.ReloadAvailable || !CandidateSession.LocalOwnerReady ||
                EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode)return false;
            long epoch=++generation;busy=true;deadline=EditorApplication.timeSinceStartup+60;
            try
            {
                string id=Guid.NewGuid().ToString("N");var transfers=new JArray();
                if(CandidateSession.Gate.LocalPlans().Count>0)
                {var row=CandidateSession.Gate.FreezeForReload(id,60);if(row==null)throw new InvalidDataException();transfers.Add(row);}
                if(MaterialCandidateSession.Gate.LocalPlans().Count>0)
                {var row=MaterialCandidateSession.Gate.FreezeForReload(id,60);if(row==null)throw new InvalidDataException();transfers.Add(row);}
                if(transfers.Count==0)throw new InvalidDataException();
                records=MaterialCandidateSession.Gate.ExportTaskRecords();history=MaterialCandidateSession.Gate.ExportTransactionHistory();
                deadline=transfers.Min(row=>ReloadTransfer.Number(row["deadline"]));
                double now=EditorApplication.timeSinceStartup;
                ticket=await owner.ArmReloadAsync(id,transfers.Select(row=>row.ToString(Formatting.None)).ToArray(),now,Math.Min(60,deadline-now));
                if(epoch!=generation || !ValidTime())throw new InvalidDataException();
                ticket=await owner.DetachReloadAsync();
                if(epoch!=generation || !ValidTime())throw new InvalidDataException();
                await CandidateSession.StopOwnedAsync();
                if(epoch!=generation || !ValidTime())throw new InvalidDataException();
                busy=false;prepared=true;Status="已冻结原清单，执行本地批准的一次编译；期限不延长";
                // No script write, refresh, menu dispatch or model-selected command.
                CompilationPipeline.RequestScriptCompilation();return true;
            }
            catch
            {
                Clear();CandidateSession.Gate.StopAll("编译续接失败，需本地重新批准");MaterialCandidateSession.Gate.StopAll("编译续接失败，候选保留");
                await CandidateSession.StopLocalOwnerAsync();Status="未完成交接；清理结果见连接状态";return false;
            }
        }
        internal static bool BeforeReload()
        {
            if(!PreserveHistory || ticket==null){Cancel();return false;}
            try
            {
                MaterialCandidateSession.SaveReloadHistory(records,history);
                var row=new JObject{["project"]=CoplayProjectIdentity.GetProjectHash(),["deadline"]=deadline,["owner"]=ticket.DeepClone()};
                SessionState.SetString(Key,row.ToString(Formatting.None));return true;
            }
            catch{Cancel();return false;}
        }
        static void Tick()
        {
            if(!Pending)return;
            if(!ValidTime() || EditorApplication.isPlayingOrWillChangePlaymode){Cancel();return;}
            if(!waiting || busy)return;
            if(!windowVisible || EditorApplication.isCompiling || EditorApplication.isUpdating){quietSince=0;return;}
            if(quietSince==0){quietSince=EditorApplication.timeSinceStartup;return;}
            if(EditorApplication.timeSinceStartup-quietSince<0.25)return;
            waiting=false;busy=true;_=RestoreAsync(generation);
        }
        static async Task RestoreAsync(long epoch)
        {
            var owner=new EditorOwnerProcess();
            try
            {
                if(!CandidateSession.AdoptReloadOwner(owner))throw new InvalidDataException();
                var local=ticket;var raw=await owner.ReattachAsync(local,CoplayProjectIdentity.GetProjectHash(),CandidateSession.ConnectOwnedAsync,CandidateSession.StopOwnedAsync);
                if(raw==null || epoch!=generation || !ValidTime() || !windowVisible)throw new InvalidDataException();
                string connection=CandidateSession.LiveConnection();var kinds=new System.Collections.Generic.HashSet<string>();var bindings=new JArray();
                foreach(JToken serialized in raw)
                {
                    var transfer=Parse((string)serialized);string kind=(string)transfer["gate"];
                    if(!kinds.Add(kind))throw new InvalidDataException();
                    if(kind=="read")
                    {
                        foreach(string cap in ((JArray)transfer["capabilities"]).Values<string>())
                        {var pair=cap.Split('/');if(pair.Length!=2)throw new InvalidDataException();CandidateSession.Gate.SetCapability(pair[0],pair[1],true);}
                        string binding=CandidateSession.Gate.StageReload(transfer,ReloadTransfer.Hash(transfer),connection);if(binding==null)throw new InvalidDataException();bindings.Add(binding);
                    }
                    else if(kind=="material")
                    {
                        foreach(string cap in ((JArray)transfer["capabilities"]).Values<string>())MaterialCandidateSession.Gate.SetCapability(cap,true);
                        string binding=MaterialCandidateSession.Gate.StageReload(transfer,ReloadTransfer.Hash(transfer),connection);if(binding==null)throw new InvalidDataException();bindings.Add(binding);
                    }
                    else throw new InvalidDataException();
                }
                if(epoch!=generation || !ValidTime() || connection!=CandidateSession.LiveConnection())throw new InvalidDataException();
                for(int i=0;i<raw.Count;i++)
                {
                    var transfer=Parse((string)raw[i]);bool committed=(string)transfer["gate"]=="read"
                        ?CandidateSession.Gate.CommitReload((string)local["handoff_id"],(string)bindings[i])
                        :MaterialCandidateSession.Gate.CommitReload((string)local["handoff_id"],(string)bindings[i]);
                    if(!committed)throw new InvalidDataException();
                }
                var ack=await owner.RequestReloadControlAsync(new JObject{["kind"]="commit",["handoff_id"]=(string)local["handoff_id"],["connection_id"]=connection,["bindings"]=bindings});
                if(epoch!=generation || !ValidTime() || !windowVisible || !owner.Ready || (string)ack["kind"]!="committed")throw new InvalidDataException();
                Clear();Status="原批准与期限已核验续接；未恢复旧撤回检查点";
                CandidateSession.ReloadStatus(Status);
            }
            catch
            {
                Clear();CandidateSession.Gate.StopAll("续接失败；未重放旧步骤");MaterialCandidateSession.Gate.StopAll("续接失败；候选保留，需本地重新批准");
                await CandidateSession.StopLocalOwnerAsync();owner.Dispose();Status="自动续接失败；未扩大范围或延长期限";
            }
        }
    }
}
#endif
