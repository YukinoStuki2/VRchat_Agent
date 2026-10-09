using System;
using System.Security.Cryptography;
using System.Text;

namespace Yukino.VRChatAgent
{
    // Local operator consent to the project's plugin trust premise, not a code
    // audit, executing-image attestation, callback inventory or plugin sandbox.
    // Never persisted or imported. Does not enable a capability or approve a task.
    // The supplied context binds the live project/connection and observed inventory.
    // Editor-thread only; no Unity calls or remote consent endpoint in this policy.
    internal sealed class ProjectPluginTrust
    {
        readonly Func<string> current;
        readonly Action invalidated;
        string pending,accepted,baseline;
        long generation;
        internal ProjectPluginTrust(Func<string> current,Action invalidated)
        { this.current=current;this.invalidated=invalidated; }
        static bool Fingerprint(string value)
        {
            if(value==null||value.Length!=64)return false;
            foreach(char c in value)if(!((c>='a'&&c<='f')||(c>='0'&&c<='9')))return false;
            return true;
        }
        internal static string Digest(string value)
        {using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-","").ToLowerInvariant();}
        internal void Revoke()
        {generation++;pending=null;accepted=null;baseline=null;invalidated?.Invoke();}
        internal string StageLocal()
        {
            Revoke();long started=generation;
            try
            {
                string token=Guid.NewGuid().ToString("N");
                string observed=current();if(!Fingerprint(observed)||generation!=started){Revoke();return null;}
                baseline=observed;return pending=token;
            }
            catch{Revoke();return null;}
        }
        internal bool ConfirmLocal(string token)
        {
            try
            {
                long started=generation;string expected=pending,context=baseline;
                if(expected==null||token!=expected||current()!=context||generation!=started||pending!=expected){Revoke();return false;}
                accepted=pending;pending=null;return true;
            }
            catch{Revoke();return false;}
        }
        internal void Observe()
        {
            if(baseline==null)return;
            long started=generation;string expected=baseline;
            try{if(current()!=expected||generation!=started||baseline!=expected)Revoke();}catch{Revoke();}
        }
        internal bool Confirmed {get{Observe();return accepted!=null;}}
        internal string Evidence(string purpose,string target)
        {
            Observe();if(accepted==null)return null;
            bool valid=purpose=="asset_load_callbacks"&&(CandidateGate.AssetTarget(target)||CandidateGate.PrefabTarget(target)) ||
                purpose=="prefab_contents_callbacks"&&CandidateGate.PrefabTarget(target) ||
                purpose=="test_discovery_callbacks"&&(target=="TestDiscovery/EditMode"||target=="TestDiscovery/PlayMode");
            return valid?Digest("local_project_plugin_trust_v1\n"+accepted+"\n"+baseline+"\n"+purpose+"\n"+target):null;
        }
    }
}
