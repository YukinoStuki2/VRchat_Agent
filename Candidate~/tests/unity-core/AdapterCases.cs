using System;
using System.IO;
using System.Reflection;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using MCPForUnity.Editor.Tools;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Services.Transport;
using MCPForUnity.Editor.Services.Transport.Transports;
using Yukino.VRChatAgent;
internal static class AdapterCases
{
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id) => new JObject { ["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]="connection-A",["client_id"]="client-A",["task_id"]="task-A",["plan_id"]=id,["body"]=new JObject()};
 static int Main()
 {
  string directory=Path.Combine(Path.GetTempPath(),"vragent-unity-adapter-"+Guid.NewGuid().ToString("N"));
  try {
   var host=Assembly.GetExecutingAssembly().GetType("Yukino.VRChatAgent.CandidateSession");
   Check(host!=null,"UA001 actual Unity adapter missing");
   Directory.CreateDirectory(Path.Combine(directory,"Assets")); Application.dataPath=Path.Combine(directory,"Assets");
   File.WriteAllText(Path.Combine(Application.dataPath,"Read.mat"),"fixture-disk");
   File.WriteAllText(Path.Combine(Application.dataPath,"Read.mat.meta"),"fixture-meta");
   var client=AdapterOwnedFixture.Begin();
   MCPServiceLocator.TransportManager.Client=client;
   var gate=(CandidateGate)host.GetField("Gate",BindingFlags.Static|BindingFlags.NonPublic).GetValue(null);
   var dispatch=Assembly.GetExecutingAssembly().GetType("Yukino.VRChatAgent.VrchatAgentDispatch").GetMethod("HandleCommand");
   Func<JObject,JObject> call=r=>JObject.FromObject(AdapterOwnedFixture.Call(r));
   gate.SetCapability("manage_material","get_material_info",true);
   Func<JObject> prepare=()=> {var r=Wire("prepare","");r["body"]=JObject.Parse("{\"operations\":[{\"command\":\"manage_material\",\"action\":\"get_material_info\"}],\"targets\":[\"Assets/Read.mat\"],\"ttl_seconds\":60}");return call(r);};
   var p=prepare();Check((bool)p["success"],"prepare "+p);
   Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");
   var execute=Wire("execute",(string)p["data"]["plan_id"]);
   execute["body"]=JObject.Parse("{\"command\":\"manage_material\",\"params\":{\"action\":\"get_material_info\",\"materialPath\":\"Assets/Read.mat\"}}");
   var result=call(execute);Check((bool)result["success"]&&CommandRegistry.Calls==1,"must delegate native handler "+result);
   Console.WriteLine("PASS UA001 adapter -> real core -> native-response serialization; Unity/handler doubled");
   AssetDatabase.Asset.Json="fixture-unsaved-change";
   Check(!(bool)call(execute)["success"]&&CommandRegistry.Calls==1,"unsaved state must stop");
   Console.WriteLine("PASS UA002 unsaved object evidence stops native call");
   p=prepare();Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve2");execute["plan_id"]=p["data"]["plan_id"];
   File.WriteAllText(Path.Combine(Application.dataPath,"Read.mat"),"external-disk-change");
   Check(!(bool)call(execute)["success"]&&CommandRegistry.Calls==1,"disk without import must stop");
   Console.WriteLine("PASS UA003 actual disk edit without AssetDatabase refresh detected");
   p=prepare();Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve3");execute["plan_id"]=p["data"]["plan_id"];
   client.State.SessionId="connection-B";EditorApplication.Tick();client.State.SessionId="connection-A";
   Check(!(bool)call(execute)["success"]&&CommandRegistry.Calls==1,"live client not manager cache");
   Console.WriteLine("PASS UA004 live transport session invalidates grant");
   AdapterOwnedFixture.Begin();
   p=prepare();AssemblyReloadEvents.Reload();Check(gate.LocalPlans().Count==0,"reload revokes");
   Console.WriteLine("PASS UA005 reload clears pending without startup/restore");
   var windowType=Assembly.GetExecutingAssembly().GetType("Yukino.VRChatAgent.CandidateWindow");
   Check(windowType!=null,"UA006 Chinese local approval window missing");
   var window=Activator.CreateInstance(windowType);var gui=windowType.GetMethod("OnGUI",BindingFlags.NonPublic|BindingFlags.Instance);
   AdapterOwnedFixture.Begin();
   p=prepare();GUILayout.NextButton="批准此清单";gui.Invoke(window,null);
   Check((bool)gate.LocalPlans()[0]["approved"],"button must approve");
   Check(EditorGUILayout.Labels.Exists(s=>s.Contains("Assets/Read.mat"))&&EditorGUILayout.Labels.Exists(s=>s.Contains((string)p["data"]["digest"])),"exact target/digest displayed");
   Console.WriteLine("PASS UA006 local UI displays and approves exact plan via doubled UI events");
   p=prepare();GUILayout.BeforeClick=()=> { prepare(); };GUILayout.NextButton="批准此清单";gui.Invoke(window,null);GUILayout.BeforeClick=null;
   Check(!(bool)gate.LocalPlans()[0]["approved"],"stale displayed plan must not approve replacement");
   Console.WriteLine("PASS UA007 stale display cannot approve replacement");
   return 0;
  } catch(Exception e){Console.Error.WriteLine("FAIL "+e);return 1;}
  finally {if(Directory.Exists(directory))Directory.Delete(directory,true);Check(!Directory.Exists(directory),"fixture residue");}
 }
}
