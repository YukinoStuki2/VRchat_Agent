using System;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Output validation only, NOT a reader. The native sync handler remains the
    // sole reader. Pinned contracts: ManageMaterial.GetMaterialInfo (both Unity
    // branches), ControllerCreate.GetInfo, and Helpers/Response.cs at 30d2207.
    internal static class NativeReadContract
    {
        static bool Shape(JToken token, params string[] fields) => token is JObject obj &&
            obj.Count == fields.Length && obj.Properties().All(p => fields.Contains(p.Name));
        static bool String(JToken t) => t?.Type == JTokenType.String;
        static bool Null(JToken t) => t?.Type == JTokenType.Null;
        static bool NullableString(JToken t) => String(t) || Null(t);
        static bool Bool(JToken t) => t?.Type == JTokenType.Boolean;
        static bool Number(JToken t) => t != null && (t.Type == JTokenType.Float || t.Type == JTokenType.Integer) &&
            !double.IsNaN((double)t) && !double.IsInfinity((double)t);
        static bool Count(JToken count, JToken array) => count?.Type == JTokenType.Integer &&
            array is JArray items && (long)count == items.Count;
        static bool All(JToken array, Func<JToken, bool> valid) => array is JArray items && items.All(valid);
        static bool Components(JToken value, params string[] names) => Shape(value, names) && names.All(n => Number(value[n]));

        static bool ClipInfo(JToken data,JObject args)
        {
            return Shape(args,"action","clipPath") && CandidateGate.ClipPath((string)args["clipPath"]) &&
                Shape(data,"path","name","length","frameRate","isLooping","wrapMode","curveCount","curves","eventCount","events") &&
                (string)data["path"]==(string)args["clipPath"] && String(data["name"]) && Number(data["length"]) && (double)data["length"]>=0 &&
                Number(data["frameRate"]) && (double)data["frameRate"]>=0 && Bool(data["isLooping"]) && String(data["wrapMode"]) &&
                new[]{"Default","Once","Loop","PingPong","ClampForever","Clamp"}.Contains((string)data["wrapMode"]) &&
                Count(data["curveCount"],data["curves"]) && ((JArray)data["curves"]).Count<=512 &&
                All(data["curves"],x=>Shape(x,"path","propertyName","type","keyCount") && String(x["path"]) && String(x["propertyName"]) && String(x["type"]) &&
                    x["keyCount"]?.Type==JTokenType.Integer && (long)x["keyCount"]>=0 && (long)x["keyCount"]<=262144) &&
                Count(data["eventCount"],data["events"]) && ((JArray)data["events"]).Count<=1024 &&
                All(data["events"],x=>Shape(x,"time","functionName","stringParameter","floatParameter","intParameter") && Number(x["time"]) &&
                    NullableString(x["functionName"]) && NullableString(x["stringParameter"]) && Number(x["floatParameter"]) && x["intParameter"]?.Type==JTokenType.Integer);
        }
        internal static bool Valid(string command, JObject result, JObject args = null)
        {
            if (result == null || result["success"]?.Type != JTokenType.Boolean || !(bool)result["success"]) return false;
            if (!(Shape(result, "success", "data") ||
                (Shape(result, "success", "message", "data") && String(result["message"])))) return false;
            var data = result["data"];
            if (command == "manage_script" || command == "manage_shader") return SourceRead(command,data,args);
            if (command == "manage_animation" && (string)args?["action"] == "clip_get_info") return ClipInfo(data,args);
            if (command == "unity_reflect") return Reflection(data,args);
            if (command == "manage_packages") return PackageInfo(data, args);
            if (command == "get_menu_items") return Shape(args, "refresh", "search") && Bool(args["refresh"]) && (bool)args["refresh"] && String(args["search"]) && (string)args["search"] == "" &&
                data is JArray menu && menu.Count <= 4096 && menu.All(x => BoundedString(x, 4096) && ((string)x).Length > 0) &&
                menu.Select(x => (string)x).SequenceEqual(menu.Select(x => (string)x).Distinct(StringComparer.Ordinal).OrderBy(x => x, StringComparer.Ordinal)) &&
                data.ToString(Newtonsoft.Json.Formatting.None).Length <= 1024 * 1024;
            if (CandidateGate.EditorCommand(command)) return EditorMetadata(command, data, args);
            if (CandidateGate.ProjectCommand(command)) return ProjectMetadata(command, data, args);
            if (command == "read_console") return ConsolePage(data, args);
            if (command == "manage_scene") return SceneMetadata(data, args);
            if (command == "find_gameobjects") return FindPage(data, args);
            if (command == "get_gameobject") return ObjectSummary(data, args);
            if (command == "get_gameobject_components") return ComponentMetadata(data, args);
            if (command == "manage_material") return Shape(data, "material", "shader", "properties") &&
                String(data["material"]) && String(data["shader"]) && All(data["properties"], Property);
            if (command == "manage_animation" && CandidateGate.AnimatorAction((string)args?["action"])) return Animator(data, args);
            if (command == "manage_animation") return Shape(data, "path", "name", "layerCount", "parameterCount", "layers", "parameters") &&
                String(data["path"]) && String(data["name"]) && Count(data["layerCount"], data["layers"]) &&
                Count(data["parameterCount"], data["parameters"]) && All(data["layers"], Layer) && All(data["parameters"], Parameter);
            return false;
        }
        static bool Reflection(JToken data,JObject args)
        {
            try { CandidateGate.ReflectionParams(args); } catch { return false; }
            if(!(data is JObject) || System.Text.Encoding.UTF8.GetByteCount(data.ToString(Newtonsoft.Json.Formatting.None))>262144)return false;
            string action=(string)args["action"],query=(string)args["class_name"];
            bool Strings(JToken a)=>a is JArray rows && rows.Count<=1024 && rows.All(x=>BoundedString(x,1024));
            bool Scalar(JToken t)=>Null(t)||Bool(t)||Number(t)||BoundedString(t,4096);
            bool TypeName(JToken t)=>BoundedString(t,256) && ((string)t==query || (query!=null && query.EndsWith("."+(string)t,System.StringComparison.Ordinal)));
            if(action=="search")return Shape(data,"query","scope","count","results","truncated") &&
                JToken.DeepEquals(data["query"],args["query"]) && (string)data["scope"]=="unity" && Bool(data["truncated"]) &&
                Count(data["count"],data["results"]) && Integer(data["count"],0,13) &&
                All(data["results"],x=>Shape(x,"name","full_name","namespace","assembly","is_class","is_enum","is_interface","is_struct") &&
                    BoundedString(x["name"],128) && BoundedString(x["full_name"],256) && (string)x["namespace"]=="UnityEngine" &&
                    BoundedString(x["assembly"],256) && Bool(x["is_class"]) && Bool(x["is_enum"]) && Bool(x["is_interface"]) && Bool(x["is_struct"]));
            if(!Bool(data["found"]))return false;
            if(!(bool)data["found"])return (Shape(data,"found","query") && JToken.DeepEquals(data["query"],args["class_name"])) ||
                (action=="get_member" && Shape(data,"found","type_name","member_name") && TypeName(data["type_name"]) && JToken.DeepEquals(data["member_name"],args["member_name"]));
            if(action=="get_type")return Shape(data,"found","name","full_name","namespace","assembly","base_class","interfaces","is_abstract","is_sealed","is_static","is_enum","is_interface","members","extension_methods","obsolete_members") &&
                TypeName(data["name"]) && BoundedString(data["full_name"],256) &&
                ((string)data["full_name"]==query || (query!=null && !query.Contains(".") && (string)data["full_name"]=="UnityEngine."+query)) &&
                (string)data["namespace"]=="UnityEngine" && BoundedString(data["assembly"],256) && NullableBoundedString(data["base_class"],1024) &&
                Strings(data["interfaces"]) && new[]{"is_abstract","is_sealed","is_static","is_enum","is_interface"}.All(n=>Bool(data[n])) &&
                Shape(data["members"],"methods","properties","fields","events") && ((JObject)data["members"]).Properties().All(p=>Strings(p.Value)) &&
                data["extension_methods"] is JArray extensions && extensions.Count==0 && Strings(data["obsolete_members"]);
            if(!TypeName(data["type_name"]) || !JToken.DeepEquals(data["member_name"],args["member_name"]))return false;
            string kind=(string)data["member_type"];
            if(kind=="method")return Shape(data,"found","type_name","member_name","member_type","overload_count","overloads") &&
                Count(data["overload_count"],data["overloads"]) && Integer(data["overload_count"],1,256) && All(data["overloads"],m=>
                    Shape(m,"signature","return_type","parameters","is_static","is_virtual","is_abstract","is_generic","generic_arguments","is_obsolete","obsolete_message","declaring_type") &&
                    BoundedString(m["signature"],8192) && BoundedString(m["return_type"],1024) &&
                    new[]{"is_static","is_virtual","is_abstract","is_generic","is_obsolete"}.All(n=>Bool(m[n])) &&
                    (Null(m["generic_arguments"]) || Strings(m["generic_arguments"])) && NullableBoundedString(m["obsolete_message"],4096) && NullableBoundedString(m["declaring_type"],1024) &&
                    m["parameters"] is JArray parameters && parameters.Count<=64 && parameters.All(p=>Shape(p,"name","type","has_default","default_value","is_params") &&
                        NullableBoundedString(p["name"],256) && BoundedString(p["type"],1024) && Bool(p["has_default"]) && Scalar(p["default_value"]) && Bool(p["is_params"])));
            if(kind=="property")return Shape(data,"found","type_name","member_name","member_type","property_type","can_read","can_write","is_static","is_obsolete","declaring_type") &&
                BoundedString(data["property_type"],1024) && new[]{"can_read","can_write","is_static","is_obsolete"}.All(n=>Bool(data[n])) && NullableBoundedString(data["declaring_type"],1024);
            if(kind=="field")return Shape(data,"found","type_name","member_name","member_type","field_type","is_static","is_readonly","is_constant","constant_value","is_obsolete","declaring_type") &&
                BoundedString(data["field_type"],1024) && new[]{"is_static","is_readonly","is_constant","is_obsolete"}.All(n=>Bool(data[n])) && Scalar(data["constant_value"]) && NullableBoundedString(data["declaring_type"],1024);
            if(kind=="event")return Shape(data,"found","type_name","member_name","member_type","event_handler_type","is_obsolete","declaring_type") &&
                BoundedString(data["event_handler_type"],1024) && Bool(data["is_obsolete"]) && NullableBoundedString(data["declaring_type"],1024);
            return false;
        }
        static bool SourceRead(string command,JToken data,JObject args)
        {
            string target=CandidateGate.SourceParams(command,args);
            if((string)args["action"]=="get_sha")return Shape(data,"uri","path","sha256","lengthBytes","lastModifiedUtc") &&
                String(data["path"]) && (string)data["path"]==target && String(data["uri"]) && (string)data["uri"]=="mcpforunity://path/"+target &&
                String(data["sha256"]) && System.Text.RegularExpressions.Regex.IsMatch((string)data["sha256"],@"\A[0-9a-f]{64}\z") &&
                Integer(data["lengthBytes"],0,131072) && BoundedString(data["lastModifiedUtc"],64);
            if(!(command=="manage_script" ? Shape(data,"uri","path","contents","encodedContents","contentsEncoded") : Shape(data,"path","contents","encodedContents","contentsEncoded")) || !String(data["path"]) ||
                (string)data["path"]!=target || (command=="manage_script" && (string)data["uri"]!="mcpforunity://path/"+target) || !String(data["contents"]) ||
                !Bool(data["contentsEncoded"]))return false;
            string text=(string)data["contents"];
            if(System.Text.Encoding.UTF8.GetByteCount(text)>131072 || (bool)data["contentsEncoded"]!=(text.Length>10000))return false;
            return text.Length>10000 ? String(data["encodedContents"]) && (string)data["encodedContents"]==Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(text)) : Null(data["encodedContents"]);
        }
        static bool PackageVersion(JToken token) => BoundedString(token, 128) &&
            System.Text.RegularExpressions.Regex.IsMatch((string)token, @"\A[0-9][0-9A-Za-z.+-]*\z");
        static bool PackageInfo(JToken data, JObject args)
        {
            return Shape(args, "action", "package") && (string)args["action"] == "get_package_info" && String(args["package"]) && CandidateGate.PackageName((string)args["package"]) &&
                Shape(data, "name", "version", "display_name", "description", "source", "resolved_path", "author", "dependencies", "dependency_count") &&
                JToken.DeepEquals(data["name"], args["package"]) && PackageVersion(data["version"]) &&
                NullableBoundedString(data["display_name"], 4096) && NullableBoundedString(data["description"], 65536) && NullableBoundedString(data["author"], 4096) &&
                BoundedString(data["source"], 128) && BoundedString(data["resolved_path"], 4096) &&
                Count(data["dependency_count"], data["dependencies"]) && Integer(data["dependency_count"], 0, 1024) &&
                All(data["dependencies"], d => Shape(d, "name", "version") && String(d["name"]) && CandidateGate.PackageName((string)d["name"]) && PackageVersion(d["version"])) &&
                System.Text.Encoding.UTF8.GetByteCount(data.ToString(Newtonsoft.Json.Formatting.None)) <= 1024 * 1024;
        }
        static bool BoundedString(JToken t, int max) => String(t) && ((string)t).Length <= max;
        static bool NullableBoundedString(JToken token, int max) => Null(token) || BoundedString(token, max);
        static bool EditorMetadata(string command, JToken data, JObject args)
        {
            if (args == null || args.Count != 0 || data == null || data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            if (command == "get_selection") return Shape(data, "activeObject", "activeGameObject", "activeTransform", "activeInstanceID", "count", "objects", "gameObjects", "assetGUIDs") &&
                NullableBoundedString(data["activeObject"], 4096) && NullableBoundedString(data["activeGameObject"], 4096) && NullableBoundedString(data["activeTransform"], 4096) &&
                Integer(data["activeInstanceID"], int.MinValue, int.MaxValue) && Count(data["count"], data["objects"]) && Integer(data["count"], 0, 1024) &&
                All(data["objects"], o => Shape(o, "name", "type", "instanceID") && NullableBoundedString(o["name"], 4096) && NullableBoundedString(o["type"], 4096) && (Null(o["instanceID"]) || Integer(o["instanceID"], int.MinValue, int.MaxValue))) &&
                data["gameObjects"] is JArray gameObjects && gameObjects.Count <= 1024 && All(gameObjects, o => Shape(o, "name", "instanceID") && NullableBoundedString(o["name"], 4096) && (Null(o["instanceID"]) || Integer(o["instanceID"], int.MinValue, int.MaxValue))) &&
                data["assetGUIDs"] is JArray guids && guids.Count <= 1024 && guids.All(g => BoundedString(g, 128));
            if (command == "get_windows") return data is JArray windows && windows.Count <= 256 && windows.All(w =>
                Shape(w, "title", "typeName", "isFocused", "position", "instanceID") && BoundedString(w["title"], 4096) && BoundedString(w["typeName"], 4096) &&
                Bool(w["isFocused"]) && Components(w["position"], "x", "y", "width", "height") && Integer(w["instanceID"], int.MinValue, int.MaxValue));
            if (command == "get_active_tool") return Shape(data, "activeTool", "isCustom", "pivotMode", "pivotRotation", "handleRotation", "handlePosition") &&
                BoundedString(data["activeTool"], 4096) && Bool(data["isCustom"]) && BoundedString(data["pivotMode"], 128) && BoundedString(data["pivotRotation"], 128) &&
                Components(data["handleRotation"], "x", "y", "z") && Components(data["handlePosition"], "x", "y", "z");
            if (command == "get_prefab_stage") return (Shape(data, "isOpen") && Bool(data["isOpen"]) && !(bool)data["isOpen"]) ||
                (Shape(data, "isOpen", "assetPath", "prefabRootName", "mode", "isDirty") && Bool(data["isOpen"]) && (bool)data["isOpen"] &&
                BoundedString(data["assetPath"], 4096) && NullableBoundedString(data["prefabRootName"], 4096) && BoundedString(data["mode"], 128) && Bool(data["isDirty"]));
            return false;
        }
        static bool ProjectMetadata(string command, JToken data, JObject args)
        {
            if (args == null || args.Count != 0) return false;
            if (command == "get_tags") return data is JArray tags && tags.Count <= 1024 && tags.All(t => BoundedString(t, 512));
            if (command == "get_layers") return data is JObject layers && layers.Count <= 32 && layers.Properties().All(p =>
                int.TryParse(p.Name, out int index) && index >= 0 && index < 32 && index.ToString(System.Globalization.CultureInfo.InvariantCulture) == p.Name && BoundedString(p.Value, 512));
            return Shape(data, "projectRoot", "projectName", "unityVersion", "platform", "assetsPath", "renderPipeline", "activeInputHandler", "packages") &&
                BoundedString(data["projectRoot"], 4096) && BoundedString(data["assetsPath"], 4096) && BoundedString(data["projectName"], 512) &&
                BoundedString(data["unityVersion"], 128) && BoundedString(data["platform"], 128) &&
                new[]{"BuiltIn","Universal","HighDefinition","Custom"}.Contains((string)data["renderPipeline"]) &&
                new[]{"Old","New","Both"}.Contains((string)data["activeInputHandler"]) &&
                Shape(data["packages"], "ugui", "textmeshpro", "inputsystem", "uiToolkit", "screenCapture") && ((JObject)data["packages"]).Properties().All(p => Bool(p.Value));
        }
        static bool Animator(JToken data, JObject args)
        {
            if (data == null || data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            if ((string)args["action"] == "animator_get_parameter")
            {
                if (!Shape(data, "name", "type", "value") || !String(data["name"]) ||
                    !JToken.DeepEquals(data["name"], args["properties"]?["parameter_name"])) return false;
                switch ((string)data["type"])
                {
                    case "Float": return Number(data["value"]);
                    case "Int": return Integer(data["value"], int.MinValue, int.MaxValue);
                    case "Bool": case "Trigger": return Bool(data["value"]);
                    default: return false;
                }
            }
            return Shape(data, "gameObject", "enabled", "speed", "hasController", "controllerName", "applyRootMotion", "updateMode", "cullingMode", "parameterCount", "layerCount", "parameters", "layers", "clips") &&
                String(data["gameObject"]) && Bool(data["enabled"]) && Number(data["speed"]) && Bool(data["hasController"]) &&
                ((bool)data["hasController"] ? String(data["controllerName"]) : Null(data["controllerName"])) &&
                Bool(data["applyRootMotion"]) && String(data["updateMode"]) && String(data["cullingMode"]) &&
                Count(data["parameterCount"], data["parameters"]) && Integer(data["parameterCount"], 0, 256) &&
                Count(data["layerCount"], data["layers"]) && Integer(data["layerCount"], 0, 64) &&
                All(data["parameters"], p => Shape(p, "name", "type", "defaultFloat", "defaultInt", "defaultBool") &&
                    String(p["name"]) && new[]{"Float", "Int", "Bool", "Trigger"}.Contains((string)p["type"]) &&
                    Number(p["defaultFloat"]) && Integer(p["defaultInt"], int.MinValue, int.MaxValue) && Bool(p["defaultBool"])) &&
                All(data["layers"], l => Shape(l, "index", "name", "weight", "currentStateHash", "currentStateNormalizedTime", "currentStateLength", "isInTransition") &&
                    Integer(l["index"], 0, 63) && String(l["name"]) && Number(l["weight"]) && Integer(l["currentStateHash"], int.MinValue, int.MaxValue) &&
                    Number(l["currentStateNormalizedTime"]) && Number(l["currentStateLength"]) && Bool(l["isInTransition"])) &&
                ((JArray)data["layers"]).Select((l, i) => (long)l["index"] == i).All(x => x) &&
                data["clips"] is JArray clips && clips.Count <= 1024 && ((bool)data["hasController"] || clips.Count == 0) &&
                clips.All(x => Shape(x, "name", "length", "frameRate", "isLooping", "wrapMode") && String(x["name"]) &&
                    Number(x["length"]) && (double)x["length"] >= 0 && Number(x["frameRate"]) && (double)x["frameRate"] >= 0 && Bool(x["isLooping"]) && String(x["wrapMode"]));
        }
        static bool InstanceId(JToken id) => Integer(id, int.MinValue, int.MaxValue) && (long)id != 0 && (long)id != -1;
        static bool ObjectSummary(JToken data, JObject args)
        {
            if (args == null || !Shape(data, "instanceID", "name", "tag", "layer", "layerName", "active", "activeInHierarchy", "isStatic", "transform", "parent", "children", "componentTypes", "path") ||
                !InstanceId(data["instanceID"]) || !JToken.DeepEquals(data["instanceID"], args["instanceID"]) ||
                !new[] { "name", "tag", "layerName", "path" }.All(k => String(data[k])) || !Integer(data["layer"], 0, 31) ||
                !new[] { "active", "activeInHierarchy", "isStatic" }.All(k => Bool(data[k])) ||
                !(Null(data["parent"]) || InstanceId(data["parent"])) || !(data["children"] is JArray children) || children.Count > 1024 ||
                !children.All(InstanceId) || children.Select(id => (long)id).Distinct().Count() != children.Count ||
                !(data["componentTypes"] is JArray types) || types.Count > 256 || !types.All(String) ||
                data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            string[] vectors = { "position", "localPosition", "rotation", "localRotation", "scale", "lossyScale" };
            return Shape(data["transform"], vectors) && vectors.All(k => Components(data["transform"][k], "x", "y", "z"));
        }
        static bool ComponentMetadata(JToken data, JObject args)
        {
            if (args == null || !Shape(data, "gameObjectID", "gameObjectName", "components", "cursor", "pageSize", "nextCursor", "totalCount", "hasMore", "includeProperties") ||
                !InstanceId(data["gameObjectID"]) || !JToken.DeepEquals(data["gameObjectID"], args["instanceID"]) || !String(data["gameObjectName"]) ||
                !Integer(data["cursor"], 0, 1000000) || !Integer(data["pageSize"], 1, 100) || !Integer(data["totalCount"], 0, int.MaxValue) ||
                !JToken.DeepEquals(data["cursor"], args["cursor"]) || !JToken.DeepEquals(data["pageSize"], args["pageSize"]) ||
                !Bool(data["hasMore"]) || !Bool(data["includeProperties"]) || (bool)data["includeProperties"] ||
                !(data["components"] is JArray items) || data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            long cursor = (long)data["cursor"], size = (long)data["pageSize"], total = (long)data["totalCount"], next = cursor + items.Count;
            return items.Count == Math.Max(0, Math.Min(size, total - cursor)) && (bool)data["hasMore"] == (next < total) &&
                (next < total ? Integer(data["nextCursor"], next, next) : Null(data["nextCursor"])) &&
                items.All(item => Shape(item, "typeName", "instanceID") && String(item["typeName"]) && InstanceId(item["instanceID"])) &&
                items.Select(item => (long)item["instanceID"]).Distinct().Count() == items.Count;
        }
        static bool FindPage(JToken data, JObject args)
        {
            if (args == null || !Shape(data, "instanceIDs", "pageSize", "cursor", "nextCursor", "totalCount", "hasMore") ||
                !(data["instanceIDs"] is JArray ids) || !Integer(data["pageSize"], 1, 100) ||
                !Integer(data["cursor"], 0, int.MaxValue) || !Integer(data["totalCount"], 0, int.MaxValue) ||
                !Bool(data["hasMore"]) || !Integer(args["pageSize"], 1, 100) || !Integer(args["cursor"], 0, 1000000)) return false;
            long total = (long)data["totalCount"], cursor = (long)data["cursor"], size = (long)data["pageSize"];
            long next = cursor + ids.Count;
            return cursor == Math.Min((long)args["cursor"], total) && size == (long)args["pageSize"] &&
                ids.Count == Math.Min(size, total - cursor) && (bool)data["hasMore"] == (next < total) &&
                (next < total ? Integer(data["nextCursor"], next, next) : Null(data["nextCursor"])) &&
                ids.All(id => Integer(id, int.MinValue, int.MaxValue) && (long)id != 0) &&
                ids.Select(id => (long)id).Distinct().Count() == ids.Count &&
                ((string)args["searchMethod"] != "by_id" || (total <= 1 && ids.All(id =>
                    ((long)id).ToString(System.Globalization.CultureInfo.InvariantCulture) == (string)args["searchTerm"])));
        }
        static bool SceneMetadata(JToken data, JObject args)
        {
            if ((string)args?["action"] == "get_hierarchy") return HierarchyPage(data, args);
            if ((string)args?["action"] == "validate") return SceneValidation(data, args);
            if (!Shape(args, "action") || !String(args["action"]) || data == null ||
                data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            switch ((string)args["action"])
            {
                case "get_active": return Shape(data, "name", "path", "buildIndex", "isDirty", "isLoaded", "rootCount") && SceneInfo(data);
                case "get_loaded_scenes": return Shape(data, "scenes") && data["scenes"] is JArray scenes && scenes.Count <= 1024 &&
                    scenes.All(s => Shape(s, "name", "path", "buildIndex", "isDirty", "isLoaded", "rootCount", "isActive") && SceneInfo(s) && Bool(s["isActive"])) &&
                    scenes.Count(s => (bool)s["isActive"]) <= 1;
                case "get_build_settings": return data is JArray builds && builds.Count <= 1024 &&
                    builds.Select((s, i) => Shape(s, "path", "guid", "enabled", "buildIndex") && String(s["path"]) &&
                        String(s["guid"]) && Bool(s["enabled"]) && s["buildIndex"]?.Type == JTokenType.Integer && (long)s["buildIndex"] == i).All(ok => ok);
                default: return false;
            }
        }
        static bool SceneValidation(JToken data, JObject args)
        {
            if (!Shape(args, "action", "autoRepair") || !Bool(args["autoRepair"]) || (bool)args["autoRepair"] ||
                !Shape(data, "sceneName", "totalIssues", "missingScripts", "brokenPrefabs", "repaired", "issues", "truncated", "note") ||
                !String(data["sceneName"]) || !Integer(data["repaired"], 0, 0) || !Bool(data["truncated"]) ||
                !new[] { "totalIssues", "missingScripts", "brokenPrefabs" }.All(k => Integer(data[k], 0, int.MaxValue)) ||
                !(data["issues"] is JArray issues) || issues.Count > 200 ||
                data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            long missing = (long)data["missingScripts"], broken = (long)data["brokenPrefabs"], total = (long)data["totalIssues"];
            if (total != missing + broken || (bool)data["truncated"] != (total > issues.Count) ||
                !(broken > 0 ? String(data["note"]) : Null(data["note"]))) return false;
            foreach (JToken issue in issues)
            {
                if (!(issue is JObject) || !String(issue["type"]) || !String(issue["gameObject"]) || !String(issue["path"])) return false;
                if ((string)issue["type"] == "missing_script")
                { if (!Shape(issue, "type", "gameObject", "path", "count") || !Integer(issue["count"], 1, int.MaxValue)) return false; }
                else if ((string)issue["type"] == "broken_prefab")
                { if (!Shape(issue, "type", "gameObject", "path", "status") || !String(issue["status"]) || (string)issue["status"] != "MissingAsset") return false; }
                else return false;
            }
            long shownMissing = issues.Where(i => (string)i["type"] == "missing_script").Sum(i => (long)i["count"]);
            long shownBroken = issues.Count(i => (string)i["type"] == "broken_prefab");
            return shownMissing <= missing && shownBroken <= broken &&
                (issues.Count == 200 || (shownMissing == missing && shownBroken == broken));
        }
        static bool Integer(JToken value, long min, long max) => value?.Type == JTokenType.Integer && (long)value >= min && (long)value <= max;
        static bool HierarchyPage(JToken data, JObject args)
        {
            if (!Shape(data, "scope", "cursor", "pageSize", "next_cursor", "truncated", "total", "items") ||
                !String(data["scope"]) || !Bool(data["truncated"]) || !Integer(data["total"], 0, int.MaxValue) ||
                !Integer(data["cursor"], 0, int.MaxValue) || !Integer(data["pageSize"], 1, 100) ||
                !(data["items"] is JArray items) || data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            long total = (long)data["total"], cursor = (long)data["cursor"], size = (long)data["pageSize"];
            if ((string)data["scope"] != (args.ContainsKey("parent") ? "children" : "roots") ||
                cursor != Math.Min((long?)args["cursor"] ?? 0, total) || size != (long)args["pageSize"] ||
                items.Count != Math.Min(size, total - cursor) || (bool)data["truncated"] != (cursor + items.Count < total)) return false;
            if ((bool)data["truncated"] ? !String(data["next_cursor"]) ||
                (string)data["next_cursor"] != (cursor + items.Count).ToString(System.Globalization.CultureInfo.InvariantCulture) :
                !Null(data["next_cursor"])) return false;
            bool transform = (bool?)args["includeTransform"] ?? false;
            return items.All(item => HierarchyItem(item, transform)) &&
                items.Select(item => (long)item["instanceID"]).Distinct().Count() == items.Count;
        }
        static bool HierarchyItem(JToken item, bool transform)
        {
            string[] fields = { "name", "instanceID", "activeSelf", "activeInHierarchy", "tag", "layer", "isStatic", "path",
                "childCount", "childrenTruncated", "childrenCursor", "childrenPageSizeDefault", "componentTypes" };
            if (!Shape(item, transform ? fields.Concat(new[] { "transform" }).ToArray() : fields) ||
                !String(item["name"]) || !Integer(item["instanceID"], int.MinValue, int.MaxValue) || (long)item["instanceID"] == 0 ||
                !Bool(item["activeSelf"]) || !Bool(item["activeInHierarchy"]) || !Bool(item["isStatic"]) ||
                !String(item["tag"]) || !String(item["path"]) || !Integer(item["layer"], 0, 31) ||
                !Integer(item["childCount"], 0, int.MaxValue) || !Bool(item["childrenTruncated"]) ||
                (bool)item["childrenTruncated"] != ((long)item["childCount"] > 0) ||
                !Integer(item["childrenPageSizeDefault"], 200, 200) || !All(item["componentTypes"], String)) return false;
            if ((long)item["childCount"] > 0 ? !String(item["childrenCursor"]) || (string)item["childrenCursor"] != "0" : !Null(item["childrenCursor"])) return false;
            return !transform || (Shape(item["transform"], "position", "rotation", "scale") &&
                new[] { "position", "rotation", "scale" }.All(k => item["transform"][k] is JArray values && values.Count == 3 && values.All(Number)));
        }
        static bool SceneInfo(JToken data) => String(data["name"]) && String(data["path"]) && Bool(data["isDirty"]) &&
            Bool(data["isLoaded"]) && data["buildIndex"]?.Type == JTokenType.Integer && (long)data["buildIndex"] >= -1 &&
            data["rootCount"]?.Type == JTokenType.Integer && (long)data["rootCount"] >= 0;
        static bool ConsolePage(JToken data, JObject args)
        {
            if (args == null || !Shape(data, "cursor", "pageSize", "nextCursor", "truncated", "total", "items") ||
                !Bool(data["truncated"]) || data["cursor"]?.Type != JTokenType.Integer ||
                data["pageSize"]?.Type != JTokenType.Integer || data["total"]?.Type != JTokenType.Integer ||
                !(data["items"] is JArray items) || data.ToString(Newtonsoft.Json.Formatting.None).Length > 1024 * 1024) return false;
            long cursor = (long)data["cursor"], size = (long)data["pageSize"], total = (long)data["total"];
            if (cursor != ((long?)args["cursor"] ?? 0) || size != (long)args["pageSize"] ||
                cursor < 0 || size < 1 || size > 100 || items.Count > size || total < items.Count) return false;
            bool truncated = (bool)data["truncated"];
            // Upstream stops after one extra match; total is a lower bound when truncated.
            if (truncated)
            {
                if (items.Count != size || total != cursor + size + 1 || !String(data["nextCursor"]) ||
                    (string)data["nextCursor"] != (cursor + size).ToString(System.Globalization.CultureInfo.InvariantCulture)) return false;
            }
            else if (!Null(data["nextCursor"]) || total > cursor + size || items.Count != Math.Max(0, total - cursor)) return false;
            return items.All(item => Shape(item, "type", "message", "file", "line", "stackTrace") &&
                String(item["type"]) && new[] { "Error", "Warning", "Log", "Exception", "Assert" }.Contains((string)item["type"]) &&
                String(item["message"]) && NullableString(item["file"]) && item["line"]?.Type == JTokenType.Integer &&
                NullableString(item["stackTrace"]) && ((bool)args["includeStacktrace"] || Null(item["stackTrace"])));
        }
        static bool Property(JToken property)
        {
            if (!Shape(property, "name", "type", "description", "value") || !String(property["name"]) ||
                !String(property["type"]) || !String(property["description"])) return false;
            var value = property["value"];
            switch ((string)property["type"])
            {
                case "Color": return Null(value) || Components(value, "r", "g", "b", "a");
                case "Vector": return Null(value) || Components(value, "x", "y", "z", "w");
                case "Float": case "Range": return Null(value) || Number(value);
                // TexEnv = pre-Unity-6 ShaderUtil; Texture = Unity-6 Shader API.
                // A literal texture name with this prefix is indistinguishable
                // from the native caught-exception marker: conservatively deny.
                case "TexEnv": case "Texture": return Null(value) || (String(value) &&
                    !((string)value).StartsWith("<error:", StringComparison.Ordinal));
                // Native switches do not read Int; they explicitly leave null.
                case "Int": return Null(value);
                default: return false;
            }
        }
        static bool Layer(JToken layer) => Shape(layer, "index", "name", "stateCount", "states") &&
            layer["index"]?.Type == JTokenType.Integer && (long)layer["index"] >= 0 && String(layer["name"]) &&
            Count(layer["stateCount"], layer["states"]) && All(layer["states"], State);
        static bool State(JToken state) => Shape(state, "name", "speed", "hasMotion", "motionName", "isDefault", "transitionCount", "transitions") &&
            String(state["name"]) && Number(state["speed"]) && Bool(state["hasMotion"]) && NullableString(state["motionName"]) &&
            Bool(state["isDefault"]) && Count(state["transitionCount"], state["transitions"]) && All(state["transitions"], Transition);
        static bool Transition(JToken transition) => Shape(transition, "destinationState", "hasExitTime", "exitTime", "duration", "conditionCount", "conditions") &&
            NullableString(transition["destinationState"]) && Bool(transition["hasExitTime"]) && Number(transition["exitTime"]) &&
            Number(transition["duration"]) && Count(transition["conditionCount"], transition["conditions"]) && All(transition["conditions"], Condition);
        static bool Condition(JToken condition) => Shape(condition, "parameter", "mode", "threshold") &&
            String(condition["parameter"]) && String(condition["mode"]) && Number(condition["threshold"]);
        static bool Parameter(JToken parameter) => Shape(parameter, "name", "type", "defaultFloat", "defaultInt", "defaultBool") &&
            String(parameter["name"]) && String(parameter["type"]) && Number(parameter["defaultFloat"]) &&
            parameter["defaultInt"]?.Type == JTokenType.Integer && Bool(parameter["defaultBool"]);
    }
}
