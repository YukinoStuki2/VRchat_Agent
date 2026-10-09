using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using NUnit.Framework.Interfaces;
using UnityEngine.TestTools;
using UnityEngine.TestTools.NUnitExtensions;
namespace UnityEditor.TestTools.TestRunner
{
    public sealed class CandidateDiscoveryOutcome
    {
        public bool Success { get; internal set; }
        public bool EffectsMayHaveOccurred { get; internal set; }
        public bool CleanupConfirmed { get; internal set; }
        public string Error { get; internal set; }
        public string[][] Rows { get; internal set; }
    }
    // Explicit local entry, Editor-thread only. No registry/initialization hook.
    // Caller owns trusted context and independent task approval. Not a sandbox.
    public sealed partial class CandidateDiscoveryJob
    {
        readonly TaskCompletionSource<CandidateDiscoveryOutcome> completion = new TaskCompletionSource<CandidateDiscoveryOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
        IEnumerator<ITest> iterator;
        Func<bool> authorized;
        string mode;
        string failure="discovery_unconfirmed";
        double deadline,lastClock;
        int visited;
        bool attempted, subscribed, cancelled, advancing, finished, iteratorFaulted;
        public Task<CandidateDiscoveryOutcome> Completion => completion.Task;
        public static CandidateDiscoveryJob Begin(string mode, Func<bool> authorized)
        {
            var job = new CandidateDiscoveryJob { mode=mode, authorized=authorized };
            try
            {
                if ((mode!="EditMode" && mode!="PlayMode") || authorized==null || !authorized())
                    throw new InvalidOperationException();
                job.lastClock=EditorApplication.timeSinceStartup;job.deadline=job.lastClock+30;
                if(!job.ClockCurrent())throw new InvalidOperationException();
                job.attempted=true;
                var assemblyProvider=new EditorLoadedTestAssemblyProvider(new EditorCompilationInterfaceProxy(),new EditorAssembliesProxy());
                var provider=new CandidateLiveTestListProvider(assemblyProvider,new UnityTestAssemblyBuilder());
                job.iterator=provider.GetTestListAsync(mode=="EditMode" ? TestPlatform.EditMode : TestPlatform.PlayMode);
                if(!job.Allowed())throw new InvalidOperationException();
                job.subscribed=true;EditorApplication.update+=job.Update;
                AssemblyReloadEvents.beforeAssemblyReload+=job.Cancel;EditorApplication.quitting+=job.Cancel;
            }
            catch { job.Finish(null); }
            return job;
        }
        public void Cancel()
        {
            cancelled=true;
            if(!advancing&&!finished)Finish(null);
        }
        bool ClockCurrent()
        {
            double now=EditorApplication.timeSinceStartup;
            if(double.IsNaN(now)||double.IsInfinity(now)||now<lastClock) { failure="discovery_clock_changed";return false; }
            if(now>=deadline) { failure="discovery_timed_out";return false; }
            lastClock=now;return true;
        }
        bool Allowed() => !cancelled && !finished && ClockCurrent() && authorized!=null && authorized() && !cancelled && !finished && ClockCurrent();
        void Update()
        {
            if(finished||advancing)return;
            advancing=true;
            try
            {
                if(!Allowed()) { Finish(null);return; }
                bool more;
                try { more=iterator.MoveNext(); }
                catch { iteratorFaulted=true;throw; }
                if(!Allowed()) { Finish(null);return; }
                if(more) return;
                if(iterator.Current==null)throw new InvalidOperationException();
                var rows=new List<Dictionary<string,string>>();
                CollectFromNode(iterator.Current,mode,rows,new HashSet<string>(StringComparer.Ordinal),new List<string>());
                if(!Allowed())throw new InvalidOperationException();
                var result=rows.Select(row=>new[]{row["name"],row["full_name"],row["path"],row["mode"]}).ToArray();
                int budget=32;
                foreach(var row in result)
                {
                    budget+=4;
                    foreach(string value in row)
                    {
                        if(string.IsNullOrEmpty(value)||value.Length>4096)throw new InvalidOperationException();
                        // Upper bound for escaped JSON UTF-16, before any wire serializer.
                        budget=checked(budget+6*value.Length+3);
                        if(budget>262144)throw new InvalidOperationException();
                    }
                }
                Finish(result);
            }
            catch { Finish(null); }
            finally { advancing=false;if(cancelled&&!finished)Finish(null); }
        }
        void Finish(string[][] rows)
        {
            if(finished)return;
            finished=true;
            // Iterator unwinding may already have thrown from nested Dispose.
            // A second no-op Dispose cannot turn that uncertainty into cleanup.
            bool cleaned=!iteratorFaulted;
            try { if(subscribed)EditorApplication.update-=Update; } catch { cleaned=false; }
            try { AssemblyReloadEvents.beforeAssemblyReload-=Cancel; } catch { cleaned=false; }
            try { EditorApplication.quitting-=Cancel; } catch { cleaned=false; }
            subscribed=false;
            try { iterator?.Dispose(); } catch { cleaned=false; }
            iterator=null;
            completion.TrySetResult(new CandidateDiscoveryOutcome { Success=rows!=null&&cleaned, Rows=cleaned?rows:null,
                Error=rows!=null&&cleaned?null:failure,EffectsMayHaveOccurred=attempted,CleanupConfirmed=cleaned });
        }
    }
}
