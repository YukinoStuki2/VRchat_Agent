// Synthetic files for locator checks only; never execute these byte fixtures.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class PortableSelectionCases
{
 internal static void Run()
 {
  var resolve=typeof(EditorOwnerProcess).GetMethod("ResolvePortablePython",BindingFlags.Static|BindingFlags.NonPublic);
  if(resolve==null)throw new Exception("PS001 portable selector missing");
  string work=Path.Combine(Path.GetTempPath(),"candidate-selection-"+Guid.NewGuid().ToString("N"));
  string package=Path.Combine(work,"original"),runtime=Path.Combine(package,"Runtime~");
  bool windows=Environment.OSVersion.Platform==PlatformID.Win32NT;
  string executable=windows?"python/python.exe":"python/bin/python3.11";
  var manifest=new JObject{["schema"]=1,["platform"]=windows?"windows-x86_64":"linux-x86_64",["python_version"]="3.11.16"};
  var files=new JObject();manifest["files"]=files;
  try {
   foreach(string name in new[]{executable,"launcher/editor_owner.py","launcher/direct_python.py"}) {
    string path=Path.Combine(runtime,name);Directory.CreateDirectory(Path.GetDirectoryName(path));File.WriteAllBytes(path,Encoding.UTF8.GetBytes(name));
    using(var hash=SHA256.Create())files[name]=BitConverter.ToString(hash.ComputeHash(File.ReadAllBytes(path))).Replace("-","").ToLowerInvariant();
   }
   File.WriteAllText(Path.Combine(runtime,"portable-launch.json"),manifest.ToString());
   string moved=Path.Combine(work,"relocated 中文 space");Directory.Move(package,moved);
   string actual=(string)resolve.Invoke(null,new object[]{moved});
   if(actual!=Path.Combine(moved,"Runtime~",executable))throw new Exception("PS001 wrong interpreter");
   Console.WriteLine("PASS PS001 fixed-path-relocation");
   string descriptor=Path.Combine(moved,"Runtime~","portable-launch.json");
   void Denied(string id, Action mutate) {
    string saved=File.ReadAllText(descriptor);mutate();bool denied=false;
    try {resolve.Invoke(null,new object[]{moved});}
    catch(TargetInvocationException){denied=true;}
    finally{File.WriteAllText(descriptor,saved);}
    if(!denied)throw new Exception(id+" invalid descriptor accepted");
   }
   Denied("PS002 missing",()=>File.Delete(descriptor));
   foreach(string field in new[]{"platform","python_version","schema"})
    Denied("PS002 "+field,()=>{var bad=(JObject)manifest.DeepClone();bad[field]="invalid";File.WriteAllText(descriptor,bad.ToString());});
   Denied("PS002 duplicate",()=>File.WriteAllText(descriptor,"{\"schema\":1,"+manifest.ToString().Substring(1)));
   Denied("PS002 oversize",()=>File.WriteAllText(descriptor,new string(' ',9000)+manifest.ToString()));
   Denied("PS002 extra",()=>{var bad=(JObject)manifest.DeepClone();bad["executable"]="/untrusted/python";File.WriteAllText(descriptor,bad.ToString());});
   Denied("PS002 extra-file",()=>{var bad=(JObject)manifest.DeepClone();bad["files"]["../outside"]="a";File.WriteAllText(descriptor,bad.ToString());});
   Console.WriteLine("PASS PS002 strict-descriptor-rejection");
   foreach(string name in files.Properties().Select(p=>p.Name)) {
    string path=Path.Combine(moved,"Runtime~",name);byte[] saved=File.ReadAllBytes(path);
    try{Denied("PS003 changed-bytes",()=>File.WriteAllBytes(path,new byte[]{0}));}
    finally{File.WriteAllBytes(path,saved);}
   }
   Console.WriteLine("PASS PS003 all-three-entry-hashes");
   string launcher=Path.Combine(moved,"Runtime~","launcher"), original=launcher+"-original";
   Directory.Move(launcher,original);
   try {
    if(windows) {
     var info=new System.Diagnostics.ProcessStartInfo("cmd.exe","/d /c mklink /J \""+launcher+"\" \""+original+"\"") {UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
     using(var junction=System.Diagnostics.Process.Start(info)) {
      if(!junction.WaitForExit(5000) || junction.ExitCode!=0)throw new Exception("PS004 junction fixture failed");
     }
    } else Directory.CreateSymbolicLink(launcher,original);
    Denied("PS004 link",()=>{});
   } finally {if(Directory.Exists(launcher))Directory.Delete(launcher);Directory.Move(original,launcher);}
   if((string)resolve.Invoke(null,new object[]{moved})!=actual)throw new Exception("PS004 fixture restore failed");
   Console.WriteLine("PASS PS004 ancestor-link-or-junction-refused");


  } finally {if(Directory.Exists(work))Directory.Delete(work,true);}
 }
}
