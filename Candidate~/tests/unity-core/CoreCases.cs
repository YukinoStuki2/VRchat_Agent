using System;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;

internal static class CoreCases
{
    sealed class Fixture
    {
        internal double Time = 100;
        internal string Connection = "connection-A", Project = "project-A", Revision = "disk+memory-A";
        internal int Calls;
        internal Action OnEvidence, OnNative;
        internal bool NativeSuccess = true;
        internal readonly CandidateGate Gate;
        internal Fixture()
        {
            Gate = new CandidateGate(() => Time, () => Project, () => Connection,
                p => { OnEvidence?.Invoke(); return Revision + p; },
                (c, p) => { Calls++; OnNative?.Invoke(); return new JObject { ["success"] = NativeSuccess,
                    ["error"] = NativeSuccess ? null : "fixture_failure", ["data"] = new JObject { ["fixture_only"] = true } }; });
            Gate.SetCapability("manage_material", "get_material_info", true);
        }
        internal JObject Prepare()
        {
            var r = Program.Wire("prepare", "");
            r["body"] = JObject.Parse("{\"operations\":[{\"command\":\"manage_material\",\"action\":\"get_material_info\"}],\"targets\":[\"Assets/Read.mat\"],\"ttl_seconds\":60}");
            return Gate.Dispatch(r);
        }
        internal JObject Ready()
        {
            var p = Prepare(); Program.Check((bool)p["success"], "prepare");
            Program.Check(Gate.Approve((string)p["data"]["plan_id"], (string)p["data"]["digest"]), "approve");
            return p;
        }
        internal JObject Execute(JObject p)
        {
            var r = Program.Wire("execute", (string)p["data"]["plan_id"]);
            r["body"] = JObject.Parse("{\"command\":\"manage_material\",\"params\":{\"action\":\"get_material_info\",\"materialPath\":\"Assets/Read.mat\"}}");
            return Gate.Dispatch(r);
        }
    }
    static void Test(string id, Action test) { test(); Console.WriteLine("PASS " + id); }
    static void Denied(JObject result) { Program.Check((bool)result["success"] == false, "must deny: " + result); }
    internal static void Run()
    {
        Test("UC015 console local capability exact approval and native get", () => {
            int calls=0;
            var gate=new CandidateGate(()=>100,()=>"project-A",()=>"connection-A",p=>"bound-scope:"+p,
                (command,args)=>{calls++;Program.Check(command=="read_console" && (string)args["action"]=="get","wrong native route");
                    return new JObject{["success"]=true,["data"]=new JObject()};});
            var prepare=Program.Wire("prepare","");
            prepare["body"]=JObject.Parse("{\"operations\":[{\"command\":\"read_console\",\"action\":\"get\"}],\"targets\":[\"Console\"],\"ttl_seconds\":60}");
            Denied(gate.Dispatch(prepare));
            bool supported=true;try{gate.SetCapability("read_console","get",true);}catch{supported=false;}
            Program.Check(supported,"UC015 console capability missing");
            var p=gate.Dispatch(prepare);Program.Check((bool)p["success"],"console prepare");
            var execute=Program.Wire("execute",(string)p["data"]["plan_id"]);
            execute["body"]=JObject.Parse("{\"command\":\"read_console\",\"params\":{\"action\":\"get\",\"types\":[\"error\",\"warning\",\"log\"],\"count\":10,\"pageSize\":20,\"cursor\":0,\"format\":\"json\",\"includeStacktrace\":true}}");
            Program.Check(calls==0,"prepare executed native read");
            Program.Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"console approve");
            Program.Check((bool)gate.Dispatch(execute)["success"] && calls==1,"console native read");
            gate.StopAll("explicit stop");Denied(gate.Dispatch(execute));Program.Check(calls==1,"reuse after stop");
        });
        Test("UC002 pending cannot execute or approve itself", () => {
            var f = new Fixture(); var p = f.Prepare(); Denied(f.Execute(p));
            Program.Check(f.Calls == 0 && !f.Gate.Approve((string)p["data"]["plan_id"], (string)p["data"]["digest"]), "failed request clears plan"); });
        Test("UC003 stale UI digest denies", () => { var f = new Fixture(); var p = f.Prepare(); Program.Check(!f.Gate.Approve((string)p["data"]["plan_id"], "stale"), "digest must bind"); Denied(f.Execute(p)); });
        Test("UC004 expire before dispatch", () => { var f = new Fixture(); var p = f.Ready(); f.Time += 60; Denied(f.Execute(p)); Program.Check(f.Calls == 0, "expired call"); });
        Test("UC005 relevant evidence change stops", () => { var f = new Fixture(); var p = f.Ready(); f.Revision = "disk+memory-B"; Denied(f.Execute(p)); Program.Check(f.Calls == 0, "changed evidence call"); });
        Test("UC006 local capability revoke does not restore", () => { var f = new Fixture(); var p = f.Ready(); f.Gate.SetCapability("manage_material", "get_material_info", false); f.Gate.SetCapability("manage_material", "get_material_info", true); Denied(f.Execute(p)); Program.Check(f.Calls == 0, "regrant old plan"); });
        Test("UC007 connection changes even if changed back", () => { var f = new Fixture(); var p = f.Ready(); f.Connection = "connection-B"; f.Gate.Observe(); f.Connection = "connection-A"; Denied(f.Execute(p)); Program.Check(f.Calls == 0, "old connection grant"); });
        Test("UC008 display snapshot is detached", () => { var f = new Fixture(); var p = f.Ready(); var display = f.Gate.LocalPlans(); display[0]["manifest"]["targets"][0] = "Assets/Other.mat"; Program.Check((bool)f.Execute(p)["success"], "UI display must not mutate plan"); });
        Test("UC009 native failure closes plan", () => { var f = new Fixture(); var p = f.Ready(); f.NativeSuccess = false; Denied(f.Execute(p)); f.NativeSuccess = true; Denied(f.Execute(p)); Program.Check(f.Calls == 1, "retry after failure"); });
        Test("UC010 revoke during native read preserved", () => { var f = new Fixture(); var p = f.Ready(); f.OnNative = () => f.Gate.StopAll("fixture-stop"); Denied(f.Execute(p)); Program.Check(f.Gate.LocalPlans().Count == 0, "callback stop restored"); });
        Test("UC011 unknown write and reserved keys denied", () => { var f = new Fixture(); var p = f.Ready(); var r = Program.Wire("execute", (string)p["data"]["plan_id"]); r["body"] = JObject.Parse("{\"command\":\"manage_material\",\"params\":{\"action\":\"set_material_color\",\"materialPath\":\"Assets/Read.mat\",\"approved\":true}}"); Denied(f.Gate.Dispatch(r)); Program.Check(f.Calls == 0, "unknown write"); });
        Test("UC012 stop during prepare evidence cannot restore pending", () => { var f = new Fixture(); f.OnEvidence = () => f.Gate.StopAll("fixture-stop"); Denied(f.Prepare()); Program.Check(f.Gate.LocalPlans().Count == 0, "stop restored pending"); });
        Test("UC013 native exception text never leaks", () => { var f = new Fixture(); var p = f.Ready(); f.OnNative = () => { throw new InvalidOperationException("fixture-private-value"); }; var denied = f.Execute(p); Denied(denied); Program.Check(!denied.ToString().Contains("fixture-private-value"), "native exception leaked"); });
        Test("UC014 prepare rejects target incompatible with allowed operation", () => { var f = new Fixture(); var r=Program.Wire("prepare", "");r["body"]=JObject.Parse("{\"operations\":[{\"command\":\"manage_material\",\"action\":\"get_material_info\"}],\"targets\":[\"Assets/Read.controller\"],\"ttl_seconds\":60}");Denied(f.Gate.Dispatch(r)); });
    }
}
