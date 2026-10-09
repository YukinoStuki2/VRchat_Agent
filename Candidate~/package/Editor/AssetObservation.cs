using System;
using System.IO;
using System.Text;
using System.Linq;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Product-owned policy/receipt adapter. The caller must supply the dedicated
    // pinned reader, never the mixed-action native registry. No review/approval here.
    internal static class AssetObservation
    {
        static JObject Failure(bool attempted) => new JObject {
            ["success"]=false,["error"]="asset_read_unconfirmed",
            ["data"]=new JObject { ["read_only"]=false,["effects_may_have_occurred"]=attempted }
        };
        static bool Keys(JObject value, params string[] names) => value!=null && value.Count==names.Length && names.All(value.ContainsKey);
        static bool Text(JToken value,int max=512) => value?.Type==JTokenType.String && ((string)value).Length>0 && ((string)value).Length<=max && !((string)value).Any(char.IsControl);
        static bool Integer(JToken value,long min,long max) => value?.Type==JTokenType.Integer && (decimal)value>=min && (decimal)value<=max;
        static bool Row(JToken token,string scope,bool exact)
        {
            var row=token as JObject;
            if(!Keys(row,"path","guid","assetType","name","fileName","isFolder","instanceID","lastWriteTimeUtc","previewBase64","previewWidth","previewHeight")) return false;
            string path=(string)row["path"];
            return row["path"].Type==JTokenType.String && CandidateGate.AssetPath(path) && (exact ? path==scope : path.StartsWith(scope+"/",StringComparison.Ordinal)) &&
                Text(row["guid"],32) && Regex.IsMatch((string)row["guid"],@"\A[a-f0-9]{32}\z") && Text(row["assetType"]) && (string)row["assetType"]!="Unknown" &&
                Text(row["name"]) && (string)row["name"]==Path.GetFileNameWithoutExtension(path) && Text(row["fileName"]) && (string)row["fileName"]==Path.GetFileName(path) &&
                row["isFolder"].Type==JTokenType.Boolean && Integer(row["instanceID"],int.MinValue,int.MaxValue) && (int)row["instanceID"]!=0 &&
                Text(row["lastWriteTimeUtc"],64) && DateTimeOffset.TryParse((string)row["lastWriteTimeUtc"],CultureInfo.InvariantCulture,DateTimeStyles.None,out _) &&
                row["previewBase64"].Type==JTokenType.Null && Integer(row["previewWidth"],0,0) && Integer(row["previewHeight"],0,0);
        }
        static bool Valid(JObject data,JObject args)
        {
            string scope=(string)args["path"];
            if((string)args["action"]=="get_info") return Row(data,scope,true);
            if(!Keys(data,"totalAssets","pageSize","pageNumber","assets") || !Integer(data["totalAssets"],0,4096) ||
                !JToken.DeepEquals(data["pageSize"],args["pageSize"]) || !JToken.DeepEquals(data["pageNumber"],args["pageNumber"]) ||
                !(data["assets"] is JArray rows)) return false;
            long total=(long)data["totalAssets"],page=(long)args["pageNumber"],size=(long)args["pageSize"];
            if(rows.Count!=Math.Min(size,Math.Max(0,total-(page-1)*size))) return false;
            var paths=new HashSet<string>(StringComparer.OrdinalIgnoreCase);var guids=new HashSet<string>(StringComparer.Ordinal);
            return rows.All(row=>Row(row,scope,false) && paths.Add((string)row["path"]) && guids.Add((string)row["guid"]));
        }
        internal static JObject Read(JObject args, Func<bool> authorized, Func<JObject,Func<bool>,object> reader)
        {
            bool attempted=false;
            try
            {
                CandidateGate.AssetParams(args);
                if(authorized==null || reader==null || !authorized()) return Failure(false);
                attempted=true;
                object raw=reader((JObject)args.DeepClone(),authorized);
                var result=raw as JObject ?? (raw==null ? null : JObject.FromObject(raw));
                if(result==null || result["success"]?.Type!=JTokenType.Boolean || !(bool)result["success"] ||
                    !(result["data"] is JObject data) || !Valid(data,args) || !authorized() ||
                    Encoding.UTF8.GetByteCount(result.ToString(Formatting.None))>262144)
                    return Failure(true);
                data=(JObject)data.DeepClone();
                data["candidate_effects"]=new JObject {
                    ["kind"]="asset_load_callbacks",["version"]=1,["read_only"]=false,
                    ["all_mutations_observed"]=false,["callback_effects_path_bounded"]=false,
                    ["observed_at_utc"]=DateTimeOffset.UtcNow.ToString("O"),
                    ["pagination_consistency"]="live_not_snapshot"
                };
                return new JObject { ["success"]=true,["data"]=data };
            }
            catch { return Failure(attempted); }
        }
    }
}
