// Real gate + full pinned native manager; Unity/SessionState remain doubles.
using System;using System.Reflection;using Newtonsoft.Json.Linq;using UnityEditor;using Yukino.VRChatAgent;using MCPForUnity.Editor.Services;
internal static class JobObservationCases {
 const string Id="0123456789abcdef0123456789abcdef",Store="MCPForUnity.TestJobsV1",Current="MCPForUnity.CurrentTestJobIdV1";
 static void Check(bool b,string s){if(!b)throw new Exception(s);}
 static JObject Wire(string kind,string id="")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="p",["connection_id"]="c",["client_id"]="client",["task_id"]="task",["plan_id"]=id,["body"]=new JObject()};
 static int Main(string[] args){try{
  string test=args.Length==0?"JO001":args[0];long now=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
  var job=new JObject{["job_id"]=Id,["status"]="running",["mode"]="EditMode",["started_unix_ms"]=now-60000,["last_update_unix_ms"]=now-60000,["init_timeout_ms"]=15000};
  SessionState.Values[Store]=new JObject{["current_job_id"]=Id,["jobs"]=new JArray(job)}.ToString();SessionState.Values[Current]=Id;
  var type=typeof(CandidateGate).Assembly.GetType("Yukino.VRChatAgent.JobObservation");Check(type!=null,"native_job_receipt_adapter_missing");
  var method=type.GetMethod("Read",BindingFlags.Static|BindingFlags.NonPublic);Check(method!=null,"native_job_read_missing");
  var gate=new CandidateGate(()=>1,()=>"p",()=>"c",t=>"live-job-project-binding",(c,a)=>(JObject)method.Invoke(null,new object[]{a}));
  gate.SetCapability("get_test_job","observe",true);gate.SetProjectJobMaintenance(true);
  var p=Wire("prepare");p["body"]=JObject.Parse("{operations:[{command:'get_test_job',action:'observe'}],targets:['TestJobs/"+Id+"'],ttl_seconds:60,effects:[{kind:'project_test_job_maintenance',version:1}]}");
  var pending=gate.Dispatch(p);Check((bool)pending["success"] && SessionState.Reads.Count==0 && SessionState.Writes.Count==0,"prepare_touched_native_state");
  Check(gate.Approve((string)pending["data"]["plan_id"],(string)pending["data"]["digest"]),"approval");
  Check(SessionState.Reads.Count==0,"approval_touched_native_state");
  var q=Wire("execute",(string)pending["data"]["plan_id"]);q["body"]=new JObject{["command"]="get_test_job",["params"]=new JObject{["job_id"]=Id}};
  if(test=="JO002")SessionState.FailWrites=true;
  if(test=="JO003")SessionState.Values[Store]="{broken";
  if(test=="JO004")SessionState.Values[Store]=new string('x',262145);
  if(test=="JO005"){q["body"]["params"]["job_id"]=new string('a',32);}
  var result=gate.Dispatch(q);
  if(test=="JO001"){
   Check((bool)result["success"] && (string)result["data"]["status"]=="failed","authorized_native_timeout_not_returned: "+result);
   Check(SessionState.Writes.Count==2,"native_persistence_not_exercised");
   Check((string)result["data"]["candidate_effects"]["persistence"]=="target_timeout_state_confirmed","truthful_timeout_receipt_missing");
  }else{
   Check(!(bool)result["success"],"unsafe_or_unconfirmed_native_success: "+test);
   Check(gate.LocalPlans().Count==0,"failed_effect_grant_survived");
   if(test=="JO002")Check((bool)result["data"]["effects_may_have_occurred"] && SessionState.Writes.Count==1,"persistence_failure_effects_hidden");
   else Check(SessionState.Writes.Count==0,"rejection_wrote_state");
   if(test=="JO005")Check(SessionState.Reads.Count==0,"unapproved_job_accessed_state");
  }
  Check(MCPServiceLocator.Tests.Starts==0 && EditorApplication.DelayRegistrations==0,"started_test_or_callback");
  Console.WriteLine("PASS "+test+" real_native_job_gate_and_receipt");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
