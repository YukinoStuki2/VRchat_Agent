// Additional Unity API doubles only; actual shipped reader is compiled unchanged.
using System;
using System.Linq;
namespace UnityEditor {
 public static partial class AssetDatabase {
  public static string GUIDToAssetPath(string guid)=>guid==new string('a',32)?ClipPath:"";
  public static bool IsValidFolder(string p)=>p=="Assets/Scope";
  public static string[] FindAssets(string filter,string[] folders)=>new[]{AssetPathToGUID(ClipPath)};
 }
 public static class AssetPreview {public static UnityEngine.Texture2D GetAssetPreview(UnityEngine.Object o)=>throw new Exception("preview_forbidden");}
}
namespace UnityEngine {
 public struct Rect {public Rect(int a,int b,int c,int d){}}
 public enum TextureFormat {RGB24}
 public class Texture2D:Object {
  public int width=1,height=1;
  public Texture2D(int w,int h,TextureFormat f,bool mip)=>throw new Exception("preview_forbidden");
  public void ReadPixels(Rect r,int a,int b)=>throw new Exception("preview_forbidden");
  public void Apply()=>throw new Exception("preview_forbidden");
  public byte[] EncodeToPNG()=>throw new Exception("preview_forbidden");
 }
 public class RenderTexture:Object {
  public static RenderTexture active;public int width=1,height=1;
  public static RenderTexture GetTemporary(int w,int h)=>throw new Exception("preview_forbidden");
  public static void ReleaseTemporary(RenderTexture r)=>throw new Exception("preview_forbidden");
 }
 public static class Graphics {public static void Blit(Texture2D a,RenderTexture b)=>throw new Exception("preview_forbidden");}
}
namespace MCPForUnity.Editor.Helpers {
 public static class AssetPathUtility {public static string SanitizeAssetPath(string p)=>p;}
 public static class McpLog {public static void Warn(string value)=>throw new Exception("unexpected_native_warning");public static void Error(string value)=>throw new Exception("unexpected_native_error");}
 public static class Extensions {public static int GetInstanceIDCompat(this UnityEngine.Object o)=>o.GetInstanceID();}
}

namespace MCPForUnity.Runtime.Helpers {public static class Compatibility {public static int GetInstanceIDCompat(this UnityEngine.GameObject o)=>o.GetInstanceID();}}
namespace UnityEditor {
 public enum PrefabAssetType {Regular,Variant}
 public static class PrefabUtility {
  public static int Loads,Unloads;
  public static UnityEngine.GameObject LoadPrefabContents(string path){Loads++;return (UnityEngine.GameObject)AssetDatabase.Asset;}
  public static void UnloadPrefabContents(UnityEngine.GameObject obj){if(!ReferenceEquals(obj,AssetDatabase.Asset))throw new Exception("wrong_owner");Unloads++;}
  public static PrefabAssetType GetPrefabAssetType(UnityEngine.GameObject obj)=>PrefabAssetType.Regular;
  public static UnityEngine.GameObject GetCorrespondingObjectFromSource(UnityEngine.GameObject obj)=>obj;
  public static bool IsAnyPrefabInstanceRoot(UnityEngine.GameObject obj)=>false;
 }
}
