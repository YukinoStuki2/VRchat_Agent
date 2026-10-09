// Actual candidate discovery lifecycle; Unity/NUnit builders are explicit doubles.
using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework.Interfaces;
using UnityEngine.TestTools;
using UnityEditor.TestTools.TestRunner;
 #if !PLUGIN_NATIVE_ASSETS
namespace UnityEditor {
 public static class EditorApplication {
  public static double timeSinceStartup;public static event Action update,quitting;
  public static int Updates=>update?.GetInvocationList().Length??0;
  public static int Quits=>quitting?.GetInvocationList().Length??0;
  public static void Tick()=>update?.Invoke();public static void Quit()=>quitting?.Invoke();
 }
 public static class AssemblyReloadEvents {public static event Action beforeAssemblyReload;public static int Count=>beforeAssemblyReload?.GetInvocationList().Length??0;public static void Reload()=>beforeAssemblyReload?.Invoke();}
}
 #endif
namespace NUnit.Framework.Interfaces {public interface ITest {string Name{get;}string FullName{get;}bool IsSuite{get;}IList<ITest> Tests{get;}}}
namespace UnityEngine.TestTools {public enum TestPlatform{EditMode=1,PlayMode=2}public static class PlatformExtensions{public static bool IsFlagIncluded(this TestPlatform a,TestPlatform b)=>(a&b)==b;}}
namespace UnityEngine.TestTools.NUnitExtensions {
 public sealed class UnityTestAssemblyBuilder {
  public static Dictionary<string,object> GetNUnitTestBuilderSettings(TestPlatform p)=>new Dictionary<string,object>();
  public IEnumerator<ITest> BuildAsync(Assembly[] a,TestPlatform[] p,IDictionary<string,object> settings){Probe.Builds++;try{Probe.OnBuild?.Invoke();if(Probe.Fail)throw new Exception("secret-not-for-output");while(Probe.Hang)yield return null;yield return Probe.Root;}finally{Probe.BuilderDisposed++;if(Probe.DisposeFail)throw new Exception("dispose secret");}}
 }
}
namespace UnityEditor.TestTools.TestRunner {
 public interface ITestListProvider {IEnumerator<ITest> GetTestListAsync(TestPlatform mode);}
 public sealed class AssemblyWrapper {public Assembly Assembly=>typeof(Probe).Assembly;}
 public sealed class EditorCompilationInterfaceProxy{}
 public sealed class EditorAssembliesProxy{}
 public sealed class EditorLoadedTestAssemblyProvider {
  public EditorLoadedTestAssemblyProvider(EditorCompilationInterfaceProxy a,EditorAssembliesProxy b){Probe.Constructed++;Probe.OnConstruct?.Invoke();}
  public IEnumerator<IDictionary<TestPlatform,List<AssemblyWrapper>>> GetAssembliesGroupedByTypeAsync(TestPlatform p){try{yield return new Dictionary<TestPlatform,List<AssemblyWrapper>>{{p,new List<AssemblyWrapper>{new AssemblyWrapper()}}};}finally{Probe.AssembliesDisposed++;}}
 }
}
internal sealed class Node:ITest {
 public string Name{get;set;}="Test";string fullName="Suite.Test";public string FullName{get{Probe.OnRead?.Invoke();return fullName;}set{fullName=value;}}public bool IsSuite{get;set;}
 public IList<ITest> Tests{get;set;}=new List<ITest>();
}
internal static class Probe {
 internal static int Constructed,Builds,BuilderDisposed,AssembliesDisposed;
 internal static bool Fail=false,Hang=false,DisposeFail=false;internal static Action OnBuild=null,OnConstruct=null,OnRead=null;
 internal static ITest Root=new Node{IsSuite=true,Name="Suite",FullName="Suite",Tests=new List<ITest>{new Node()}};
 static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
 static void Pump(){for(int i=0;i<20&&UnityEditor.EditorApplication.Updates>0;i++)UnityEditor.EditorApplication.Tick();}
 static void Clean()=>Need(UnityEditor.EditorApplication.Updates==0&&UnityEditor.EditorApplication.Quits==0&&UnityEditor.AssemblyReloadEvents.Count==0,"owned subscriptions remain");
 static int Main(string[] args){try{
  switch(args[0]){
   case "DR001":var denied=CandidateDiscoveryJob.Begin("EditMode",()=>false);Need(denied.Completion.IsCompleted,"denial must complete");Need(!denied.Completion.Result.Success&&!denied.Completion.Result.EffectsMayHaveOccurred,"denial receipt");Need(Constructed==0&&Builds==0,"denial reached native source");Clean();break;
   case "DR002":var live=CandidateDiscoveryJob.Begin("EditMode",()=>true);Need(!live.Completion.IsCompleted,"not an asynchronous native query");Pump();var result=live.Completion.Result;Need(result.Success&&result.EffectsMayHaveOccurred&&result.CleanupConfirmed,"fresh native discovery did not succeed");Need(result.Rows.Length==1&&result.Rows[0][1]=="Suite.Test","native leaf missing");Need(Builds==1&&Constructed==1&&BuilderDisposed==1&&AssembliesDisposed==1,"native provider lifecycle not used");Clean();break;
   case "DR003":bool allowed=true;Hang=true;var revoked=CandidateDiscoveryJob.Begin("EditMode",()=>allowed);for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();Need(Builds==1,"fixture did not enter builder");allowed=false;Pump();Need(revoked.Completion.IsCompleted,"revocation left pending task");Need(!revoked.Completion.Result.Success&&revoked.Completion.Result.EffectsMayHaveOccurred,"revocation falsely succeeded");Need(BuilderDisposed==1,"nested iterator not disposed");Clean();break;
   case "DR004":Hang=true;var cancelled=CandidateDiscoveryJob.Begin("PlayMode",()=>true);OnBuild=()=>cancelled.Cancel();Pump();Need(cancelled.Completion.IsCompleted,"reentrant cancel left task");Need(!cancelled.Completion.Result.Success&&cancelled.Completion.Result.CleanupConfirmed,"cancel did not drain");Need(BuilderDisposed==1,"in-flight iterator disposed incorrectly");Clean();break;
   case "DR005":Hang=true;var reload=CandidateDiscoveryJob.Begin("EditMode",()=>true);for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();UnityEditor.AssemblyReloadEvents.Reload();Need(reload.Completion.IsCompleted,"reload left discovery running");Need(!reload.Completion.Result.Success&&reload.Completion.Result.CleanupConfirmed&&BuilderDisposed==1,"reload did not cancel own work");Clean();break;
   case "DR006":Hang=true;var quit=CandidateDiscoveryJob.Begin("EditMode",()=>true);for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();UnityEditor.EditorApplication.Quit();Need(quit.Completion.IsCompleted,"quit left discovery running");Need(!quit.Completion.Result.Success&&quit.Completion.Result.CleanupConfirmed&&BuilderDisposed==1,"quit did not cancel own work");Clean();break;
   case "DR007":Hang=true;var timed=CandidateDiscoveryJob.Begin("EditMode",()=>true);for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();UnityEditor.EditorApplication.timeSinceStartup=31;Pump();Need(timed.Completion.IsCompleted,"timeout did not complete");Need(!timed.Completion.Result.Success&&timed.Completion.Result.CleanupConfirmed&&BuilderDisposed==1,"timeout falsely complete or leaked");Clean();break;
   case "DR008":bool constructorAllowed=true;OnConstruct=()=>constructorAllowed=false;var changed=CandidateDiscoveryJob.Begin("EditMode",()=>constructorAllowed);Need(changed.Completion.IsCompleted,"constructor revocation still subscribed");Need(!changed.Completion.Result.Success&&Builds==0,"constructor revocation dispatched builder");Clean();break;
   case "DR009":Root=null;var missing=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!missing.Completion.Result.Success&&missing.Completion.Result.Rows==null,"missing root returned successful empty set");Clean();break;
   case "DR010":Root=new Node{IsSuite=true,Tests=new List<ITest>()};var empty=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(empty.Completion.Result.Success&&empty.Completion.Result.Rows.Length==0,"empty suite invented test");Clean();break;
   case "DR011":{Root=new Node{IsSuite=true,Tests=new List<ITest>{new Node(),new Node()}};var duplicate=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!duplicate.Completion.Result.Success&&duplicate.Completion.Result.Rows==null,"duplicate silently dropped");Clean();}break;
   case "DR012":{Root=new Node{IsSuite=true,Tests=new List<ITest>{null}};var incomplete=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!incomplete.Completion.Result.Success&&incomplete.Completion.Result.Rows==null,"null child became complete empty set");Clean();}break;
   case "DR013":{for(int i=0;i<66;i++)Root=new Node{IsSuite=true,Tests=new List<ITest>{Root}};var deep=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!deep.Completion.Result.Success&&deep.Completion.Result.Rows==null,"depth budget ignored");Clean();}break;
   case "DR014":{var wide=new List<ITest>();for(int i=0;i<4097;i++)wide.Add(new Node{FullName="T"+i});Root=new Node{IsSuite=true,Tests=wide};var large=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!large.Completion.Result.Success&&large.Completion.Result.Rows==null,"node budget ignored");Clean();}break;
   case "DR015":{bool readAllowed=true;OnRead=()=>readAllowed=false;var duringRead=CandidateDiscoveryJob.Begin("EditMode",()=>readAllowed);Pump();Need(!duringRead.Completion.Result.Success&&duringRead.Completion.Result.Rows==null,"revoked metadata was published");Clean();}break;
   case "DR016":{bool once=true;var finalCheck=CandidateDiscoveryJob.Begin("EditMode",()=>{if(BuilderDisposed>0&&once){once=false;return false;}return true;});Pump();Need(!finalCheck.Completion.Result.Success&&finalCheck.Completion.Result.Rows==null,"temporary denial was revived");Clean();}break;
   case "DR017":{Hang=true;DisposeFail=true;var badDispose=CandidateDiscoveryJob.Begin("EditMode",()=>true);for(int i=0;i<4;i++)UnityEditor.EditorApplication.Tick();badDispose.Cancel();Need(!badDispose.Completion.Result.Success&&!badDispose.Completion.Result.CleanupConfirmed,"failed dispose reported clean");Need(badDispose.Completion.Result.Error=="discovery_unconfirmed","raw error escaped");Clean();}break;
   case "DR018":{Root=new Node{FullName=new string('x',270000)};var oversized=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!oversized.Completion.Result.Success&&oversized.Completion.Result.Rows==null,"response budget ignored");Clean();}break;
   case "DR019":{var cycle=new Node{IsSuite=true};cycle.Tests.Add(cycle);Root=cycle;var cyclic=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!cyclic.Completion.Result.Success&&cyclic.Completion.Result.Rows==null,"cycle yielded partial success");Clean();}break;
   case "DR020":{OnBuild=()=>UnityEditor.EditorApplication.Tick();var reentry=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(reentry.Completion.Result.Success&&Builds==1,"reentrant update executed nested discovery");reentry.Cancel();UnityEditor.EditorApplication.Tick();Need(Builds==1,"late cancel restarted discovery");Clean();}break;
   case "DR021":{Fail=true;var badBuilder=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!badBuilder.Completion.Result.Success&&!badBuilder.Completion.Result.CleanupConfirmed&&badBuilder.Completion.Result.Error=="discovery_unconfirmed","builder failure escaped");Need(BuilderDisposed==1&&AssembliesDisposed==1,"builder failure retained iterator");Clean();}break;
   case "DR022":{Hang=true;var deadline=CandidateDiscoveryJob.Begin("EditMode",()=>true);UnityEditor.EditorApplication.timeSinceStartup=31;Pump();Need(deadline.Completion.Result.Error=="discovery_timed_out","timeout not distinguished");Clean();}break;
   case "DR023":{foreach(double bad in new[]{double.NaN,double.PositiveInfinity}){UnityEditor.EditorApplication.timeSinceStartup=bad;var clock=CandidateDiscoveryJob.Begin("EditMode",()=>true);Need(clock.Completion.IsCompleted&&!clock.Completion.Result.Success&&!clock.Completion.Result.EffectsMayHaveOccurred,"bad initial clock started native code");Clean();}Need(Constructed==0,"invalid clock constructed native provider");}break;
   case "DR024":{foreach(string bad in new[]{"all","EditMode|PlayMode",null,"","editmode"}){var invalid=CandidateDiscoveryJob.Begin(bad,()=>true);Need(invalid.Completion.IsCompleted&&!invalid.Completion.Result.Success&&!invalid.Completion.Result.EffectsMayHaveOccurred,"invalid mode accepted");Clean();}Need(Constructed==0,"invalid mode constructed provider");}break;
   case "DR025":{DisposeFail=true;var naturalDispose=CandidateDiscoveryJob.Begin("EditMode",()=>true);Pump();Need(!naturalDispose.Completion.Result.Success&&!naturalDispose.Completion.Result.CleanupConfirmed,"MoveNext disposal fault reported clean after second Dispose");Need(naturalDispose.Completion.Result.Rows==null,"native disposal fault published rows");Clean();}break;
   default:throw new Exception("unknown case");
  }
  Console.WriteLine("PASS "+args[0]+" live_discovery_case");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
