// Characterization of pinned native reflection, not a replacement reader.
// Real CLR assembly resolution; Unity lifecycle/compilation APIs are doubles.
using System;
using System.IO;
using System.Reflection;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Tools;
using MCPForUnity.Runtime.Helpers;

namespace UnityEngine {
 public class Object {} public class Component:Object {} public class ScriptableObject:Object {}
 public class Transform:Component {
  static Transform(){ReflectionFixture.Counts.Constructors++;}
  public static int Property {get{ReflectionFixture.Counts.Getters++;return 42;}}
  public static int Method(int amount=3){ReflectionFixture.Counts.Methods++;return amount;}
  public const int Constant=42;
 }
 public class GameObject:Object{} public class Animator:Component{} public class RuntimeAnimatorController:Object{}
 public class AnimationClip:Object{} public class Material:Object{} public class Shader:Object{} public class SkinnedMeshRenderer:Component{}
 public struct Vector3{} public struct Quaternion{} public struct Color{}
}
namespace UnityEditor {
 [AttributeUsage(AttributeTargets.Class)] public sealed class InitializeOnLoadAttribute:Attribute {}
 [AttributeUsage(AttributeTargets.Method)] public sealed class InitializeOnLoadMethodAttribute:Attribute {}
 public static class AssemblyReloadEvents { public static event Action afterAssemblyReload; public static void Reload()=>afterAssemblyReload?.Invoke(); }
}
namespace MCPForUnity.Editor.Services { public static class EditorStateCache { public static bool GetActualIsCompiling()=>false; } }
namespace MCPForUnity.Editor.Tools {
 [AttributeUsage(AttributeTargets.Class)] public sealed class McpForUnityToolAttribute:Attribute {
  public string Description {get;set;} public bool AutoRegister {get;set;} public string Group {get;set;}
  public McpForUnityToolAttribute(string name){}
 }
}
namespace ReflectionFixture {
 public static class Counts { public static int Constructors,Getters,Methods; }
 public class LoadedTarget {
  static LoadedTarget(){Counts.Constructors++;}
  public static int Property {get {Counts.Getters++;return 42;}}
  public static int Method(){Counts.Methods++;return 42;}
  public const int Constant=42;
 }
 internal static class ReflectionBoundaryCases {
  static void Check(bool ok,string label){if(!ok)throw new Exception(label);}
  static void Gate() {
   int calls=0;string connection="connected";double now=1;
   var gate=new Yukino.VRChatAgent.CandidateGate(()=>now,()=>"project",()=>connection,_=>"metadata",(command,p)=>{calls++;return JObject.FromObject(CandidateScopedUnityReflect.HandleCommand(p));});
   Func<string,string,JObject,JObject> request=(kind,id,body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project",["connection_id"]=connection,["client_id"]="client",["task_id"]="task",["plan_id"]=id,["body"]=body};
   var manifest=JObject.Parse("{operations:[{command:'unity_reflect',action:'get_type'}],targets:['ApiMetadata'],ttl_seconds:60}");
   Check(!(bool)gate.Dispatch(request("prepare","",manifest))["success"],"capability default open");
   gate.SetCapability("unity_reflect","get_type",true);
   var pending=gate.Dispatch(request("prepare","",manifest));Check((bool)pending["success"],"metadata prepare failed: "+pending);
   var body=JObject.Parse("{command:'unity_reflect',params:{action:'get_type',class_name:'UnityEngine.Transform'}}");
   Check(!(bool)gate.Dispatch(request("execute",(string)pending["data"]["plan_id"],body))["success"] && calls==0,"unapproved metadata executed");
   foreach(string bad in new[]{"{action:'get_type'}","{action:'get_member',class_name:'Transform'}","{action:'search',scope:'unity'}","{action:'get_type',class_name:'Transform',query:null}","{action:'get_type',class_name:'Evil, Assembly'}","{action:'invoke',class_name:'Transform'}"}) {
    pending=gate.Dispatch(request("prepare","",manifest));Check((bool)pending["success"],"negative baseline prepare");
    string id=(string)pending["data"]["plan_id"];Check(gate.Approve(id,(string)pending["data"]["digest"]),"approval failed");
    Check((bool)gate.Dispatch(request("execute",id,body))["success"],"approved metadata failed");int before=calls;
    var invalid=(JObject)body.DeepClone();invalid["params"]=JObject.Parse(bad);
    Check(!(bool)gate.Dispatch(request("execute",id,invalid))["success"] && calls==before,"invalid metadata reached native");
   }
   pending=gate.Dispatch(request("prepare","",manifest));Check(gate.Approve((string)pending["data"]["plan_id"],(string)pending["data"]["digest"]),"stop baseline");
   gate.StopAll("stop");int stopped=calls;
   Check(!(bool)gate.Dispatch(request("execute",(string)pending["data"]["plan_id"],body))["success"]&&calls==stopped,"stopped metadata executed");
  }
  public static int Main(string[] args){
   try {
    string mode=args[0];
    // Warm only the real compatibility assembly-list helper, NOT the native type cache.
    // Unity is a stub here; this keeps its fixed engine-name probes outside the observer.
    UnityAssembliesCompat.GetLoadedAssemblies();
    int missingDependencyCallbacks=0,otherResolveCallbacks=0;
    ResolveEventHandler observer=(sender,e)=>{
     if(new AssemblyName(e.Name).Name=="ReflectionMissingDependency")missingDependencyCallbacks++;
     else otherResolveCallbacks++;
     return null;
    };
    if(mode!="metadata") {
     Check(File.Exists(args[1]),"broken fixture missing");
     Assembly.LoadFile(Path.GetFullPath(args[1]));
    }
    AppDomain.CurrentDomain.AssemblyResolve+=observer;
    JObject result;
    if(mode.StartsWith("scoped_",StringComparison.Ordinal)) {
     try {
      var query=mode=="scoped_search"?JObject.Parse("{action:'search',query:'Transform',scope:'all'}"):
       mode=="scoped_member"?JObject.Parse("{action:'get_member',class_name:'UnityEngine.Transform',member_name:'Property'}"):
       mode=="scoped_missing"?JObject.Parse("{action:'get_member',class_name:'UnityEngine.Transform',member_name:'Absent'}"):
       JObject.Parse("{action:'get_type',class_name:'UnityEngine.Transform'}");
      result=JObject.FromObject(CandidateScopedUnityReflect.HandleCommand(query));
      Check((bool?)result["success"]==true,"scoped native command failed");
      if(mode=="scoped_missing")Check((bool?)result["data"]?["found"]==false,"missing member fabricated");
      else if(mode=="scoped_search")Check((int?)result["data"]?["count"]==1,"fixed table search missing");
      else Check((bool?)result["data"]?["found"]==true,"scoped target absent");
      foreach(string name in new[]{"BrokenPlugin","ReflectionFixture.LoadedTarget","System.String","Evil, UnloadedAssembly"}) {
       var refused=JObject.FromObject(CandidateScopedUnityReflect.HandleCommand(new JObject{["action"]="get_type",["class_name"]=name}));
       Check((bool?)refused["data"]?["found"]==false,"outside fixed table resolved");
      }
      Check(missingDependencyCallbacks==0 && otherResolveCallbacks==0,"restricted reader still resolves assemblies");
      Check(Counts.Constructors==0&&Counts.Getters==0&&Counts.Methods==0,"restricted metadata executed target");
      if(mode=="scoped_gate") Gate();
     } finally {AppDomain.CurrentDomain.AssemblyResolve-=observer;}
     Console.WriteLine(new JObject{["mode"]=mode,["native_success"]=true,["missing_dependency_callbacks"]=missingDependencyCallbacks,
       ["other_resolution_callbacks"]=otherResolveCallbacks,["target_static_constructors"]=Counts.Constructors,["target_getters"]=Counts.Getters,["target_methods"]=Counts.Methods}.ToString(Newtonsoft.Json.Formatting.None));
     return 0;
    }
    try {
     JObject query;
     if(mode=="metadata")query=new JObject{["action"]="get_type",["class_name"]="ReflectionFixture.LoadedTarget"};
     else if(mode=="get_type")query=new JObject{["action"]="get_type",["class_name"]="System.String"};
     else if(mode=="get_member")query=new JObject{["action"]="get_member",["class_name"]="System.String",["member_name"]="NoSuchFixtureMember"};
     else if(mode=="search")query=new JObject{["action"]="search",["query"]="String",["scope"]="all"};
     else throw new Exception("unknown fixture mode");
     result=JObject.FromObject(UnityReflect.HandleCommand(query));
    } finally {AppDomain.CurrentDomain.AssemblyResolve-=observer;}
    Check((bool?)result["success"]==true,"native command failed");
    Check(Counts.Constructors==0&&Counts.Getters==0&&Counts.Methods==0,"metadata executed target code");
    if(mode=="metadata") {
     Check((bool?)result["data"]?["found"]==true,"target metadata absent");
     Check(missingDependencyCallbacks==0,"unexpected missing dependency");
    } else Check(missingDependencyCallbacks>0,"risk characterization not reproduced");
    Console.WriteLine(new JObject {
     ["mode"]=mode,["native_success"]=true,["missing_dependency_callbacks"]=missingDependencyCallbacks,
     ["other_resolution_callbacks"]=otherResolveCallbacks,["target_static_constructors"]=Counts.Constructors,
     ["target_getters"]=Counts.Getters,["target_methods"]=Counts.Methods,
     ["already_loaded_lookup_can_trigger_resolution_callback"]=mode!="metadata"
    }.ToString(Newtonsoft.Json.Formatting.None));
    return 0;
   } catch(Exception e){Console.Error.WriteLine(e.GetType().Name+": "+e.Message);return 1;}
  }
 }
}
