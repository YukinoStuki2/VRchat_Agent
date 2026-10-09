// Local consent policy is real; inventory and local operator are explicit doubles.
using System;
using System.Reflection;
using Yukino.VRChatAgent;
internal static class PluginTrustCases
{
 static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
 static object trust;static string context=new string('a',64);static int revoked;static Action capture=null;
 static object Call(string method,params object[] args)=>trust.GetType().GetMethod(method,BindingFlags.Instance|BindingFlags.NonPublic).Invoke(trust,args);
 static string Evidence(string purpose="asset_load_callbacks",string target="AssetReads/Assets/Scope")=>(string)Call("Evidence",purpose,target);
 static int Main(){try{
  var type=typeof(CandidateGate).Assembly.GetType("Yukino.VRChatAgent.ProjectPluginTrust");
  Check(type!=null,"project_plugin_trust_policy_missing");
  trust=Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.NonPublic,null,new object[]{(Func<string>)(()=>{capture?.Invoke();return context;}),(Action)(()=>revoked++)},null);
  Check(Evidence()==null,"cold trust enabled");
  string token=(string)Call("StageLocal");Check(token!=null&&Evidence()==null,"staging granted or unavailable");
  Check(!(bool)Call("ConfirmLocal","wrong-token")&&Evidence()==null,"wrong token accepted");
  token=(string)Call("StageLocal");Check((bool)Call("ConfirmLocal",token),"separate local trust confirmation failed");
  string asset=Evidence();Check(asset!=null&&asset.Length==64,"confirmed trust unavailable");
  Check(Evidence("asset_load_callbacks","AssetReads/Assets/Other")!=asset,"target not bound");
  string prefab=Evidence("asset_load_callbacks","PrefabReads/Assets/a.prefab"),contents=Evidence("prefab_contents_callbacks","PrefabReads/Assets/a.prefab"),discovery=Evidence("test_discovery_callbacks","TestDiscovery/EditMode");
  Check(prefab!=null&&contents!=null&&discovery!=null&&prefab!=contents&&discovery!=asset,"effect/target identity mixed");
  foreach(var pair in new[]{new[]{"unknown","AssetReads/Assets/Scope"},new[]{"prefab_contents_callbacks","AssetReads/Assets/Scope"},new[]{"test_discovery_callbacks","TestDiscovery/all"},new[]{"asset_load_callbacks","Assets/a.prefab"},new[]{"asset_load_callbacks","AssetReads/Assets/../Other"}})
   Check(Evidence(pair[0],pair[1])==null,"invalid target or purpose authorized");
  Console.WriteLine("PASS PT001 local_consent_inert_until_confirmed_effect_and_target_bound");
  foreach(string changed in new[]{null,"",new string('b',64),"not-a-fingerprint"})
  {
   context=new string('a',64);token=(string)Call("StageLocal");Check((bool)Call("ConfirmLocal",token),"fixture consent failed");string previous=Evidence();
   context=changed;Check(Evidence()==null,"changed context retained consent");context=new string('a',64);Check(Evidence()==null,"old context revived consent");
   token=(string)Call("StageLocal");Check((bool)Call("ConfirmLocal",token)&&Evidence()!=previous,"re-consent reused old evidence");
   Call("Revoke");Check(Evidence()==null&&!(bool)Call("ConfirmLocal",token),"revocation retained grant");
  }
  context=null;Check(Call("StageLocal")==null,"missing context staged");context=new string('a',64);
  token=(string)Call("StageLocal");capture=()=>throw new Exception("fixture-private");Check(!(bool)Call("ConfirmLocal",token),"throwing context accepted");capture=null;Check(Evidence()==null,"fault retained consent");
  Console.WriteLine("PASS PT002 changed_missing_throwing_context_and_revocation_never_revive");
  foreach(string phase in new[]{"stage","confirm","evidence"})
  foreach(bool replace in new[]{false,true})
  {
   token=(string)Call("StageLocal");if(phase=="evidence")Check((bool)Call("ConfirmLocal",token),"fixture initial consent failed");
   capture=()=>{capture=null;Call("Revoke");if(replace){string nested=(string)Call("StageLocal");Check((bool)Call("ConfirmLocal",nested),"fixture nested consent failed");}};
   if(phase=="stage")Check(Call("StageLocal")==null,"stage revived consent after reentry");
   if(phase=="confirm")Check(!(bool)Call("ConfirmLocal",token),"confirm accepted reentry");
   if(phase=="evidence")Check(Evidence()==null,"evidence accepted reentry");
   capture=null;Check(Evidence()==null,"nested consent survived rejected outer operation");
  }
  Console.WriteLine("PASS PT003 reentrant_revocation_or_replacement_cannot_restore_consent");
  return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
