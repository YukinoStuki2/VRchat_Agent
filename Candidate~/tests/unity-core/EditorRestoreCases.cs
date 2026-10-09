// C# restore API over a real OS channel; owner/grant/TLS replies are explicit
// test fixtures. This does not claim an actual Editor or domain reload.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
static class EditorRestoreCases
{
 internal static async Task<int> Prepare(string python,string fixture,bool cancel=false)
 {
  var arm=typeof(EditorOwnerProcess).GetMethod("ArmReloadAsync",BindingFlags.Instance|BindingFlags.NonPublic);
  var detach=typeof(EditorOwnerProcess).GetMethod("DetachReloadAsync",BindingFlags.Instance|BindingFlags.NonPublic);
  if(arm==null||detach==null){Console.WriteLine("FAIL ECP007 missing_local_arm_detach");return 20;}
  Func<Uri,string,byte[],Task<bool>> connect=(uri,token,pin)=>Task.FromResult(true);
  Func<Task> close=()=>Task.CompletedTask;
  using(var first=new EditorOwnerProcess())using(var second=new EditorOwnerProcess())
  {
   if(!await first.StartAsync(python,fixture,"restore-fixture",connect,close,enableReloadControl:true))return 21;
   var ticket=await (Task<JObject>)arm.Invoke(first,new object[]{new string('d',32),new[]{"{}"},1.0,20.0});
   if(ticket==null)return 22;
   var detached=await (Task<JObject>)detach.Invoke(first,new object[]{});
   if(!JToken.DeepEquals(ticket,detached)||first.Ready)return 23;
   if(cancel){await first.StopAsync();if(!first.CleanupComplete)return 26;Console.WriteLine("PASS ECP008 detached-local-stop-no-reattach");return 0;}
   first.Dispose(); // Must not terminate the explicitly detached original owner.
   var raw=await second.ReattachAsync(detached,"restore-fixture",connect,close);
   if(raw==null||raw.Count!=1||second.Ready)return 24;
   await second.RequestReloadControlAsync(new JObject{["kind"]="commit",["handoff_id"]=new string('d',32),["connection_id"]="fixture-new",["bindings"]=new JArray(new string('a',64))});
   await second.StopAsync();if(!second.CleanupComplete)return 25;
  }
  Console.WriteLine("PASS ECP007 arm-detach-new-managed-owner-same-os-process-fixture");return 0;
 }
 internal static async Task<int> Run(string python,string fixture)
 {
  var restore=typeof(EditorOwnerProcess).GetMethod("ReattachAsync",BindingFlags.Instance|BindingFlags.NonPublic);
  if(restore==null){Console.WriteLine("FAIL ECP005 missing_ReattachAsync");return 9;}
  foreach(string mode in new[]{"valid","changed-transfer"})
  {
   var info=new ProcessStartInfo(python){Arguments="-I -B \""+fixture+"\" "+mode,UseShellExecute=false,CreateNoWindow=true,
    RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8};
   using(var process=Process.Start(info))using(var owner=new EditorOwnerProcess())
   {
    var stderr=process.StandardError.ReadToEndAsync();
    try
    {
     var line=process.StandardOutput.ReadLineAsync();if(await Task.WhenAny(line,Task.Delay(5000))!=line)return 10;
     var ticket=JObject.Parse(await line);if((int)ticket["owner_pid"]!=process.Id)return 11;
     int connects=0;
     Func<Uri,string,byte[],Task<bool>> connect=(uri,token,pin)=>{connects++;return Task.FromResult(uri.Scheme=="wss"&&pin.Length==32);};
     Func<Task> close=()=>Task.CompletedTask;
     var transferred=await (Task<JArray>)restore.Invoke(owner,new object[]{ticket,"restore-fixture",connect,close});
     if(mode=="changed-transfer")
     {if(transferred!=null||connects!=0||owner.Ready)return 12;}
     else
     {
      if(transferred==null||transferred.Count!=1||connects!=1||owner.Ready)return 13;
      var result=await owner.RequestReloadControlAsync(new JObject{["kind"]="commit",["handoff_id"]=(string)ticket["handoff_id"],["connection_id"]="new-fixture",["bindings"]=new JArray(new string('a',64))});
      if((string)result["kind"]!="committed"||!owner.Ready)return 14;
      await owner.StopAsync();if(!owner.CleanupComplete)return 15;
     }
     process.StandardInput.Close();
     if(!process.WaitForExit(5000)||process.ExitCode!=0)return 16;
     if((await stderr).Length!=0)return 17;
     Console.WriteLine(mode=="valid"?"PASS ECP005 restored-local-channel-lifecycle-fixture":"PASS ECP006 changed-transfer-rejected-before-connect");
    }
    finally
    {
     process.StandardInput.Close();
     if(!process.WaitForExit(5000)){process.Kill();process.WaitForExit();throw new Exception("fixture_forced_cleanup");}
     await stderr;
    }
   }
  }
  return 0;
 }
}
