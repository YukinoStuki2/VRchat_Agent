// TEST ONLY local console approval peer: actual adapter/gates and pinned transport;
// Unity editor APIs/native handler side effects remain explicit doubles.
using System;
using System.IO;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using Yukino.VRChatAgent;
using MCPForUnity.Editor.Services.Transport;
internal static class OwnedGatePeer
{
 static async Task<int> Main(string[] args)
 {
  string old=Directory.GetCurrentDirectory();
  try
  {
   var ownedType=typeof(CandidateSession).GetField("ownedClient",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Static).FieldType;
   if(ownedType!=typeof(MCPForUnity.Editor.Services.Transport.Transports.CandidateOwnedWebSocketTransportClient))
    throw new Exception("OD002 adapter depends on patched shared type instead of additive owned type");
   if(typeof(CandidateSession).Assembly==ownedType.Assembly)
    throw new Exception("OD003 candidate and upstream transport must be compiled in separate assemblies");
   Directory.SetCurrentDirectory(args[2]);Application.dataPath=Path.Combine(args[2],"Assets");
   UnityEditor.AssetDatabase.Objects["Assets/Read.mat"]=new Material();
   CandidateSession.Gate.SetCapability("manage_material","get_material_info",true);
   MaterialCandidateSession.Gate.SetCapability("copy",true);MaterialCandidateSession.Gate.SetCapability("edit",true);
   if(!await CandidateSession.ConnectOwnedAsync(new Uri(args[0]),Environment.GetEnvironmentVariable("FIXTURE_UNITY_BEARER"),Convert.FromHexString(args[1])))return 3;
   Console.WriteLine("fixture_ready");Console.Out.Flush();
   string line;
   while((line=await Console.In.ReadLineAsync())!=null)
   {
    JObject answer;
    if(line=="approve-native")
    {
     var p=CandidateSession.Gate.LocalPlans();answer=new JObject{["approved"]=p.Count==1 && CandidateSession.Gate.Approve((string)p[0]["plan_id"],(string)p[0]["digest"])};
    }
    else if(line=="approve-material")
    {
     var p=MaterialCandidateSession.Gate.LocalPlans();answer=new JObject{["approved"]=p.Count==1 && MaterialCandidateSession.Gate.Approve((string)p[0]["plan_id"],(string)p[0]["digest"])};
    }
    else if(line=="inspect")answer=new JObject{["native_plans"]=CandidateSession.Gate.LocalPlans().Count,["material_plans"]=MaterialCandidateSession.Gate.LocalPlans().Count,["calls"]=MCPForUnity.Editor.Tools.CommandRegistry.Calls};
    else if(line=="stop")break;
    else throw new Exception("fixture_command_rejected");
    Console.WriteLine(answer.ToString(Newtonsoft.Json.Formatting.None));Console.Out.Flush();
   }
   await CandidateSession.StopOwnedAsync();
   if(CandidateSession.LiveConnection()!="" || CandidateSession.Gate.LocalPlans().Count!=0 || MaterialCandidateSession.Gate.LocalPlans().Count!=0 || OwnedFixtureObservation.GlobalCalls!=0) return 4;
   Console.WriteLine("fixture_clean");return 0;
  }
  finally{await CandidateSession.StopOwnedAsync();Directory.SetCurrentDirectory(old);}
 }
}
