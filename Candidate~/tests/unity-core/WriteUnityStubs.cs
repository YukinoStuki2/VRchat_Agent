// Explicit Unity API doubles: compiling these is NOT compiling inside Unity.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
namespace UnityEngine {
 public class Object { public string name, Json = "fixture-memory"; public int GetInstanceID() => 1; }
 public class TextAsset : Object {}
 public class DefaultAsset : Object {}
 public class Texture : Object {}
 public class Shader : Object {}
 public class GameObject : Object { public UnityEngine.SceneManagement.Scene scene=new UnityEngine.SceneManagement.Scene(); public Renderer Renderer;public T[] GetComponents<T>() where T:Object=>new[]{Renderer as T};public T GetComponent<T>() where T:Object=>Renderer as T; }
 public class Renderer : Object { public GameObject gameObject;public Material[] sharedMaterials=new Material[1]; }
 public class MeshRenderer : Renderer {}
 public class SkinnedMeshRenderer : Renderer {}
 public class Material : Object { public Shader shader=new Shader(); public bool HasProperty(string name)=>true; public Texture Texture;public string[] GetTexturePropertyNames()=>Texture==null?Array.Empty<string>():new[]{"_MainTex"};public Texture GetTexture(string name)=>Texture;public void SetTexture(string name,Texture tex){Texture=tex;}public Color GetColor(string name)=>new Color();public Vector4 GetVector(string name)=>new Vector4();public float GetFloat(string name)=>0.7f; }
 public static class Application { public static string dataPath; }
 public struct Vector2 {}
 public struct Color { public float r,g,b,a; }
 public struct Vector4 { public float x,y,z,w; }
 public static class GUILayout {
  public static string NextButton; public static Action BeforeClick;
  public static bool Button(string text) {
   if(UnityEditor.EditorGUI.Disabled || NextButton != text)return false;
   NextButton=null; BeforeClick?.Invoke();return true;
  }
 }
}
namespace UnityEngine.SceneManagement { public class Scene { public bool isLoaded=true,isDirty;public string path="Assets/test.unity";public bool IsValid()=>true; } }
namespace UnityEditor.SceneManagement { public static class EditorSceneManager { public static Action sceneDirtied;public static bool MarkSceneDirty(UnityEngine.SceneManagement.Scene s){s.isDirty=true;return true;} } }
namespace UnityEditor {
 [AttributeUsage(AttributeTargets.Class)] public class InitializeOnLoadAttribute : Attribute {}
 [AttributeUsage(AttributeTargets.Method)] public class MenuItemAttribute : Attribute { public MenuItemAttribute(string s) {} }
 public enum MessageType { Info, Warning, Error }
 public enum PlayModeStateChange { EnteredEditMode, ExitingEditMode }
 public class EditorWindow { public static T GetWindow<T>(string title) where T:new() => new T(); public void Repaint(){} }
 public static class EditorApplication {
  public static bool isCompiling, isUpdating, isPlayingOrWillChangePlaymode; public static double timeSinceStartup = 100;
  public static event Action update, quitting; public static event Action<PlayModeStateChange> playModeStateChanged;
  public static void Tick() => update?.Invoke(); public static void Quit() => quitting?.Invoke(); public static void Play() => playModeStateChanged?.Invoke(PlayModeStateChange.ExitingEditMode);
 }
 public static class AssemblyReloadEvents { public static event Action beforeAssemblyReload; public static void Reload() => beforeAssemblyReload?.Invoke(); }
 public static class AssetDatabase {
  public static UnityEngine.Object Asset = new UnityEngine.Material();
  public static readonly Dictionary<string,UnityEngine.Object> Objects = new Dictionary<string,UnityEngine.Object>();
  public static int Saves,Copies,Refreshes;public static void Refresh(ImportAssetOptions o){Refreshes++;}public static string GenerateUniqueAssetPath(string p)=>p+"copy";public static bool CopyAsset(string a,string b){Copies++;System.IO.File.Copy(a,b);System.IO.File.WriteAllText(b+".meta","native-new-guid");Objects[b]=new UnityEngine.Material();return true;}
  public static string[] Dependencies=Array.Empty<string>();
  public static string[] GetDependencies(string path,bool recursive)=>Dependencies;
  public static Type GetMainAssetTypeAtPath(string path)=>Objects.TryGetValue(path,out var o)?o.GetType():typeof(UnityEngine.Material);
  public static T LoadAssetAtPath<T>(string path) where T:UnityEngine.Object => Objects.TryGetValue(path,out var o)?o as T:null;
  public static void SaveAssetIfDirty(UnityEngine.Object o){Saves++;System.IO.File.WriteAllText(GetAssetPath(o),UnityEditor.EditorJsonUtility.ToJson(o));}
  public static bool IsValidFolder(string path)=>System.IO.Directory.Exists(path);
  public static string GetAssetPath(UnityEngine.Object obj){foreach(var p in Objects)if(ReferenceEquals(p.Value,obj))return p.Key;return "Assets/source.mat";}
  public static string AssetPathToGUID(string path) => System.IO.File.Exists(path)?"fixture-guid":"";
  public static string GetAssetDependencyHash(string path) => "fixture-dependency-hash";
  public static UnityEngine.Object[] LoadAllAssetsAtPath(string path) => new[] { Objects.TryGetValue(path,out var o)?o:Asset };
 }
 public struct GlobalObjectId { public static Dictionary<string,UnityEngine.Object> Objects=new Dictionary<string,UnityEngine.Object>();string id;public static bool TryParse(string s,out GlobalObjectId value){value=new GlobalObjectId{id=s};return Objects.ContainsKey(s);}public static UnityEngine.Object GlobalObjectIdentifierToObjectSlow(GlobalObjectId id)=>Objects[id.id];public static GlobalObjectId GetGlobalObjectIdSlow(UnityEngine.Object o){foreach(var p in Objects)if(ReferenceEquals(p.Value,o))return new GlobalObjectId{id=p.Key};return default;} public override string ToString()=>id; }
 public static class EditorUtility { public static bool IsPersistent(UnityEngine.Object o)=>false;public static UnityEngine.Object Dirty;public static bool IsDirty(UnityEngine.Object o)=>ReferenceEquals(o,Dirty);public static void SetDirty(UnityEngine.Object o){}public static void ClearDirty(UnityEngine.Object o){} }
 public static class PrefabUtility { public static bool IsPartOfPrefabAsset(UnityEngine.Object o)=>false;public static void RecordPrefabInstancePropertyModifications(UnityEngine.Object o){} }
 public static class Undo { public static Action postprocessModifications,willFlushUndoRecord;public static void RecordObject(UnityEngine.Object o,string s){} }
 public static class ObjectChangeEvents { public static Action changesPublished; }
 public enum ImportAssetOptions {ForceSynchronousImport}
 public static class ShaderUtil {public enum ShaderPropertyType{Color,Vector,Float,Range,TexEnv}public static int GetPropertyCount(UnityEngine.Shader s)=>0;public static string GetPropertyName(UnityEngine.Shader s,int i)=>"";public static string GetPropertyDescription(UnityEngine.Shader s,int i)=>"";public static ShaderPropertyType GetPropertyType(UnityEngine.Shader s,int i)=>ShaderPropertyType.Float;}
 public class AssetPostprocessor {}
 public class AssetModificationProcessor {}
 public static class TypeCache { public static bool Unknown;public static IEnumerable<Type> GetTypesDerivedFrom<T>()=>Unknown?new[]{typeof(WriteUnityCases)}:Array.Empty<Type>(); }
 public static class EditorJsonUtility { public static string ToJson(UnityEngine.Object obj) => obj.Json;public static void FromJsonOverwrite(string json,UnityEngine.Object obj){obj.Json=json;} }
 public static class EditorGUILayout {
  public static int IntField(string label,int value)=>value;
  public static string NextText; public static string TextField(string label,string value) {var result=NextText??value;NextText=null;return result;}
  public static readonly List<string> Labels = new List<string>();
  public static void HelpBox(string s, MessageType t){} public static bool ToggleLeft(string s, bool v)=>v;
  public static void LabelField(string a, string b=""){Labels.Add(a+":"+b);} public static void Space(){}
  public static UnityEngine.Vector2 BeginScrollView(UnityEngine.Vector2 v)=>v; public static void EndScrollView(){}
 }
 public static class EditorGUI { public static bool Disabled; public static void BeginDisabledGroup(bool v){Disabled=v;} public static void EndDisabledGroup(){Disabled=false;} }
}
namespace MCPForUnity.Editor.Helpers {
 internal static class ProjectIdentityUtility { public static string GetProjectHash()=>"project-A"; }
 public static class HttpEndpointUtility { public static string BaseUrl="http://127.0.0.1:18081"; public static string GetBaseUrl()=>BaseUrl; public static bool IsRemoteScope()=>false; }
}
namespace MCPForUnity.Editor.Services.Transport {
 public enum TransportMode { Http, Stdio }
 public sealed class TransportState { public bool IsConnected; public string SessionId, Details; }
 public interface IMcpTransportClient { bool IsConnected {get;} TransportState State {get;} }
 public class TransportManager { public IMcpTransportClient Client; public IMcpTransportClient GetClient(TransportMode mode)=>Client; }
}
namespace MCPForUnity.Editor.Services.Transport.Transports {
 public partial class WebSocketTransportClient : MCPForUnity.Editor.Services.Transport.IMcpTransportClient {
  public bool IsConnected {get;set;} public MCPForUnity.Editor.Services.Transport.TransportState State {get;set;}
 }
}
namespace MCPForUnity.Editor.Services {
 public static class MCPServiceLocator { public static Transport.TransportManager TransportManager = new Transport.TransportManager(); }
}
namespace MCPForUnity.Editor.Tools {
 [AttributeUsage(AttributeTargets.Class)] public class McpForUnityToolAttribute : Attribute {
  public string Description {get;set;} public bool AutoRegister {get;set;} public string Group {get;set;}
  public McpForUnityToolAttribute(string name){}
 }
 public static class CommandRegistry {
  public static Func<string,JObject,object> RawOverride;
  // Same shape as pinned ManageMaterial.GetMaterialInfo's empty property list.
  // Unknown {fixture_only:true} remains a denial regression in UF008; it is not
  // a native successful response. AdapterCases assertions remain unchanged.
  public static int Calls; public static Func<string,JObject,object> Implementation = (c,p) => new MCPForUnity.Editor.Helpers.SuccessResponse("fixture-native",
      new { material="fixture material", shader="fixture shader", properties=new object[0] });
  public static Func<JObject,object> GetHandler(string command) => p => { Calls++;if(RawOverride!=null)return RawOverride(command,p); if(command=="manage_asset" && (string)p["action"]=="duplicate") { System.IO.File.Copy((string)p["path"],(string)p["destination"]);System.IO.File.WriteAllText((string)p["destination"]+".meta","new-guid");UnityEditor.AssetDatabase.Objects[(string)p["destination"]]=new UnityEngine.Material();return new MCPForUnity.Editor.Helpers.SuccessResponse("fixture"); }if(command=="manage_material" && (string)p["action"]=="assign_material_to_renderer") {foreach(var o in UnityEditor.GlobalObjectId.Objects.Values)if(o is UnityEngine.Renderer ren){var mats=ren.sharedMaterials;mats[(int)p["slot"]]=(UnityEngine.Material)UnityEditor.AssetDatabase.Objects[(string)p["materialPath"]];ren.sharedMaterials=mats;ren.Json="reference-switched";}return new MCPForUnity.Editor.Helpers.SuccessResponse("fixture-assign");}
 if(command=="manage_material" && (string)p["action"]=="set_material_shader_property") {UnityEditor.AssetDatabase.Objects[(string)p["materialPath"]].Json=p["value"].ToString();if(p["value"].Type==JTokenType.String && UnityEditor.AssetDatabase.Objects.TryGetValue((string)p["value"],out var tex))((UnityEngine.Material)UnityEditor.AssetDatabase.Objects[(string)p["materialPath"]]).Texture=tex as UnityEngine.Texture;return new MCPForUnity.Editor.Helpers.SuccessResponse("fixture-write");}return Implementation(command,p); };
 }
}


namespace UnityEditor.PackageManager {
 public sealed class PackageInfo {
  public static string TestRoot;
  public string resolvedPath;
  public static PackageInfo FindForAssembly(System.Reflection.Assembly a) => TestRoot == null ? null : new PackageInfo {resolvedPath=TestRoot};
 }
}
