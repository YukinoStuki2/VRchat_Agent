// Real CandidateGate + actual candidate reader; Unity APIs only are doubles.
using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using MCPForUnity.Editor.Tools.Prefabs;
internal static class PrefabGateCases {
 static System.Collections.Generic.Dictionary<string,string> store;
 static EffectCleanupLedger Ledger()=>new EffectCleanupLedger(k=>store.TryGetValue(k,out var v)?v:"",(k,v)=>store[k]=v);
 static double now=1;static string project="p",connection="c",review="review-v1";
 static CandidateGate gate;static bool forged=false,inReader=false;static Action duringReview;static int generic,reviews;static Func<bool> lastTicket;
 static void Need(bool v,string why){if(!v)throw new Exception(why);}
 static JObject Wire(string kind,string plan="")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]=project,["connection_id"]=connection,["client_id"]="client",["task_id"]="task",["plan_id"]=plan,["body"]=new JObject()};
 static JObject Prepare(string action) {var r=Wire("prepare");var effects=JArray.Parse("[{kind:'asset_load_callbacks',version:1}]");if(action=="get_hierarchy")effects.Add(JObject.Parse("{kind:'prefab_contents_callbacks',version:1}"));r["body"]=new JObject{["operations"]=new JArray(new JObject{["command"]="manage_prefabs",["action"]=action}),["targets"]=new JArray("PrefabReads/Assets/fixture.prefab"),["ttl_seconds"]=60,["effects"]=effects};return r;}
 static JObject Execute(JObject p,string action){var r=Wire("execute",(string)p["data"]["plan_id"]);r["body"]=new JObject{["command"]="manage_prefabs",["params"]=new JObject{["action"]=action,["prefabPath"]="Assets/fixture.prefab"}};return r;}
 static void Contents(bool value){var m=typeof(CandidateGate).GetMethod("SetPrefabContentsCallbacks");Need(m!=null,"prefab_contents_ceiling_missing");m.Invoke(gate,new object[]{value});}
 static JObject Approved(string action){var p=gate.Dispatch(Prepare(action));Need((bool)p["success"],"prepare failed "+p);Need(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approval failed");return p;}
 static CandidateGate Create(bool freshEditor=true){if(freshEditor)store=new System.Collections.Generic.Dictionary<string,string>();var ctor=typeof(CandidateGate).GetConstructors().SingleOrDefault(c=>c.GetParameters().Length==12);Need(ctor!=null,"prefab_trusted_adapters_missing");return (CandidateGate)ctor.Invoke(new object[]{(Func<double>)(()=>now),(Func<string>)(()=>project),(Func<string>)(()=>connection),(Func<string,string>)(t=>{generic++;throw new Exception();}),(Func<string,JObject,JObject>)((c,a)=>{generic++;throw new Exception();}),null,null,(Func<string,string,string>)((action,target)=>{reviews++;if(inReader){var callback=duringReview;duringReview=null;callback?.Invoke();}return review;}),(Func<JObject,Func<bool>,JObject>)((a,v)=>{lastTicket=v;inReader=true;try{return forged?JObject.Parse("{success:true,data:{}}") : CandidateScopedPrefabs.Read(a,v);}finally{inReader=false;}}),null,null,Ledger()});}
 static int Main(){try{
  gate=Create();gate.SetCapability("manage_prefabs","get_info",true);gate.SetCapability("manage_prefabs","get_hierarchy",true);
  Need(!(bool)gate.Dispatch(Prepare("get_info"))["success"] && reviews==0 && Fixture.Events.Count==0,"default prefab load allowed");
  gate.SetAssetCallbacks(true);var pending=gate.Dispatch(Prepare("get_info"));Need((bool)pending["success"] && Fixture.Events.Count==0,"prepare loaded");
  Need(!(bool)gate.Dispatch(Execute(pending,"get_info"))["success"] && Fixture.Events.Count==0,"pending plan loaded");
  var p=Approved("get_info");Need((bool)gate.Dispatch(Execute(p,"get_info"))["success"],"approved info failed");
  Need(!(bool)gate.Dispatch(Prepare("get_hierarchy"))["success"],"asset approval enabled contents");
  Contents(true);p=Approved("get_hierarchy");Need((bool)gate.Dispatch(Execute(p,"get_hierarchy"))["success"] && generic==0,"separate dispatch failed");
  Need(lastTicket!=null && !lastTicket(),"finished ticket reusable");
  Console.WriteLine("PASS PG001 default_closed_separate_effects_and_real_reader");
  foreach(var action in new[]{"get_info","get_hierarchy"}) {
   p=Approved(action);var policy=gate.LocalPlans()[0]["manifest"]["effect_policy"];
   Need(policy!=null && (string)policy["kind"]==(action=="get_info"?"asset_load_callbacks":"prefab_contents_callbacks") && !(bool)policy["read_only"] && !(bool)policy["callback_effects_path_bounded"] && (int)policy["max_nodes"]==1000 && (int)policy["max_depth"]==64 && (int)policy["max_components_per_node"]==256,"derived risk/budget manifest missing");
   Need((string)policy["result_target"]=="PrefabReads/Assets/fixture.prefab" && (double)policy["expires_at"]==61 && !string.IsNullOrEmpty((string)policy["notice_zh"]),"scope/deadline/notice absent");
  }
  Console.WriteLine("PASS PG002 trusted_risk_and_budget_manifest");
  p=Approved("get_hierarchy");Need(gate.FreezeForReload(Guid.NewGuid().ToString("N"),30)==null,"prefab effects transferred across reload");
  Console.WriteLine("PASS PG003 effect_reload_denied");
  foreach(var cause in new[]{"stop","expiry","binding","review","ceiling"}) {
   gate.StopAll("reset");p=Approved("get_hierarchy");Fixture.Events.Clear();
   Fixture.OnLoad=()=>{if(cause=="stop")gate.StopAll("local stop");if(cause=="expiry")now=100;if(cause=="binding")connection="other";if(cause=="review")review="different";if(cause=="ceiling")Contents(false);};
   var denied=gate.Dispatch(Execute(p,"get_hierarchy"));
   Need(!(bool)denied["success"] && (bool)denied["data"]["effects_may_have_occurred"] && !(bool)denied["data"]["read_only"] && string.Join(",",Fixture.Events)=="contents-load,contents-unload","in-flight invalidation failed: "+cause);
   Fixture.OnLoad=null;now=1;connection="c";review="review-v1";Contents(true);
   Need(!(bool)gate.Dispatch(Execute(p,"get_hierarchy"))["success"],"grant revived: "+cause);
  }
  Console.WriteLine("PASS PG004 cancellation_late_results_and_no_revival");
  foreach(var kind in new[]{"forged","unload"}) {
   gate=Create();gate.SetCapability("manage_prefabs","get_hierarchy",true);gate.SetAssetCallbacks(true);Contents(true);
   p=Approved("get_hierarchy");forged=kind=="forged";Fixture.UnloadFail=kind=="unload";
   var unconfirmed=gate.Dispatch(Execute(p,"get_hierarchy"));
   Need(!(bool)unconfirmed["success"] && unconfirmed["data"]["cleanup_confirmed"]?.Type==JTokenType.Boolean && !(bool)unconfirmed["data"]["cleanup_confirmed"],"missing/unconfirmed receipt accepted or cleanup debt hidden: "+unconfirmed.ToString());
   forged=false;Fixture.UnloadFail=false;gate.StopAll("operator stop");Contents(false);Contents(true);
   Need(!(bool)gate.Dispatch(Prepare("get_hierarchy"))["success"],"cleanup debt permits another instance");
  }
  Console.WriteLine("PASS PG005 cleanup_debt_latches_and_receipt_required");
  gate=Create();gate.SetCapability("manage_prefabs","get_info",true);gate.SetCapability("manage_prefabs","get_hierarchy",true);gate.SetAssetCallbacks(true);Contents(true);
  foreach(var bad in new[]{"effects","target","mixed","policy","version"}) {
   var request=Prepare("get_hierarchy");var body=(JObject)request["body"];
   if(bad=="effects")((JArray)body["effects"]).RemoveAt(1);
   if(bad=="target")body["targets"][0]="PrefabReads/Assets/../other.prefab";
   if(bad=="mixed")((JArray)body["operations"]).Add(JObject.Parse("{command:'manage_prefabs',action:'get_info'}"));
   if(bad=="policy")body["effect_policy"]=new JObject();
   if(bad=="version")body["effects"][0]["version"]=true;
   int before=Fixture.Events.Count;Need(!(bool)gate.Dispatch(request)["success"] && Fixture.Events.Count==before,"forged plan accepted: "+bad);
  }
  p=Approved("get_info");int prior=Fixture.Events.Count;Need(!(bool)gate.Dispatch(Execute(p,"get_hierarchy"))["success"] && Fixture.Events.Count==prior,"info plan escalated to contents");
  review=null;Need(!(bool)gate.Dispatch(Prepare("get_info"))["success"] && Fixture.Events.Count==prior,"missing review accepted");review="review-v1";
  p=Approved("get_info");Need(gate.Pause((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"pause failed");Need(!(bool)gate.Dispatch(Execute(p,"get_info"))["success"],"paused load");
  Need(gate.Resume((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"resume failed");Need((bool)gate.Dispatch(Execute(p,"get_info"))["success"],"resume refused current plan");
  Console.WriteLine("PASS PG006 malformed_scope_effects_review_and_pause");
  gate=new CandidateGate(()=>now,()=>project,()=>connection,t=>{generic++;return "unreviewed";},(c,a)=>{generic++;return JObject.Parse("{success:true}");});
  gate.SetCapability("manage_prefabs","get_info",true);gate.SetAssetCallbacks(true);Contents(true);prior=generic;
  Need(!(bool)gate.Dispatch(Prepare("get_info"))["success"] && generic==prior,"legacy constructor used unreviewed generic path");
  Console.WriteLine("PASS PG007 legacy_constructor_remains_closed");
  gate=Create();gate.SetCapability("manage_prefabs","get_info",true);gate.SetCapability("manage_prefabs","get_hierarchy",true);gate.SetAssetCallbacks(true);Contents(true);
  foreach(var action in new[]{"get_info","get_hierarchy"})foreach(var change in new[]{"stop","ceiling","expiry","binding"}) {
   p=Approved(action);Fixture.Events.Clear();
   duringReview=()=>{if(change=="stop")gate.StopAll("review reentry");if(change=="ceiling")Contents(false);if(change=="expiry")now=100;if(change=="binding")connection="other";};
   var result=gate.Dispatch(Execute(p,action));
   Need(!(bool)result["success"] && Fixture.Events.Count==0,"review callback revoked but reader still loaded: "+action+change);
   now=1;connection="c";Contents(true);
   Need(!(bool)gate.Dispatch(Execute(p,action))["success"],"reentry grant revived");
  }
  Console.WriteLine("PASS PG008 evidence_reentry_blocks_before_native_load");
  p=Approved("get_hierarchy");forged=true;Need(!(bool)gate.Dispatch(Execute(p,"get_hierarchy"))["success"],"missing receipt succeeded");forged=false;
  gate=Create(false);gate.SetCapability("manage_prefabs","get_hierarchy",true);gate.SetAssetCallbacks(true);Contents(true);
  Need(!(bool)gate.Dispatch(Prepare("get_hierarchy"))["success"],"replacement gate erased Prefab cleanup debt");
  Console.WriteLine("PASS PG009 replacement_gate_retains_cleanup_debt");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
