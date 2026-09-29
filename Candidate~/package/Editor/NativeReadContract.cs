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

        internal static bool Valid(string command, JObject result)
        {
            if (result == null || result["success"]?.Type != JTokenType.Boolean || !(bool)result["success"]) return false;
            if (!(Shape(result, "success", "data") ||
                (Shape(result, "success", "message", "data") && String(result["message"])))) return false;
            var data = result["data"];
            if (command == "manage_material") return Shape(data, "material", "shader", "properties") &&
                String(data["material"]) && String(data["shader"]) && All(data["properties"], Property);
            if (command == "manage_animation") return Shape(data, "path", "name", "layerCount", "parameterCount", "layers", "parameters") &&
                String(data["path"]) && String(data["name"]) && Count(data["layerCount"], data["layers"]) &&
                Count(data["parameterCount"], data["parameters"]) && All(data["layers"], Layer) && All(data["parameters"], Parameter);
            return false;
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
