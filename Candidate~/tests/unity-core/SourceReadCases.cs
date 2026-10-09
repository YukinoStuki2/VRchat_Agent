// Actual pinned native Script handler slice; Unity/approval remain doubles.
using System;using System.IO;using System.Reflection;using System.Text;using Newtonsoft.Json.Linq;
using UnityEngine;using UnityEditor;using Yukino.VRChatAgent;
using MCPForUnity.Editor.Tools;
internal static class SourceReadCases {
 static void Check(bool b,string message){if(!b)throw new Exception(message);}
 static JObject Wire(string kind,string id="")=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]="connection-A",["client_id"]="client-A",["task_id"]="source-task",["plan_id"]=id,["body"]=new JObject()};
 static int Main(){
  string dir=Path.Combine(Path.GetTempPath(),"candidate-source-"+Guid.NewGuid().ToString("N"));
  try{
   Directory.CreateDirectory(Path.Combine(dir,"Assets","Scripts"));Application.dataPath=Path.Combine(dir,"Assets");
   string text="// 中文\n"+new string('x',10001),path=Path.Combine(Application.dataPath,"Scripts","Read.cs");
   File.WriteAllText(path,text,new UTF8Encoding(true));File.WriteAllText(path+".meta","meta");
   AdapterOwnedFixture.Begin();var gate=CandidateSession.Gate;
   var prepare=Wire("prepare");prepare["body"]=JObject.Parse("{\"operations\":[{\"command\":\"manage_script\",\"action\":\"read\"}],\"targets\":[\"Assets/Scripts/Read.cs\"],\"ttl_seconds\":60}");
   gate.SetCapability("manage_script","read",true);
   var p=gate.Dispatch(prepare);Check((bool)p["success"],"source_prepare_failed: "+p);
   Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"source_approval_failed");
   var r=Wire("execute",(string)p["data"]["plan_id"]);r["body"]=JObject.Parse("{\"command\":\"manage_script\",\"params\":{\"action\":\"read\",\"name\":\"Read\",\"path\":\"Assets/Scripts\"}}");
   var result=gate.Dispatch(r);Check((bool)result["success"],"source_execute_failed: "+result);
   Check((string)result["data"]["contents"]==text && (bool)result["data"]["contentsEncoded"] && Encoding.UTF8.GetString(Convert.FromBase64String((string)result["data"]["encodedContents"]))==text,"native_body_or_base64_changed");
   Check(AssetDatabase.SourceReads==0,"source_read_loaded_or_serialized_unity_assets");
   Check(MCPForUnity.Editor.Helpers.McpLog.Warns==1,"native_handler_not_called");
   Console.WriteLine("PASS ST001 pinned_script_read_whole_utf8_bom_no_asset_load");
   gate.SetCapability("manage_script","get_sha",true);prepare["body"]["operations"][0]["action"]="get_sha";
   p=gate.Dispatch(prepare);Check((bool)p["success"] && gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"sha prepare");
   r["plan_id"]=p["data"]["plan_id"];r["body"]["params"]["action"]="get_sha";
   result=gate.Dispatch(r);Check((bool)result["success"],"sha execute: "+result);
   using(var sha=System.Security.Cryptography.SHA256.Create())
    Check((string)result["data"]["sha256"]==BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", "").ToLowerInvariant(),"native_sha_not_decoded_text");
   Check((int)result["data"]["lengthBytes"]==Encoding.UTF8.GetByteCount(text),"sha_length_includes_bom");
   Console.WriteLine("PASS ST002 native_sha_is_decoded_utf8_not_raw_bom_bytes");
   string shader=Path.Combine(Application.dataPath,"Scripts","Read.shader");File.WriteAllText(shader,text);File.WriteAllText(shader+".meta","meta");
   gate.SetCapability("manage_shader","read",true);prepare["body"]["operations"][0]["command"]="manage_shader";prepare["body"]["operations"][0]["action"]="read";
   prepare["body"]["targets"]=new JArray("Assets/Scripts/Read.shader");
   p=gate.Dispatch(prepare);Check((bool)p["success"] && gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"shader prepare");
   r["plan_id"]=p["data"]["plan_id"];r["body"]["command"]="manage_shader";r["body"]["params"]["action"]="read";
   result=gate.Dispatch(r);Check((bool)result["success"] && (string)result["data"]["contents"]==text,"shader execute: "+result);
   Check(AssetDatabase.SourceReads==0 && AssetDatabase.RefreshCalls==0,"shader_loaded_or_refreshed_unity_asset");
   Console.WriteLine("PASS ST003 shader_native_read_no_asset_loading_or_refresh");
   foreach(string cmd in new[]{"manage_script","manage_shader"}) {
    string ext=cmd=="manage_script"?".cs":".shader";
    prepare["body"]["operations"][0]["command"]=cmd;prepare["body"]["targets"]=new JArray("Assets/Scripts/Read"+ext);
    r["body"]["command"]=cmd;
    foreach(string json in new[]{
      "{action:'delete',name:'Read',path:'Assets/Scripts'}","{action:'create',name:'Read',path:'Assets/Scripts'}",
      "{action:'update',name:'Read',path:'Assets/Scripts'}","{action:'read',name:'Other',path:'Assets/Scripts'}",
      "{action:'read',name:'Read',path:'Assets/Scripts/..'}","{action:'read',name:'Read',path:'Assets/Scripts',contents:null}",
      "{action:'read',name:'Read',path:'Assets/Scripts',contentsEncoded:false}","{action:'read',name:'Read',path:'Assets/Scripts',unknown:1}"}) {
      p=gate.Dispatch(prepare);Check((bool)p["success"] && gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"negative baseline");
      r["plan_id"]=p["data"]["plan_id"];r["body"]["params"]=JObject.Parse("{action:'read',name:'Read',path:'Assets/Scripts'}");
      Check((bool)gate.Dispatch(r)["success"],"baseline_read_failed");int calls=MCPForUnity.Editor.Helpers.McpLog.Warns;
      r["body"]["params"]=JObject.Parse(json);Check(!(bool)gate.Dispatch(r)["success"],"negative_dispatched: "+json);
      Check(calls==MCPForUnity.Editor.Helpers.McpLog.Warns && AssetDatabase.RefreshCalls==0,"negative_native_side_effect");
    }
   }
   Console.WriteLine("PASS ST004 invalid_source_args_scope_and_writes_blocked_before_native");
   prepare["body"]["operations"][0]["command"]="manage_script";prepare["body"]["targets"]=new JArray("Assets/Scripts/Read.cs");
   r["body"]["command"]="manage_script";r["body"]["params"]=JObject.Parse("{action:'read',name:'Read',path:'Assets/Scripts'}");
   foreach(string change in new[]{"source","meta"}) {
    p=gate.Dispatch(prepare);Check((bool)p["success"] && gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"evidence baseline");r["plan_id"]=p["data"]["plan_id"];
    Check((bool)gate.Dispatch(r)["success"],"evidence baseline read");int calls=MCPForUnity.Editor.Helpers.McpLog.Warns;
    File.AppendAllText(change=="source"?path:path+".meta","changed");
    Check(!(bool)gate.Dispatch(r)["success"] && calls==MCPForUnity.Editor.Helpers.McpLog.Warns,"changed_source_was_read");
    File.WriteAllText(path,text,new UTF8Encoding(true));File.WriteAllText(path+".meta","meta");
    Check(!(bool)gate.Dispatch(r)["success"],"old_grant_revived");
   }
   Console.WriteLine("PASS ST005 source_or_meta_change_revokes_and_restore_does_not_reauthorize");
   File.WriteAllText(path,new string('a',131073));Check(!(bool)gate.Dispatch(prepare)["success"],"raw_source_budget_not_enforced");
   File.WriteAllText(path,text,new UTF8Encoding(true));p=gate.Dispatch(prepare);Check((bool)p["success"],"budget baseline");
   var args=JObject.Parse("{action:'read',name:'Read',path:'Assets/Scripts'}");var raw=JObject.FromObject(ManageScript.HandleCommand(args));
   Check(NativeReadContract.Valid("manage_script",raw,args),"native contract baseline");
   foreach(string field in new[]{"path","uri","contents","contentsEncoded","encodedContents","unexpected"}) {
    var broken=(JObject)raw.DeepClone();broken["data"][field]=field=="contentsEncoded"?(JToken)false:field=="contents"?new string('a',131073):"bad";
    Check(!NativeReadContract.Valid("manage_script",broken,args),"output_field_accepted: "+field);
   }
   Console.WriteLine("PASS ST006 source_raw_size_and_native_response_contract_enforced");
   gate.SetCapability("manage_script","get_sha",false);var window=new CandidateWindow();
   var flags=BindingFlags.Instance|BindingFlags.NonPublic;
   typeof(CandidateWindow).GetField("catalog",flags).SetValue(window,JArray.Parse("[{name:'get_sha',unity_target:'manage_script',group:'core',name_zh:'脚本内容哈希',has_action_parameter:false,declared_actions:[],implemented_candidate_read_actions:['get_sha']} ]"));
   typeof(CandidateWindow).GetField("catalogTool",flags).SetValue(window,"get_sha");
   EditorGUILayout.NextToggle="脚本内容哈希  manage_script/get_sha";
   typeof(CandidateWindow).GetMethod("DrawCatalog",flags).Invoke(window,null);
   Check(gate.Allows("manage_script","get_sha"),"alias_ui_did_not_enable_exact_native_sha");
   var capacity=new CandidateGate(()=>1,()=>"project-A",()=>"connection-A",target=>"fixture-evidence",(cmd,a)=>throw new Exception("capacity test must not execute"));
   var operations=JArray.Parse("[{\"command\":\"find_gameobjects\",\"action\":\"find\"},{\"command\":\"manage_script\",\"action\":\"get_sha\"},{\"command\":\"manage_animation\",\"action\":\"controller_get_info\"},{\"command\":\"manage_animation\",\"action\":\"animator_get_info\"},{\"command\":\"manage_animation\",\"action\":\"animator_get_parameter\"},{\"command\":\"manage_material\",\"action\":\"get_material_info\"},{\"command\":\"manage_packages\",\"action\":\"get_package_info\"},{\"command\":\"manage_scene\",\"action\":\"get_active\"},{\"command\":\"manage_scene\",\"action\":\"get_build_settings\"},{\"command\":\"manage_scene\",\"action\":\"get_loaded_scenes\"},{\"command\":\"manage_scene\",\"action\":\"get_hierarchy\"},{\"command\":\"manage_scene\",\"action\":\"validate\"},{\"command\":\"manage_script\",\"action\":\"read\"},{\"command\":\"manage_shader\",\"action\":\"read\"},{\"command\":\"read_console\",\"action\":\"get\"},{\"command\":\"get_gameobject\",\"action\":\"read\"},{\"command\":\"get_gameobject_components\",\"action\":\"read\"},{\"command\":\"get_project_info\",\"action\":\"read\"},{\"command\":\"get_tags\",\"action\":\"read\"},{\"command\":\"get_layers\",\"action\":\"read\"},{\"command\":\"get_selection\",\"action\":\"read\"},{\"command\":\"get_windows\",\"action\":\"read\"},{\"command\":\"get_active_tool\",\"action\":\"read\"},{\"command\":\"get_prefab_stage\",\"action\":\"read\"},{\"command\":\"get_menu_items\",\"action\":\"read\"}]");
   operations.Add(new JObject{["command"]="manage_animation",["action"]="clip_get_info"});
   foreach(string action in new[]{"get_type","get_member","search"})operations.Add(new JObject{["command"]="unity_reflect",["action"]=action});
   foreach(JObject op in operations)capacity.SetCapability((string)op["command"],(string)op["action"],true);
   var all=Wire("prepare");all["body"]=new JObject{["operations"]=operations,["targets"]=new JArray("Scenes","Console","EditorMetadata","ProjectMetadata","ApiMetadata","Assets/Scripts/Read.cs","Assets/Scripts/Read.shader","Assets/Test.mat","Assets/Test.controller"),["ttl_seconds"]=60};
   Check((bool)capacity.Dispatch(all)["success"],"full_29_operation_manifest_rejected");
   operations.Add(operations[0].DeepClone());Check(!(bool)capacity.Dispatch(all)["success"],"30_operations_accepted");
   Console.WriteLine("PASS ST007 sha_alias_ui_and_complete_operation_manifest");
   string clipPath="Assets/Scripts/Walk.anim",fullClip=Path.Combine(dir,clipPath);
   File.WriteAllText(fullClip,"clip-native-fixture");File.WriteAllText(fullClip+".meta","clip-meta");
   var clip=new AnimationClip{name="Walk",length=1.5f,frameRate=60,Persistent=true};AssetDatabase.Asset=clip;AssetDatabase.ClipPath=clipPath;Resources.Items=new UnityEngine.Object[]{clip};
   AnimationUtility.Bindings=new[]{new EditorCurveBinding{path="Body",propertyName="m_LocalPosition.x",type=typeof(Transform)}};
   AnimationUtility.Events=new[]{new AnimationEvent{time=0.5f,functionName="DoNotInvoke",stringParameter="data-only",floatParameter=2,intParameter=3}};
   gate.SetCapability("manage_animation","clip_get_info",true);
   prepare["body"]=new JObject{["operations"]=new JArray(new JObject{["command"]="manage_animation",["action"]="clip_get_info"}),["targets"]=new JArray(clipPath),["ttl_seconds"]=60};
   p=gate.Dispatch(prepare);Check((bool)p["success"],"clip_prepare_failed: "+p);
   Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"clip_approve");
   r["plan_id"]=p["data"]["plan_id"];r["body"]=new JObject{["command"]="manage_animation",["params"]=new JObject{["action"]="clip_get_info",["clipPath"]=clipPath}};
   result=gate.Dispatch(r);Check((bool)result["success"],"clip_native: "+result);
   Check((int)result["data"]["curveCount"]==1 && (int)result["data"]["curves"][0]["keyCount"]==2 && (string)result["data"]["events"][0]["functionName"]=="DoNotInvoke" && (double)result["data"]["length"]==1.5,"clip_contract");
   Check(AssetDatabase.RefreshCalls==0,"clip_refreshed");
   Console.WriteLine("PASS ST008 pinned_loaded_clip_native_metadata_without_event_execution");
   JObject ReadyClip(){var q=gate.Dispatch(prepare);Check((bool)q["success"] && gate.Approve((string)q["data"]["plan_id"],(string)q["data"]["digest"]),"clip_ready");r["plan_id"]=q["data"]["plan_id"];return q;}
   var goodArgs=(JObject)r["body"]["params"].DeepClone();int clipCalls=MCPForUnity.Editor.Tools.Animation.ManageAnimation.Calls;
   foreach(var bad in new[]{new JObject{["action"]="clip_add_event",["clipPath"]=clipPath},new JObject{["action"]="clip_get_info",["clipPath"]="Assets/Scripts/Other.anim"},new JObject{["action"]="clip_get_info",["clipPath"]=clipPath,["properties"]=new JObject()},new JObject{["action"]="clip_get_info",["clipPath"]="Assets/Scripts/../Walk.anim"}}){
    ReadyClip();r["body"]["params"]=bad;Check(!(bool)gate.Dispatch(r)["success"] && MCPForUnity.Editor.Tools.Animation.ManageAnimation.Calls==clipCalls,"clip_bad_reached_reader");r["body"]["params"]=goodArgs.DeepClone();
   }
   ReadyClip();Resources.Items=Array.Empty<UnityEngine.Object>();Check(!(bool)gate.Dispatch(r)["success"],"unloaded_clip_accepted");
   Check(!(bool)gate.Dispatch(prepare)["success"],"unloaded_clip_plan");Resources.Items=new UnityEngine.Object[]{clip};Check(!(bool)gate.Dispatch(r)["success"],"clip_reloaded_reauthorized");
   ReadyClip();clip.Json="unsaved clip modified";Check(!(bool)gate.Dispatch(r)["success"],"clip_memory_change");
   clip.Json="fixture-memory";Check(!(bool)gate.Dispatch(r)["success"],"memory_restore_reauthorized");
   ReadyClip();File.AppendAllText(fullClip+".meta","changed");Check(!(bool)gate.Dispatch(r)["success"],"clip_meta_change");File.WriteAllText(fullClip+".meta","clip-meta");
   var savedBindings=AnimationUtility.Bindings;AnimationUtility.Bindings=new EditorCurveBinding[513];Check(!(bool)gate.Dispatch(prepare)["success"],"clip_curves_over_budget");AnimationUtility.Bindings=savedBindings;
   var savedEvents=AnimationUtility.Events;AnimationUtility.Events=new AnimationEvent[1025];Check(!(bool)gate.Dispatch(prepare)["success"],"clip_events_over_budget");AnimationUtility.Events=savedEvents;
   File.WriteAllText(fullClip,new string('x',131073));Check(!(bool)gate.Dispatch(prepare)["success"],"clip_raw_over_budget");File.WriteAllText(fullClip,"clip-native-fixture");
   Check(MCPForUnity.Editor.Tools.Animation.ManageAnimation.Calls==clipCalls,"clip_denial_loaded_native");
   var validClip=(JObject)result.DeepClone();
   foreach(string field in new[]{"path","curveCount","eventCount","length"}){
    var bad=(JObject)validClip.DeepClone();bad["data"][field]=field=="path"?new JValue("Assets/Other.anim"):field=="length"?new JValue(double.NaN):new JValue(12);
    Check(!NativeReadContract.Valid("manage_animation",bad,goodArgs),"clip_bad_output_"+field);
   }
   Check(!NativeReadContract.Valid("manage_animation",validClip,new JObject{["action"]="clip_get_info",["clipPath"]=clipPath,["extra"]=true}),"clip_unknown_output_args");
   Console.WriteLine("PASS ST009 clip_scope_mutation_budget_change_and_response_denials");

   typeof(CandidateWindow).GetField("catalog",flags).SetValue(window,JArray.Parse("[{name:'unity_reflect',group:'docs',name_zh:'类型与成员反射查询',declared_actions:['get_type','get_member','search']}]"));
   typeof(CandidateWindow).GetField("catalogTool",flags).SetValue(window,"unity_reflect");
   EditorGUILayout.Labels.Clear();
   typeof(CandidateWindow).GetMethod("DrawCatalog",flags).Invoke(window,null);
   Check(EditorGUILayout.Labels.Exists(s=>s.Contains("ApiMetadata") && s.Contains("13") && s.Contains("不是全工程API")),"reflection_UI_scope_disclosure_missing");
   // Actual native additive reader through the installed CandidateSession gate.
   gate.SetCapability("unity_reflect","get_type",true);
   prepare["body"]=JObject.Parse("{operations:[{command:'unity_reflect',action:'get_type'}],targets:['ApiMetadata'],ttl_seconds:60}");
   p=gate.Dispatch(prepare);Check((bool)p["success"],"scoped metadata prepare: "+p);
   Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"scoped metadata approval");
   r["plan_id"]=p["data"]["plan_id"];r["body"]=JObject.Parse("{command:'unity_reflect',params:{action:'get_type',class_name:'UnityEngine.Transform'}}");
   int registry=CommandRegistry.Calls,assetReads=AssetDatabase.SourceReads;
   result=gate.Dispatch(r);Check((bool)result["success"],"scoped metadata dispatch: "+result);
   Check((string)result["data"]["full_name"]=="UnityEngine.Transform" && (bool?)result["data"]["candidate_scope"]?["all_loaded_types"]==false &&
     (bool?)result["data"]["candidate_scope"]?["extension_methods_included"]==false,"scope or native metadata missing");
   Check(CommandRegistry.Calls==registry && AssetDatabase.SourceReads==assetReads && Transform.MetadataGetterCalls==0,"metadata used global registry/assets/getter");
   var native=JObject.FromObject(CandidateScopedUnityReflect.HandleCommand((JObject)r["body"]["params"]));
   Check(NativeReadContract.Valid("unity_reflect",native,(JObject)r["body"]["params"]),"native reflection shape rejected");
   foreach(string field in new[]{"full_name","members","found","unexpected"}){
    var bad=(JObject)native.DeepClone();bad["data"][field]=field=="found"?(JToken)false:new JValue("bad");
    Check(!NativeReadContract.Valid("unity_reflect",bad,(JObject)r["body"]["params"]),"invalid reflection output: "+field);
   }
   Console.WriteLine("PASS ST010 scoped_native_metadata_session_contract_no_global_dispatch");
   foreach(string action in new[]{"get_member","search"})gate.SetCapability("unity_reflect",action,true);
   prepare["body"]=JObject.Parse("{operations:[{command:'unity_reflect',action:'get_type'},{command:'unity_reflect',action:'get_member'},{command:'unity_reflect',action:'search'}],targets:['ApiMetadata'],ttl_seconds:60}");
   p=gate.Dispatch(prepare);Check((bool)p["success"] && gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"member/search approve");r["plan_id"]=p["data"]["plan_id"];
   foreach(var reflectionArgs in new[]{
     JObject.Parse("{action:'get_type',class_name:'System.IO.File'}"),
     JObject.Parse("{action:'get_member',class_name:'Transform',member_name:'MetadataOnly'}"),
     JObject.Parse("{action:'get_member',class_name:'UnityEngine.Transform',member_name:'Missing'}"),
     JObject.Parse("{action:'search',query:'Transform',scope:'unity'}"),
   }){
    r["body"]=new JObject{["command"]="unity_reflect",["params"]=reflectionArgs};result=gate.Dispatch(r);
    Check((bool)result["success"] && result["data"]["candidate_scope"]!=null,"member/search shape: "+result);
    if((string)reflectionArgs["class_name"]=="System.IO.File" || (string)reflectionArgs["member_name"]=="Missing")Check((bool?)result["data"]["found"]==false,"out-of-set lookup found");
   }
   Check(Transform.MetadataGetterCalls==0 && AssetDatabase.SourceReads==assetReads && CommandRegistry.Calls==registry,"member/search side effects");
   gate.StopAll("fixture-stop");Check(!(bool)gate.Dispatch(r)["success"],"metadata survived revoke");
   Console.WriteLine("PASS ST011 scoped_members_search_unknown_type_and_stop");
   return 0;
  }catch(Exception e){Console.WriteLine("FAIL "+e);return 1;}
  finally{CandidateSession.StopOwnedAsync().GetAwaiter().GetResult();if(Directory.Exists(dir))Directory.Delete(dir,true);}
 }
}
namespace MCPForUnity.Editor.Helpers {public static class McpLog {public static int Warns;public static void Warn(string s){Warns++;}}}
