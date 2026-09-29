// Characterization of unsupported upstream: no identity getter exists in this fixture.
using System;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class FixIdentityAbsent
{
    static int Main()
    {
        if(CoplayProjectIdentity.GetProjectHash()!="")throw new Exception("must not invent identity");
        var request=new JObject { ["protocol"]=1,["kind"]="status",["project_id"]="invented-project",["connection_id"]="fixture-connection",
            ["client_id"]="fixture-client",["task_id"]="",["plan_id"]="",["body"]=new JObject() };
        var result=JObject.FromObject(VrchatAgentDispatch.HandleCommand(request));
        if((bool)result["success"])throw new Exception("missing identity accepted");
        Console.WriteLine("PASS UF024 missing upstream getter fails closed, no synthesized hash");
        return 0;
    }
}
