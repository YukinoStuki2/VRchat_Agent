// Real candidate gate; Unity identity/evidence/native operation remain fixtures.
using System;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class LifecycleCases
{
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static JObject Wire(string kind, string client, string task, string id) => new JObject {
        ["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]=client,
        ["connection_id"]="fixture-connection",["task_id"]=task,["plan_id"]=id,["body"]=new JObject() };
    static CandidateGate Gate() {
        var gate = new CandidateGate(()=>1,()=>"fixture-project",()=>"fixture-connection",p=>"fixture-evidence",
            (c,p)=>new JObject {["success"]=true,["data"]=new JObject()});
        gate.SetCapability("manage_material","get_material_info",true); return gate;
    }
    static JObject Prepare(CandidateGate gate, string client, string task) {
        var r=Wire("prepare",client,task,"");
        r["body"]=JObject.Parse("{\"operations\":[{\"command\":\"manage_material\",\"action\":\"get_material_info\"}],\"targets\":[\"Assets/Read.mat\"],\"ttl_seconds\":60}");
        var result=gate.Dispatch(r); Check((bool)result["success"],"fixture prepare"); return (JObject)result["data"];
    }
    static void Main() {
        var gate=Gate(); var old=Prepare(gate,"client-A","task-A"); var current=Prepare(gate,"client-A","task-A");
        var denied=gate.Dispatch(Wire("stop","client-A","task-A",(string)old["plan_id"]));
        Check((bool)denied["success"]==false,"stale stop must not succeed");
        Check(gate.LocalPlans().Count==1 && (string)gate.LocalPlans()[0]["plan_id"]==(string)current["plan_id"],
            "stale stop removed a replacement plan");
        Console.WriteLine("PASS CLC001 stale stop cannot remove replacement plan");
        gate=Gate(); var a=Prepare(gate,"client-A","task-A"); var b=Prepare(gate,"client-B","task-B");
        var stopped=gate.Dispatch(Wire("stop","client-A","task-A",(string)a["plan_id"]));
        Check((bool)stopped["success"] && (string)stopped["data"]["status"]=="stopped","exact stop failed");
        Check(gate.LocalPlans().Count==1 && (string)gate.LocalPlans()[0]["plan_id"]==(string)b["plan_id"],
            "exact stop affected a different client's plan");
        Check((bool)gate.Dispatch(Wire("stop","client-A","task-A",(string)a["plan_id"]))["success"]==false,
            "duplicate stop cannot claim a second revocation");
        Check(gate.LocalPlans().Count==1,"duplicate stop affected another client");
        Console.WriteLine("PASS CLC002 exact stop isolates clients and duplicate cleanup");
    }
}
