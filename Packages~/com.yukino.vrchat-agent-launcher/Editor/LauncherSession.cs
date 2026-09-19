using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using MCPForUnity.Editor.Services.Transport.Transports;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEngine;

namespace Yukino.VRChatAgentLauncher
{
    [InitializeOnLoad]
    internal static class LauncherSession
    {
        [Serializable] private sealed class Config
        {
            public int parent_pid, ssh_port, remote_port;
            public string stop_file, status_file, uvx_path, expected_project, ssh_path, ssh_host, ssh_user;
        }
        [Serializable] private sealed class Status { public string phase = "", message = "", code = "", resume_nonce = "", reason = "", step = ""; public int elapsed_ms, retry_count; public bool cleanup_complete = false; }
        [Serializable] private sealed class ResumeAck { public string resume_nonce; }
        private sealed class RunGeneration
        {
            internal readonly string Run;
            internal WebSocketTransportClient Client;
            internal Task ConnectOperation = Task.CompletedTask, StopOperation;
            internal bool ConnectRequested, StopRequested, Aborted;
            internal string AcknowledgedPause = "";
            internal RunGeneration(string run) { Run = run; }
            internal bool ConnectionCleanupComplete => ConnectOperation.IsCompleted &&
                (Client == null || Aborted || (StopOperation != null && StopOperation.Status == TaskStatus.RanToCompletion && !Client.IsConnected));
        }
        private const string RunKey = "Yukino.AgentLauncher.Run", StoppingKey = "Yukino.AgentLauncher.Stopping", TransportClean = "Yukino.AgentLauncher.TransportClean";
        private static RunGeneration generation;
        private static Process supervisor;
        private static bool processStarted;
        private static double nextPoll;
        private const string RecoveryKey = "Yukino.AgentLauncher.Recovery";
        private static RecoveryState recovery = LoadRecovery();
        private static double lastImport = -1;
        internal static bool IsReloading { get; private set; }
        internal static bool WindowOpen { get; set; }
        internal static bool RecoveryPending => recovery.Waiting;
        private static string Project => Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        private static bool EditorBusy => EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode;
        private static RecoveryState LoadRecovery()
        {
            try { return JsonUtility.FromJson<RecoveryState>(SessionState.GetString(RecoveryKey, "{}")) ?? new RecoveryState(); }
            catch { return new RecoveryState(); }
        }
        private static void SaveRecovery() { SessionState.SetString(RecoveryKey, JsonUtility.ToJson(recovery)); }
        private static void CancelRecovery() { recovery.Cancel(); SessionState.EraseString(RecoveryKey); }
        internal static void WindowClosed(bool destroyed = false)
        {
            WindowOpen = false;
            if (destroyed || !IsReloading) RequestStop("连接窗口关闭：停止并取消恢复。");
        }
        private static void BeforeReload()
        {
            IsReloading = true;
            PauseForImport(true);
        }
        private static void OnQuit() { CancelRecovery(); if (Busy) RequestStop("Unity 退出：停止连接，不在下次启动时恢复。", true); }
        private static void PauseForImport(bool abort = false)
        {
            lastImport = EditorApplication.timeSinceStartup;
            if (recovery.Waiting) { recovery.QuietSince = -1; SaveRecovery(); }
            if (!Busy) return;
            bool resume = recovery.BeginPause(lastImport, Project); SaveRecovery();
            RequestStop(resume ? "导入／重编译中：撤销权限并断开，清理后等待同工程恢复。" : "导入／重编译中：已断开，完成后请手动连接。", abort, resume);
            if (resume) Phase = "paused_for_import";
        }
        private static void TryRecover()
        {
            if (!recovery.Waiting) return;
            bool ready = recovery.Ready(EditorApplication.timeSinceStartup, Project, EditorBusy, !Busy, WindowOpen);
            SaveRecovery();
            if (!recovery.Waiting) { Message = "恢复已取消或等待超时，请手动连接。"; return; }
            Phase = "waiting_recovery"; Message = "等待导入结束、窗口就绪和清理确认；连续空闲 5 秒后仅恢复连接。";
            if (!ready) return;
            string snapshot = recovery.Consume(); SaveRecovery(); // consume BEFORE any new process
            try
            {
                var settings = JsonUtility.FromJson<LauncherSettings>(snapshot);
                if (settings == null || !settings.autoRecoverAfterImport) { CancelRecovery(); return; }
                StartCore(settings, true);
            }
            catch { CancelRecovery(); Message = "恢复失败，已停止自动尝试，请手动检查。"; }
        }
        internal static string Phase { get; private set; } = "idle";
        internal static string Message { get; private set; } = "未启动；连接不会授予编辑权限。";
        internal static string LastRun { get; private set; } = "";
        private static string Run => SessionState.GetString(RunKey, "");
        internal static bool Busy => Run.Length != 0;
        internal static bool OwnedConnected => generation?.Client?.IsConnected == true && !generation.StopRequested;
        internal static string OwnedSessionId => generation?.Client?.State?.SessionId ?? "";
        static LauncherSession()
        {
            AssemblyReloadEvents.beforeAssemblyReload += BeforeReload;
            CompilationPipeline.compilationStarted += _ => PauseForImport();
            EditorApplication.quitting += OnQuit;
            EditorApplication.update += Tick;
            LastRun = Run;
            if (Run.Length != 0) RequestStop("代码重载：先清理旧连接。", false, recovery.Waiting);
        }
        internal static void Start(LauncherSettings settings)
        {
            if (Busy) { Message = "前次连接或清理尚未结束。"; return; }
            CancelRecovery(); StartCore(settings, false);
        }
        private static void StartCore(LauncherSettings settings, bool automatic)
        {
            if (Busy) { Message = "前次连接或清理尚未结束。"; return; }
            processStarted = false;
            try
            {
                string error = settings.Validate(); if (error.Length == 0) error = CoplayAdapter.Prerequisite();
                if (error.Length != 0) throw new InvalidOperationException(error);
                if (EditorBusy) throw new InvalidOperationException("请等待 Unity 导入或编译结束。");
                if (!CoplayAdapter.SettingsReady() || CoplayAdapter.ManagerBusy) throw new InvalidOperationException("先准备本地设置，并人工断开 Coplay 面板已有连接。");
                CoplayAdapter.RevokeManaged();
                var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(LauncherSession).Assembly);
                if (package == null) throw new InvalidOperationException("无法确定包安装位置。");
                string runtime = Path.Combine(package.resolvedPath, "Editor", "Runtime~"), script = Path.Combine(runtime, "launcher_supervisor.py");
                foreach (string name in new[] { "launcher_supervisor.py", "bridge.py", "windows_processes.py" })
                    if (!File.Exists(Path.Combine(runtime, name))) throw new InvalidOperationException("包文件不完整。");
                string project = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
                string run = Path.Combine(project, "Library", "YukinoAgentLauncher", Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(run);
                var config = new Config { parent_pid = Process.GetCurrentProcess().Id, stop_file = Path.Combine(run, "stop"), status_file = Path.Combine(run, "status.json"), uvx_path = settings.uvx, expected_project = project, ssh_path = settings.ssh, ssh_host = settings.host, ssh_user = settings.user, ssh_port = settings.sshPort, remote_port = settings.remotePort };
                string configFile = Path.Combine(run, "config.json"); File.WriteAllText(configFile, JsonUtility.ToJson(config));
                generation = new RunGeneration(run); SessionState.SetString(RunKey, run); SessionState.SetBool(StoppingKey, false); SessionState.SetBool(TransportClean, true);
                LastRun = run; Phase = "starting"; Message = "检查本地服务；首次 uvx 可能下载固定版本。";
                var start = new ProcessStartInfo { FileName = settings.python, Arguments = "-I " + LauncherSettings.QuoteArgument(script) + " --config " + LauncherSettings.QuoteArgument(configFile), WorkingDirectory = run, UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
                supervisor = new Process { StartInfo = start };
                supervisor.OutputDataReceived += (_, e) => { }; supervisor.ErrorDataReceived += (_, e) => { };
                if (!supervisor.Start()) throw new InvalidOperationException("Python 启动失败。");
                processStarted = true;
                if (!automatic) { recovery.Remember(settings.autoRecoverAfterImport, project, JsonUtility.ToJson(settings)); SaveRecovery(); }
                supervisor.StandardInput.Close(); supervisor.BeginOutputReadLine(); supervisor.BeginErrorReadLine();
            }
            catch (Exception e)
            {
                CancelRecovery();
                Message = "启动失败：" + (e is InvalidOperationException ? e.Message : e.GetType().Name); Phase = "error";
                if (!processStarted) ClearRun(); else RequestStop(Message);
            }
        }
        private static bool SafeExited(Process p) { try { return p.HasExited; } catch (InvalidOperationException) { return true; } }
        internal static void RequestStop(string reason = "已请求断开；等待清理。", bool lifecycle = false, bool preserveRecovery = false)
        {
            if (!preserveRecovery) CancelRecovery();
            if (Run.Length == 0) { Message = reason; Phase = "stopped"; return; }
            SessionState.SetBool(StoppingKey, true); Message = reason;
            try { CoplayAdapter.RevokeManaged(); } catch { Message += " 撤销接口失败，请本地检查。"; }
            try { File.WriteAllText(Path.Combine(Run, "stop"), "stop"); } catch { Message += " 停止文件写入失败，请正常退出编辑器。"; }
            RunGeneration g = generation;
            if (g == null) return; // Never inspect/stop a newly created manager client after reload.
            g.StopRequested = true;
            if (lifecycle)
            {
                g.Aborted = CoplayAdapter.AbortOwned(g.Client);
                SessionState.SetBool(TransportClean, g.Aborted);
                if (!g.Aborted) Message += " 私有连接取消未确认。";
                return;
            }
            if (!g.ConnectOperation.IsCompleted) { CoplayAdapter.AbortOwned(g.Client); return; }
            if (g.Client != null && g.StopOperation == null) g.StopOperation = StopConnection(g);
            SessionState.SetBool(TransportClean, g.ConnectionCleanupComplete);
        }
        private static async Task StopConnection(RunGeneration g)
        {
            await g.Client.StopAsync();
            if (g.Client.IsConnected) throw new InvalidOperationException("连接停止未确认。");
        }
        private static async Task ConnectUnity(RunGeneration g)
        {
            g.ConnectRequested = true;
            try
            {
                g.Client = CoplayAdapter.CreateOwned();
                SessionState.SetBool(TransportClean, false);
                bool success = await CoplayAdapter.StartOwned(g.Client);
                if (g.StopRequested || Run != g.Run)
                { g.StopOperation = StopConnection(g); await g.StopOperation; return; }
                if (!success || !CoplayAdapter.SettingsReady() || CoplayAdapter.ManagerBusy)
                {
                    g.StopRequested = true; g.StopOperation = StopConnection(g); await g.StopOperation;
                    if (Run == g.Run) RequestStop("Unity 连接失败或设置已变更。");
                }
            }
            catch
            {
                if (g.Client != null) { try { g.StopOperation = StopConnection(g); await g.StopOperation; } catch { } }
                if (Run == g.Run) RequestStop("Unity Connect 异常，正在清理。");
            }
        }
        private static void AcknowledgePause(RunGeneration g, string nonce)
        {
            // Local only: never expose revoke/ack to the remote MCP catalog.
            if (g == null || g.Run != Run || g.StopRequested || SessionState.GetBool(StoppingKey, false)) return;
            if (nonce == g.AcknowledgedPause) return;
            if (nonce == null || !Regex.IsMatch(nonce, @"\A[a-f0-9]{64}\z"))
            { RequestStop("暂停标识无效，已停止连接。"); return; }
            string staged = Path.Combine(g.Run, "resume-ack.tmp");
            try
            {
                CoplayAdapter.RevokeManaged(); // MUST succeed before acknowledgement
                string destination = Path.Combine(g.Run, "resume-ack.json");
                File.WriteAllText(staged, JsonUtility.ToJson(new ResumeAck { resume_nonce = nonce }));
                if (File.Exists(destination)) File.Delete(destination);
                File.Move(staged, destination);
                g.AcknowledgedPause = nonce;
            }
            catch { RequestStop("撤销编辑权限或暂停确认失败，已停止连接。"); }
            finally { try { if (File.Exists(staged)) File.Delete(staged); } catch { } }
        }
        private static void ClearRun()
        {
            LastRun = Run.Length == 0 ? LastRun : Run;
            SessionState.EraseString(RunKey); SessionState.EraseBool(StoppingKey); SessionState.EraseBool(TransportClean);
            supervisor?.Dispose(); supervisor = null; generation = null; processStarted = false;
        }
        internal static void Tick()
        {
            if (EditorApplication.timeSinceStartup < nextPoll) return; nextPoll = EditorApplication.timeSinceStartup + 0.25;
            if (EditorBusy) { lastImport = EditorApplication.timeSinceStartup; if (Busy && !SessionState.GetBool(StoppingKey, false)) PauseForImport(); }
            if (recovery.Waiting && Busy) { recovery.Ready(EditorApplication.timeSinceStartup, Project, EditorBusy, false, WindowOpen); SaveRecovery(); }
            string run = Run; if (run.Length == 0) { TryRecover(); return; }
            try
            {
                RunGeneration g = generation;
                if (g != null && g.ConnectRequested && !g.StopRequested && (!CoplayAdapter.SettingsReady() || CoplayAdapter.ManagerBusy)) RequestStop("连接设置或其他 Unity 连接发生变化，已停止本窗口连接。");
                string file = Path.Combine(run, "status.json");
                Status state = File.Exists(file) ? JsonUtility.FromJson<Status>(File.ReadAllText(file)) : null;
                if (state != null)
                {
                    Phase = state.phase ?? "unknown";
                    if (state.phase == "suspended") AcknowledgePause(g, state.resume_nonce);
                    if (state.phase == "connected" && !SessionState.GetBool(StoppingKey, false)) { recovery.Connected(); SaveRecovery(); }
                    if (!SessionState.GetBool(StoppingKey, false))
                    {
                        Message = state.message ?? Phase;
                        if (!string.IsNullOrEmpty(state.step)) Message += "\n步骤：" + state.step + "，最近耗时 " + state.elapsed_ms + "ms，复查 " + state.retry_count + " 次";
                        if (!string.IsNullOrEmpty(state.reason) && state.reason != "none") Message += "\n原因：" + state.reason;
                    }
                    if (state.phase == "sidecar_ready" && g != null && !g.ConnectRequested && !SessionState.GetBool(StoppingKey, false)) g.ConnectOperation = ConnectUnity(g);
                    if (state.phase == "error")
                    {
                        bool importRelated = state.code == "PROJECT_UNAVAILABLE" && (recovery.Waiting || EditorBusy || (lastImport >= 0 && EditorApplication.timeSinceStartup - lastImport < 10));
                        if (importRelated && recovery.BeginPause(EditorApplication.timeSinceStartup, Project))
                        { SaveRecovery(); if (!SessionState.GetBool(StoppingKey, false)) RequestStop("导入期间暂时失联，先清理再恢复。", false, true); }
                        else { CancelRecovery(); if (!SessionState.GetBool(StoppingKey, false)) RequestStop(state.message ?? "监督程序错误。"); }
                    }
                    if (state.cleanup_complete && (supervisor == null || SafeExited(supervisor)))
                    {
                        if (!SessionState.GetBool(StoppingKey, false)) RequestStop(Message, false, recovery.Waiting);
                        bool clean = g != null ? g.ConnectionCleanupComplete : SessionState.GetBool(TransportClean, false);
                        if (clean) { ClearRun(); if (Phase != "error") Phase = "stopped"; TryRecover(); return; }
                        Message = "Python 清理完成，Unity 私有连接清理仍未确认，禁止重新启动。";
                    }
                }
                if (supervisor != null && SafeExited(supervisor) && (state == null || !state.cleanup_complete))
                {
                    CancelRecovery();
                    if (!SessionState.GetBool(StoppingKey, false)) RequestStop("监督进程提前退出，清理未确认。检查诊断文件，禁止自动重试。");
                    Phase = "error";
                }
            }
            catch (IOException) { }
            catch (Exception) { RequestStop("状态读取失败，停止连接。"); }
        }
    }
}
