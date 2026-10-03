// Exact upstream method slices; Unity state/local approvals are doubles.
using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using MCPForUnity.Editor.Tools;
namespace UnityEngine {
 public struct Vector3 {}
 public static class Application { public static string dataPath=Path.Combine(Path.GetTempPath(),"nonexistent-native-fixture","Assets"); }
 public static class Mathf { public static int Clamp(int n,int a,int b)=>Math.Min(b,Math.Max(a,n));public static int Max(int a,int b)=>Math.Max(a,b); }
}
namespace UnityEngine.SceneManagement {
 public struct Scene {public string name,path;public int buildIndex,rootCount;public bool isDirty,isLoaded,valid;public bool IsValid()=>valid;public static bool operator==(Scene a,Scene b)=>a.name==b.name;public static bool operator!=(Scene a,Scene b)=>!(a==b);public override bool Equals(object o)=>o is Scene s&&this==s;public override int GetHashCode()=>name?.GetHashCode()??0;}
 public static class SceneManager {public static Scene[] Scenes={new Scene{name="Unsaved",path="",buildIndex=-1,rootCount=2,isDirty=true,isLoaded=true,valid=true},new Scene{name="Fixture",path="Assets/Fixture.unity",buildIndex=0,rootCount=0,isLoaded=false,valid=true}};public static int Reads;public static int sceneCount=>Scenes.Length;public static Scene GetSceneAt(int i){Reads++;return Scenes[i];}public static Scene GetActiveScene(){Reads++;return Scenes[0];}}
}
namespace UnityEditor.SceneManagement {public static class EditorSceneManager {public static UnityEngine.SceneManagement.Scene GetActiveScene()=>UnityEngine.SceneManagement.SceneManager.GetActiveScene();}}
namespace UnityEditor {
 public class EditorBuildSettingsScene {public string path;public Guid guid;public bool enabled;}
 public static class EditorBuildSettings {public static EditorBuildSettingsScene[] scenes={new EditorBuildSettingsScene{path="Assets/Fixture.unity",guid=Guid.Empty,enabled=true},new EditorBuildSettingsScene{path="Assets/Disabled.unity",guid=Guid.Empty,enabled=false}};}
}
namespace MCPForUnity.Runtime.Helpers {internal sealed class FixtureNamespace {}}
namespace MCPForUnity.Editor.Helpers {
 public static class McpLog {public static void Info(string s,bool always=false){}public static void Error(string s){}}
 public static class VectorParsing {public static UnityEngine.Vector3? ParseVector3(JToken t){if(t!=null)throw new Exception("ungranted vector");return null;}}
 public static class AssetPathUtility {public static string NormalizeSeparators(string s)=>throw new Exception("ungranted path");}
}
namespace MCPForUnity.Editor.Tools {[AttributeUsage(AttributeTargets.Class)]public sealed class McpForUnityToolAttribute:Attribute {public bool AutoRegister{get;set;}public McpForUnityToolAttribute(string name){}}}
internal static class SceneNativeCases {
 static string[] Actions={"get_active","get_build_settings","get_loaded_scenes"};
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="scene-task",["plan_id"]=id,["body"]=body};
 static JObject Manifest()=>new JObject{["operations"]=new JArray(Actions.Select(a=>new JObject{["command"]="manage_scene",["action"]=a})),["targets"]=new JArray("Scenes"),["ttl_seconds"]=60};
 static JObject Ready(CandidateGate gate){var p=gate.Dispatch(Wire("prepare","",Manifest()));Check((bool)p["success"],"prepare "+p);Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");return p;}
 static JObject Execute(CandidateGate gate,JObject p,JObject args)=>gate.Dispatch(Wire("execute",(string)p["data"]["plan_id"],new JObject{["command"]="manage_scene",["params"]=args}));
 static int Main(){try{
  int calls=0;double clock=100;
  var gate=new CandidateGate(()=>clock,()=>"fixture-project",()=>"fixture-connection",target=>"live-scenes-generation",(cmd,args)=>{calls++;var r=JObject.FromObject(ManageScene.HandleCommand(args));return (bool?)r["success"]==true&&!NativeReadContract.Valid(cmd,r,args)?new JObject{["success"]=false}:r;});
  Check(!(bool)gate.Dispatch(Wire("prepare","",Manifest()))["success"],"default open");
  foreach(string action in Actions)gate.SetCapability("manage_scene",action,true);
  var pending=gate.Dispatch(Wire("prepare","",Manifest()));Check(!(bool)Execute(gate,pending,new JObject{["action"]="get_active"})["success"]&&calls==0,"pending reached native");
  var plan=Ready(gate);
  foreach(string action in Actions){var result=Execute(gate,plan,new JObject{["action"]=action});Check((bool)result["success"],"native scene "+action+" "+result);if(action=="get_active")Check((bool)result["data"]["isDirty"]&&(string)result["data"]["path"]=="","dirty unsaved scene lost");if(action=="get_loaded_scenes")Check(((JArray)result["data"]["scenes"]).Count==2,"scene count");if(action=="get_build_settings")Check((int)result["data"][1]["buildIndex"]==1&&!(bool)result["data"][1]["enabled"],"build index is position incl disabled, not runtime index");}
  Check(calls==3,"unexpected native call");Console.WriteLine("PASS NS001 exact native metadata methods through final gate; Unity API doubled");
  foreach(string action in new[]{"load","save","create","get_hierarchy","scene_view_frame","validate","GET_ACTIVE","get_active "}){plan=Ready(gate);int before=calls;Check(!(bool)Execute(gate,plan,new JObject{["action"]=action})["success"]&&calls==before,"ungranted operation reached native");}
  foreach(string key in new[]{"path","name","autoRepair","buildIndex","additive","approved","cursor"}){plan=Ready(gate);int before=calls;Check(!(bool)Execute(gate,plan,new JObject{["action"]="get_active",[key]="unexpected"})["success"]&&calls==before,"extraneous argument reached native");}
  Console.WriteLine("PASS NS002 mutations, hierarchy, framing, aliases and extra args rejected before handler");
  plan=Ready(gate);string id=(string)plan["data"]["plan_id"],digest=(string)plan["data"]["digest"];
  Check(gate.Pause(id,digest),"pause");int prior=calls;Check((string)Execute(gate,plan,new JObject{["action"]="get_active"})["error"]=="plan_paused"&&prior==calls,"paused ran");Check(gate.Resume(id,digest),"resume");Check((bool)Execute(gate,plan,new JObject{["action"]="get_active"})["success"],"resumed denied");gate.StopAll("fixture stop");Check(!(bool)Execute(gate,plan,new JObject{["action"]="get_active"})["success"],"stopped reused");plan=Ready(gate);clock+=60;Check(!(bool)Execute(gate,plan,new JObject{["action"]="get_active"})["success"],"expired used");
  Console.WriteLine("PASS NS003 pause, resume, stop and absolute expiry preserve gate semantics");
  foreach(string action in Actions){var args=new JObject{["action"]=action};var good=JObject.FromObject(ManageScene.HandleCommand(args));Check(NativeReadContract.Valid("manage_scene",good,args),"native contract rejected");var bad=(JObject)good.DeepClone();bad["data"]=new JObject{["arbitrary"]="unexpected"};Check(!NativeReadContract.Valid("manage_scene",bad,args),"malformed native accepted");Check(!NativeReadContract.Valid("manage_scene",good,new JObject{["action"]="save"}),"cross-action response accepted");}
  Console.WriteLine("PASS NS004 native output/action contracts reject unknown payloads");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
