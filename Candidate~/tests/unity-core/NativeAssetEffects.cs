// Characterization only: verbatim pinned native methods, explicit Unity API doubles.
// No candidate tool registration, real Unity project, or disk mutation.
using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Tools;
#if CANDIDATE_ASSET
using ManageAsset = MCPForUnity.Editor.Tools.CandidateScopedAssets;
#endif

namespace UnityEngine
{
    public class Object { public int GetInstanceID() => 17; public static void DestroyImmediate(Object o) => throw new Exception("preview forbidden"); }
    public enum TextureFormat { RGB24 }
    public struct Rect { public Rect(int a,int b,int c,int d) {} }
    public class Texture2D : Object
    {
        public int width => 8; public int height => 8;
        public Texture2D(int w,int h,TextureFormat f,bool m) => throw new Exception("preview forbidden");
        public void ReadPixels(Rect r,int x,int y) => throw new Exception("preview forbidden");
        public void Apply() => throw new Exception("preview forbidden");
        public byte[] EncodeToPNG() => throw new Exception("preview forbidden");
    }
    public class RenderTexture : Object
    {
        public static RenderTexture active; public int width => 8; public int height => 8;
        public static RenderTexture GetTemporary(int w,int h) => throw new Exception("preview forbidden");
        public static void ReleaseTemporary(RenderTexture r) => throw new Exception("preview forbidden");
    }
    public static class Graphics { public static void Blit(Texture2D t,RenderTexture r) => throw new Exception("preview forbidden"); }
}
namespace UnityEditor
{
    public static class AssetDatabase
    {
        public static string[] Paths = {"Assets/Scope/a.asset","Assets/Scope/b.asset","Assets/Scope/c.asset","Assets/Other/d.asset"};
        public static List<string> Loads = new List<string>();
        public static Action<string> OnLoad;
        public static string[] LastFolders;
        public static string AssetPathToGUID(string p) { if(!Paths.Contains(p))return ""; using(var hash=System.Security.Cryptography.MD5.Create())return BitConverter.ToString(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(p))).Replace("-","").ToLowerInvariant(); } // Deterministic fixture IDs, not security hashes.
        public static Func<string,string> ResolveOverride;
        public static string GUIDToAssetPath(string g) => ResolveOverride == null ? Paths.SingleOrDefault(p=>AssetPathToGUID(p)==g) ?? "" : ResolveOverride(g);
        public static bool IsValidFolder(string p) => p == "Assets/Scope" || p == "Assets/Other";
        public static Type GetMainAssetTypeAtPath(string p) => typeof(UnityEngine.Object);
        public static T LoadAssetAtPath<T>(string p) where T : UnityEngine.Object, new()
        { Loads.Add(p); OnLoad?.Invoke(p); return new T(); }
        public static string[] FindAssets(string filter,string[] folders)
        { LastFolders=folders; return Paths.Where(p=>folders==null || folders.Any(f=>p.StartsWith(f+"/",StringComparison.Ordinal))).Select(AssetPathToGUID).ToArray(); }
    }
    public static class AssetPreview
    {
        public static int Calls;
        public static UnityEngine.Texture2D GetAssetPreview(UnityEngine.Object o)
        { Calls++; throw new Exception("preview forbidden"); }
    }
}
namespace MCPForUnity.Editor.Helpers
{
    public static class AssetPathUtility { public static string SanitizeAssetPath(string p) => p; } // Input paths in these cases are fixed, not sanitizer coverage.
    public static class McpLog { public static List<string> Warnings=new List<string>(); public static void Warn(string s) => Warnings.Add(s); }
    public static class Extensions { public static int GetInstanceIDCompat(this UnityEngine.Object o) => o.GetInstanceID(); }
}
static class NativeAssetEffects
{
    static void Check(bool v,string reason) { if(!v) throw new Exception(reason); }
    static bool Allowed = true;
    static object Query(JObject p)
    {
#if CANDIDATE_ASSET
        return ManageAsset.Query(p, () => Allowed);
#else
        return ManageAsset.Query(p);
#endif
    }
    static JObject Search(string path="Assets/Scope",int page=1,int size=1) => JObject.FromObject(Query(new JObject { ["path"]=path,["pageNumber"]=page,["pageSize"]=size,["generatePreview"]=false }));
    static int OutsideMutation;
    static int Main(string[] args)
    {
        try
        {
            string id=args[0]; JObject r;
            switch(id)
            {
                case "BA015":
#if CANDIDATE_ASSET
                    var infoGuid=UnityEditor.AssetDatabase.AssetPathToGUID("Assets/Scope/a.asset");
                    UnityEditor.AssetDatabase.OnLoad=path=>UnityEditor.AssetDatabase.ResolveOverride=g=>g==infoGuid ? "Assets/Other/d.asset" : UnityEditor.AssetDatabase.Paths.SingleOrDefault(p=>UnityEditor.AssetDatabase.AssetPathToGUID(p)==g) ?? "";
                    r=JObject.FromObject(ManageAsset.Info("Assets/Scope/a.asset",()=>Allowed));
                    Check(!(bool)r["success"] && r.ToString().Contains("effects_may_have_occurred=true") && UnityEditor.AssetDatabase.Loads.Count==1,"INFO_ACCEPTED_GUID_MOVED_IN_CALLBACK");
                    Console.WriteLine("OBS exact_info_identity_revalidated_after_load=true");break;
#else
                    Check(false,"asset info identity requires candidate");break;
#endif
                case "BA014":
#if CANDIDATE_ASSET
                    var movedGuid=UnityEditor.AssetDatabase.AssetPathToGUID("Assets/Scope/b.asset");
                    UnityEditor.AssetDatabase.OnLoad=path=>UnityEditor.AssetDatabase.ResolveOverride=g=>g==movedGuid ? "Assets/Other/d.asset" : UnityEditor.AssetDatabase.Paths.SingleOrDefault(p=>UnityEditor.AssetDatabase.AssetPathToGUID(p)==g) ?? "";
                    r=Search(size:2);
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==1 && UnityEditor.AssetDatabase.Loads[0]=="Assets/Scope/a.asset","LOAD_AFTER_GUID_MOVED_BETWEEN_ROWS");
                    Console.WriteLine("OBS guid_move_after_first_callback_stops_next_asset_load=true");break;
#else
                    Check(false,"asset identity contract requires candidate");break;
#endif
                case "BA013":
#if CANDIDATE_ASSET
                    double gateTime=1;string reviewContext=null;int genericCalls=0;
                    var realGate=new Yukino.VRChatAgent.CandidateGate(()=>gateTime,()=>"fixture-project",()=>"fixture-connection",
                        target=>{genericCalls++;throw new Exception("generic evidence is not reviewed asset evidence");},
                        (command,a)=>{genericCalls++;throw new Exception("generic native registry is forbidden");},
                        target=>reviewContext,
                        (a,ticket)=>Yukino.VRChatAgent.AssetObservation.Read(a,ticket,(query,valid)=>{
                            var forwarded=(JObject)query.DeepClone();forwarded.Remove("action");
                            return ManageAsset.Query(forwarded,valid);
                        }));
                    JObject Wire(string kind,string plan="")=>new JObject { ["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["connection_id"]="fixture-connection",["client_id"]="fixture-client",["task_id"]="fixture-task",["plan_id"]=plan,["body"]=new JObject() };
                    JObject PrepareAsset(){var w=Wire("prepare");w["body"]=JObject.Parse("{operations:[{command:'manage_asset',action:'search'}],targets:['AssetReads/Assets/Scope'],ttl_seconds:60,effects:[{kind:'asset_load_callbacks',version:1}]}");return w;}
                    JObject ExecuteAsset(JObject plan){var w=Wire("execute",(string)plan["data"]["plan_id"]);w["body"]=JObject.Parse("{command:'manage_asset',params:{action:'search',path:'Assets/Scope',pageNumber:1,pageSize:2,generatePreview:false}}");return w;}
                    realGate.SetCapability("manage_asset","search",true);
                    Check(!(bool)realGate.Dispatch(PrepareAsset())["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"PIPELINE_DEFAULT_NOT_CLOSED");
                    realGate.SetAssetCallbacks(true);
                    Check(!(bool)realGate.Dispatch(PrepareAsset())["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"PIPELINE_UNKNOWN_REVIEW_ACCEPTED");
                    reviewContext="synthetic-reviewed-context-not-real-project";
                    var realPlan=realGate.Dispatch(PrepareAsset());Check((bool)realPlan["success"],"PIPELINE_PREPARE_FAILED");
                    Check(!(bool)realGate.Dispatch(ExecuteAsset(realPlan))["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"PIPELINE_PENDING_EXECUTED");
                    // Denied execution revokes that pending plan; approval requires a fresh plan.
                    realPlan=realGate.Dispatch(PrepareAsset());Check((bool)realPlan["success"],"PIPELINE_REPREPARE_FAILED");
                    Check(realGate.Approve((string)realPlan["data"]["plan_id"],(string)realPlan["data"]["digest"]),"PIPELINE_APPROVAL_FAILED");
                    r=realGate.Dispatch(ExecuteAsset(realPlan));
                    Check((bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==2 && (string)r["data"]["candidate_effects"]["kind"]=="asset_load_callbacks" && !(bool)r["data"]["candidate_effects"]["all_mutations_observed"],"PIPELINE_REAL_READER_RECEIPT_FAILED");
                    UnityEditor.AssetDatabase.Loads.Clear();UnityEditor.AssetDatabase.OnLoad=path=>realGate.StopAll("fixture local stop inside callback");
                    r=realGate.Dispatch(ExecuteAsset(realPlan));
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==1 && (bool)r["data"]["effects_may_have_occurred"],"PIPELINE_STOP_DID_NOT_BLOCK_NEXT_LOAD");
                    UnityEditor.AssetDatabase.OnLoad=null;
                    Check(!(bool)realGate.Dispatch(ExecuteAsset(realPlan))["success"] && UnityEditor.AssetDatabase.Loads.Count==1,"PIPELINE_STOPPED_PLAN_REVIVED");
                    Check(genericCalls==0,"PIPELINE_CALLED_GENERIC_PATH");
                    Console.WriteLine("OBS real_candidate_gate_adapter_shipped_reader=true; review_UI_Unity_APIs_are_doubles=true");break;
#else
                    Check(false,"asset pipeline requires candidate");break;
#endif
                case "BA012":
#if CANDIDATE_ASSET
                    var infoRead=typeof(Yukino.VRChatAgent.CandidateGate).Assembly.GetType("Yukino.VRChatAgent.AssetObservation").GetMethod("Read",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
                    var infoArgs=JObject.Parse("{action:'get_info',path:'Assets/Scope/a.asset',generatePreview:false}");
                    Func<JObject,Func<bool>,object> actualInfo=(a,t)=>ManageAsset.Info((string)a["path"],t);
                    r=(JObject)infoRead.Invoke(null,new object[]{infoArgs,(Func<bool>)(()=>Allowed),actualInfo});
                    Check((bool)r["success"] && (string)r["data"]["path"]=="Assets/Scope/a.asset" && (string)r["data"]["candidate_effects"]["kind"]=="asset_load_callbacks","EXACT_INFO_RECEIPT_FAILED");
                    UnityEditor.AssetDatabase.OnLoad=p=>Allowed=false;
                    r=(JObject)infoRead.Invoke(null,new object[]{infoArgs,(Func<bool>)(()=>Allowed),actualInfo});
                    Check(!(bool)r["success"] && (bool)r["data"]["effects_may_have_occurred"] && UnityEditor.AssetDatabase.Loads.Count==2,"EXACT_INFO_LATE_RESULT_ACCEPTED");
                    Allowed=true;UnityEditor.AssetDatabase.OnLoad=null;
                    foreach(var bad in new[]{"preview","action","path","extra"})
                    {
                        var invalid=(JObject)infoArgs.DeepClone();if(bad=="preview")invalid["generatePreview"]=true;if(bad=="action")invalid["action"]="create";if(bad=="path")invalid["path"]="Assets/../outside";if(bad=="extra")invalid["refresh"]=true;
                        r=(JObject)infoRead.Invoke(null,new object[]{invalid,(Func<bool>)(()=>Allowed),actualInfo});
                        Check(!(bool)r["success"] && !(bool)r["data"]["effects_may_have_occurred"] && UnityEditor.AssetDatabase.Loads.Count==2,"INVALID_INFO_CALLED_READER");
                    }
                    Console.WriteLine("OBS info_exact_result_receipt_and_revocation_characterization=true");break;
#else
                    Check(false,"asset info adapter requires candidate");break;
#endif
                case "BA011":
#if CANDIDATE_ASSET
                    var validation=typeof(Yukino.VRChatAgent.CandidateGate).Assembly.GetType("Yukino.VRChatAgent.AssetObservation").GetMethod("Read",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
                    var query=JObject.Parse("{action:'search',path:'Assets/Scope',pageNumber:1,pageSize:1,generatePreview:false}");
                    var baseline=Search();
                    foreach(var bad in new[]{"path","count","page","more","guid","preview","shape","unknown","date"})
                    {
                        var broken=(JObject)baseline.DeepClone();var data=(JObject)broken["data"];var row=(JObject)data["assets"][0];
                        if(bad=="path")row["path"]="Assets/Other/x.asset";
                        if(bad=="count")data["totalAssets"]=0;if(bad=="page")data["pageNumber"]=2;if(bad=="more")data["hasMore"]=false;
                        if(bad=="guid")row["guid"]="not-a-guid";if(bad=="preview")row["previewBase64"]="unexpected";
                        if(bad=="shape")row["hidden"]="sensitive-fixture-detail";if(bad=="unknown"){row["assetType"]="Unknown";row["instanceID"]=0;}
                        if(bad=="date")row["lastWriteTimeUtc"]="invalid";
                        r=(JObject)validation.Invoke(null,new object[]{query,(Func<bool>)(()=>true),(Func<JObject,Func<bool>,object>)((a,t)=>broken)});
                        Check(!(bool)r["success"] && (bool)r["data"]["effects_may_have_occurred"] && !r.ToString().Contains("sensitive-fixture-detail"),"INVALID_ASSET_RESULT_ACCEPTED_"+bad);
                    }
                    Console.WriteLine("OBS invalid_scope_counts_shape_and_preview_denied_after_read=true");break;
#else
                    Check(false,"asset result validator requires candidate");break;
#endif
                case "BA010":
#if CANDIDATE_ASSET
                    var observer=typeof(Yukino.VRChatAgent.CandidateGate).Assembly.GetType("Yukino.VRChatAgent.AssetObservation");
                    Check(observer!=null,"ASSET_RECEIPT_ADAPTER_MISSING");
                    var read=observer.GetMethod("Read",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);
                    Func<JObject,Func<bool>,object> invoke=(a,t)=>{var forwarded=(JObject)a.DeepClone();forwarded.Remove("action");return ManageAsset.Query(forwarded,t);};
                    var arguments=JObject.Parse("{action:'search',path:'Assets/Scope',pageNumber:1,pageSize:1,generatePreview:false}");
                    r=(JObject)read.Invoke(null,new object[]{arguments,(Func<bool>)(()=>false),invoke});
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"RECEIPT_ADAPTER_WITHOUT_AUTH_LOADED");
                    r=(JObject)read.Invoke(null,new object[]{arguments,(Func<bool>)(()=>true),invoke});
                    Check((bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==1,"RECEIPT_REAL_READER_FAILED");
                    var receipt=(JObject)r["data"]["candidate_effects"];
                    Check(receipt!=null && (string)receipt["kind"]=="asset_load_callbacks" && !(bool)receipt["read_only"] && !(bool)receipt["all_mutations_observed"] && !(bool)receipt["callback_effects_path_bounded"],"RECEIPT_OVERCLAIMS_EFFECT_OBSERVATION");
                    Console.WriteLine("OBS actual_reader_effect_receipt_without_zero_mutation_claim=true");break;
#else
                    Check(false,"asset receipt requires candidate");break;
#endif
                case "BA009":
#if CANDIDATE_ASSET
                    var gate=new Yukino.VRChatAgent.CandidateGate(()=>1,()=>"p",()=>"c",_=>throw new Exception("generic evidence forbidden"),
                        (c,a)=>throw new Exception("registry forbidden"),_=>"explicit-test-review",(a,ticket)=> {
                            var forwarded=(JObject)a.DeepClone();forwarded.Remove("action");
                            return JObject.FromObject(ManageAsset.Query(forwarded,ticket));
                        });
                    gate.SetCapability("manage_asset","search",true);gate.SetAssetCallbacks(true);
                    var prepare=JObject.Parse("{protocol:1,kind:'prepare',project_id:'p',connection_id:'c',client_id:'client',task_id:'task',plan_id:'',body:{operations:[{command:'manage_asset',action:'search'}],targets:['AssetReads/Assets/Scope'],ttl_seconds:60,effects:[{kind:'asset_load_callbacks',version:1}]}}");
                    var pending=gate.Dispatch(prepare);
                    Check((bool)pending["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"PREPARE_REAL_CHAIN_LOADED");
                    Check(gate.Approve((string)pending["data"]["plan_id"],(string)pending["data"]["digest"]),"CHAIN_APPROVAL_FAILED");
                    var request=(JObject)prepare.DeepClone();request["kind"]="execute";request["plan_id"]=pending["data"]["plan_id"].DeepClone();
                    request["body"]=JObject.Parse("{command:'manage_asset',params:{action:'search',path:'Assets/Scope',pageNumber:1,pageSize:2,generatePreview:false}}");
                    UnityEditor.AssetDatabase.OnLoad=p=>gate.StopAll("fixture revoke");
                    r=gate.Dispatch(request);
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==1 && (bool)r["data"]["effects_may_have_occurred"],"REAL_READER_IGNORED_GATE_REVOCATION");
                    Check(!(bool)gate.Dispatch(request)["success"] && UnityEditor.AssetDatabase.Loads.Count==1,"REPLAY_LOADED_AFTER_REVOKE");
                    Console.WriteLine("OBS actual_gate_and_shipped_reader_stop_after_one_load=true");break;
#else
                    throw new Exception("candidate fixture required");
#endif
                case "BA008":
                    UnityEditor.AssetDatabase.OnLoad=p=>{ OutsideMutation++; throw new Exception("sensitive-fixture-detail"); };
                    r=Search();
                    Check(!(bool)r["success"] && OutsideMutation==1 && r.ToString().Contains("effects_may_have_occurred=true") && !r.ToString().Contains("sensitive-fixture-detail"),"CALLBACK_FAILURE_UNCERTAINTY_NO_DETAIL");
#if CANDIDATE_ASSET
                    r=JObject.FromObject(ManageAsset.Info("Assets/Scope/a.asset",()=>Allowed));
#else
                    r=JObject.FromObject(ManageAsset.Info("Assets/Scope/a.asset"));
#endif
                    Check(!(bool)r["success"] && OutsideMutation==2 && r.ToString().Contains("effects_may_have_occurred=true") && !r.ToString().Contains("sensitive-fixture-detail"),"INFO_FAILURE_UNCERTAINTY_NO_DETAIL");
                    Console.WriteLine("OBS load_failure_uncertainty_disclosed_details_suppressed=true"); break;
                case "BA007":
                    foreach(var resolved in new[]{"Assets/Other/d.asset", "Assets/Scope/a.asset", ""})
                    {
                        UnityEditor.AssetDatabase.ResolveOverride=g=>g==UnityEditor.AssetDatabase.AssetPathToGUID("Assets/Scope/b.asset")?resolved:UnityEditor.AssetDatabase.Paths.SingleOrDefault(p=>UnityEditor.AssetDatabase.AssetPathToGUID(p)==g) ?? "";
                        r=Search();
                        Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"ALL_PATHS_VALIDATED_BEFORE_PAGE_LOAD");
                    }
                    Console.WriteLine("OBS moved_duplicate_missing_guid_zero_loads=true"); break;
                case "BA006":
                    UnityEditor.AssetDatabase.OnLoad=p=>Allowed=false;
                    r=Search(size:2);
                    Check(!Allowed && !(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==1,"REVOKE_STOPS_NEXT_LOAD_AND_SUCCESS");
                    Console.WriteLine("OBS revoked_after_first_load_no_next_load=true"); break;
                case "BA005":
                    r=JObject.FromObject(ManageAsset.Query(new JObject { ["path"]="Assets/Scope",["pageNumber"]=1,["pageSize"]=1,["generatePreview"]=false }));
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"NO_TRUST_TICKET_ZERO_LOAD");
                    r=JObject.FromObject(ManageAsset.Info("Assets/Scope/a.asset"));
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"NO_TRUST_TICKET_INFO_ZERO_LOAD");
                    Console.WriteLine("OBS missing_ticket_denied=true"); break;
                case "BA004":
                    var valid=new JObject { ["path"]="Assets/Scope",["pageNumber"]=1,["pageSize"]=1,["generatePreview"]=false };
                    var bads=new List<JObject>();
                    foreach(var badPath in new[]{"", "Assets", "Assets/Scope/../Other", "Assets/Scope/", "assets/Scope"})
                    { var x=(JObject)valid.DeepClone();x["path"]=badPath;bads.Add(x); }
                    foreach(var field in new[]{"pageNumber","pageSize"})
                    foreach(JToken bad in new JToken[]{new JValue(0),new JValue(-1),new JValue(2147483647),new JValue("1"),new JValue(true)})
                    { var x=(JObject)valid.DeepClone();x[field]=bad;bads.Add(x); }
                    var preview=(JObject)valid.DeepClone();preview["generatePreview"]=true;bads.Add(preview);
                    var unknown=(JObject)valid.DeepClone();unknown["write"]=true;bads.Add(unknown);
                    var date=(JObject)valid.DeepClone();date["filterDateAfter"]="not-a-date";bads.Add(date);
                    foreach(var bad in bads)
                    {
                        r=JObject.FromObject(Query(bad));
                        Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0 && UnityEditor.AssetPreview.Calls==0,"BAD_PARAMS_ZERO_LOAD");
                    }
                    Console.WriteLine("OBS invalid_inputs_zero_loads=true"); break;
                case "BA003":
                    UnityEditor.AssetDatabase.Paths=Enumerable.Range(0,4097).Select(i=>"Assets/Scope/"+i+".asset").ToArray();
                    r=Search();
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"MATCH_BUDGET_BEFORE_ANY_LOAD");
                    Console.WriteLine("OBS too_many_matches_zero_loads=true"); break;
                case "BA002":
                    r=Search("Assets/Missing");
                    Check(!(bool)r["success"] && UnityEditor.AssetDatabase.Loads.Count==0,"INVALID_SCOPE_MUST_NOT_LOAD");
                    Check(UnityEditor.AssetDatabase.LastFolders==null,"no native search for invalid folder");
                    Console.WriteLine("OBS invalid_folder_rejected_before_search=true"); break;
                case "BA001":
                    r=Search();
                    Check((bool)r["success"] && r["data"]["assets"].Count()==1,"returned page");
                    Check(UnityEditor.AssetDatabase.Loads.Count==1,"PAGE_LOAD_BUDGET_VIOLATED");
                    Console.WriteLine("OBS returned=1 loads=1"); break;
                case "NA001":
                    r=Search();
                    Check((bool)r["success"] && r["data"]["assets"].Count()==1,"returned page");
                    Check(UnityEditor.AssetDatabase.Loads.Count==3,"native loads every result before paging");
                    if(args.Contains("--assert-page-budget")) Check(UnityEditor.AssetDatabase.Loads.Count<=1,"PAGE_LOAD_BUDGET_VIOLATED");
                    Console.WriteLine("OBS returned=1 loads=3 preview_calls="+UnityEditor.AssetPreview.Calls); break;
                case "NA002":
                    r=Search("Assets/Missing",1,20);
                    Check((bool)r["success"] && UnityEditor.AssetDatabase.LastFolders==null,"native invalid folder fallback");
                    Check(UnityEditor.AssetDatabase.Loads.Contains("Assets/Other/d.asset"),"whole-project fixture load");
                    Check(r["data"]["assets"].Count()==4,"fallback returns all fixture paths");
                    Console.WriteLine("OBS invalid_folder_became_global=true loads=4"); break;
                case "NA003":
                    UnityEditor.AssetDatabase.OnLoad=p=>OutsideMutation++;
                    r=JObject.FromObject(ManageAsset.Info("Assets/Scope/a.asset"));
                    Check((bool)r["success"] && OutsideMutation==1,"in-process load callback runs outside result boundary");
                    Check(UnityEditor.AssetDatabase.Loads.SequenceEqual(new[]{"Assets/Scope/a.asset"}),"exact target loaded");
                    Console.WriteLine("OBS exact_result_scope_does_not_isolate_callback=true"); break;
                case "NA004":
                    var first=Search();
                    UnityEditor.AssetDatabase.Paths=new[]{"Assets/Scope/b.asset","Assets/Scope/a.asset","Assets/Scope/c.asset","Assets/Other/d.asset"};
                    var second=Search(page:2);
                    Check((string)first["data"]["assets"][0]["path"]==(string)second["data"]["assets"][0]["path"],"requery pagination can duplicate rows");
                    Check(UnityEditor.AssetDatabase.Loads.Count==6,"each page loads all matching fixture assets");
                    Console.WriteLine("OBS separate_queries_not_snapshot_consistent=true loads=6"); break;
                case "NA005":
                    UnityEditor.AssetDatabase.OnLoad=p=>{ OutsideMutation++; throw new Exception("synthetic load callback failed"); };
                    r=Search();
                    Check(!(bool)r["success"] && OutsideMutation==1,"error does not undo prior callback effect");
                    Console.WriteLine("OBS failure_with_prior_callback_effect=true"); break;
                case "NA006":
                    r=JObject.FromObject(ManageAsset.Info("Assets/Scope/b.asset"));
                    Check((bool)r["success"] && (string)r["data"]["path"]=="Assets/Scope/b.asset","native metadata shape");
                    Check(UnityEditor.AssetDatabase.Loads.Count==1 && UnityEditor.AssetPreview.Calls==0,"preview disabled still loads");
                    Console.WriteLine("OBS preview_disabled_is_not_load_disabled=true"); break;
                default: throw new Exception("unknown test id");
            }
            Check(UnityEditor.AssetPreview.Calls==0,"preview forbidden");
            Console.WriteLine("PASS "+id+" pinned native method characterization; Unity doubles"); return 0;
        }
        catch(Exception e) { Console.Error.WriteLine(e.Message); return 1; }
    }
}
