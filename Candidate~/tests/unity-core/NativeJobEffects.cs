// Fresh PROCESS for every case: static constructor is part of the behavior.
// Characterization, not a product authorization gate or real Unity acceptance.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.TestTools.TestRunner.Api;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
internal static class NativeJobEffects {
 const string JobsKey="MCPForUnity.TestJobsV1",CurrentKey="MCPForUnity.CurrentTestJobIdV1";
 static readonly long Now=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
 static void Check(bool condition,string reason){if(!condition)throw new InvalidOperationException(reason);}
 static JObject Job(string id,string status="succeeded",long age=0,int? total=1)=>new JObject {
  ["job_id"]=id,["status"]=status,["mode"]="EditMode",["started_unix_ms"]=Now-age,
  ["last_update_unix_ms"]=Now-age,["total_tests"]=total.HasValue?(JToken)total.Value:JValue.CreateNull(),
  ["completed_tests"]=0,["init_timeout_ms"]=15000
 };
 static void Seed(string current,params JObject[] jobs){
  SessionState.Values[JobsKey]=new JObject{["current_job_id"]=current,["jobs"]=new JArray(jobs)}.ToString();
  SessionState.Values[CurrentKey]=current??"";
 }
 static Dictionary<string,TestJob> Memory()=>(Dictionary<string,TestJob>)typeof(TestJobManager).GetField("Jobs",BindingFlags.Static|BindingFlags.NonPublic).GetValue(null);
 static JObject Call(string id)=>JObject.FromObject(GetTestJob.HandleCommand(new JObject{["job_id"]=id}));
 static JObject Stored()=>JObject.Parse(SessionState.Values[JobsKey]);
 static void Success(JObject r,string status){Check((bool)r["success"],"native response failed: "+r);Check((string)r["data"]["status"]==status,"wrong native status: "+r);}
 static void Invariants(){Check(MCPServiceLocator.Tests.Starts==0,"observation started tests");Check(EditorApplication.DelayRegistrations==0,"observation queued finalize");}
 static int Main(string[] args){
  string id=args[0];bool assertSingle=args.Length>1&&args[1]=="--assert-single-job";
  try {
   JObject result;
   switch(id){
    case "NJ001":
     result=Call("missing");Check(!(bool)result["success"] && (string)result["error"]=="Unknown job_id.","unknown response");
     Check(SessionState.Writes.Count==0 && Memory().Count==0,"empty query mutated persistence");break;
    case "NJ002":
     Seed("other-running",Job("requested-done"),Job("other-running","running",600000,1));
     string before=SessionState.Values[JobsKey];result=Call("requested-done");Success(result,"succeeded");
     Check(Memory()["other-running"].Status==TestJobStatus.Failed && TestJobManager.CurrentJobId==null,"stale unrelated job not observed");
     Check(SessionState.Writes.Count==0 && SessionState.Values[JobsKey]==before,"restore unexpectedly persisted");
     if(assertSingle)Check(Memory()["other-running"].Status==TestJobStatus.Running,"SINGLE_JOB_SCOPE_VIOLATED: completed-job query failed unrelated restored job");break;
    case "NJ003":
     Seed("other-running",Job("other-running","running",600000,1));
     result=JObject.FromObject(GetTestJob.HandleCommand(new JObject()));
     Check(!(bool)result["success"] && SessionState.Reads.Count==0 && SessionState.Writes.Count==0,"invalid command initialized manager");break;
    case "NJ004":
     Seed("current",Job("current","running",0,1),Job("done"));
     string original=SessionState.Values[JobsKey];result=Call("current");Success(result,"running");
     Check(TestJobManager.CurrentJobId=="current" && SessionState.Writes.Count==0 && SessionState.Values[JobsKey]==original,"normal observation changed state");break;
    case "NJ005":
     Seed("target",Job("target","running",60000,null));TestRunStatus.MarkStarted(TestMode.EditMode);
     result=Call("target");Success(result,"failed");
     Check(!TestRunStatus.IsRunning && TestRunStatus.FinishedUnixMs.HasValue && TestJobManager.CurrentJobId==null,"timed-out current job did not finish native status");
     Check(SessionState.Writes.SequenceEqual(new[]{CurrentKey,JobsKey}) && (string)Stored()["jobs"][0]["status"]=="failed","timeout not persisted");break;
    case "NJ006":
     Seed("other-current",Job("target","running",60000,null),Job("other-current","running",0,1));TestRunStatus.MarkStarted(TestMode.EditMode);
     result=Call("target");Success(result,"failed");
     Check(TestJobManager.CurrentJobId=="other-current" && TestRunStatus.IsRunning && Memory()["other-current"].Status==TestJobStatus.Running,"timeout cleared other current run");
     Check(SessionState.Writes.Count==2 && ((JArray)Stored()["jobs"]).Count==2,"global persistence not observed");break;
    case "NJ007":
     Seed("target",Job("target","running",60000,null));
     EditorStateCache.Compiling=true;Success(Call("target"),"running");
     EditorStateCache.Compiling=false;EditorApplication.isUpdating=true;Success(Call("target"),"running");
     Check(SessionState.Writes.Count==0,"busy editor persisted timeout");
     EditorApplication.isUpdating=false;result=Call("target");Success(result,"failed");Check(SessionState.Writes.Count==2,"ready editor did not persist timeout");break;
    case "NJ008":
     var jobs=new List<JObject>{Job("target","running",60000,null)};
     for(int i=0;i<11;i++)jobs.Add(Job("other-"+i,"succeeded",120000+i*1000,1));
     Seed("target",jobs.ToArray());result=Call("target");Success(result,"failed");
     Check(Memory().Count==12 && ((JArray)Stored()["jobs"]).Count==10,"persistence retention changed");
     var saved=((JArray)Stored()["jobs"]).Select(x=>(string)x["job_id"]).ToArray();
     Check(!saved.Contains("other-9") && !saved.Contains("other-10"),"unrelated historical pruning not observed");break;
    case "NJ009":
     Seed("target",Job("target","running",60000,null));string persisted=SessionState.Values[JobsKey];SessionState.FailWrites=true;
     result=Call("target");Success(result,"failed");
     Check(SessionState.Writes.Count==1 && SessionState.Values[JobsKey]==persisted && McpLog.Warnings.Any(x=>x.Contains("Failed to persist")),"silent persistence failure not observed");break;
    case "NJ010":
     Seed("other-running",Job("other-running","running",600000,1));result=Call("does-not-exist");
     Check(!(bool)result["success"] && Memory()["other-running"].Status==TestJobStatus.Failed && TestJobManager.CurrentJobId==null,"unknown job did not trigger unrelated restore");
     Check(SessionState.Writes.Count==0,"restore persisted on unknown query");break;
    default:throw new InvalidOperationException("unknown case");
   }
   Invariants();
   Console.WriteLine("PASS "+id+" pinned_full_native_characterization");
   Console.WriteLine(new JObject{["case"]=id,["session_reads"]=new JArray(SessionState.Reads),["session_write_attempts"]=new JArray(SessionState.Writes),["warnings"]=new JArray(McpLog.Warnings),["test_starts"]=MCPServiceLocator.Tests.Starts,["unity_apis_are_doubles"]=true}.ToString(Newtonsoft.Json.Formatting.None));
   return 0;
  } catch(Exception e){Console.Error.WriteLine(e.ToString());return 1;}
 }
}
