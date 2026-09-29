// Real product adapter/core and upstream Response; Unity/native handler/evidence are fixtures.
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
internal static class FixOutputCases
{
    const string Marker="FIXTURE_ONLY_PRIVATE_EXCEPTION";
    static int failures;
    static void Check(bool ok,string message) { if(!ok) throw new Exception(message); }
    static JObject Wire(string kind,string id,JObject body)=>new JObject {
        ["protocol"]=1,["kind"]=kind,["project_id"]="project-A",["connection_id"]="connection-A",
        ["client_id"]="client-fix",["task_id"]="task-fix",["plan_id"]=id,["body"]=body};
    static JObject Call(JObject r)=>JObject.FromObject(AdapterOwnedFixture.Call(r));
    static JObject Ready(string command)
    {
        CandidateSession.Gate.StopAll("fix fixture reset");
        string action=command=="manage_material"?"get_material_info":"controller_get_info";
        string path=command=="manage_material"?"Assets/Read.mat":"Assets/Read.controller";
        CandidateSession.Gate.SetCapability(command,action,true);
        var p=Call(Wire("prepare","",new JObject { ["operations"]=new JArray(new JObject{["command"]=command,["action"]=action}),["targets"]=new JArray(path),["ttl_seconds"]=60 }));
        Check((bool)p["success"] && CandidateSession.Gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"prepare/approve");
        return Wire("execute",(string)p["data"]["plan_id"],new JObject{["command"]=command,["params"]=new JObject{["action"]=action,[command=="manage_material"?"materialPath":"controllerPath"]=path}});
    }
    static void Case(string id,Func<object> response,bool success=false,string command="manage_material")
    {
        try {
            var request=Ready(command); int before=CommandRegistry.Calls;
            object native=response();
            CommandRegistry.Implementation=(c,p)=>native;
            var result=Call(request);
            Check(CommandRegistry.Calls==before+1,"native must execute exactly once");
            if(success) {
                Check((bool)result["success"] && JToken.DeepEquals(result["data"],JObject.FromObject(native)["data"]),"normal data must be retained without filtering/fabrication: "+result);
                Check(CandidateSession.Gate.LocalPlans().Count==1,"normal read keeps plan");
            } else {
                var expected=JObject.FromObject(new ErrorResponse("native_read_failed",new JObject{["status"]="denied",["reason"]="native_read_failed",["read_only"]=true}));
                Check(JToken.DeepEquals(result,expected),"only fixed structured error allowed: "+result);
                Check(!result.ToString().Contains(Marker),"exception leak");
                Check(CandidateSession.Gate.LocalPlans().Count==0,"failure revokes");
                Check(!(bool)Call(request)["success"] && CommandRegistry.Calls==before+1,"failure cannot retry old plan");
            }
            Console.WriteLine("PASS "+id);
        } catch(Exception e) { failures++; Console.WriteLine("FAIL "+id+" "+e.Message); }
    }
    static JObject Material(string type="Float", JToken value=null) => new JObject {
        ["material"]="fixture material",["shader"]="fixture shader",["properties"]=new JArray(new JObject {
            ["name"]="_Fixture",["type"]=type,["description"]="fixture description",["value"]=value??JValue.CreateNull()})};
    // Exact ControllerCreate.GetInfo output structure, including nullable motion/exit destination.
    static JObject Controller() => JObject.Parse(@"{'path':'Assets/Read.controller','name':'fixture controller','layerCount':1,'parameterCount':1,
        'layers':[{'index':0,'name':'Base Layer','stateCount':1,'states':[{'name':'Idle','speed':1.0,'hasMotion':false,'motionName':null,'isDefault':true,'transitionCount':1,
        'transitions':[{'destinationState':null,'hasExitTime':true,'exitTime':0.5,'duration':0.25,'conditionCount':1,'conditions':[{'parameter':'Speed','mode':'Greater','threshold':0.1}]}]}]}],
        'parameters':[{'name':'Speed','type':'Float','defaultFloat':0.0,'defaultInt':0,'defaultBool':false}]}");
    static object ChangedController(Action<JObject> change) { var data=Controller();change(data);return new {success=true,data}; }
    static void SuccessContracts()
    {
        Case("UF005_material_float_exception_revokes",()=>new SuccessResponse("fixture",Material("Float","<error: "+Marker+">")));
        Case("UF006_material_texenv_exception_revokes",()=>new SuccessResponse("fixture",Material("TexEnv","<error: "+Marker+">")));
        Case("UF007_material_texture_exception_revokes",()=>new SuccessResponse("fixture",Material("Texture","<error: "+Marker+">")));
        Case("UF008_unknown_success_shape_denied",()=>new SuccessResponse("fixture",new{fixture_only=true}));
        Case("UF009_unknown_material_type_denied",()=>new SuccessResponse("fixture",Material("Unknown",null)));
        Case("UF010_material_extra_error_field_denied",()=> {var d=Material("Float",1);d["stackTrace"]=Marker;return new SuccessResponse("fixture",d);});
        Case("UF011_material_value_extra_field_denied",()=>new SuccessResponse("fixture",Material("Color",JObject.Parse("{'r':1,'g':1,'b':1,'a':1,'exception':'private'}"))));
        Case("UF012_controller_nested_error_denied",()=>ChangedController(d=>d["layers"][0]["states"][0]["transitions"][0]["conditions"][0]["stackTrace"]=Marker),false,"manage_animation");
        Case("UF013_controller_unknown_shape_denied",()=>new {success=true,data=new{fixture_only=true}},false,"manage_animation");
        Case("UF014_controller_count_mismatch_denied",()=>ChangedController(d=>d["layerCount"]=2),false,"manage_animation");
        Case("UF015_controller_wrong_primitive_denied",()=>ChangedController(d=>d["parameters"][0]["defaultBool"]="true"),false,"manage_animation");
        Case("UF016_unknown_success_envelope_denied",()=>new {success=true,data=Material("Float",1),error=Marker});
        foreach(string type in new[]{"Float","Range","Color","Vector","TexEnv","Texture","Int"}) {
            JToken value=type=="Color"?JObject.Parse("{'r':0.1,'g':0.2,'b':0.3,'a':1}"):
                type=="Vector"?JObject.Parse("{'x':1,'y':2,'z':3,'w':4}"):
                type=="Float"||type=="Range"?new JValue(0.25):
                type=="Int"?JValue.CreateNull():new JValue("fixture texture");
            Case("UF017_material_normal_"+type,()=>new SuccessResponse("fixture",Material(type,value)),true);
            Case("UF018_material_absent_property_"+type,()=>new SuccessResponse("fixture",Material(type,null)),true);
        }
        Case("UF019_material_empty_properties",()=>new SuccessResponse("fixture",new {material="fixture",shader="fixture",properties=new object[0]}),true);
        Case("UF020_controller_normal_nested_preserved",()=>new {success=true,data=Controller()},true,"manage_animation");
        Case("UF021_controller_empty_preserved",()=>ChangedController(d=>{d["layers"]=new JArray();d["parameters"]=new JArray();d["layerCount"]=0;d["parameterCount"]=0;}),true,"manage_animation");
        Case("UF022_controller_named_motion_preserved",()=>ChangedController(d=>{d["layers"][0]["states"][0]["motionName"]="clip";d["layers"][0]["states"][0]["hasMotion"]=true;d["layers"][0]["states"][0]["transitions"][0]["destinationState"]="Next";}),true,"manage_animation");
    }
    static int Main(string[] args)
    {
        string directory=Path.Combine(Path.GetTempPath(),"vragent-unity-fix-"+Guid.NewGuid().ToString("N"));
        try {
            Directory.CreateDirectory(Path.Combine(directory,"Assets")); Application.dataPath=Path.Combine(directory,"Assets");
            foreach(string asset in new[]{"Read.mat","Read.controller"}) {
                File.WriteAllText(Path.Combine(Application.dataPath,asset),"fixture disk");
                File.WriteAllText(Path.Combine(Application.dataPath,asset+".meta"),"fixture meta");
            }
            AdapterOwnedFixture.Begin();
            Case("UF002_error_response_safe",()=>new ErrorResponse(Marker,new {stackTrace=Marker}));
            Case("UF003_animation_message_failure_safe",()=>new {success=false,message=Marker},false,"manage_animation");
            Case("UF004_error_fields_not_trusted",()=>new {success=false,error=Marker,code=Marker,data=new{nested=new{message=Marker}}});
            SuccessContracts();
            return failures==0?0:1;
        } finally {
            CandidateSession.Gate.StopAll("fix fixture cleanup");
            if(Directory.Exists(directory))Directory.Delete(directory,true);
            Console.WriteLine("cleanup_fixture_removed="+!Directory.Exists(directory));
        }
    }
}
