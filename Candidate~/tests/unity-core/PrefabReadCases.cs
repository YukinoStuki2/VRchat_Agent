// Explicit Unity API doubles; actual candidate reader is compiled by the verifier.
using System;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;


namespace UnityEngine {
 public class Object { public string name="fixture"; }
 public class Component:Object {}
 public sealed class GameObject:Object {
  public Transform transform; public bool activeSelf=true;
  public GameObject(string n){name=n;transform=new Transform(this);}
  public T[] GetComponents<T>() where T:Component {Fixture.ComponentCalls++;if(Fixture.ComponentsFail)throw new Exception("fixture component enumeration failed");if(Fixture.MissingComponent)return new T[1];if(Fixture.ManyComponents){var a=new T[300];for(int i=0;i<a.Length;i++)a[i]=(T)(Component)new Component();return a;}return new T[0];}
 }
 public sealed class Transform:Component,IEnumerable {
  public GameObject gameObject;public Transform parent;public List<Transform> children=new List<Transform>();
  public Transform(GameObject g){gameObject=g;}
  public int childCount {get{if(Fixture.TraversalFail)throw new Exception("fixture traversal failed");return children.Count;}}
  public Transform GetChild(int i)=>children[i];public IEnumerator GetEnumerator()=>children.GetEnumerator();
 }
}
namespace MCPForUnity.Runtime.Helpers { public static class Compatibility { public static int GetInstanceIDCompat(this GameObject value)=>1; } }
namespace MCPForUnity.Editor.Helpers { public static class McpLog {public static int Warnings;public static void Warn(string value){Warnings++;}public static void Error(string value){} } }
namespace UnityEditor {
 public enum PrefabAssetType {Regular,Variant}
 public static class AssetDatabase {
  public static T LoadAssetAtPath<T>(string path) where T:UnityEngine.Object {Fixture.Paths.Add(path);Fixture.Events.Add("asset-load");Fixture.Unrelated++;Fixture.OnLoad?.Invoke();return (T)(UnityEngine.Object)Fixture.Root;}
  public static string AssetPathToGUID(string path)=>Fixture.Guid;
  public static string GUIDToAssetPath(string guid)=>Fixture.MappedPath;
  public static string GetAssetPath(UnityEngine.Object obj)=>"Assets/fixture.prefab";
 }
 public static class PrefabUtility {
  public static GameObject LoadPrefabContents(string path){Fixture.Paths.Add(path);Fixture.Events.Add("contents-load");Fixture.Unrelated++;Fixture.OnLoad?.Invoke();if(Fixture.LoadFail)throw new Exception("fixture load failed after effect");return Fixture.Root;}
  public static void UnloadPrefabContents(GameObject obj){Fixture.Events.Add("contents-unload");Fixture.Unrelated++;if(Fixture.UnloadFail)throw new Exception("fixture unload failed after effect");}
  public static PrefabAssetType GetPrefabAssetType(GameObject obj)=>Fixture.Variant?PrefabAssetType.Variant:PrefabAssetType.Regular;
  public static GameObject GetCorrespondingObjectFromSource(GameObject obj){if(Fixture.VariantFail)throw new Exception("fixture variant resolver failed");return Fixture.ParentMissing?null:Fixture.Root;}
  public static bool IsAnyPrefabInstanceRoot(GameObject obj)=>Fixture.Nested;
 }
}
internal static class Fixture {
 internal static GameObject Root=new GameObject("Root");
 internal static List<string> Events=new List<string>(),Paths=new List<string>();
 internal static int Unrelated,ComponentCalls; internal static Action OnLoad=null; internal static string Guid=new string('a',32),MappedPath="Assets/fixture.prefab";
 internal static bool ComponentsFail=false,TraversalFail=false,LoadFail=false,UnloadFail=false,Variant=false,VariantFail=false,MissingComponent=false,ManyComponents=false,ParentMissing=false,Nested=false;
}
internal static class CandidatePrefabCases {
 static void Need(bool value,string reason){if(!value)throw new Exception(reason);}
 static JObject Call(string action,Func<bool> valid,string path="Assets/fixture.prefab") {
  var type=typeof(CandidatePrefabCases).Assembly.GetType("MCPForUnity.Editor.Tools.Prefabs.CandidateScopedPrefabs");
  Need(type!=null,"candidate_prefab_reader_missing");
  var method=type.GetMethod("Read");Need(method!=null,"candidate_prefab_read_entry_missing");
  return (JObject)method.Invoke(null,new object[]{new JObject{["action"]=action,["prefabPath"]=path},valid});
 }
 static int Main(string[] args){try{
  switch(args[0]) {
   case "PR001":
    var denied=Call("get_hierarchy",()=>false);Need(!(bool)denied["success"] && Fixture.Events.Count==0,"unapproved reader loaded");
    var result=Call("get_hierarchy",()=>true);
    Need((bool)result["success"] && string.Join(",",Fixture.Events)=="contents-load,contents-unload","owned prefab lifecycle failed");
    Need((bool)result["data"]["candidate_effects"]["cleanup_confirmed"] && !(bool)result["data"]["candidate_effects"]["read_only"],"missing cleanup/effect receipt");break;
   case "PR002":
    foreach(var failure in new[]{"component", "variant"}) {
     Fixture.ComponentsFail=failure=="component";Fixture.Variant=Fixture.VariantFail=failure=="variant";
     var incomplete=Call("get_info",()=>true);
     Need(!(bool)incomplete["success"] && (bool)incomplete["data"]["effects_may_have_occurred"],"helper swallowed metadata failure: "+failure);
    }
    break;
   case "PR003":
    foreach(var shape in new[]{"wide","deep"})foreach(var action in new[]{"get_info","get_hierarchy"}) {
     Fixture.Root=new GameObject("Root");var parent=Fixture.Root.transform;
     for(int i=0;i<(shape=="wide"?1001:70);i++){var g=new GameObject("N"+i);g.transform.parent=parent;parent.children.Add(g.transform);if(shape=="deep")parent=g.transform;}
     Fixture.ComponentCalls=0;Fixture.Events.Clear();var bounded=Call(action,()=>true);
     Need(!(bool)bounded["success"],"unbounded prefab traversal: "+shape+action);
     Need(Fixture.ComponentCalls<=1000,"budget checked after metadata enumeration");
     if(action=="get_hierarchy")Need(string.Join(",",Fixture.Events)=="contents-load,contents-unload" && (bool)bounded["data"]["candidate_effects"]["cleanup_confirmed"],"budget failure leaked contents");
    }
    break;
   case "PR004":
    foreach(var action in new[]{"get_info","get_hierarchy"}) {
     bool permitted=true;Fixture.Events.Clear();Fixture.ComponentCalls=0;Fixture.OnLoad=()=>permitted=false;
     var revoked=Call(action,()=>permitted);
     Need(!(bool)revoked["success"] && Fixture.ComponentCalls==0,"revoked load continued metadata execution: "+action);
     if(action=="get_hierarchy")Need(string.Join(",",Fixture.Events)=="contents-load,contents-unload" && (bool)revoked["data"]["candidate_effects"]["cleanup_confirmed"],"revocation blocked owned cleanup");
    }break;
   case "PR005":
    foreach(var failure in new[]{"load","unload","traversal"}) {
     Fixture.Events.Clear();Fixture.LoadFail=failure=="load";Fixture.UnloadFail=failure=="unload";Fixture.TraversalFail=failure=="traversal";
     var failed=Call("get_hierarchy",()=>true);var receipt=failed["data"]["candidate_effects"];
     Need(!(bool)failed["success"] && (bool)failed["data"]["effects_may_have_occurred"],"effect failure hidden");
     Need((bool)receipt["cleanup_confirmed"]==(failure=="traversal"),"cleanup debt falsely cleared: "+failure);
     Need(Fixture.Events.Count==(failure=="load"?1:2),"cleanup retried or unknown handle unloaded");
    }break;
   case "PR006":
    foreach(var path in new[]{"relative.prefab","assets/fixture.prefab","Assets/../fixture.prefab","Assets/fixture.prefab ","Assets/CON.prefab","Assets/fixture.asset","Assets//fixture.prefab"}) {
     Need(!(bool)Call("get_info",()=>true,path)["success"],"path coerced: "+path);
    }
    foreach(var action in new[]{"modify_contents","save_open_stage","open_stage","create_from_gameobject"})Need(!(bool)Call(action,()=>true)["success"],"write exposed");
    Need(Fixture.Events.Count==0,"invalid request caused native load");break;
   case "PR007":
    foreach(var action in new[]{"get_info","get_hierarchy"})foreach(var timing in new[]{"before","after"}) {
     Fixture.Events.Clear();Fixture.ComponentCalls=0;Fixture.Guid=new string('a',32);Fixture.MappedPath="Assets/fixture.prefab";Fixture.OnLoad=null;
     if(timing=="before")Fixture.MappedPath="Assets/other.prefab";else Fixture.OnLoad=()=>Fixture.Guid=new string('b',32);
     var changed=Call(action,()=>true);
     Need(!(bool)changed["success"] && Fixture.ComponentCalls==0,"GUID/path identity mismatch accepted: "+action+timing);
     Need(Fixture.Events.Count==(timing=="before"?0:action=="get_info"?1:2),"identity drift cleanup or preflight failed");
    }break;
   case "PR008":
    foreach(var action in new[]{"get_info","get_hierarchy"})foreach(var invalid in new[]{"missing","too_many"}) {
     Fixture.Events.Clear();Fixture.MissingComponent=invalid=="missing";Fixture.ManyComponents=invalid=="too_many";
     var bad=Call(action,()=>true);Need(!(bool)bad["success"],"incomplete/unbounded components accepted: "+invalid);
     if(action=="get_hierarchy")Need((bool)bad["data"]["candidate_effects"]["cleanup_confirmed"],"component failure leaked contents");
    }break;
   case "PR009":
    Fixture.ParentMissing=true;
    foreach(var action in new[]{"get_info","get_hierarchy"}) {
     Fixture.Variant=action=="get_info";Fixture.Nested=action=="get_hierarchy";
     Need(!(bool)Call(action,()=>true)["success"],"unresolved variant/nested source accepted");
    }break;
   case "PR010":
    Fixture.Root.name=new string('X',300000);
    foreach(var action in new[]{"get_info","get_hierarchy"})Need(!(bool)Call(action,()=>true)["success"],"unbounded response accepted");
    break;
   default:throw new Exception("unknown case");
  }
  Console.WriteLine("PASS "+args[0]+" candidate_prefab_reader");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
