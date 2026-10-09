// Actual C# private Process + Python runtime on either OS. Synthetic Unity wire.
using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class EditorBootstrapCases
{
 static async Task<int> Main(string[] args)
 {
  if(args.Length==1 && args[0]=="--selection-tests"){PortableSelectionCases.Run();return 0;}
  if(args.Length==3 && args[0]=="--client-admission-tests"){await ClientAdmissionCases.Run(args[1],args[2]);return 0;}
  if(args.Length==3 && args[0]=="--restore-tests")return await EditorRestoreCases.Run(args[1],args[2]);
  if(args.Length==3 && args[0]=="--prepare-tests")return await EditorRestoreCases.Prepare(args[1],args[2]);
  if(args.Length==3 && args[0]=="--cancel-tests")return await EditorRestoreCases.Prepare(args[1],args[2],true);
  bool reload=args.Length==3 && args[0]=="--reload-control-tests";
  if(reload)args=new[]{args[1],args[2]};
  string project=reload?"fixture-editor-control-"+Process.GetCurrentProcess().Id:"fixture-project";
  bool portable=args.Length==1;
  string python=portable?EditorOwnerProcess.ResolvePortablePython(args[0]):args[0];
  string entry=portable?Path.Combine(args[0],"Runtime~","launcher","editor_owner.py"):args[1];
  foreach(bool dispose in new[]{false,true})
  {
   ClientWebSocket ws=null;Task peer=null;int port=0;bool closing=false;
   using(var owner=new EditorOwnerProcess())
   {
    async Task<bool> Connect(Uri endpoint,string token,byte[] pin)
    {
     port=endpoint.Port;ws=new ClientWebSocket();
     ws.Options.RemoteCertificateValidationCallback=(_,certificate,chain,error)=>{
      using(var hash=SHA256.Create())return Convert.ToBase64String(hash.ComputeHash(certificate.GetRawCertData()))==Convert.ToBase64String(pin);
     };
     ws.Options.SetRequestHeader("Authorization","Bearer "+token);
     await ws.ConnectAsync(endpoint,CancellationToken.None);
     await Receive(ws);
     await Send(ws,new JObject{["type"]="register",["project_hash"]=project,["project_name"]="TEST",["unity_version"]="FIXTURE"});
     if((string)(await Receive(ws))["type"]!="registered")return false;
     peer=Task.Run(async()=>{
      try {
       while(ws.State==WebSocketState.Open){
        var command=await Receive(ws);
        await Send(ws,new JObject{["type"]="command_result",["id"]=command["id"],
         ["result"]=new JObject{["status"]="success",["result"]=new JObject{["success"]=true,["data"]=new JObject{["read_only"]=true}}}});
       }
      } catch(WebSocketException){} catch(ObjectDisposedException){} catch(IOException){}
       catch(OperationCanceledException) when(closing){}
     });
     return true;
    }
    async Task Close(){closing=true;if(ws!=null){ws.Abort();if(peer!=null)await peer;ws.Dispose();}}
    try
    {
     if(!await owner.StartAsync(python,entry,project,Connect,Close,enableReloadControl:reload)){Console.WriteLine("FAIL ECP001 owner_start_refused");return 3;}
     if(!owner.Ready)return 4;
     if(reload){
      var status=await owner.RequestReloadControlAsync(new JObject{["kind"]="status"});
      if(!JToken.DeepEquals(status,new JObject{["kind"]="editor_control_status",["phase"]="idle"}))return 8;
     }
     int pid=owner.OwnerPid;
     if(dispose){owner.Dispose();await Close();}else await owner.StopAsync();
     if(owner.Ready || (!dispose && !owner.CleanupComplete))return 5;
     try{using(var process=Process.GetProcessById(pid)){if(!process.HasExited)return 6;}}catch(ArgumentException){}
     using(var probe=new TcpClient()){
      try{await probe.ConnectAsync("127.0.0.1",port);return 7;}catch(SocketException){}
     }
     Console.WriteLine(reload?(dispose?"PASS ECP004 controlled-dispose-child-and-listener-absent":"PASS ECP003 controlled-ready-stop-session-child-and-listener"):
      (dispose?"PASS ECP002 dispose-child-and-listener-absent":"PASS ECP001 ready-stop-session-child-and-listener"));
    }
    finally{await Close();}
   }
  }
  return 0;
 }
 static async Task Send(ClientWebSocket ws,JObject value){var bytes=Encoding.UTF8.GetBytes(value.ToString(Newtonsoft.Json.Formatting.None));await ws.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,CancellationToken.None);}
 static async Task<JObject> Receive(ClientWebSocket ws){
  byte[] buffer=new byte[16384];int count=0;
  while(count<buffer.Length){var message=await ws.ReceiveAsync(new ArraySegment<byte>(buffer,count,buffer.Length-count),CancellationToken.None);if(message.MessageType!=WebSocketMessageType.Text)throw new IOException();count+=message.Count;if(message.EndOfMessage)return JObject.Parse(Encoding.UTF8.GetString(buffer,0,count));}
  throw new IOException();
 }
}
