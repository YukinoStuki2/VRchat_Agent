// Real policy and CandidateSession; native SessionState is an explicit fixture.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using Yukino.VRChatAgent;
internal static class CleanupLifetimeCases
{
 static void Need(bool value,string why){if(!value)throw new Exception(why);}
 const string Prefix="Yukino.VRChatAgent.EffectCleanup.v1.";
 static readonly Dictionary<string,string> values=new Dictionary<string,string>();
 static EffectCleanupLedger Ledger()=>new EffectCleanupLedger(k=>values.TryGetValue(k,out var v)?v:"",(k,v)=>values[k]=v);
 static void Refused(Action action){bool denied=false;try{action();}catch{denied=true;}Need(denied,"required denial absent");}
 sealed class Isolated : AssemblyLoadContext
 {
  internal Isolated():base(true){}
  protected override Assembly Load(AssemblyName name){foreach(var a in Default.Assemblies)if(a.GetName().Name==name.Name)return a;return null;}
 }
 [MethodImpl(MethodImplOptions.NoInlining)]
 static WeakReference AbandonInIsolatedLoad()
 {
  var context=new Isolated();var reference=new WeakReference(context);
  var assembly=context.LoadFromAssemblyPath(typeof(CandidateGate).Assembly.Location);
  var type=assembly.GetType("Yukino.VRChatAgent.EffectCleanupLedger",true);
  var owner=Activator.CreateInstance(type,new object[]{(Func<string,string>)(k=>values.TryGetValue(k,out var v)?v:""),(Action<string,string>)((k,v)=>values[k]=v)});
  type.GetMethod("Begin",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(owner,new object[]{"discovery"});
  Need(values["discovery"]!="","marker missing before unload");context.Unload();return reference;
 }
 static int Main(){try{
  Need(!CandidateSession.Gate.TestDiscoveryCleanupUnconfirmed&&!CandidateSession.Gate.PrefabCleanupUnconfirmed,"native session gate lacks clean denial store");
  Need(UnityEditor.SessionState.Values.Count==0,"constructing gate wrote session state");
  UnityEditor.SessionState.Values[Prefix+"discovery"]="abandoned";
  Need(CandidateSession.Gate.TestDiscoveryCleanupUnconfirmed&&!CandidateSession.Gate.PrefabCleanupUnconfirmed,"native session key not wired or debt mixed");
  CandidateSession.Gate.StopAll("local stop");Need(UnityEditor.SessionState.Values[Prefix+"discovery"]=="abandoned","stop cleared unknown work");
  Console.WriteLine("PASS CD001 native_session_denial_binding_no_automatic_write");
  values.Clear();var a=Ledger();var lease=a.Begin("discovery");var b=Ledger();
  Need(b.Blocked("discovery")&&!a.Blocked("discovery",lease),"another ledger bypasses in-flight owner");
  Need(!b.Finish(lease)&&values["discovery"]==lease.Token,"foreign ledger cleared work");
  Need(a.Finish(lease)&&values["discovery"]==""&&!a.Finish(lease),"own receipt not exactly once");
  Console.WriteLine("PASS CD002 own_receipt_only_and_cross_instance_block");
  values.Clear();var weak=AbandonInIsolatedLoad();for(int i=0;weak.IsAlive&&i<30;i++){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}
  Need(!weak.IsAlive,"isolated load context remained alive");Need(Ledger().Blocked("discovery"),"assembly unload erased debt");
  Console.WriteLine("PASS CD003 real_clr_unload_preserves_denial_not_unity_acceptance");
  foreach(var bad in new string[]{null,"junk"," ","{}"}){var l=new EffectCleanupLedger(k=>bad,(k,v)=>{throw new Exception();});Need(l.Blocked("prefab"),"unknown state opened");Refused(()=>l.Begin("prefab"));}
  var unreadable=new EffectCleanupLedger(k=>throw new Exception(),(k,v)=>{});Need(unreadable.Blocked("discovery"),"read fault opened");Refused(()=>unreadable.Begin("discovery"));
  Console.WriteLine("PASS CD004 malformed_missing_provider_and_read_fault_denied");
  var dropped=new EffectCleanupLedger(k=>"",(k,v)=>{});Refused(()=>dropped.Begin("prefab"));Need(dropped.Blocked("prefab"),"write readback failure not latched");
  values.Clear();a=Ledger();lease=a.Begin("prefab");values["prefab"]="new-owner";Need(!a.Finish(lease)&&values["prefab"]=="new-owner","late old completion cleared another owner");
  Console.WriteLine("PASS CD005 failed_write_or_foreign_generation_cannot_clear");
  values.Clear();a=Ledger();lease=a.Begin("prefab");Need(!a.Blocked("discovery"),"debt kinds not independent");Refused(()=>a.Begin("unknown"));
  foreach(var method in typeof(EffectCleanupLedger).GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))throw new Exception("public debt reset/import API: "+method.Name);
  Console.WriteLine("PASS CD006 kinds_separate_no_public_reset_or_import");
  values.Clear();EffectCleanupLedger nested=null;bool inside=false;
  nested=new EffectCleanupLedger(k=>{if(!inside){inside=true;Need(nested.Blocked(k),"reentrant store read allowed");inside=false;}return values.TryGetValue(k,out var v)?v:"";},(k,v)=>values[k]=v);
  lease=nested.Begin("discovery");Need(values["discovery"]==lease.Token&&nested.Finish(lease),"bounded store reentry lost own lease");
  Console.WriteLine("PASS CD007 store_reentry_refused");
  values.Clear();bool refuseClear=false;
  var io=new EffectCleanupLedger(k=>values.TryGetValue(k,out var v)?v:"",(k,v)=>{if(refuseClear)throw new Exception();values[k]=v;});
  lease=io.Begin("prefab");refuseClear=true;Need(!io.Finish(lease)&&Ledger().Blocked("prefab"),"clear fault erased marker");
  Console.WriteLine("PASS CD008 clear_io_fault_leaves_blocking_marker");
  return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
