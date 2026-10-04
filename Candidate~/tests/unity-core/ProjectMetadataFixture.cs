using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using MCPForUnity.Editor.Resources.Project;
namespace UnityEditorInternal {public static class InternalEditorUtility {public static string[] tags={"Untagged","Player"};}}
namespace UnityEditor {public static class PlayerSettings {public static int activeInputHandler=>2;}public static class EditorUserBuildSettings {public static string activeBuildTarget="StandaloneWindows64";}}
namespace UnityEditor.PackageManager {public sealed partial class PackageInfo {public static PackageInfo FindForAssetPath(string path)=>path=="Packages/com.unity.ugui"?new PackageInfo():null;}}
namespace UnityEngine.Rendering {public static class GraphicsSettings {public static object currentRenderPipeline;}}
internal static class ProjectMetadataFixture {
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="metadata-task",["plan_id"]=id,["body"]=body};
 public static object Native(string cmd,JObject args)=>cmd=="get_tags"?Tags.HandleCommand(args):cmd=="get_layers"?Layers.HandleCommand(args):ProjectInfo.HandleCommand(args);
 public static void Run(){
  int calls=0;double clock=100;
  var gate=new CandidateGate(()=>clock,()=>"fixture-project",()=>"fixture-connection",p=>"live-project",(cmd,args)=>{calls++;var r=JObject.FromObject(Native(cmd,args));return NativeReadContract.Valid(cmd,r,args)?r:new JObject{["success"]=false};});
  foreach(string cmd in new[]{"get_project_info","get_tags","get_layers"}){
   var manifest=new JObject{["operations"]=new JArray(new JObject{["command"]=cmd,["action"]="read"}),["targets"]=new JArray("ProjectMetadata"),["ttl_seconds"]=60};
   Check(!(bool)gate.Dispatch(Wire("prepare","",manifest))["success"],"metadata default open");gate.SetCapability(cmd,"read",true);
   JObject Ready(){var p=gate.Dispatch(Wire("prepare","",manifest));Check((bool)p["success"],"metadata prepare: "+p);Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");return p;}
   JObject Exec(JObject p,JObject args)=>gate.Dispatch(Wire("execute",(string)p["data"]["plan_id"],new JObject{["command"]=cmd,["params"]=args}));
   var plan=Ready();Check((bool)Exec(plan,new JObject())["success"],"native metadata missing "+cmd);
   foreach(string key in new[]{"action","refresh","path","approved"}){plan=Ready();int before=calls;Check(!(bool)Exec(plan,new JObject{[key]="unexpected"})["success"]&&calls==before,"metadata unexpected argument");}
   foreach(string scope in new[]{"Scenes","Console","Assets/Fixture.mat","ProjectMetadata/"}){var bad=(JObject)manifest.DeepClone();bad["targets"]=new JArray(scope);Check(!(bool)gate.Dispatch(Wire("prepare","",bad))["success"],"scope alias");}
   plan=Ready();string id=(string)plan["data"]["plan_id"],digest=(string)plan["data"]["digest"];Check(gate.Pause(id,digest),"pause");Check((string)Exec(plan,new JObject())["error"]=="plan_paused","paused metadata read");Check(gate.Resume(id,digest),"resume");Check((bool)Exec(plan,new JObject())["success"],"resumed metadata");
   gate.StopAll("fixture stop");Check(!(bool)Exec(plan,new JObject())["success"],"stopped metadata");
   var good=JObject.FromObject(Native(cmd,new JObject()));Check(NativeReadContract.Valid(cmd,good,new JObject()),"native metadata contract");
   var badResult=(JObject)good.DeepClone();badResult["data"]=new JObject{["unexpected"]=true};Check(!NativeReadContract.Valid(cmd,badResult,new JObject()),"wrong metadata shape");
   Check(!NativeReadContract.Valid(cmd,good,new JObject{["refresh"]=true}),"wrong request contract");
  }
  var tags=JObject.FromObject(Tags.HandleCommand(new JObject()));tags["data"]=new JArray(Enumerable.Repeat("x",1025));Check(!NativeReadContract.Valid("get_tags",tags,new JObject()),"oversize tags");
  var layers=JObject.FromObject(Layers.HandleCommand(new JObject()));foreach(string key in new[]{"32","-1","00","1.0"}){layers["data"]=new JObject{[key]="bad"};Check(!NativeReadContract.Valid("get_layers",layers,new JObject()),"invalid layer index");}
  var info=JObject.FromObject(ProjectInfo.HandleCommand(new JObject()));Check((string)info["data"]["activeInputHandler"]=="Both"&&(bool)info["data"]["packages"]["ugui"],"native project properties");info["data"]["projectRoot"]=new string('x',4097);Check(!NativeReadContract.Valid("get_project_info",info,new JObject()),"unbounded path");
  Console.WriteLine("PASS NS014 pinned project info/tags/layers; exact no-arg scope, output bounds and local lifecycle; Unity APIs doubled");
 }
}
