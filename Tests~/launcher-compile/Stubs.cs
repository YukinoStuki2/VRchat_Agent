// Compile/test doubles ONLY, not Unity assemblies or evidence of Windows runtime behavior.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;
namespace UnityEngine {
 public enum RuntimePlatform { WindowsEditor,LinuxEditor }
 public static class Application { public static string dataPath="C:/test/Assets"; public static RuntimePlatform platform=RuntimePlatform.WindowsEditor; }
 public struct Vector2 { public Vector2(float x,float y){} }
 public class GUILayoutOption{}
 public static class GUILayout { public static bool Button(string s,params GUILayoutOption[] o)=>false; public static GUILayoutOption Height(float v)=>null; public static GUILayoutOption Width(float v)=>null; }
 public static class JsonUtility { public static T FromJson<T>(string s)=>System.Text.Json.JsonSerializer.Deserialize<T>(s,new System.Text.Json.JsonSerializerOptions {IncludeFields=true}); public static string ToJson(object o)=>System.Text.Json.JsonSerializer.Serialize(o,new System.Text.Json.JsonSerializerOptions {IncludeFields=true}); }
}
namespace UnityEditor {
 public class InitializeOnLoadAttribute:Attribute{}
 public class MenuItem:Attribute { public MenuItem(string x){} }
 public static class AssemblyReloadEvents { public static event Action beforeAssemblyReload; public static void Fire()=>beforeAssemblyReload?.Invoke(); }
 public static class EditorApplication { public static event Action quitting,update; public static double timeSinceStartup; public static void FireUpdate()=>update?.Invoke(); public static void Quit()=>quitting?.Invoke(); }
 public class EditorWindow { public UnityEngine.Vector2 minSize; public void Repaint(){} public static T GetWindow<T>(string s) where T:new()=>new T(); }
 public static class SessionState { static readonly Dictionary<string,object> d=new Dictionary<string,object>(); public static string GetString(string k,string v)=>d.ContainsKey(k)?(string)d[k]:v; public static void SetString(string k,string v)=>d[k]=v; public static bool GetBool(string k,bool v)=>d.ContainsKey(k)?(bool)d[k]:v; public static void SetBool(string k,bool v)=>d[k]=v; public static void EraseString(string k)=>d.Remove(k); public static void EraseBool(string k)=>d.Remove(k); }
 public static class EditorPrefs { public static bool GetBool(string k,bool v)=>SessionState.GetBool(k,v); public static void SetBool(string k,bool v)=>SessionState.SetBool(k,v); public static string GetString(string k,string v)=>SessionState.GetString(k,v); public static void SetString(string k,string v)=>SessionState.SetString(k,v); }
 public static class EditorStyles { public static object boldLabel=>null; }
 public enum MessageType { Info,None,Warning }
 public static class EditorGUILayout { public static void LabelField(string s,object o){} public static void LabelField(string s){} public static void HelpBox(string s,MessageType t){} public static UnityEngine.Vector2 BeginScrollView(UnityEngine.Vector2 s)=>s; public static void EndScrollView(){} public static void Space(){} public static string TextField(string n,string v)=>v; public static int IntField(string n,int v)=>v; public static bool ToggleLeft(string n,bool v)=>v; public static void BeginHorizontal(){} public static void EndHorizontal(){} }
 public static class EditorGUI { public sealed class DisabledScope:IDisposable { public DisabledScope(bool b){} public void Dispose(){} } }
 public static class EditorUtility { public static bool DisplayDialog(string t,string m,string yes,string no)=>false; public static void RevealInFinder(string s){} public static string OpenFilePanel(string t,string p,string e)=>""; }
 // Real Unity 2022 also has a namesake; keep ambiguity exposed if source forgets qualification.
 public class PackageInfo {}
}
namespace UnityEditor.PackageManager { public class PackageInfo {
 public string name,version,resolvedPath;
 public static string CoplayVersion="10.2.0";
 public static PackageInfo FindForAssembly(Assembly a)=>a.GetName().Name=="MCPForUnity.Editor" ? new PackageInfo { name="com.coplaydev.unity-mcp", version=CoplayVersion } : a.GetName().Name=="Yukino.VRChatManagedEditing.Editor" ? new PackageInfo {name="com.yukino.vrchat-managed-editing",version="0.1.0-preview.2"} : null;
} }
namespace MCPForUnity.Editor.Helpers { public static class HttpEndpointUtility { public static bool Remote; public static string Url="http://127.0.0.1:18081"; public static bool IsRemoteScope()=>Remote; public static string GetBaseUrl()=>Url; } }
namespace MCPForUnity.Editor.Services.Transport {
 public enum TransportMode { Http,Stdio }
 public class TransportState { public string SessionId {get;set;} public string Details {get;set;} }
 public class TransportManager {
  private Task<bool> _httpStartTask;
  public Transports.WebSocketTransportClient Client;
  public void SetInFlight(Task<bool> t)=>_httpStartTask=t;
  public Transports.WebSocketTransportClient GetClient(TransportMode m)=>Client;
 }
}
namespace MCPForUnity.Editor.Services {
 public interface IToolDiscoveryService {}
 public static class MCPServiceLocator { public static Transport.TransportManager TransportManager=new Transport.TransportManager(); public static IToolDiscoveryService ToolDiscovery=>null; }
 public class EditorConfigurationCache { public static EditorConfigurationCache Instance=new EditorConfigurationCache(); public bool UseHttpTransport=true; public void Refresh(){} public void SetUseHttpTransport(bool v)=>UseHttpTransport=v; public void SetHttpTransportScope(string v)=>Helpers.HttpEndpointUtility.Remote=v!="local"; public void SetHttpBaseUrl(string v)=>Helpers.HttpEndpointUtility.Url=v; }
}
namespace MCPForUnity.Editor.Services.Transport.Transports {
 public class WebSocketTransportClient {
  private System.Net.WebSockets.ClientWebSocket _socket;
  private System.Threading.CancellationTokenSource _lifecycleCts;
  private Uri _endpointUri;
  public static WebSocketTransportClient Last;
  public static TaskCompletionSource<bool> NextStart, NextStop;
  public static bool FailNextStop, ThrowOnCancel;
  public int Stops;
  public bool IsConnected {get;private set;}
  public TransportState State {get;private set;}
  public WebSocketTransportClient(IToolDiscoveryService tools=null){ Last=this; }
  public async Task<bool> StartAsync(){
   await StopAsync();
   _lifecycleCts=new System.Threading.CancellationTokenSource();
   if(ThrowOnCancel) _lifecycleCts.Token.Register(()=>throw new InvalidOperationException("cancel injected"));
   _endpointUri=new Uri(Helpers.HttpEndpointUtility.GetBaseUrl().Replace("http:","ws:")+"/hub/plugin");
   _socket=new System.Net.WebSockets.ClientWebSocket();
   var wait=NextStart; NextStart=null;
   bool ok=wait==null || await wait.Task;
   IsConnected=ok;
   State=new TransportState {SessionId="test-session",Details=_endpointUri.ToString()};
   return ok;
  }
  public async Task StopAsync(){
   if(_lifecycleCts==null)return;
   Stops++;
   if(FailNextStop){FailNextStop=false;throw new InvalidOperationException("stop injected");}
   _lifecycleCts.Cancel();
   var wait=NextStop; NextStop=null; if(wait!=null)await wait.Task;
   _socket?.Dispose();_socket=null;IsConnected=false;
   _lifecycleCts.Dispose();_lifecycleCts=null;
  }
 }
}
