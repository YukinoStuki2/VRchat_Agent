// Deliberate transport double: actual TLS/C# transport tested by verify_owned_transport.py.
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
namespace MCPForUnity.Editor.Services.Transport.Transports
{
 public sealed class CandidateOwnedWebSocketTransportClient : WebSocketTransportClient
 {
  public CandidateOwnedWebSocketTransportClient(Uri endpoint,string bearer,byte[] pin,Func<string,JObject,object> dispatch)
   :base(endpoint,bearer,pin,dispatch){}
 }
 public partial class WebSocketTransportClient
 {
  public static readonly List<WebSocketTransportClient> OwnedCreated=new List<WebSocketTransportClient>();
  public static string NextSession="connection-A";
  public static TaskCompletionSource<bool> StartBarrier;
  public static TaskCompletionSource<bool> StopBarrier;
  public int Stops,Disposals;
  readonly Func<string,JObject,object> handler;
  public WebSocketTransportClient(){}
  public WebSocketTransportClient(Uri endpoint,string bearer,byte[] pin,Func<string,JObject,object> dispatch)
  {handler=dispatch;State=new MCPForUnity.Editor.Services.Transport.TransportState{IsConnected=false,SessionId=NextSession,Details=endpoint.AbsoluteUri};OwnedCreated.Add(this);}
  public async Task<bool> StartAsync()
  {bool ok=StartBarrier==null || await StartBarrier.Task;IsConnected=ok;State.IsConnected=ok;return ok;}
  public async Task StopAsync()
  {Stops++;IsConnected=false;State.IsConnected=false;if(StopBarrier!=null)await StopBarrier.Task;}
  public void ForceStop(){IsConnected=false;State.IsConnected=false;}
  public void Dispose(){Disposals++;IsConnected=false;State.IsConnected=false;}
  public object Deliver(string command,JObject args)=>handler(command,args);
 }
}
