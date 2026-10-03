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
   var flags=BindingFlags.Instance|BindingFlags.NonPublic;
   Check(!(bool)windowType.GetField("allowHermes",flags).GetValue(window) && !(bool)windowType.GetField("allowCodex",flags).GetValue(window),"new window client roles default closed");
   EditorGUILayout.NextToggle="允许本轮 Hermes 角色";gui.Invoke(window,null);
   Check((bool)windowType.GetField("allowHermes",flags).GetValue(window) && !(bool)windowType.GetField("allowCodex",flags).GetValue(window),"independent local client checkbox");
   var localOwner=host.GetField("localOwner",BindingFlags.Static|BindingFlags.NonPublic);
   using(var pending=new EditorOwnerProcess()) {
    localOwner.SetValue(null,pending);
    try {EditorGUILayout.NextToggle="允许本轮 Codex 角色";gui.Invoke(window,null);
     Check(!(bool)windowType.GetField("allowCodex",flags).GetValue(window),"running owner selection is immutable");
    } finally {localOwner.SetValue(null,null);EditorGUILayout.NextToggle=null;}
   }
   AdapterOwnedFixture.Begin();
   p=prepare();GUILayout.NextButton="批准此清单";gui.Invoke(window,null);
   Check((bool)gate.LocalPlans()[0]["approved"],"button must approve");
   Check(EditorGUILayout.Labels.Exists(s=>s.Contains("Assets/Read.mat"))&&EditorGUILayout.Labels.Exists(s=>s.Contains((string)p["data"]["digest"])),"exact target/digest displayed");
   execute["plan_id"]=p["data"]["plan_id"];int beforePauseCalls=CommandRegistry.Calls;
   GUILayout.NextButton="暂停此清单（不回退）";gui.Invoke(window,null);
   Check((bool?)gate.LocalPlans()[0]["paused"]==true && (string)call(execute)["error"]=="plan_paused" && CommandRegistry.Calls==beforePauseCalls,"UI pause must block handler");
   GUILayout.NextButton="核验后继续原清单";gui.Invoke(window,null);
   Check((string)gate.LocalPlans()[0]["plan_id"]==(string)p["data"]["plan_id"] && (bool?)call(execute)["success"]==true,"UI resume exact old plan");
   Console.WriteLine("PASS UA006 local UI displays and approves exact plan via doubled UI events");
   p=prepare();GUILayout.BeforeClick=()=> { prepare(); };GUILayout.NextButton="批准此清单";gui.Invoke(window,null);GUILayout.BeforeClick=null;
   Check(!(bool)gate.LocalPlans()[0]["approved"],"stale displayed plan must not approve replacement");
   Console.WriteLine("PASS UA007 stale display cannot approve replacement");
   string catalogDir=Path.Combine(directory,"Runtime~","catalog");Directory.CreateDirectory(catalogDir);
   string catalogPath=Path.Combine(catalogDir,"native-inventory.json");
   string catalogJson=File.ReadAllText(Path.Combine(Directory.GetCurrentDirectory(),"catalog","native-inventory.json"));
   File.WriteAllText(catalogPath,catalogJson);UnityEditor.PackageManager.PackageInfo.TestRoot=directory;
   int callsBeforeCatalog=CommandRegistry.Calls;gate.SetCapability("manage_material","get_material_info",false);
   EditorGUILayout.Labels.Clear();GUILayout.NextButton="展开原生操作目录";gui.Invoke(window,null);
   var catalogDoc=JObject.Parse(catalogJson);
   foreach(JObject tool in (JArray)catalogDoc["tools"])
    Check(EditorGUILayout.Labels.Exists(s=>s.Contains((string)tool["name_zh"])&&s.Contains((string)tool["name"])),"catalog row not visible: "+(string)tool["name"]);
   Check(!gate.Allows("manage_material","get_material_info")&&gate.LocalPlans().Count==0&&CommandRegistry.Calls==callsBeforeCatalog,"catalog granted/dispatched");
   GUILayout.NextButton="展开操作：manage_material";gui.Invoke(window,null);
   Check(EditorGUILayout.Labels.Exists(s=>s.Contains("set_material_shader_property")&&s.Contains("尚未接通")),"unsupported operation not marked");
   Console.WriteLine("PASS UA008 full shipped catalog shown without authority or native execution");
   EditorGUILayout.NextToggle="控制台读取与清除  read_console/get";
   GUILayout.NextButton="展开操作：read_console";gui.Invoke(window,null);
   Check(gate.Allows("read_console","get"),"console catalog switch must be live");
   gate.SetCapability("read_console","get",false);
   // Same real local adapter, only native registry and Unity API are doubles.
   AdapterOwnedFixture.Begin();gate.SetCapability("read_console","get",true);
   var cp=Wire("prepare","");cp["body"]=JObject.Parse("{\"operations\":[{\"command\":\"read_console\",\"action\":\"get\"}],\"targets\":[\"Console\"],\"ttl_seconds\":60}");
   var consolePending=call(cp);Check((bool)consolePending["success"],"UA009 Console scope must not be treated as asset path: "+consolePending);
   Check(gate.Approve((string)consolePending["data"]["plan_id"],(string)consolePending["data"]["digest"]),"console approval");
   var cr=Wire("execute",(string)consolePending["data"]["plan_id"]);
   cr["body"]=JObject.Parse("{\"command\":\"read_console\",\"params\":{\"action\":\"get\",\"types\":[\"error\"],\"count\":10,\"pageSize\":20,\"cursor\":0,\"format\":\"json\",\"includeStacktrace\":true}}");
   var originalHandler=CommandRegistry.Implementation;
   try {
    CommandRegistry.Implementation=(cmd,a)=>new MCPForUnity.Editor.Helpers.SuccessResponse("Retrieved 1 log entries.",
      new {cursor=0,pageSize=20,nextCursor=(string)null,truncated=false,total=1,items=new[]{new {type="Error",message="fixture compiler error",file="Assets/Fixture.cs",line=3,stackTrace=(string)null}}});
    Check((bool)call(cr)["success"],"native console response rejected");
   } finally {CommandRegistry.Implementation=originalHandler;}
   gate.SetCapability("read_console","get",false);
   Console.WriteLine("PASS UA009 explicit Console scope through local adapter; logs remain live, native reader doubled");
   AdapterOwnedFixture.Begin();
   string sceneName="";foreach(JObject row in (JArray)catalogDoc["tools"])if((string)row["name"]=="manage_scene")sceneName=(string)row["name_zh"];
   EditorGUILayout.NextToggle=sceneName+"  manage_scene/get_active";GUILayout.NextButton="展开操作：manage_scene";gui.Invoke(window,null);
   Check(gate.Allows("manage_scene","get_active"),"scene catalog switch not wired");
   var sp=Wire("prepare","");sp["body"]=JObject.Parse("{\"operations\":[{\"command\":\"manage_scene\",\"action\":\"get_active\"}],\"targets\":[\"Scenes\"],\"ttl_seconds\":60}");
   var scenePending=call(sp);Check((bool)scenePending["success"],"UA010 Scenes is a live scope, not an asset: "+scenePending);
   Check(gate.Approve((string)scenePending["data"]["plan_id"],(string)scenePending["data"]["digest"]),"scene approval");
   var sr=Wire("execute",(string)scenePending["data"]["plan_id"]);sr["body"]=JObject.Parse("{\"command\":\"manage_scene\",\"params\":{\"action\":\"get_active\"}}");
   originalHandler=CommandRegistry.Implementation;
   try {
    CommandRegistry.Implementation=(cmd,a)=>new MCPForUnity.Editor.Helpers.SuccessResponse("scene fixture",new {name="Unsaved",path="",buildIndex=-1,isDirty=true,isLoaded=true,rootCount=3});
    Check((bool)call(sr)["success"],"scene response rejected");int callsBeforeCompile=CommandRegistry.Calls;
    EditorApplication.isCompiling=true;EditorApplication.Tick();Check(!(bool)call(sr)["success"]&&CommandRegistry.Calls==callsBeforeCompile,"compilation reached native");
    EditorApplication.isCompiling=false;Check(!(bool)call(sr)["success"],"compile auto-restored grant");
   } finally {EditorApplication.isCompiling=false;CommandRegistry.Implementation=originalHandler;gate.SetCapability("manage_scene","get_active",false);}
   Console.WriteLine("PASS UA010 scene scope/catalog/compile readiness through actual local adapter, Unity APIs doubled");
   EditorGUILayout.NextToggle=sceneName+"  manage_scene/get_hierarchy";gui.Invoke(window,null);
   Check(gate.Allows("manage_scene","get_hierarchy"),"hierarchy local catalog switch");
   sp["body"]["operations"][0]["action"]="get_hierarchy";
   originalHandler=CommandRegistry.Implementation;
   try {
    CommandRegistry.Implementation=(cmd,a)=>new MCPForUnity.Editor.Helpers.SuccessResponse("children fixture",new {scope="children",cursor=0,pageSize=2,next_cursor=(string)null,truncated=false,total=0,items=new object[0]});
    Action<bool,string> parentCase=(allowed,why)=>{
     var hp=call(sp);Check((bool)hp["success"],"hierarchy prepare");Check(gate.Approve((string)hp["data"]["plan_id"],(string)hp["data"]["digest"]),"hierarchy approve");
     var hq=Wire("execute",(string)hp["data"]["plan_id"]);hq["body"]=JObject.Parse("{\"command\":\"manage_scene\",\"params\":{\"action\":\"get_hierarchy\",\"pageSize\":2,\"parent\":123}}");
     int count=CommandRegistry.Calls;Check((bool)call(hq)["success"]==allowed,why);Check(CommandRegistry.Calls==count+(allowed?1:0),"denial must precede native read: "+why);
    };
    var current=UnityEditor.SceneManagement.EditorSceneManager.Current;
    var go=new GameObject{scene=current};MCPForUnity.Editor.Helpers.GameObjectLookup.Fixture=go;
    parentCase(true,"same active scene permitted");
    go.Persistent=true;parentCase(false,"persistent prefab asset must not be a live hierarchy parent");go.Persistent=false;
    go.scene=new UnityEngine.SceneManagement.Scene{Id=2,isLoaded=true};parentCase(false,"other scene rejected");
    go.scene=new UnityEngine.SceneManagement.Scene{Id=1,isLoaded=false};parentCase(false,"unloaded rejected");
    go.scene=default;parentCase(false,"invalid scene rejected");
    MCPForUnity.Editor.Helpers.GameObjectLookup.Fixture=new UnityEngine.Object();parentCase(false,"component or unknown object rejected");
    MCPForUnity.Editor.Helpers.GameObjectLookup.Fixture=null;parentCase(false,"stale ID rejected");
    var stage=new UnityEngine.SceneManagement.Scene{Id=3,isLoaded=true};UnityEditor.SceneManagement.PrefabStageUtility.Current=new UnityEditor.SceneManagement.PrefabStage{scene=stage};
    go.scene=stage;MCPForUnity.Editor.Helpers.GameObjectLookup.Fixture=go;parentCase(true,"prefab stage exact parent");
    go.scene=current;parentCase(false,"main scene not stage parent");
   } finally {CommandRegistry.Implementation=originalHandler;UnityEditor.SceneManagement.PrefabStageUtility.Current=null;MCPForUnity.Editor.Helpers.GameObjectLookup.Fixture=null;gate.SetCapability("manage_scene","get_hierarchy",false);}
   Console.WriteLine("PASS UA011 final adapter confines native hierarchy parent to nonpersistent GameObject in exact active scene/stage");
   return 0;
  } catch(Exception e){Console.Error.WriteLine("FAIL "+e);return 1;}
  finally {if(Directory.Exists(directory))Directory.Delete(directory,true);Check(!Directory.Exists(directory),"fixture residue");}
 }
}
