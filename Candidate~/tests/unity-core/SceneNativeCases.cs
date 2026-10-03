// Exact upstream method slices; Unity state/local approvals are doubles.
using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using MCPForUnity.Editor.Tools;
namespace UnityEngine {
 public struct Vector3 {public float x,y,z;}
 public struct Quaternion {public Vector3 eulerAngles;}
 public class Object {public string name;public int Id;public int GetInstanceID()=>Id;}
 public class Component : Object {public GameObject gameObject;}
 public class Transform : Component, System.Collections.Generic.IEnumerable<Transform> {
  public Transform parent;public Vector3 localPosition,localScale;public Quaternion localRotation;
  public System.Collections.Generic.List<Transform> Children=new System.Collections.Generic.List<Transform>();
  public int childCount=>Children.Count;
  public System.Collections.Generic.IEnumerator<Transform> GetEnumerator()=>Children.GetEnumerator();
  System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator()=>GetEnumerator();
 }
 public class GameObject : Object {
  public bool activeSelf=true,activeInHierarchy=true,isStatic;public string tag="Untagged";public int layer;
  public Transform transform;
  public GameObject(string name,int id){this.name=name;Id=id;transform=new Transform{name=name,Id=id+1000,gameObject=this};}
  public T[] GetComponents<T>() where T:Component =>new[]{transform}.OfType<T>().ToArray();
  public T[] GetComponentsInChildren<T>(bool includeInactive) where T:Component =>throw new Exception("ungranted name lookup");
 }
 public static class HierarchyFixture {
  public static GameObject[] Roots={new GameObject("Root",11),new GameObject("Second",22),new GameObject("Third",33)};
  public static GameObject Child=new GameObject("Inactive child",44){activeSelf=false,activeInHierarchy=false};
  static HierarchyFixture(){Child.transform.parent=Roots[0].transform;Roots[0].transform.Children.Add(Child.transform);}
 }
 public static class Application { public static string dataPath=Path.Combine(Path.GetTempPath(),"nonexistent-native-fixture","Assets"); }
 public static class Mathf { public static int Clamp(int n,int a,int b)=>Math.Min(b,Math.Max(a,n));public static int Max(int a,int b)=>Math.Max(a,b);public static int Min(int a,int b)=>Math.Min(a,b); }
}
namespace UnityEngine.SceneManagement {
 public struct Scene {public string name,path;public int buildIndex,rootCount;public bool isDirty,isLoaded,valid;public UnityEngine.GameObject[] GetRootGameObjects()=>UnityEngine.HierarchyFixture.Roots;public bool IsValid()=>valid;public static bool operator==(Scene a,Scene b)=>a.name==b.name;public static bool operator!=(Scene a,Scene b)=>!(a==b);public override bool Equals(object o)=>o is Scene s&&this==s;public override int GetHashCode()=>name?.GetHashCode()??0;}
 public static class SceneManager {public static Scene[] Scenes={new Scene{name="Unsaved",path="",buildIndex=-1,rootCount=2,isDirty=true,isLoaded=true,valid=true},new Scene{name="Fixture",path="Assets/Fixture.unity",buildIndex=0,rootCount=0,isLoaded=false,valid=true}};public static int Reads;public static int sceneCount=>Scenes.Length;public static Scene GetSceneAt(int i){Reads++;return Scenes[i];}public static Scene GetActiveScene(){Reads++;return Scenes[0];}}
}
namespace UnityEditor.SceneManagement {public class PrefabStage {public UnityEngine.SceneManagement.Scene scene;}public static class PrefabStageUtility {public static PrefabStage Current;public static PrefabStage GetCurrentPrefabStage()=>Current;}public static class EditorSceneManager {public static UnityEngine.SceneManagement.Scene GetActiveScene()=>UnityEngine.SceneManagement.SceneManager.GetActiveScene();}}
namespace UnityEditor {
 public class EditorBuildSettingsScene {public string path;public Guid guid;public bool enabled;}
 public static class EditorBuildSettings {public static EditorBuildSettingsScene[] scenes={new EditorBuildSettingsScene{path="Assets/Fixture.unity",guid=Guid.Empty,enabled=true},new EditorBuildSettingsScene{path="Assets/Disabled.unity",guid=Guid.Empty,enabled=false}};}
}
namespace MCPForUnity.Runtime.Helpers {public static class UnityObjectIdCompat {public static int GetInstanceIDCompat(this UnityEngine.Object obj)=>obj.Id;}}
namespace MCPForUnity.Editor.Helpers {
 public static class McpLog {public static void Info(string s,bool always=false){}public static void Error(string s){}public static void Debug(string s){}}
 public static class GameObjectLookup {
  public static UnityEngine.Object ResolveInstanceID(int id)=>UnityEngine.HierarchyFixture.Roots.FirstOrDefault(x=>x.Id==id) ?? (id==44?UnityEngine.HierarchyFixture.Child:null);
  public static System.Collections.Generic.List<int> SearchGameObjects(string a,string b,bool includeInactive,int maxResults)=>throw new Exception("ungranted path lookup");
  public static UnityEngine.GameObject FindById(int id)=>throw new Exception("ungranted path lookup");
 }
 public static class VectorParsing {public static UnityEngine.Vector3? ParseVector3(JToken t){if(t!=null)throw new Exception("ungranted vector");return null;}}
 public static class AssetPathUtility {public static string NormalizeSeparators(string s)=>throw new Exception("ungranted path");}
}
namespace MCPForUnity.Editor.Tools {[AttributeUsage(AttributeTargets.Class)]public sealed class McpForUnityToolAttribute:Attribute {public bool AutoRegister{get;set;}public McpForUnityToolAttribute(string name){}}}
internal static class SceneNativeCases {
 static string[] Actions={"get_active","get_build_settings","get_loaded_scenes"};
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="scene-task",["plan_id"]=id,["body"]=body};
 static JObject Manifest()=>new JObject{["operations"]=new JArray(Actions.Select(a=>new JObject{["command"]="manage_scene",["action"]=a})),["targets"]=new JArray("Scenes"),["ttl_seconds"]=60};
 static JObject Ready(CandidateGate gate,JObject manifest=null){var p=gate.Dispatch(Wire("prepare","",manifest??Manifest()));Check((bool)p["success"],"prepare "+p);Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");return p;}
 static JObject Execute(CandidateGate gate,JObject p,JObject args)=>gate.Dispatch(Wire("execute",(string)p["data"]["plan_id"],new JObject{["command"]="manage_scene",["params"]=args}));
 static void SevenReads(){
  var reads=new[]{
   new JObject{["command"]="manage_animation",["params"]=new JObject{["action"]="controller_get_info",["controllerPath"]="Assets/Fixture.controller"}},
   new JObject{["command"]="manage_material",["params"]=new JObject{["action"]="get_material_info",["materialPath"]="Assets/Fixture.mat"}},
   new JObject{["command"]="read_console",["params"]=new JObject{["action"]="get",["types"]=new JArray("error","warning","log"),["count"]=10,["pageSize"]=2,["format"]="json",["includeStacktrace"]=false}},
   new JObject{["command"]="manage_scene",["params"]=new JObject{["action"]="get_active"}},
   new JObject{["command"]="manage_scene",["params"]=new JObject{["action"]="get_build_settings"}},
   new JObject{["command"]="manage_scene",["params"]=new JObject{["action"]="get_loaded_scenes"}},
   new JObject{["command"]="manage_scene",["params"]=new JObject{["action"]="get_hierarchy",["pageSize"]=2}}};
  var manifest=new JObject{["operations"]=new JArray(reads.Select(r=>new JObject{["command"]=r["command"],["action"]=r["params"]["action"]})),
   ["targets"]=new JArray("Assets/Fixture.controller","Assets/Fixture.mat","Console","Scenes"),["ttl_seconds"]=60};
  var seen=new System.Collections.Generic.List<string>();
  var gate=new CandidateGate(()=>100,()=>"fixture-project",()=>"fixture-connection",target=>"fixture-evidence",
   (cmd,args)=>{seen.Add(cmd+"/"+(string)args["action"]);return new JObject{["success"]=true,["data"]=new JObject{["fixture_only"]=true}};});
  JObject Request(JObject p,JObject read)=>Wire("execute",(string)p["data"]["plan_id"],read);
  void Denied(JObject request,string reason){int before=seen.Count;var result=gate.Dispatch(request);Check(!(bool)result["success"]&&(string)result["error"]==reason&&seen.Count==before,"seven-read denial "+reason+": "+result);}
  foreach(JObject op in (JArray)manifest["operations"]){
   Check(!gate.Allows((string)op["command"],(string)op["action"]),"read capability default open");
   var single=(JObject)manifest.DeepClone();single["operations"]=new JArray(op.DeepClone());
   Denied(Wire("prepare","",single),"local_capability_disabled");
  }
  foreach(JObject op in (JArray)manifest["operations"])gate.SetCapability((string)op["command"],(string)op["action"],true);
  var plan=Ready(gate,manifest); // Regression: all seven valid read kinds must fit one plan.
  foreach(var read in reads)Check((bool)gate.Dispatch(Request(plan,read))["success"],"seven-read execution denied");
  Check(seen.SequenceEqual(reads.Select(r=>(string)r["command"]+"/"+(string)r["params"]["action"])),"missing or duplicate read execution");
  foreach(var read in reads){
   var pending=gate.Dispatch(Wire("prepare","",manifest));Check((bool)pending["success"],"seven-read pending failed");
   Denied(Request(pending,read),"local_approval_required");
  }
  foreach(JObject op in (JArray)manifest["operations"]){
   gate.SetCapability((string)op["command"],(string)op["action"],false);
   Denied(Wire("prepare","",manifest),"local_capability_disabled");
   gate.SetCapability((string)op["command"],(string)op["action"],true);
  }
  foreach(string field in new[]{"client_id","task_id","project_id","connection_id"}){
   plan=Ready(gate,manifest);var request=Request(plan,reads[0]);request[field]="other-scope";
   Denied(request,field=="client_id"||field=="task_id"?"plan_not_current":"binding_changed");
  }
  plan=Ready(gate,manifest);var outside=(JObject)reads[0].DeepClone();outside["params"]["controllerPath"]="Assets/Other.controller";
  Denied(Request(plan,outside),"outside_plan");
  plan=Ready(gate,manifest);var unknown=(JObject)reads[3].DeepClone();unknown["params"]["action"]="save";
  Denied(Request(plan,unknown),"operation_not_supported");
  var invalid=(JObject)manifest.DeepClone();invalid["operations"][6]["action"]="save";
  Denied(Wire("prepare","",invalid),"operation_not_supported");
  invalid=(JObject)manifest.DeepClone();invalid["operations"][6]=invalid["operations"][0].DeepClone();
  Denied(Wire("prepare","",invalid),"local_capability_disabled");
  invalid=(JObject)manifest.DeepClone();((JArray)invalid["operations"]).Add(invalid["operations"][0].DeepClone());
  Denied(Wire("prepare","",invalid),"invalid_manifest");
  invalid=(JObject)manifest.DeepClone();((JArray)invalid["targets"]).Add("Scenes");
  Denied(Wire("prepare","",invalid),"duplicate_target");
  plan=Ready(gate,manifest);var replacement=Ready(gate,manifest);
  Denied(Request(plan,reads[0]),"plan_mismatch");
  plan=Ready(gate,manifest);gate.StopAll("fixture revoke");
  Check(!gate.Approve((string)plan["data"]["plan_id"],(string)plan["data"]["digest"]),"old approval replay");
  foreach(var read in reads)Denied(Request(plan,read),"plan_not_current");
  Console.WriteLine("PASS NS008 seven read kinds fit one locally approved plan; default deny, scope, unknown, duplicate, replay and revoke stay closed; backend fixture");
 }
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
  Console.WriteLine("PASS NS004 native output/action contracts reject unknown payloads");
  Actions=Actions.Concat(new[]{"get_hierarchy"}).ToArray();gate.SetCapability("manage_scene","get_hierarchy",true);plan=Ready(gate);
  var rootArgs=new JObject{["action"]="get_hierarchy",["pageSize"]=2,["includeTransform"]=true};
  var first=Execute(gate,plan,rootArgs);Check((bool)first["success"],"hierarchy read missing: "+first);
  Check((int)first["data"]["total"]==3&&(string)first["data"]["next_cursor"]=="2"&&((JArray)first["data"]["items"]).Count==2,"root pagination");
  rootArgs["cursor"]=2;var last=Execute(gate,plan,rootArgs);Check((bool)last["success"]&&!(bool)last["data"]["truncated"]&&((JArray)last["data"]["items"]).Count==1,"last page");
  rootArgs["cursor"]=999;var empty=Execute(gate,plan,rootArgs);Check((bool)empty["success"]&&(int)empty["data"]["cursor"]==3&&((JArray)empty["data"]["items"]).Count==0,"native clamps cursor to total");
  var children=Execute(gate,plan,new JObject{["action"]="get_hierarchy",["pageSize"]=2,["parent"]=11});
  Check((bool)children["success"]&&(string)children["data"]["scope"]=="children"&&(int)children["data"]["items"][0]["instanceID"]==44&&!(bool)children["data"]["items"][0]["activeSelf"],"inactive child paging");
  Console.WriteLine("PASS NS005 exact native root/child paging, local transforms and cursor clamp through final gate");
  foreach(var change in new[]{new JObject{["pageSize"]="2"},new JObject{["pageSize"]=101},new JObject{["pageSize"]=true},
    new JObject{["cursor"]=-1},new JObject{["cursor"]=1000001},new JObject{["cursor"]="0"},new JObject{["parent"]="Root"},new JObject{["parent"]="11"},
    new JObject{["parent"]=0},new JObject{["parent"]=2147483648L},new JObject{["includeTransform"]="true"},new JObject{["maxDepth"]=2},new JObject{["path"]="Assets/X.unity"}}){
   plan=Ready(gate);var args=new JObject{["action"]="get_hierarchy",["pageSize"]=2};args.Merge(change);int count=calls;
   Check(!(bool)Execute(gate,plan,args)["success"]&&calls==count,"invalid hierarchy params reached handler "+args);
  }
  Console.WriteLine("PASS NS006 final gate rejects hierarchy coercions, global selectors, oversized pages and mixed arguments");
  var pageArgs=new JObject{["action"]="get_hierarchy",["pageSize"]=2};var goodPage=JObject.FromObject(ManageScene.HandleCommand(pageArgs));
  Check(NativeReadContract.Valid("manage_scene",goodPage,pageArgs),"baseline page contract");
  foreach(var key in new[]{"scope","cursor","pageSize","total","next_cursor","truncated","items"}){
   var bad=(JObject)goodPage.DeepClone();((JObject)bad["data"]).Remove(key);Check(!NativeReadContract.Valid("manage_scene",bad,pageArgs),"missing page field accepted");
  }
  foreach(var itemChange in new[]{new JObject{["instanceID"]=0},new JObject{["childCount"]=-1},new JObject{["childrenCursor"]="5"},new JObject{["unexpected"]=true},new JObject{["componentTypes"]=new JArray(42)}}){
   var bad=(JObject)goodPage.DeepClone();((JObject)bad["data"]["items"][0]).Merge(itemChange);Check(!NativeReadContract.Valid("manage_scene",bad,pageArgs),"malformed item accepted");
  }
  var duplicate=(JObject)goodPage.DeepClone();duplicate["data"]["items"][1]=duplicate["data"]["items"][0].DeepClone();Check(!NativeReadContract.Valid("manage_scene",duplicate,pageArgs),"duplicate IDs accepted");
  Console.WriteLine("PASS NS007 page and node contracts reject incomplete, malformed and duplicate output");SevenReads();return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
