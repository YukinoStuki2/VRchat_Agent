using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using MCPForUnity.Editor.Services.Transport.Transports;
using UnityEditor;
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
        [Serializable] private sealed class Status { public string phase = "", message = ""; public bool cleanup_complete = false; }
        private sealed class RunGeneration
        {
            internal readonly string Run;
            internal WebSocketTransportClient Client;
            internal Task ConnectOperation = Task.CompletedTask, StopOperation;
            internal bool ConnectRequested, StopRequested, Aborted;
            internal RunGeneration(string run) { Run = run; }
            internal bool ConnectionCleanupComplete => ConnectOperation.IsCompleted &&
                (Client == null || Aborted || (StopOperation != null && StopOperation.Status == TaskStatus.RanToCompletion && !Client.IsConnected));
        }
        private const string RunKey = "Yukino.AgentLauncher.Run", StoppingKey = "Yukino.AgentLauncher.Stopping", TransportClean = "Yukino.AgentLauncher.TransportClean";
        private static RunGeneration generation;
        private static Process supervisor;
        private static bool processStarted;
        private static double nextPoll;
        internal static string Phase { get; private set; } = "idle";
        internal static string Message { get; private set; } = "未启动；连接不会授予编辑权限。";
        internal static string LastRun { get; private set; } = "";
        private static string Run => SessionState.GetString(RunKey, "");
        internal static bool Busy => Run.Length != 0;
        internal static bool OwnedConnected => generation?.Client?.IsConnected == true && !generation.StopRequested;
        internal static string OwnedSessionId => generation?.Client?.State?.SessionId ?? "";
        static LauncherSession()
        {
            AssemblyReloadEvents.beforeAssemblyReload += OnLifecycleStop;
            EditorApplication.quitting += OnLifecycleStop;
            EditorApplication.update += Tick;
            LastRun = Run;
            if (Run.Length != 0) RequestStop("代码重载：停止旧连接，不自动重连。");
        }
        internal static void Start(LauncherSettings settings)
        {
            if (Busy) { Message = "前次连接或清理尚未结束。"; return; }
            processStarted = false;
            try
            {
                string error = settings.Validate(); if (error.Length == 0) error = CoplayAdapter.Prerequisite();
                if (error.Length != 0) throw new InvalidOperationException(error);
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
                supervisor.StandardInput.Close(); supervisor.BeginOutputReadLine(); supervisor.BeginErrorReadLine();
            }
            catch (Exception e)
            {
                Message = "启动失败：" + (e is InvalidOperationException ? e.Message : e.GetType().Name); Phase = "error";
                if (!processStarted) ClearRun(); else RequestStop(Message);
            }
        }
        private static bool SafeExited(Process p) { try { return p.HasExited; } catch (InvalidOperationException) { return true; } }
        private static void OnLifecycleStop()
        {
            if (!Busy) return;
            RequestStop("Unity 退出或重载：停止本窗口的连接。", true);
        }
        internal static void RequestStop(string reason = "已请求断开；等待清理。", bool lifecycle = false)
        {
            if (Run.Length == 0) return;
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
        private static void ClearRun()
        {
            LastRun = Run.Length == 0 ? LastRun : Run;
            SessionState.EraseString(RunKey); SessionState.EraseBool(StoppingKey); SessionState.EraseBool(TransportClean);
            supervisor?.Dispose(); supervisor = null; generation = null; processStarted = false;
        }
        internal static void Tick()
        {
            if (EditorApplication.timeSinceStartup < nextPoll) return; nextPoll = EditorApplication.timeSinceStartup + 0.25;
            string run = Run; if (run.Length == 0) return;
            try
            {
                RunGeneration g = generation;
                if (g != null && g.ConnectRequested && !g.StopRequested && (!CoplayAdapter.SettingsReady() || CoplayAdapter.ManagerBusy)) RequestStop("连接设置或其他 Unity 连接发生变化，已停止本窗口连接。");
                string file = Path.Combine(run, "status.json");
                Status state = File.Exists(file) ? JsonUtility.FromJson<Status>(File.ReadAllText(file)) : null;
                if (state != null)
                {
                    Phase = state.phase ?? "unknown";
                    if (!SessionState.GetBool(StoppingKey, false)) Message = state.message ?? Phase;
                    if (state.phase == "sidecar_ready" && g != null && !g.ConnectRequested && !SessionState.GetBool(StoppingKey, false)) g.ConnectOperation = ConnectUnity(g);
                    if (state.phase == "error" && !SessionState.GetBool(StoppingKey, false)) RequestStop(state.message ?? "监督程序错误。");
                    if (state.cleanup_complete && (supervisor == null || SafeExited(supervisor)))
                    {
                        if (!SessionState.GetBool(StoppingKey, false)) RequestStop(Message);
                        bool clean = g != null ? g.ConnectionCleanupComplete : SessionState.GetBool(TransportClean, false);
                        if (clean) { ClearRun(); if (Phase != "error") Phase = "stopped"; return; }
                        Message = "Python 清理完成，Unity 私有连接清理仍未确认，禁止重新启动。";
                    }
                }
                if (supervisor != null && SafeExited(supervisor) && (state == null || !state.cleanup_complete))
                {
                    if (!SessionState.GetBool(StoppingKey, false)) RequestStop("监督进程提前退出，清理未确认。检查诊断文件，禁止自动重试。");
                    Phase = "error";
                }
            }
            catch (IOException) { }
            catch (Exception) { RequestStop("状态读取失败，停止连接。"); }
        }
    }
}
