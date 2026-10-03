// TEST ONLY. Synthetic Unity peer, synthetic evidence, explicit fixture approval.
// Not included in the Unity package and must never be offered as a launcher.
using System;
using System.Diagnostics;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class WirePeer
{
 static void Trace(string phase){if(Environment.GetEnvironmentVariable("VRC_FIXTURE_TRACE")=="1")Console.Error.WriteLine("VRC_WIRE_PHASE:"+phase);}
 static void Main()
 {
  Trace("main");
  string connection=""; var timer=Stopwatch.StartNew(); int calls=0;
  using var backend=new WriteFixture(); Trace("fixture");
  var material=new MaterialCandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,backend);
  material.SetCapability("copy",true); material.SetCapability("edit",true);
  var gate=new CandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,
   p=>"fixture-only-evidence-"+p,(c,p)=> {
    if(c=="read_console"){var r=JObject.FromObject(MCPForUnity.Editor.Tools.ReadConsole.HandleCommand(p));return (bool?)r["success"]==true&&!NativeReadContract.Valid(c,r,p)?new JObject{["success"]=false}:r;}
    return JObject.FromObject(new SuccessResponse("fixture handler",new{fixture_only=true,call=++calls,command=c,path=(string)(p["materialPath"]??p["controllerPath"])}));
   });
  ConsoleNativeCases.Seed();
  gate.SetCapability("read_console","get",true);
  gate.SetCapability("manage_material","get_material_info",true);
  gate.SetCapability("manage_animation","controller_get_info",true);
  Trace("ready");
  if(Environment.GetEnvironmentVariable("VRC_FIXTURE_TRACE")=="1"){Console.WriteLine("{\"fixture_started\":true}");Console.Out.Flush();}
  string line;
  while((line=Console.ReadLine())!=null)
  {
   JObject input=JObject.Parse(line);JObject output;
   bool isMaterial=(string)input["route"]=="vrchat_agent_material_dispatch";
   if(input["fixture_connection"]!=null){connection=(string)input["fixture_connection"];output=new JObject{["fixture_ready"]=true};}
   else if(input["fixture_reload_material"]!=null){var records=material.ExportTaskRecords();material.StopAll("fixture reload");material=new MaterialCandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,backend);output=new JObject{["fixture_reloaded"]=material.ImportTaskRecords(records),["plans"]=material.LocalPlans(),["capabilities"]=new JArray()};if(material.Allows("edit")||material.Allows("copy"))throw new Exception("reload authority");}
   else if(input["fixture_material_records"]!=null){output=new JObject{["records"]=material.ExportTaskRecords()};}
   else if(input["fixture_material_capabilities"] is JArray capabilities){foreach(var op in capabilities)material.SetCapability((string)op,true);output=new JObject{["fixture_configured"]=true};}
   else if(input["fixture_recover_exact"] is JObject recovery){output=new JObject{["fixture_recovered"]=material.RecoverPending((string)recovery["plan_id"],(string)recovery["digest"],(string)recovery["record_id"],(string)recovery["record_digest"])};}
   else if(input["fixture_local_plans"]!=null){output=new JObject{["fixture_plans"]=isMaterial?material.LocalPlans():gate.LocalPlans()};}
   else if(input["fixture_approve_exact"] is JObject a){output=new JObject{["fixture_approved"]=isMaterial?material.Approve((string)a["plan_id"],(string)a["digest"]):gate.Approve((string)a["plan_id"],(string)a["digest"])};}
   else if(input["fixture_pause_exact"] is JObject pause){output=new JObject{["fixture_paused"]=isMaterial?material.Pause((string)pause["plan_id"],(string)pause["digest"]):gate.Pause((string)pause["plan_id"],(string)pause["digest"])};}
   else if(input["fixture_resume_exact"] is JObject resume){output=new JObject{["fixture_resumed"]=isMaterial?material.Resume((string)resume["plan_id"],(string)resume["digest"]):gate.Resume((string)resume["plan_id"],(string)resume["digest"])};}
   else if(input["fixture_bytes"]!=null){output=new JObject{["candidate"]=backend.Value(input["fixture_bytes"].Type==JTokenType.String && (string)input["fixture_bytes"]=="codex"?"Assets/codex-candidate.mat":"Assets/candidate.mat"),["source"]=backend.Value("Assets/source.mat"),["writes"]=backend.Writes};}
   else if(input["fixture_local_approve"]!=null){var p=gate.LocalPlans();output=new JObject{["fixture_approved"]=p.Count==1&&gate.Approve((string)p[0]["plan_id"],(string)p[0]["digest"])};}
   else {
    var result=isMaterial?material.Dispatch((JObject)input["request"]):gate.Dispatch((JObject)input["request"]);
    object native=(bool?)result["success"]==true ? (object)new SuccessResponse("fixture transport",result["data"]):new ErrorResponse((string)result["error"],result["data"]);
    // Fixed upstream TransportCommandDispatcher success transport envelope.
    output=new JObject{["status"]="success",["result"]=JObject.FromObject(native)};
   }
   Console.WriteLine(output.ToString(Formatting.None));Console.Out.Flush(); Trace("reply");
  }
  Trace("eof");
 }
}
