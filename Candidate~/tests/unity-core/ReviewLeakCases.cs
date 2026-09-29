// Review only: real candidate adapter/core/window and fixed upstream Response.cs.
// Unity events, assets/evidence, native handler and human approval are fixtures.
using System;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Services.Transport;
using MCPForUnity.Editor.Services.Transport.Transports;
using UnityEngine;
using Yukino.VRChatAgent;
internal static class ReviewLeakCases
{
    const string Marker="FIXTURE_ONLY_PRIVATE_EXCEPTION";
    static JObject Wire(string kind,string id,JObject body)=>new JObject {
        ["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]="connection-A",
        ["client_id"]="client-review",["task_id"]="task-review",["plan_id"]=id,["body"]=body};
    static JObject Call(JObject r)=>JObject.FromObject(AdapterOwnedFixture.Call(r));
    static JObject Ready()
    {
        CandidateSession.Gate.StopAll("review fixture reset");
        CandidateSession.Gate.SetCapability("manage_material","get_material_info",true);
        var p=Call(Wire("prepare","",JObject.Parse("{\"operations\":[{\"command\":\"manage_material\",\"action\":\"get_material_info\"}],\"targets\":[\"Assets/Read.mat\"],\"ttl_seconds\":60}")));
        if(!(bool)p["success"] || !CandidateSession.Gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]))
            throw new Exception("review fixture prepare/approve failed: "+p);
        return Wire("execute",(string)p["data"]["plan_id"],JObject.Parse("{\"command\":\"manage_material\",\"params\":{\"action\":\"get_material_info\",\"materialPath\":\"Assets/Read.mat\"}}"));
    }
    static int Case(string id,Func<object> response)
    {
        var request=Ready(); int before=CommandRegistry.Calls;
        CommandRegistry.Implementation=(c,p)=>response();
        var result=Call(request);
        bool leak=result.ToString(Formatting.None).Contains(Marker);
        Console.WriteLine(new JObject { ["test_id"]=id,["fixture_only"]=true,["observed_response"]=result,
            ["native_calls"]=CommandRegistry.Calls-before,["remaining_plans"]=CandidateSession.Gate.LocalPlans().Count,
            ["expected_exception_marker_absent"]=true,["actual_exception_marker_present"]=leak,
            ["outcome"]=leak?"FAIL":"PASS" }.ToString(Formatting.None));
        return leak?1:0;
    }
    static int Main()
    {
        string directory=Path.Combine(Path.GetTempPath(),"vragent-unity-review-"+Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(directory,"Assets")); Application.dataPath=Path.Combine(directory,"Assets");
            File.WriteAllText(Path.Combine(Application.dataPath,"Read.mat"),"fixture disk");
            File.WriteAllText(Path.Combine(Application.dataPath,"Read.mat.meta"),"fixture meta");
            AdapterOwnedFixture.Begin();
            // Exact returned-error shape of upstream ManageMaterial.HandleCommand catch at 52-54.
            int failures=Case("UR002_native_error_response_must_not_leak_exception",()=>new ErrorResponse(Marker,new {stackTrace="fixture stack "+Marker}));
            // Exact success-data placement of property-level caught errors at 563-565,578-583.
            failures+=Case("UR003_native_success_property_error_must_not_leak_exception",()=>new SuccessResponse("fixture material info",new {
                material="fixture material",shader="fixture shader",properties=new [] {new {name="_Fixture",type="Float",description="fixture",value="<error: "+Marker+">"}}}));
            return failures==0?0:1;
        }
        catch(Exception e){Console.Error.WriteLine("HARNESS_ERROR "+e);return 2;}
        finally
        {
            CandidateSession.Gate.StopAll("review fixture cleanup");
            if(Directory.Exists(directory))Directory.Delete(directory,true);
            Console.WriteLine(new JObject { ["cleanup_fixture_removed"]=!Directory.Exists(directory),["fixture_path"]=directory }.ToString(Formatting.None));
        }
    }
}
