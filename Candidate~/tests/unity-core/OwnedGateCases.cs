// Real candidate adapters + gates. Unity, transport and native handlers are doubles.
using System;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Services.Transport;
using MCPForUnity.Editor.Services.Transport.Transports;
using Yukino.VRChatAgent;
internal static class WriteUnityCases {} // TypeCache's deliberate unknown-callback marker.
internal static class OwnedGateCases
{
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Status()=>new JObject{["protocol"]=1,["kind"]="status",["project_id"]="project-A",["connection_id"]="connection-A",["client_id"]="fixture-client",["task_id"]="",["plan_id"]="",["body"]=new JObject()};
 static int Main()
 {
  try {
   MCPServiceLocator.TransportManager.Client=new WebSocketTransportClient{IsConnected=true,State=new TransportState{IsConnected=true,SessionId="connection-A",Details="ws://127.0.0.1:18081/hub/plugin"}};
   Check(!(bool)JObject.FromObject(VrchatAgentDispatch.HandleCommand(Status()))["success"],"OI001 global native route accepted an unowned transport");
   Check(!(bool)JObject.FromObject(VrchatAgentMaterialDispatch.HandleCommand(Status()))["success"],"OI001 global material route accepted an unowned transport");
   Check(typeof(VrchatAgentDispatch).GetCustomAttributes(false).Length==0 && typeof(VrchatAgentMaterialDispatch).GetCustomAttributes(false).Length==0,"OI001 candidate route must not be globally discovered");
   Console.WriteLine("PASS OI001 global paths unregistered and fail closed");
   var host=typeof(CandidateSession);
   var start=host.GetMethod("ConnectOwnedAsync",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
   Check(start!=null,"OI002 missing private owned connector");
   var connected=(System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]});
   Check(connected.GetAwaiter().GetResult(),"OI002 owned positive control failed");
   var owned=WebSocketTransportClient.OwnedCreated[0];
   Check((bool)JObject.FromObject(owned.Deliver("vrchat_agent_dispatch",Status()))["success"],"OI002 actual native gate not reached");
   var materialStatus=Status(); materialStatus["task_id"]="fixture-task";
   Check((bool)JObject.FromObject(owned.Deliver("vrchat_agent_material_dispatch",materialStatus))["success"],"OI002 actual material gate not reached");
   Check(!(bool)JObject.FromObject(VrchatAgentDispatch.HandleCommand(Status()))["success"],"OI002 global bypass active during owned run");
   Check(!(bool)JObject.FromObject(owned.Deliver("execute_anything",Status()))["success"],"OI002 arbitrary command accepted");
   MCPServiceLocator.TransportManager.Client=null;
   Check((bool)JObject.FromObject(owned.Deliver("vrchat_agent_dispatch",Status()))["success"],"OI002 global manager influences owned run");
   Console.WriteLine("PASS OI002 private owned connection reaches both real gates without global manager");
   var stop=host.GetMethod("StopOwnedAsync",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
   Check(stop!=null,"OI003 missing exact-owner asynchronous stop");
   ((System.Threading.Tasks.Task)stop.Invoke(null,null)).GetAwaiter().GetResult();
   Check(CandidateSession.LiveConnection()=="" && owned.Stops==1 && owned.Disposals==1,"OI003 connection survives stop or cleanup missing");
   Check(!(bool)JObject.FromObject(owned.Deliver("vrchat_agent_dispatch",Status()))["success"],"OI003 old callback survives stop");
   Console.WriteLine("PASS OI003 owned stop revokes before releasing exact client");
   WebSocketTransportClient.StopBarrier=new System.Threading.Tasks.TaskCompletionSource<bool>();
   Check(((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI004 second local run failed");
   var second=WebSocketTransportClient.OwnedCreated[1];
   var closing=(System.Threading.Tasks.Task)stop.Invoke(null,null);
   Check(!closing.IsCompleted && CandidateSession.LiveConnection()=="","OI004 cleanup must wait while ingress is already revoked");
   Check(!((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI004 replacement allowed during cleanup");
   Check(!(bool)JObject.FromObject(second.Deliver("vrchat_agent_dispatch",Status()))["success"],"OI004 in-flight cleanup callback accepted");
   WebSocketTransportClient.StopBarrier.SetResult(true);closing.GetAwaiter().GetResult();WebSocketTransportClient.StopBarrier=null;
   Check(second.Stops==1 && second.Disposals==1,"OI004 exact second owner not cleaned");
   Console.WriteLine("PASS OI004 replacement blocked until exact cleanup completes");
   WebSocketTransportClient.StartBarrier=new System.Threading.Tasks.TaskCompletionSource<bool>();
   var starting=(System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]});
   var third=WebSocketTransportClient.OwnedCreated[2];
   var stoppedDuringStart=(System.Threading.Tasks.Task)stop.Invoke(null,null);
   Check(!stoppedDuringStart.IsCompleted,"OI005 cleanup completed before connect continuation settled");
   Check(!((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI005 overlap after stop during startup");
   WebSocketTransportClient.StartBarrier.SetResult(true);
   Check(!starting.GetAwaiter().GetResult(),"OI005 cancelled startup became live");
   stoppedDuringStart.GetAwaiter().GetResult();WebSocketTransportClient.StartBarrier=null;
   Check(third.Disposals==1 && CandidateSession.LiveConnection()=="","OI005 late connect cleanup missing");
   Console.WriteLine("PASS OI005 stop holds owner until late connect continuation is cleaned");
   WebSocketTransportClient.StartBarrier=new System.Threading.Tasks.TaskCompletionSource<bool>();WebSocketTransportClient.StartBarrier.SetResult(false);
   Check(!((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI006 failed transport reported connected");
   var failed=WebSocketTransportClient.OwnedCreated[3];
   Check(failed.Disposals==1 && failed.Stops>0,"OI006 failed startup leaked owned transport");WebSocketTransportClient.StartBarrier=null;
   Check(((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI006 clean failed start permanently occupied slot");
   ((System.Threading.Tasks.Task)stop.Invoke(null,null)).GetAwaiter().GetResult();
   Console.WriteLine("PASS OI006 failed startup cleaned before another explicit local start");
   Check(((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI007 lifecycle run failed");
   var lifecycle=WebSocketTransportClient.OwnedCreated[5];
   UnityEditor.AssemblyReloadEvents.Reload();
   Check(CandidateSession.LiveConnection()=="" && !lifecycle.IsConnected,"OI007 reload leaves private connection live");
   Check(!(bool)JObject.FromObject(lifecycle.Deliver("vrchat_agent_dispatch",Status()))["success"],"OI007 late callback after reload accepted");
   ((System.Threading.Tasks.Task)stop.Invoke(null,null)).GetAwaiter().GetResult();
   Console.WriteLine("PASS OI007 lifecycle force-revokes private ingress synchronously");
   WebSocketTransportClient.NextSession="pending";
   var registering=(System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]});
   Check(!registering.IsCompleted,"OI008 TCP/WS startup mistaken for completed registration");
   var delayed=WebSocketTransportClient.OwnedCreated[6];delayed.State.SessionId="connection-A";
   Check(registering.GetAwaiter().GetResult(),"OI008 delayed registration did not become ready");
   ((System.Threading.Tasks.Task)stop.Invoke(null,null)).GetAwaiter().GetResult();WebSocketTransportClient.NextSession="connection-A";
   Console.WriteLine("PASS OI008 asynchronous native registration awaited, not TCP-only readiness");
   Check(((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI009 run failed");
   var changed=WebSocketTransportClient.OwnedCreated[7];changed.State.SessionId="different-connection";
   Check(CandidateSession.LiveConnection()=="","OI009 replaced session silently adopted");
   changed.State.SessionId="connection-A";
   Check(CandidateSession.LiveConnection()=="","OI009 changed session restored automatically");
   ((System.Threading.Tasks.Task)stop.Invoke(null,null)).GetAwaiter().GetResult();
   Console.WriteLine("PASS OI009 private instance session replacement permanently revokes that run");
   Check(((System.Threading.Tasks.Task<bool>)start.Invoke(null,new object[]{new Uri("wss://127.0.0.1:18081/hub/plugin"),"synthetic-bearer",new byte[32]})).GetAwaiter().GetResult(),"OI010 run failed");
   var dropped=WebSocketTransportClient.OwnedCreated[8];dropped.IsConnected=false;
   Check(CandidateSession.LiveConnection()=="","OI010 dropped socket accepted");dropped.IsConnected=true;
   Check(CandidateSession.LiveConnection()=="","OI010 automatic resurrection after observed disconnect");
   ((System.Threading.Tasks.Task)stop.Invoke(null,null)).GetAwaiter().GetResult();
   Console.WriteLine("PASS OI010 observed unexpected disconnect latches revoked until new local run");
   return 0;
  }catch(Exception e){Console.Error.WriteLine("FAIL "+e);return 1;}
 }
}
