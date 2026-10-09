// TEST ONLY. Synthetic Unity peer, synthetic evidence, explicit fixture approval.
// Not included in the Unity package and must never be offered as a launcher.
using System;
using System.Diagnostics;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class WirePeer
{
 static void Trace(string phase){if(Environment.GetEnvironmentVariable("VRC_FIXTURE_TRACE")=="1")Console.Error.WriteLine("VRC_WIRE_PHASE:"+phase);}
 static void Main()
 {
  Trace("main");
  string connection=""; var timer=Stopwatch.StartNew(); int calls=0;
  using var backend=new WriteFixture(); Trace("fixture");
  var material=new MaterialCandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,backend);
  material.SetCapability("copy",true); material.SetCapability("edit",true);
  // Protocol-only readers: NOT Unity data; actual shipped readers/Session run in PS/BA/PR/DR groups.
  var debt=new System.Collections.Generic.Dictionary<string,string>();
  var ledger=new EffectCleanupLedger(k=>debt.TryGetValue(k,out var v)?v:"",(k,v)=>debt[k]=v);
  JObject Receipt(string kind,bool clean=false){var r=JObject.Parse("{version:1,read_only:false,all_mutations_observed:false,callback_effects_path_bounded:false}");r["kind"]=kind;if(clean)r["cleanup_confirmed"]=true;return r;}
  JObject FixtureRead(JObject p,Func<bool> ticket,bool prefab){
   if(!ticket())throw new Exception("fixture ticket revoked");
   bool hierarchy=(string)p["action"]=="get_hierarchy";
   var receipt=Receipt(prefab&&hierarchy?"prefab_contents_callbacks":"asset_load_callbacks",prefab);
   if(prefab){receipt["load_started"]=hierarchy;receipt["unload_started"]=hierarchy;}
   else{receipt["observed_at_utc"]="2026-10-08T00:00:00+00:00";receipt["pagination_consistency"]="live_not_snapshot";}
   return new JObject{["success"]=true,["data"]=new JObject{["fixture_only"]=true,["candidate_effects"]=receipt}};
  }
  async System.Threading.Tasks.Task<JObject> Discover(JObject p,Func<bool> ticket){
   await System.Threading.Tasks.Task.Delay(20);if(!ticket())throw new Exception("fixture ticket revoked");
   return new JObject{["success"]=true,["error"]=null,["data"]=new JObject{["tests"]=new JArray{new JArray("fixture-id","Fixture.Test","Fixture.Assembly",(string)p["mode"])},["candidate_effects"]=Receipt("test_discovery_callbacks",true)}};
  }
  Func<CandidateGate> newRead=()=>new CandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,
   p=>"fixture-only-evidence-"+p,(c,p)=> {
    // Protocol fixture only. Exact upstream scene methods are exercised separately by SceneNativeCases.
    if(c=="get_test_job"){
     // Protocol fixture ONLY; complete pinned manager/receipts are exercised by JobObservationCases.
     return new JObject{["success"]=true,["data"]=new JObject{
      ["job_id"]=(string)p["job_id"],["status"]="running",["mode"]="EditMode",["last_update_unix_ms"]=1,
      ["progress"]=new JObject{["editor_is_focused"]=false},
      ["candidate_effects"]=new JObject{["kind"]="project_test_job_maintenance",["version"]=1,
       ["project_wide"]=true,["read_only"]=false,["persistence"]="not_claimed",["all_mutations_observed"]=false,
       ["observed_at_utc"]="2026-10-08T00:00:00+00:00"}}};
    }
    if(c=="unity_reflect"){
     // Explicit protocol fixture. Not a reflection implementation or real Unity result.
     JToken d=(string)p["action"]=="search"?JObject.Parse("{query:'Transform',scope:'unity',count:0,results:[],truncated:false}"):
      (string)p["action"]=="get_member"?JObject.Parse("{found:false,type_name:'Transform',member_name:'Missing'}"):
      JObject.Parse("{found:false,query:'Transform'}");
     var r=JObject.FromObject(new SuccessResponse("fixture scoped metadata",d));
     if(!NativeReadContract.Valid(c,r,p))return new JObject{["success"]=false};
     r["data"]["candidate_scope"]=JObject.Parse("{type_set:'unity-engine-core-v1',all_loaded_types:false,extension_methods_included:false}");return r;
    }
    if(c=="manage_script" || c=="manage_shader"){
     // Explicit protocol fixture: real reader/file evidence are tested separately by SourceReadCases.
     string target=CandidateGate.SourceParams(c,p),text="fixture source\n";
     var d=new JObject{["path"]=target};
     if((string)p["action"]=="get_sha"){
      using var hash=System.Security.Cryptography.SHA256.Create();
      d["uri"]="mcpforunity://path/"+target;d["sha256"]=BitConverter.ToString(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(text))).Replace("-","").ToLowerInvariant();
      d["lengthBytes"]=System.Text.Encoding.UTF8.GetByteCount(text);d["lastModifiedUtc"]="2020-01-01T00:00:00.0000000Z";
     }else{
      d["contents"]=text;d["encodedContents"]=null;d["contentsEncoded"]=false;
      if(c=="manage_script")d["uri"]="mcpforunity://path/"+target;
     }
     var r=JObject.FromObject(new SuccessResponse("fixture source read",d));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    if(c=="manage_animation" && (string)p["action"]=="clip_get_info")return new JObject{["success"]=true,["data"]=new JObject{["path"]=(string)p["clipPath"],["name"]="Fixture clip",["length"]=1,["frameRate"]=60,["isLooping"]=true,["wrapMode"]="Loop",["curveCount"]=0,["curves"]=new JArray(),["eventCount"]=0,["events"]=new JArray()}};
    if(c=="manage_packages"){var r=JObject.FromObject(MCPForUnity.Editor.Tools.ManagePackages.HandleCommand(p));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};}
    if(c=="get_menu_items"){var r=JObject.FromObject(MCPForUnity.Editor.Resources.MenuItems.GetMenuItems.HandleCommand(p));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};}
    if(CandidateGate.EditorCommand(c)){
     var r=JObject.FromObject(MCPForUnity.Editor.Resources.Editor.MetadataFixture.Read(c));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    if(CandidateGate.ProjectCommand(c)){
     object data=c=="get_tags"?(object)new[]{"Untagged","Player"}:c=="get_layers"?new JObject{["0"]="Default",["5"]="UI"}:(object)new {projectRoot="/Fixture",projectName="Fixture",unityVersion="2022.3",platform="StandaloneWindows64",assetsPath="/Fixture/Assets",renderPipeline="BuiltIn",activeInputHandler="Old",packages=new {ugui=false,textmeshpro=false,inputsystem=false,uiToolkit=true,screenCapture=true}};
     var r=JObject.FromObject(new SuccessResponse("fixture project metadata",data));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    if(c=="manage_scene"){
     object data;
     if((string)p["action"]=="get_active")data=new{name="FixtureScene",path="",buildIndex=-1,isDirty=true,isLoaded=true,rootCount=2};
     else if((string)p["action"]=="get_build_settings")data=new[]{new{path="Assets/Fixture.unity",guid="fixture-guid",enabled=true,buildIndex=0}};
     else if((string)p["action"]=="validate")data=new{sceneName="FixtureScene",totalIssues=0,missingScripts=0,brokenPrefabs=0,repaired=0,issues=new JArray(),truncated=false,note=(string)null};
     else if((string)p["action"]=="get_hierarchy"){
      int total=p.ContainsKey("parent")?1:3,cursor=Math.Min((int?)p["cursor"]??0,total),size=(int)p["pageSize"],end=Math.Min(total,cursor+size);
      var items=new JArray();for(int i=cursor;i<end;i++){
       var item=new JObject{["name"]="fixture-node-"+i,["instanceID"]=p.ContainsKey("parent")?44:11+i,["activeSelf"]=true,["activeInHierarchy"]=true,
        ["tag"]="Untagged",["layer"]=0,["isStatic"]=false,["path"]="fixture-node-"+i,["childCount"]=0,["childrenTruncated"]=false,["childrenCursor"]=null,["childrenPageSizeDefault"]=200,["componentTypes"]=new JArray("Transform")};
       if((bool?)p["includeTransform"]==true)item["transform"]=new JObject{["position"]=new JArray(0,0,0),["rotation"]=new JArray(0,0,0),["scale"]=new JArray(1,1,1)};
       items.Add(item);
      }
      data=new{scope=p.ContainsKey("parent")?"children":"roots",cursor,pageSize=size,next_cursor=end<total?end.ToString():null,truncated=end<total,total,items};
     }
     else data=new{scenes=new[]{new{name="FixtureScene",path="",buildIndex=-1,isDirty=true,isLoaded=true,rootCount=2,isActive=true}}};
     var r=JObject.FromObject(new SuccessResponse("fixture scene metadata",data));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    if(c=="read_console"){var r=JObject.FromObject(MCPForUnity.Editor.Tools.ReadConsole.HandleCommand(p));return (bool?)r["success"]==true&&!NativeReadContract.Valid(c,r,p)?new JObject{["success"]=false}:r;}
    if(c=="get_gameobject" || c=="get_gameobject_components") {
     object d;
     if(c=="get_gameobject"){
      var v=new{x=0,y=0,z=0};d=new{instanceID=(int)p["instanceID"],name="fixture",tag="Untagged",layer=0,layerName="Default",active=true,activeInHierarchy=true,isStatic=false,
       transform=new{position=v,localPosition=v,rotation=v,localRotation=v,scale=v,lossyScale=v},parent=(int?)null,children=new int[0],componentTypes=new[]{"Transform"},path="fixture"};
     }else{
      int cursor=(int)p["cursor"],size=(int)p["pageSize"],total=3,end=Math.Min(total,cursor+size);var items=new JArray();
      for(int i=cursor;i<end;i++)items.Add(new JObject{["typeName"]="FixtureComponent",["instanceID"]=111+i});
      d=new{gameObjectID=(int)p["instanceID"],gameObjectName="fixture",components=items,cursor,pageSize=size,nextCursor=end<total?(int?)end:null,totalCount=total,hasMore=end<total,includeProperties=false};
     }
     var r=JObject.FromObject(new SuccessResponse("synthetic object protocol fixture",d));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    if(c=="manage_animation" && CandidateGate.AnimatorAction((string)p["action"])){
     object data=(string)p["action"]=="animator_get_parameter"?(object)new{name="Speed",type="Float",value=0.5f}:
      new{gameObject="Avatar",enabled=true,speed=1,hasController=false,controllerName=(string)null,applyRootMotion=false,updateMode="Normal",cullingMode="AlwaysAnimate",parameterCount=0,layerCount=0,parameters=new object[0],layers=new object[0],clips=new object[0]};
     var r=JObject.FromObject(new SuccessResponse("synthetic animator protocol fixture",data));return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    if(c=="find_gameobjects"){
     int total=3,size=(int)p["pageSize"],cursor=Math.Min((int?)p["cursor"]??0,total),end=Math.Min(total,cursor+size);
     var ids=new JArray();for(int i=cursor;i<end;i++)ids.Add(11+i);
     var r=JObject.FromObject(new SuccessResponse("synthetic find protocol fixture",new{instanceIDs=ids,pageSize=size,cursor,nextCursor=end<total?(int?)end:null,totalCount=total,hasMore=end<total}));
     return NativeReadContract.Valid(c,r,p)?r:new JObject{["success"]=false};
    }
    return JObject.FromObject(new SuccessResponse("fixture handler",new{fixture_only=true,call=++calls,command=c,path=(string)(p["materialPath"]??p["controllerPath"])}));
   },p=>"protocol-fixture-asset-"+p,(p,t)=>FixtureRead(p,t,false),
     (a,p)=>"protocol-fixture-prefab-"+a+p,(p,t)=>FixtureRead(p,t,true),
     p=>"protocol-fixture-discovery-"+p,Discover,ledger);
  var gate=newRead();
  ConsoleNativeCases.Seed();
  Action configureRead=()=>{
  foreach(string command in new[]{"get_project_info","get_tags","get_layers","get_selection","get_windows","get_active_tool","get_prefab_stage","get_menu_items"})gate.SetCapability(command,"read",true);
  gate.SetCapability("read_console","get",true);
  gate.SetCapability("find_gameobjects","find",true);
  gate.SetCapability("get_gameobject","read",true);gate.SetCapability("get_gameobject_components","read",true);
  foreach(string a in new[]{"get_active","get_build_settings","get_loaded_scenes","get_hierarchy","validate"})gate.SetCapability("manage_scene",a,true);
  foreach(string action in new[]{"get_type","get_member","search"})gate.SetCapability("unity_reflect",action,true);
  gate.SetCapability("manage_packages","get_package_info",true);
  gate.SetCapability("manage_script","read",true);gate.SetCapability("manage_script","get_sha",true);gate.SetCapability("manage_shader","read",true);
  gate.SetCapability("manage_material","get_material_info",true);
  foreach(string action in new[]{"controller_get_info","clip_get_info","animator_get_info","animator_get_parameter"})gate.SetCapability("manage_animation",action,true);
  };configureRead();
  JObject frozenRead=null,frozenMaterial=null;JArray savedHistory=null,savedRecords=null;
  Trace("ready");
  if(Environment.GetEnvironmentVariable("VRC_FIXTURE_TRACE")=="1"){Console.WriteLine("{\"fixture_started\":true}");Console.Out.Flush();}
  string line;
  while((line=Console.ReadLine())!=null)
  {
   JObject input=JObject.Parse(line);JObject output;
   bool isMaterial=(string)input["route"]=="vrchat_agent_material_dispatch";
   if(input["fixture_connection"]!=null){connection=(string)input["fixture_connection"];output=new JObject{["fixture_ready"]=true};}
   // TEST-ONLY private pipe fixture. It replaces gate objects, not a Unity domain.
   else if(input["fixture_freeze_reload"] is JObject fr){
    double now=timer.Elapsed.TotalSeconds;string id=(string)fr["handoff_id"];double window=(double)fr["window"];
    frozenRead=gate.FreezeForReload(id,window);frozenMaterial=material.FreezeForReload(id,window);
    savedHistory=material.ExportTransactionHistory();savedRecords=material.ExportTaskRecords();
    output=new JObject{["fixture_frozen"]=frozenRead!=null&&frozenMaterial!=null,["editor_now"]=now,
     ["transfers"]=frozenRead!=null&&frozenMaterial!=null?new JArray(frozenRead.ToString(Formatting.None),frozenMaterial.ToString(Formatting.None)):new JArray()};
   }
   else if(input["fixture_job_ceiling"] is JValue jc){
    gate.SetCapability("get_test_job","observe",true);gate.SetProjectJobMaintenance((bool)jc);
    output=new JObject{["fixture_job_ceiling"]=gate.ProjectJobMaintenanceAllowed};
   }
   else if(input["fixture_live_ceiling"] is JValue live){
    foreach(string a in new[]{"get_info","search"})gate.SetCapability("manage_asset",a,true);
    foreach(string a in new[]{"get_info","get_hierarchy"})gate.SetCapability("manage_prefabs",a,true);
    gate.SetCapability("get_tests","discover",true);
    gate.SetAssetCallbacks((bool)live);gate.SetPrefabContentsCallbacks((bool)live);gate.SetTestDiscoveryCallbacks((bool)live);
    output=new JObject{["fixture_live_ceiling"]=gate.AssetCallbacksAllowed&&gate.PrefabContentsCallbacksAllowed&&gate.TestDiscoveryCallbacksAllowed};
   }
   else if(input["fixture_evidence_change"]!=null){backend.Put("texture","fixture-user-edit");output=new JObject{["fixture_changed"]=true};}
   else if(input["fixture_stage_reload"] is JObject st){
    gate.StopAll("fixture gate replacement");material.StopAll("fixture gate replacement");gate=newRead();configureRead();
    material=new MaterialCandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,backend);
    bool history=material.ImportTransactionHistory(savedHistory),records=material.ImportTaskRecords(savedRecords);
    material.SetCapability("copy",true);material.SetCapability("edit",true);
    string readBinding=gate.StageReload(JObject.Parse((string)st["transfers"][0]),ReloadTransfer.Hash(frozenRead),connection);
    string materialBinding=material.StageReload(JObject.Parse((string)st["transfers"][1]),ReloadTransfer.Hash(frozenMaterial),connection);
    output=new JObject{["fixture_staged"]=history&&records&&readBinding!=null&&materialBinding!=null,["bindings"]=new JArray(readBinding,materialBinding)};
   }
   else if(input["fixture_commit_reload"] is JObject cm){
    bool read=gate.CommitReload((string)cm["handoff_id"],(string)cm["bindings"][0]);
    bool write=material.CommitReload((string)cm["handoff_id"],(string)cm["bindings"][1]);
    output=new JObject{["fixture_committed"]=read&&write};
   }
   else if(input["fixture_reload_material"]!=null){var records=material.ExportTaskRecords();material.StopAll("fixture reload");material=new MaterialCandidateGate(()=>timer.Elapsed.TotalSeconds,()=>"fixture-project",()=>connection,backend);output=new JObject{["fixture_reloaded"]=material.ImportTaskRecords(records),["plans"]=material.LocalPlans(),["capabilities"]=new JArray()};if(material.Allows("edit")||material.Allows("copy"))throw new Exception("reload authority");}
   else if(input["fixture_material_records"]!=null){output=new JObject{["records"]=material.ExportTaskRecords()};}
   else if(input["fixture_material_capabilities"] is JArray capabilities){foreach(var op in capabilities)material.SetCapability((string)op,true);output=new JObject{["fixture_configured"]=true};}
   else if(input["fixture_recover_exact"] is JObject recovery){output=new JObject{["fixture_recovered"]=material.RecoverPending((string)recovery["plan_id"],(string)recovery["digest"],(string)recovery["record_id"],(string)recovery["record_digest"])};}
   else if(input["fixture_local_plans"]!=null){output=new JObject{["fixture_plans"]=isMaterial?material.LocalPlans():gate.LocalPlans()};}
   else if(input["fixture_approve_exact"] is JObject a){output=new JObject{["fixture_approved"]=isMaterial?material.Approve((string)a["plan_id"],(string)a["digest"]):gate.Approve((string)a["plan_id"],(string)a["digest"])};}
   else if(input["fixture_pause_exact"] is JObject pause){output=new JObject{["fixture_paused"]=isMaterial?material.Pause((string)pause["plan_id"],(string)pause["digest"]):gate.Pause((string)pause["plan_id"],(string)pause["digest"])};}
   else if(input["fixture_resume_exact"] is JObject resume){output=new JObject{["fixture_resumed"]=isMaterial?material.Resume((string)resume["plan_id"],(string)resume["digest"]):gate.Resume((string)resume["plan_id"],(string)resume["digest"])};}
   else if(input["fixture_bytes"]!=null){output=new JObject{["candidate"]=backend.Value(input["fixture_bytes"].Type==JTokenType.String && (string)input["fixture_bytes"]=="codex"?"Assets/codex-candidate.mat":"Assets/candidate.mat"),["source"]=backend.Value("Assets/source.mat"),["writes"]=backend.Writes};}
   else if(input["fixture_local_approve"]!=null){var p=gate.LocalPlans();output=new JObject{["fixture_approved"]=p.Count==1&&gate.Approve((string)p[0]["plan_id"],(string)p[0]["digest"])};}
   else {
    var result=isMaterial?material.Dispatch((JObject)input["request"]):gate.DispatchAsync((JObject)input["request"]).GetAwaiter().GetResult();
    object native=(bool?)result["success"]==true ? (object)new SuccessResponse("fixture transport",result["data"]):new ErrorResponse((string)result["error"],result["data"]);
    // Fixed upstream TransportCommandDispatcher success transport envelope.
    output=new JObject{["status"]="success",["result"]=JObject.FromObject(native)};
   }
   Console.WriteLine(output.ToString(Formatting.None));Console.Out.Flush(); Trace("reply");
  }
  Trace("eof");
 }
}
