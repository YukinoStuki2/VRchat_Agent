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
   Console.WriteLine("PASS CS007 C# explicit flags and exact versioned selection receipt; synthetic private owner");
  } finally {Directory.Delete(home,true);Check(!Directory.Exists(home),"selection test residue");}
 }
}
