// Real synchronous authorization core; evidence/native execution are fixtures.
using System;using System.Linq;using Newtonsoft.Json.Linq;using Yukino.VRChatAgent;
internal static class EffectGateCases {
 const string Job="0123456789abcdef0123456789abcdef",Target="TestJobs/"+Job;
 static double now=1;static string project="project",connection="connection";static int executions,captures;static CandidateGate gate;
 static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
 static JObject Wire(string kind,string plan="")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]=project,["connection_id"]=connection,["client_id"]="client",["task_id"]="task",["plan_id"]=plan,["body"]=new JObject()};
 static JObject Prepare(){var p=Wire("prepare");p["body"]=new JObject{["operations"]=JArray.Parse("[{command:'get_test_job',action:'observe'}]"),["targets"]=new JArray(Target),["ttl_seconds"]=60,["effects"]=JArray.Parse("[{kind:'project_test_job_maintenance',version:1}]")};return p;}
 static JObject Execute(JObject p){var q=Wire("execute",(string)p["data"]["plan_id"]);q["body"]=new JObject{["command"]="get_test_job",["params"]=new JObject{["job_id"]=Job}};return q;}
 static void EnableEffect(bool value){var m=typeof(CandidateGate).GetMethod("SetProjectJobMaintenance");Check(m!=null,"independent_project_job_maintenance_ceiling_missing");m.Invoke(gate,new object[]{value});}
 static JObject Approved(){var p=gate.Dispatch(Prepare());Check((bool)p["success"],"effect_prepare_failed: "+p);Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"effect_approve_failed");return p;}
 static int Main(){try{
  gate=new CandidateGate(()=>now,()=>project,()=>connection,t=>{captures++;return "live:"+t;},(c,a)=>{executions++;return JObject.Parse("{success:true,data:{job_id:'"+Job+"',status:'running'}}");});
  // RED must be a missing behavior assertion, not a missing-symbol compile error.
  try{gate.SetCapability("get_test_job","observe",true);}catch{Check(false,"job_observation_capability_missing");}
  Check(!(bool)gate.Dispatch(Prepare())["success"] && executions==0 && captures==0,"effect_ceiling_default_not_closed");
  EnableEffect(true);var pending=gate.Dispatch(Prepare());Check((bool)pending["success"],"explicit_effect_prepare_not_supported");
  Check(executions==0 && captures>0,"prepare_dispatched_native_effect");
  Check(!(bool)gate.Dispatch(Execute(pending))["success"] && executions==0,"pending_executed");
  var approved=Approved();var local=(JObject)gate.LocalPlans()[0];
  Check((string)local["manifest"]["effect_policy"]["kind"]=="project_test_job_maintenance" && (bool)local["manifest"]["effect_policy"]["project_wide"] && !(bool)local["manifest"]["effect_policy"]["read_only"],"trusted_risk_policy_missing");
  Check((bool)gate.Dispatch(Execute(approved))["success"] && executions==1,"approved_effect_not_executed");
  Console.WriteLine("PASS EG001 independent_ceiling_explicit_manifest_pending_and_approval");
  foreach(string bad in new[]{"missing","empty","kind","version","target","mixed","extra"}){
   var p=Prepare();var b=(JObject)p["body"];
   if(bad=="missing")b.Remove("effects");if(bad=="empty")b["effects"]=new JArray();
   if(bad=="kind")b["effects"][0]["kind"]="asset_load_callbacks";
   if(bad=="version")b["effects"][0]["version"]=true;
   if(bad=="target")b["targets"][0]="TestJobs/"+Job.ToUpperInvariant();
   if(bad=="mixed")((JArray)b["targets"]).Add("Scenes");
   if(bad=="extra")b["effect_policy"]=new JObject();
   int n=executions;Check(!(bool)gate.Dispatch(p)["success"] && executions==n,"bad_effect_manifest: "+bad);
  }
  Console.WriteLine("PASS EG002 missing_forged_mixed_or_noncanonical_effects_rejected");
  foreach(string bad in new[]{"other","wait","run","details-string"}){
   var p=Approved();var q=Execute(p);var a=(JObject)q["body"]["params"];
   if(bad=="other")a["job_id"]=new string('a',32);if(bad=="wait")a["wait_timeout"]=1;
   if(bad=="run")q["body"]["command"]="run_tests";if(bad=="details-string")a["includeDetails"]="false";
   int n=executions;Check(!(bool)gate.Dispatch(q)["success"] && executions==n,"outside_effect_args: "+bad);
  }
  Console.WriteLine("PASS EG003_exact_job_no_run_wait_or_coercion");
  approved=Approved();EnableEffect(false);int before=executions;
  Check(!(bool)gate.Dispatch(Execute(approved))["success"] && executions==before,"disabled_effect_still_runs");
  EnableEffect(true);Check(!(bool)gate.Dispatch(Execute(approved))["success"],"reenable_revived_grant");
  approved=Approved();now=100;Check(!(bool)gate.Dispatch(Execute(approved))["success"],"expired_effect");now=1;
  approved=Approved();Check(gate.FreezeForReload(Guid.NewGuid().ToString("N"),30)==null,"effect_implicitly_transferred");
  Check(!(bool)gate.Dispatch(Execute(approved))["success"],"failed_freeze_revived_effect");
  Console.WriteLine("PASS EG004 ceiling_revocation_expiry_and_no_reload_inheritance");
  return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
