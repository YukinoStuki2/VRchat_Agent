using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Strict in-memory transfer envelope shared by the two local gates. A caller
    // must authenticate the surviving owner BEFORE supplying expectedDigest.
    // This utility provides integrity/shape checks, never caller authentication.
    internal static class ReloadTransfer
    {
        internal static string Hash(JToken value)
        { using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(value.ToString(Formatting.None)))).Replace("-","").ToLowerInvariant(); }
        internal static double Number(JToken token)
        {
            if(token==null || (token.Type!=JTokenType.Float && token.Type!=JTokenType.Integer))throw new InvalidOperationException();
            double value=(double)token;if(double.IsNaN(value)||double.IsInfinity(value))throw new InvalidOperationException();return value;
        }
        internal static void Window(string id,double window,double now)
        { if(!Guid.TryParseExact(id,"N",out _) || double.IsNaN(window)||double.IsInfinity(window)||window<=0||window>60||double.IsNaN(now)||double.IsInfinity(now))throw new InvalidOperationException(); }
        internal static JObject Create(string kind,string id,string project,string connection,double deadline,IEnumerable<string> capabilities,JArray plans)
        {
            if(double.IsNaN(deadline)||double.IsInfinity(deadline))throw new InvalidOperationException();
            var result=new JObject{["version"]=1,["gate"]=kind,["handoff_id"]=id,["project_id"]=project,["from_connection_id"]=connection,["deadline"]=deadline,
                ["capabilities"]=new JArray(capabilities.OrderBy(x=>x,StringComparer.Ordinal)),["plans"]=plans};
            if(Encoding.UTF8.GetByteCount(result.ToString(Formatting.None))>4*1024*1024)throw new InvalidOperationException();return result;
        }
        internal static JObject Validate(JObject input,string digest,string kind,string project,string newConnection,string liveConnection,double now)
        {
            if(input==null || Encoding.UTF8.GetByteCount(input.ToString(Formatting.None))>4*1024*1024 || Hash(input)!=digest)throw new InvalidOperationException();
            var t=(JObject)input.DeepClone();string[] keys={"version","gate","handoff_id","project_id","from_connection_id","deadline","capabilities","plans"};
            if(t.Count!=keys.Length || t.Properties().Any(p=>!keys.Contains(p.Name)) || t["version"]?.Type!=JTokenType.Integer || (int)t["version"]!=1 ||
                (string)t["gate"]!=kind || (string)t["project_id"]!=project || string.IsNullOrEmpty(newConnection) || newConnection!=liveConnection ||
                string.IsNullOrEmpty((string)t["from_connection_id"]) || newConnection==(string)t["from_connection_id"] ||
                !(t["capabilities"] is JArray caps) || caps.Count==0 || caps.Count>32 || caps.Any(x=>x.Type!=JTokenType.String) || caps.Select(x=>(string)x).Distinct().Count()!=caps.Count ||
                !(t["plans"] is JArray rows) || rows.Count==0 || rows.Count>128 || rows.Any(x=>!(x is JObject)))throw new InvalidOperationException();
            Window((string)t["handoff_id"],Number(t["deadline"])-now,now);return t;
        }
        internal static string Binding(JObject transfer,string connection)=>Hash(new JObject{["transfer"]=transfer.DeepClone(),["to_connection_id"]=connection});
    }
    // Denial-only Editor-session storage. No grants, import, reset or foreign-ticket clearing.
    // Native adapters run on the Editor thread; this is not a same-process sandbox.
    public sealed class EffectCleanupLedger
    {
        internal sealed class Lease
        { internal EffectCleanupLedger Owner; internal string Kind, Token; internal bool Closed; }
        static readonly object Sync = new object();
        static bool accessing;
        readonly Func<string,string> read;
        readonly Action<string,string> write;
        bool failed;
        public EffectCleanupLedger(Func<string,string> read, Action<string,string> write)
        { this.read=read??throw new ArgumentNullException(nameof(read));this.write=write??throw new ArgumentNullException(nameof(write)); }
        T Access<T>(Func<T> action)
        {
            lock(Sync)
            {
                if(accessing||failed)throw new InvalidOperationException("cleanup_store_unavailable");
                accessing=true;
                try{return action();}catch{failed=true;throw;}finally{accessing=false;}
            }
        }
        static void Kind(string kind)
        {if(kind!="discovery"&&kind!="prefab")throw new InvalidOperationException("cleanup_kind_invalid");}
        internal bool Blocked(string kind,Lease own=null)
        {
            try{return Access(()=>{Kind(kind);string value=read(kind);
                return own==null ? value!="" : own.Owner!=this||own.Closed||own.Kind!=kind||value!=own.Token;});}
            catch{return true;}
        }
        internal Lease Begin(string kind)
        {
            return Access(()=>{Kind(kind);if(read(kind)!="")throw new InvalidOperationException("cleanup_pending");
                var lease=new Lease{Owner=this,Kind=kind,Token=Guid.NewGuid().ToString("N")};
                write(kind,lease.Token);if(read(kind)!=lease.Token)throw new InvalidOperationException("cleanup_store_unconfirmed");return lease;});
        }
        internal bool Finish(Lease own)
        {
            try{return Access(()=>{
                if(own==null||own.Owner!=this||own.Closed||read(own.Kind)!=own.Token)throw new InvalidOperationException("cleanup_owner_changed");
                write(own.Kind,"");if(read(own.Kind)!="")throw new InvalidOperationException("cleanup_clear_unconfirmed");own.Closed=true;return true;});}
            catch{return false;}
        }
    }
    // Local policy core. Async discovery releases its lock while awaiting the owned reader.
    // Only Unity-local UI calls Approve/SetCapability.
    // This is the managed MCP boundary, not a local-admin or terminal sandbox.
    public sealed class CandidateGate
    {
        sealed class Plan
        {
            internal string Id, Digest, Client, Connection, Project, Task, ApprovalConnection, BindingDigest;
            internal double Expires;
            internal bool Approved, Paused;
            internal JObject Manifest;
            internal Dictionary<string, string> Evidence;
        }
        readonly Func<double> clock;
        readonly Func<string> project, connection;
        readonly Func<string, string> evidence;
        readonly Func<string, JObject, JObject> native;
        // Trusted local adapters only; evidence MUST NOT load assets. The product
        // uses explicit local project-plugin trust, not executing-code attestation.
        // Missing/unconfirmed trust denies. Other adapters may enforce stricter review.
        readonly Func<string, string> assetReview;
        readonly Func<JObject, Func<bool>, JObject> assetRead;
        readonly Func<string,string,string> prefabReview;
        readonly Func<JObject,Func<bool>,JObject> prefabRead;
        readonly Func<string,string> discoveryReview;
        readonly Func<JObject,Func<bool>,Task<JObject>> discoveryRead;
        readonly EffectCleanupLedger cleanup;
        EffectCleanupLedger.Lease discoveryLease,prefabLease;
        bool testDiscoveryCallbacks,discoveryCleanupUnconfirmed;
        public bool TestDiscoveryCleanupUnconfirmed { get {lock(sync)return discoveryCleanupUnconfirmed || cleanup==null || cleanup.Blocked("discovery");} }
        public bool TestDiscoveryCallbacksAllowed { get { lock(sync)return testDiscoveryCallbacks; } }
        public void SetTestDiscoveryCallbacks(bool allowed)
        { lock(sync){testDiscoveryCallbacks=allowed;if(!allowed)StopAll("测试发现许可已撤销；不强停在途回调、不回退作用");} }
        bool DiscoveryAvailable()=>!discoveryCleanupUnconfirmed&&cleanup!=null&&!cleanup.Blocked("discovery",discoveryLease)&&testDiscoveryCallbacks&&discoveryReview!=null&&discoveryRead!=null;
        static bool DiscoveryPlan(JObject manifest)=>((JArray)manifest["operations"]).Any(x=>(string)x["command"]=="get_tests");
        static bool DiscoveryTarget(string target)=>target=="TestDiscovery/EditMode"||target=="TestDiscovery/PlayMode";
        static string DiscoveryParams(JObject args) {Keys(args,"mode");string target="TestDiscovery/"+Text(args["mode"]);Require(DiscoveryTarget(target),"invalid_discovery_mode");return target;}
        bool prefabContentsCallbacks, prefabCleanupUnconfirmed;
        public bool PrefabCleanupUnconfirmed { get { lock(sync)return prefabCleanupUnconfirmed || cleanup==null || cleanup.Blocked("prefab"); } }
        public bool PrefabContentsCallbacksAllowed { get { lock(sync)return prefabContentsCallbacks; } }
        public void SetPrefabContentsCallbacks(bool allowed)
        { lock(sync){prefabContentsCallbacks=allowed;if(!allowed)StopAll("Prefab临时内容许可已撤销；仅清理自有实例，不回退回调作用");} }
        bool assetCallbacks;
        public bool AssetCallbacksAllowed { get { lock(sync) return assetCallbacks; } }
        public void SetAssetCallbacks(bool allowed)
        { lock(sync) { assetCallbacks=allowed; if(!allowed) StopAll("资产回调许可已撤销；不回退已发生作用"); } }
        readonly Dictionary<string, Plan> plans = new Dictionary<string, Plan>(StringComparer.Ordinal);
        readonly HashSet<string> capabilities = new HashSet<string>(StringComparer.Ordinal);
        readonly object sync = new object();
        bool busy;
        bool projectJobMaintenance;
        public bool ProjectJobMaintenanceAllowed { get { lock(sync) return projectJobMaintenance; } }
        public void SetProjectJobMaintenance(bool allowed)
        { lock(sync) { projectJobMaintenance=allowed; if(!allowed) StopAll("工程级测试作业维护已撤销；不回退状态"); } }
        long generation;
        bool reloadBlocked, reloadConsumed;
        JObject reloadTransfer;
        string reloadBinding;
        Dictionary<string, Plan> reloadPlans;
        string observedProject, observedConnection;
        public string LastReason { get; private set; } = "默认关闭";

        public CandidateGate(Func<double> clock, Func<string> project, Func<string> connection,
            Func<string, string> evidence, Func<string, JObject, JObject> native)
            : this(clock, project, connection, evidence, native, null, null) { }
        public CandidateGate(Func<double> clock, Func<string> project, Func<string> connection,
            Func<string, string> evidence, Func<string, JObject, JObject> native,
            Func<string, string> assetReview, Func<JObject, Func<bool>, JObject> assetRead)
            : this(clock,project,connection,evidence,native,assetReview,assetRead,null,null) { }
        public CandidateGate(Func<double> clock, Func<string> project, Func<string> connection,
            Func<string,string> evidence, Func<string,JObject,JObject> native,
            Func<string,string> assetReview, Func<JObject,Func<bool>,JObject> assetRead,
            Func<string,string,string> prefabReview, Func<JObject,Func<bool>,JObject> prefabRead)
            : this(clock,project,connection,evidence,native,assetReview,assetRead,prefabReview,prefabRead,null,null) { }
        public CandidateGate(Func<double> clock,Func<string> project,Func<string> connection,
            Func<string,string> evidence,Func<string,JObject,JObject> native,
            Func<string,string> assetReview,Func<JObject,Func<bool>,JObject> assetRead,
            Func<string,string,string> prefabReview,Func<JObject,Func<bool>,JObject> prefabRead,
            Func<string,string> discoveryReview,Func<JObject,Func<bool>,Task<JObject>> discoveryRead, EffectCleanupLedger cleanup=null)
        {
            this.cleanup=cleanup;
            this.discoveryReview=discoveryReview;this.discoveryRead=discoveryRead;
            this.clock = clock; this.project = project; this.connection = connection;
            this.evidence = evidence; this.native = native; this.assetReview=assetReview; this.assetRead=assetRead;this.prefabReview=prefabReview;this.prefabRead=prefabRead;
        }
        sealed class Denied : Exception { internal Denied(string code) : base(code) {} }
        static void Require(bool ok, string code) { if (!ok) throw new Denied(code); }
        static string Text(JToken token)
        {
            Require(token != null && token.Type == JTokenType.String, "invalid_string");
            string value = (string)token;
            Require(value.Length > 0 && value.Length <= 512 && value == value.Trim() && !value.Any(char.IsControl), "invalid_string");
            return value;
        }
        static void Keys(JObject value, params string[] keys)
        {
            Require(value != null && value.Count == keys.Length && value.Properties().All(p => keys.Contains(p.Name)), "unexpected_fields");
        }
        static string Op(string command, string action)
        {
            Require((command == "manage_material" && action == "get_material_info") ||
                (command == "manage_animation" && (action == "controller_get_info" || action == "clip_get_info" || AnimatorAction(action))) ||
                (command == "read_console" && action == "get") ||
                (command == "get_test_job" && action == "observe") ||
                (command == "get_tests" && action == "discover") ||
                (command == "manage_asset" && (action == "search" || action == "get_info")) ||
                (command == "manage_prefabs" && (action == "get_info" || action == "get_hierarchy")) ||
                (command == "manage_script" && (action == "read" || action == "get_sha")) ||
                (command == "manage_shader" && action == "read") ||
                (command == "unity_reflect" && new[]{"get_type","get_member","search"}.Contains(action)) ||
                (command == "manage_packages" && action == "get_package_info") ||
                (command == "find_gameobjects" && action == "find") ||
                ((ObjectCommand(command) || ProjectCommand(command) || EditorCommand(command)) && action == "read") ||
                (command == "manage_scene" && new[] { "get_active", "get_build_settings", "get_loaded_scenes", "get_hierarchy", "validate" }.Contains(action)), "operation_not_supported");
            return command + "/" + action;
        }
        static void SceneParams(JObject args)
        {
            Require(args != null && args["action"]?.Type == JTokenType.String, "invalid_scene_arguments");
            if ((string)args["action"] == "validate")
            {
                Keys(args, "action", "autoRepair");
                Require(args["autoRepair"]?.Type == JTokenType.Boolean && !(bool)args["autoRepair"], "invalid_scene_arguments");
                return;
            }
            if ((string)args["action"] != "get_hierarchy") { Keys(args, "action"); return; }
            string[] allowed = { "action", "pageSize", "cursor", "parent", "includeTransform" };
            Require(args.Properties().All(p => allowed.Contains(p.Name)) &&
                args["pageSize"]?.Type == JTokenType.Integer && (long)args["pageSize"] >= 1 &&
                (long)args["pageSize"] <= 100, "invalid_hierarchy_page");
            if (args.ContainsKey("cursor")) Require(args["cursor"].Type == JTokenType.Integer &&
                (long)args["cursor"] >= 0 && (long)args["cursor"] <= 1000000, "invalid_hierarchy_cursor");
            if (args.ContainsKey("parent")) Require(args["parent"].Type == JTokenType.Integer &&
                (long)args["parent"] >= int.MinValue && (long)args["parent"] <= int.MaxValue &&
                (long)args["parent"] != 0, "hierarchy_requires_exact_instance_id");
            if (args.ContainsKey("includeTransform")) Require(args["includeTransform"].Type == JTokenType.Boolean, "invalid_hierarchy_transform");
        }
        internal static bool AnimatorAction(string action) => action == "animator_get_info" || action == "animator_get_parameter";
        static void AnimatorParams(JObject args)
        {
            string action = Text(args?["action"]);
            Require(AnimatorAction(action), "operation_not_supported");
            if (action == "animator_get_info") Keys(args, "action", "target", "searchMethod");
            else Keys(args, "action", "target", "searchMethod", "properties");
            string value = Text(args["target"]);
            Require(Text(args["searchMethod"]) == "by_id" && int.TryParse(value,
                System.Globalization.NumberStyles.AllowLeadingSign, System.Globalization.CultureInfo.InvariantCulture, out int id) &&
                id != 0 && id != -1 && id.ToString(System.Globalization.CultureInfo.InvariantCulture) == value,
                "animator_requires_exact_instance_id");
            if (action == "animator_get_parameter")
            {
                var props = args["properties"] as JObject; Keys(props, "parameter_name");
                string name = Text(props["parameter_name"]);
                Require(name.Length > 0 && name.Length <= 256 && !name.Any(ch => ch < 32 || (ch >= 127 && ch <= 159)), "invalid_animator_parameter");
            }
        }
        internal static bool PackageName(string value) => value != null && value.Length <= 214 &&
            System.Text.RegularExpressions.Regex.IsMatch(value, @"\A(?:[a-z0-9][a-z0-9_-]*\.)+[a-z0-9][a-z0-9_-]*\z");
        internal static void ReflectionParams(JObject args)
        {
            string action=Text(args?["action"]);
            Require(new[]{"get_type","get_member","search"}.Contains(action),"operation_not_supported");
            Keys(args,action=="search"?new[]{"action","query","scope"}:action=="get_member"?new[]{"action","class_name","member_name"}:new[]{"action","class_name"});
            foreach(var p in args.Properties().Where(p=>p.Name!="action" && p.Name!="scope"))
            {
                string value=Text(p.Value),pattern=p.Name=="member_name"?@"\A[A-Za-z_][A-Za-z0-9_]*\z":@"\A[A-Za-z_][A-Za-z0-9_.]*\z";
                Require(value.Length<=128 && System.Text.RegularExpressions.Regex.IsMatch(value,pattern),"invalid_reflection_arguments");
            }
            if(action=="search")Require(Text(args["scope"])=="unity","reflection_scope_not_supported");
        }
        static void PackageParams(JObject args)
        {
            Keys(args, "action", "package");
            Require(Text(args["action"]) == "get_package_info" && PackageName(Text(args["package"])), "invalid_package_info_arguments");
        }
        internal static bool EditorCommand(string command) => command == "get_selection" || command == "get_windows" || command == "get_active_tool" || command == "get_prefab_stage" || command == "get_menu_items";
        internal static bool ProjectCommand(string command) => command == "get_project_info" || command == "get_tags" || command == "get_layers";
        static bool ObjectCommand(string command) => command == "get_gameobject" || command == "get_gameobject_components";
        static void ObjectParams(string command, JObject args)
        {
            Keys(args, command == "get_gameobject" ? new[] { "instanceID" } : new[] { "instanceID", "pageSize", "cursor", "includeProperties" });
            Require(args["instanceID"]?.Type == JTokenType.Integer && (long)args["instanceID"] >= int.MinValue &&
                (long)args["instanceID"] <= int.MaxValue && (long)args["instanceID"] != 0 && (long)args["instanceID"] != -1, "invalid_object_id");
            if (command == "get_gameobject_components") Require(args["includeProperties"]?.Type == JTokenType.Boolean && !(bool)args["includeProperties"] &&
                args["pageSize"]?.Type == JTokenType.Integer && (long)args["pageSize"] >= 1 && (long)args["pageSize"] <= 100 &&
                args["cursor"]?.Type == JTokenType.Integer && (long)args["cursor"] >= 0 && (long)args["cursor"] <= 1000000, "invalid_component_metadata_arguments");
        }
        static void FindParams(JObject args)
        {
            Keys(args, "searchTerm", "searchMethod", "includeInactive", "pageSize", "cursor");
            string term = Text(args["searchTerm"]), method = Text(args["searchMethod"]);
            // Caller type names can enter native assembly-resolution callbacks.
            Require(method != "by_component", "component_type_resolution_not_read_only");
            Require(new[] { "by_name", "by_tag", "by_layer", "by_path", "by_id" }.Contains(method) &&
                args["includeInactive"]?.Type == JTokenType.Boolean && (bool)args["includeInactive"] &&
                args["pageSize"]?.Type == JTokenType.Integer && (long)args["pageSize"] >= 1 && (long)args["pageSize"] <= 100 &&
                args["cursor"]?.Type == JTokenType.Integer && (long)args["cursor"] >= 0 && (long)args["cursor"] <= 1000000,
                "invalid_find_arguments");
            if (method == "by_id") Require(int.TryParse(term, System.Globalization.NumberStyles.AllowLeadingSign,
                System.Globalization.CultureInfo.InvariantCulture, out int id) && id != 0 &&
                id.ToString(System.Globalization.CultureInfo.InvariantCulture) == term, "find_requires_exact_instance_id");
        }
        static void ConsoleParams(JObject args)
        {
            string[] required = { "action", "types", "count", "pageSize", "format", "includeStacktrace" };
            Require(args != null && required.All(k => args.ContainsKey(k)) &&
                args.Properties().All(p => required.Contains(p.Name) || p.Name == "cursor" || p.Name == "filterText"), "invalid_console_arguments");
            Require((string)args["action"] == "get" && (string)args["format"] == "json", "operation_not_supported");
            Require(args["count"]?.Type == JTokenType.Integer && (long)args["count"] == 10 &&
                args["pageSize"]?.Type == JTokenType.Integer && (long)args["pageSize"] >= 1 && (long)args["pageSize"] <= 100 &&
                args["includeStacktrace"]?.Type == JTokenType.Boolean, "invalid_console_page");
            if (args.ContainsKey("cursor")) Require(args["cursor"].Type == JTokenType.Integer &&
                (long)args["cursor"] >= 0 && (long)args["cursor"] <= 1000000, "invalid_console_page");
            if (args.ContainsKey("filterText")) Require(args["filterText"].Type == JTokenType.String &&
                ((string)args["filterText"]).Length <= 512 && !((string)args["filterText"]).Any(char.IsControl), "invalid_console_filter");
            var types = args["types"] as JArray;
            Require(types != null && types.Count >= 1 && types.Count <= 3 && types.All(t => t.Type == JTokenType.String &&
                new[] { "error", "warning", "log" }.Contains((string)t)) && types.Select(t => (string)t).Distinct().Count() == types.Count, "invalid_console_types");
        }
        internal static bool SourcePath(string path)
        {
            if(path==null || path.Length>512 || !path.StartsWith("Assets/",StringComparison.Ordinal) || (!path.EndsWith(".cs",StringComparison.Ordinal) && !path.EndsWith(".shader",StringComparison.Ordinal)) ||
                path.Any(ch=>ch<32 || (ch>=127&&ch<=159) || "\\:%<>\"|?*".Contains(ch)))return false;
            var parts=path.Split('/');string extension=path.EndsWith(".shader",StringComparison.Ordinal)?".shader":".cs";
            if(extension==".shader" && parts.Length<3)return false;
            return parts.All(p=>p.Length>0 && p!="." && p!=".." && p==p.Trim() && !p.EndsWith(".",StringComparison.Ordinal) &&
                !System.Text.RegularExpressions.Regex.IsMatch(p.Split('.')[0],@"\A(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z")) &&
                !parts.Take(parts.Length-1).Any(p=>p.EndsWith(".cs",StringComparison.Ordinal)) &&
                System.Text.RegularExpressions.Regex.IsMatch(parts.Last().Substring(0,parts.Last().Length-extension.Length),@"\A[A-Za-z_][A-Za-z0-9_]*\z");
        }
        internal static bool ClipPath(string path)
        {
            if(path==null || path.Length>512 || !path.StartsWith("Assets/",StringComparison.Ordinal) || !path.EndsWith(".anim",StringComparison.Ordinal) || path.Split('/').Last()==".anim" ||
                path.Any(ch=>ch<32 || (ch>=127&&ch<=159) || "\\:%<>\"|?*".Contains(ch)))return false;
            return path.Split('/').All(p=>p.Length>0 && p!="." && p!=".." && p==p.Trim() && !p.EndsWith(".",StringComparison.Ordinal) &&
                !System.Text.RegularExpressions.Regex.IsMatch(p.Split('.')[0],@"\A(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z"));
        }
        internal static string SourceParams(string command,JObject args)
        {
            Keys(args,"action","name","path");
            Require(command=="manage_script" || command=="manage_shader","operation_not_supported");
            Require(Text(args["action"])=="read" || (command=="manage_script" && Text(args["action"])=="get_sha"),"operation_not_supported");
            string name=Text(args["name"]),directory=Text(args["path"]),target=directory+"/"+name+(command=="manage_shader"?".shader":".cs");
            Require(System.Text.RegularExpressions.Regex.IsMatch(name,@"\A[A-Za-z_][A-Za-z0-9_]*\z") && SourcePath(target),"invalid_source_target");
            return target;
        }
        internal static bool JobTarget(string value) => value!=null && System.Text.RegularExpressions.Regex.IsMatch(value,@"\ATestJobs/[0-9a-f]{32}\z");
        internal static string JobParams(JObject args)
        {
            Require(args!=null && args.ContainsKey("job_id") && args.Properties().All(p=>new[]{"job_id","includeDetails","includeFailedTests"}.Contains(p.Name)),"invalid_job_arguments");
            string target="TestJobs/"+Text(args["job_id"]);Require(JobTarget(target),"invalid_job_id");
            foreach(string key in new[]{"includeDetails","includeFailedTests"}) if(args.ContainsKey(key)) Require(args[key].Type==JTokenType.Boolean && (bool)args[key],"invalid_job_arguments");
            return target;
        }
        internal static bool AssetPath(string value) => value != null && value.Length <= 490 &&
            value.StartsWith("Assets/", StringComparison.Ordinal) && !value.Any(ch=>char.IsControl(ch) || "\\:%<>\"|?*".Contains(ch)) &&
            value.Split('/').All(p=>p.Length>0 && p!="." && p!=".." && p==p.Trim() && !p.EndsWith(".",StringComparison.Ordinal) &&
                !System.Text.RegularExpressions.Regex.IsMatch(p.Split('.')[0],@"\A(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z"));
        internal static bool AssetTarget(string value) => value != null && value.StartsWith("AssetReads/",StringComparison.Ordinal) && AssetPath(value.Substring(11));
        static bool AssetPlan(JObject manifest) => ((JArray)manifest["operations"]).Any(x=>(string)x["command"]=="manage_asset");
        internal static string AssetParams(JObject args)
        {
            Require(args!=null && args["path"]?.Type==JTokenType.String && AssetPath((string)args["path"]),"invalid_asset_path");
            string action=Text(args["action"]);
            if(action=="get_info") Keys(args,"action","path","generatePreview");
            else
            {
                Require(action=="search","operation_not_supported");
                string[] keys={"action","path","generatePreview","pageNumber","pageSize","searchPattern","filterType","filterDateAfter"};
                Require(args.Properties().All(x=>keys.Contains(x.Name)) && args["pageNumber"]?.Type==JTokenType.Integer &&
                    (decimal)args["pageNumber"]>=1 && (decimal)args["pageNumber"]<=1000000 && args["pageSize"]?.Type==JTokenType.Integer &&
                    (decimal)args["pageSize"]>=1 && (decimal)args["pageSize"]<=50,"invalid_asset_page");
                foreach(var key in new[]{"searchPattern","filterType","filterDateAfter"})
                    if(args[key]!=null) Require(args[key].Type==JTokenType.String && ((string)args[key]).Length<=128 && !((string)args[key]).Any(char.IsControl),"invalid_asset_filter");
                string date=(string)args["filterDateAfter"];
                Require(string.IsNullOrEmpty(date) || DateTime.TryParse(date,System.Globalization.CultureInfo.InvariantCulture,
                    System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal,out _),"invalid_asset_date");
            }
            Require(args["generatePreview"]?.Type==JTokenType.Boolean && !(bool)args["generatePreview"],"asset_preview_forbidden");
            return "AssetReads/"+(string)args["path"];
        }
        internal static bool PrefabTarget(string value) => value!=null && value.StartsWith("PrefabReads/",StringComparison.Ordinal) && AssetPath(value.Substring(12)) && value.EndsWith(".prefab",StringComparison.Ordinal);
        static bool PrefabPlan(JObject manifest) => ((JArray)manifest["operations"]).Any(x=>(string)x["command"]=="manage_prefabs");
        static string PrefabAction(JObject manifest) => (string)manifest["operations"][0]["action"];
        internal static string PrefabParams(JObject args)
        {
            Keys(args,"action","prefabPath");
            Require(Text(args["action"])=="get_info" || Text(args["action"])=="get_hierarchy","invalid_prefab_action");
            string target="PrefabReads/"+Text(args["prefabPath"]);Require(PrefabTarget(target),"invalid_prefab_path");return target;
        }
        bool PrefabAvailable(string action)=>!prefabCleanupUnconfirmed && cleanup!=null && !cleanup.Blocked("prefab",prefabLease) && assetCallbacks && prefabReview!=null && prefabRead!=null && (action=="get_info" || prefabContentsCallbacks);
        static bool JobPlan(JObject manifest) => ((JArray)manifest["operations"]).Any(x=>(string)x["command"]=="get_test_job");
        static string PathValue(JToken token)
        {
            string path = Text(token);
            if (path == "Console" || path == "Scenes" || path == "ProjectMetadata" || path == "EditorMetadata" || path == "ApiMetadata" || JobTarget(path) || SourcePath(path) || ClipPath(path)) return path;
            Require(path.StartsWith("Assets/", StringComparison.Ordinal) && path.IndexOfAny(new[] { '\\', ':' }) < 0 &&
                path.Split('/').All(p => p.Length > 0 && p != "." && p != ".." && p == p.Trim()), "invalid_target");
            Require(path.EndsWith(".mat", StringComparison.Ordinal) || path.EndsWith(".controller", StringComparison.Ordinal), "invalid_target");
            return path;
        }
        static JObject Ok(JObject data) => new JObject { ["success"] = true, ["data"] = data };
        static JObject Error(string code) => new JObject { ["success"] = false, ["error"] = code,
            ["data"] = new JObject { ["status"] = "denied", ["reason"] = code, ["read_only"] = true } };
        public bool Allows(string command, string action)
        {
            lock (sync) return capabilities.Contains(Op(command, action));
        }
        public void SetCapability(string command, string action, bool allowed)
        {
            lock (sync)
            {
                string op = Op(command, action);
                if (allowed) capabilities.Add(op);
                else { capabilities.Remove(op); StopAll("本地能力已撤销"); }
            }
        }
        public void StopAll(string reason)
        {
            lock (sync) { generation++; plans.Clear(); reloadPlans=null; reloadTransfer=null; reloadBinding=null; reloadBlocked=false; reloadConsumed=true; LastReason = reason; }
        }
        public void Observe()
        {
            lock (sync)
            {
                string p = project(), c = connection();
                if(reloadPlans!=null && (!(clock()<(double)reloadTransfer["deadline"]) || reloadPlans.Values.Any(value=>value.Project!=p || value.Connection!=c)))
                    StopAll("暂存后身份或期限变化；禁止恢复");
                if (p != observedProject || c != observedConnection || string.IsNullOrEmpty(c))
                { generation++; plans.Clear(); observedProject = p; observedConnection = c; LastReason = "工程或连接变化，需重新批准"; }
                foreach (string key in plans.Where(x => x.Value.Expires <= clock()).Select(x => x.Key).ToArray()) plans.Remove(key);
            }
        }
        Dictionary<string, string> Capture(JObject manifest)
        {
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (JToken path in (JArray)manifest["targets"])
            {
                string value = DiscoveryPlan(manifest) ? discoveryReview?.Invoke((string)path) : PrefabPlan(manifest) ? prefabReview?.Invoke(PrefabAction(manifest),(string)path) : AssetPlan(manifest) ? assetReview?.Invoke((string)path) : evidence((string)path);
                Require(!string.IsNullOrEmpty(value), "evidence_unavailable");
                result.Add((string)path, value);
            }
            return result;
        }
        void Current(Plan plan, bool approved)
        {
            Observe();
            Require(plans.TryGetValue(plan.Client, out var current) && ReferenceEquals(current, plan), "plan_not_current");
            Require(plan.Project == project() && plan.Connection == connection(), "binding_changed");
            Require(!approved || plan.Approved, "local_approval_required");
            Require(!DiscoveryPlan(plan.Manifest) || DiscoveryAvailable(),"test_discovery_unavailable");
            Require(!JobPlan(plan.Manifest) || projectJobMaintenance,"project_job_maintenance_disabled");
            Require(!PrefabPlan(plan.Manifest) || PrefabAvailable(PrefabAction(plan.Manifest)),"prefab_callbacks_unavailable");
            Require(!AssetPlan(plan.Manifest) || (assetCallbacks && assetReview!=null && assetRead!=null),"asset_callbacks_unavailable");
            foreach (JObject op in (JArray)plan.Manifest["operations"])
                Require(capabilities.Contains(Op((string)op["command"], (string)op["action"])), "local_capability_disabled");
        }
        void VerifyEvidence(Plan plan)
        {
            var actual = Capture(plan.Manifest);
            Require(actual.Count == plan.Evidence.Count && actual.All(p => plan.Evidence.TryGetValue(p.Key, out var old) && old == p.Value), "relevant_evidence_changed");
            Current(plan, false); // A local callback may have revoked/replaced during capture.
        }
        public JArray LocalPlans()
        {
            lock (sync)
            {
                Observe();
                return new JArray(plans.Values.Select(p => new JObject {
                    ["plan_id"] = p.Id, ["digest"] = p.Digest, ["client_id"] = p.Client, ["task_id"] = p.Task,
                    ["connection_id"] = p.Connection, ["project_id"] = p.Project, ["approved"] = p.Approved,
                    ["approval_connection_id"] = p.ApprovalConnection ?? p.Connection, ["binding_digest"] = p.BindingDigest ?? p.Digest,
                    ["paused"] = p.Paused, ["seconds_left"] = Math.Max(0, p.Expires - clock()), ["manifest"] = p.Manifest.DeepClone() }));
            }
        }
        public bool Approve(string id, string digest)
        {
            lock (sync)
            {
                Plan plan = plans.Values.FirstOrDefault(p => p.Id == id);
                if (plan == null || plan.Paused || reloadBlocked) return false;
                try
                {
                    Require(!busy && digest == plan.Digest, "approval_mismatch");
                    Current(plan, false); VerifyEvidence(plan); plan.Approved = true;
                    LastReason = "本地已批准；仅本任务、本连接、本清单"; return true;
                }
                catch { plans.Remove(plan.Client); LastReason = "批准失败，清单已撤销"; return false; }
            }
        }
        // Local UI only. Pause is not stop, and resume never extends expiry/rebinds.
        public bool Pause(string id, string digest) => SetPaused(id, digest, true);
        public bool Resume(string id, string digest) => SetPaused(id, digest, false);
        bool SetPaused(string id, string digest, bool paused)
        {
            lock (sync)
            {
                Observe();
                Plan plan = plans.Values.FirstOrDefault(p => p.Id == id);
                if (busy || reloadBlocked || plan == null || plan.Digest != digest || !plan.Approved || plan.Paused == paused) return false;
                busy = true;
                try
                {
                    Current(plan, true);
                    if (!paused) VerifyEvidence(plan);
                    Current(plan, true); plan.Paused = paused;
                    LastReason = paused ? "本地已暂停；清单与期限保留" : "定点证据复核通过；原清单继续";
                    return true;
                }
                catch { plans.Remove(plan.Client); LastReason = "继续核验失败，清单已撤销"; return false; }
                finally { busy = false; }
            }
        }
        // Trusted local coordinator ONLY. Never exposed through Dispatch, MCP,
        // SessionState or task-record import. Hashes bind bytes; they are NOT auth.
        internal JObject FreezeForReload(string handoffId, double window)
        {
            lock(sync)
            {
                if(busy || reloadBlocked) return null;
                busy=true;
                try
                {
                    Observe(); ReloadTransfer.Window(handoffId, window, clock());
                    Require(plans.Count>0 && plans.Values.All(p=>p.Approved && !p.Paused), "reload_not_approved");
                    var snapshot=plans.Values.ToArray();
                    Require(snapshot.All(p=>!JobPlan(p.Manifest) && !AssetPlan(p.Manifest) && !PrefabPlan(p.Manifest) && !DiscoveryPlan(p.Manifest)),"effect_reload_not_supported");
                    foreach(var p in snapshot) { Current(p,true); VerifyEvidence(p); }
                    Require(plans.Count==snapshot.Length && snapshot.All(p=>plans.TryGetValue(p.Client,out var value) && ReferenceEquals(value,p)), "reload_plan_changed");
                    double deadline=Math.Min(clock()+window,snapshot.Min(p=>p.Expires));
                    var rows=new JArray(snapshot.Select(p=>new JObject {
                        ["plan_id"]=p.Id,["approval_digest"]=p.Digest,["client_id"]=p.Client,["task_id"]=p.Task,
                        ["approval_connection_id"]=p.ApprovalConnection??p.Connection,["previous_binding_digest"]=p.BindingDigest??p.Digest,
                        ["expires_at"]=p.Expires,["manifest"]=p.Manifest.DeepClone(),["evidence"]=JObject.FromObject(p.Evidence) }));
                    var transfer=ReloadTransfer.Create("read",handoffId,project(),connection(),deadline,capabilities,rows);
                    reloadBlocked=true; reloadTransfer=transfer;
                    LastReason="已冻结；等待受信任交接，不执行或续期";
                    return (JObject)transfer.DeepClone();
                }
                catch { StopAll("冻结核验失败；需本地重新批准"); return null; }
                finally { busy=false; }
            }
        }
        internal string StageReload(JObject input, string expectedDigest, string newConnection)
        {
            lock(sync)
            {
                if(busy || reloadBlocked || reloadConsumed || plans.Count!=0) return null;
                reloadConsumed=true; busy=true; long start=generation;
                try
                {
                    var transfer=ReloadTransfer.Validate(input,expectedDigest,"read",project(),newConnection,connection(),clock());
                    var ceiling=(JArray)transfer["capabilities"];
                    Require(ceiling.All(x=>capabilities.Contains((string)x)),"capability_disabled");
                    var staged=new Dictionary<string,Plan>(StringComparer.Ordinal);
                    foreach(JObject r in (JArray)transfer["plans"])
                    {
                        Keys(r,"plan_id","approval_digest","client_id","task_id","approval_connection_id","previous_binding_digest","expires_at","manifest","evidence");
                        var p=new Plan {Id=Text(r["plan_id"]),Digest=Text(r["approval_digest"]),Client=Text(r["client_id"]),Task=Text(r["task_id"]),
                            Project=project(),Connection=newConnection,ApprovalConnection=Text(r["approval_connection_id"]),
                            Expires=ReloadTransfer.Number(r["expires_at"]),Manifest=(JObject)r["manifest"].DeepClone(),Evidence=r["evidence"].ToObject<Dictionary<string,string>>()};
                        Require(!JobPlan(p.Manifest) && !AssetPlan(p.Manifest) && !PrefabPlan(p.Manifest) && !DiscoveryPlan(p.Manifest) && p.Manifest["effects"]==null,"effect_reload_not_supported");
                        Text(r["previous_binding_digest"]);
                        Require(p.Expires>clock() && (double)transfer["deadline"]<=p.Expires,"reload_expired");
                        foreach(JObject op in (JArray)p.Manifest["operations"])
                            Require(ceiling.Any(x=>(string)x==Op(Text(op["command"]),Text(op["action"]))),"outside_capability_ceiling");
                        var actual=Capture(p.Manifest);
                        Require(actual.Count==p.Evidence.Count && actual.All(x=>p.Evidence.TryGetValue(x.Key,out var value) && value==x.Value),"relevant_evidence_changed");
                        staged.Add(p.Client,p);
                    }
                    Require(generation==start && transfer["project_id"].Value<string>()==project() && newConnection==connection() && clock()<(double)transfer["deadline"],"reload_changed");
                    string binding=ReloadTransfer.Binding(transfer,newConnection);
                    foreach(var p in staged.Values) p.BindingDigest=binding;
                    reloadPlans=staged;reloadTransfer=transfer;reloadBinding=binding;reloadBlocked=true;
                    LastReason="重附证据已核验；尚未收到双端提交";return binding;
                }
                catch { StopAll("续接暂存失败；需本地重新批准");return null; }
                finally { busy=false; }
            }
        }
        internal bool CommitReload(string handoffId,string bindingDigest)
        {
            lock(sync)
            {
                if(busy || reloadPlans==null || reloadTransfer==null || (string)reloadTransfer["handoff_id"]!=handoffId || reloadBinding!=bindingDigest)return false;
                busy=true;long start=generation;var staged=reloadPlans;var transfer=reloadTransfer;
                try
                {
                    foreach(var p in staged.Values)
                    {
                        Require(project()==p.Project && connection()==p.Connection && clock()<p.Expires && clock()<(double)transfer["deadline"],"reload_changed");
                        foreach(var cap in (JArray)transfer["capabilities"])Require(capabilities.Contains((string)cap),"capability_disabled");
                        var actual=Capture(p.Manifest);Require(actual.Count==p.Evidence.Count && actual.All(x=>p.Evidence.TryGetValue(x.Key,out var value) && value==x.Value),"relevant_evidence_changed");
                    }
                    Require(start==generation && ReferenceEquals(staged,reloadPlans) && clock()<(double)transfer["deadline"] && staged.Values.All(p=>p.Project==project() && p.Connection==connection()),"reload_cancelled");
                    foreach(var p in staged.Values){p.Approved=true;plans.Add(p.Client,p);}
                    observedProject=project();observedConnection=connection();reloadPlans=null;reloadTransfer=null;reloadBinding=null;reloadBlocked=false;
                    LastReason="原批准和期限保持；新连接绑定已提交";return true;
                }
                catch { StopAll("续接提交失败；未恢复授权");return false; }
                finally { busy=false; }
            }
        }
        public JObject Dispatch(JObject request)
        {
            lock (sync)
            {
                string client = null;
                bool stopRequest = false;
                bool effectAttempted = false, prefabAttempted=false, prefabHierarchy=false, prefabClean=false;
                if (reloadBlocked && (string)request?["kind"] != "stop") return Error("planned_reload_frozen");
                if (busy && (string)request?["kind"]!="stop") return Error("execution_in_progress");
                bool wasBusy=busy; busy = true;
                try
                {
                    Require(request != null && request.ToString(Formatting.None).Length <= 65536, "request_too_large");
                    var r = (JObject)request.DeepClone();
                    Keys(r, "protocol", "kind", "project_id", "client_id", "connection_id", "task_id", "plan_id", "body");
                    stopRequest = (string)r["kind"] == "stop";
                    Require(r["protocol"].Type == JTokenType.Integer && (int)r["protocol"] == 1, "unsupported_protocol");
                    Observe(); client = Text(r["client_id"]);
                    Require(Text(r["project_id"]) == project() && Text(r["connection_id"]) == connection(), "binding_changed");
                    string kind = Text(r["kind"]); var body = r["body"] as JObject;
                    if (kind == "status")
                    {
                        Keys(body); Require((string)r["plan_id"] == "" && (string)r["task_id"] == "", "unexpected_identity");
                        return Ok(new JObject { ["status"] = capabilities.Count == 0 ? "本地能力关闭" : "等待本地清单批准",
                            ["capabilities"] = new JArray(capabilities), ["read_only"] = !projectJobMaintenance && !assetCallbacks && !prefabContentsCallbacks && !testDiscoveryCallbacks, ["project_test_job_maintenance"] = projectJobMaintenance, ["asset_load_callbacks"] = assetCallbacks, ["prefab_contents_callbacks"]=prefabContentsCallbacks, ["prefab_cleanup_unconfirmed"]=PrefabCleanupUnconfirmed,["test_discovery_callbacks"]=testDiscoveryCallbacks,["test_discovery_cleanup_unconfirmed"]=TestDiscoveryCleanupUnconfirmed });
                    }
                    string task = Text(r["task_id"]);
                    if(kind=="stop" && reloadPlans!=null)
                    {
                        Keys(body);Require(reloadPlans.TryGetValue(client,out var staged) && staged.Task==task && staged.Id==(string)r["plan_id"],"plan_mismatch");
                        StopAll("精确任务停止已取消续接");return Ok(new JObject{["status"]="stopped"});
                    }
                    if (kind == "prepare")
                    {
                        plans.Remove(client);
                        Require((string)r["plan_id"] == "", "unexpected_identity");
                        if(body!=null && body.ContainsKey("effects")) Keys(body,"operations","targets","ttl_seconds","effects");
                        else Keys(body, "operations", "targets", "ttl_seconds");
                        var ops = body["operations"] as JArray; var targets = body["targets"] as JArray;
                        Require(ops != null && ops.Count > 0 && ops.Count <= 29 && targets != null && targets.Count > 0 && targets.Count <= 64, "invalid_manifest");
                        var seen = new HashSet<string>(StringComparer.Ordinal);
                        foreach (JToken item in ops)
                        {
                            var op = item as JObject; Keys(op, "command", "action");
                            string key = Op(Text(op["command"]), Text(op["action"]));
                            Require(seen.Add(key) && capabilities.Contains(key), "local_capability_disabled");
                        }
                        bool jobPlan=seen.Contains("get_test_job/observe");
                        if(seen.Contains("get_tests/discover"))
                        {
                            Require(DiscoveryAvailable(),"test_discovery_unavailable");
                            Require(ops.Count==1&&targets.Count==1&&targets[0].Type==JTokenType.String&&DiscoveryTarget((string)targets[0]),"discovery_requires_separate_exact_plan");
                            var effects=body["effects"] as JArray;Require(effects!=null&&effects.Count==1,"explicit_discovery_effect_required");
                            var effect=effects[0] as JObject;Keys(effect,"kind","version");
                            Require((string)effect["kind"]=="test_discovery_callbacks"&&effect["version"]?.Type==JTokenType.Integer&&(long)effect["version"]==1,"invalid_discovery_effect_policy");
                        }
                        else if(jobPlan)
                        {
                            Require(projectJobMaintenance,"project_job_maintenance_disabled");
                            Require(ops.Count==1 && targets.Count==1 && JobTarget((string)targets[0]),"job_requires_separate_exact_plan");
                            var effects=body["effects"] as JArray;Require(effects!=null && effects.Count==1,"explicit_job_effect_required");
                            var effect=effects[0] as JObject;Keys(effect,"kind","version");
                            Require((string)effect["kind"]=="project_test_job_maintenance" && effect["version"]?.Type==JTokenType.Integer && (long)effect["version"]==1,"invalid_effect_policy");
                        }
                        else if(seen.Any(x=>x.StartsWith("manage_asset/",StringComparison.Ordinal)))
                        {
                            Require(assetCallbacks && assetReview!=null && assetRead!=null,"asset_callbacks_unavailable");
                            Require(ops.Count==1 && targets.Count==1 && targets[0].Type==JTokenType.String && AssetTarget((string)targets[0]),"asset_requires_separate_exact_plan");
                            var effects=body["effects"] as JArray;Require(effects!=null && effects.Count==1,"explicit_asset_effect_required");
                            var effect=effects[0] as JObject;Keys(effect,"kind","version");
                            Require((string)effect["kind"]=="asset_load_callbacks" && effect["version"]?.Type==JTokenType.Integer && (long)effect["version"]==1,"invalid_effect_policy");
                        }
                        else if(seen.Any(x=>x.StartsWith("manage_prefabs/",StringComparison.Ordinal)))
                        {
                            Require(ops.Count==1 && targets.Count==1 && targets[0].Type==JTokenType.String && PrefabTarget((string)targets[0]),"prefab_requires_separate_exact_plan");
                            string prefabAction=(string)ops[0]["action"];
                            Require(PrefabAvailable(prefabAction),"prefab_callbacks_unavailable");
                            var expected=prefabAction=="get_info" ? new[]{"asset_load_callbacks"} : new[]{"asset_load_callbacks","prefab_contents_callbacks"};
                            var effects=body["effects"] as JArray;Require(effects!=null && effects.Count==expected.Length,"explicit_prefab_effects_required");
                            for(int i=0;i<expected.Length;i++){var effect=effects[i] as JObject;Keys(effect,"kind","version");Require(effect["kind"]?.Type==JTokenType.String && (string)effect["kind"]==expected[i] && effect["version"]?.Type==JTokenType.Integer && (long)effect["version"]==1,"invalid_prefab_effect_policy");}
                        }
                        else Require(!body.ContainsKey("effects"),"unexpected_effects");
                        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                        foreach (JToken token in targets)
                        {
                            string path = seen.Contains("get_tests/discover") || seen.Any(x=>x.StartsWith("manage_asset/",StringComparison.Ordinal) || x.StartsWith("manage_prefabs/",StringComparison.Ordinal)) ? Text(token) : PathValue(token);
                            Require(paths.Add(path), "duplicate_target");
                            Require((DiscoveryTarget(path)&&seen.Contains("get_tests/discover")) || (SourcePath(path) && ((path.EndsWith(".cs",StringComparison.Ordinal) && (seen.Contains("manage_script/read") || seen.Contains("manage_script/get_sha"))) ||
                        (path.EndsWith(".shader",StringComparison.Ordinal) && seen.Contains("manage_shader/read")))) ||
                                (path.EndsWith(".mat", StringComparison.Ordinal) && seen.Contains("manage_material/get_material_info")) ||
                                (path.EndsWith(".controller", StringComparison.Ordinal) && seen.Contains("manage_animation/controller_get_info")) ||
                                (ClipPath(path) && seen.Contains("manage_animation/clip_get_info")) ||
                                (path == "ApiMetadata" && seen.Any(op=>op.StartsWith("unity_reflect/",StringComparison.Ordinal))) ||
                                (JobTarget(path) && seen.Contains("get_test_job/observe")) ||
                                (PrefabTarget(path) && seen.Any(x=>x.StartsWith("manage_prefabs/",StringComparison.Ordinal))) ||
                                (AssetTarget(path) && seen.Any(x=>x.StartsWith("manage_asset/",StringComparison.Ordinal))) ||
                                (path == "Console" && seen.Contains("read_console/get")) ||
                                (path == "EditorMetadata" && seen.Any(op => new[]{"get_selection/read","get_windows/read","get_active_tool/read","get_prefab_stage/read","get_menu_items/read"}.Contains(op))) ||
                                (path == "ProjectMetadata" && seen.Any(op => op == "manage_packages/get_package_info" || op == "get_project_info/read" || op == "get_tags/read" || op == "get_layers/read")) ||
                                (path == "Scenes" && seen.Any(op => op.StartsWith("manage_scene/", StringComparison.Ordinal) || op == "find_gameobjects/find" || op == "get_gameobject/read" || op == "get_gameobject_components/read" || op == "manage_animation/animator_get_info" || op == "manage_animation/animator_get_parameter")), "target_operation_mismatch");
                        }
                        Require(body["ttl_seconds"].Type == JTokenType.Float || body["ttl_seconds"].Type == JTokenType.Integer, "invalid_ttl");
                        double ttl = (double)body["ttl_seconds"];
                        Require(!double.IsNaN(ttl) && !double.IsInfinity(ttl) && ttl > 0 && ttl <= 900, "invalid_ttl");
                        Require(plans.Count < 128, "plan_capacity");
                        var plan = new Plan { Id = Guid.NewGuid().ToString("N"), Client = client, Project = project(), Connection = connection(),
                            Task = task, Expires = clock() + ttl, Manifest = (JObject)body.DeepClone() };
                        if(jobPlan) plan.Manifest["effect_policy"]=new JObject { ["kind"]="project_test_job_maintenance",["version"]=1,["project_wide"]=true,["read_only"]=false,
                            ["result_target"]=targets[0].DeepClone(),["expires_at"]=plan.Expires,["native_commit"]="30d22075093d1d35dfb0091c1c7550e9ad948577",
                            ["notice_zh"]="查询可恢复并改变本工程其他过期作业、保存SessionState并裁剪历史；结果只返回指定作业。不会启动/清空测试或抢焦点；停止不回退已发生维护。" };
                        if(AssetPlan(plan.Manifest)) plan.Manifest["effect_policy"]=new JObject {
                            ["kind"]="asset_load_callbacks",["version"]=1,["read_only"]=false,["callback_effects_path_bounded"]=false,
                            ["result_target"]=targets[0].DeepClone(),["max_page_loads"]=50,["max_matches"]=4096,["expires_at"]=plan.Expires,
                            ["native_commit"]="30d22075093d1d35dfb0091c1c7550e9ad948577",
                            ["notice_zh"]="实时加载依赖本地认可的工程插件信任前提；不是插件沙箱，不能保证阻止内部未知回调。结果范围不隔离回调写文件、联网或启动进程。禁止预览、刷新和工具写分支；撤销不强停在途回调、不回退作用。" };
                        if(PrefabPlan(plan.Manifest)) plan.Manifest["effect_policy"]=new JObject {
                            ["kind"]=PrefabAction(plan.Manifest)=="get_hierarchy" ? "prefab_contents_callbacks" : "asset_load_callbacks",
                            ["version"]=1,["read_only"]=false,["callback_effects_path_bounded"]=false,["result_target"]=targets[0].DeepClone(),
                            ["max_nodes"]=1000,["max_depth"]=64,["max_components_per_node"]=256,["max_response_bytes"]=262144,["expires_at"]=plan.Expires,
                            ["native_commit"]="30d22075093d1d35dfb0091c1c7550e9ad948577",
                            ["notice_zh"]="实时读取会加载资产；层级读取另会临时加载内容及卸载，两者均可能执行本地认可插件的回调；不是插件沙箱，不保证阻止内部未知回调。工具不保存、不打开Stage；范围不隔离回调作用，预算不强停原生加载或插件。停止仍清理自有实例，失败不回退。" };
                        if(DiscoveryPlan(plan.Manifest))plan.Manifest["effect_policy"]=new JObject{
                            ["kind"]="test_discovery_callbacks",["version"]=1,["read_only"]=false,["callback_effects_path_bounded"]=false,
                            ["result_target"]=targets[0].DeepClone(),["max_nodes"]=4096,["max_depth"]=64,["max_response_bytes"]=262144,["expires_at"]=plan.Expires,
                            ["notice_zh"]="重新发现依赖本地认可的工程插件信任前提，可能运行测试构建回调；不是插件沙箱，不保证阻止内部未知回调。模式和结果限制不隔离回调副作用。不运行测试、不维护作业、不切焦点、不使用缓存；撤销拒绝结果并清理自有枚举/订阅，不强停回调、不回退作用。"};
                        long startedGeneration = generation;
                        plan.Evidence = Capture(plan.Manifest);
                        Require(generation == startedGeneration && clock() < plan.Expires, "prepare_cancelled");
                        Require(plan.Project == project() && plan.Connection == connection(), "binding_changed");
                        var digestInput = new JObject { ["id"] = plan.Id, ["project"] = plan.Project, ["client"] = client,
                            ["connection"] = plan.Connection, ["task"] = task, ["manifest"] = plan.Manifest.DeepClone(),
                            ["evidence"] = JObject.FromObject(plan.Evidence) };
                        using (var hash = SHA256.Create()) plan.Digest = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(digestInput.ToString(Formatting.None)))).Replace("-", "").ToLowerInvariant();
                        plans[client] = plan; LastReason = "等待本地核对清单";
                        return Ok(new JObject { ["status"] = "pending", ["plan_id"] = plan.Id, ["digest"] = plan.Digest });
                    }
                    Require(plans.TryGetValue(client, out var active) && active.Task == task, "plan_not_current");
                    Require((string)r["plan_id"] == active.Id, "plan_mismatch");
                    if (kind == "stop") { Keys(body); if(reloadBlocked) StopAll("本地续接已取消"); else plans.Remove(client); LastReason = "已停止，不回退文件"; return Ok(new JObject { ["status"] = "stopped" }); }
                    Require(kind == "execute", "unknown_kind");
                    Keys(body, "command", "params"); string command = Text(body["command"]);
                    var args = body["params"] as JObject;
                    string action, target;
                    Require(command!="get_tests","asynchronous_discovery_required");
                    if(command=="get_test_job")
                    { target=JobParams(args);action="observe"; }
                    else if(command=="manage_prefabs")
                    { target=PrefabParams(args);action=Text(args["action"]); }
                    else if(command=="manage_asset")
                    { target=AssetParams(args);action=Text(args["action"]); }
                    else if (command == "manage_script" || command == "manage_shader")
                    { target=SourceParams(command,args);action=Text(args["action"]); }
                    else if (command == "read_console")
                    { ConsoleParams(args); action = "get"; target = "Console"; }
                    else if (command == "manage_scene")
                    { SceneParams(args); action = Text(args["action"]); target = "Scenes"; }
                    else if (command == "manage_animation" && AnimatorAction((string)args?["action"]))
                    { AnimatorParams(args); action = Text(args["action"]); target = "Scenes"; }
                    else if (command == "unity_reflect")
                    { ReflectionParams(args); action=Text(args["action"]);target="ApiMetadata"; }
                    else if (command == "manage_packages")
                    { PackageParams(args); action = "get_package_info"; target = "ProjectMetadata"; }
                    else if (ProjectCommand(command) || EditorCommand(command))
                    {
                        if (command == "get_menu_items")
                        { Keys(args, "refresh", "search"); Require(args["refresh"]?.Type == JTokenType.Boolean && (bool)args["refresh"] && args["search"]?.Type == JTokenType.String && (string)args["search"] == "", "invalid_menu_arguments"); }
                        else Keys(args);
                        action = "read"; target = ProjectCommand(command) ? "ProjectMetadata" : "EditorMetadata";
                    }
                    else if (ObjectCommand(command))
                    { ObjectParams(command, args); action = "read"; target = "Scenes"; }
                    else if (command == "find_gameobjects")
                    { FindParams(args); action = "find"; target = "Scenes"; }
                    else
                    {
                        string keyName = command == "manage_material" ? "materialPath" : (string)args?["action"]=="clip_get_info" ? "clipPath" : "controllerPath";
                        Keys(args, "action", keyName); action = Text(args["action"]); target = PathValue(args[keyName]);
                        if(keyName=="clipPath")Require(ClipPath(target),"invalid_clip_target");
                        Require(target != "Console" && target != "Scenes" && target != "ProjectMetadata" && target != "EditorMetadata" && target != "ApiMetadata", "invalid_target");
                    }
                    string operation = Op(command, action);
                    Require(((JArray)active.Manifest["operations"]).Cast<JObject>().Any(x => (string)x["command"] == command && (string)x["action"] == action) &&
                        ((JArray)active.Manifest["targets"]).Any(x => (string)x == target), "outside_plan");
                    Current(active, true);
                    if (active.Paused) return new JObject { ["success"] = false, ["error"] = "plan_paused",
                        ["data"] = new JObject { ["status"] = "paused", ["reason"] = "plan_paused", ["plan_id"] = active.Id } };
                    VerifyEvidence(active); Current(active, true);
                    effectAttempted=command=="get_test_job" || command=="manage_asset" || command=="manage_prefabs";
                    prefabAttempted=command=="manage_prefabs";prefabHierarchy=prefabAttempted && action=="get_hierarchy";
                    bool inFlight=true;
                    Func<bool> assetTicket=()=> { lock(sync) { try { Require(inFlight,"asset_call_finished"); Current(active,true); Require(!active.Paused,"plan_paused"); VerifyEvidence(active); return true; } catch { return false; } } };
                    JObject result;
                    if(prefabHierarchy)prefabLease=cleanup.Begin("prefab");
                    try { result = command=="manage_prefabs" ? prefabRead((JObject)args.DeepClone(),assetTicket) : command=="manage_asset" ? assetRead((JObject)args.DeepClone(),assetTicket) : native(command, (JObject)args.DeepClone()); }
                    finally { inFlight=false; }
                    if(prefabAttempted)
                    {
                        var receipt=result?["data"]?["candidate_effects"] as JObject;
                        Keys(receipt,"kind","version","read_only","all_mutations_observed","callback_effects_path_bounded","load_started","unload_started","cleanup_confirmed");
                        Require(receipt["kind"]?.Type==JTokenType.String && (string)receipt["kind"]==(prefabHierarchy ? "prefab_contents_callbacks" : "asset_load_callbacks") && receipt["version"]?.Type==JTokenType.Integer && (int)receipt["version"]==1,"prefab_receipt_invalid");
                        foreach(string key in new[]{"read_only","all_mutations_observed","callback_effects_path_bounded","load_started","unload_started","cleanup_confirmed"})Require(receipt[key]?.Type==JTokenType.Boolean,"prefab_receipt_invalid");
                        Require(!(bool)receipt["read_only"] && !(bool)receipt["all_mutations_observed"] && !(bool)receipt["callback_effects_path_bounded"],"prefab_receipt_invalid");
                        bool loaded=(bool)receipt["load_started"],unloaded=(bool)receipt["unload_started"];
                        prefabClean=(bool)receipt["cleanup_confirmed"] && (!loaded || unloaded);
                        if(prefabHierarchy && prefabClean){prefabClean=cleanup.Finish(prefabLease);if(prefabClean)prefabLease=null;}
                        if(prefabHierarchy && !prefabClean)prefabCleanupUnconfirmed=true;
                        Require(prefabClean && (!prefabHierarchy ? !loaded && !unloaded : result["success"]?.Type!=JTokenType.Boolean || !(bool)result["success"] || loaded && unloaded),"prefab_cleanup_unconfirmed");
                    }
                    Require(result != null && result["success"]?.Type == JTokenType.Boolean, "native_result_invalid");
                    if ((bool)result["success"] != true) { plans.Remove(client); LastReason = "原生命令失败；已撤权，未自动回退"; return prefabAttempted ? PrefabError("native_read_failed",prefabClean) : EffectError("native_read_failed",effectAttempted); }
                    VerifyEvidence(active); Current(active, true);
                    return result;
                }
                catch (Exception e)
                {
                    // Delayed lifecycle cleanup must never revoke a newer plan.
                    // Stop only removes the exact task/plan after validation above.
                    if (client != null && !stopRequest) plans.Remove(client);
                    LastReason = stopRequest ? "停止请求被拒绝" : "请求失败，需重新核对清单";
                    // No raw paths/Unity exception detail is sent remotely.
                    if(prefabHierarchy && !prefabClean)prefabCleanupUnconfirmed=true;
                    return prefabAttempted ? PrefabError(e is Denied ? e.Message : "prefab_read_unconfirmed",prefabClean) : EffectError(e is Denied ? e.Message : "local_validation_failed",effectAttempted);
                }
                finally { busy = wasBusy; }
            }
        }
        // Editor-thread caller/continuation; no managed lock is held across await.
        public async Task<JObject> DispatchAsync(JObject request)
        {
            if((string)request?["kind"]!="execute" || (string)request?["body"]?["command"]!="get_tests")return Dispatch(request);
            Plan active=null;string client=null;JObject args=null;bool inFlight=false,attempted=false,ownsBusy=false,cleaned=false;
            Func<bool> ticket=null;
            try
            {
                lock(sync)
                {
                    Require(!busy&&!reloadBlocked,"execution_in_progress");busy=true;ownsBusy=true;
                    Require(request.ToString(Formatting.None).Length<=65536,"request_too_large");
                    var r=(JObject)request.DeepClone();
                    Keys(r,"protocol","kind","project_id","client_id","connection_id","task_id","plan_id","body");
                    Require(r["protocol"]?.Type==JTokenType.Integer&&(long)r["protocol"]==1,"unsupported_protocol");
                    Observe();client=Text(r["client_id"]);
                    Require(Text(r["project_id"])==project()&&Text(r["connection_id"])==connection(),"binding_changed");
                    Require(plans.TryGetValue(client,out var selected)&&selected.Task==Text(r["task_id"])&&selected.Id==Text(r["plan_id"]),"plan_not_current");
                    active=selected; // A stale request must not acquire a replacement's failure cleanup.
                    var body=r["body"] as JObject;Keys(body,"command","params");
                    args=body["params"] as JObject;string target=DiscoveryParams(args);
                    Require(DiscoveryPlan(active.Manifest)&&((JArray)active.Manifest["targets"]).Any(t=>(string)t==target),"outside_plan");
                    Current(active,true);
                    if(active.Paused)return new JObject { ["success"]=false,["error"]="plan_paused",
                        ["data"]=new JObject { ["status"]="paused",["reason"]="plan_paused",["plan_id"]=active.Id } };
                    VerifyEvidence(active);Current(active,true);
                    inFlight=true;
                    ticket=()=>{lock(sync){try{Require(inFlight,"discovery_call_finished");Current(active,true);Require(!active.Paused&&clock()<active.Expires,"discovery_not_current");VerifyEvidence(active);return inFlight;}catch{return false;}}};
                    Require(ticket(),"discovery_not_current");
                    discoveryLease=cleanup.Begin("discovery");Require(ticket(),"discovery_not_current");attempted=true;
                }
                JObject result=await discoveryRead((JObject)args.DeepClone(),ticket);
                lock(sync)
                {
                    Require(result!=null&&result["success"]?.Type==JTokenType.Boolean,"discovery_result_invalid");
                    var receipt=result["data"]?["candidate_effects"] as JObject;
                    Keys(receipt,"kind","version","read_only","all_mutations_observed","callback_effects_path_bounded","cleanup_confirmed");
                    Require((string)receipt["kind"]=="test_discovery_callbacks"&&receipt["version"]?.Type==JTokenType.Integer&&(long)receipt["version"]==1,"discovery_receipt_invalid");
                    foreach(string key in new[]{"read_only","all_mutations_observed","callback_effects_path_bounded","cleanup_confirmed"})Require(receipt[key]?.Type==JTokenType.Boolean,"discovery_receipt_invalid");
                    Require(!(bool)receipt["read_only"]&&!(bool)receipt["all_mutations_observed"]&&!(bool)receipt["callback_effects_path_bounded"],"discovery_receipt_invalid");
                    cleaned=(bool)receipt["cleanup_confirmed"] && cleanup.Finish(discoveryLease);
                    if(cleaned)discoveryLease=null;
                    Require(cleaned,"discovery_cleanup_unconfirmed");
                    Require((bool)result["success"],new[]{"discovery_timed_out","discovery_clock_changed"}.Contains((string)result["error"])?(string)result["error"]:"discovery_failed");
                    Keys(result,"success","error","data");Require(result["error"] is JValue errorValue && errorValue.Value==null,"discovery_result_invalid");
                    var data=result["data"] as JObject;Keys(data,"tests","candidate_effects");
                    var rows=data["tests"] as JArray;Require(rows!=null&&rows.Count<=4096,"discovery_result_invalid");
                    var names=new HashSet<string>(StringComparer.Ordinal);
                    foreach(var token in rows)
                    {
                        var row=token as JArray;Require(row!=null&&row.Count==4&&row.All(s=>s.Type==JTokenType.String&&!string.IsNullOrEmpty((string)s)&&((string)s).Length<=4096&&!((string)s).Any(char.IsControl)),"discovery_result_invalid");
                        Require((string)row[3]==(string)args["mode"]&&names.Add((string)row[1]),"discovery_result_invalid");
                    }
                    Require(Encoding.UTF8.GetByteCount(result.ToString(Formatting.None))<=262144,"discovery_response_budget");
                    Require(ticket(),"discovery_not_current");return result;
                }
            }
            catch(Exception e)
            {
                lock(sync)
                {
                    if(active!=null&&plans.TryGetValue(client,out var current)&&ReferenceEquals(current,active))plans.Remove(client);
                    LastReason="测试发现失败或已撤销；未自动回退";
                    if(attempted&&!cleaned)discoveryCleanupUnconfirmed=true;
                    var error=EffectError(e is Denied?e.Message:"discovery_unconfirmed",attempted);
                    if(attempted)error["data"]["cleanup_confirmed"]=cleaned;
                    return error;
                }
            }
            finally {lock(sync){inFlight=false;if(ownsBusy)busy=false;}}
        }
        static JObject PrefabError(string reason,bool cleanup)
        { var result=EffectError(reason,true);result["data"]["cleanup_confirmed"]=cleanup;return result; }
        static JObject EffectError(string reason,bool attempted)
        { var result=Error(reason);if(attempted){result["data"]["read_only"]=false;result["data"]["effects_may_have_occurred"]=true;}return result; }
    }
}
