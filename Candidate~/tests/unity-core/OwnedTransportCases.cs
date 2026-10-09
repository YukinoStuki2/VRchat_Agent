using System;
using System.Reflection;
using System.Threading.Tasks;
using WebSocketTransportClient = MCPForUnity.Editor.Services.Transport.Transports.CandidateOwnedWebSocketTransportClient;
using MCPForUnity.Editor.Services.Transport;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json.Linq;
class OwnedTransportCases {
 static void Check(bool x,string why){if(!x)throw new Exception(why);}
 static async Task Main(string[] args){
  var ctor=typeof(WebSocketTransportClient).GetConstructor(new[]{typeof(Uri),typeof(string),typeof(byte[]),typeof(Func<string,JObject,object>)});
  Check(ctor!=null,"OT001 missing isolated endpoint/credential/pin/dispatch constructor");
  Check(typeof(WebSocketTransportClient).GetConstructors().Length==1,"OD004 public discovery constructor exposed");
  var original=typeof(MCPForUnity.Editor.Services.Transport.Transports.WebSocketTransportClient);
  Check(original.GetConstructor(new[]{typeof(Uri),typeof(string),typeof(byte[]),typeof(Func<string,JObject,object>)})==null,"OD004 original upstream type modified");
  Check(original.Assembly==typeof(WebSocketTransportClient).Assembly && original.Assembly!=typeof(OwnedTransportCases).Assembly,"OD003 asmref boundary not represented");
  if(args.Length==0){Console.WriteLine("PASS OT001");return;}
  int calls=0;
  async Task<object> Delayed(){await Task.Delay(25);return new {success=true,data=new {probe="owned-native-wire"}};}
  Func<string,JObject,object> handler=(name,p)=>{calls++; return Delayed();};
  byte[] pin=Convert.FromHexString(args[1]);
  var client=(WebSocketTransportClient)ctor.Invoke(new object[]{new Uri(args[0]),Environment.GetEnvironmentVariable("FIXTURE_UNITY_BEARER") ?? "fixture-bearer-not-real",pin,handler});
  Array.Clear(pin,0,pin.Length); // original array must not change the captured pin
  try {
   bool started=await client.StartAsync();
   if(args[2]=="bad-pin"){Check(!started,"OT002 wrong server certificate accepted");}
   else {
    Check(started,"OT003 connect failed");
    var deadline=DateTime.UtcNow.AddSeconds(5);
    while((string.IsNullOrEmpty(client.State.SessionId) || client.State.SessionId=="pending") && DateTime.UtcNow<deadline)await Task.Delay(10);
    Check(!string.IsNullOrEmpty(client.State.SessionId) && client.State.SessionId!="pending","OT003 registration lost or late state overwritten");
    if(args[2]!="sdk-wire")Check(client.State.SessionId=="fixture-session","OT003 wrong fixture session");
    while(client.IsConnected && DateTime.UtcNow<deadline)await Task.Delay(10);
    Check(!client.IsConnected,"OT004 close must invalidate immediately");
    await Task.Delay(100);
    Check(calls==(args[2]=="duplicate-register" ? 0 : 1),"OT005 private dispatcher count");
    Check(OwnedFixtureObservation.GlobalCalls==0,"OT005 global dispatcher reached");
    Check(OwnedFixtureObservation.MainCalls==(args[2]=="duplicate-register" ? 0 : 1),"OT005 private dispatch bypassed main-thread seam");
   }
   Check(OwnedFixtureObservation.ProjectWrites==0,"OT006 session prefs written");
   Check(OwnedFixtureObservation.EndpointReads==0 && UnityEditor.EditorPrefs.Reads==0,"OT006 shared endpoint/prefs read");
   Check(!await client.StartAsync(),"OT007 owned instance restarted without new local run");
   Console.WriteLine("PASS "+args[2]);
  } finally {await client.StopAsync();client.Dispose();}
 }
}
