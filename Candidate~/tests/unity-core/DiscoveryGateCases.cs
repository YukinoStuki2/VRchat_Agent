// Actual gate + candidate discovery; only Unity/NUnit boundaries are doubles.
using System;
using System.Threading;
using System.Threading.Tasks;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using UnityEditor.TestTools.TestRunner;
internal static class DiscoveryGateCases
{
 static CandidateGate gate;
 static System.Collections.Generic.Dictionary<string,string> store=new System.Collections.Generic.Dictionary<string,string>();
 static EffectCleanupLedger Ledger()=>new EffectCleanupLedger(k=>store.TryGetValue(k,out var v)?v:"",(k,v)=>store[k]=v);
 static string project="p",connection="c",review="review-v1";
 static int generic,starts;static bool forged,badRows,throwReader,numericSuccess;static Action reviewAction;
 static string Review(string target){var call=reviewAction;reviewAction=null;call?.Invoke();return review;}
 static Func<bool> ticket;
 static void Need(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id="")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]=project,["connection_id"]=connection,["client_id"]="client",["task_id"]="task",["plan_id"]=id,["body"]=new JObject()};
 static JObject Prepare(){var r=Wire("prepare");r["body"]=new JObject{["operations"]=JArray.Parse("[{command:'get_tests',action:'discover'}]"),["targets"]=new JArray("TestDiscovery/EditMode"),["ttl_seconds"]=60,["effects"]=JArray.Parse("[{kind:'test_discovery_callbacks',version:1}]")};return r;}
 static JObject Execute(JObject p){var r=Wire("execute",(string)p["data"]["plan_id"]);r["body"]=JObject.Parse("{command:'get_tests',params:{mode:'EditMode'}}");return r;}
 static async Task<JObject> Reader(JObject args,Func<bool> allowed)
 {
  starts++;ticket=allowed;if(throwReader)throw new InvalidOperationException("PRIVATE_MARKER /unpublished/project");if(forged)return JObject.Parse("{success:true,data:{tests:[]}}");
  var job=CandidateDiscoveryJob.Begin((string)args["mode"],allowed);
  var result=await job.Completion;
  var payload=new JObject{["success"]=result.Success,["error"]=result.Error,["data"]=new JObject{
   ["tests"]=badRows?JArray.Parse("[['Test','Suite.Test','Suite/Test','PlayMode']]"):result.Rows==null?null:JArray.FromObject(result.Rows),
   ["candidate_effects"]=new JObject{["kind"]="test_discovery_callbacks",["version"]=1,["read_only"]=false,
    ["all_mutations_observed"]=false,["callback_effects_path_bounded"]=false,["cleanup_confirmed"]=result.CleanupConfirmed}}};
  if(numericSuccess)payload["success"]=1;return payload;
 }
 static JObject Pump(Task<JObject> task)
 {
  var end=DateTime.UtcNow.AddSeconds(5);
  while(!task.IsCompleted&&DateTime.UtcNow<end){UnityEditor.EditorApplication.Tick();Thread.Sleep(1);}
  Need(task.IsCompleted,"async gate did not complete");return task.GetAwaiter().GetResult();
 }
 static void Setup(bool freshEditor=true){if(freshEditor)store=new System.Collections.Generic.Dictionary<string,string>();gate=new CandidateGate(()=>UnityEditor.EditorApplication.timeSinceStartup,()=>project,()=>connection,t=>{generic++;throw new Exception();},(c,a)=>{generic++;throw new Exception();},null,null,null,null,Review,Reader,Ledger());gate.SetCapability("get_tests","discover",true);gate.SetTestDiscoveryCallbacks(true);}
 static JObject Approved(){var p=gate.Dispatch(Prepare());Need((bool)p["success"],"prepare failed");Need(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve failed");return p;}
 static int Main(){try{
  gate=new CandidateGate(()=>UnityEditor.EditorApplication.timeSinceStartup,()=>project,()=>connection,t=>{generic++;throw new Exception();},(c,a)=>{generic++;throw new Exception();},null,null,null,null,Review,Reader,Ledger());
  gate.SetCapability("get_tests","discover",true);
  Need(!(bool)gate.Dispatch(Prepare())["success"]&&starts==0&&generic==0,"default discovery opened");
  gate.SetTestDiscoveryCallbacks(true);var pending=gate.Dispatch(Prepare());Need((bool)pending["success"]&&starts==0,"prepare executed discovery");
  Need(!(bool)Pump(gate.DispatchAsync(Execute(pending)))["success"]&&starts==0,"unapproved discovery ran");
  var p=gate.Dispatch(Prepare());Need(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve failed");
  var result=Pump(gate.DispatchAsync(Execute(p)));Need((bool)result["success"]&&starts==1&&generic==0,"approved dedicated async reader failed: "+result.ToString());
  Need(ticket!=null&&!ticket(),"finished async ticket reusable");
  Console.WriteLine("PASS DG001 default_closed_exact_plan_native_reader");
  forged=true;var noReceipt=Pump(gate.DispatchAsync(Execute(p)));
  Need(!(bool)noReceipt["success"]&&noReceipt["data"]?["cleanup_confirmed"]?.Type==JTokenType.Boolean&&!(bool)noReceipt["data"]["cleanup_confirmed"],"forged receipt accepted or cleanup uncertainty hidden");
  forged=false;gate.StopAll("stop");gate.SetTestDiscoveryCallbacks(false);gate.SetTestDiscoveryCallbacks(true);
  Need(!(bool)gate.Dispatch(Prepare())["success"],"cleanup debt was cleared by toggle");
  Console.WriteLine("PASS DG002 missing_receipt_latches_cleanup_debt");
  Setup();Probe.Hang=true;p=Approved();var active=gate.DispatchAsync(Execute(p));
  for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();int entered=starts;
  Need(!(bool)gate.Dispatch(Prepare())["success"]&&starts==entered,"pending job allowed another prepare");
  var stop=Wire("stop",(string)p["data"]["plan_id"]);Need((bool)gate.Dispatch(stop)["success"],"exact stop rejected while busy");
  var stopped=Pump(active);Need(!(bool)stopped["success"]&&(bool)stopped["data"]["cleanup_confirmed"]&&!(bool)stopped["data"]["read_only"],"stop lost effect/cleanup state");
  Need(ticket!=null&&!ticket(),"cancelled ticket revived");Probe.Hang=false;
  Need(!(bool)Pump(gate.DispatchAsync(Execute(p)))["success"],"stopped plan resumed");
  Console.WriteLine("PASS DG003 async_stop_revokes_and_awaits_owned_cleanup");
  Setup();p=Approved();badRows=true;var invalidRows=Pump(gate.DispatchAsync(Execute(p)));badRows=false;
  Need(!(bool)invalidRows["success"]&&(bool)invalidRows["data"]["cleanup_confirmed"],"invalid result mode accepted");
  Need(gate.LocalPlans().Count==0,"invalid result retained authority");
  Console.WriteLine("PASS DG004 result_validation_revokes_without_inventing_cleanup_debt");
  foreach(string cause in new[]{"review","binding","expiry","ceiling","pause"}) {
   Setup();UnityEditor.EditorApplication.timeSinceStartup=0;Probe.Hang=true;p=Approved();active=gate.DispatchAsync(Execute(p));for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();
   if(cause=="review")review="different";if(cause=="binding")connection="other";if(cause=="expiry")UnityEditor.EditorApplication.timeSinceStartup=61;if(cause=="ceiling")gate.SetTestDiscoveryCallbacks(false);
   if(cause=="pause"){Need(!gate.Pause((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"busy operation paused without cancellation");gate.StopAll("stop after refused busy pause");}
   var denied=Pump(active);Need(!(bool)denied["success"]&&(bool)denied["data"]["cleanup_confirmed"],"async invalidation returned stale result "+cause);
   review="review-v1";connection="c";UnityEditor.EditorApplication.timeSinceStartup=0;Probe.Hang=false;gate.SetTestDiscoveryCallbacks(true);
   Need(!(bool)Pump(gate.DispatchAsync(Execute(p)))["success"],"old async grant revived "+cause);
  }
  Console.WriteLine("PASS DG005 async_context_ceiling_pause_and_expiry_invalidation");
  Setup();
  foreach(string bad in new[]{"effects","target","mixed","policy","version"}) {
   var request=Prepare();var body=(JObject)request["body"];
   if(bad=="effects")body.Remove("effects");if(bad=="target")body["targets"][0]="TestDiscovery/all";
   if(bad=="mixed")((JArray)body["operations"]).Add(JObject.Parse("{command:'get_test_job',action:'observe'}"));
   if(bad=="policy")body["effect_policy"]=new JObject();if(bad=="version")body["effects"][0]["version"]=true;
   entered=starts;Need(!(bool)gate.Dispatch(request)["success"]&&starts==entered,"invalid manifest allowed "+bad);
  }
  p=Approved();var wrong=Execute(p);wrong["body"]["params"]["mode"]="PlayMode";entered=starts;
  Need(!(bool)Pump(gate.DispatchAsync(wrong))["success"]&&starts==entered,"mode escaped plan");
  p=Approved();Need(gate.FreezeForReload(Guid.NewGuid().ToString("N"),30)==null,"effect plan transferred across reload");
  gate=new CandidateGate(()=>0,()=>project,()=>connection,t=>{generic++;return "not_trusted";},(c,a)=>{generic++;return JObject.Parse("{success:true}");});
  gate.SetCapability("get_tests","discover",true);gate.SetTestDiscoveryCallbacks(true);entered=generic;
  Need(!(bool)gate.Dispatch(Prepare())["success"]&&generic==entered,"legacy gate used generic provider");
  Console.WriteLine("PASS DG006 explicit_effect_mode_reload_and_legacy_boundaries");
  Setup();p=Approved();Probe.Hang=true;Probe.DisposeFail=true;active=gate.DispatchAsync(Execute(p));for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();gate.StopAll("stop");var uncertain=Pump(active);
  Need(!(bool)uncertain["success"]&&!(bool)uncertain["data"]["cleanup_confirmed"]&&gate.TestDiscoveryCleanupUnconfirmed,"dispose failure lost cleanup debt");
  Probe.Hang=false;Probe.DisposeFail=false;gate.SetTestDiscoveryCallbacks(true);Need(!(bool)gate.Dispatch(Prepare())["success"],"cleanup debt permits retry");
  Console.WriteLine("PASS DG007 actual_reader_disposal_debt_latches");
  Setup();p=Approved();throwReader=true;var exception=Pump(gate.DispatchAsync(Execute(p)));throwReader=false;
  Need(!(bool)exception["success"]&&!exception.ToString().Contains("PRIVATE_MARKER")&&gate.TestDiscoveryCleanupUnconfirmed,"raw delegate error escaped or uncertainty erased");
  Console.WriteLine("PASS DG008 exception_redaction_and_uncertainty");
  Setup();p=Approved();entered=starts;reviewAction=()=>gate.StopAll("during review");var reentered=Pump(gate.DispatchAsync(Execute(p)));
  Need(!(bool)reentered["success"]&&starts==entered,"review reentry launched discovery");
  Console.WriteLine("PASS DG009 review_reentry_rejected_before_effects");
  Setup();p=Approved();numericSuccess=true;var badType=Pump(gate.DispatchAsync(Execute(p)));numericSuccess=false;
  Need(!(bool)badType["success"]&&!(bool)badType["data"]["cleanup_confirmed"]&&gate.TestDiscoveryCleanupUnconfirmed,"malformed typed result was accepted or treated as trusted cleanup");
  Console.WriteLine("PASS DG010 strict_result_boolean");
  Setup(false);entered=starts;
  Need(!(bool)gate.Dispatch(Prepare())["success"]&&starts==entered,"new gate erased outstanding discovery cleanup debt");
  Console.WriteLine("PASS DG011 new_gate_cannot_erase_cleanup_debt");
  Setup();p=Approved();Probe.Hang=true;active=gate.DispatchAsync(Execute(p));var owner=gate;
  Need(store.TryGetValue("discovery",out var marker)&&marker!="","reader started before denial marker");
  Setup(false);var replacement=gate;Need(!(bool)gate.Dispatch(Prepare())["success"],"parallel gate ignored pending work");
  owner.StopAll("stop owner");var cleaned=Pump(active);Probe.Hang=false;
  Need(!(bool)cleaned["success"]&&(bool)cleaned["data"]["cleanup_confirmed"]&&store["discovery"]=="","own revoked completion did not clean its marker");
  Need(replacement.LocalPlans().Count==0&&!replacement.TestDiscoveryCleanupUnconfirmed,"cleanup manufactured approval or left false debt");
  Console.WriteLine("PASS DG012 pending_across_instances_and_exact_owner_completion");
  gate=new CandidateGate(()=>0,()=>project,()=>connection,t=>"unused",(c,a)=>null,null,null,null,null,Review,Reader);
  gate.SetCapability("get_tests","discover",true);gate.SetTestDiscoveryCallbacks(true);entered=starts;
  Need(!(bool)gate.Dispatch(Prepare())["success"]&&starts==entered,"adapters without durable denial storage opened");
  Console.WriteLine("PASS DG013 absent_store_denies_without_reader");
  Setup();UnityEditor.EditorApplication.timeSinceStartup=0;p=Approved();entered=starts;
  Need(gate.Pause((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"pause failed");
  var paused=Pump(gate.DispatchAsync(Execute(p)));
  Need(!(bool)paused["success"]&&(string)paused["error"]=="plan_paused"&&(string)paused["data"]["status"]=="paused"&&paused["data"].Count()==3,"exact pause receipt lost");
  Need(starts==entered&&gate.LocalPlans().Count==1&&!gate.TestDiscoveryCleanupUnconfirmed,"paused call executed or removed grant");
  Console.WriteLine("PAUSE_RECEIPT "+paused.ToString(Newtonsoft.Json.Formatting.None));
  Need(gate.Resume((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"resume failed");
  Need((bool)Pump(gate.DispatchAsync(Execute(p)))["success"]&&starts==entered+1,"resumed discovery failed");
  foreach(string cause in new[]{"expiry","stop","ceiling","binding","replace"}){
   Setup();UnityEditor.EditorApplication.timeSinceStartup=0;p=Approved();entered=starts;
   Need(gate.Pause((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"pause invalidation setup failed");
   if(cause=="expiry")UnityEditor.EditorApplication.timeSinceStartup=61;
   if(cause=="stop")gate.StopAll("local stop");if(cause=="ceiling")gate.SetTestDiscoveryCallbacks(false);
   if(cause=="binding")connection="other";if(cause=="replace")Approved();
   var invalid=Pump(gate.DispatchAsync(Execute(p)));
   Need(!(bool)invalid["success"]&&(string)invalid["data"]["status"]!="paused"&&starts==entered,"pause hid invalid authority "+cause);
   Need(!gate.Resume((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"invalid paused grant resumed "+cause);
   if(cause=="replace")Need(gate.LocalPlans().Count==1,"old call revoked replacement");
   connection="c";UnityEditor.EditorApplication.timeSinceStartup=0;
  }
  Console.WriteLine("PASS DG014 pause_preserves_only_current_unexpired_grant");
  foreach(string effect in new[]{"asset_load_callbacks","prefab_contents_callbacks","test_discovery_callbacks","project_test_job_maintenance"}){
   Setup();gate.SetTestDiscoveryCallbacks(false);
   if(effect=="asset_load_callbacks")gate.SetAssetCallbacks(true);
   if(effect=="prefab_contents_callbacks")gate.SetPrefabContentsCallbacks(true);
   if(effect=="test_discovery_callbacks")gate.SetTestDiscoveryCallbacks(true);
   if(effect=="project_test_job_maintenance")gate.SetProjectJobMaintenance(true);
   var statusRequest=Wire("status");statusRequest["task_id"]="";
   var status=gate.Dispatch(statusRequest);
   Need((bool)status["success"]&&!(bool)status["data"]["read_only"]&&(bool)status["data"][effect]&&gate.LocalPlans().Count==0,"effect status conflated readiness/grant");
   Console.WriteLine("EFFECT_STATUS "+status["data"].ToString(Newtonsoft.Json.Formatting.None));
  }
  Console.WriteLine("PASS DG015 effect_status_truthful_without_task_grant");
  return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
