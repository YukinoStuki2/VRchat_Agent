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
 static void Main()
 {
  string connection=""; var timer=Stopwatch.StartNew(); int calls=0;
  using var backend=new WriteFixture();
  var material=new MaterialCandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,backend);
  material.SetCapability("copy",true); material.SetCapability("edit",true);
  var gate=new CandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,
   p=>"fixture-only-evidence-"+p,(c,p)=>JObject.FromObject(new SuccessResponse("fixture handler",new{fixture_only=true,call=++calls,command=c,path=(string)(p["materialPath"]??p["controllerPath"])})));
  gate.SetCapability("manage_material","get_material_info",true);
  gate.SetCapability("manage_animation","controller_get_info",true);
  string line;
  while((line=Console.ReadLine())!=null)
  {
   JObject input=JObject.Parse(line);JObject output;
   bool isMaterial=(string)input["route"]=="vrchat_agent_material_dispatch";
   if(input["fixture_connection"]!=null){connection=(string)input["fixture_connection"];output=new JObject{["fixture_ready"]=true};}
   else if(input["fixture_local_plans"]!=null){output=new JObject{["fixture_plans"]=isMaterial?material.LocalPlans():gate.LocalPlans()};}
   else if(input["fixture_approve_exact"] is JObject a){output=new JObject{["fixture_approved"]=isMaterial?material.Approve((string)a["plan_id"],(string)a["digest"]):gate.Approve((string)a["plan_id"],(string)a["digest"])};}
   else if(input["fixture_bytes"]!=null){output=new JObject{["candidate"]=backend.Value("Assets/candidate.mat"),["source"]=backend.Value("Assets/source.mat"),["writes"]=backend.Writes};}
   else if(input["fixture_local_approve"]!=null){var p=gate.LocalPlans();output=new JObject{["fixture_approved"]=p.Count==1&&gate.Approve((string)p[0]["plan_id"],(string)p[0]["digest"])};}
   else {
    var result=isMaterial?material.Dispatch((JObject)input["request"]):gate.Dispatch((JObject)input["request"]);
    object native=(bool?)result["success"]==true ? (object)new SuccessResponse("fixture transport",result["data"]):new ErrorResponse((string)result["error"],result["data"]);
    // Fixed upstream TransportCommandDispatcher success transport envelope.
    output=new JObject{["status"]="success",["result"]=JObject.FromObject(native)};
   }
   Console.WriteLine(output.ToString(Formatting.None));Console.Out.Flush();
  }
 }
}
