using System;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;

namespace Yukino.VRChatAgent
{
    // Policy/receipt adapter only. The fixed native command owns every job read
    // and maintenance operation. Call only after CandidateGate's explicit grant.
    internal static class JobObservation
    {
        const string Store = "MCPForUnity.TestJobsV1";
        const string Current = "MCPForUnity.CurrentTestJobIdV1";
        const string TimeoutError = "Test job failed to initialize (tests did not start within timeout)";
        static JObject State()
        {
            string raw = SessionState.GetString(Store, "");
            if (string.IsNullOrEmpty(raw)) return null;
            if (Encoding.UTF8.GetByteCount(raw) > 262144) throw new IOException("job_state_budget");
            using var reader = new JsonTextReader(new StringReader(raw)) { MaxDepth = 16 };
            var state = JObject.Load(reader);
            if (reader.Read() || !(state["jobs"] is JArray jobs) || jobs.Count > 128)
                throw new IOException("job_state_invalid");
            return state;
        }
        internal static JObject Read(JObject args)
        {
            CandidateGate.JobParams(args); // No alternate caller can smuggle wait/run.
            State(); // Bounded SessionState read does NOT initialize native manager.
            object raw = MCPForUnity.Editor.Tools.GetTestJob.HandleCommand(args);
            JObject result = raw as JObject ?? JObject.FromObject(raw);
            if ((bool?)result["success"] != true) return result;
            var data = result["data"] as JObject;
            if (data == null || (string)data["job_id"] != (string)args["job_id"] ||
                !new[] { "running", "succeeded", "failed" }.Contains((string)data["status"]) ||
                Encoding.UTF8.GetByteCount(result.ToString(Formatting.None)) > 262144)
                throw new IOException("job_result_invalid");
            string receipt = "not_claimed";
            if ((string)data["error"] == TimeoutError)
            {
                // Native force-persist errors are swallowed. Re-read EXACT native
                // storage and compare target fields; never treat success as receipt.
                var state = State();
                var jobs = state?["jobs"] as JArray;
                var saved = jobs?.OfType<JObject>().SingleOrDefault(x => (string)x["job_id"] == (string)args["job_id"]);
                string[] fields = { "job_id", "status", "started_unix_ms", "finished_unix_ms", "last_update_unix_ms", "error" };
                if (saved == null || jobs.Count > 10 || fields.Any(k => !data.ContainsKey(k) || !JToken.DeepEquals(saved[k], data[k])) ||
                    (string)state["current_job_id"] == (string)args["job_id"] ||
                    ((string)state["current_job_id"] ?? "") != SessionState.GetString(Current, ""))
                    throw new IOException("job_persistence_unconfirmed");
                receipt = "target_timeout_state_confirmed";
            }
            data["candidate_effects"] = new JObject {
                ["kind"] = "project_test_job_maintenance", ["version"] = 1,
                ["project_wide"] = true, ["read_only"] = false,
                ["persistence"] = receipt, ["all_mutations_observed"] = false,
                ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O")
            };
            return result;
        }
    }
}
