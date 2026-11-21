// Stand-in Unity APIs only. No fake GetInstanceIDCompat: use the pinned Coplay ZIP.
using System;
using System.Linq;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
namespace UnityEngine {
 public class Object { public int GetInstanceID()=>37; public static void DestroyImmediate(Object o)=>throw new Exception(); }
 public enum TextureFormat { RGB24 }
 public struct Rect {public Rect(int a,int b,int c,int d){} }
 public class Texture2D:Object {public int width,height; public Texture2D(int w,int h,TextureFormat f,bool m){} public void ReadPixels(Rect r,int a,int b){} public void Apply(){} public byte[] EncodeToPNG()=>null;}
 public class RenderTexture:Object {public int width,height; public static RenderTexture active; public static RenderTexture GetTemporary(int w,int h)=>null; public static void ReleaseTemporary(RenderTexture r){} }
 public static class Graphics {public static void Blit(Texture2D a,RenderTexture b){} }
}
namespace UnityEditor {
 public static class EditorUtility { public static UnityEngine.Object InstanceIDToObject(int id)=>null; }
 public static class AssetDatabase {
  public static int Loads; public static string AssetPathToGUID(string p)=>p=="Assets/a.asset"?"aaa":"";public static string GUIDToAssetPath(string g)=>g=="aaa"?"Assets/a.asset":"";
  public static bool IsValidFolder(string p)=>p=="Assets"; public static string[] FindAssets(string f,string[] paths)=>new[]{"aaa"};public static Type GetMainAssetTypeAtPath(string p)=>typeof(UnityEngine.Object);public static T LoadAssetAtPath<T>(string p) where T:UnityEngine.Object,new(){Loads++;return new T();}
 }
 public static class AssetPreview {public static UnityEngine.Texture2D GetAssetPreview(UnityEngine.Object o)=>throw new Exception("unexpected preview");}
}
namespace MCPForUnity.Editor.Helpers { public static class AssetPathUtility {public static string SanitizeAssetPath(string p)=>p;} public static class McpLog {public static void Warn(string s){} } }
static class Program {static int Main(){var blocked=CandidateScopedAssets.Info("Assets/a.asset",()=>false); if(!(blocked is ErrorResponse)||UnityEditor.AssetDatabase.Loads!=0)return 1;
 var ok=CandidateScopedAssets.Info("Assets/a.asset",()=>true) as SuccessResponse; if(ok==null||UnityEditor.AssetDatabase.Loads!=1)return 2;
 var id=ok.Data.GetType().GetProperty("instanceID").GetValue(ok.Data); if(!Equals(id,37))return 3; Console.WriteLine("PASS: denied access loads zero; approved read returns ID from Coplay runtime shim");return 0;}}
