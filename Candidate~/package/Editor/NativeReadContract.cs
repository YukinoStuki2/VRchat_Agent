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

        internal static bool Valid(string command, JObject result, JObject args = null)
        {
            if (result == null || result["success"]?.Type != JTokenType.Boolean || !(bool)result["success"]) return false;
            if (!(Shape(result, "success", "data") ||
                (Shape(result, "success", "message", "data") && String(result["message"])))) return false;
            var data = result["data"];
            if (command == "read_console") return ConsolePage(data, args);
            if (command == "manage_scene") return SceneMetadata(data, args);
            if (command == "manage_material") return Shape(data, "material", "shader", "properties") &&
                String(data["material"]) && String(data["shader"]) && All(data["properties"], Property);
            if (command == "manage_animation") return Shape(data, "path", "name", "layerCount", "parameterCount", "layers", "parameters") &&
                String(data["path"]) && String(data["name"]) && Count(data["layerCount"], data["layers"]) &&
                Count(data["parameterCount"], data["parameters"]) && All(data["layers"], Layer) && All(data["parameters"], Parameter);
            return false;
        }
        static bool SceneMetadata(JToken data, JObject args)
        {
            if ((string)args?["action"] == "get_hierarchy") return HierarchyPage(data, args);
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
