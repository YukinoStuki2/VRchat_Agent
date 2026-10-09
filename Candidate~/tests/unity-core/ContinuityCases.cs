using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;

// Production gates with explicit local fixture actions; no Unity/human acceptance.
static class ContinuityCases
{
 static void Check(bool ok,string reason){if(!ok)throw new Exception(reason);}
 static bool Local(object gate,string name,JObject p){var method=gate.GetType().GetMethod(name,new[]{typeof(string),typeof(string)});Check(method!=null,"missing_local_"+name);return (bool)method.Invoke(gate,new object[]{(string)p["plan_id"],(string)p["digest"]});}
 static JObject Request(string kind,JObject body=null,string plan="",string client="client-A")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]="connection-A",["client_id"]=client,["task_id"]="task-A",["plan_id"]=plan,["body"]=body??new JObject()};
 static JObject ReadManifest()=>new JObject{["operations"]=new JArray(new JObject{["command"]="manage_material",["action"]="get_material_info"}),["targets"]=new JArray("Assets/source.mat"),["ttl_seconds"]=300};
 static JObject Read(CandidateGate g,JObject p)=>g.Dispatch(Request("execute",new JObject{["command"]="manage_material",["params"]=new JObject{["action"]="get_material_info",["materialPath"]="Assets/source.mat"}},(string)p["plan_id"]));
 static void ReadContinuity(){int calls=0;var g=new CandidateGate(()=>100,()=>"project-A",()=>"connection-A",_=>"same",(_,__)=>{calls++;return new JObject{["success"]=true};});g.SetCapability("manage_material","get_material_info",true);
 var p=(JObject)g.Dispatch(Request("prepare",ReadManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"approve");var before=(JObject)g.LocalPlans()[0].DeepClone();
 Check(Local(g,"Pause",p),"pause");var denied=Read(g,p);Check((bool?)denied["success"]==false && (string)denied["error"]=="plan_paused" && (string)denied["data"]?["plan_id"]==(string)p["plan_id"] && calls==0,"paused_no_native_call");
 var paused=(JObject)g.LocalPlans()[0].DeepClone();Check((bool?)paused["paused"]==true,"pause_visible");paused.Remove("paused");before.Remove("paused");Check(JToken.DeepEquals(before,paused),"identity_or_deadline_changed");
 Check(!g.Approve((string)p["plan_id"],(string)p["digest"]),"approve_not_resume");Check(Local(g,"Resume",p),"resume");Check((bool?)Read(g,p)["success"]==true && calls==1,"same_plan_resumed");
 }
 static JObject WriteManifest()=>new JObject{["source"]="Assets/source.mat",["candidate"]="Assets/candidate.mat",["operations"]=new JArray("copy","edit"),["references"]=new JArray(),["ttl_seconds"]=300};
 static JObject Write(MaterialCandidateGate g,JObject p,string action,string value="")=>g.Dispatch(Request("execute",new JObject{["action"]=action,["arguments"]=action=="edit"?new JObject{["property"]="_Value",["value"]=value}:new JObject()},(string)p["plan_id"]));
 static void MaterialContinuity(){using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
 var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"material_approve");Check((bool?)Write(g,p,"copy")["success"]==true,"copy");Check((bool?)Write(g,p,"edit","0.4")["success"]==true,"edit");int writes=f.Writes;
 var before=(JObject)g.LocalPlans()[0].DeepClone();Check(Local(g,"Pause",p),"material_pause");var denied=Write(g,p,"edit","0.8");Check((bool?)denied["success"]==false && (string)denied["error"]=="plan_paused" && f.Writes==writes,"paused_no_write");
 Check((bool?)g.Dispatch(Request("status",plan:(string)p["plan_id"]))["data"]?["grant_active"]==false,"paused_not_active");var paused=(JObject)g.LocalPlans()[0].DeepClone();Check((bool?)paused["paused"]==true,"material_pause_visible");paused.Remove("paused");before.Remove("paused");Check(JToken.DeepEquals(before,paused),"material_identity_or_deadline_changed");
 Check(!g.Approve((string)p["plan_id"],(string)p["digest"]),"material_approve_not_resume");Check(Local(g,"Resume",p),"material_resume");Check((bool?)Write(g,p,"edit","0.6")["success"]==true,"resumed_write");Check(f.Value("Assets/source.mat")=="original" && f.Value("Assets/candidate.mat")=="0.6","material_final_bytes");}
 static void ReadBoundaries()
 {
  foreach(string change in new[]{"evidence","expiry","connection","project","stop","capability","callback_stop","replacement"}){
   double now=100;string conn="connection-A",project="project-A",evidence="old";int calls=0;Action during=null;
   var g=new CandidateGate(()=>now,()=>project,()=>conn,_=>{during?.Invoke();return evidence;},(_,__)=>{calls++;return new JObject{["success"]=true};});g.SetCapability("manage_material","get_material_info",true);
   var p=(JObject)g.Dispatch(Request("prepare",ReadManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"boundary_approve");Check(Local(g,"Pause",p),"boundary_pause");
   if(change=="evidence")evidence="changed";if(change=="expiry")now=400;if(change=="connection")conn="other";if(change=="project")project="other";
   if(change=="stop")g.StopAll("local stop");if(change=="capability")g.SetCapability("manage_material","get_material_info",false);if(change=="callback_stop")during=()=>g.StopAll("during capture");
   if(change=="replacement")g.Dispatch(Request("prepare",ReadManifest()));
   Check(!Local(g,"Resume",p),"read_resume_should_refuse_"+change);Check(calls==0,"read_called_during_resume");if(change!="replacement")Check(g.LocalPlans().Count==0,"read_stale_plan_retained_"+change);
  }
 }
 static void MaterialBoundaries()
 {
  foreach(string change in new[]{"candidate","source","dependency","expiry","connection","project","stop","capability","replacement"}){
   using var f=new WriteFixture();double now=100;string conn="connection-A",project="project-A";var g=new MaterialCandidateGate(()=>now,()=>project,()=>conn,f);g.SetCapability("copy",true);g.SetCapability("edit",true);
   var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"boundary_material_approve");Write(g,p,"copy");Write(g,p,"edit","0.4");int writes=f.Writes;Check(Local(g,"Pause",p),"boundary_material_pause");
   if(change=="candidate")f.Put("Assets/candidate.mat","user-new");if(change=="source")f.Put("Assets/source.mat","user-new");if(change=="dependency")f.Put("texture","user-new");
   if(change=="expiry")now=400;if(change=="connection")conn="other";if(change=="project")project="other";if(change=="stop")g.StopAll("local stop");if(change=="capability")g.SetCapability("edit",false);
   if(change=="replacement"){var manifest=WriteManifest();manifest["operations"]=new JArray("edit");g.Dispatch(Request("prepare",manifest));}
   Check(!Local(g,"Resume",p),"material_resume_should_refuse_"+change);Check(f.Writes==writes,"material_wrote_during_resume");Check(f.Value("Assets/candidate.mat")== (change=="candidate"?"user-new":"0.4"),"resume_overwrote_candidate");if(change!="replacement")Check(g.LocalPlans().Count==0,"material_stale_plan_retained");
  }
 }
 static void LocalOnlyAndSerialWriter(){using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];
 Check(!Local(g,"Pause",p) && !Local(g,"Resume",p),"pending_grant_elevated");Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"approve");Local(g,"Pause",p);
 var bad=(JObject)p.DeepClone();bad["digest"]="bad";Check(!Local(g,"Resume",bad) && g.LocalPlans().Count==1,"stale_click_changed_plan");
 var remote=g.Dispatch(Request("resume",plan:(string)p["plan_id"],client:"client-B"));Check((bool?)remote["success"]==false && g.LocalPlans().Count==1,"foreign_resume");
 var b=g.Dispatch(Request("prepare",WriteManifest(),client:"client-B"));Check((string)b["error"]=="project_write_busy" && g.LocalPlans().Count==1,"pause_released_project_writer");
 var own=g.Dispatch(Request("resume",plan:(string)p["plan_id"]));Check((string)own["error"]=="unknown_kind","remote_resume_enabled");Check(!Local(g,"Resume",p),"invalid_remote_request_did_not_revoke");
 }
 static object Invoke(object target,string method,params object[] args){var m=target.GetType().GetMethod(method);Check(m!=null,"missing_"+method);return m.Invoke(target,args);}
 static void MaterialRecordsAreNotGrants()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"record_approve");Write(g,p,"copy");Write(g,p,"edit","0.4");
  var records=(JArray)Invoke(g,"ExportTaskRecords");Check(records.Count==1,"record_count");
  Check(!records.ToString().Contains("approved") && !records.ToString().Contains("expires"),"record_contains_grant");
  var reloaded=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);
  Check((bool)Invoke(reloaded,"ImportTaskRecords",records),"record_import");
  Check(reloaded.LocalPlans().Count==0 && !reloaded.Allows("edit") && reloaded.LocalTransactions().Count==0,"import_restored_authority_or_undo");
  Check((bool?)Write(reloaded,p,"edit","0.9")["success"]==false && f.Value("Assets/candidate.mat")=="0.4","import_allowed_stale_write");
  records[0]["task_id"]="tampered";Check((string)((JArray)Invoke(reloaded,"ExportTaskRecords"))[0]["task_id"]=="task-A","record_alias");
 }
 static JObject RequestAt(string kind,JObject body=null,string plan="",string client="client-B",string conn="connection-B") {var r=Request(kind,body,plan,client);r["connection_id"]=conn;return r;}
 static void RecoverMaterialInNewBinding()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"recover_approve");Write(g,p,"copy");Write(g,p,"edit","0.4");
  var records=(JArray)Invoke(g,"ExportTaskRecords");var old=(JObject)records[0];g.StopAll("disconnect");
  var n=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);Check((bool)Invoke(n,"ImportTaskRecords",records),"recover_import");n.SetCapability("edit",true);
  var m=WriteManifest();m["operations"]=new JArray("edit");var response=n.Dispatch(RequestAt("prepare",m));
  Check((bool?)response["success"]==true,"recover_prepare_"+(string)response["error"]);var pending=(JObject)response["data"];
  Check((string)pending["recovery_record_id"]==(string)old["record_id"],"provenance_not_visible");
  Check(!n.Approve((string)pending["plan_id"],(string)pending["digest"]),"ordinary_approve_bypassed_recovery");
  var edit=new JObject{["action"]="edit",["arguments"]=new JObject{["property"]="_Value",["value"]="0.6"}};
  // Check denial on a separate imported instance: invalid use revokes its pending plan.
  var denied=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);Invoke(denied,"ImportTaskRecords",records);denied.SetCapability("edit",true);
  var dp=denied.Dispatch(RequestAt("prepare",m));Check((bool?)denied.Dispatch(RequestAt("execute",edit,(string)dp["data"]?["plan_id"]))["success"]==false && f.Writes==2,"record_granted_remote_write");
  Check((bool)Invoke(n,"RecoverPending",(string)pending["plan_id"],(string)pending["digest"],(string)old["record_id"],(string)old["digest"]),"local_recovery");
  Check((bool?)n.Dispatch(RequestAt("execute",edit,(string)pending["plan_id"]))["success"]==true && f.Value("Assets/candidate.mat")=="0.6","recovered_write");
  Check((string)pending["plan_id"]!=(string)p["plan_id"],"old_grant_reused");
 }
 static void RecoveryRevalidates()
 {
  foreach(string change in new[]{"candidate","source","dependency","project","connection","stop","capability","expiry","new_scope","bad_digest","remote"})
  {
   using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
   var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);Write(g,p,"copy");Write(g,p,"edit","0.4");var records=(JArray)Invoke(g,"ExportTaskRecords");var old=(JObject)records[0];
   double now=120;string project="project-A",conn="connection-B";var n=new MaterialCandidateGate(()=>now,()=>project,()=>conn,f);Invoke(n,"ImportTaskRecords",records);n.SetCapability("edit",true);n.SetCapability("reference",true);
   var m=WriteManifest();m["operations"]=new JArray("edit");
   if(change=="new_scope"){m["operations"]=new JArray("edit","reference");m["references"]=new JArray(new JObject{["renderer"]="new-host",["slot"]=0});}
   var response=n.Dispatch(RequestAt("prepare",m));if(change=="new_scope"){Check((bool?)response["success"]==false,"expanded_recovery_scope");continue;}
   var pending=(JObject)response["data"];Check(pending!=null,"boundary_recovery_prepare");
   if(change=="candidate")f.Put("Assets/candidate.mat","user");if(change=="source")f.Put("Assets/source.mat","user");if(change=="dependency")f.Put("texture","user");
   if(change=="project")project="other";if(change=="connection")conn="other";if(change=="stop")n.StopAll("local stop");if(change=="capability")n.SetCapability("edit",false);if(change=="expiry")now=500;
   if(change=="remote")Check((bool?)n.Dispatch(RequestAt("recover",plan:(string)pending["plan_id"]))["success"]==false,"remote_recovery");
   Check(!(bool)Invoke(n,"RecoverPending",(string)pending["plan_id"],(string)pending["digest"],(string)old["record_id"],change=="bad_digest"?"bad":(string)old["digest"]),"recovered_changed_"+change);
   Check(f.Writes==2 && f.Value("Assets/candidate.mat")== (change=="candidate"?"user":"0.4"),"recovery_changed_files");
  }
 }
 static void InvalidRecoveryRecords()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);Write(g,p,"copy");
  var saved=(JArray)Invoke(g,"ExportTaskRecords");
  foreach(string bad in new[]{"project","extra","digest","duplicate","type","null"})
  {
   var records=(JArray)saved.DeepClone();if(bad=="project")records[0]["project_id"]="other";if(bad=="extra")records[0]["approved"]=true;if(bad=="digest")records[0]["digest"]="wrong";
   if(bad=="duplicate")records.Add(records[0].DeepClone());if(bad=="type")records[0]["copied"]="true";if(bad=="null")records=null;
   var n=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);Check(!(bool)Invoke(n,"ImportTaskRecords",new object[]{records}),"invalid_import_"+bad);
   Check(((JArray)Invoke(n,"ExportTaskRecords")).Count==0 && n.LocalPlans().Count==0,"partial_import");
  }
  f.ThrowAfterWrite=true;Write(g,p,"edit","0.7");var failed=(JArray)Invoke(g,"ExportTaskRecords");Check((bool?)failed[0]["recoverable"]==false,"failure_recoverable");
 }
 static void SupersededRecordsCannotCompete()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);Write(g,p,"copy");
  var m=WriteManifest();m["operations"]=new JArray("edit");var next=(JObject)g.Dispatch(Request("prepare",m))["data"];Check(g.Approve((string)next["plan_id"],(string)next["digest"]),"reapproval");
  var records=(JArray)Invoke(g,"ExportTaskRecords");Check(records.Count==2 && records.Count(r=>(bool?)r["recoverable"]==true)==1,"superseded_record_still_recoverable");
  var n=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);Invoke(n,"ImportTaskRecords",records);n.SetCapability("edit",true);
  Check((bool?)n.Dispatch(RequestAt("prepare",m))["success"]==true,"superseded_record_caused_ambiguity");
 }
 static void TransactionHistorySurvivesWithoutUndo()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];Check(g.Approve((string)p["plan_id"],(string)p["digest"]),"history_approve");
  Write(g,p,"copy");var edit=Write(g,p,"edit","0.4");string tx=(string)edit["data"]["transaction"]["id"];
  var exported=(JArray)Invoke(g,"ExportTransactionHistory");Check(exported.Count==2,"history_export_count");
  var restored=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);
  Check((bool)Invoke(restored,"ImportTransactionHistory",JArray.Parse(exported.ToString())),"history_import");
  Check(restored.LocalPlans().Count==0 && !restored.Allows("edit") && restored.ExportTaskRecords().Count==0,"history_restored_grant_or_recovery");
  var rows=restored.LocalTransactions();Check(rows.Count==2,"history_lost");
  foreach(JObject row in rows){Check((bool?)row["checkpoint_available"]==false && (bool?)row["withdrawal_available"]==false,"history_undo_advertised");Check((bool?)row["withdrawn"]==false,"false_withdrawal");Check((string)row["connection_id"]=="connection-A","rewritten_historical_connection");}
  int writes=f.Writes;var denied=restored.Withdraw(tx);Check((string)denied["error"]=="checkpoint_unavailable_after_reload" && f.Writes==writes && f.Value("Assets/candidate.mat")=="0.4","archive_restore_attempted");
  exported[0]["task_id"]="mutated";rows[0]["task_id"]="mutated";Check((string)restored.LocalTransactions()[0]["task_id"]=="task-A","history_alias");
  var m=WriteManifest();m["operations"]=new JArray("edit");restored.SetCapability("edit",true);
  Check((string)restored.Dispatch(RequestAt("prepare",m))["error"]=="candidate_provenance_conflict","history_used_as_live_provenance");
 }
 static void HistoryCapacityCannotResetAtReload()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);Write(g,p,"copy");
  var history=(JArray)Invoke(g,"ExportTransactionHistory");var row=(JObject)history[0];history=new JArray();
  for(int i=0;i<128;i++){var copy=(JObject)row.DeepClone();copy["transaction"]["id"]=Guid.NewGuid().ToString("N");history.Add(copy);}
  var n=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);Check((bool)Invoke(n,"ImportTransactionHistory",history),"capacity_import");n.SetCapability("copy",true);
  var m=WriteManifest();m["candidate"]="Assets/next.mat";m["operations"]=new JArray("copy");var pending=(JObject)n.Dispatch(RequestAt("prepare",m))["data"];Check(n.Approve((string)pending["plan_id"],(string)pending["digest"]),"capacity_approve");
  int writes=f.Writes;var response=n.Dispatch(RequestAt("execute",new JObject{["action"]="copy",["arguments"]=new JObject()},(string)pending["plan_id"]));
  Check((string)response["error"]=="journal_capacity" && f.Writes==writes && n.LocalTransactions().Count==128,"reload_reset_journal_capacity");
 }
 static void InvalidHistoryIsAtomic()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);var m=WriteManifest();m["operations"]=new JArray("copy");
  var p=(JObject)g.Dispatch(Request("prepare",m))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);Write(g,p,"copy");var saved=(JArray)Invoke(g,"ExportTransactionHistory");
  foreach(string bad in new[]{"project","extra","duplicate","count","type","null","transaction","false_withdrawal","size"})
  {
   var input=(JArray)saved.DeepClone();
   if(bad=="project")input[0]["project_id"]="other";if(bad=="extra")input[0]["checkpoint_available"]=true;
   if(bad=="duplicate")input.Add(input[0].DeepClone());if(bad=="count")while(input.Count<129)input.Add(input[0].DeepClone());
   if(bad=="type")input[0]["withdrawn"]="false";if(bad=="transaction")input[0]["transaction"]["approved"]=true;
   if(bad=="false_withdrawal")input[0]["withdrawn"]=true;if(bad=="size")input[0]["manifest"]["source"]=new string('x',65536);
   if(bad=="null")input=null;
   var n=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-B",f);Check(!(bool)Invoke(n,"ImportTransactionHistory",new object[]{input}),"history_accepted_"+bad);
   Check(n.LocalTransactions().Count==0 && n.LocalPlans().Count==0 && !n.Allows("copy"),"partial_history_import");
   Check((bool)Invoke(n,"ImportTransactionHistory",saved),"invalid_attempt_poisoned_import");
   Check(!(bool)Invoke(n,"ImportTransactionHistory",saved) && n.LocalTransactions().Count==1,"second_import_changed_history");
  }
 }
 static void WithdrawalHistoryAndNewCheckpoints()
 {
  using var f=new WriteFixture();var g=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"connection-A",f);g.SetCapability("copy",true);g.SetCapability("edit",true);
  var p=(JObject)g.Dispatch(Request("prepare",WriteManifest()))["data"];g.Approve((string)p["plan_id"],(string)p["digest"]);Write(g,p,"copy");var edit=Write(g,p,"edit","0.4");
  Check((bool?)g.Withdraw((string)edit["data"]["transaction"]["id"])["success"]==true,"history_withdraw");
  var saved=(JArray)Invoke(g,"ExportTransactionHistory");var n=new MaterialCandidateGate(()=>120,()=>"project-A",()=>"connection-B",f);Check((bool)Invoke(n,"ImportTransactionHistory",JArray.Parse(saved.ToString())),"withdrawn_import");
  Check((bool?)n.LocalTransactions()[1]["withdrawn"]==true && JToken.DeepEquals(n.LocalTransactions()[1]["transaction"],saved[1]["transaction"]),"withdrawal_report_lost");
  n.SetCapability("copy",true);n.SetCapability("edit",true);var m=WriteManifest();m["candidate"]="Assets/new.mat";var pending=(JObject)n.Dispatch(RequestAt("prepare",m))["data"];Check(n.Approve((string)pending["plan_id"],(string)pending["digest"]),"new_history_approve");
  var copy=new JObject{["action"]="copy",["arguments"]=new JObject()};Check((bool?)n.Dispatch(RequestAt("execute",copy,(string)pending["plan_id"]))["success"]==true,"new_history_copy");
  var cmd=new JObject{["action"]="edit",["arguments"]=new JObject{["property"]="_Value",["value"]="0.9"}};Check((bool?)n.Dispatch(RequestAt("execute",cmd,(string)pending["plan_id"]))["success"]==true,"new_history_edit");
  var rows=n.LocalTransactions();Check(rows.Count==4 && (bool?)rows[3]["withdrawal_available"]==true && (bool?)rows[1]["withdrawal_available"]==false,"new_checkpoint_not_distinct");
  Check((bool?)n.Withdraw((string)rows[3]["transaction"]["id"])["success"]==true && f.Value("Assets/new.mat")=="original","new_checkpoint_unusable");
  var again=new MaterialCandidateGate(()=>130,()=>"project-A",()=>"connection-C",f);Check((bool)Invoke(again,"ImportTransactionHistory",Invoke(n,"ExportTransactionHistory")) && again.LocalTransactions().Count==4,"second_reload_history_lost");
 }
 public static int Main(string[] args){try{InvalidHistoryIsAtomic();Console.WriteLine("PASS PC013 invalid_history_atomic_and_bounded");WithdrawalHistoryAndNewCheckpoints();Console.WriteLine("PASS PC014 old_withdrawals_preserved_new_checkpoints_usable");HistoryCapacityCannotResetAtReload();Console.WriteLine("PASS PC012 history_counts_toward_journal_capacity");TransactionHistorySurvivesWithoutUndo();Console.WriteLine("PASS PC011 transaction_history_without_authority_or_checkpoint");SupersededRecordsCannotCompete();Console.WriteLine("PASS PC010 superseded_records_not_recoverable");RecoveryRevalidates();Console.WriteLine("PASS PC008 recovery_revalidates_scope_and_live_evidence");InvalidRecoveryRecords();Console.WriteLine("PASS PC009 invalid_and_failed_records_denied");RecoverMaterialInNewBinding();Console.WriteLine("PASS PC007 explicit_local_new_binding_recovery");MaterialRecordsAreNotGrants();Console.WriteLine("PASS PC006 reload_records_are_not_grants");ReadContinuity();Console.WriteLine("PASS PC001 read_plan_identity_survives_pause");MaterialContinuity();Console.WriteLine("PASS PC002 material_plan_and_postimage_survive_pause");ReadBoundaries();Console.WriteLine("PASS PC003 read_revalidation_lifecycle_boundaries");MaterialBoundaries();Console.WriteLine("PASS PC004 material_revalidation_lifecycle_boundaries");LocalOnlyAndSerialWriter();Console.WriteLine("PASS PC005 local_only_and_single_writer");return 0;}catch(Exception e){Console.WriteLine("FAIL "+e.GetBaseException().Message);return 1;}}
}
