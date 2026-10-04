// TEST ONLY: pinned native menu reader with Unity metadata API doubles.
using System;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
namespace UnityEditor {
 [AttributeUsage(AttributeTargets.Method)] public class InitializeOnLoadMethodAttribute:Attribute{}
 [AttributeUsage(AttributeTargets.Method,AllowMultiple=true)] public sealed class MenuItem:Attribute {public string menuItem;public MenuItem(string name){menuItem=name;}}
 public static class TypeCache {public static int Calls;public static bool Fail;public static MethodInfo[] GetMethodsWithAttribute<T>(){Calls++;if(Fail)throw new Exception("fixture scan failure");return typeof(MenuMetadataFixture).GetMethods(BindingFlags.Static|BindingFlags.Public).Where(m=>m.IsDefined(typeof(T),false)).ToArray();}}
}
internal static class MenuMetadataFixture {
 static int Invocations;
 [UnityEditor.MenuItem("Tools/Z")] public static void Z(){Invocations++;}
 [UnityEditor.MenuItem("Tools/A")][UnityEditor.MenuItem("Tools/Z")] public static void A(){Invocations++;}
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="menu-metadata",["plan_id"]=id,["body"]=body};
 static JObject Native(JObject args)=>JObject.FromObject(MCPForUnity.Editor.Resources.MenuItems.GetMenuItems.HandleCommand(args));
 public static void Run(){
  var args=new JObject{["refresh"]=true,["search"]=""};int reads=0;
  var gate=new CandidateGate(()=>100,()=>"fixture-project",()=>"fixture-connection",_=>"live-editor",(cmd,p)=>{reads++;var result=Native(p);return NativeReadContract.Valid(cmd,result,p)?result:new JObject{["success"]=false};});
  var manifest=new JObject{["operations"]=new JArray(new JObject{["command"]="get_menu_items",["action"]="read"}),["targets"]=new JArray("EditorMetadata"),["ttl_seconds"]=60};
  Check(!(bool)gate.Dispatch(Wire("prepare","",manifest))["success"],"menu default enabled");
  gate.SetCapability("get_menu_items","read",true);
  JObject Ready(){var r=gate.Dispatch(Wire("prepare","",manifest));Check((bool)r["success"],"menu prepare missing: "+r);Check(gate.Approve((string)r["data"]["plan_id"],(string)r["data"]["digest"]),"approve menu");return (JObject)r["data"];}
  JObject Exec(JObject plan,JObject p)=>gate.Dispatch(Wire("execute",(string)plan["plan_id"],new JObject{["command"]="get_menu_items",["params"]=p}));
  var plan=Ready();Check((bool)Exec(plan,args)["success"],"menu read missing");
  foreach(var bad in new[]{new JObject(),new JObject{["refresh"]=false,["search"]=""},new JObject{["refresh"]=1,["search"]=""},new JObject{["refresh"]=true,["search"]="Tools"},new JObject{["refresh"]=true,["search"]="",["execute"]=true}}){plan=Ready();int before=reads;Check(!(bool)Exec(plan,bad)["success"]&&reads==before,"invalid menu params reached reader");}
  foreach(string scope in new[]{"ProjectMetadata","Scenes","Console","Assets/Fixture.mat"}){var bad=(JObject)manifest.DeepClone();bad["targets"]=new JArray(scope);Check(!(bool)gate.Dispatch(Wire("prepare","",bad))["success"],"menu scope inherited");}
  plan=Ready();Check(gate.Pause((string)plan["plan_id"],(string)plan["digest"]),"pause menu");Check((string)Exec(plan,args)["error"]=="plan_paused","menu paused read");Check(gate.Resume((string)plan["plan_id"],(string)plan["digest"]),"resume menu");Check((bool)Exec(plan,args)["success"],"menu resumed read");gate.StopAll("stop");Check(!(bool)Exec(plan,args)["success"],"stopped menu read");
  var result=Native(args);Check(JToken.DeepEquals(result["data"],new JArray("Tools/A","Tools/Z")),"native sorted distinct menu");Check(Invocations==0&&UnityEditor.TypeCache.Calls>0,"menu method invoked");
  foreach(var bad in new JToken[]{new JArray(42),new JArray("Z","A"),new JArray("A","A"),new JArray(new string('x',4097)),new JArray(Enumerable.Range(0,4097).Select(i=>i.ToString("D5")))}){var changed=(JObject)result.DeepClone();changed["data"]=bad;Check(!NativeReadContract.Valid("get_menu_items",changed,args),"malformed menu output accepted");}
  UnityEditor.TypeCache.Fail=true;var cached=Native(args);UnityEditor.TypeCache.Fail=false;Check(JToken.DeepEquals(cached["data"],result["data"]),"native cache fallback changed");
  Console.WriteLine("PASS NS016 pinned menu metadata, no execution, fixed refresh/search, scope, pause, output limits; Unity APIs doubled");
 }
}
