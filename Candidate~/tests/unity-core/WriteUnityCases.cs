using System;
using System.IO;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
using UnityEngine;
using UnityEditor;
using MCPForUnity.Editor.Tools;
static class WriteUnityCases
{
 static void Check(bool v,string s){if(!v)throw new Exception(s);}
 static JObject Manifest()=>new JObject{["source"]="Assets/source.mat",["candidate"]="Assets/candidate.mat",["operations"]=new JArray("copy","edit"),["references"]=new JArray(),["ttl_seconds"]=300};
 static int Main(){string root=Path.Combine(Path.GetTempPath(),"vragent-write-unity-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root+"/Assets");string previous=Directory.GetCurrentDirectory();try{
  Application.dataPath=root+"/Assets";Directory.SetCurrentDirectory(root);
  File.WriteAllText(root+"/Assets/source.mat","original");File.WriteAllText(root+"/Assets/source.mat.meta","source-guid");
  var backend=new UnityMaterialCandidateBackend();var m=Manifest();
  var before=backend.Capture(m,null);Check((string)before["asset:Assets/candidate.mat"]=="absent","candidate absent");
  var r=backend.Apply(m,new JObject{["action"]="copy"});Check((bool?)r["success"]==true,"copy");
  Check(File.ReadAllText(root+"/Assets/source.mat")=="original","source mutated");Check(File.Exists(root+"/Assets/candidate.mat"),"missing copy");
  Check(CommandRegistry.Calls==1,"copy did not reuse registry");
  Console.WriteLine("PASS WU001 unity_backend_native_copy");
  var edit=new JObject{["action"]="edit",["property"]="_Glossiness",["value"]=0.6};
  var point=backend.Checkpoint(m,edit);var changed=backend.Apply(m,edit);Check((bool?)changed["success"]==true,"edit failed");
  Check(AssetDatabase.Saves==1,"not narrow saved");Check(AssetDatabase.Objects["Assets/candidate.mat"].Json=="0.6","native edit not reached");
  var read=backend.Read(m);Check(read["native"] is JObject,"native readback not returned");
  Console.WriteLine("PASS WU002 native_edit_narrow_save_readback");
  File.WriteAllText("Assets/texture.png","png-v1");File.WriteAllText("Assets/texture.png.meta","tex-guid");AssetDatabase.Objects["Assets/texture.png"]=new Texture();AssetDatabase.Dependencies=new[]{"Assets/texture.png"};
  var d1=backend.Capture(m,null);File.WriteAllText("Assets/texture.png","png-v2");var d2=backend.Capture(m,null);Check(!JToken.DeepEquals(d1,d2),"unimported dependency disk invisible");
  File.WriteAllText("Assets/texture.png.meta","tex-guid-v2");var d3=backend.Capture(m,null);Check(!JToken.DeepEquals(d2,d3),"dependency meta invisible");
  AssetDatabase.Objects["Assets/texture.png"].Json="unsaved-texture";var d4=backend.Capture(m,null);Check(!JToken.DeepEquals(d3,d4),"dependency memory invisible");
  TypeCache.Unknown=true;bool denied=false;try{backend.Apply(m,edit);}catch(InvalidOperationException){denied=true;}finally{TypeCache.Unknown=false;}Check(denied,"unknown callbacks accepted");
  Console.WriteLine("PASS WU003 dependency_disk_meta_memory_callbacks");
  File.WriteAllText("Assets/test.unity","scene-original");File.WriteAllText("Assets/test.unity.meta","scene-guid");
  var renderer=new MeshRenderer();renderer.gameObject=new GameObject{Renderer=renderer};GlobalObjectId.Objects["renderer-1"]=renderer;
  m["references"]=new JArray(new JObject{["renderer"]="renderer-1",["slot"]=0});
  var refBefore=backend.Capture(m,null);var refCommand=new JObject{["action"]="reference",["renderer"]="renderer-1",["slot"]=0};
  var refPoint=backend.Checkpoint(m,refCommand);backend.Apply(m,refCommand);Check(ReferenceEquals(renderer.sharedMaterials[0],AssetDatabase.Objects["Assets/candidate.mat"]),"native reference not reached");
  Check(renderer.gameObject.scene.isDirty,"scene not marked dirty");Check(File.ReadAllText("Assets/test.unity")=="scene-original","scene saved");Check(!JToken.DeepEquals(refBefore,backend.Capture(m,null)),"reference evidence missing");
  Console.WriteLine("PASS WU004 reference_host_scene_unsaved");
  backend.Restore(m,refCommand,refPoint);Check(renderer.sharedMaterials[0]==null,"reference undo failed");Check(File.ReadAllText("Assets/test.unity")=="scene-original","undo saved scene");
  backend.Restore(m,edit,point);Check(File.ReadAllText("Assets/candidate.mat")=="original","disk checkpoint not restored");Check(AssetDatabase.Objects["Assets/candidate.mat"].Json=="fixture-memory","unsaved memory checkpoint not restored");
  Console.WriteLine("PASS WU005 material_reference_direct_restore");
  AdapterOwnedFixture.Begin("conn-A");
  var gate=MaterialCandidateSession.Gate;gate.SetCapability("copy",true);gate.SetCapability("edit",true);
  var wire=new JObject{["protocol"]=1,["kind"]="prepare",["project_id"]="project-A",["client_id"]="client-A",["connection_id"]="conn-A",["task_id"]="task-A",["plan_id"]="",["body"]=Manifest()};wire["body"]["candidate"]="Assets/candidate2.mat";
  var prepared=JObject.FromObject(AdapterOwnedFixture.Material(wire));Check((bool?)prepared["success"]==true,prepared.ToString());Check(gate.Approve((string)prepared["data"]["plan_id"],(string)prepared["data"]["digest"]),"approve");
  wire["plan_id"]=prepared["data"]["plan_id"];wire["kind"]="execute";wire["body"]=new JObject{["action"]="copy",["arguments"]=new JObject()};var copied=JObject.FromObject(AdapterOwnedFixture.Material(wire));Check((bool?)copied["success"]==true,copied.ToString());
  var window=new CandidateWindow();typeof(CandidateWindow).GetMethod("OnGUI",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic).Invoke(window,null);Check(EditorGUILayout.Labels.Exists(s=>s.Contains("候选材质修改")),"write UI absent");
  AssemblyReloadEvents.Reload();
  Check(gate.LocalPlans().Count==0,"reload_did_not_revoke");
  string recordKey="Yukino.VRChatAgent.material-tasks.v1.project-A";
  var stored=SessionState.GetString(recordKey,"");Check(stored!="","reload_task_history_missing");
  var restored=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"new-connection",new UnityMaterialCandidateBackend());
  var loader=typeof(MaterialCandidateSession).GetMethod("LoadTaskRecords",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
  Check(loader!=null,"reload_loader_missing");loader.Invoke(null,new object[]{restored});
  Check(restored.ExportTaskRecords().Count==1 && restored.LocalPlans().Count==0 && !restored.Allows("edit"),"reload_history_became_grant");
  var originalWire=(JObject)wire.DeepClone();
  AdapterOwnedFixture.Begin("conn-B");wire["kind"]="prepare";wire["plan_id"]="";wire["client_id"]="client-B";wire["connection_id"]="conn-B";
  wire["body"]=Manifest();wire["body"]["candidate"]="Assets/candidate2.mat";wire["body"]["operations"]=new JArray("edit");
  var recovery=gate.Dispatch(wire);Check((bool?)recovery["success"]==true,"ui_recovery_prepare");
  GUILayout.NextButton="核验记录并重新批准此绑定 "+(string)recovery["data"]["plan_id"];
  MaterialCandidateSession.Draw();Check((bool?)gate.LocalPlans()[0]["approved"]==true,"local_recovery_button_missing");
  Console.WriteLine("PASS WU012 explicit_local_recovery_button");wire=originalWire;
  EditorApplication.Quit();Check(gate.LocalPlans().Count==0 && SessionState.GetString(recordKey,"")=="","quit_kept_recovery_ticket");
  Console.WriteLine("PASS WU011 reload_history_no_authority_quit_clears");
  Console.WriteLine("PASS WU006 separate_wire_local_ui_lifecycle");
  AssetDatabase.Dependencies=Array.Empty<string>();var cg=new MaterialCandidateGate(()=>100,()=>"project-A",()=>"conn-A",new UnityMaterialCandidateBackend());cg.SetCapability("copy",true);cg.SetCapability("edit",true);wire["kind"]="prepare";wire["plan_id"]="";wire["body"]=Manifest();wire["body"]["candidate"]="Assets/candidate3.mat";
  var prep=cg.Dispatch(wire);Check((bool?)prep["success"]==true,prep.ToString());Check(cg.Approve((string)prep["data"]["plan_id"],(string)prep["data"]["digest"]),"approve texture plan");wire["plan_id"]=prep["data"]["plan_id"];wire["kind"]="execute";wire["body"]=new JObject{["action"]="copy",["arguments"]=new JObject()};Check((bool?)cg.Dispatch(wire)["success"]==true,"copy3");
  foreach(string t in new[]{"Assets/texA.png","Assets/texB.png","Assets/texC.png"}){File.WriteAllText(t,"texture-original");File.WriteAllText(t+".meta",t);AssetDatabase.Objects[t]=new Texture();wire["body"]=new JObject{["action"]="edit",["arguments"]=new JObject{["property"]="_MainTex",["value"]=t}};var changedTex=cg.Dispatch(wire);Check((bool?)changedTex["success"]==true,changedTex.ToString());Check(File.ReadAllText(t)=="texture-original","texture itself changed");}
  var textureManifest=(JObject)Manifest();textureManifest["candidate"]="Assets/candidate3.mat";var te1=backend.Capture(textureManifest,null);AssetDatabase.Objects["Assets/texC.png"].Json="user-unsaved-texture";var te2=backend.Capture(textureManifest,null);Check(!JToken.DeepEquals(te1,te2),"unimported texture reference memory omitted");
  Console.WriteLine("PASS WU007 repeated_existing_texture_reference");
  var protectedManifest=Manifest();protectedManifest["candidate"]="Assets/protected.mat";EditorUtility.Dirty=AssetDatabase.Asset;
  bool dirtyDenied=false;try{backend.Apply(protectedManifest,new JObject{["action"]="copy"});}catch(InvalidOperationException){dirtyDenied=true;}finally{EditorUtility.Dirty=null;}
  Check(dirtyDenied && !File.Exists("Assets/protected.mat"),"unsaved source silently copied from disk");
  Undo.postprocessModifications=()=>{};bool callbackDenied=false;try{backend.Apply(m,edit);}catch(InvalidOperationException){callbackDenied=true;}finally{Undo.postprocessModifications=null;}
  Check(callbackDenied,"unknown Undo callback permitted");
  Console.WriteLine("PASS WU008 unsaved_source_unknown_undo_callbacks");
  File.CreateSymbolicLink("Assets/dangling.mat",Path.Combine(root,"missing-target.mat"));var dangling=Manifest();dangling["candidate"]="Assets/dangling.mat";bool linkDenied=false;try{backend.Capture(dangling,null);}catch(InvalidOperationException){linkDenied=true;}Check(linkDenied,"dangling symlink accepted");
  Console.WriteLine("PASS WU009 dangling_reparse_rejected");
  wire["kind"]="prepare";wire["plan_id"]="";wire["body"]=Manifest();wire["body"]["candidate"]="Assets/candidate4.mat";TypeCache.Unknown=true;var knownDenial=cg.Dispatch(wire);TypeCache.Unknown=false;Check((string)knownDenial["error"]=="unknown_asset_callbacks","safe rejection reason hidden");
  Console.WriteLine("PASS WU010 callback_reason_is_actionable");return 0;
 }catch(Exception e){Console.WriteLine("FAIL "+e);return 1;}finally{Directory.SetCurrentDirectory(previous);Directory.Delete(root,true);}}
}
