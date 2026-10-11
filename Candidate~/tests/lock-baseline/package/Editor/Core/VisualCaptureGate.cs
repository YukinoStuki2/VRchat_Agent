using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Final Editor authority. Image bytes never enter a wire response before an
    // explicit local preview + confirmation. No remote approval or path reader.
    // The native capture/Unity UI are separate adapters, not simulated here.
    internal sealed class VisualCaptureGate
    {
        sealed class Plan
        {
            internal string Id, Digest, Project, Client, Connection, Task, Attempt, ImageHash;
            internal double Expires;
            internal JObject Context;
            internal byte[] Image;
            internal int Used, Width, Height;
            internal bool Approved, Previewed, Confirmed, Sent;
        }
        readonly Func<double> clock;
        readonly Func<string> project, connection;
        readonly Func<JObject> context;
        readonly Func<JObject,int,JObject> capture;
        readonly Action<string> saveLedger;
        readonly HashSet<string> consumed = new HashSet<string>(StringComparer.Ordinal);
        readonly object sync = new object();
        Plan plan;
        bool allowed, busy, ledgerInvalid;
        long generation;
        public string LastReason {get;private set;} = "视觉采集默认关闭；每张图须本地确认后外发";
        internal VisualCaptureGate(Func<double> clock,Func<string> project,Func<string> connection,
            Func<JObject> context,Func<JObject,int,JObject> capture,Func<string> loadLedger,Action<string> saveLedger)
        {
            this.clock=clock;this.project=project;this.connection=connection;
            this.context=context;this.capture=capture;this.saveLedger=saveLedger;
            try
            {
                string raw=loadLedger();
                if(raw!="")
                {
                    Need(raw!=null && raw.Length<=8192,"invalid_visual_ledger");
                    var rows=JArray.Parse(raw);Need(rows.Count<=64,"visual_task_capacity");
                    foreach(var row in rows){string key=Text(row);Need(key.Length==64 && key.All(c=>"0123456789abcdef".Contains(c)) && consumed.Add(key),"invalid_visual_ledger");}
                }
            }
            catch{ledgerInvalid=true;LastReason="视觉次数记录无效；保持关闭";}
        }
        sealed class Denied : Exception {internal Denied(string reason):base(reason){}}
        static void Need(bool ok,string reason){if(!ok)throw new Denied(reason);}
        static void Keys(JObject o,params string[] keys)=>Need(o!=null && o.Count==keys.Length && o.Properties().All(p=>keys.Contains(p.Name)),"unexpected_fields");
        static string Text(JToken t){Need(t?.Type==JTokenType.String,"invalid_string");string s=(string)t;Need(s.Length>0 && s.Length<=512 && s==s.Trim() && !s.Any(char.IsControl),"invalid_string");return s;}
        static string Hash(byte[] data){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(data)).Replace("-","").ToLowerInvariant();}
        static string Hash(string text)=>ProjectPluginTrust.Digest(text);
        static JObject Ok(JObject data)=>new JObject{["success"]=true,["data"]=data};
        static JObject Fail(string error)=>new JObject{["success"]=false,["error"]=error,["data"]=new JObject{["status"]="denied",["reason"]=error}};
        public bool Allowed {get{lock(sync)return allowed;}}
        public void SetCapability(bool value){lock(sync){allowed=value;if(!value)StopAll("视觉能力已撤销；PNG保留，不外发");}}
        public void StopAll(string reason){lock(sync){generation++;if(plan!=null)plan.Image=null;plan=null;LastReason=reason;}}
        public void Observe()
        {
            lock(sync)
            {
                if(plan==null)return;
                try{double now=clock();if(!allowed || !(now<plan.Expires) || project()!=plan.Project || connection()!=plan.Connection || string.IsNullOrEmpty(plan.Connection))StopAll("视觉绑定或期限失效；未发送图片不外发");}
                catch{StopAll("视觉绑定不可核验；不外发");}
            }
        }
        void Current(Plan p,bool approval=true)
        {
            Observe();Need(p!=null && ReferenceEquals(p,plan),"plan_not_current");
            Need(allowed && !ledgerInvalid,"visual_disabled");Need(!approval || p.Approved,"local_approval_required");
        }
        JObject Context()
        {
            var value=context();Need(value!=null && value.Count>0 && value.ToString(Formatting.None).Length<=8192,"visual_context_unavailable");
            return (JObject)value.DeepClone();
        }
        void Verify(Plan p,bool approval=true)
        {Current(p,approval);Need(JToken.DeepEquals(p.Context,Context()),"visual_context_changed");Current(p,approval);}
        JObject Receipt(Plan p,string status)=>new JObject{["status"]=status,["plan_id"]=p.Id,["attempt_id"]=p.Attempt??"",["attempts_used"]=p.Used,["read_only"]=false};
        public JArray LocalPlans()
        {
            lock(sync){Observe();return plan==null?new JArray():new JArray(new JObject{["plan_id"]=plan.Id,["digest"]=plan.Digest,["task_id"]=plan.Task,["client_id"]=plan.Client,["approved"]=plan.Approved,["context"]=plan.Context.DeepClone(),["attempts_used"]=plan.Used});}
        }
        public bool ApproveLocal(string id,string digest)
        {
            lock(sync)
            {
                if(busy || plan==null || plan.Id!=id || plan.Digest!=digest || plan.Approved)return false;
                try{Verify(plan,false);plan.Approved=true;LastReason="任务已批准；每张图仍须本地预览确认";return true;}
                catch{StopAll("任务核验失败；未批准");return false;}
            }
        }
        public JObject PreviewLocal()
        {
            lock(sync)
            {
                if(busy || plan?.Image==null || plan.Sent)return null;
                try
                {
                    var p=plan;Verify(p);p.Previewed=true;
                    return new JObject{["attempt_id"]=p.Attempt,["sha256"]=p.ImageHash,["imageBase64"]=Convert.ToBase64String(p.Image),["imageWidth"]=p.Width,["imageHeight"]=p.Height};
                }
                catch{StopAll("预览绑定失效；不外发");return null;}
            }
        }
        public bool ConfirmImageLocal(string attempt,string digest)
        {
            lock(sync)
            {
                if(busy || plan==null || !plan.Previewed || plan.Sent || plan.Confirmed || plan.Attempt!=attempt || plan.ImageHash!=digest)return false;
                try{Verify(plan);Need(plan.Image!=null && Hash(plan.Image)==digest,"image_changed");plan.Confirmed=true;LastReason="此张图片已本地确认；等待原任务领取";return true;}
                catch{StopAll("图片核验失败；不外发");return false;}
            }
        }
        static int UInt(byte[] b,int i)=>checked((int)(((uint)b[i]<<24)|((uint)b[i+1]<<16)|((uint)b[i+2]<<8)|b[i+3]));
        internal static byte[] Image(JObject image,out int width,out int height)
        {
            Keys(image,"imageBase64","imageWidth","imageHeight");
            Need(image["imageBase64"]?.Type==JTokenType.String && ((string)image["imageBase64"]).Length<=700000,"image_budget");
            byte[] bytes=Convert.FromBase64String((string)image["imageBase64"]);
            Need(bytes.Length>=45 && bytes.Length<=512*1024 && bytes.Take(8).SequenceEqual(new byte[]{137,80,78,71,13,10,26,10}) && UInt(bytes,8)==13 && bytes.Skip(12).Take(4).SequenceEqual(new byte[]{73,72,68,82}),"invalid_png_header");
            width=UInt(bytes,16);height=UInt(bytes,20);
            Need(width>0 && height>0 && width<=640 && height<=640 && image["imageWidth"]?.Type==JTokenType.Integer && image["imageHeight"]?.Type==JTokenType.Integer && (int)image["imageWidth"]==width && (int)image["imageHeight"]==height,"image_dimensions");
            return bytes; // Native adapter separately validates decode; no custom PNG decoder.
        }
        public JObject Dispatch(JObject request)
        {
            lock(sync)
            {
                if(busy)return Fail("execution_in_progress");busy=true;Plan active=null;
                try
                {
                    Need(request!=null && request.ToString(Formatting.None).Length<=8192,"request_budget");var r=(JObject)request.DeepClone();
                    Keys(r,"protocol","kind","project_id","connection_id","client_id","task_id","plan_id","body");
                    Need(r["protocol"]?.Type==JTokenType.Integer && (int)r["protocol"]==1,"unsupported_protocol");
                    Observe();string proj=Text(r["project_id"]), conn=Text(r["connection_id"]), client=Text(r["client_id"]),task=Text(r["task_id"]),kind=Text(r["kind"]);
                    Need(proj==project() && conn==connection(),"binding_changed");
                    var body=r["body"] as JObject;
                    if(kind=="prepare")
                    {
                        Need(plan==null || plan.Client==client,"visual_busy");Keys(body,"ttl_seconds");
                        Need(r["plan_id"]?.Type==JTokenType.String && (string)r["plan_id"]=="","unexpected_identity");
                        Need(allowed && !ledgerInvalid,"visual_disabled");
                        string key=Hash(new JArray(proj,task).ToString(Formatting.None));
                        Need(!consumed.Contains(key),"visual_task_consumed");Need(consumed.Count<64,"visual_task_capacity");
                        Need(body["ttl_seconds"]?.Type==JTokenType.Integer || body["ttl_seconds"]?.Type==JTokenType.Float,"invalid_ttl");
                        double ttl=(double)body["ttl_seconds"], now=clock();Need(ttl>0 && ttl<=900 && !double.IsInfinity(now) && !double.IsNaN(now) && now+ttl>now,"invalid_ttl");
                        StopAll("新视觉清单；尚未批准");long start=generation;
                        var p=new Plan{Id=Guid.NewGuid().ToString("N"),Project=proj,Connection=conn,Client=client,Task=task,Expires=now+ttl,Context=Context()};
                        Need(start==generation && proj==project() && conn==connection() && clock()<p.Expires,"prepare_cancelled");
                        p.Digest=Hash(new JObject{["id"]=p.Id,["project"]=proj,["connection"]=conn,["client"]=client,["task"]=task,["expires"]=p.Expires,["context"]=p.Context}.ToString(Formatting.None));plan=p;
                        return Ok(new JObject{["status"]="pending",["plan_id"]=p.Id,["digest"]=p.Digest});
                    }
                    Need(plan!=null && plan.Client==client && plan.Task==task && plan.Id==Text(r["plan_id"]),"plan_not_current");active=plan;
                    if(kind=="stop"){Keys(body);StopAll("任务停止；未发送图像丢弃，PNG保留");return Ok(new JObject{["status"]="stopped"});}
                    if(kind=="status"){Keys(body);Current(active,false);return Ok(Receipt(active,active.Sent?"sent":active.Image!=null?active.Confirmed?"confirmed":"awaiting_local_preview":active.Approved?"ready":"pending"));}
                    Verify(active);
                    if(kind=="capture")
                    {
                        Keys(body,"correction_reason");Need(body["correction_reason"]?.Type==JTokenType.String,"invalid_correction");
                        Need(active.Used<2,"visual_budget_exhausted");
                        if(active.Used==0)Need((string)body["correction_reason"]=="","invalid_correction");
                        else{Text(body["correction_reason"]);Need(active.Sent,"first_image_not_delivered");}
                        string key=Hash(new JArray(active.Project,active.Task).ToString(Formatting.None));
                        if(active.Used==0)
                        {
                            Need(consumed.Add(key),"visual_task_consumed");
                            try{saveLedger(new JArray(consumed.OrderBy(x=>x,StringComparer.Ordinal)).ToString(Formatting.None));}
                            catch{ledgerInvalid=true;throw new Denied("visual_ledger_write_failed");}
                        }
                        Verify(active);active.Used++;active.Attempt=Guid.NewGuid().ToString("N");
                        active.Image=null;active.Previewed=false;active.Confirmed=false;active.Sent=false;
                        var result=capture((JObject)active.Context.DeepClone(),active.Used);
                        Verify(active);active.Image=Image(result,out active.Width,out active.Height);active.ImageHash=Hash(active.Image);
                        LastReason="图片仅在本地；请预览并逐张确认外发";
                        return Ok(Receipt(active,"awaiting_local_preview"));
                    }
                    Need(kind=="collect","unknown_kind");Keys(body,"attempt_id");Need(Text(body["attempt_id"])==active.Attempt,"attempt_mismatch");
                    Need(!active.Sent && active.Image!=null,"image_not_available");
                    if(!active.Confirmed)return Ok(Receipt(active,"awaiting_local_preview"));
                    var data=Receipt(active,"image_confirmed");data["sha256"]=active.ImageHash;data["imageWidth"]=active.Width;data["imageHeight"]=active.Height;data["imageBase64"]=Convert.ToBase64String(active.Image);
                    active.Sent=true;active.Image=null;return Ok(data);
                }
                catch(Exception ex){if(active!=null && ReferenceEquals(active,plan))StopAll("视觉操作失败；停止，不重试或外发");return Fail(ex is Denied?ex.Message:"visual_operation_failed");}
                finally{busy=false;}
            }
        }
    }
}
