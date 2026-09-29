// Unity API substitutes only. The transport under test is pinned upstream source.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
namespace UnityEngine { public static class Application { public static string dataPath="/fixture/Assets",unityVersion="fixture"; } }
namespace UnityEditor { public static class EditorPrefs { public static int Reads; public static string GetString(string k,string d){Reads++;return d;} } }
namespace MCPForUnity.Editor.Constants { public static class EditorPrefKeys { public const string ApiKey="fixture"; } public static class AuthConstants {public const string ApiKeyHeader="X-API-Key";} }
namespace MCPForUnity.Editor.Helpers {
 public static class McpLog { public static void Error(string x){} public static void Warn(string x){} public static void Debug(string x){} public static void Info(string x,bool y){} }
 internal static class ProjectIdentityUtility {public static int Writes; public static string GetProjectName()=>"fixture"; public static string GetProjectHash()=>"fixture-project"; public static void SetSessionId(string x){Writes++;}}
 internal static class HttpEndpointUtility {public static int Reads; public static bool IsRemoteScope(){Reads++;return false;}public static bool IsCurrentRemoteUrlAllowed(out string error){error=null;return false;}public static string GetBaseUrl(){Reads++;return "http://127.0.0.1:1";} }
}
namespace MCPForUnity.Editor.Services.Transport {
 internal static class TransportCommandDispatcher {
  public static int GlobalCalls,MainCalls;
  public static Task<T> RunOnMainThreadAsync<T>(Func<T> fn,CancellationToken token){token.ThrowIfCancellationRequested();MainCalls++;return Task.FromResult(fn());}
  public static Task<string> ExecuteCommandJsonAsync(string json,CancellationToken token){GlobalCalls++;return Task.FromResult("{}");}
 }
}

// Test-only public counters; not present in the materialized package.
public static class OwnedFixtureObservation {
 public static int GlobalCalls=>MCPForUnity.Editor.Services.Transport.TransportCommandDispatcher.GlobalCalls;
 public static int MainCalls=>MCPForUnity.Editor.Services.Transport.TransportCommandDispatcher.MainCalls;
 public static int ProjectWrites=>MCPForUnity.Editor.Helpers.ProjectIdentityUtility.Writes;
 public static int EndpointReads=>MCPForUnity.Editor.Helpers.HttpEndpointUtility.Reads;
}
