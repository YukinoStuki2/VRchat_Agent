// TEST ONLY: exact pinned readers with Unity API doubles; not actual Editor acceptance.
using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
namespace UnityEngine {
 public struct Rect {public float x,y,width,height;}
 public class GUIContent {public string text;public GUIContent(string text){this.text=text;}}
 public static class Resources {public static UnityEditor.EditorWindow[] Windows=new UnityEditor.EditorWindow[0];public static T[] FindObjectsOfTypeAll<T>()=>Windows.Cast<T>().ToArray();}
}
namespace UnityEditor {
 public enum Tool {Move,Custom} public enum PivotMode {Center,Pivot} public enum PivotRotation {Global,Local}
 public static class Tools {public static Tool current=Tool.Move;public static PivotMode pivotMode;public static PivotRotation pivotRotation;public static UnityEngine.Quaternion handleRotation;public static UnityEngine.Vector3 handlePosition;}
 public class EditorWindow:UnityEngine.Object {public UnityEngine.GUIContent titleContent=new UnityEngine.GUIContent("Fixture");public UnityEngine.Rect position;public static EditorWindow focusedWindow;}
 public static class Selection {public static UnityEngine.Object activeObject;public static UnityEngine.GameObject activeGameObject;public static UnityEngine.Transform activeTransform;public static UnityEngine.Object[] objects=new UnityEngine.Object[0];public static UnityEngine.GameObject[] gameObjects=new UnityEngine.GameObject[0];public static string[] assetGUIDs=new string[0];public static int count=>objects.Length;}
}
internal static class EditorMetadataFixture {
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="editor-metadata",["plan_id"]=id,["body"]=body};
 static object Native(string cmd,JObject args)=>cmd=="get_selection"?MCPForUnity.Editor.Resources.Editor.Selection.HandleCommand(args):cmd=="get_windows"?MCPForUnity.Editor.Resources.Editor.Windows.HandleCommand(args):cmd=="get_active_tool"?MCPForUnity.Editor.Resources.Editor.ActiveTool.HandleCommand(args):MCPForUnity.Editor.Resources.Editor.GetPrefabStage.HandleCommand(args);
 public static void Run(){
  UnityEditor.SceneManagement.PrefabStageUtility.Current=null;
  UnityEditor.Selection.objects=new UnityEngine.Object[]{new UnityEngine.Object{name="asset-metadata-only",Id=801},null};
  UnityEditor.Selection.activeObject=UnityEditor.Selection.objects[0];UnityEditor.Selection.assetGUIDs=new[]{"fixture-guid"};
  UnityEngine.Resources.Windows=new[]{new UnityEditor.EditorWindow{Id=901}};
  int calls=0;var gate=new CandidateGate(()=>100,()=>"fixture-project",()=>"fixture-connection",p=>"live-editor",(cmd,args)=>{calls++;var r=JObject.FromObject(Native(cmd,args));return NativeReadContract.Valid(cmd,r,args)?r:new JObject{["success"]=false};});
  foreach(string cmd in new[]{"get_selection","get_windows","get_active_tool","get_prefab_stage"}){
   var manifest=new JObject{["operations"]=new JArray(new JObject{["command"]=cmd,["action"]="read"}),["targets"]=new JArray("EditorMetadata"),["ttl_seconds"]=60};
   Check(!(bool)gate.Dispatch(Wire("prepare","",manifest))["success"],"editor metadata default open");
   gate.SetCapability(cmd,"read",true);
   JObject Ready(){var p=gate.Dispatch(Wire("prepare","",manifest));Check((bool)p["success"],"editor metadata prepare missing: "+p);Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");return p;}
   JObject Exec(JObject p,JObject args)=>gate.Dispatch(Wire("execute",(string)p["data"]["plan_id"],new JObject{["command"]=cmd,["params"]=args}));
   var plan=Ready();Check((bool)Exec(plan,new JObject())["success"],"native editor resource missing "+cmd);
   foreach(string key in new[]{"action","refresh","path","select","focus"}){plan=Ready();int before=calls;Check(!(bool)Exec(plan,new JObject{[key]=true})["success"]&&calls==before,"unexpected argument called handler");}
   foreach(string scope in new[]{"Scenes","Console","ProjectMetadata","Assets/Fixture.mat","EditorMetadata/"}){var bad=(JObject)manifest.DeepClone();bad["targets"]=new JArray(scope);Check(!(bool)gate.Dispatch(Wire("prepare","",bad))["success"],"scope alias");}
   plan=Ready();string id=(string)plan["data"]["plan_id"],digest=(string)plan["data"]["digest"];Check(gate.Pause(id,digest),"pause");Check((string)Exec(plan,new JObject())["error"]=="plan_paused","paused execution");Check(gate.Resume(id,digest),"resume");Check((bool)Exec(plan,new JObject())["success"],"resume read");
   gate.StopAll("fixture stop");Check(!(bool)Exec(plan,new JObject())["success"],"stopped read");
   var good=JObject.FromObject(Native(cmd,new JObject()));Check(NativeReadContract.Valid(cmd,good,new JObject()),"native response contract");
   var badResult=(JObject)good.DeepClone();badResult["data"]=new JObject{["unexpected"]=true};Check(!NativeReadContract.Valid(cmd,badResult,new JObject()),"wrong shape accepted");
   Check(!NativeReadContract.Valid(cmd,good,new JObject{["refresh"]=true}),"request extras accepted");
  }
  var selection=JObject.FromObject(Native("get_selection",new JObject()));Check((int)selection["data"]["count"]==2&&selection["data"]["objects"][1]["instanceID"].Type==JTokenType.Null,"native selection null slots");selection["data"]["count"]=1;Check(!NativeReadContract.Valid("get_selection",selection,new JObject()),"wrong selection count");
  var windows=JObject.FromObject(Native("get_windows",new JObject()));windows["data"]=new JArray(Enumerable.Range(0,257).Select(i=>windows["data"][0].DeepClone()));Check(!NativeReadContract.Valid("get_windows",windows,new JObject()),"window budget missing");
  UnityEditor.Tools.current=UnityEditor.Tool.Custom;var tool=JObject.FromObject(Native("get_active_tool",new JObject()));Check((string)tool["data"]["activeTool"]=="Unknown Custom Tool"&&NativeReadContract.Valid("get_active_tool",tool,new JObject()),"custom tool invokes no custom getter");
  UnityEditor.SceneManagement.PrefabStageUtility.Current=new UnityEditor.SceneManagement.PrefabStage{assetPath="Assets/Fixture.prefab",mode="InIsolation",prefabContentsRoot=new UnityEngine.GameObject("FixtureRoot",701),scene=new UnityEngine.SceneManagement.Scene{isDirty=true}};
  var stage=JObject.FromObject(Native("get_prefab_stage",new JObject()));Check((bool)stage["data"]["isOpen"]&&NativeReadContract.Valid("get_prefab_stage",stage,new JObject()),"open stage metadata");stage["data"]["unexpected"]=true;Check(!NativeReadContract.Valid("get_prefab_stage",stage,new JObject()),"stage extras");
  Console.WriteLine("PASS NS015 pinned editor selection/windows/tool/stage, exact scope, no args, bounds and lifecycle; Unity APIs doubled");
 }
}
