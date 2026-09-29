// Explicit dependency doubles for native-method characterization; not Unity.
using System;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;
namespace MCPForUnity.Editor.Helpers {
 public static class AssetPathUtility {public static string SanitizeAssetPath(string path)=>path;}
 public static class ObjectResolver {public static UnityEngine.Object Resolve(JObject p,Type t){string path=(string)p["find"];if(AssetDatabase.Objects.TryGetValue(path,out var o))return o;if(t==typeof(Material))return AssetDatabase.Asset;foreach(var obj in GlobalObjectId.Objects.Values)if(obj is Renderer r && t==typeof(GameObject))return r.gameObject;return null;}}
 public static class UnityJsonSerializer {public static object Instance=new object();}
 public static class MaterialOps {public static string ResolvePropertyName(Material m,string n)=>n;public static bool TrySetShaderProperty(Material m,string p,JToken v,object serializer){m.Json=v.ToString();return true;}}
}
// Satisfy the shared callback-double type identity without loading the other Main.
static class WriteUnityCases {}
