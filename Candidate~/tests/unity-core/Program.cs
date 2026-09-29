using System;
using System.Reflection;
using Newtonsoft.Json.Linq;

internal static class Program
{
    internal static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    static int Main()
    {
        try
        {
            var type = Assembly.GetExecutingAssembly().GetType("Yukino.VRChatAgent.CandidateGate");
            Check(type != null, "UC001: Unity final gate is not implemented");
            double now = 10; string connection = "connection-A"; int nativeCalls = 0;
            Func<double> clock = () => now;
            Func<string> project = () => "project-A";
            Func<string> session = () => connection;
            Func<string, string> evidence = p => "fixture-evidence-" + p;
            Func<string, JObject, JObject> native = (command, args) => { nativeCalls++; return new JObject { ["success"] = true, ["data"] = new JObject { ["fixture_only"] = true } }; };
            dynamic gate = Activator.CreateInstance(type, clock, project, session, evidence, native);
            JObject prepare = Wire("prepare", "");
            prepare["body"] = JObject.Parse("{\"operations\":[{\"command\":\"manage_material\",\"action\":\"get_material_info\"}],\"targets\":[\"Assets/Read.mat\"],\"ttl_seconds\":60}");
            Check(!(bool)((JObject)gate.Dispatch(prepare))["success"], "default must be closed");
            gate.SetCapability("manage_material", "get_material_info", true);
            JObject pending = gate.Dispatch(prepare);
            Check((bool)pending["success"], "local read capability allows prepare");
            string id = (string)pending["data"]["plan_id"];
            string digest = (string)pending["data"]["digest"];
            JObject execute = Wire("execute", id);
            execute["body"] = JObject.Parse("{\"command\":\"manage_material\",\"params\":{\"action\":\"get_material_info\",\"materialPath\":\"Assets/Read.mat\"}}");
            // Do not execute while pending: a failed native request closes this plan.
            Check(nativeCalls == 0 && (string)pending["data"]["status"] == "pending", "prepare must not execute or approve");
            Check((bool)gate.Approve(id, digest), "exact local plan approval");
            Check((bool)((JObject)gate.Dispatch(execute))["success"] && nativeCalls == 1, "read must invoke native once");
            gate.Dispatch(Wire("stop", id));
            Check(!(bool)((JObject)gate.Dispatch(execute))["success"] && nativeCalls == 1, "stop must prevent reuse");
            Console.WriteLine("PASS UC001 local prepare -> exact local approve -> native read -> stop");
            CoreCases.Run();
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine("FAIL " + e); return 1; }
    }
    internal static JObject Wire(string kind, string plan) => new JObject {
        ["protocol"] = 1, ["kind"] = kind, ["project_id"] = "project-A", ["client_id"] = "client-A",
        ["connection_id"] = "connection-A", ["task_id"] = "task-A", ["plan_id"] = plan, ["body"] = new JObject() };
}
