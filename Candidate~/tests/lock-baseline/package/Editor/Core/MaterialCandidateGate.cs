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
            internal string Id, Digest, Project, Client, Connection, Task, RecoveryRecord, RecoveryDigest, ApprovalConnection, BindingDigest;
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
        bool reloadBlocked, reloadConsumed;
        JObject reloadTransfer;
        string reloadBinding;
        Plan reloadPlan;
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
        public void StopAll(string reason) { lock(sync){generation++;plan=null;reloadPlan=null;reloadTransfer=null;reloadBinding=null;reloadBlocked=false;reloadConsumed=true;LastReason=reason;} }
        public void Observe() { lock(sync){
            if(reloadPlan!=null && (!(clock()<(double)reloadTransfer["deadline"]) || project()!=reloadPlan.Project || connection()!=reloadPlan.Connection))StopAll("暂存后身份或期限变化；禁止恢复");
            if(plan!=null && (clock()>=plan.Expires || project()!=plan.Project || connection()!=plan.Connection || string.IsNullOrEmpty(connection())))StopAll("身份/期限变化，写权限撤销");} }
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
            lock(sync){Observe();return plan==null?new JArray():new JArray(new JObject{["plan_id"]=plan.Id,["digest"]=plan.Digest,["client_id"]=plan.Client,["task_id"]=plan.Task,["approved"]=plan.Approved,["paused"]=plan.Paused,["recovery_record_id"]=plan.RecoveryRecord,["recovery_digest"]=plan.RecoveryDigest,["connection_id"]=plan.Connection,["project_id"]=plan.Project,["seconds_left"]=Math.Max(0,plan.Expires-clock()),["approval_connection_id"]=plan.ApprovalConnection??plan.Connection,["binding_digest"]=plan.BindingDigest??plan.Digest,["manifest"]=plan.Manifest.DeepClone()});}
        }
        // Local task history is NOT an authorization or an undo checkpoint. No remote import/export.
        readonly Dictionary<string,JObject> taskRecords=new Dictionary<string,JObject>(StringComparer.Ordinal);
        public JArray ExportTaskRecords() { lock(sync)return new JArray(taskRecords.Values.Select(r=>r.DeepClone())); }
        static string RecordDigest(JObject record) { var copy=(JObject)record.DeepClone();copy.Remove("digest");return Hash(copy); }
        void Remember(Plan p,bool recoverable=true)
        {
            Need(taskRecords.ContainsKey(p.Id) || taskRecords.Count<128,"task_record_capacity");
            var record=new JObject{["record_id"]=p.Id,["project_id"]=p.Project,["client_id"]=p.Client,["task_id"]=p.Task,
                ["manifest"]=p.Manifest.DeepClone(),["evidence"]=p.Evidence.DeepClone(),["copied"]=p.Copied,["recoverable"]=recoverable};
            record["digest"]=RecordDigest(record);
            foreach(var prior in taskRecords.Values.Where(r=>(string)r["record_id"]!=p.Id && (string)r["project_id"]==p.Project && (string)r["task_id"]==p.Task && JToken.DeepEquals(r["manifest"]?["source"],p.Manifest["source"]) && JToken.DeepEquals(r["manifest"]?["candidate"],p.Manifest["candidate"])))
            {prior["recoverable"]=false;prior["digest"]=RecordDigest(prior);}
            taskRecords[p.Id]=record;
        }
        public bool ImportTaskRecords(JArray input)
        {
            lock(sync)
            {
                if(busy || plan!=null || journal.Count!=0 || taskRecords.Count!=0)return false;
                try
                {
                    Need(input!=null && input.Count<=128 && input.ToString(Formatting.None).Length<=4*1024*1024,"invalid_task_records");
                    var checkedRecords=new Dictionary<string,JObject>(StringComparer.Ordinal);
                    foreach(var token in input)
                    {
                        var r=token as JObject;Keys(r,"record_id","project_id","client_id","task_id","manifest","evidence","copied","recoverable","digest");
                        string id=Text(r["record_id"]);Need(Guid.TryParseExact(id,"N",out _) && Text(r["project_id"])==project(),"record_identity_mismatch");
                        Text(r["client_id"]);Text(r["task_id"]);Text(r["digest"]);
                        Need(r["copied"]?.Type==JTokenType.Boolean && r["recoverable"]?.Type==JTokenType.Boolean && r["manifest"] is JObject && r["evidence"] is JObject,"invalid_task_record");
                        Need((string)r["digest"]==RecordDigest(r) && r.ToString(Formatting.None).Length<=65536,"task_record_mismatch");
                        checkedRecords.Add(id,(JObject)r.DeepClone());
                    }
                    foreach(var pair in checkedRecords)taskRecords.Add(pair.Key,pair.Value);
                    return true;
                }
                catch{return false;}
            }
        }
        static bool SameRecoveryScope(JObject record,Plan p)
        {
            var previous=record["manifest"] as JObject;
            return (bool?)record["recoverable"]==true && (bool?)record["copied"]==true &&
                (string)record["project_id"]==p.Project && (string)record["task_id"]==p.Task && previous!=null &&
                JToken.DeepEquals(previous["source"],p.Manifest["source"]) && JToken.DeepEquals(previous["candidate"],p.Manifest["candidate"]) &&
                JToken.DeepEquals(previous["references"],p.Manifest["references"]) && previous["operations"] is JArray ops &&
                ((JArray)p.Manifest["operations"]).All(op=>(string)op!="copy" && ops.Any(old=>JToken.DeepEquals(old,op))) &&
                JToken.DeepEquals(record["evidence"],p.Evidence);
        }
        // A fresh, explicit local approval of the displayed NEW principal/session and scope.
        // No remote resume, identity inference, old expiry restoration or replay of commands.
        public bool RecoverPending(string id,string digest,string recordId,string recordDigest)
        {
            lock(sync)
            {
                var p=plan;
                if(busy || reloadBlocked || p==null || p.Approved || p.Id!=id || p.Digest!=digest || p.RecoveryRecord!=recordId || p.RecoveryDigest!=recordDigest)return false;
                busy=true;
                try
                {
                    Current(p,false);Verify(p);
                    Need(taskRecords.TryGetValue(recordId,out var record) && (string)record["digest"]==recordDigest && SameRecoveryScope(record,p),"recovery_record_changed");
                    Current(p,false);Remember(p);record["recoverable"]=false;record["digest"]=RecordDigest(record);
                    p.RecoveryRecord=null;p.RecoveryDigest=null;p.Approved=true;
                    LastReason="本地已重新批准新绑定；定点证据一致，旧授权未复用";return true;
                }
                catch{StopAll("恢复核验失败；保留现场，未授权");return false;}
                finally{busy=false;}
            }
        }
        public bool Approve(string id,string digest)
        {
            lock(sync){if(plan==null || plan.Id!=id || plan.Digest!=digest || plan.Paused || plan.RecoveryRecord!=null || busy || reloadBlocked)return false;try{var p=plan;Current(p,false);Verify(p);Remember(p);p.Approved=true;return true;}catch{StopAll("证据变化，重新批准");return false;}}
        }
        // Local-only continuation; keep exact plan/postimage and never renew expiry.
        public bool Pause(string id,string digest) => SetPaused(id,digest,true);
        public bool Resume(string id,string digest) => SetPaused(id,digest,false);
        bool SetPaused(string id,string digest,bool paused)
        {
            lock(sync)
            {
                Observe();var p=plan;
                if(busy || reloadBlocked || p==null || p.Id!=id || p.Digest!=digest || !p.Approved || p.Paused==paused)return false;
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
        // Pure local history: never inserted into the live journal/provenance path.
        readonly JArray archivedTransactions=new JArray();
        static JObject HistoryRow(Journal j) => new JObject{["transaction"]=j.Report.DeepClone(),
            ["project_id"]=j.Plan.Project,["client_id"]=j.Plan.Client,["connection_id"]=j.Plan.Connection,
            ["task_id"]=j.Plan.Task,["plan_id"]=j.Plan.Id,["manifest"]=j.Plan.Manifest.DeepClone(),["withdrawn"]=j.Withdrawn};
        public JArray ExportTransactionHistory()
        { lock(sync)return new JArray(archivedTransactions.Select(r=>r.DeepClone()).Concat(journal.Select(HistoryRow))); }
        public bool ImportTransactionHistory(JArray input)
        {
            lock(sync)
            {
                if(busy || plan!=null || journal.Count!=0 || archivedTransactions.Count!=0)return false;
                try
                {
                    Need(input!=null && input.Count<=128 && Encoding.UTF8.GetByteCount(input.ToString(Formatting.None))<=4*1024*1024,"invalid_transaction_history");
                    var accepted=new JArray();var ids=new HashSet<string>(StringComparer.Ordinal);
                    foreach(var token in input)
                    {
                        var row=token as JObject;Keys(row,"transaction","project_id","client_id","connection_id","task_id","plan_id","manifest","withdrawn");
                        Need(Text(row["project_id"])==project(),"history_project_mismatch");Text(row["client_id"]);Text(row["connection_id"]);Text(row["task_id"]);
                        Need(Guid.TryParseExact(Text(row["plan_id"]),"N",out _) && row["manifest"] is JObject && row["withdrawn"]?.Type==JTokenType.Boolean,"invalid_transaction_history");
                        var tx=row["transaction"] as JObject;Need(tx!=null,"invalid_transaction_history");
                        var names=new[]{"id","action","outcome","before","after","changed","side_effects","direct_target"};
                        Need(tx.Count==names.Length+(tx.ContainsKey("withdrawal")?1:0) && names.All(n=>tx.ContainsKey(n)),"invalid_transaction_history");
                        Need(Guid.TryParseExact(Text(tx["id"]),"N",out _) && ids.Add((string)tx["id"]),"duplicate_transaction");
                        Operation(tx["action"]);Text(tx["direct_target"]);
                        Need(new[]{"unknown","unchanged","changed"}.Contains((string)tx["outcome"]) && tx["before"] is JObject && (tx["after"] is JObject || tx["after"]?.Type==JTokenType.Null) && tx["changed"] is JArray && tx["side_effects"] is JArray,"invalid_transaction_history");
                        Need(!tx.ContainsKey("withdrawal") || tx["withdrawal"] is JObject,"invalid_transaction_history");
                        Need(!(bool)row["withdrawn"] || ((string)tx["action"]!="copy" && (string)tx["withdrawal"]?["direct_outcome"]=="withdrawn"),"invalid_withdrawal_history");
                        Need(Encoding.UTF8.GetByteCount(row.ToString(Formatting.None))<=65536,"transaction_history_too_large");
                        accepted.Add(row.DeepClone());
                    }
                    foreach(var row in accepted)archivedTransactions.Add(row.DeepClone());
                    return true;
                }
                catch{return false;}
            }
        }
        public JArray LocalTransactions()
        {
            lock(sync)
            {
                var result=ExportTransactionHistory();
                for(int i=0;i<result.Count;i++)
                {
                    var row=(JObject)result[i];bool checkpoint=i>=archivedTransactions.Count && journal[i-archivedTransactions.Count].Checkpoint!=null;
                    bool available=checkpoint && !(bool)row["withdrawn"] && (string)row["transaction"]["action"]!="copy";
                    row["checkpoint_available"]=checkpoint;row["withdrawal_available"]=available;
                    row["withdrawal_unavailable_reason"]=i<archivedTransactions.Count?"domain_reload_checkpoint_lost":available?"":(bool)row["withdrawn"]?"already_withdrawn":"created_candidate_retained";
                }
                return result;
            }
        }
        // Local-human action only. Stop/remote requests never call this method.
        public JObject Withdraw(string transactionId)
        {
            lock(sync)
            {
                if(busy)return Fail("execution_in_progress");busy=true;
                try
                {
                    Need(!archivedTransactions.Any(r=>(string)r["transaction"]?["id"]==transactionId),"checkpoint_unavailable_after_reload");
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
        // Only the authenticated local coordinator may move this memory payload.
        // SessionState/task history is inert and never calls these methods.
        internal JObject FreezeForReload(string handoffId,double window)
        {
            lock(sync)
            {
                if(busy || reloadBlocked)return null;busy=true;
                try
                {
                    Observe();ReloadTransfer.Window(handoffId,window,clock());var p=plan;
                    Need(p!=null && p.Approved && !p.Paused && p.RecoveryRecord==null,"reload_not_approved");
                    Current(p,true);Verify(p);Current(p,true);
                    var row=new JObject{["plan_id"]=p.Id,["approval_digest"]=p.Digest,["client_id"]=p.Client,["task_id"]=p.Task,
                        ["approval_connection_id"]=p.ApprovalConnection??p.Connection,["previous_binding_digest"]=p.BindingDigest??p.Digest,
                        ["expires_at"]=p.Expires,["manifest"]=p.Manifest.DeepClone(),["evidence"]=p.Evidence.DeepClone(),["copied"]=p.Copied,
                        ["history_digest"]=ReloadTransfer.Hash(ExportTransactionHistory()),["records_digest"]=ReloadTransfer.Hash(ExportTaskRecords())};
                    var transfer=ReloadTransfer.Create("material",handoffId,p.Project,p.Connection,Math.Min(clock()+window,p.Expires),capabilities,new JArray(row));
                    reloadTransfer=transfer;reloadBlocked=true;LastReason="材质任务冻结；不执行、不保存检查点授权";return (JObject)transfer.DeepClone();
                }
                catch{StopAll("冻结失败，候选保留；需本地重新批准");return null;}
                finally{busy=false;}
            }
        }
        internal string StageReload(JObject input,string expectedDigest,string newConnection)
        {
            lock(sync)
            {
                if(busy || reloadBlocked || reloadConsumed || plan!=null || journal.Count!=0)return null;
                reloadConsumed=true;busy=true;long start=generation;
                try
                {
                    var transfer=ReloadTransfer.Validate(input,expectedDigest,"material",project(),newConnection,connection(),clock());
                    var ceiling=(JArray)transfer["capabilities"];Need(ceiling.All(x=>capabilities.Contains((string)x)),"capability_disabled");
                    var rows=(JArray)transfer["plans"];Need(rows.Count==1,"invalid_reload_plans");var r=(JObject)rows[0];
                    Keys(r,"plan_id","approval_digest","client_id","task_id","approval_connection_id","previous_binding_digest","expires_at","manifest","evidence","copied","history_digest","records_digest");
                    Need(r["copied"]?.Type==JTokenType.Boolean && Text(r["history_digest"])==ReloadTransfer.Hash(ExportTransactionHistory()) && Text(r["records_digest"])==ReloadTransfer.Hash(ExportTaskRecords()),"reload_history_changed");
                    var p=new Plan{Id=Text(r["plan_id"]),Digest=Text(r["approval_digest"]),Client=Text(r["client_id"]),Task=Text(r["task_id"]),Project=project(),Connection=newConnection,
                        ApprovalConnection=Text(r["approval_connection_id"]),Expires=ReloadTransfer.Number(r["expires_at"]),Manifest=(JObject)r["manifest"].DeepClone(),Evidence=(JObject)r["evidence"].DeepClone(),Copied=(bool)r["copied"]};
                    Text(r["previous_binding_digest"]);Need(clock()<p.Expires && (double)transfer["deadline"]<=p.Expires,"reload_expired");
                    foreach(var op in (JArray)p.Manifest["operations"])Need(ceiling.Any(x=>(string)x==Operation(op)),"outside_capability_ceiling");
                    Need(JToken.DeepEquals(p.Evidence,Capture(p)),"relevant_evidence_changed");
                    Need(start==generation && project()==p.Project && connection()==p.Connection && clock()<(double)transfer["deadline"],"reload_changed");
                    p.BindingDigest=ReloadTransfer.Binding(transfer,newConnection);reloadPlan=p;reloadTransfer=transfer;reloadBinding=p.BindingDigest;reloadBlocked=true;
                    LastReason="材质重附证据通过；仍等待双端提交";return reloadBinding;
                }
                catch{StopAll("续接暂存失败；候选保留且未授权");return null;}
                finally{busy=false;}
            }
        }
        internal bool CommitReload(string handoffId,string bindingDigest)
        {
            lock(sync)
            {
                if(busy || reloadPlan==null || reloadTransfer==null || (string)reloadTransfer["handoff_id"]!=handoffId || reloadBinding!=bindingDigest)return false;
                busy=true;long start=generation;var p=reloadPlan;var transfer=reloadTransfer;
                try
                {
                    Need(project()==p.Project && connection()==p.Connection && clock()<p.Expires && clock()<(double)transfer["deadline"],"reload_changed");
                    foreach(var cap in (JArray)transfer["capabilities"])Need(capabilities.Contains((string)cap),"capability_disabled");
                    var r=transfer["plans"][0];Need((string)r["history_digest"]==ReloadTransfer.Hash(ExportTransactionHistory()) && (string)r["records_digest"]==ReloadTransfer.Hash(ExportTaskRecords()),"reload_history_changed");
                    Need(JToken.DeepEquals(p.Evidence,Capture(p)),"relevant_evidence_changed");
                    Need(start==generation && ReferenceEquals(p,reloadPlan) && project()==p.Project && connection()==p.Connection && clock()<(double)transfer["deadline"],"reload_cancelled");
                    Remember(p);p.Approved=true;plan=p;reloadPlan=null;reloadTransfer=null;reloadBinding=null;reloadBlocked=false;
                    LastReason="原材质批准/期限保留；新连接已提交，旧检查点不恢复";return true;
                }
                catch{StopAll("续接提交失败；候选保留且未授权");return false;}
                finally{busy=false;}
            }
        }
        public JObject Dispatch(JObject request)
        {
            lock(sync)
            {
                if(reloadBlocked && (string)request?["kind"]!="stop")return Fail("planned_reload_frozen");
                if(busy)return Fail("execution_in_progress");busy=true;bool stop=false;string requestingClient=null;
                try
                {
                    Need(request!=null && request.ToString(Formatting.None).Length<=65536,"request_too_large");var r=(JObject)request.DeepClone();
                    Keys(r,"protocol","kind","project_id","client_id","connection_id","task_id","plan_id","body");
                    stop=(string)r["kind"]=="stop";
                    Need(r["protocol"].Type==JTokenType.Integer && (int)r["protocol"]==1,"unsupported_protocol");
                    Observe();Need(Text(r["project_id"])==project() && Text(r["connection_id"])==connection(),"binding_changed");
                    var client=Text(r["client_id"]);requestingClient=client;var task=Text(r["task_id"]);var kind=Text(r["kind"]);var body=r["body"] as JObject;
                    if(kind=="stop" && reloadPlan!=null)
                    {
                        Keys(body);Need(reloadPlan.Client==client && reloadPlan.Task==task && reloadPlan.Id==(string)r["plan_id"],"plan_mismatch");
                        StopAll("精确任务停止已取消材质续接");return Ok(new JObject{["status"]="stopped"});
                    }
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
                            bool own=prior!=null && prior.Report["after"] is JObject && JToken.DeepEquals(prior.Report["after"]["asset:"+candidate],p.Evidence["asset:"+candidate]) && JToken.DeepEquals(prior.Report["after"]["asset:"+source],p.Evidence["asset:"+source]);
                            if(!own)
                            {
                                var matches=taskRecords.Values.Where(record=>SameRecoveryScope(record,p)).ToArray();
                                Need(matches.Length==1,"candidate_provenance_conflict");
                                p.RecoveryRecord=(string)matches[0]["record_id"];p.RecoveryDigest=(string)matches[0]["digest"];
                            }
                            p.Copied=true;
                        }
                        p.Digest=Hash(new JObject{["id"]=p.Id,["project"]=p.Project,["connection"]=p.Connection,["client"]=client,["task"]=task,["manifest"]=p.Manifest.DeepClone(),["evidence"]=p.Evidence.DeepClone()});plan=p;
                        var pending=new JObject{["status"]="pending",["plan_id"]=p.Id,["digest"]=p.Digest};
                        if(p.RecoveryRecord!=null)pending["recovery_record_id"]=p.RecoveryRecord;
                        return Ok(pending);
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
                    Need(journal.Count+archivedTransactions.Count<128,"journal_capacity");var before=Capture(active,command);var checkpoint=backend.Checkpoint(active.Manifest,command);
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
                    if(error!=null){Remember(active,false);StopAll("失败，保留现场，不自动回退");return Fail(error,data);}
                    active.Copied=true;active.Evidence=nextEvidence;Remember(active);return Ok(data);
                }
                catch(Exception ex){if(!stop && plan!=null && plan.Client==requestingClient)StopAll("失败，保留现场，不自动回退");return Fail(ex is Denied || ex is CandidateWriteDenied?ex.Message:"local_validation_failed");}
                finally{busy=false;}
            }
        }
    }
}
