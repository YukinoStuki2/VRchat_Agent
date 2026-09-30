using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Only locally generated fixed validation codes may cross the wire.
    public sealed class CandidateWriteDenied : InvalidOperationException
    { internal CandidateWriteDenied(string code):base(code){} }
    // The interface separates real editor state from explicit filesystem test fixtures.
    public interface IMaterialCandidateBackend
    {
        JObject Capture(JObject manifest, JObject command);
        object Checkpoint(JObject manifest, JObject command);
        JObject Apply(JObject manifest, JObject command);
        JObject Read(JObject manifest);
        void Restore(JObject manifest, JObject command, object checkpoint);
    }

    // Independent wire command: never widens CandidateGate's strict readonly v1 schema.
    public sealed class MaterialCandidateGate
    {
        sealed class Plan
        {
            internal string Id, Digest, Project, Client, Connection, Task;
            internal double Expires;
            internal bool Approved, Copied, Paused;
            internal JObject Manifest, Evidence;
        }
        readonly Func<double> clock;
        readonly Func<string> project, connection;
        readonly IMaterialCandidateBackend backend;
        readonly HashSet<string> capabilities = new HashSet<string>(StringComparer.Ordinal);
        readonly object sync = new object();
        sealed class Journal
        {
            internal Plan Plan;
            internal JObject Command, Report;
            internal object Checkpoint;
            internal bool Withdrawn;
        }
        readonly List<Journal> journal = new List<Journal>();
        Plan plan;
        bool busy;
        long generation;
        public string LastReason { get; private set; } = "候选写能力默认关闭";
        public MaterialCandidateGate(Func<double> clock, Func<string> project, Func<string> connection, IMaterialCandidateBackend backend)
        { this.clock=clock; this.project=project; this.connection=connection; this.backend=backend; }
        sealed class Denied : Exception { internal Denied(string reason):base(reason){} }
        static void Need(bool ok,string reason) { if(!ok) throw new Denied(reason); }
        static void Keys(JObject o, params string[] names) => Need(o!=null && o.Count==names.Length && o.Properties().All(p=>names.Contains(p.Name)),"unexpected_fields");
        static string Text(JToken t)
        { Need(t?.Type==JTokenType.String,"invalid_string");var s=(string)t;Need(s.Length>0 && s.Length<=512 && s==s.Trim() && !s.Any(char.IsControl),"invalid_string");return s; }
        public static string AssetPath(JToken t)
        {
            string s=Text(t);
            Need(s.StartsWith("Assets/",StringComparison.Ordinal) && s.IndexOfAny(new[]{'\\',':','*','?','\"','<','>','|'})<0 && s.Split('/').All(p=>p!="" && p!="." && p!=".." && p==p.Trim() && !p.EndsWith(".",StringComparison.Ordinal)),"invalid_path");
            return s;
        }
        static string Operation(JToken t) { var s=Text(t);Need(s=="copy" || s=="edit" || s=="reference", "unsupported_operation");return s; }
        static JObject Ok(JObject data)=>new JObject{["success"]=true,["data"]=data};
        static JObject Fail(string reason,JObject data=null)=>new JObject{["success"]=false,["error"]=reason,["data"]=data??new JObject{["reason"]=reason,["status"]="denied"}};
        public bool Allows(string operation) { lock(sync) return capabilities.Contains(operation); }
        public void SetCapability(string operation,bool allowed)
        { lock(sync){Operation(operation);if(allowed)capabilities.Add(operation);else{capabilities.Remove(operation);StopAll("本地能力已撤销，不回退");}} }
        public void StopAll(string reason) { lock(sync){generation++;plan=null;LastReason=reason;} }
        public void Observe() { lock(sync){if(plan!=null && (clock()>=plan.Expires || project()!=plan.Project || connection()!=plan.Connection || string.IsNullOrEmpty(connection())))StopAll("身份/期限变化，写权限撤销");} }
        void Current(Plan p,bool approved)
        {
            Observe();Need(ReferenceEquals(plan,p),"plan_not_current");Need(!approved || p.Approved,"local_approval_required");
            foreach(var op in (JArray)p.Manifest["operations"])Need(capabilities.Contains((string)op),"capability_disabled");
        }
        JObject Capture(Plan p,JObject cmd=null)
        { var s=backend.Capture((JObject)p.Manifest.DeepClone(),cmd==null?null:(JObject)cmd.DeepClone());Need(s!=null && s.Count>0,"evidence_unavailable");return (JObject)s.DeepClone(); }
        void Verify(Plan p) { Need(JToken.DeepEquals(p.Evidence,Capture(p)),"relevant_evidence_changed");Current(p,false); }
        static string Hash(JObject o) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(o.ToString(Formatting.None)))).Replace("-","").ToLowerInvariant(); }
        public JArray LocalPlans()
        {
            lock(sync){Observe();return plan==null?new JArray():new JArray(new JObject{["plan_id"]=plan.Id,["digest"]=plan.Digest,["client_id"]=plan.Client,["task_id"]=plan.Task,["approved"]=plan.Approved,["paused"]=plan.Paused,["manifest"]=plan.Manifest.DeepClone()});}
        }
        public bool Approve(string id,string digest)
        {
            lock(sync){if(plan==null || plan.Id!=id || plan.Digest!=digest || plan.Paused || busy)return false;try{var p=plan;Current(p,false);Verify(p);p.Approved=true;return true;}catch{StopAll("证据变化，重新批准");return false;}}
        }
        // Local-only continuation; keep exact plan/postimage and never renew expiry.
        public bool Pause(string id,string digest) => SetPaused(id,digest,true);
        public bool Resume(string id,string digest) => SetPaused(id,digest,false);
        bool SetPaused(string id,string digest,bool paused)
        {
            lock(sync)
            {
                Observe();var p=plan;
                if(busy || p==null || p.Id!=id || p.Digest!=digest || !p.Approved || p.Paused==paused)return false;
                busy=true;
                try
                {
                    Current(p,true);if(!paused)Verify(p);Current(p,true);p.Paused=paused;
                    LastReason=paused?"本地已暂停；保留候选及原清单期限":"定点证据复核通过；原材质任务继续";
                    return true;
                }
                catch{StopAll("继续核验失败，保留候选，撤销清单");return false;}
                finally{busy=false;}
            }
        }
        public JArray LocalTransactions() { lock(sync)return new JArray(journal.Select(j=>new JObject{["transaction"]=j.Report.DeepClone(),["task_id"]=j.Plan.Task,["manifest"]=j.Plan.Manifest.DeepClone(),["withdrawn"]=j.Withdrawn})); }
        // Local-human action only. Stop/remote requests never call this method.
        public JObject Withdraw(string transactionId)
        {
            lock(sync)
            {
                if(busy)return Fail("execution_in_progress");busy=true;
                try
                {
                    var j=journal.FirstOrDefault(x=>(string)x.Report["id"]==transactionId);
                    Need(j!=null && !j.Withdrawn,"transaction_not_current");
                    Need(j.Plan.Project==project(),"binding_changed");
                    Need((string)j.Command["action"]!="copy","created_candidate_retained");
                    string target=(string)j.Report["direct_target"];
                    var now=Capture(j.Plan,j.Command);
                    Need(j.Report["after"] is JObject && JToken.DeepEquals(now[target],j.Report["after"][target]),"postimage_conflict");
                    StopAll("本地明确撤回，原授权撤销");
                    string error=null;JObject after=null;
                    try{backend.Restore(j.Plan.Manifest,j.Command,j.Checkpoint);}catch{error="withdraw_state_unknown";}
                    try{after=Capture(j.Plan,j.Command);}catch{error="withdraw_state_unknown";}
                    bool restored=after!=null && JToken.DeepEquals(after[target],j.Report["before"][target]);
                    var side=after==null?new string[0]:now.Properties().Select(p=>p.Name).Union(after.Properties().Select(p=>p.Name)).Where(k=>k!=target && !JToken.DeepEquals(now[k],after[k])).ToArray();
                    if(after!=null && !restored)error="withdraw_readback_mismatch";
                    if(side.Length>0)error="withdraw_side_effect";
                    j.Withdrawn=restored;
                    var data=new JObject{["status"]=error==null?"withdrawn":"withdraw_paused",["transaction_id"]=transactionId,["direct_outcome"]=after==null?"unknown":restored?"withdrawn":"not_restored",["side_effects"]=new JArray(side),["before"]=now,["after"]=after,["candidate_retained"]=true,["scene_saved"]=false};
                    j.Report["withdrawal"]=data.DeepClone();LastReason=error??"此步骤直接改动已回读撤回；候选保留";
                    return error==null?Ok(data):Fail(error,data);
                }
                catch(Exception e){StopAll("撤回暂停，保留当前现场");return Fail(e is Denied || e is CandidateWriteDenied?e.Message:"withdraw_state_unknown");}
                finally{busy=false;}
            }
        }
        public JObject Dispatch(JObject request)
        {
            lock(sync)
            {
                if(busy)return Fail("execution_in_progress");busy=true;bool stop=false;string requestingClient=null;
                try
                {
                    Need(request!=null && request.ToString(Formatting.None).Length<=65536,"request_too_large");var r=(JObject)request.DeepClone();
                    Keys(r,"protocol","kind","project_id","client_id","connection_id","task_id","plan_id","body");
                    stop=(string)r["kind"]=="stop";
                    Need(r["protocol"].Type==JTokenType.Integer && (int)r["protocol"]==1,"unsupported_protocol");
                    Observe();Need(Text(r["project_id"])==project() && Text(r["connection_id"])==connection(),"binding_changed");
                    var client=Text(r["client_id"]);requestingClient=client;var task=Text(r["task_id"]);var kind=Text(r["kind"]);var body=r["body"] as JObject;
                    if(kind=="status")
                    {
                        Keys(body);Need(r["plan_id"].Type==JTokenType.String,"invalid_string");string id=(string)r["plan_id"];
                        var entries=journal.Where(j=>j.Plan.Client==client && j.Plan.Task==task && j.Plan.Project==project() && j.Plan.Connection==connection() && j.Plan.Id==id);
                        return Ok(new JObject{["grant_active"]=plan!=null && plan.Id==id && plan.Client==client && plan.Task==task && plan.Approved && !plan.Paused,["transactions"]=new JArray(entries.Select(j=>j.Report.DeepClone())),["capabilities"]=new JArray(capabilities)});
                    }
                    if(kind=="prepare")
                    {
                        Need(plan==null || plan.Client==client,"project_write_busy");StopAll("新清单替代旧授权");
                        Need((string)r["plan_id"]=="","unexpected_identity");Keys(body,"source","candidate","operations","references","ttl_seconds");
                        string source=AssetPath(body["source"]), candidate=AssetPath(body["candidate"]);
                        Need(source.EndsWith(".mat",StringComparison.Ordinal) && candidate.EndsWith(".mat",StringComparison.Ordinal) && !string.Equals(source,candidate,StringComparison.OrdinalIgnoreCase),"invalid_material_pair");
                        var ops=body["operations"] as JArray;var refs=body["references"] as JArray;
                        Need(ops!=null && ops.Count>0 && ops.Count<=3 && refs!=null && refs.Count<=32,"invalid_manifest");
                        var seen=new HashSet<string>();foreach(var op in ops)Need(seen.Add(Operation(op)) && capabilities.Contains((string)op),"capability_disabled");
                        // Existing candidates require our retained exact postimage provenance below.
                        Need((refs.Count>0)==seen.Contains("reference"),"reference_scope_required");
                        var hosts=new HashSet<string>();foreach(var host in refs){var h=host as JObject;Keys(h,"renderer","slot");Text(h["renderer"]);Need(h["slot"].Type==JTokenType.Integer && (int)h["slot"]>=0 && (int)h["slot"]<256 && hosts.Add(h.ToString(Formatting.None)),"invalid_reference");}
                        Need(body["ttl_seconds"].Type==JTokenType.Integer || body["ttl_seconds"].Type==JTokenType.Float,"invalid_ttl");
                        double ttl=(double)body["ttl_seconds"];Need(!double.IsNaN(ttl) && !double.IsInfinity(ttl) && ttl>0 && ttl<=900,"invalid_ttl");
                        var p=new Plan{Id=Guid.NewGuid().ToString("N"),Project=project(),Connection=connection(),Client=client,Task=task,Expires=clock()+ttl,Manifest=(JObject)body.DeepClone()};
                        long start=generation;p.Evidence=Capture(p);Need(start==generation && project()==p.Project && connection()==p.Connection && clock()<p.Expires,"prepare_cancelled");
                        if((string)p.Evidence["asset:"+candidate]=="absent")Need(seen.Contains("copy"),"copy_required");
                        else
                        {
                            Need(!seen.Contains("copy"),"candidate_exists");
                            var prior=journal.LastOrDefault(j=>j.Plan.Project==p.Project && j.Plan.Client==client && j.Plan.Task==task && (string)j.Plan.Manifest["source"]==source && (string)j.Plan.Manifest["candidate"]==candidate);
                            Need(prior!=null && prior.Report["after"] is JObject && JToken.DeepEquals(prior.Report["after"]["asset:"+candidate],p.Evidence["asset:"+candidate]) && JToken.DeepEquals(prior.Report["after"]["asset:"+source],p.Evidence["asset:"+source]),"candidate_provenance_conflict");
                            p.Copied=true;
                        }
                        p.Digest=Hash(new JObject{["id"]=p.Id,["project"]=p.Project,["connection"]=p.Connection,["client"]=client,["task"]=task,["manifest"]=p.Manifest.DeepClone(),["evidence"]=p.Evidence.DeepClone()});plan=p;
                        return Ok(new JObject{["status"]="pending",["plan_id"]=p.Id,["digest"]=p.Digest});
                    }
                    var active=plan;Need(active!=null && active.Client==client && active.Task==task,"plan_not_current");Need((string)r["plan_id"]==active.Id,"plan_mismatch");
                    if(kind=="stop"){Keys(body);StopAll("已停止，不回退");return Ok(new JObject{["status"]="stopped"});}
                    Need(kind=="execute","unknown_kind");Keys(body,"action","arguments");var action=Operation(body["action"]);var args=body["arguments"] as JObject;
                    Need(((JArray)active.Manifest["operations"]).Any(o=>(string)o==action),"outside_plan");
                    if(action=="copy"){Keys(args);Need(!active.Copied,"already_copied");}
                    else if(action=="reference"){Keys(args,"renderer","slot");Need(active.Copied,"copy_required");Need(((JArray)active.Manifest["references"]).Any(h=>JToken.DeepEquals(h,args)),"reference_not_approved");}
                    else{Keys(args,"property","value");Text(args["property"]);Need(active.Copied,"copy_required");}
                    var command=(JObject)args.DeepClone();command["action"]=action;Current(active,true);
                    if(active.Paused)return Fail("plan_paused",new JObject{["status"]="paused",["reason"]="plan_paused",["plan_id"]=active.Id});
                    Verify(active);Current(active,true);
                    Need(journal.Count<128,"journal_capacity");var before=Capture(active,command);var checkpoint=backend.Checkpoint(active.Manifest,command);
                    Need(JToken.DeepEquals(before,Capture(active,command)),"checkpoint_evidence_changed");Current(active,true);
                    string error=null;JObject after=null,readback=null,nextEvidence=null;
                    try{var result=backend.Apply(active.Manifest,command);if((bool?)result?["success"]!=true)error="native_write_failed";}
                    catch{error="native_write_failed";}
                    try{readback=backend.Read(active.Manifest);after=Capture(active,command);nextEvidence=Capture(active);}catch{error="readback_unknown";}
                    string direct=action=="reference"?"host:"+(string)command["renderer"]:"asset:"+(string)active.Manifest["candidate"];
                    var changes=after==null?new string[0]:before.Properties().Select(p=>p.Name).Union(after.Properties().Select(p=>p.Name)).Where(k=>!JToken.DeepEquals(before[k],after[k])).OrderBy(k=>k,StringComparer.Ordinal).ToArray();
                    var sideEffects=changes.Where(k=>k!=direct).ToArray();
                    if(sideEffects.Length>0)error="unexpected_side_effect";
                    var transaction=new JObject{["id"]=Guid.NewGuid().ToString("N"),["action"]=action,["outcome"]=after==null?"unknown":changes.Length==0?"unchanged":"changed",["before"]=before,["after"]=after,["changed"]=new JArray(changes),["side_effects"]=new JArray(sideEffects),["direct_target"]=direct};
                    journal.Add(new Journal{Plan=active,Command=(JObject)command.DeepClone(),Report=(JObject)transaction.DeepClone(),Checkpoint=checkpoint});
                    Observe();bool stillActive=ReferenceEquals(plan,active) && active.Approved;
                    var data=new JObject{["transaction"]=transaction,["readback"]=readback,["grant_active"]=stillActive && error==null,["status"]=error!=null?"failed_preserved":stillActive?"completed":"stopped_after_safe_point"};
                    if(error!=null){StopAll("失败，保留现场，不自动回退");return Fail(error,data);}
                    active.Copied=true;active.Evidence=nextEvidence;return Ok(data);
                }
                catch(Exception ex){if(!stop && plan!=null && plan.Client==requestingClient)StopAll("失败，保留现场，不自动回退");return Fail(ex is Denied || ex is CandidateWriteDenied?ex.Message:"local_validation_failed");}
                finally{busy=false;}
            }
        }
    }
}
