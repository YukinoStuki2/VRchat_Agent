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
  var gate=new CandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,
   p=>"fixture-only-evidence-"+p,(c,p)=>JObject.FromObject(new SuccessResponse("fixture handler",new{fixture_only=true,call=++calls,command=c,path=(string)(p["materialPath"]??p["controllerPath"])})));
  gate.SetCapability("manage_material","get_material_info",true);
  gate.SetCapability("manage_animation","controller_get_info",true);
  string line;
  while((line=Console.ReadLine())!=null)
  {
   JObject input=JObject.Parse(line);JObject output;
   if(input["fixture_connection"]!=null){connection=(string)input["fixture_connection"];output=new JObject{["fixture_ready"]=true};}
   else if(input["fixture_local_plans"]!=null){output=new JObject{["fixture_plans"]=gate.LocalPlans()};}
   else if(input["fixture_local_approve"]!=null){var p=gate.LocalPlans();output=new JObject{["fixture_approved"]=p.Count==1&&gate.Approve((string)p[0]["plan_id"],(string)p[0]["digest"])};}
   else {
    var result=gate.Dispatch((JObject)input["request"]);
    object native=(bool?)result["success"]==true ? (object)new SuccessResponse("fixture transport",result["data"]):new ErrorResponse((string)result["error"],result["data"]);
    // Fixed upstream TransportCommandDispatcher success transport envelope.
    output=new JObject{["status"]="success",["result"]=JObject.FromObject(native)};
   }
   Console.WriteLine(output.ToString(Formatting.None));Console.Out.Flush();
  }
 }
}
