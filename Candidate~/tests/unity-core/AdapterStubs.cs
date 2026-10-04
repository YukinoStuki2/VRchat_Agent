// Explicit Unity API doubles: compiling these is NOT compiling inside Unity.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
namespace UnityEngine {
 public class AnimationClip:Object {}
 public class RuntimeAnimatorController:Object {public AnimationClip[] animationClips=Array.Empty<AnimationClip>();}
 public class Animator:Component {public int parameterCount,layerCount;public RuntimeAnimatorController runtimeAnimatorController;}

 public class Object { public bool Persistent; public string name, Json = "fixture-memory"; public int GetInstanceID() => 1; }
 public class Component : Object {}
 public class Transform : Component {public int childCount;}
 public class GameObject : Object { public UnityEngine.SceneManagement.Scene scene; public Transform transform=new Transform(); public Component[] Components=Array.Empty<Component>(); public T[] GetComponents<T>() where T:Component=>Array.ConvertAll(Components,x=>(T)x); }
 public static class Application { public static string dataPath; }
 public struct Vector2 {}
 public static class GUILayout {
  public static string NextButton; public static Action BeforeClick;
  public static bool Button(string text) {
   if(UnityEditor.EditorGUI.Disabled || NextButton != text)return false;
   NextButton=null; BeforeClick?.Invoke();return true;
  }
 }
}
namespace UnityEngine.SceneManagement {
 public struct Scene {
  public int Id; public bool isLoaded; public bool IsValid()=>Id!=0;
  public static bool operator==(Scene a,Scene b)=>a.Id==b.Id;
  public static bool operator!=(Scene a,Scene b)=>a.Id!=b.Id;
  public override bool Equals(object other)=>other is Scene scene && this==scene;
  public override int GetHashCode()=>Id;
 }
}
namespace UnityEditor.SceneManagement {
 public static class EditorSceneManager {public static UnityEngine.SceneManagement.Scene Current=new UnityEngine.SceneManagement.Scene{Id=1,isLoaded=true};public static UnityEngine.SceneManagement.Scene GetActiveScene()=>Current;}
 public class PrefabStage {public UnityEngine.SceneManagement.Scene scene;}
 public static class PrefabStageUtility {public static PrefabStage Current;public static PrefabStage GetCurrentPrefabStage()=>Current;}
}
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
  public static UnityEngine.Object Asset = new UnityEngine.Object();
  public static string AssetPathToGUID(string path) => "fixture-guid";
  public static string GetAssetDependencyHash(string path) => "fixture-dependency-hash";
  public static UnityEngine.Object[] LoadAllAssetsAtPath(string path) => new[] { Asset };
 }
 public static class EditorUtility {public static bool IsPersistent(UnityEngine.Object obj)=>obj.Persistent;}
 public static class EditorJsonUtility { public static string ToJson(UnityEngine.Object obj) => obj.Json; }
 public static class EditorGUILayout {
  public static int IntField(string label,int value)=>value;
  public static string NextText; public static string TextField(string label,string value) {var result=NextText??value;NextText=null;return result;}
  public static readonly List<string> Labels = new List<string>();
  public static string NextToggle;
  public static void HelpBox(string s, MessageType t){} public static bool ToggleLeft(string s, bool v){
   if(EditorGUI.Disabled || NextToggle!=s)return v;NextToggle=null;return !v;
  }
  public static void LabelField(string a, string b=""){Labels.Add(a+":"+b);} public static void Space(){}
  public static UnityEngine.Vector2 BeginScrollView(UnityEngine.Vector2 v)=>v; public static void EndScrollView(){}
 }
 public static class EditorGUI { public static bool Disabled; public static void BeginDisabledGroup(bool v){Disabled=v;} public static void EndDisabledGroup(){Disabled=false;} }
}
namespace MCPForUnity.Editor.Helpers {
 public static class GameObjectLookup {public static UnityEngine.Object Fixture;public static UnityEngine.Object ResolveInstanceID(int id)=>Fixture;}
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
  // Same shape as pinned ManageMaterial.GetMaterialInfo's empty property list.
  // Unknown {fixture_only:true} remains a denial regression in UF008; it is not
  // a native successful response. AdapterCases assertions remain unchanged.
  public static int Calls; public static Func<string,JObject,object> Implementation = (c,p) => new MCPForUnity.Editor.Helpers.SuccessResponse("fixture-native",
      new { material="fixture material", shader="fixture shader", properties=new object[0] });
  public static Func<JObject,object> GetHandler(string command) => p => { Calls++; return Implementation(command,p); };
 }
}

namespace MCPForUnity.Editor.Tools.Animation {
 public static class ManageAnimation {
  public static int Calls;public static bool WrongName;
  public static object HandleCommand(JObject args){
   Calls++;if((string)args["action"]=="animator_get_parameter")return new {success=true,data=(object)new {name=WrongName?"wrong":"Speed",type="Float",value=0.5f}};
   return new {success=true,data=(object)new {gameObject=WrongName?"wrong":"Avatar",enabled=true,speed=1,hasController=false,controllerName=(string)null,applyRootMotion=false,updateMode="Normal",cullingMode="AlwaysAnimate",parameterCount=0,layerCount=0,parameters=new object[0],layers=new object[0],clips=new object[0]}};
  }
 }
}
namespace MCPForUnity.Editor.Resources.Scene {
 public static class ResourceFixture {
  public static int Calls;
  public static object Read(string command,JObject args){
   Calls++;if(command=="get_gameobject_components")return new {success=true,data=(object)new {gameObjectID=123,gameObjectName="fixture",components=new object[0],cursor=0,pageSize=2,nextCursor=(int?)null,totalCount=0,hasMore=false,includeProperties=false}};
   var vector=new {x=0,y=0,z=0};return new {success=true,data=(object)new {instanceID=123,name="fixture",tag="Untagged",layer=0,layerName="Default",active=true,activeInHierarchy=true,isStatic=false,
    transform=new {position=vector,localPosition=vector,rotation=vector,localRotation=vector,scale=vector,lossyScale=vector},parent=(int?)null,children=new int[0],componentTypes=new[]{"Transform"},path="fixture"}};
  }
 }
 public static class GameObjectResource {public static object HandleCommand(JObject args)=>ResourceFixture.Read("get_gameobject",args);}
 public static class GameObjectComponentsResource {public static object HandleCommand(JObject args)=>ResourceFixture.Read("get_gameobject_components",args);}
}
namespace UnityEditor.PackageManager {
 public sealed class PackageInfo {
  public static string TestRoot;
  public string resolvedPath;
  public static PackageInfo FindForAssembly(System.Reflection.Assembly a) => TestRoot == null ? null : new PackageInfo {resolvedPath=TestRoot};
 }
}
