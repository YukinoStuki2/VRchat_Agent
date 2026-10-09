// Real OS transport, controlled process parent, NOT Unity or a human approval.
using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Yukino.VRChatAgent;
static class EditorPeerCases
{
 public static async Task<int> Main(string[] args)
 {
  try {
   using var stop=new CancellationTokenSource();
   if(args[3]=="cancel")stop.CancelAfter(300);
   using var peer=new EditorPeerChannel.HeldPeer(int.Parse(args[0]),long.Parse(args[1]));
   using var channel=await EditorPeerChannel.ConnectAsync(args[2],peer,20,stop.Token);
   byte[] message=Encoding.UTF8.GetBytes("fixture-中文-\0-byte-channel");
   if(args[3]=="queue"){
    var first=channel.ExchangeAsync(message,2,stop.Token);await Task.Delay(30);
    var clock=System.Diagnostics.Stopwatch.StartNew();bool rejected=false;
    try{await channel.ExchangeAsync(message,.1,stop.Token);}catch{rejected=true;}
    double elapsed=clock.Elapsed.TotalSeconds;channel.Dispose();try{await first;}catch{}
    if(!rejected||elapsed>=.8){Console.WriteLine("FAIL queued_deadline");return 3;}
    Console.WriteLine("PASS queued_deadline");return 0;
   }
   byte[] result=await channel.ExchangeAsync(message,5,stop.Token);
   if(Encoding.UTF8.GetString(result)!="reply-中文")throw new Exception("fixture_reply_changed");
   Console.WriteLine("PASS editor_peer_exchange");return 0;
  }catch(Exception e){
   string reason=e is OperationCanceledException?"cancelled":
    (e.Message=="owner_identity_changed"||e.Message=="owner_channel_foreign"||e.Message=="owner_frame_invalid"||
     e.Message=="owner_channel_closed"||e.Message=="owner_channel_expired")?e.Message:e.GetType().Name;
   Console.WriteLine("DENIED "+reason);return 2;
  }
 }
}
