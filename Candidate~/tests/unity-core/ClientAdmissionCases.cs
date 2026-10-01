// Actual private Process contract with a synthetic non-network owner; no real credentials.
using System;
using System.IO;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class ClientAdmissionCases
{
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 internal static async Task Run(string python,string directHelper)
 {
  var build=typeof(EditorOwnerProcess).GetMethod("HermesArguments",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
  Check(build!=null,"CS008 missing restricted SSH settings builder");
  var settings=new JObject{["host"]="fixture.invalid",["user"]="fixture",["port"]=22022,["remote_port"]=18088};
  string output=(string)build.Invoke(null,new object[]{settings,true});
  Check(output.Contains("--hermes-host \"fixture.invalid\"") && output.Contains("--hermes-forward-port 18088"),"CS008 exact settings not passed");
  foreach(string field in new[]{"host","user","port","remote_port","extra"}) {
   var bad=(JObject)settings.DeepClone();
   if(field=="host")bad[field]="-oProxyCommand=sh";
   else if(field=="user")bad[field]="a;id";
   else if(field=="extra")bad[field]="unsupported";
   else bad[field]=0;
   bool refused=false;try{build.Invoke(null,new object[]{bad,true});}catch(System.Reflection.TargetInvocationException){refused=true;}
   Check(refused,"CS008 invalid SSH field accepted "+field);
  }
  bool disabled=false;try{build.Invoke(null,new object[]{settings,false});}catch(System.Reflection.TargetInvocationException){disabled=true;}
  Check(disabled,"CS008 unselected Hermes accepted remote settings");
  Check((string)build.Invoke(null,new object[]{null,false})=="","CS008 default must be inert");
  Console.WriteLine("PASS CS008 structured SSH arguments and selection boundary");
  var codexArgs=typeof(EditorOwnerProcess).GetMethod("CodexArguments",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
  Check(codexArgs!=null,"CS009 missing local Codex arguments builder");
  string local=Path.Combine(Path.GetTempPath(),"codex-args-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(local);
  try {
   string exe=Path.Combine(local,"native codex.exe");File.WriteAllText(exe,"fixture-not-executed");
   string args=(string)codexArgs.Invoke(null,new object[]{exe,local,true});
   Check(args.Contains("--codex-executable ") && args.Contains("--codex-project "),"CS009 fields missing");
   foreach(var values in new[]{new object[]{exe,local,false},new object[]{"codex.cmd",local,true},new object[]{exe,"relative",true}}) {
    bool refused=false;try{codexArgs.Invoke(null,values);}catch(System.Reflection.TargetInvocationException){refused=true;}
    Check(refused,"CS009 unsafe local launch accepted");
   }
   Check((string)codexArgs.Invoke(null,new object[]{null,null,false})=="","CS009 default must be inert");
  } finally {Directory.Delete(local,true);}
  Console.WriteLine("PASS CS009 native local Codex arguments, no shell or default launch");
  string home=Path.Combine(Path.GetTempPath(),"candidate-selection-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(home);
  File.Copy(directHelper,Path.Combine(home,"direct_python.py"));
  try {
   foreach(bool hermes in new[]{false,true})foreach(bool codex in new[]{false,true}) {
    foreach(string variant in new[]{"exact","missing","wrong","legacy","invalid"}) {
     // Real metadata probe reused, fake owner outputs only public/test constants.
     string entry=Path.Combine(home,"editor_owner.py");
     string script="import sys,os,json,time\nfrom pathlib import Path\nargs=sys.argv[1:]\nclients=[args[i+1] for i,x in enumerate(args[:-1]) if x=='--client']\n"+
      "project=args[args.index('--project')+1]\nsys.stdin.readline()\n"+
      "doc={'kind':'unity_binding','version':2,'owner_pid':os.getpid(),'project':project,'endpoint':'wss://127.0.0.1:18081/hub/plugin','pin':'a'*64,'unity_bearer':'x'*64,'expires_at':int(time.time())+120,'clients':clients}\n";
     if(variant=="missing")script+="doc.pop('clients')\n";
     if(variant=="wrong")script+="doc['clients']=['codex'] if clients!=['codex'] else ['hermes']\n";
     if(variant=="legacy")script+="doc['version']=1\n";
     if(variant=="invalid")script+="doc['clients']=[1]\n";
     script+="print(json.dumps(doc),flush=True)\nsys.stdin.read()\n";
     File.WriteAllText(entry,script);
     bool called=false;
     using(var owner=new EditorOwnerProcess()) {
      bool ready=await owner.StartAsync(python,entry,"selection-fixture",(u,t,p)=>{called=true;return Task.FromResult(false);},()=>Task.CompletedTask,hermes,codex);
      Check(!ready,"fixture must never connect");Check(called==(variant=="exact"),"selection mismatch accepted or exact selection lost: "+variant);
     }
    }
   }
   string native=Path.Combine(home,"fixture-codex.exe");File.WriteAllText(native,"fixture-not-executed");
   foreach(string variant in new[]{"missing","false","true"}) {
    string entry=Path.Combine(home,"editor_owner.py");
    string script="import sys,os,json,time\nargs=sys.argv[1:]\nsys.stdin.readline()\n"+
      "print(json.dumps({'kind':'unity_binding','version':2,'owner_pid':os.getpid(),'project':'selection-fixture','endpoint':'wss://127.0.0.1:18081/hub/plugin','pin':'a'*64,'unity_bearer':'x'*64,'expires_at':int(time.time())+120,'clients':['codex']}),flush=True)\n"+
      "print(json.dumps({'kind':'ready'}),flush=True)\nsys.stdin.read()\n"+
      "result={'kind':'stopped','process_cleanup_complete':True,'probe_cleanup_complete':True,'probe_session_cleanup_confirmed':True}\n";
    if(variant!="missing")script+="result['codex_cleanup_complete']="+(variant=="true"?"True":"False")+"\n";
    script+="print(json.dumps(result),flush=True)\n";File.WriteAllText(entry,script);
    using(var owner=new EditorOwnerProcess()) {
     Check(await owner.StartAsync(python,entry,"selection-fixture",(u,t,p)=>Task.FromResult(true),()=>Task.CompletedTask,false,true,null,native,home),"CS010 synthetic owner failed");
     await owner.StopAsync();Check(owner.CleanupComplete==(variant=="true"),"CS010 local Codex cleanup receipt not enforced: "+variant);
    }
   }
   Console.WriteLine("PASS CS010 exact Codex cleanup receipt required; synthetic owner only");
   Console.WriteLine("PASS CS007 C# explicit flags and exact versioned selection receipt; synthetic private owner");
  } finally {Directory.Delete(home,true);Check(!Directory.Exists(home),"selection test residue");}
 }
}
