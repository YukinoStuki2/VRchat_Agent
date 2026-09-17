using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using Yukino.VRChatAgentLauncher;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Services.Transport.Transports;
class Program {
 static int checks;
 static void Check(bool ok,string message){if(!ok)throw new Exception(message);checks++;}
 sealed class QueueContext:SynchronizationContext {
  readonly Queue<Action> queue=new Queue<Action>();
  public override void Post(SendOrPostCallback d,object s){queue.Enqueue(()=>d(s));}
  public void Drain(){int n=0;while(queue.Count>0){if(++n>1000)throw new Exception("continuation loop");queue.Dequeue()();}}
 }
 static void ManagedStub(){
  var a=AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("Yukino.VRChatManagedEditing.Editor"),AssemblyBuilderAccess.Run);
  var t=a.DefineDynamicModule("m").DefineType("Yukino.VRChatManagedEditing.ManagedSession");
  t.DefineMethod("Revoke",MethodAttributes.Static|MethodAttributes.Assembly,typeof(void),Type.EmptyTypes).GetILGenerator().Emit(OpCodes.Ret);t.CreateType();
 }
 static void Set(string field,object value)=>typeof(LauncherSession).GetField(field,BindingFlags.Static|BindingFlags.NonPublic).SetValue(null,value);
 static string PrepareRun(){
  string dir=Path.Combine(Path.GetTempPath(),"launcher-review-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);
  SessionState.SetString("Yukino.AgentLauncher.Run",dir);SessionState.SetBool("Yukino.AgentLauncher.Stopping",false);SessionState.SetBool("Yukino.AgentLauncher.TransportClean",true);
  var t=typeof(LauncherSession).GetNestedType("RunGeneration",BindingFlags.NonPublic);
  Set("generation",Activator.CreateInstance(t,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,new object[]{dir},null));
  WriteStatus(dir,"sidecar_ready",false);return dir;
 }
 static void WriteStatus(string dir,string phase,bool clean){File.WriteAllText(Path.Combine(dir,"status.json"),"{\"phase\":\""+phase+"\",\"cleanup_complete\":"+(clean?"true":"false")+"}");}
 static void Poll(){EditorApplication.timeSinceStartup+=1;LauncherSession.Tick();}
 static int Main(){
  RecoveryTests.Run();
  ManagedStub(); var ctx=new QueueContext();SynchronizationContext.SetSynchronizationContext(ctx);
  string[,] pairs={{"","\"\""},{"C:\\path with spaces\\file.py","\"C:\\path with spaces\\file.py\""},{"a\"b","\"a\\\"b\""},{"a\\","\"a\\\\\""}};
  for(int i=0;i<pairs.GetLength(0);i++)Check(LauncherSettings.QuoteArgument(pairs[i,0])==pairs[i,1],"quoting "+i);
  Check(!LauncherSession.Busy && LauncherSession.Phase=="idle","cold import");Poll();AssemblyReloadEvents.Fire();Check(!LauncherSession.Busy,"passive/reload started");
  Check(CoplayAdapter.Prerequisite()=="","pinned stub API");
  UnityEditor.PackageManager.PackageInfo.CoplayVersion="11.0.0";Check(CoplayAdapter.Prerequisite()!="","version mismatch accepted");UnityEditor.PackageManager.PackageInfo.CoplayVersion="10.2.0";
  var user=new WebSocketTransportClient();MCPServiceLocator.TransportManager.Client=user;
  var pendingUser=new TaskCompletionSource<bool>();MCPServiceLocator.TransportManager.SetInFlight(pendingUser.Task);
  Check(CoplayAdapter.ManagerBusy,"in-flight user not rejected");pendingUser.SetResult(true);MCPServiceLocator.TransportManager.SetInFlight(null);
  user.StartAsync().GetAwaiter().GetResult();Check(CoplayAdapter.ManagerBusy,"connected user not rejected");
  string denied=PrepareRun();Poll();Check(user.Stops==0 && File.Exists(Path.Combine(denied,"stop")),"user connection stolen");WriteStatus(denied,"stopped",true);Poll();Check(!LauncherSession.Busy,"denied run not cleaned");
  user.StopAsync().GetAwaiter().GetResult();int userStops=user.Stops;
  string changed=PrepareRun();HttpEndpointUtility.Url="http://example.invalid:18081";Poll();Check(File.Exists(Path.Combine(changed,"stop")),"changed endpoint accepted");WriteStatus(changed,"stopped",true);Poll();HttpEndpointUtility.Url=CoplayAdapter.Endpoint;
  string run=PrepareRun();var start=new TaskCompletionSource<bool>();WebSocketTransportClient.NextStart=start;Poll();var owned=WebSocketTransportClient.Last;
  Check(!ReferenceEquals(owned,user),"manager reused");Check(LauncherSession.Busy,"connect not busy");
  LauncherSession.RequestStop();WriteStatus(run,"stopped",true);SynchronizationContext.SetSynchronizationContext(null);start.SetResult(true);SynchronizationContext.SetSynchronizationContext(ctx);Poll();
  Check(LauncherSession.Busy,"released before queued connect continuation");LauncherSession.Start(new LauncherSettings());Check(SessionState.GetString("Yukino.AgentLauncher.Run","")==run,"new run replaced pending generation");
  ctx.Drain();Poll();Check(!LauncherSession.Busy && !owned.IsConnected,"late start not stopped");Check(user.Stops==userStops,"manager stopped during own cleanup");
  string failed=PrepareRun();Poll();WebSocketTransportClient.FailNextStop=true;LauncherSession.RequestStop();WriteStatus(failed,"stopped",true);Poll();Check(LauncherSession.Busy,"stop failure erased ownership");
  AssemblyReloadEvents.Fire();ctx.Drain();Poll();Check(!LauncherSession.Busy,"verified lifecycle abort not accepted");
  string abortFail=PrepareRun();WebSocketTransportClient.ThrowOnCancel=true;Poll();WebSocketTransportClient.ThrowOnCancel=false;AssemblyReloadEvents.Fire();WriteStatus(abortFail,"stopped",true);Poll();Check(LauncherSession.Busy,"cancellation failure acknowledged");
  AssemblyReloadEvents.Fire();Poll();Check(!LauncherSession.Busy,"second verified abort failed");
  string delayedStop=PrepareRun();Poll();var stop=new TaskCompletionSource<bool>();WebSocketTransportClient.NextStop=stop;LauncherSession.RequestStop();WriteStatus(delayedStop,"stopped",true);Poll();Check(LauncherSession.Busy,"unfinished StopAsync accepted");stop.SetResult(true);ctx.Drain();Poll();Check(!LauncherSession.Busy,"finished StopAsync not acknowledged");
  string noPython=PrepareRun();Poll();LauncherSession.RequestStop();Poll();Check(LauncherSession.Busy,"no Python ack accepted");WriteStatus(noPython,"stopped",true);Poll();Check(!LauncherSession.Busy,"dual ack not accepted");
  string reload=PrepareRun();Poll();user.StartAsync().GetAwaiter().GetResult();userStops=user.Stops;AssemblyReloadEvents.Fire();Check(user.Stops==userStops && user.IsConnected,"reload stole user replacement");Set("generation",null);WriteStatus(reload,"stopped",true);Poll();Check(!LauncherSession.Busy,"reload verified proof lost");
  Check(user.IsConnected,"recovery stopped manager");
  user.StopAsync().GetAwaiter().GetResult();
  LauncherSession.WindowOpen=true;
  typeof(LauncherSession).GetProperty("IsReloading",BindingFlags.Static|BindingFlags.NonPublic).SetValue(null,false);
  var recovery=new RecoveryState();
  string project=Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath,".."));
  string settings=UnityEngine.JsonUtility.ToJson(new LauncherSettings {autoRecoverAfterImport=true});
  recovery.Remember(true,project,settings);Set("recovery",recovery);
  string importing=PrepareRun();Poll();WriteStatus(importing,"connected",false);Poll();
  EditorApplication.isUpdating=true;Poll();
  Check(LauncherSession.RecoveryPending && File.Exists(Path.Combine(importing,"stop")),"import did not pause owned run");
  Check(!LauncherSession.OwnedConnected,"pause still exposes owned connection");
  WriteStatus(importing,"stopped",true);Poll();Check(!LauncherSession.Busy && LauncherSession.RecoveryPending,"cleanup lost recovery intent");
  for(int i=0;i<8;i++)Poll();Check(LauncherSession.RecoveryPending && !LauncherSession.Busy,"recovered while editor busy");
  EditorApplication.isUpdating=false;Poll();
  for(int i=0;i<4;i++)Poll();Check(LauncherSession.RecoveryPending,"quiet window too short");
  Poll();Check(!LauncherSession.RecoveryPending && LauncherSession.Phase=="error","automatic attempt not consumed before failing validation");
  for(int i=0;i<8;i++)Poll();Check(!LauncherSession.Busy && !LauncherSession.RecoveryPending,"auto retry loop");
  recovery=new RecoveryState();recovery.Remember(true,project,settings);Set("recovery",recovery);
  string reloading=PrepareRun();Poll();WriteStatus(reloading,"connected",false);Poll();AssemblyReloadEvents.Fire();
  Check(LauncherSession.RecoveryPending,"reload lost ticket");LauncherSession.WindowClosed();Check(LauncherSession.RecoveryPending,"reload OnDisable canceled intent");
  string saved=SessionState.GetString("Yukino.AgentLauncher.Recovery","");
  Set("generation",null);Set("recovery",UnityEngine.JsonUtility.FromJson<RecoveryState>(saved));
  typeof(LauncherSession).GetProperty("IsReloading",BindingFlags.Static|BindingFlags.NonPublic).SetValue(null,false);
  WriteStatus(reloading,"stopped",true);Poll();Check(LauncherSession.RecoveryPending && !LauncherSession.Busy,"reload cleanup proof lost");
  LauncherSession.WindowOpen=true;LauncherSession.WindowClosed();Check(!LauncherSession.RecoveryPending,"real close did not cancel");
  recovery=new RecoveryState();recovery.Remember(true,project,settings);recovery.Connected();recovery.BeginPause(EditorApplication.timeSinceStartup,project);Set("recovery",recovery);
  LauncherSession.RequestStop();Check(!LauncherSession.RecoveryPending,"manual stop while waiting failed");
  recovery.Remember(true,project,settings);recovery.Connected();recovery.BeginPause(EditorApplication.timeSinceStartup,project);EditorApplication.Quit();Check(!LauncherSession.RecoveryPending,"quit failed to cancel");
  recovery.Remember(true,project,settings);recovery.Connected();recovery.BeginPause(EditorApplication.timeSinceStartup,project);
  typeof(LauncherSession).GetProperty("IsReloading",BindingFlags.Static|BindingFlags.NonPublic).SetValue(null,true);
  LauncherSession.WindowClosed(true);Check(!LauncherSession.RecoveryPending,"destroyed window during reload failed to cancel");
  recovery.Remember(true,project,settings);recovery.Connected();recovery.BeginPause(EditorApplication.timeSinceStartup,project);
  recovery.Ready(EditorApplication.timeSinceStartup,project,false,true,true);
  double originalDeadline=recovery.Deadline;
  AssemblyReloadEvents.Fire();
  Check(recovery.QuietSince<0 && recovery.Deadline==originalDeadline,"reload during cleaned wait did not reset quiet without extending deadline");
  LauncherSession.RequestStop();
  typeof(LauncherSession).GetProperty("IsReloading",BindingFlags.Static|BindingFlags.NonPublic).SetValue(null,false);
  LauncherSession.WindowOpen=true;Set("lastImport",-1d);
  recovery.Remember(true,project,settings);string network=PrepareRun();Poll();WriteStatus(network,"connected",false);Poll();
  File.WriteAllText(Path.Combine(network,"status.json"),"{\"phase\":\"error\",\"code\":\"PROJECT_UNAVAILABLE\",\"cleanup_complete\":true}");Poll();
  Check(!LauncherSession.RecoveryPending && !LauncherSession.Busy,"ordinary network failure auto recovered");
  recovery.Remember(true,project,settings);string changedProject=PrepareRun();Poll();WriteStatus(changedProject,"connected",false);Poll();
  EditorApplication.isUpdating=true;Poll();
  File.WriteAllText(Path.Combine(changedProject,"status.json"),"{\"phase\":\"error\",\"code\":\"PROJECT_CHANGED\",\"cleanup_complete\":true}");Poll();
  Check(!LauncherSession.RecoveryPending,"real project change retained ticket");EditorApplication.isUpdating=false;
  foreach(string dir in new[]{network,changedProject,importing,reloading})Directory.Delete(dir,true);
  foreach(string dir in new[]{denied,changed,run,failed,abortFail,delayedStop,noPython,reload})Directory.Delete(dir,true);
  Console.WriteLine("PASS "+checks+" assertions: owned transport, endpoint preflight, delayed continuations, stop/abort failures, dual acknowledgements, lifecycle isolation. C#9 TEST DOUBLES ONLY; not Unity/Windows runtime verification.");return 0;
 }
}
