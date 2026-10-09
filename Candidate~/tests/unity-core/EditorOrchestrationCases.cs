// Real C# owner/OS peer and collectible managed reload; Unity APIs, transport,
// human approval and surviving owner responses remain explicit TEST doubles.
using System;
using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEngine;
using Transport=MCPForUnity.Editor.Services.Transport.Transports.WebSocketTransportClient;
public static class EditorOrchestrationCases
{
 static void Check(bool v,string reason){if(!v)throw new Exception(reason);}
 static void Window(string method){typeof(CandidateWindow).GetMethod(method,BindingFlags.Instance|BindingFlags.NonPublic)?.Invoke(new CandidateWindow(),null);}
 public static int Run(string[] args)
 {
  try {
   string mode=args.Length>2?args[2]:"normal";string saved=Phase(args[0],args[1],null,mode);
   if(mode=="stop" || mode=="play" || mode=="window-close" || mode=="unplanned" || mode=="deadline"){Console.WriteLine("PASS EC006 lifecycle_cancel_no_reauthorization");return 0;}
   if(mode=="revoke-all" || mode=="capability"){Console.WriteLine(mode=="capability"?"PASS EC005 capability_revocation_cancels_reload":"PASS EC002 revoke_all_cancels_detached_owner");return 0;}
   var context=new AssemblyLoadContext("Editor-domain-fixture",true);
   try {
    var assembly=context.LoadFromAssemblyPath(typeof(EditorOrchestrationCases).Assembly.Location);
    assembly.GetType("EditorOrchestrationCases").GetMethod("Phase").Invoke(null,new object[]{args[0],args[1],saved,mode});
   }finally{context.Unload();}
   Console.WriteLine(mode=="evidence-change"?"PASS EC007 changed_candidate_denies_both_gates_preserves_user_edit":mode=="live-reads"?"PASS EC004 live_read_scopes_keep_approval_and_new_binding":mode=="cold-cancel"?"PASS EC003 restored_window_cancel_never_reattaches":"PASS EC001 explicit_compile_frozen_history_same_owner_restore");return 0;
  }catch(Exception e){Console.WriteLine("FAIL "+e);return 1;}
 }
 public static string Phase(string python,string package,string saved,string mode)
 {
  Application.dataPath=Path.Combine(package,"Assets");
  if(saved==null)
  {
   Directory.CreateDirectory(Application.dataPath);
   File.WriteAllText(Path.Combine(Application.dataPath,"source.mat"),"original");
   File.WriteAllText(Path.Combine(Application.dataPath,"source.mat.meta"),"guid");
   UnityEditor.PackageManager.PackageInfo.TestRoot=package;
   Window("OnEnable");
   var start=typeof(CandidateSession).GetMethod("StartLocalOwnerAsync",BindingFlags.NonPublic|BindingFlags.Static);
   var parameters=start.GetParameters();Check(parameters.Length==6 && parameters[5].Name=="enableReloadControl","explicit_reload_opt_in_missing");
   Check(((Task<bool>)start.Invoke(null,new object[]{python,false,false,null,null,true})).GetAwaiter().GetResult(),"owner_start_failed");
   try
   {
    var gate=MaterialCandidateSession.Gate;gate.SetCapability("copy",true);gate.SetCapability("edit",true);
    var wire=new JObject{["protocol"]=1,["kind"]="prepare",["project_id"]="project-A",["client_id"]="client-A",["connection_id"]=CandidateSession.LiveConnection(),["task_id"]="task-A",["plan_id"]="",
     ["body"]=new JObject{["source"]="Assets/source.mat",["candidate"]="Assets/candidate.mat",["operations"]=new JArray("copy","edit"),["references"]=new JArray(),["ttl_seconds"]=300}};
    var p=gate.Dispatch(wire);Check((bool?)p["success"]==true,"prepare failed "+p);
    Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve failed");
    wire["plan_id"]=p["data"]["plan_id"];wire["kind"]="execute";wire["body"]=new JObject{["action"]="copy",["arguments"]=new JObject()};
    Check((bool?)gate.Dispatch(wire)["success"]==true,"copy failed");
    if(mode=="live-reads")
    {
     var read=CandidateSession.Gate;var ops=new JArray();
     foreach(var pair in new[]{new[]{"read_console","get"},new[]{"manage_scene","get_active"},new[]{"get_selection","read"},new[]{"get_tags","read"}})
     {read.SetCapability(pair[0],pair[1],true);ops.Add(new JObject{["command"]=pair[0],["action"]=pair[1]});}
     var req=(JObject)wire.DeepClone();req["kind"]="prepare";req["plan_id"]="";
     req["body"]=new JObject{["operations"]=ops,["targets"]=new JArray("Console","Scenes","EditorMetadata","ProjectMetadata"),["ttl_seconds"]=300};
     var prep=read.Dispatch(req);Check((bool?)prep["success"]==true,"read prepare "+prep);
     Check(read.Approve((string)prep["data"]["plan_id"],(string)prep["data"]["digest"]),"read approve");
    }
    Check(CandidateReload.BeginAsync().GetAwaiter().GetResult(),"explicit_compile_did_not_arm");
    Check(CompilationPipeline.Requests==1 && gate.LocalPlans().Count==0,"compile_not_frozen");
    if(mode=="stop" || mode=="play" || mode=="window-close" || mode=="unplanned" || mode=="deadline")
    {
     if(mode=="stop")CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();
     if(mode=="play")EditorApplication.Play();
     if(mode=="window-close")Window("OnDestroy");
     if(mode=="unplanned")AssemblyReloadEvents.Reload();
     if(mode=="deadline"){EditorApplication.timeSinceStartup+=61;EditorApplication.Tick();}
     Check(!CandidateReload.Pending,"lifecycle_left_reload_armed: "+mode);
     CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();
     Check(!CandidateSession.HasLocalOwner && gate.LocalPlans().Count==0,"lifecycle_owner_cleanup_unconfirmed: "+mode);
     Check(SessionState.GetString("Yukino.VRChatAgent.planned-reload.v1.project-A","")=="","lifecycle_ticket_survived");
     return "";
    }
    if(mode=="revoke-all" || mode=="capability")
    {
     if(mode=="capability")EditorGUILayout.NextToggle="复制具体材质候选（原生 manage_asset/duplicate）";
     else GUILayout.NextButton="撤销全部任务权限（不回退文件）";
     Window("OnGUI");
     Check(!CandidateReload.Pending,"revoke_all_left_reload_armed");
     CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();
     Check(!CandidateSession.HasLocalOwner,"cancel_owner_cleanup_unconfirmed");
     CompilationPipeline.Start();AssemblyReloadEvents.Reload();
     Check(SessionState.GetString("Yukino.VRChatAgent.planned-reload.v1.project-A","")=="","revoked_reload_ticket_survived");
     return "";
    }
    CompilationPipeline.Start();AssemblyReloadEvents.Reload();
    var state=JObject.FromObject(SessionState.Values);
    Check(state["Yukino.VRChatAgent.planned-reload.v1.project-A"]!=null,"planned_reload_ticket_missing");
    Check(CandidateSession.LocalOwner!=null && !CandidateSession.LocalOwner.Ready,"old_owner_authorized");
    // Copy only API-double asset memory, not a production persistence mechanism.
    return new JObject{["session"]=state,["wire"]=wire,["material"]=AssetDatabase.Objects["Assets/candidate.mat"].Json,["plan"]=p["data"]}.ToString();
   }
   catch {CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();throw;}
  }
  var stored=JObject.Parse(saved);
  foreach(var row in ((JObject)stored["session"]).Properties())SessionState.SetString(row.Name,(string)row.Value);
  AssetDatabase.Objects["Assets/candidate.mat"]=new Material{Json=(string)stored["material"]};
  if(mode=="evidence-change")File.WriteAllText(Path.Combine(Application.dataPath,"candidate.mat"),"human-edit");
  Transport.NextSession="connection-B";
  Window("OnEnable");
  try
  {
   Check(CandidateReload.Pending,"cold_reload_ticket_not_staged");
   if(mode=="cold-cancel")
   {
    var ticket=JObject.Parse((string)stored["session"]["Yukino.VRChatAgent.planned-reload.v1.project-A"]);
    int pid=(int)ticket["owner"]["owner_pid"];
    Window("OnDestroy");CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();
    Check(!CandidateReload.Pending && Transport.OwnedCreated.Count==0,"cancel_reopened_transport");
    bool gone=false;try{using(var process=System.Diagnostics.Process.GetProcessById(pid))gone=process.WaitForExit(2000);}catch(ArgumentException){gone=true;}
    Check(gone,"restored_window_cancel_left_original_owner_alive");return "";
   }
   Check(MaterialCandidateSession.Gate.LocalPlans().Count==0,"ticket_granted_early");
   EditorApplication.Tick();EditorApplication.timeSinceStartup+=0.3;EditorApplication.Tick();
   var timer=System.Diagnostics.Stopwatch.StartNew();
   while(CandidateReload.Pending && timer.Elapsed.TotalSeconds<8){Thread.Sleep(10);EditorApplication.Tick();}
   if(mode=="evidence-change")
   {
    CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();
    Check(!CandidateSession.HasLocalOwner && !CandidateReload.Pending && CandidateSession.Gate.LocalPlans().Count==0 && MaterialCandidateSession.Gate.LocalPlans().Count==0,"changed_evidence_authorized_or_cleanup_failed");
    Check(File.ReadAllText(Path.Combine(Application.dataPath,"candidate.mat"))=="human-edit","human_edit_reverted");return "";
   }
   Check(!CandidateReload.Pending && CandidateSession.LocalOwnerReady,"restore_not_ready: "+CandidateReload.Status+" / "+MaterialCandidateSession.Gate.LastReason);
   if(mode=="live-reads")Check(CandidateSession.Gate.LocalPlans().Count==1 && (bool)CandidateSession.Gate.LocalPlans()[0]["approved"],"live_read_scope_not_resumed");
   var plans=MaterialCandidateSession.Gate.LocalPlans();Check(plans.Count==1 && (bool)plans[0]["approved"],"restored_plan_absent");
   Check((string)plans[0]["plan_id"]==(string)stored["plan"]["plan_id"] && (string)plans[0]["digest"]==(string)stored["plan"]["digest"],"original_approval_changed");
   Check((double)plans[0]["seconds_left"]<300,"approval_extended");
   var tx=MaterialCandidateSession.Gate.LocalTransactions();Check(tx.Count==1 && (bool?)tx[0]["withdrawal_available"]==false,"history_lost_or_undo_restored");
   var wire=(JObject)stored["wire"];wire["connection_id"]="connection-B";wire["body"]=new JObject{["action"]="edit",["arguments"]=new JObject{["property"]="_Glossiness",["value"]=0.6}};
   var result=MaterialCandidateSession.Gate.Dispatch(wire);Check((bool?)result["success"]==true,"restored_execution_denied: "+result);
  }
  finally{CandidateSession.StopLocalOwnerAsync().GetAwaiter().GetResult();}
  Check(!CandidateSession.HasLocalOwner,"cleanup_not_confirmed");return "";
 }
}
