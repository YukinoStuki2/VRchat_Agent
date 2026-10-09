using Newtonsoft.Json.Linq;
#if !UNITY_EDITOR
namespace UnityEditor { public static class SessionState {
 public static readonly System.Collections.Generic.Dictionary<string,string> Values=new System.Collections.Generic.Dictionary<string,string>();
 public static string GetString(string k,string fallback)=>Values.TryGetValue(k,out var v)?v:fallback;
 public static void SetString(string k,string v){Values[k]=v;}
} }
#endif
namespace MCPForUnity.Editor.Tools {
#if !PLUGIN_NATIVE_ASSETS
 // Deliberately unavailable in unrelated fixtures; PluginSession compiles shipped reader.
 public static class CandidateScopedAssets {
  public static object Info(string path,System.Func<bool> ticket)=>throw new System.Exception("asset_reader_not_in_fixture");
  public static object Query(JObject args,System.Func<bool> ticket)=>throw new System.Exception("asset_reader_not_in_fixture");
 }
#endif
 public static class GetTestJob {public static int Calls;public static object HandleCommand(JObject args){Calls++;return new {success=true,data=new {job_id=(string)args["job_id"],status="running",mode="EditMode"}};}}

#if !SOURCE_NATIVE_TESTS
 public static class CandidateScopedUnityReflect { public static object HandleCommand(JObject args)=>throw new System.Exception("reflection native reader not included in this fixture"); }
 public static class ManageShader { public static object HandleCommand(JObject args)=>throw new System.Exception("source native handler not included in this fixture"); }
 public static class ManageScript {public static object HandleCommand(JObject p)=>throw new System.Exception("source read requires native fixture");}
#endif
 public static class ManagePackages {
  public static int Calls;
  public static object HandleCommand(JObject p){Calls++;return new {success=true,data=new {name=(string)p["package"],version="1.0.0",display_name="Fixture package",description="Local metadata fixture",source="Registry",resolved_path="/Fixture/Package",author=(string)null,dependencies=new object[0],dependency_count=0}};}
 }
}
namespace MCPForUnity.Editor.Resources.Project {
 public static class MetadataFixture {
  public static int Calls;
  public static object Read(string command){Calls++;return new {success=true,data=command=="get_tags"?(object)new[]{"Untagged"}:command=="get_layers"?new JObject{["0"]="Default"}:(object)new {projectRoot="/Fixture",projectName="Fixture",unityVersion="2022.3",platform="StandaloneWindows64",assetsPath="/Fixture/Assets",renderPipeline="BuiltIn",activeInputHandler="Old",packages=new {ugui=false,textmeshpro=false,inputsystem=false,uiToolkit=true,screenCapture=true}}};}
 }
 public static class ProjectInfo {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_project_info");}
 public static class Tags {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_tags");}
 public static class Layers {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_layers");}
}
namespace MCPForUnity.Editor.Resources.Editor {
 public static class MetadataFixture {
  public static int Calls;
  public static object Read(string command){Calls++;object data;
   if(command=="get_selection")data=new {activeObject=(string)null,activeGameObject=(string)null,activeTransform=(string)null,activeInstanceID=0,count=0,objects=new object[0],gameObjects=new object[0],assetGUIDs=new string[0]};
   else if(command=="get_windows")data=new object[0];
   else if(command=="get_active_tool"){var v=new{x=0,y=0,z=0};data=new{activeTool="Move",isCustom=false,pivotMode="Center",pivotRotation="Global",handleRotation=v,handlePosition=v};}
   else data=new {isOpen=false};
   return new {success=true,data};
  }
 }
 public static class Selection {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_selection");}
 public static class Windows {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_windows");}
 public static class ActiveTool {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_active_tool");}
 public static class GetPrefabStage {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_prefab_stage");}
}

namespace MCPForUnity.Editor.Resources.MenuItems {
 public static class GetMenuItems {public static int Calls;public static object HandleCommand(JObject p){Calls++;return new {success=true,data=new[]{"Tools/Fixture"}};}}
}

#if !WIRE_PEER_TESTS
// Clip APIs are Unity doubles; reader bytes are pinned upstream source.
namespace UnityEngine {
 public class AnimationCurve {public int length=2;}
 public class AnimationEvent {public float time,floatParameter;public string functionName,stringParameter;public int intParameter;}
}
namespace UnityEditor {
 public struct EditorCurveBinding {public string path,propertyName;public System.Type type;}
 public class AnimationClipSettings {public bool loopTime=true;}
 public static class AnimationUtility {
  public static EditorCurveBinding[] Bindings=System.Array.Empty<EditorCurveBinding>();
  public static UnityEngine.AnimationEvent[] Events=System.Array.Empty<UnityEngine.AnimationEvent>();
  public static AnimationClipSettings GetAnimationClipSettings(UnityEngine.AnimationClip clip)=>new AnimationClipSettings();
  public static EditorCurveBinding[] GetCurveBindings(UnityEngine.AnimationClip clip)=>Bindings;
  public static UnityEngine.AnimationCurve GetEditorCurve(UnityEngine.AnimationClip clip,EditorCurveBinding b)=>new UnityEngine.AnimationCurve();
  public static UnityEngine.AnimationEvent[] GetAnimationEvents(UnityEngine.AnimationClip clip)=>Events;
 }
}
#endif

#if !PLUGIN_NATIVE_ASSETS
namespace MCPForUnity.Editor.Tools.Prefabs {public static class CandidateScopedPrefabs {
 public static JObject Read(JObject args,System.Func<bool> ticket)=>throw new System.Exception("prefab_reader_not_in_fixture");
}}
#endif

#if !PLUGIN_NATIVE_ASSETS
namespace UnityEditor.TestTools.TestRunner {
 public sealed class CandidateDiscoveryOutcome {public bool Success,CleanupConfirmed;public string Error;public string[][] Rows;}
 public sealed class CandidateDiscoveryJob {
  public System.Threading.Tasks.Task<CandidateDiscoveryOutcome> Completion=>throw new System.Exception("discovery_reader_not_in_fixture");
  public static CandidateDiscoveryJob Begin(string mode,System.Func<bool> ticket)=>throw new System.Exception("discovery_reader_not_in_fixture");
 }
}
#endif
