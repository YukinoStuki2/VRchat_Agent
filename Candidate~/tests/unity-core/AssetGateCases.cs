// Real candidate gate; trusted review evidence and native execution are doubles.
using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class AssetGateCases
{
    const string Target="AssetReads/Assets/Scope";
    static CandidateGate gate; static double now=1; static string project="p",connection="c",review="reviewed-context-v1";
    static int loads,captures,generic; static Action DuringRead; static Func<bool> LastTicket;
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    static JObject Wire(string kind,string plan="")=>new JObject { ["protocol"]=1,["kind"]=kind,["project_id"]=project,["connection_id"]=connection,["client_id"]="client",["task_id"]="task",["plan_id"]=plan,["body"]=new JObject() };
    static JObject Prepare(){var r=Wire("prepare");r["body"]=new JObject { ["operations"]=JArray.Parse("[{command:'manage_asset',action:'search'}]"),["targets"]=new JArray(Target),["ttl_seconds"]=60,["effects"]=JArray.Parse("[{kind:'asset_load_callbacks',version:1}]") };return r;}
    static JObject Execute(JObject plan){var r=Wire("execute",(string)plan["data"]["plan_id"]);r["body"]=new JObject { ["command"]="manage_asset",["params"]=new JObject { ["action"]="search",["path"]="Assets/Scope",["pageNumber"]=1,["pageSize"]=1,["generatePreview"]=false } };return r;}
    static void Enable(bool allowed){var m=typeof(CandidateGate).GetMethod("SetAssetCallbacks");Check(m!=null,"asset_callback_ceiling_missing");m.Invoke(gate,new object[]{allowed});}
    static CandidateGate Create()
    {
        var ctor=typeof(CandidateGate).GetConstructors().SingleOrDefault(x=>x.GetParameters().Length==7);
        Check(ctor!=null,"trusted_review_and_separate_asset_dispatch_seams_missing");
        return (CandidateGate)ctor.Invoke(new object[]{(Func<double>)(()=>now),(Func<string>)(()=>project),(Func<string>)(()=>connection),
            (Func<string,string>)(t=>{generic++;throw new Exception("generic evidence must not load assets");}),
            (Func<string,JObject,JObject>)((c,a)=>{generic++;throw new Exception("generic registry forbidden");}),
            (Func<string,string>)(t=>{captures++;return review;}),
            (Func<JObject,Func<bool>,JObject>)((a,valid)=>{LastTicket=valid;Check(valid(),"initial ticket invalid");loads++;DuringRead?.Invoke();return valid()?JObject.Parse("{success:true,data:{totalAssets:1,assets:[]}}") : JObject.Parse("{success:false}");})});
    }
    static JObject Approved(){var r=gate.Dispatch(Prepare());Check((bool)r["success"],"prepare failed: "+r);Check(gate.Approve((string)r["data"]["plan_id"],(string)r["data"]["digest"]),"approval failed");return r;}
    static int Main(){try{
        gate=Create();gate.SetCapability("manage_asset","search",true);
        Check(!(bool)gate.Dispatch(Prepare())["success"] && captures==0 && loads==0,"default ceiling not closed");
        Enable(true);var p=gate.Dispatch(Prepare());Check((bool)p["success"] && loads==0 && generic==0,"prepare called generic/native path");
        Check(!(bool)gate.Dispatch(Execute(p))["success"] && loads==0,"pending plan executed");
        p=Approved();Check((bool)gate.Dispatch(Execute(p))["success"] && loads==1 && generic==0,"approved read not separated");
        var policy=gate.LocalPlans()[0]["manifest"]["effect_policy"];
        Check((string)policy["kind"]=="asset_load_callbacks" && !(bool)policy["read_only"] && !(bool)policy["callback_effects_path_bounded"],"misleading callback risk manifest");
        Console.WriteLine("PASS AG001 default_denial_trusted_review_and_separate_dispatch");
        foreach(var bad in new[]{"missing","kind","version","mixed","target","policy"})
        {
            var request=Prepare();var body=(JObject)request["body"];
            if(bad=="missing")body.Remove("effects");
            if(bad=="kind")body["effects"][0]["kind"]="project_test_job_maintenance";
            if(bad=="version")body["effects"][0]["version"]=true;
            if(bad=="mixed")((JArray)body["operations"]).Add(JObject.Parse("{command:'read_console',action:'get'}"));
            if(bad=="target")body["targets"][0]="AssetReads/Assets/Scope/../Other";
            if(bad=="policy")body["effect_policy"]=new JObject();
            int before=loads;Check(!(bool)gate.Dispatch(request)["success"] && loads==before,"malformed effect plan: "+bad);
        }
        review=null;int old=captures;Check(!(bool)gate.Dispatch(Prepare())["success"] && captures>old,"unknown callback context accepted");review="reviewed-context-v1";
        Console.WriteLine("PASS AG002 missing_unknown_mixed_and_forged_review_denied");
        foreach(var bad in new[]{"scope","preview","run","size","extra"})
        {
            p=Approved();var request=Execute(p);var a=(JObject)request["body"]["params"];
            if(bad=="scope")a["path"]="Assets/Other";if(bad=="preview")a["generatePreview"]=true;
            if(bad=="run")a["action"]="delete";if(bad=="size")a["pageSize"]=51;if(bad=="extra")a["refresh"]=true;
            int before=loads;Check(!(bool)gate.Dispatch(request)["success"] && loads==before,"outside plan: "+bad);
        }
        Console.WriteLine("PASS AG003 strict_exact_target_action_and_budget");
        p=Approved();int beforePause=loads;
        Check(gate.Pause((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"pause failed");
        Check(!(bool)gate.Dispatch(Execute(p))["success"] && loads==beforePause,"pause ran read");
        Check(gate.Resume((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"resume failed");
        Enable(false);Enable(true);Check(!(bool)gate.Dispatch(Execute(p))["success"],"ceiling revival");
        p=Approved();review="changed";Check(!(bool)gate.Dispatch(Execute(p))["success"] && loads==beforePause,"review drift accepted");review="reviewed-context-v1";
        p=Approved();now=100;Check(!(bool)gate.Dispatch(Execute(p))["success"],"expiry ignored");now=1;
        p=Approved();Check(gate.FreezeForReload(Guid.NewGuid().ToString("N"),30)==null,"effect transferred on reload");
        Console.WriteLine("PASS AG004 pause_revoke_review_drift_expiry_and_reload");
        foreach(var cancel in new[]{"stop","context","binding","expiry"})
        {
            p=Approved();int before=loads;
            DuringRead=()=>{if(cancel=="stop")gate.StopAll("test stop");if(cancel=="context")review="changed";if(cancel=="binding")connection="changed";if(cancel=="expiry")now=100;};
            var result=gate.Dispatch(Execute(p));
            Check(!(bool)result["success"] && loads==before+1 && (bool)result["data"]["effects_may_have_occurred"] && !(bool)result["data"]["read_only"],"late result accepted: "+cancel);
            DuringRead=null;review="reviewed-context-v1";connection="c";now=1;
            Check(!(bool)gate.Dispatch(Execute(p))["success"],"late grant revived");
        }
        Check(generic==0,"generic path invoked");
        Console.WriteLine("PASS AG005 in_flight_ticket_rechecks_and_uncertainty");
        p=Approved();Check((bool)gate.Dispatch(Execute(p))["success"],"ticket fixture failed");
        Check(LastTicket!=null && !LastTicket(),"finished_call_ticket_reusable");
        Console.WriteLine("PASS AG006 call_ticket_expires_on_return");
        gate=new CandidateGate(()=>now,()=>project,()=>connection,t=>{generic++;return "unreviewed";},(c,a)=>{generic++;return JObject.Parse("{success:true}");});
        gate.SetCapability("manage_asset","search",true);Enable(true);
        int missingReviewBefore=generic;Check(!(bool)gate.Dispatch(Prepare())["success"] && generic==missingReviewBefore,"missing_trusted_adapters_not_closed");
        Console.WriteLine("PASS AG007 legacy_constructor_cannot_enable_unreviewed_assets");
        return 0;
    }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
