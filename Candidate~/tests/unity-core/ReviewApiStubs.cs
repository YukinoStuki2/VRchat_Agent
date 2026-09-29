// Explicit Unity API doubles: compiling these is NOT compiling inside Unity.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
namespace UnityEngine {
 public class Object { public string name, Json = "fixture-memory"; public int GetInstanceID() => 1; }
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
namespace UnityEditor {
 [AttributeUsage(AttributeTargets.Class)] public class InitializeOnLoadAttribute : Attribute {}
 [AttributeUsage(AttributeTargets.Method)] public class MenuItemAttribute : Attribute { public MenuItemAttribute(string s) {} }
 public enum MessageType { Info, Warning, Error }
 public enum PlayModeStateChange { EnteredEditMode, ExitingEditMode }
 public class EditorWindow { public static T GetWindow<T>(string title) where T:new() => new T(); public void Repaint(){} }
 public static class EditorApplication {
  public static bool isCompiling, isUpdating, isPlayingOrWillChangePlaymode; public static double timeSinceStartup = 100;
  public static event Action update, quitting, projectChanged, delayCall; public static event Action<PlayModeStateChange> playModeStateChanged;
  public static void Tick() => update?.Invoke(); public static void Quit() => quitting?.Invoke(); public static void Play() => playModeStateChanged?.Invoke(PlayModeStateChange.ExitingEditMode);
 }
 public static class AssemblyReloadEvents { public static event Action beforeAssemblyReload; public static void Reload() => beforeAssemblyReload?.Invoke(); }
 public static class AssetDatabase {
  public static UnityEngine.Object Asset = new UnityEngine.Object();
  public static string AssetPathToGUID(string path) => "fixture-guid";
  public static string GetAssetDependencyHash(string path) => "fixture-dependency-hash";
  public static UnityEngine.Object[] LoadAllAssetsAtPath(string path) => new[] { Asset };
 }
 public static class EditorJsonUtility { public static string ToJson(UnityEngine.Object obj) => obj.Json; }
 public static class EditorGUILayout {
  public static string NextText; public static string TextField(string label,string value) {var result=NextText??value;NextText=null;return result;}
  public static readonly List<string> Labels = new List<string>();
  public static void HelpBox(string s, MessageType t){} public static bool ToggleLeft(string s, bool v)=>v;
  public static void LabelField(string a, string b=""){Labels.Add(a+":"+b);} public static void Space(){}
  public static UnityEngine.Vector2 BeginScrollView(UnityEngine.Vector2 v)=>v; public static void EndScrollView(){}
 }
 public static class EditorGUI { public static bool Disabled; public static void BeginDisabledGroup(bool v){Disabled=v;} public static void EndDisabledGroup(){Disabled=false;} }
}
namespace MCPForUnity.Editor.Helpers {
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
  public static int Calls; public static Func<string,JObject,object> Implementation = (c,p) => new MCPForUnity.Editor.Helpers.SuccessResponse("fixture-native",new { fixture_only=true });
  public static Func<JObject,object> GetHandler(string command) => p => { Calls++; return Implementation(command,p); };
 }
}

namespace UnityEditor { public static class EditorPrefs { public static string GetString(string k,string d)=>d; public static void SetString(string k,string v){throw new System.InvalidOperationException("review-must-not-write-prefs");} public static bool HasKey(string k)=>false; public static void DeleteKey(string k){throw new System.InvalidOperationException("review-must-not-write-prefs");} } }
namespace MCPForUnity.Editor.Constants { public static class EditorPrefKeys { public const string SessionId="fixture-only-session-key"; } }
namespace MCPForUnity.Editor.Helpers { public static class McpLog { public static void Warn(string s){} } }

namespace UnityEditor.PackageManager {
 public sealed class PackageInfo {
  public static string TestRoot;
  public string resolvedPath;
  public static PackageInfo FindForAssembly(System.Reflection.Assembly a) => TestRoot == null ? null : new PackageInfo {resolvedPath=TestRoot};
 }
}
