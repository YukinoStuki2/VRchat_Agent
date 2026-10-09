using System;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;

// Trusted local callers and domain replacement are fixtures. NOT authenticated
// owner reattachment, runtime ACK, real Editor/Mono or human approval evidence.
static class ReloadCases
{
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static object Local(object target,string name,params object[] args){var m=target.GetType().GetMethod(name,BindingFlags.Instance|BindingFlags.NonPublic);Check(m!=null,"missing_"+name);return m.Invoke(target,args);}
 static string Hash(JToken v){using var h=SHA256.Create();return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(v.ToString(Formatting.None)))).Replace("-","").ToLowerInvariant();}
 static JObject Request(string kind,JObject body=null,string plan="",string conn="connection-A",string client="client-A")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]=conn,["client_id"]=client,["task_id"]="task-A",["plan_id"]=plan,["body"]=body??new JObject()};
 static JObject Manifest()=>new JObject{["operations"]=new JArray(new JObject{["command"]="manage_material",["action"]="get_material_info"}),["targets"]=new JArray("Assets/source.mat"),["ttl_seconds"]=300};
 static JObject Read(CandidateGate g,JObject p,string conn="connection-A")=>g.Dispatch(Request("execute",new JObject{["command"]="manage_material",["params"]=new JObject{["action"]="get_material_info",["materialPath"]="Assets/source.mat"}},(string)p["plan_id"],conn));
 static JObject Prepare(CandidateGate g){g.SetCapability("manage_material","get_material_info",true);var p=(JObject)g.Dispatch(Request("prepare",Manifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"approve");return p;}
 static void ReadTransfer()
 {
  double now=100;int calls=0;var old=new CandidateGate(()=>now,()=>"project-A",()=>"connection-A",_=>"same",(_,__)=>{calls++;return new JObject{["success"]=true};});var p=Prepare(old);
  string id=Guid.NewGuid().ToString("N");var transfer=(JObject)Local(old,"FreezeForReload",id,30d);Check(transfer!=null,"freeze");
  Check((string)Read(old,p)["error"]=="planned_reload_frozen" && calls==0,"frozen_dispatch");
  now=110;var next=new CandidateGate(()=>now,()=>"project-A",()=>"connection-B",_=>"same",(_,__)=>{calls++;return new JObject{["success"]=true};});next.SetCapability("manage_material","get_material_info",true);
  string binding=(string)Local(next,"StageReload",JObject.Parse(transfer.ToString()),Hash(transfer),"connection-B");Check(binding!=null,"stage");
  Check(next.LocalPlans().Count==0 && (string)Read(next,p,"connection-B")["error"]=="planned_reload_frozen" && calls==0,"staged_not_active");
  Check((bool)Local(next,"CommitReload",id,binding),"commit");Check(!(bool)Local(next,"CommitReload",id,binding),"replay_commit");
  var row=next.LocalPlans().Single();Check((string)row["plan_id"]==(string)p["plan_id"] && (string)row["digest"]==(string)p["digest"] && (string)row["task_id"]=="task-A" && (string)row["connection_id"]=="connection-B" && (double)row["seconds_left"]==290,"changed_approval_or_expiry");
  Check((string)row["approval_connection_id"]=="connection-A" && (string)row["binding_digest"]==binding && binding!=(string)p["digest"],"binding_reinterpreted_as_approval");
  Check((bool?)Read(next,p,"connection-B")["success"]==true && calls==1,"next_read");
  Check(Local(next,"StageReload",transfer,Hash(transfer),"connection-B")==null,"replay_stage");
 }
 static JObject WriteManifest()=>new JObject{["source"]="Assets/source.mat",["candidate"]="Assets/candidate.mat",["operations"]=new JArray("copy","edit"),["references"]=new JArray(),["ttl_seconds"]=300};
 static JObject Write(MaterialCandidateGate g,JObject p,string action,string conn="connection-A")=>g.Dispatch(Request("execute",new JObject{["action"]=action,["arguments"]=action=="edit"?new JObject{["property"]="_Value",["value"]="0.6"}:new JObject()},(string)p["plan_id"],conn));
 static void MaterialTransfer()
 {
  using var f=new WriteFixture();double now=100;var old=new MaterialCandidateGate(()=>now,()=>"project-A",()=>"connection-A",f);old.SetCapability("copy",true);old.SetCapability("edit",true);
  var p=(JObject)old.Dispatch(Request("prepare",WriteManifest()))["data"];Check(old.Approve((string)p["plan_id"],(string)p["digest"]),"write_approve");Check((bool?)Write(old,p,"copy")["success"]==true,"copy");
  string id=Guid.NewGuid().ToString("N");var transfer=(JObject)Local(old,"FreezeForReload",id,30d);Check(transfer!=null,"write_freeze");
  var history=old.ExportTransactionHistory();var records=old.ExportTaskRecords();Check((string)Write(old,p,"edit")["error"]=="planned_reload_frozen" && f.Writes==1,"write_frozen");
  now=110;var next=new MaterialCandidateGate(()=>now,()=>"project-A",()=>"connection-B",f);next.ImportTransactionHistory(history);next.ImportTaskRecords(records);next.SetCapability("copy",true);next.SetCapability("edit",true);
  string binding=(string)Local(next,"StageReload",JObject.Parse(transfer.ToString()),Hash(transfer),"connection-B");Check(binding!=null,"write_stage");
  Check(next.LocalPlans().Count==0 && (string)Write(next,p,"edit","connection-B")["error"]=="planned_reload_frozen","write_staged");
  Check((bool)Local(next,"CommitReload",id,binding) && !(bool)Local(next,"CommitReload",id,binding),"write_commit");
  var row=next.LocalPlans().Single();Check((string)row["plan_id"]==(string)p["plan_id"] && (string)row["digest"]==(string)p["digest"] && (string)row["task_id"]=="task-A" && (double)row["seconds_left"]==290,"write_identity_changed");
  Check((string)row["approval_connection_id"]=="connection-A" && (string)row["connection_id"]=="connection-B" && (string)row["binding_digest"]==binding,"write_binding");
  Check((bool?)Write(next,p,"edit","connection-B")["success"]==true && f.Writes==2 && f.Value("Assets/source.mat")=="original","next_write");
  var rows=next.LocalTransactions();Check(rows.Count==2 && (string)rows[0]["connection_id"]=="connection-A" && (string)rows[1]["connection_id"]=="connection-B" && (bool?)rows[0]["checkpoint_available"]==false && (bool?)rows[1]["checkpoint_available"]==true,"journal_binding_rewritten");
  Check((bool?)next.Withdraw((string)rows[1]["transaction"]["id"])["success"]==true && f.Value("Assets/candidate.mat")=="original","new_checkpoint");
 }
 static void StagedStopIsExact()
 {
  foreach(bool material in new[]{false,true})
  {
   using var f=new WriteFixture();object old;JObject p;var manifest=material?WriteManifest():Manifest();
   if(material){var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);p=(JObject)g.Dispatch(Request("prepare",manifest))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);old=g;}
   else{var g=new CandidateGate(()=>100,()=>"project-A",()=>"connection-A",_=>"same",(_,__)=>new JObject{["success"]=true});p=Prepare(g);old=g;}
   string id=Guid.NewGuid().ToString("N");var transfer=(JObject)Local(old,"FreezeForReload",id,30d);
   object next;if(material){var g=new MaterialCandidateGate(()=>110,()=>"project-A",()=>"connection-B",f);g.ImportTransactionHistory(((MaterialCandidateGate)old).ExportTransactionHistory());g.ImportTaskRecords(((MaterialCandidateGate)old).ExportTaskRecords());g.SetCapability("copy",true);g.SetCapability("edit",true);next=g;}
   else{var g=new CandidateGate(()=>110,()=>"project-A",()=>"connection-B",_=>"same",(_,__)=>new JObject{["success"]=true});g.SetCapability("manage_material","get_material_info",true);next=g;}
   string binding=(string)Local(next,"StageReload",transfer,Hash(transfer),"connection-B");Check(binding!=null,"stop_stage");
   Func<JObject,JObject> dispatch=material?new Func<JObject,JObject>(((MaterialCandidateGate)next).Dispatch):((CandidateGate)next).Dispatch;
   Check((bool?)dispatch(Request("stop",plan:"wrong",conn:"connection-B"))["success"]==false,"wrong_stop");
   var stopped=dispatch(Request("stop",plan:(string)p["plan_id"],conn:"connection-B"));
   Check((bool?)stopped["success"]==true && (string)stopped["data"]?["status"]=="stopped","staged_stop_unacknowledged");
   Check(!(bool)Local(next,"CommitReload",id,binding),"stopped_grant_resurrected");
  }
 }
 sealed class Rig:IDisposable
 {
  internal readonly WriteFixture Files=new WriteFixture();internal object Old,Next;internal JObject P,Transfer;internal string Id,Binding,Connection="connection-B",Project="project-A",Evidence="same";internal double Now=110;internal Action OnCapture;internal int Calls;
  readonly bool material;
  internal Rig(bool material)
  {
   this.material=material;
   if(material){var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",Files);g.SetCapability("copy",true);g.SetCapability("edit",true);P=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];g.Approve((string)P["plan_id"],(string)P["digest"]);Write(g,P,"copy");Old=g;}
   else{var g=new CandidateGate(()=>100,()=>"project-A",()=>"connection-A",_=>"same",(_,__)=>new JObject{["success"]=true});P=Prepare(g);Old=g;}
   Id=Guid.NewGuid().ToString("N");Transfer=(JObject)Local(Old,"FreezeForReload",Id,30d);Check(Transfer!=null,"rig_freeze");
   if(material){var g=new MaterialCandidateGate(()=>Now,()=>Project,()=>Connection,new CallbackBackend(this));g.ImportTransactionHistory(((MaterialCandidateGate)Old).ExportTransactionHistory());g.ImportTaskRecords(((MaterialCandidateGate)Old).ExportTaskRecords());g.SetCapability("copy",true);g.SetCapability("edit",true);Next=g;}
   else{var g=new CandidateGate(()=>Now,()=>Project,()=>Connection,_=>{OnCapture?.Invoke();return Evidence;},(_,__)=>{Calls++;return new JObject{["success"]=true};});g.SetCapability("manage_material","get_material_info",true);Next=g;}
  }
  sealed class CallbackBackend:IMaterialCandidateBackend
  {
   readonly Rig rig;internal CallbackBackend(Rig r){rig=r;}
   public JObject Capture(JObject m,JObject c){rig.OnCapture?.Invoke();return rig.Files.Capture(m,c);}
   public object Checkpoint(JObject m,JObject c)=>rig.Files.Checkpoint(m,c);
   public JObject Apply(JObject m,JObject c)=>rig.Files.Apply(m,c);
   public JObject Read(JObject m)=>rig.Files.Read(m);
   public void Restore(JObject m,JObject c,object p)=>rig.Files.Restore(m,c,p);
  }
  internal void Stage(){Binding=(string)Local(Next,"StageReload",Transfer,Hash(Transfer),Connection);Check(Binding!=null,"rig_stage");}
  internal bool Commit()=>(bool)Local(Next,"CommitReload",Id,Binding);
  internal void Observe(){if(material)((MaterialCandidateGate)Next).Observe();else((CandidateGate)Next).Observe();}
  internal void Stop(){if(material)((MaterialCandidateGate)Next).StopAll("user revoke");else((CandidateGate)Next).StopAll("user revoke");}
  internal void Narrow(){if(material)((MaterialCandidateGate)Next).SetCapability("edit",false);else((CandidateGate)Next).SetCapability("manage_material","get_material_info",false);}
  internal int Count=>material?((MaterialCandidateGate)Next).LocalPlans().Count:((CandidateGate)Next).LocalPlans().Count;
  public void Dispose(){Files.Dispose();}
 }
 static void StagedDisconnectCannotReturn()
 {
  foreach(bool material in new[]{false,true})foreach(string fault in new[]{"connection","project","expiry"})
  {
   using var r=new Rig(material);r.Stage();if(fault=="connection")r.Connection="";if(fault=="project")r.Project="other";if(fault=="expiry")r.Now=130;
   r.Observe();r.Connection="connection-B";r.Project="project-A";r.Now=120;
   Check(!r.Commit() && r.Count==0,"observed_"+fault+"_restored_staged_grant_"+material);
  }
 }
 static void CommitBoundaries()
 {
  foreach(bool material in new[]{false,true})foreach(string fault in new[]{"stop","capability","connection","project","expiry","nonfinite","evidence","callback_stop"})
  {
   using var r=new Rig(material);r.Stage();int writes=r.Files.Writes;
   if(fault=="stop")r.Stop();if(fault=="capability")r.Narrow();if(fault=="connection")r.Connection="wrong";if(fault=="project")r.Project="wrong";if(fault=="expiry")r.Now=130;if(fault=="nonfinite")r.Now=double.NaN;
   if(fault=="evidence"){r.Evidence="changed";r.Files.Put("texture","user-change");}if(fault=="callback_stop")r.OnCapture=()=>r.Stop();
   Check(!r.Commit() && r.Count==0,"commit_accepted_"+fault+"_"+material);Check(r.Files.Writes==writes && r.Calls==0,"commit_dispatched_work");
  }
 }
 static void StageBoundaries()
 {
  foreach(bool material in new[]{false,true})foreach(string fault in new[]{"digest","tampered","stop","capability","project","connection","expiry","nonfinite","evidence","callback_stop","history"})
  {
   if(fault=="history" && !material)continue;using var r=new Rig(material);string digest=Hash(r.Transfer);int writes=r.Files.Writes;
   if(fault=="digest")digest="wrong";if(fault=="tampered")r.Transfer["plans"][0]["expires_at"]=99999;
   if(fault=="stop")r.Stop();if(fault=="capability")r.Narrow();if(fault=="project")r.Project="wrong";if(fault=="connection")r.Connection="wrong";if(fault=="expiry")r.Now=130;if(fault=="nonfinite")r.Now=double.NaN;
   if(fault=="evidence"){r.Evidence="changed";r.Files.Put("texture","user-change");}if(fault=="callback_stop")r.OnCapture=()=>r.Stop();
   if(fault=="history"){r.Transfer["plans"][0]["history_digest"]="wrong";digest=Hash(r.Transfer);}
   Check(Local(r.Next,"StageReload",r.Transfer,digest,"connection-B")==null && r.Count==0,"stage_accepted_"+fault+"_"+material);
   Check(r.Files.Writes==writes && r.Calls==0,"stage_mutated");
  }
 }
 static void FreezeClockFailsClosed()
 {
  double now=100;bool fault=false;var g=new CandidateGate(()=>now,()=>"project-A",()=>"connection-A",_=>{if(fault)now=double.NaN;return "same";},(_,__)=>new JObject{["success"]=true});Prepare(g);fault=true;
  Check(Local(g,"FreezeForReload",Guid.NewGuid().ToString("N"),30d)==null && g.LocalPlans().Count==0,"freeze_accepted_invalid_clock_after_capture");
 }
 static void CohortAndRepeatedReload()
 {
  double now=100;var old=new CandidateGate(()=>now,()=>"project-A",()=>"connection-A",_=>"same",(_,__)=>new JObject{["success"]=true});var p=Prepare(old);
  var other=(JObject)old.Dispatch(Request("prepare",Manifest(),client:"client-B"))["data"];Check(old.Approve((string)other["plan_id"],(string)other["digest"]),"other_approve");
  string id=Guid.NewGuid().ToString("N");var t=(JObject)Local(old,"FreezeForReload",id,30d);Check(((JArray)t["plans"]).Count==2,"cohort_lost");
  now=110;var next=new CandidateGate(()=>now,()=>"project-A",()=>"connection-B",_=>"same",(_,__)=>new JObject{["success"]=true});next.SetCapability("manage_material","get_material_info",true);
  string b=(string)Local(next,"StageReload",t,Hash(t),"connection-B");Check(b!=null,"cohort_stage");Check(!(bool)Local(next,"CommitReload","wrong",b) && next.LocalPlans().Count==0,"wrong_handoff");
  Check(!(bool)Local(next,"CommitReload",id,"wrong") && (bool)Local(next,"CommitReload",id,b) && next.LocalPlans().Count==2,"cohort_commit");
  now=115;string secondId=Guid.NewGuid().ToString("N");var second=(JObject)Local(next,"FreezeForReload",secondId,30d);Check(second!=null,"second_freeze");
  foreach(var row in second["plans"])Check((string)row["previous_binding_digest"]==b && (string)row["approval_connection_id"]=="connection-A" && (double)row["expires_at"]==400,"lineage_changed");
  now=120;var last=new CandidateGate(()=>now,()=>"project-A",()=>"connection-C",_=>"same",(_,__)=>new JObject{["success"]=true});last.SetCapability("manage_material","get_material_info",true);
  string lastBinding=(string)Local(last,"StageReload",second,Hash(second),"connection-C");Check(lastBinding!=null && lastBinding!=b && (bool)Local(last,"CommitReload",secondId,lastBinding),"second_commit");
  Check(last.LocalPlans().Count==2 && last.LocalPlans().All(r=>(double)r["seconds_left"]==280 && (string)r["approval_connection_id"]=="connection-A"),"cohort_renewed");
  Check((bool?)Read(last,p,"connection-A")["success"]==false,"old_connection_admitted");
 }
 static void FrozenSourceAndLocalSurface()
 {
  foreach(string fault in new[]{"pending","paused","expiry","stop","invalid_window"})
  {
   double now=100;var g=new CandidateGate(()=>now,()=>"project-A",()=>"connection-A",_=>"same",(_,__)=>new JObject{["success"]=true});var p=Prepare(g);
   if(fault=="pending")g.Dispatch(Request("prepare",Manifest(),client:"client-B"));if(fault=="paused")g.Pause((string)p["plan_id"],(string)p["digest"]);if(fault=="expiry")now=400;if(fault=="stop")g.StopAll("stop");
   Check(Local(g,"FreezeForReload",Guid.NewGuid().ToString("N"),fault=="invalid_window"?61d:30d)==null,"unapproved_freeze_"+fault);
  }
  foreach(var type in new[]{typeof(CandidateGate),typeof(MaterialCandidateGate)})foreach(string method in new[]{"FreezeForReload","StageReload","CommitReload"})Check(type.GetMethod(method)==null,"public_reload_import");
  foreach(bool material in new[]{false,true})
  {
   using var r=new Rig(material);r.Stage();r.Transfer["plans"][0]["manifest"]["ttl_seconds"]=99999;
   Check(r.Commit(),"external_alias_changed_staged_grant");
   var method=r.Next.GetType().GetMethod("Dispatch");foreach(string kind in new[]{"approve","resume","stage_reload","commit_reload"}){
    var result=(JObject)method.Invoke(r.Next,new object[]{Request(kind,plan:(string)r.P["plan_id"],conn:"connection-B")});Check((bool?)result["success"]==false,"remote_grant_path");}
  }
 }
 public static int Main(){try{CohortAndRepeatedReload();Console.WriteLine("PASS RH008 cohort_and_repeated_binding_lineage");FrozenSourceAndLocalSurface();Console.WriteLine("PASS RH009 approved_cohort_only_private_api_no_alias");FreezeClockFailsClosed();Console.WriteLine("PASS RH007 freeze_invalid_clock_after_capture");CommitBoundaries();Console.WriteLine("PASS RH005 commit_revalidates_and_no_mutation");StageBoundaries();Console.WriteLine("PASS RH006 stage_rejects_untrusted_or_changed_state");StagedDisconnectCannotReturn();Console.WriteLine("PASS RH004 observed_disconnect_expiry_cannot_restore");StagedStopIsExact();Console.WriteLine("PASS RH003 exact_staged_stop_cancels_handoff");MaterialTransfer();Console.WriteLine("PASS RH002 material_postimage_history_and_new_checkpoint");ReadTransfer();Console.WriteLine("PASS RH001 read_frozen_staged_committed_original_deadline");return 0;}catch(Exception e){Console.WriteLine("FAIL "+e.GetBaseException().Message);return 1;}}
}
