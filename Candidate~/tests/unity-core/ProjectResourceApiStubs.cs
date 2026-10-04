using Newtonsoft.Json.Linq;
namespace MCPForUnity.Editor.Tools {
 public static class ManagePackages {
  public static int Calls;
  public static object HandleCommand(JObject p){Calls++;return new {success=true,data=new {name=(string)p["package"],version="1.0.0",display_name="Fixture package",description="Local metadata fixture",source="Registry",resolved_path="/Fixture/Package",author=(string)null,dependencies=new object[0],dependency_count=0}};}
 }
}
namespace MCPForUnity.Editor.Resources.Project {
 public static class MetadataFixture {
  public static int Calls;
  public static object Read(string command){Calls++;return new {success=true,data=command=="get_tags"?(object)new[]{"Untagged"}:command=="get_layers"?new JObject{["0"]="Default"}:(object)new {projectRoot="/Fixture",projectName="Fixture",unityVersion="2022.3",platform="StandaloneWindows64",assetsPath="/Fixture/Assets",renderPipeline="BuiltIn",activeInputHandler="Old",packages=new {ugui=false,textmeshpro=false,inputsystem=false,uiToolkit=true,screenCapture=true}}};}
 }
 public static class ProjectInfo {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_project_info");}
 public static class Tags {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_tags");}
 public static class Layers {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_layers");}
}
namespace MCPForUnity.Editor.Resources.Editor {
 public static class MetadataFixture {
  public static int Calls;
  public static object Read(string command){Calls++;object data;
   if(command=="get_selection")data=new {activeObject=(string)null,activeGameObject=(string)null,activeTransform=(string)null,activeInstanceID=0,count=0,objects=new object[0],gameObjects=new object[0],assetGUIDs=new string[0]};
   else if(command=="get_windows")data=new object[0];
   else if(command=="get_active_tool"){var v=new{x=0,y=0,z=0};data=new{activeTool="Move",isCustom=false,pivotMode="Center",pivotRotation="Global",handleRotation=v,handlePosition=v};}
   else data=new {isOpen=false};
   return new {success=true,data};
  }
 }
 public static class Selection {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_selection");}
 public static class Windows {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_windows");}
 public static class ActiveTool {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_active_tool");}
 public static class GetPrefabStage {public static object HandleCommand(JObject p)=>MetadataFixture.Read("get_prefab_stage");}
}

namespace MCPForUnity.Editor.Resources.MenuItems {
 public static class GetMenuItems {public static int Calls;public static object HandleCommand(JObject p){Calls++;return new {success=true,data=new[]{"Tools/Fixture"}};}}
}
