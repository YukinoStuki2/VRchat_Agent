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
  foreach(string dir in new[]{denied,changed,run,failed,abortFail,delayedStop,noPython,reload})Directory.Delete(dir,true);
  Console.WriteLine("PASS "+checks+" assertions: owned transport, endpoint preflight, delayed continuations, stop/abort failures, dual acknowledgements, lifecycle isolation. C#9 TEST DOUBLES ONLY; not Unity/Windows runtime verification.");return 0;
 }
}
