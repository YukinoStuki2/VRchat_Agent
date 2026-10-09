// Test doubles ONLY: no Unity process, real Editor state, or test execution.
// The complete pinned job manager, status class, command and parsers are native.
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
namespace UnityEditor {
 public static class SessionState {
  public static readonly Dictionary<string,string> Values=new Dictionary<string,string>();
  public static readonly List<string> Reads=new List<string>();
  public static readonly List<string> Writes=new List<string>();
  public static bool FailWrites;
  public static string GetString(string key,string fallback) { Reads.Add(key);return Values.TryGetValue(key,out var s)?s:fallback; }
  public static void SetString(string key,string value) { Writes.Add(key);if(FailWrites)throw new InvalidOperationException("fixture persistence failure");Values[key]=value; }
 }
 public static class EditorApplication {
  public static bool isUpdating;
  public static int DelayRegistrations;
  public static event Action delayCall { add { DelayRegistrations++;throw new InvalidOperationException("test start/finalize outside characterization scope"); } remove { } }
 }
}
namespace UnityEditorInternal { public static class InternalEditorUtility { public static bool isApplicationActive=true; } }
namespace UnityEditor.TestTools.TestRunner.Api { public enum TestMode { EditMode, PlayMode } }
namespace MCPForUnity.Editor.Helpers {
 [AttributeUsage(AttributeTargets.Class)] public sealed class McpForUnityToolAttribute:Attribute {
  public McpForUnityToolAttribute(string name){} public bool AutoRegister{get;set;} public string Group{get;set;}
 }
 public static class McpLog {
  public static readonly List<string> Warnings=new List<string>();
  public static void Warn(string text){Warnings.Add(text);}
  public static void Error(string text){throw new InvalidOperationException(text);}
 }
}
namespace MCPForUnity.Editor.Services {
 public static class EditorStateCache { public static bool Compiling; public static bool GetActualIsCompiling()=>Compiling; }
 public sealed class TestFilterOptions { }
 public sealed class TestRunResult {
  public int Failed{get;set;}
  public object ToSerializable(string mode,bool details,bool failed){throw new InvalidOperationException("fixture result serialization not exercised");}
 }
 public sealed class TestRunnerSentinel {
  public int Starts;
  public Task<TestRunResult> RunTestsAsync(UnityEditor.TestTools.TestRunner.Api.TestMode mode,TestFilterOptions filter) {
   Starts++;throw new InvalidOperationException("must not start tests");
  }
 }
 public static class MCPServiceLocator { public static readonly TestRunnerSentinel Tests=new TestRunnerSentinel(); }
}
