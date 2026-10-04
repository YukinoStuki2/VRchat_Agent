// Actual pinned animator/resolver handlers; only Unity APIs and unused mutation branches are doubles.
using System;using System.Linq;using Newtonsoft.Json.Linq;using Yukino.VRChatAgent;
namespace UnityEngine {
 public class Material:Object{} public class Texture:Object{} public class ScriptableObject:Object{} public class AudioClip:Object{} public class Font:Object{} public class Shader:Object{} public class ComputeShader:Object{}
 public enum AnimatorControllerParameterType {Float,Int,Bool,Trigger}
 public class AnimatorControllerParameter {public string name="Speed";public AnimatorControllerParameterType type;public float defaultFloat;public int defaultInt;public bool defaultBool;}
 public class AnimationClip:Object {public float length=1,frameRate=60;public bool isLooping=true;public string wrapMode="Loop";}
 public class RuntimeAnimatorController:Object {public AnimationClip[] animationClips={new AnimationClip{name="Walk"}};}
 public struct AnimatorStateInfo {public int fullPathHash;public float normalizedTime,length;}
 public class Animator:Component {
  public bool enabled=true,applyRootMotion;public float speed=1;public string updateMode="Normal",cullingMode="AlwaysAnimate";
  public RuntimeAnimatorController runtimeAnimatorController=new RuntimeAnimatorController{name="Fixture"};
  public AnimatorControllerParameter[] parameters={new AnimatorControllerParameter{type=AnimatorControllerParameterType.Float}};
  public int parameterCount=>parameters.Length;public int layerCount=1;
  public AnimatorControllerParameter GetParameter(int i)=>parameters[i];public bool IsInTransition(int i)=>false;
  public AnimatorStateInfo GetNextAnimatorStateInfo(int i)=>new AnimatorStateInfo{fullPathHash=42,length=1};
  public AnimatorStateInfo GetCurrentAnimatorStateInfo(int i)=>GetNextAnimatorStateInfo(i);
  public string GetLayerName(int i)=>"Base";public float GetLayerWeight(int i)=>1;
  public float GetFloat(string n)=>0.5f;public int GetInteger(string n)=>3;public bool GetBool(string n)=>true;
 }
}
namespace UnityEditor {public static class AssetDatabase {
 public static UnityEngine.Object LoadAssetAtPath(string p,Type t)=>throw new Exception("asset load");
 public static T LoadAssetAtPath<T>(string p)=>throw new Exception("asset load");
 public static string[] FindAssets(string p)=>throw new Exception("asset search");
 public static string GUIDToAssetPath(string p)=>throw new Exception("asset lookup");
}}
namespace MCPForUnity.Editor.Tools.Animation {
internal static class AnimatorControl {public static object Play(JObject p)=>throw new Exception("ungranted native branch");public static object Crossfade(JObject p)=>throw new Exception("ungranted native branch");public static object SetParameter(JObject p)=>throw new Exception("ungranted native branch");public static object SetSpeed(JObject p)=>throw new Exception("ungranted native branch");public static object SetEnabled(JObject p)=>throw new Exception("ungranted native branch");}
internal static class ControllerCreate {public static object Create(JObject p)=>throw new Exception("ungranted native branch");public static object AddState(JObject p)=>throw new Exception("ungranted native branch");public static object AddTransition(JObject p)=>throw new Exception("ungranted native branch");public static object AddParameter(JObject p)=>throw new Exception("ungranted native branch");public static object GetInfo(JObject p)=>throw new Exception("ungranted native branch");public static object AssignToGameObject(JObject p)=>throw new Exception("ungranted native branch");}
internal static class ControllerLayers {public static object AddLayer(JObject p)=>throw new Exception("ungranted native branch");public static object RemoveLayer(JObject p)=>throw new Exception("ungranted native branch");public static object SetLayerWeight(JObject p)=>throw new Exception("ungranted native branch");}
internal static class ControllerBlendTrees {public static object CreateBlendTree1D(JObject p)=>throw new Exception("ungranted native branch");public static object CreateBlendTree2D(JObject p)=>throw new Exception("ungranted native branch");public static object AddBlendTreeChild(JObject p)=>throw new Exception("ungranted native branch");}
internal static class ClipCreate {public static object Create(JObject p)=>throw new Exception("ungranted native branch");public static object GetInfo(JObject p)=>throw new Exception("ungranted native branch");public static object AddCurve(JObject p)=>throw new Exception("ungranted native branch");public static object SetCurve(JObject p)=>throw new Exception("ungranted native branch");public static object SetVectorCurve(JObject p)=>throw new Exception("ungranted native branch");public static object Assign(JObject p)=>throw new Exception("ungranted native branch");public static object AddEvent(JObject p)=>throw new Exception("ungranted native branch");public static object RemoveEvent(JObject p)=>throw new Exception("ungranted native branch");}
internal static class ClipPresets {public static object CreatePreset(JObject p)=>throw new Exception("ungranted native branch");}
}
internal static class AnimatorNativeFixture {
 static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
 static JObject Wire(string kind,string id,JObject body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="fixture-project",["client_id"]="fixture-client",["connection_id"]="fixture-connection",["task_id"]="animator-task",["plan_id"]=id,["body"]=body};
 public static void Run(){
  var go=UnityEngine.HierarchyFixture.Roots[0];var animator=new UnityEngine.Animator();go.Extra=new[]{animator};int calls=0;
  var gate=new CandidateGate(()=>100,()=>"fixture-project",()=>"fixture-connection",p=>"live-scenes",(cmd,args)=>{calls++;var result=JObject.FromObject(MCPForUnity.Editor.Tools.Animation.ManageAnimation.HandleCommand(args));return NativeReadContract.Valid(cmd,result,args)?result:new JObject{["success"]=false};});
  foreach(string action in new[]{"animator_get_info","animator_get_parameter"}){
   var manifest=new JObject{["operations"]=new JArray(new JObject{["command"]="manage_animation",["action"]=action}),["targets"]=new JArray("Scenes"),["ttl_seconds"]=60};
   Check(!(bool)gate.Dispatch(Wire("prepare","",manifest))["success"],"animator default open");gate.SetCapability("manage_animation",action,true);
   JObject Ready(){var p=gate.Dispatch(Wire("prepare","",manifest));Check((bool)p["success"],"animator prepare: "+p);Check(gate.Approve((string)p["data"]["plan_id"],(string)p["data"]["digest"]),"approve");return p;}
   JObject Exec(JObject p,JObject a)=>gate.Dispatch(Wire("execute",(string)p["data"]["plan_id"],new JObject{["command"]="manage_animation",["params"]=a}));
   var args=new JObject{["action"]=action,["target"]="11",["searchMethod"]="by_id"};if(action=="animator_get_parameter")args["properties"]=new JObject{["parameter_name"]="Speed"};
   var plan=Ready();Check((bool)Exec(plan,args)["success"],"native animator "+action);
   foreach(var change in new[]{new JObject{["target"]=11},new JObject{["target"]="+11"},new JObject{["target"]="0"},new JObject{["target"]="-1"},new JObject{["target"]="Assets/X.prefab"},new JObject{["searchMethod"]="by_name"},new JObject{["controllerPath"]="Assets/X.controller"},new JObject{["properties"]="{}"},new JObject{["properties"]=new JObject{["parameter_name"]="Speed",["value"]=1}},new JObject{["action"]="animator_play"}}){
    plan=Ready();var bad=(JObject)args.DeepClone();bad.Merge(change);int before=calls;Check(!(bool)Exec(plan,bad)["success"]&&calls==before,"unsafe animator args "+bad);
   }
   plan=Ready();var good=JObject.FromObject(MCPForUnity.Editor.Tools.Animation.ManageAnimation.HandleCommand(args));Check(NativeReadContract.Valid("manage_animation",good,args),"native contract");
   var wrong=(JObject)good.DeepClone();wrong["data"]["unexpected"]=true;Check(!NativeReadContract.Valid("manage_animation",wrong,args),"unexpected output");
   if(action=="animator_get_parameter"){
    foreach(var kind in (UnityEngine.AnimatorControllerParameterType[])Enum.GetValues(typeof(UnityEngine.AnimatorControllerParameterType))){animator.parameters[0].type=kind;Check((bool)Exec(plan,args)["success"],"parameter type "+kind);}
    wrong=(JObject)good.DeepClone();wrong["data"]["name"]="other";Check(!NativeReadContract.Valid("manage_animation",wrong,args),"wrong parameter");
   }
   gate.StopAll("fixture stop");Check(!(bool)Exec(plan,args)["success"],"animator stop");
  }
  go.Extra=Array.Empty<UnityEngine.Component>();
  Console.WriteLine("PASS NS013 pinned full AnimatorRead/ManageAnimation/ObjectResolver reads; strict two-operation gate and response contracts, no mutation/assets");
 }
}
