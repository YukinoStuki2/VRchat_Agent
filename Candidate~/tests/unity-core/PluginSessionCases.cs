// Actual Session/UI/trust policy; Unity and owned transport are doubles.
using System;
using System.IO;
using System.Reflection;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Yukino.VRChatAgent;
internal static class PluginSessionCases
{
 static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
 static int Main(){string dir=Path.Combine(Path.GetTempPath(),"vragent-plugin-session-"+Guid.NewGuid().ToString("N"));try{
  Directory.CreateDirectory(Path.Combine(dir,"Assets"));Directory.CreateDirectory(Path.Combine(dir,"Packages"));Application.dataPath=Path.Combine(dir,"Assets");
  File.WriteAllText(Path.Combine(dir,"Packages/manifest.json"),"{\"dependencies\":{}}");File.WriteAllText(Path.Combine(dir,"Packages/packages-lock.json"),"{\"dependencies\":{}}");
  AdapterOwnedFixture.Begin();
  var field=typeof(CandidateSession).GetField("Plugins",BindingFlags.Static|BindingFlags.NonPublic);Check(field!=null,"session_plugin_trust_not_wired");
  var trust=(ProjectPluginTrust)field.GetValue(null);var gate=CandidateSession.Gate;
  var window=new CandidateWindow();var draw=typeof(CandidateWindow).GetMethod("OnGUI",BindingFlags.Instance|BindingFlags.NonPublic);
  draw.Invoke(window,null);Check(!trust.Confirmed&&!gate.AssetCallbacksAllowed,"cold UI granted trust");
  GUILayout.NextButton="核对本轮工程插件信任";draw.Invoke(window,null);Check(!trust.Confirmed,"stage auto-confirmed");
  Check(EditorGUILayout.Labels.Exists(x=>x.Contains("不是插件沙箱"))&&EditorGUILayout.Labels.Exists(x=>x.Contains("project-A")),"trust scope/risk not shown");
  GUILayout.NextButton="确认信任此工程插件（不批准任务）";draw.Invoke(window,null);
  Check(trust.Confirmed&&!gate.AssetCallbacksAllowed&&gate.LocalPlans().Count==0,"trust button missing or granted capabilities/task");
  CandidateSession.StopOwnedAsync().GetAwaiter().GetResult();Check(!trust.Confirmed,"stop retained trust");
  AdapterOwnedFixture.Begin();Check(!trust.Confirmed,"reconnect restored trust");
  Console.WriteLine("PASS PS001 actual_session_ui_explicit_local_consent_and_stop_no_restoration");
  File.WriteAllText(Path.Combine(dir,"Assets/a.asset"),"fixture");
  JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]="connection-A",["client_id"]="client",["task_id"]="task",["plan_id"]=id,["body"]=body};
  Func<JObject,JObject> call=r=>JObject.FromObject(AdapterOwnedFixture.Call(r));
  var body=JObject.Parse("{operations:[{command:'manage_asset',action:'get_info'}],targets:['AssetReads/Assets/a.asset'],ttl_seconds:60,effects:[{kind:'asset_load_callbacks',version:1}]}");
  gate.SetCapability("manage_asset","get_info",true);gate.SetAssetCallbacks(true);
  Check(!(bool)call(Wire("prepare","",body))["success"],"unconfirmed project trust accepted");
  GUILayout.NextButton="核对本轮工程插件信任";draw.Invoke(window,null);GUILayout.NextButton="确认信任此工程插件（不批准任务）";draw.Invoke(window,null);
  Check(trust.Confirmed,"second explicit local confirmation failed");
  AssetDatabase.ClipPath="Assets/a.asset";
  gate.SetCapability("manage_asset","get_info",true);gate.SetAssetCallbacks(true);
  var plan=call(Wire("prepare","",body));Check((bool)plan["success"],"asset_session_prepare_not_wired: "+plan);
  var execution=Wire("execute",(string)plan["data"]["plan_id"],JObject.Parse("{command:'manage_asset',params:{action:'get_info',path:'Assets/a.asset',generatePreview:false}}"));
  Check(!(bool)call(execution)["success"],"trust bypassed task approval");
  plan=call(Wire("prepare","",body));Check(gate.Approve((string)plan["data"]["plan_id"],(string)plan["data"]["digest"]),"effect plan approval");execution["plan_id"]=plan["data"]["plan_id"];
  Check((bool)call(execution)["success"],"asset_session_read_not_wired");
  trust.Revoke();Check(!(bool)call(execution)["success"],"revoked trust retained executable plan");
  Console.WriteLine("PASS PS002 actual_session_asset_route_requires_local_trust_effect_capability_and_task_approval");
  AssetDatabase.ClipPath="Assets/a.prefab";AssetDatabase.Asset=new GameObject{name="Root"};
  foreach(string action in new[]{"get_info","get_hierarchy"}) {
   gate.SetCapability("manage_prefabs",action,true);gate.SetPrefabContentsCallbacks(true);
   GUILayout.NextButton="核对本轮工程插件信任";draw.Invoke(window,null);GUILayout.NextButton="确认信任此工程插件（不批准任务）";draw.Invoke(window,null);
   var prefabBody=JObject.FromObject(new{operations=new[]{new{command="manage_prefabs",action}},targets=new[]{"PrefabReads/Assets/a.prefab"},ttl_seconds=60,effects=action=="get_info"?new[]{new{kind="asset_load_callbacks",version=1}}:new[]{new{kind="asset_load_callbacks",version=1},new{kind="prefab_contents_callbacks",version=1}}});
   var prepared=call(Wire("prepare","",prefabBody));Check((bool)prepared["success"],"prefab_session_prepare_not_wired: "+prepared);
   Check(gate.Approve((string)prepared["data"]["plan_id"],(string)prepared["data"]["digest"]),"prefab approval failed");
   var read=call(Wire("execute",(string)prepared["data"]["plan_id"],JObject.FromObject(new{command="manage_prefabs",@params=new{action,prefabPath="Assets/a.prefab"}})));
   Check((bool)read["success"]&&(bool)read["data"]["candidate_effects"]["cleanup_confirmed"],"prefab_session_read_not_wired: "+read);
  }
  Check(PrefabUtility.Loads==1&&PrefabUtility.Unloads==1,"prefab instance ownership or cleanup mismatch");
  Console.WriteLine("PASS PS003 actual_session_shipped_prefab_info_and_owned_hierarchy");
  gate.SetCapability("get_tests","discover",true);gate.SetTestDiscoveryCallbacks(true);
  GUILayout.NextButton="核对本轮工程插件信任";draw.Invoke(window,null);GUILayout.NextButton="确认信任此工程插件（不批准任务）";draw.Invoke(window,null);
  var discoveryBody=JObject.Parse("{operations:[{command:'get_tests',action:'discover'}],targets:['TestDiscovery/EditMode'],ttl_seconds:60,effects:[{kind:'test_discovery_callbacks',version:1}]}");
  var discoveryPlan=call(Wire("prepare","",discoveryBody));Check((bool)discoveryPlan["success"],"discovery_session_prepare_not_wired: "+discoveryPlan);
  Check(gate.Approve((string)discoveryPlan["data"]["plan_id"],(string)discoveryPlan["data"]["digest"]),"discovery task approval failed");
  object pending=AdapterOwnedFixture.Call(Wire("execute",(string)discoveryPlan["data"]["plan_id"],JObject.Parse("{command:'get_tests',params:{mode:'EditMode'}}")));
  Check(pending is System.Threading.Tasks.Task<object>,"discovery_session_not_async");
  var job=(System.Threading.Tasks.Task<object>)pending;
  var deadline=System.Diagnostics.Stopwatch.StartNew();while(!job.IsCompleted&&deadline.Elapsed.TotalSeconds<3){EditorApplication.Tick();System.Threading.Thread.Sleep(1);}
  Check(job.IsCompleted,"discovery_session_not_completed");
  var discovered=JObject.FromObject(job.GetAwaiter().GetResult());Check((bool)discovered["success"]&&((JArray)discovered["data"]["tests"]).Count==1,"discovery_session_result_incomplete: "+discovered);
  Console.WriteLine("PASS PS004 actual_session_async_shipped_live_discovery");
  Probe.Hang=true;int buildsBefore=Probe.Builds,disposedBefore=Probe.BuilderDisposed,subscriptionsBefore=EditorApplication.Updates;
  discoveryPlan=call(Wire("prepare","",discoveryBody));Check((bool)discoveryPlan["success"],"revocation fixture prepare");
  Check(gate.Approve((string)discoveryPlan["data"]["plan_id"],(string)discoveryPlan["data"]["digest"]),"revocation fixture approval");
  job=(System.Threading.Tasks.Task<object>)AdapterOwnedFixture.Call(Wire("execute",(string)discoveryPlan["data"]["plan_id"],JObject.Parse("{command:'get_tests',params:{mode:'EditMode'}}")));
  for(int i=0;i<4;i++)EditorApplication.Tick();Check(Probe.Builds==buildsBefore+1&&!job.IsCompleted,"fixture did not enter asynchronous builder");
  trust.Revoke();deadline.Restart();while(!job.IsCompleted&&deadline.Elapsed.TotalSeconds<3){EditorApplication.Tick();System.Threading.Thread.Sleep(1);}
  Check(job.IsCompleted,"revoked session discovery left pending task");var revoked=JObject.FromObject(job.GetAwaiter().GetResult());
  Check(!(bool)revoked["success"]&&(bool)revoked["data"]["effects_may_have_occurred"]&&(bool)revoked["data"]["cleanup_confirmed"]&&!trust.Confirmed,"revoked discovery reported success or hid effects");
  Check(Probe.BuilderDisposed==disposedBefore+1&&EditorApplication.Updates==subscriptionsBefore,"revoked discovery retained iterator or subscriptions");Probe.Hang=false;
  Console.WriteLine("PASS PS008 actual_session_revocation_drains_owned_discovery_and_discards_results");
  string consent=trust.StageLocal();Check(trust.ConfirmLocal(consent),"explicit consent failed after clean revocation");
  gate.StopAll("fixture");gate.SetAssetCallbacks(false);gate.SetPrefabContentsCallbacks(false);gate.SetTestDiscoveryCallbacks(false);
  foreach(string label in new[]{"允许资产加载回调（独立副作用）","允许Prefab临时内容回调（独立副作用）","允许实时测试发现回调（独立副作用）"}){EditorGUILayout.NextToggle=label;draw.Invoke(window,null);}
  Check(gate.AssetCallbacksAllowed&&gate.PrefabContentsCallbacksAllowed&&gate.TestDiscoveryCallbacksAllowed&&gate.LocalPlans().Count==0,"effect toggles missing or automatically approved tasks");
  Console.WriteLine("PASS PS005 separate_local_effect_toggles_do_not_approve_tasks");
  string manifest=Path.Combine(dir,"Packages/manifest.json"),original=File.ReadAllText(manifest);
  File.WriteAllText(manifest,"{\"changed\":true}");EditorApplication.Tick();Check(!trust.Confirmed,"package inventory change retained trust");File.WriteAllText(manifest,original);EditorApplication.Tick();Check(!trust.Confirmed,"package restoration resurrected trust");
  Console.WriteLine("PASS PS006 observed_package_change_revokes_without_auto_restoration");
  string localToken=trust.StageLocal();Check(trust.ConfirmLocal(localToken),"stop fixture trust confirmation failed");
  var ownerField=typeof(CandidateSession).GetField("localOwner",BindingFlags.Static|BindingFlags.NonPublic);
  var stopField=typeof(CandidateSession).GetField("localStop",BindingFlags.Static|BindingFlags.NonPublic);
  var pendingStop=new System.Threading.Tasks.TaskCompletionSource<bool>();var owner=new EditorOwnerProcess();
  try{ownerField.SetValue(null,owner);stopField.SetValue(null,pendingStop.Task);var stopping=CandidateSession.StopLocalOwnerAsync();Check(!stopping.IsCompleted&&!trust.Confirmed,"local_stop_wait_retained_plugin_trust");Check(trust.StageLocal()==null&&!trust.Confirmed,"local_stop_allowed_new_trust");}
  finally{pendingStop.TrySetResult(true);ownerField.SetValue(null,null);stopField.SetValue(null,null);owner.Dispose();}
  Console.WriteLine("PASS PS007 local_stop_revokes_trust_before_waiting_owned_cleanup");
  return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}
 finally{CandidateSession.StopOwnedAsync().GetAwaiter().GetResult();Directory.Delete(dir,true);}}
}
