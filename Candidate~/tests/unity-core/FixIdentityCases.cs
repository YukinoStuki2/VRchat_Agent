// Real pinned internal identity in a separate assembly; no friend name or source transplant.
using System;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using MCPForUnity.Editor.Tools;
using UnityEngine;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class FixIdentityCases
{
    static int Main(string[] args)
    {
        try {
            Application.dataPath = args[0]; // String-only fixture, never accesses this path.
            var upstream = typeof(CommandRegistry).Assembly;
            var identity = upstream.GetType("MCPForUnity.Editor.Helpers.ProjectIdentityUtility", true);
            if (identity.IsPublic || upstream == typeof(CandidateGate).Assembly) throw new Exception("visibility/assembly boundary lost");
            var bridge = typeof(CandidateGate).Assembly.GetType("Yukino.VRChatAgent.CoplayProjectIdentity");
            if (bridge == null || !bridge.IsPublic) throw new Exception("UF001 explicit public identity bridge missing");
            string actual = (string)bridge.GetMethod("GetProjectHash").Invoke(null, null);
            string upstreamValue = (string)identity.GetMethod("GetProjectHash").Invoke(null, null);
            string expected;
            using(var sha = SHA1.Create()) expected=BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(args[0]))).Replace("-", "").ToLowerInvariant().Substring(0,16);
            if (actual != upstreamValue || actual != expected) throw new Exception("identity mismatch");
            var project = actual;
            AdapterOwnedFixture.Begin("fixture-connection");
            var request = new JObject { ["protocol"]=1,["kind"]="status",["project_id"]=project,["connection_id"]="fixture-connection",
                ["client_id"]="fixture-client",["task_id"]="",["plan_id"]="",["body"]=new JObject() };
            var status=JObject.FromObject(AdapterOwnedFixture.Call(request));
            if(!(bool)status["success"])throw new Exception("actual gate project binding mismatch");
            request["project_id"]="wrong-fixture-project";
            if((bool)JObject.FromObject(AdapterOwnedFixture.Call(request))["success"])throw new Exception("wrong project accepted");
            var window=new CandidateWindow();
            typeof(CandidateWindow).GetMethod("OnGUI",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(window,null);
            if(!UnityEditor.EditorGUILayout.Labels.Contains("当前工程:"+actual))throw new Exception("UI identity mismatch");
            Console.WriteLine("PASS UF001 same real upstream hash: " + actual + "; assembly=" + upstream.GetName().Name);
            Console.WriteLine("PASS UF023 real identity gate binding and UI agree; wrong project refused");
            return 0;
        } catch(Exception e) { Console.Error.WriteLine("FAIL UF001 " + e); return 1; }
    }
}
