// Real child/file/pipe tests; package layout and review context are fixtures.
using System;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class ReviewCaptureCases
{
 static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
 sealed class PausedEditorContext:SynchronizationContext
 {
  readonly System.Collections.Concurrent.ConcurrentQueue<Action> pending=new System.Collections.Concurrent.ConcurrentQueue<Action>();
  public override void Post(SendOrPostCallback callback,object state){pending.Enqueue(()=>callback(state));}
  internal void Pump(){while(pending.TryDequeue(out var action))action();}
 }
 static MethodInfo method;
 static string package,python,source;
 static Task<byte[]> Capture(string name,CancellationToken token=default)=>(Task<byte[]>)method.Invoke(null,new object[]{package,source,name,token,python});
 static void Copy(string from,string to){Directory.CreateDirectory(to);foreach(string f in Directory.GetFiles(from))File.Copy(f,Path.Combine(to,Path.GetFileName(f)));}
 static async Task Refused(string name,CancellationToken token=default){bool refused=false;try{await Capture(name,token);}catch(Exception e){Check(e.Message=="local_review_capture_refused","private exception escaped");refused=true;}Check(refused,"invalid capture succeeded");}
 static async Task<int> Main(string[] args)
 {
  string temp=Path.Combine(Path.GetTempPath(),"review-capture-"+Guid.NewGuid().ToString("N"));
  try {
   method=typeof(EditorOwnerProcess).GetMethod("CaptureReviewAsync",BindingFlags.Static|BindingFlags.NonPublic);
   Check(method!=null,"editor_owned_review_capture_missing");
   python=args[0];string root=args[1];package=Path.Combine(temp,"FixturePackage");source=Path.Combine(temp,"selected");
   Directory.CreateDirectory(source);
   foreach(string folder in new[]{"diagnostics","launcher"})Copy(Path.Combine(root,folder),Path.Combine(package,"Runtime~",folder));
   byte[] expected=Encoding.UTF8.GetBytes("{\"fixture\":\"合成记录—not an approval\"}");
   File.WriteAllBytes(Path.Combine(source,"review.json"),expected);
   Check(Convert.ToBase64String(await Capture("review.json"))==Convert.ToBase64String(expected),"owned bytes changed");
   Console.WriteLine("PASS RC001 actual_editor_owner_private_helper_returns_exact_bytes");
   foreach(string name in new[]{"missing.json","../review.json","anything.cs"})await Refused(name);
   using(var cancelled=new CancellationTokenSource()){cancelled.Cancel();await Refused("review.json",cancelled.Token);}
   File.WriteAllBytes(Path.Combine(source,"too-big.json"),new byte[262145]);await Refused("too-big.json");
   Console.WriteLine("PASS RC002 invalid_selection_and_precancel_never_return_bytes");
   var now=DateTimeOffset.UtcNow;var context=JObject.Parse("{project_id:'fixture',editor:'fixture',candidate_sha256:'"+new string('a',64)+"',code:{fixture:'"+new string('b',64)+"'},dependencies:{},callbacks:[],complete:true}");
   var record=new JObject{["schema"]=1,["purpose"]="asset_load_callbacks",["target"]="AssetReads/Assets/Scope",["reviewer"]="fixture not real review",["reviewed_at_utc"]=now.AddMinutes(-1).ToString("O"),["expires_at_utc"]=now.AddMinutes(5).ToString("O"),["conclusion"]="reviewed",["unassessed_callbacks"]=new JArray(),["context"]=context};
   File.WriteAllText(Path.Combine(source,"record.json"),record.ToString(),new UTF8Encoding(false));
   var review=new AssetCallbackReview(()=>context,()=>DateTimeOffset.UtcNow,()=>1,()=>{});
   var digest=await review.StageCapturedLocalAsync(()=>Capture("record.json"));
   Check(digest!=null && review.Evidence("AssetReads/Assets/Scope")==null,"actual owner auto-approved or failed");
   Check(review.ConfirmLocal(digest),"fixture separate confirmation failed");
   Console.WriteLine("PASS RC003 actual_owner_to_review_core_stages_without_confirmation");
   var paused=new PausedEditorContext();var oldContext=SynchronizationContext.Current;Task<byte[]> independent;
   using(var cancel=new CancellationTokenSource())
   {
    try {SynchronizationContext.SetSynchronizationContext(paused);independent=Capture("review.json",cancel.Token);}
    finally {SynchronizationContext.SetSynchronizationContext(oldContext);}
    bool completed=await Task.WhenAny(independent,Task.Delay(3000))==independent;
    if(!completed){cancel.Cancel();for(int i=0;i<200 && !independent.IsCompleted;i++){paused.Pump();await Task.Delay(20);}try{await independent;}catch{}}
    Check(completed,"capture cleanup depends on paused Editor continuations");
    Check((await independent).Length==expected.Length,"paused Editor changed capture");
   }
   Console.WriteLine("PASS RC004 process_lifetime_does_not_depend_on_editor_message_pump");
   string helper=Path.Combine(package,"Runtime~","diagnostics","asset_review.py");
   foreach(string mode in new[]{"oversize","stderr","nonzero","timeout","cancel"})
   {
    string marker=Path.Combine(source,"started");if(File.Exists(marker))File.Delete(marker);
    string code="import sys,time,pathlib,os\n"+
     "pathlib.Path("+JToken.FromObject(marker).ToString(Newtonsoft.Json.Formatting.None)+").write_text(str(os.getpid()))\n";
    if(mode=="oversize")code+="sys.stdout.buffer.write(b'x'*262145);sys.stdout.flush()\n";
    else if(mode=="stderr")code+="sys.stdout.write('{}');sys.stderr.write('private path must not escape')\n";
    else if(mode=="nonzero")code+="sys.stdout.write('{}');sys.exit(2)\n";
    else code+="time.sleep(60)\n";
    File.WriteAllText(helper,code,new UTF8Encoding(false));
    using(var cancel=new CancellationTokenSource())
    {
     Task<byte[]> capture=Capture("review.json",cancel.Token);
     var timer=System.Diagnostics.Stopwatch.StartNew();
     while(!File.Exists(marker) && !capture.IsCompleted && timer.Elapsed.TotalSeconds<3)await Task.Delay(10);
     Check(File.Exists(marker),"fault fixture did not start");
     int pid=int.Parse(File.ReadAllText(marker));
     if(mode=="cancel")cancel.Cancel();
     bool refused=false;try{await capture;}catch(Exception e){Check(e.Message=="local_review_capture_refused","child diagnostics escaped");refused=true;}
     Check(refused,"faulty helper accepted: "+mode);
     Check(!Directory.Exists("/proc/"+pid),"owned child survives refused capture");
    }
   }
   Console.WriteLine("PASS RC005 oversize_stderr_exit_timeout_and_cancel_cleanup_actual_children");
   return 0;
  }catch(Exception e){Console.Error.WriteLine(e);return 1;}
  finally {if(Directory.Exists(temp))Directory.Delete(temp,true);}
 }
}
