// Real pinned upstream console handler/reflection + production gate/contracts.
// Unity LogEntries and human approval are doubles, NOT real Editor acceptance.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using MCPForUnity.Editor.Tools;
namespace UnityEngine {
 public enum LogType { Error, Assert, Warning, Log, Exception }
 public static class Mathf { public static int Clamp(int n,int min,int max)=>Math.Min(max,Math.Max(min,n));public static int Max(int a,int b)=>Math.Max(a,b); }
}
namespace UnityEditorInternal { internal class FixtureNamespace {} }
namespace UnityEditor {
 public static class EditorApplication {}
 public sealed class LogEntry { public int mode,line; public string message,file; }
 public static class LogEntries {
  public static readonly List<LogEntry> Entries=new List<LogEntry>();
  public static int Clears,Starts,Ends; public static bool FailRead;
  public static int StartGettingEntries(){Starts++;return Entries.Count;}
  public static void EndGettingEntries(){Ends++;}
  public static int GetCount()=>Entries.Count;
  public static void Clear(){Clears++;Entries.Clear();}
  public static void GetEntryInternal(int index,LogEntry entry){if(FailRead)throw new Exception("fixture private failure");var s=Entries[index];entry.mode=s.mode;entry.message=s.message;entry.file=s.file;entry.line=s.line;}
 }
}
namespace MCPForUnity.Editor.Helpers { public static class McpLog { public static void Error(string text){} } }
namespace MCPForUnity.Editor.Tools { [AttributeUsage(AttributeTargets.Class)]public sealed class McpForUnityToolAttribute:Attribute { public bool AutoRegister{get;set;}public McpForUnityToolAttribute(string name){} } }
internal static class ConsoleNativeCases {
 static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="fixture-task",["plan_id"]=id,["body"]=body};
 static JObject Args()=>JObject.Parse("{\"action\":\"get\",\"types\":[\"error\",\"warning\",\"log\"],\"count\":10,\"pageSize\":2,\"cursor\":0,\"format\":\"json\",\"includeStacktrace\":true}");
 static JObject Prepare(CandidateGate gate)=>gate.Dispatch(Wire("prepare","",JObject.Parse("{\"operations\":[{\"command\":\"read_console\",\"action\":\"get\"}],\"targets\":[\"Console\"],\"ttl_seconds\":60}")));
 static JObject Ready(CandidateGate gate){var p=Prepare(gate);Check((bool)p["success"],"prepare");Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");return p;}
 static JObject Execute(CandidateGate gate,JObject plan,JObject args)=>gate.Dispatch(Wire("execute",(string)plan["data"]["plan_id"],new JObject{["command"]="read_console",["params"]=args}));
 static internal void Seed(){
  UnityEditor.LogEntries.Entries.Clear();
  for(int i=0;i<5;i++)UnityEditor.LogEntries.Entries.Add(new UnityEditor.LogEntry{mode=1,message="fixture compiler error "+i+"\nUnityEngine.Debug:LogError (object)",file="Assets/Fixture.cs",line=i+1});
 }
 static int Main(){try{
  Seed();
  int calls=0;
  var gate=new CandidateGate(()=>100,()=>"fixture-project",()=>"fixture-connection",p=>"live-console-generation",
   (cmd,args)=>{calls++;var r=JObject.FromObject(ReadConsole.HandleCommand(args));return (bool?)r["success"]==true&&!NativeReadContract.Valid(cmd,r,args)?new JObject{["success"]=false}:r;});
  Check(!(bool)Prepare(gate)["success"],"default deny");gate.SetCapability("read_console","get",true);
  var pending=Prepare(gate);Check(!(bool)Execute(gate,pending,Args())["success"]&&calls==0,"pending executed");
  var plan=Ready(gate);var first=Execute(gate,plan,Args());Check((bool)first["success"],"first native page "+first);
  Check((int)first["data"]["total"]==3&&(bool)first["data"]["truncated"]&&(string)first["data"]["nextCursor"]=="2","upstream total is lower bound");
  var rows=new List<string>();for(int cursor=0;;){var a=Args();a["cursor"]=cursor;var r=Execute(gate,plan,a);Check((bool)r["success"],"page failed");foreach(JObject item in (JArray)r["data"]["items"])rows.Add((string)item["message"]);if(!(bool)r["data"]["truncated"])break;cursor=int.Parse((string)r["data"]["nextCursor"]);}
  Check(rows.Count==5&&new HashSet<string>(rows).Count==5&&UnityEditor.LogEntries.Clears==0,"native pagination/clear");
  Console.WriteLine("PASS NC001 actual upstream get reflection pagination and local grant; Unity log API doubled");
  var mutations=new Action<JObject>[] {a=>a["action"]="clear",a=>a["pageSize"]=0,a=>a["pageSize"]=101,a=>a["pageSize"]="2",a=>a["cursor"]=-1,a=>a["count"]=null,a=>a["approved"]=true,a=>a["types"]=new JArray("all"),a=>a["includeStacktrace"]="true",a=>a["format"]="plain"};
  foreach(var mutate in mutations){plan=Ready(gate);var a=Args();mutate(a);int before=calls;Check(!(bool)Execute(gate,plan,a)["success"]&&calls==before,"bad native args reached handler");}
  Check(UnityEditor.LogEntries.Clears==0,"clear escaped gate");Console.WriteLine("PASS NC002 clear/coercion/oversized/unrecognized arguments rejected before native handler");
  plan=Ready(gate);UnityEditor.LogEntries.FailRead=true;var failed=Execute(gate,plan,Args());Check(!(bool)failed["success"]&&!failed.ToString().Contains("fixture private failure")&&gate.LocalPlans().Count==0,"native failure leak/regrant");
  Check(UnityEditor.LogEntries.Starts==UnityEditor.LogEntries.Ends,"native finally not exercised");UnityEditor.LogEntries.FailRead=false;
  Console.WriteLine("PASS NC003 actual native read failure closes plan with sanitized response and balanced Start/End");
  var good=JObject.FromObject(ReadConsole.HandleCommand(Args()));
  foreach(var change in new Action<JObject>[] {d=>d["total"]=2,d=>d["nextCursor"]="3",d=>d["cursor"]=1,d=>d["items"][0]["stackTrace"]=new JObject(),d=>d["items"][0]["line"]="1",d=>d["extra"]="private",d=>d["items"][0]["message"]=new string('x',1024*1024)}){
   var bad=(JObject)good.DeepClone();change((JObject)bad["data"]);Check(!NativeReadContract.Valid("read_console",bad,Args()),"malformed successful result accepted");}
  Console.WriteLine("PASS NC004 real native output contract rejects malformed page metadata/fields/size");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
