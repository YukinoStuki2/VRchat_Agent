using System;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Single existing C#/Shader file exception. Editor-thread policy, not a plugin
    // sandbox. A caller must supply locally accepted live plugin-context evidence.
    // No remote approve/restore/compile endpoint and no grant persistence.
    internal sealed class ScriptWriteGate
    {
        sealed class Plan
        {
            internal string Id,Digest,Project,Connection,Client,Task,Target,Context;
            internal double Expires;
            internal bool Approved;
            internal JObject Evidence,Manifest;
        }
        readonly Func<double> clock;
        readonly Func<string> project,connection,context;
        readonly ScriptFileStore store;
        Plan plan;
        bool enabled,compileEnabled,busy;
        long generation;
        double lastTime=double.NegativeInfinity;
        internal string LastReason {get;private set;}="单文件写入与导入/编译效果均默认关闭";
        internal ScriptWriteGate(Func<double> clock,Func<string> project,Func<string> connection,Func<string> context,ScriptFileStore store)
        {this.clock=clock;this.project=project;this.connection=connection;this.context=context;this.store=store;}
        static void Need(bool ok,string reason){if(!ok)throw new CandidateWriteDenied(reason);}
        static void Keys(JObject obj,params string[] keys)=>Need(obj!=null&&obj.Count==keys.Length&&obj.Properties().All(p=>keys.Contains(p.Name)),"unexpected_fields");
        static string Text(JToken token)
        {
            Need(token?.Type==JTokenType.String,"invalid_string");string value=(string)token;
            Need(value.Length>0&&value.Length<=512&&value==value.Trim()&&!value.Any(char.IsControl),"invalid_string");return value;
        }
        static bool Digest(string value)=>value!=null&&value.Length==64&&value.All(c=>"0123456789abcdef".Contains(c));
        static JObject Ok(JObject data)=>new JObject{["success"]=true,["data"]=data};
        static JObject Fail(string reason,JObject data=null)=>new JObject{["success"]=false,["error"]=reason,["data"]=data??new JObject{["status"]="denied"}};
        double Now()
        {
            double now=clock();Need(!double.IsNaN(now)&&!double.IsInfinity(now)&&now>=lastTime,"invalid_clock");lastTime=now;return now;
        }
        internal void StopAll(string reason){generation++;plan=null;LastReason=reason;}
        internal bool Enabled=>enabled;
        internal bool CompileEnabled=>compileEnabled;
        internal void SetCapability(bool value){enabled=value;if(!value)StopAll("单文件写入已撤权；不自动回退");}
        internal void SetCompileCapability(bool value){compileEnabled=value;if(!value)StopAll("导入/编译效果已撤权；不自动回退");}
        void Current(Plan expected,bool approved)
        {
            Need(expected!=null&&ReferenceEquals(plan,expected),"plan_not_current");long epoch=generation;
            Need(enabled&&compileEnabled,"capability_disabled");Need(!approved||expected.Approved,"local_approval_required");
            Need(Now()<expected.Expires&&expected.Project==project()&&expected.Connection==connection()&&expected.Connection.Length>0,"binding_or_expiry_changed");
            Need(expected.Context==context()&&epoch==generation&&ReferenceEquals(plan,expected),"plugin_context_changed");
        }
        void Verify(Plan expected)
        {Current(expected,false);Need(JToken.DeepEquals(store.Capture(expected.Target),expected.Evidence),"relevant_evidence_changed");Current(expected,false);}
        internal void Observe()
        {if(plan==null)return;try{Current(plan,false);}catch{StopAll("绑定、插件前提或期限失效；保留现场");}}
        internal JArray LocalPlans()
        {
            Observe();var p=plan;return p==null?new JArray():new JArray(new JObject{["plan_id"]=p.Id,["digest"]=p.Digest,
                ["project_id"]=p.Project,["connection_id"]=p.Connection,["client_id"]=p.Client,["task_id"]=p.Task,
                ["approved"]=p.Approved,["manifest"]=p.Manifest.DeepClone(),["evidence"]=p.Evidence.DeepClone()});
        }
        internal bool Approve(string id,string digest)
        {
            var p=plan;if(busy||p==null||p.Approved||p.Id!=id||p.Digest!=digest)return false;
            busy=true;try{Verify(p);Current(p,false);p.Approved=true;LastReason="本地已批准单文件例外及导入/编译效果";return true;}
            catch{StopAll("批准前证据变化；未授权");return false;}finally{busy=false;}
        }
        internal JArray LocalHistory()=>store.History();
        internal JObject Withdraw(string id)
        {
            if(busy)return Fail("execution_in_progress");busy=true;
            // Local UI only. Revocation does not imply permission for rollback.
            StopAll("本地明确撤回；原任务不恢复");long epoch=generation;
            try
            {
                string expectedProject=project(),expectedContext=context();
                Need(enabled&&compileEnabled&&Digest(expectedContext),"local_recovery_effect_consent_required");
                var receipt=store.Restore(id,()=>project()==expectedProject&&context()==expectedContext&&epoch==generation&&enabled&&compileEnabled);
                var data=Receipt(receipt);
                return (string)receipt["outcome"]=="restored"&&receipt["error"]?.Type==JTokenType.Null?Ok(data):Fail("recovery_preserved",data);
            }
            catch(Exception ex){return Fail(ex is CandidateWriteDenied?ex.Message:"recovery_state_unconfirmed");}
            finally{busy=false;}
        }
        static JObject Receipt(JObject receipt)=>new JObject{["transaction"]=receipt.DeepClone(),["scene_saved"]=false,
            ["compilation_verified"]=false,["automatic_import_possible"]=true,["callback_effects_path_bounded"]=false,
            ["all_mutations_observed"]=false};
        internal JObject Dispatch(JObject input)
        {
            bool stop=(string)input?["kind"]=="stop";if(busy&&!stop)return Fail("execution_in_progress");
            bool previousBusy=busy;busy=true;string client=null;Plan executing=null;
            try
            {
                Need(input!=null&&System.Text.Encoding.UTF8.GetByteCount(input.ToString(Formatting.None))<=1024*1024,"request_budget");
                var r=(JObject)input.DeepClone();Keys(r,"protocol","kind","project_id","connection_id","client_id","task_id","plan_id","body");
                Need(r["protocol"]?.Type==JTokenType.Integer&&(long)r["protocol"]==1,"unsupported_protocol");
                Need(Text(r["project_id"])==project()&&Text(r["connection_id"])==connection(),"binding_changed");
                client=Text(r["client_id"]);string task=Text(r["task_id"]),kind=Text(r["kind"]);var body=r["body"] as JObject;
                if(kind=="prepare")
                {
                    Observe();Need(plan==null||plan.Client==client,"project_write_busy");StopAll("新清单替代旧授权");
                    Keys(body,"target","ttl_seconds","effects");Need(r["plan_id"]?.Type==JTokenType.String&&(string)r["plan_id"]=="","unexpected_identity");
                    Need(enabled&&compileEnabled,"capability_disabled");string target=ScriptFileStore.Target(Text(body["target"]));
                    Need(JToken.DeepEquals(body["effects"],new JArray("source_import_compile_callbacks")),"explicit_compile_effect_required");
                    Need(body["ttl_seconds"]?.Type==JTokenType.Float||body["ttl_seconds"]?.Type==JTokenType.Integer,"invalid_ttl");
                    double ttl=(double)body["ttl_seconds"],now=Now();Need(!double.IsNaN(ttl)&&!double.IsInfinity(ttl)&&ttl>0&&ttl<=900&&now+ttl>now,"invalid_ttl");
                    long epoch=generation;string plugin=context();Need(Digest(plugin),"local_plugin_trust_required");
                    var p=new Plan{Id=Guid.NewGuid().ToString("N"),Client=client,Task=task,Project=project(),Connection=connection(),Target=target,
                        Context=plugin,Expires=now+ttl,Manifest=body,Evidence=store.Capture(target)};
                    Need(plugin==context()&&p.Project==project()&&p.Connection==connection()&&Now()<p.Expires&&epoch==generation&&enabled&&compileEnabled,"prepare_cancelled");
                    p.Digest=ProjectPluginTrust.Digest(new JObject{["id"]=p.Id,["project"]=p.Project,["connection"]=p.Connection,["client"]=client,
                        ["task"]=task,["expires_at"]=p.Expires,["manifest"]=body.DeepClone(),["context"]=plugin,["evidence"]=p.Evidence.DeepClone()}.ToString(Formatting.None));
                    plan=p;return Ok(new JObject{["status"]="pending",["plan_id"]=p.Id,["digest"]=p.Digest});
                }
                var active=plan;Need(active!=null&&active.Client==client&&active.Task==task&&Text(r["plan_id"])==active.Id,"plan_not_current");
                executing=active;
                if(kind=="stop"){Keys(body);StopAll("任务停止；保留直接修改和备份");return Ok(new JObject{["status"]="stopped"});}
                Need(kind=="execute","unknown_kind");Keys(body,"content");Need(body["content"]?.Type==JTokenType.String,"invalid_source_text");
                Current(active,true);Verify(active);Current(active,true);
                var receipt=store.Write(active.Target,active.Evidence,(string)body["content"],()=>{try{Current(active,true);return true;}catch{return false;}});
                var data=Receipt(receipt);
                if((string)receipt["outcome"]!="changed"||receipt["error"]?.Type!=JTokenType.Null)
                {StopAll("写入未确认完成；保留现场与备份，不自动回退");return Fail("write_preserved",data);}
                try
                {
                    Current(active,true);var observed=store.Capture(active.Target);Current(active,true);
                    Need((string)observed["sha256"]==(string)receipt["expected_after_sha256"]&&(string)observed["meta_sha256"]==(string)receipt["meta_sha256"],"postimage_conflict");
                    active.Evidence=observed;data["grant_active"]=true;return Ok(data);
                }
                catch{StopAll("写后已撤权或发生并发变化；保留实际回执");data["grant_active"]=false;return Fail("written_but_revalidation_failed",data);}
            }
            catch(Exception ex)
            {
                if(!stop&&executing!=null&&ReferenceEquals(plan,executing))StopAll("调用失败；原件现场与备份保留");
                return Fail(ex is CandidateWriteDenied?ex.Message:"local_validation_failed");
            }
            finally{busy=previousBusy;}
        }
    }
}
