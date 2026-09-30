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
 public static int Main(string[] args){try{ReadContinuity();Console.WriteLine("PASS PC001 read_plan_identity_survives_pause");MaterialContinuity();Console.WriteLine("PASS PC002 material_plan_and_postimage_survive_pause");ReadBoundaries();Console.WriteLine("PASS PC003 read_revalidation_lifecycle_boundaries");MaterialBoundaries();Console.WriteLine("PASS PC004 material_revalidation_lifecycle_boundaries");LocalOnlyAndSerialWriter();Console.WriteLine("PASS PC005 local_only_and_single_writer");return 0;}catch(Exception e){Console.WriteLine("FAIL "+e.GetBaseException().Message);return 1;}}
}
