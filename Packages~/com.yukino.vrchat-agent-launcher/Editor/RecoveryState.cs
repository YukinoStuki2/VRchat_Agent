using System;

namespace Yukino.VRChatAgentLauncher
{
    // SessionState only. No credentials, process control, Unity tools or permission grants.
    [Serializable]
    internal sealed class RecoveryState
    {
        public bool Allowed, WasConnected, Waiting;
        public string Project = "", Settings = "";
        public double Deadline, QuietSince = -1;
        internal void Remember(bool enabled, string project, string settings)
        {
            Cancel(); Allowed = enabled; Project = project; Settings = settings;
        }
        internal void Connected() { if (Allowed && !Waiting) WasConnected = true; }
        internal bool BeginPause(double now, string project)
        {
            if (!Allowed || Project != project) { Cancel(); return false; }
            if (Waiting) return true; // repeated callbacks never extend the deadline/budget
            if (!WasConnected) return false;
            Waiting = true; WasConnected = false; Deadline = now + 180; QuietSince = -1;
            return true;
        }
        internal bool Ready(double now, string project, bool editorBusy, bool cleanupComplete, bool windowOpen)
        {
            if (!Waiting) return false;
            if (project != Project || now >= Deadline || now < Deadline - 180) { Cancel(); return false; }
            if (editorBusy || !cleanupComplete || !windowOpen) { QuietSince = -1; return false; }
            if (QuietSince < 0) QuietSince = now;
            return now - QuietSince >= 5;
        }
        internal string Consume()
        {
            if (!Waiting) return null;
            Waiting = false; QuietSince = -1; WasConnected = false;
            return Settings;
        }
        internal void Cancel()
        {
            Allowed = WasConnected = Waiting = false; Project = Settings = ""; Deadline = 0; QuietSince = -1;
        }
    }
}
