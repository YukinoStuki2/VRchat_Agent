// Only compiled into .NET tests. Replaces old unowned-global fixture setup;
// production has no test hook or arbitrary client adoption method.
using System;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Services.Transport.Transports;
using Yukino.VRChatAgent;
internal static class AdapterOwnedFixture
{
 internal static WebSocketTransportClient Client;
 internal static WebSocketTransportClient Begin(string session="connection-A")
 {
  CandidateSession.StopOwnedAsync().GetAwaiter().GetResult();
  WebSocketTransportClient.NextSession=session;
  if(!CandidateSession.ConnectOwnedAsync(new Uri("wss://127.0.0.1:18081/hub/plugin"),"fixture-bearer-not-real",new byte[32]).GetAwaiter().GetResult())
   throw new Exception("Fixture owned connection failed");
  Client=WebSocketTransportClient.OwnedCreated[WebSocketTransportClient.OwnedCreated.Count-1];
  return Client;
 }
 internal static object Call(JObject r)=>Client.Deliver("vrchat_agent_dispatch",r);
 internal static object Material(JObject r)=>Client.Deliver("vrchat_agent_material_dispatch",r);
}
