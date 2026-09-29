using System;
using System.IO;
using System.Reflection;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using UnityEngine;
using UnityEditor;
using MCPForUnity.Editor.Tools;
static class WriteNativeCases
{
 static void Check(bool v,string s){if(!v)throw new Exception(s);}
 static object Invoke(Type type,string name,params object[] args)=>type.GetMethod(name,BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,args);
 static int Main(){var root=Path.Combine(Path.GetTempPath(),"vragent-native-write-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root+"/Assets");var previous=Directory.GetCurrentDirectory();try{
  Application.dataPath=root+"/Assets";Directory.SetCurrentDirectory(root);File.WriteAllText("Assets/source.mat","source");File.WriteAllText("Assets/source.mat.meta","source-guid");
  CommandRegistry.RawOverride=(command,p)=>command=="manage_asset"?Invoke(typeof(WritePinnedAsset),"DuplicateAsset",(string)p["path"],(string)p["destination"]):Invoke(typeof(WritePinnedMaterial), (string)p["action"]=="set_material_shader_property"?"SetMaterialShaderProperty":(string)p["action"]=="assign_material_to_renderer"?"AssignMaterialToRenderer":"GetMaterialInfo",p);
  var backend=new UnityMaterialCandidateBackend();var m=new JObject{["source"]="Assets/source.mat",["candidate"]="Assets/candidate.mat",["operations"]=new JArray("copy","edit"),["references"]=new JArray(),["ttl_seconds"]=300};
  Check((bool?)backend.Apply(m,new JObject{["action"]="copy"})["success"]==true,"native duplicate failed");Check(AssetDatabase.Copies==1 && AssetDatabase.Refreshes==0,"copy broad refresh");
  Check((bool?)backend.Apply(m,new JObject{["action"]="edit",["property"]="_Float",["value"]=0.7})["success"]==true,"native setter failed");Check(((Material)AssetDatabase.Objects["Assets/candidate.mat"]).Json=="0.7","actual native setter not exercised");Check(AssetDatabase.Saves==1,"narrow save");Check(File.ReadAllText("Assets/source.mat")=="source","original modified");
  Console.WriteLine("PASS WN001 pinned_native_copy_edit_method_bodies");return 0;
 }catch(Exception e){Console.WriteLine("FAIL "+e);return 1;}finally{CommandRegistry.RawOverride=null;Directory.SetCurrentDirectory(previous);Directory.Delete(root,true);}}
}
