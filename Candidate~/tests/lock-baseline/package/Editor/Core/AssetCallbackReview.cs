using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Local-only review bookkeeping. A trusted, no-load context collector and a
    // reviewer supply the facts; this class does not assess arbitrary code safety.
    // A digest identifies a record, not a signer. Nothing here enables a capability
    // or approves a task, and neither StageLocal nor ConfirmLocal is an MCP tool.
    internal sealed class AssetCallbackReview
    {
        readonly Func<JObject> current;
        readonly Func<DateTimeOffset> utc;
        readonly Func<double> monotonic;
        readonly Action invalidated;
        JObject pending,accepted;
        string pendingDigest,acceptedDigest;
        long generation;
        double deadline,lastMonotonic=double.MinValue;
        DateTimeOffset lastUtc=DateTimeOffset.MinValue;
        bool ObserveClock()
        {
            double tick=monotonic();var stamp=utc();
            if(double.IsNaN(tick) || double.IsInfinity(tick) || tick<0 || tick<lastMonotonic || stamp<lastUtc){Revoke();return false;}
            lastMonotonic=tick;lastUtc=stamp;return true;
        }
        internal AssetCallbackReview(Func<JObject> current,Func<DateTimeOffset> utc,Func<double> monotonic,Action invalidated)
        { this.current=current;this.utc=utc;this.monotonic=monotonic;this.invalidated=invalidated; }
        static string Digest(JObject value)
        { using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value.ToString(Formatting.None)))).Replace("-","").ToLowerInvariant(); }
        static bool Keys(JObject value,params string[] names)=>value!=null && value.Count==names.Length && names.All(value.ContainsKey);
        static bool Text(JToken value)=>value?.Type==JTokenType.String && ((string)value).Length>0 && ((string)value).Length<=512 && !((string)value).Any(char.IsControl) && (string)value==((string)value).Trim();
        static bool Hash(JToken value)=>value?.Type==JTokenType.String && Regex.IsMatch((string)value,@"\A[a-f0-9]{64}\z");
        static bool Hashes(JToken value,bool nonempty)=>value is JObject map && map.Count<=1024 && (!nonempty || map.Count>0) && map.Properties().All(p=>Text(new JValue(p.Name)) && Hash(p.Value));
        static bool Context(JObject value)=>Keys(value,"project_id","editor","candidate_sha256","code","dependencies","callbacks","complete") &&
            Text(value["project_id"]) && Text(value["editor"]) && Hash(value["candidate_sha256"]) && Hashes(value["code"],true) && Hashes(value["dependencies"],false) &&
            value["complete"]?.Type==JTokenType.Boolean && (bool)value["complete"] && value["callbacks"] is JArray ids && ids.Count<=1024 && ids.All(Text) && ids.Select(x=>(string)x).Distinct(StringComparer.Ordinal).Count()==ids.Count;
        static DateTimeOffset Stamp(JToken value)
        {
            if(value?.Type!=JTokenType.String || !DateTimeOffset.TryParseExact((string)value,"O",CultureInfo.InvariantCulture,DateTimeStyles.None,out var stamp) || stamp.Offset!=TimeSpan.Zero)throw new InvalidDataException();
            return stamp;
        }
        bool Matches(JObject record)
        {
            if(!Keys(record,"schema","purpose","target","reviewer","reviewed_at_utc","expires_at_utc","conclusion","unassessed_callbacks","context"))return false;
            var context=record["context"] as JObject;var actual=current();var now=utc();
            return record["schema"]?.Type==JTokenType.Integer && (int)record["schema"]==1 &&
                record["purpose"]?.Type==JTokenType.String && (string)record["purpose"]=="asset_load_callbacks" &&
                record["conclusion"]?.Type==JTokenType.String && (string)record["conclusion"]=="reviewed" && Text(record["reviewer"]) &&
                record["target"]?.Type==JTokenType.String && CandidateGate.AssetTarget((string)record["target"]) &&
                Context(context) && Context(actual) && record["unassessed_callbacks"] is JArray missing && missing.Count==0 &&
                JToken.DeepEquals(context,actual) && Stamp(record["reviewed_at_utc"])<=now && Stamp(record["expires_at_utc"])>now;
        }
        static JObject Parse(string json)
        {
            using(var input=new StringReader(json))using(var reader=new JsonTextReader(input){DateParseHandling=DateParseHandling.None,MaxDepth=16})
            {
                var record=JObject.Load(reader,new JsonLoadSettings{DuplicatePropertyNameHandling=DuplicatePropertyNameHandling.Error});
                if(reader.Read())throw new InvalidDataException();return record;
            }
        }
        internal void Revoke()
        {
            generation++;pending=null;accepted=null;pendingDigest=null;acceptedDigest=null;deadline=0;
            invalidated?.Invoke();
        }
        // Trusted local capture only. The caller owns stable file reading and its
        // time/process budget; a completed capture is data, never consent.
        internal string StageCapturedLocal(Func<byte[]> capture)
        {
            try
            {
                Revoke();long started=generation;
                byte[] data=capture?.Invoke();
                if(generation!=started || data==null || data.Length==0 || data.Length>262144 ||
                    (data.Length>=3 && data[0]==0xef && data[1]==0xbb && data[2]==0xbf)){Revoke();return null;}
                return StageLocal(new UTF8Encoding(false,true).GetString(data));
            }
            catch { Revoke();return null; }
        }
        // Editor-thread caller and continuation only, not arbitrary-thread safety.
        // Capture owns cancellation/time/process cleanup; late bytes confer no grant.
        internal async System.Threading.Tasks.Task<string> StageCapturedLocalAsync(Func<System.Threading.Tasks.Task<byte[]>> capture)
        {
            try
            {
                Revoke();long started=generation;
                byte[] data=await capture();
                if(generation!=started){Revoke();return null;}
                return StageCapturedLocal(()=>data);
            }
            catch { Revoke();return null; }
        }
        internal string StageLocal(string json)
        {
            try
            {
                Revoke();long started=generation;
                if(json==null || Encoding.UTF8.GetByteCount(json)>262144)return null;
                var record=Parse(json);
                if(!ObserveClock() || !Matches(record) || !ObserveClock() || generation!=started){Revoke();return null;}
                pending=(JObject)record.DeepClone();pendingDigest=Digest(pending);
                deadline=lastMonotonic+(Stamp(record["expires_at_utc"])-lastUtc).TotalSeconds;
                if(double.IsInfinity(deadline) || !(deadline>lastMonotonic)){Revoke();return null;}
                return pendingDigest;
            }
            catch { Revoke();return null; }
        }
        internal bool ConfirmLocal(string digest)
        {
            try
            {
                long started=generation;var expected=pending;
                if(pending==null || digest!=pendingDigest || !ObserveClock() || !(lastMonotonic<deadline) || !Matches(expected) || !ObserveClock() || !(lastMonotonic<deadline) || generation!=started || !ReferenceEquals(expected,pending)) { Revoke();return false; }
                accepted=pending;acceptedDigest=pendingDigest;pending=null;pendingDigest=null;return true;
            }
            catch { Revoke();return false; }
        }
        internal string Evidence(string target)
        {
            try
            {
                var expected=accepted;long started=generation;
                if(expected==null)return null;
                if(!ObserveClock() || !(lastMonotonic<deadline) || !Matches(expected) || !ObserveClock() || !(lastMonotonic<deadline) || generation!=started || !ReferenceEquals(expected,accepted)){Revoke();return null;}
                return (string)accepted["target"]==target ? acceptedDigest : null;
            }
            catch { Revoke();return null; }
        }
    }
}
