// TEST ONLY: fixed native GetPackageInfo and dispatch, Unity package APIs doubled.
using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
namespace UnityEditor.PackageManager {
 public sealed partial class PackageInfo {
  public sealed class Author {public string name;}
  public sealed class Dependency {public string name,version;}
  public string name,version,displayName,description,source,resolvedPath;public Author author;public Dependency[] dependencies;
  public static int Reads;
  public static PackageInfo[] Registered={new PackageInfo{name="com.unity.ugui",version="1.0.0",displayName="UI",description="Fixture package",source="Registry",resolvedPath="/Fixture/Library/PackageCache/com.unity.ugui",author=new Author{name="Fixture"},dependencies=new[]{new Dependency{name="com.unity.modules.ui",version="1.0.0"}}}};
  public static PackageInfo[] GetAllRegisteredPackages(){Reads++;return Registered;}
 }
}
internal static class PackageMetadataFixture {
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="package-metadata",["plan_id"]=id,["body"]=body};
 public static void Run(){
  var args=new JObject{["action"]="get_package_info",["package"]="com.unity.ugui"};int reads=0;
  JObject Native(JObject a)=>JObject.FromObject(MCPForUnity.Editor.Tools.ManagePackages.HandleCommand(a));
  var gate=new CandidateGate(()=>100,()=>"fixture-project",()=>"fixture-connection",_=>"live-project",(cmd,p)=>{reads++;var r=Native(p);return NativeReadContract.Valid(cmd,r,p)?r:new JObject{["success"]=false};});
  var manifest=new JObject{["operations"]=new JArray(new JObject{["command"]="manage_packages",["action"]="get_package_info"}),["targets"]=new JArray("ProjectMetadata"),["ttl_seconds"]=60};
  Check(!(bool)gate.Dispatch(Wire("prepare","",manifest))["success"],"package default open");
  gate.SetCapability("manage_packages","get_package_info",true);
  JObject Ready(){var r=gate.Dispatch(Wire("prepare","",manifest));Check((bool)r["success"],"package prepare "+r);Check(gate.Approve((string)r["data"]["plan_id"],(string)r["data"]["digest"]),"package approve");return (JObject)r["data"];}
  JObject Exec(JObject plan,JObject p)=>gate.Dispatch(Wire("execute",(string)plan["plan_id"],new JObject{["command"]="manage_packages",["params"]=p}));
  var plan=Ready();Check((bool)Exec(plan,args)["success"],"package read");
  foreach(var change in new[]{new JObject{["action"]="list_packages"},new JObject{["action"]="search_packages"},new JObject{["action"]="status"},new JObject{["action"]="resolve_packages"},new JObject{["action"]="add_package"},new JObject{["action"]="list_registries"},new JObject{["force"]=false},new JObject{["package"]="com.unity.ugui@1.0.0"},new JObject{["package"]="COM.unity.ugui"},new JObject{["package"]="com..ui"},new JObject{["package"]="com.unity.ui\n"},new JObject{["package"]=true}}){plan=Ready();var bad=(JObject)args.DeepClone();bad.Merge(change);int before=reads;Check(!(bool)Exec(plan,bad)["success"]&&reads==before,"unsafe package request reached handler");}
  foreach(var scope in new[]{"Scenes","Console","EditorMetadata","Assets/Fixture.mat"}){var bad=(JObject)manifest.DeepClone();bad["targets"]=new JArray(scope);Check(!(bool)gate.Dispatch(Wire("prepare","",bad))["success"],"package inherited scope");}
  plan=Ready();Check(gate.Pause((string)plan["plan_id"],(string)plan["digest"]),"pause");Check((string)Exec(plan,args)["error"]=="plan_paused","paused read");Check(gate.Resume((string)plan["plan_id"],(string)plan["digest"]),"resume");Check((bool)Exec(plan,args)["success"],"resumed read");gate.StopAll("stop");Check(!(bool)Exec(plan,args)["success"],"stopped read");
  var good=Native(args);Check((string)good["data"]["name"]=="com.unity.ugui"&&(int)good["data"]["dependency_count"]==1,"native result");Check(NativeReadContract.Valid("manage_packages",good,args),"native output rejected");
  foreach(var change in new[]{new JObject{["name"]="com.other.package"},new JObject{["dependency_count"]=2},new JObject{["unknown"]=true},new JObject{["dependencies"]=new JArray(new JObject{["name"]="com.other.package",["version"]="https://example.invalid/repo"})},new JObject{["resolved_path"]=new string('x',4097)}}){var bad=(JObject)good.DeepClone();((JObject)bad["data"]).Merge(change,new Newtonsoft.Json.Linq.JsonMergeSettings{MergeArrayHandling=MergeArrayHandling.Replace});Check(!NativeReadContract.Valid("manage_packages",bad,args),"malformed package output accepted");}
  var missing=new JObject{["action"]="get_package_info",["package"]="com.missing.package"};Check(!(bool)Native(missing)["success"],"missing package silently succeeded");
  Check(UnityEditor.PackageManager.PackageInfo.Reads>0,"native installed-package API not used");
  Console.WriteLine("PASS NS017 pinned installed-package metadata; exact operation/scope/output, no UPM request; Unity APIs doubled");
 }
}
