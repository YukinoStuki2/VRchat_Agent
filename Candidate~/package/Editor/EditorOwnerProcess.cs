using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Local, single-use owner. Never registered as a tool or given model-provided paths.
    internal sealed class EditorOwnerProcess : IDisposable
    {
        Process process;
        Task stderrDrain, monitor, starting;
        Func<Task> disconnect;
        bool used, stopping, disposed;
        public bool Ready { get; private set; }
        public bool CleanupComplete { get; private set; }
        public int OwnerPid { get; private set; }

        internal Task<bool> StartAsync(string python, string entry, string project,
            Func<Uri, string, byte[], Task<bool>> connect, Func<Task> close)
        {
            if (used || disposed) throw new InvalidOperationException("owner_single_use");
            used = true; disconnect = close;
            var task = StartCoreAsync(python, entry, project, connect);
            starting = task;
            return task;
        }
        async Task<bool> StartCoreAsync(string python, string entry, string project,
            Func<Uri, string, byte[], Task<bool>> connect)
        {
            try
            {
                if (!Path.IsPathRooted(python) || !Path.IsPathRooted(entry) || !File.Exists(python) ||
                    !File.Exists(entry) || string.IsNullOrWhiteSpace(project) || project.Length > 256)
                    throw new InvalidOperationException("owner_path_invalid");
                var info = new ProcessStartInfo(python) {
                    Arguments = "-I -B " + Quote(entry) + " --project " + Quote(project) +
                        " --parent-pid " + Process.GetCurrentProcess().Id,
                    UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = new UTF8Encoding(false, true), StandardErrorEncoding = Encoding.UTF8,
                    WorkingDirectory = Path.GetDirectoryName(entry)
                };
                info.EnvironmentVariables.Clear();
                foreach (string name in new[] {"SystemRoot","WINDIR","PATH","COMSPEC","PATHEXT","TEMP","TMP","HOME","USERPROFILE"})
                {
                    string value = Environment.GetEnvironmentVariable(name);
                    if (value != null) info.EnvironmentVariables[name] = value;
                }
                info.EnvironmentVariables["PYTHONUTF8"] = "1";
                info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                info.EnvironmentVariables["DISABLE_TELEMETRY"] = "true";
                // Inspect only interpreter metadata before issuing any credential.
                // The selected Windows venv is a redirector; CPython's own launch
                // hint preserves that venv while the real interpreter is our child.
                string arguments = info.Arguments;
                info.Arguments = "-I -B " + Quote(Path.Combine(Path.GetDirectoryName(entry), "direct_python.py"));
                using (var probe = new Process {StartInfo = info})
                {
                    if (stopping || !probe.Start()) throw new InvalidOperationException("python_probe_refused");
                    var drain = DrainAsync(probe.StandardError);
                    try
                    {
                        probe.StandardInput.Close();
                        var metadata = Parse(await ReadLineAsync(probe.StandardOutput, 5));
                        if (!probe.WaitForExit(3000) || probe.ExitCode != 0 || metadata.Count != 3 ||
                            metadata["executable"]?.Type != JTokenType.String || metadata["selected"]?.Type != JTokenType.String ||
                            metadata["windows"]?.Type != JTokenType.Boolean)
                            throw new InvalidOperationException("python_probe_invalid");
                        bool windows = Environment.OSVersion.Platform == PlatformID.Win32NT;
                        var comparison = windows ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
                        string direct = (string)metadata["executable"], selected = (string)metadata["selected"];
                        if ((bool)metadata["windows"] != windows || !Path.IsPathRooted(direct) || !File.Exists(direct) ||
                            !string.Equals(Path.GetFullPath(selected), Path.GetFullPath(python), comparison))
                            throw new InvalidOperationException("python_probe_mismatch");
                        info.FileName = direct;
                        if (windows) info.EnvironmentVariables["__PYVENV_LAUNCHER__"] = selected;
                    }
                    finally
                    {
                        if (!probe.HasExited) { probe.Kill(); probe.WaitForExit(3000); }
                        await drain;
                    }
                }
                info.Arguments = arguments;
                process = new Process {StartInfo = info};
                if (stopping || !process.Start()) throw new InvalidOperationException("owner_start_refused");
                OwnerPid = process.Id;
                stderrDrain = DrainAsync(process.StandardError); // Discard, never persist child logs/secrets.
                await process.StandardInput.WriteAsync("start\n"); await process.StandardInput.FlushAsync();
                JObject bundle = Parse(await ReadLineAsync(process.StandardOutput, 12));
                var expected = new[] {"kind","version","owner_pid","project","endpoint","pin","unity_bearer","expires_at"};
                if (!bundle.Properties().Select(p=>p.Name).OrderBy(x=>x).SequenceEqual(expected.OrderBy(x=>x)) ||
                    bundle["version"].Type != JTokenType.Integer || (int)bundle["version"] != 1 ||
                    bundle["owner_pid"].Type != JTokenType.Integer || (int)bundle["owner_pid"] != OwnerPid ||
                    bundle["kind"].Type != JTokenType.String || (string)bundle["kind"] != "unity_binding" ||
                    bundle["project"].Type != JTokenType.String || (string)bundle["project"] != project ||
                    bundle["expires_at"].Type != JTokenType.Integer)
                    throw new InvalidOperationException("owner_bundle_invalid");
                long remaining = (long)bundle["expires_at"] - DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                if (remaining <= 0 || remaining > 3600) throw new InvalidOperationException("owner_expired");
                foreach (string key in new[] {"endpoint","pin","unity_bearer"})
                    if (bundle[key].Type != JTokenType.String) throw new InvalidOperationException("owner_bundle_type");
                var uri = new Uri((string)bundle["endpoint"], UriKind.Absolute);
                if (uri.Scheme != "wss" || uri.Host != "127.0.0.1" || uri.Port < 1 ||
                    uri.AbsolutePath != "/hub/plugin" || uri.Query != "" || uri.Fragment != "" || uri.UserInfo != "")
                    throw new InvalidOperationException("owner_endpoint_invalid");
                string pin = (string)bundle["pin"], bearer = (string)bundle["unity_bearer"];
                if (pin.Length != 64 || pin.Any(ch=>!Uri.IsHexDigit(ch)) || bearer.Length < 32 ||
                    bearer.Length > 8192 || bearer.Any(ch=>!(char.IsLetterOrDigit(ch) || ch=='.' || ch=='_' || ch=='-')))
                    throw new InvalidOperationException("owner_material_invalid");
                byte[] bytes = Enumerable.Range(0,32).Select(i=>Convert.ToByte(pin.Substring(i*2,2),16)).ToArray();
                bundle.RemoveAll();
                if (stopping || !await connect(uri,bearer,bytes)) throw new InvalidOperationException("owner_connect_refused");
                bearer = null;
                JObject ready = Parse(await ReadLineAsync(process.StandardOutput, 6));
                if (stopping || ready.Count != 1 || (string)ready["kind"] != "ready")
                    throw new InvalidOperationException("owner_gate_not_ready");
                Ready = true; monitor = MonitorAsync(remaining);
                return true;
            }
            catch
            {
                Ready = false; Terminate();
                if (stderrDrain != null) { try { await stderrDrain; } catch { } }
                if (disconnect != null) await disconnect();
                return false;
            }
        }
        async Task MonitorAsync(long lifetime)
        {
            try
            {
                JObject result = Parse(await ReadLineAsync(process.StandardOutput, lifetime + 8));
                if ((string)result["kind"] != "stopped") return;
                var deadline = Stopwatch.StartNew();
                while (!process.HasExited && deadline.Elapsed.TotalSeconds < 5) await Task.Delay(20);
                CleanupComplete = process.HasExited && process.ExitCode == 0 &&
                    (bool?)result["process_cleanup_complete"] == true && (bool?)result["probe_cleanup_complete"] == true &&
                    (bool?)result["probe_session_cleanup_confirmed"] == true;
                if (stderrDrain != null && process.HasExited) await stderrDrain;
            }
            catch { CleanupComplete = false; }
            finally
            {
                Ready = false;
                if (!CleanupComplete) Terminate();
                if (disconnect != null) await disconnect();
            }
        }
        internal async Task StopAsync()
        {
            Ready = false; stopping = true;
            try
            {
                if (process != null && !process.HasExited)
                { await process.StandardInput.WriteAsync("stop\n"); await process.StandardInput.FlushAsync(); process.StandardInput.Close(); }
            }
            catch { }
            if (starting != null) { try { await starting; } catch { } }
            if (monitor != null)
            {
                if (await Task.WhenAny(monitor,Task.Delay(12000)) != monitor) Terminate();
                await monitor;
            }
            else if (disconnect != null) await disconnect();
        }
        static async Task DrainAsync(StreamReader reader)
        {
            char[] buffer = new char[512];
            while (await reader.ReadAsync(buffer,0,buffer.Length) != 0) { }
        }
        static async Task<string> ReadLineAsync(StreamReader reader, double seconds)
        {
            var text = new StringBuilder(); char[] ch = new char[1];
            Task deadline = Task.Delay(TimeSpan.FromSeconds(seconds));
            while (text.Length <= 16384)
            {
                var read = reader.ReadAsync(ch,0,1);
                if (await Task.WhenAny(read,deadline) != read) throw new TimeoutException("owner_pipe_timeout");
                if (await read == 0) throw new IOException("owner_pipe_closed");
                if (ch[0]=='\n') return text.ToString();
                text.Append(ch[0]);
            }
            throw new IOException("owner_pipe_oversize");
        }
        static JObject Parse(string line) => JObject.Parse(line,
            new JsonLoadSettings {DuplicatePropertyNameHandling=DuplicatePropertyNameHandling.Error});
        static string Quote(string value)
        {
            if (value.IndexOfAny(new[] {'\0','\r','\n'}) >= 0) throw new ArgumentException("owner_argument_invalid");
            var text = new StringBuilder("\""); int slashes = 0;
            foreach(char ch in value)
            {
                if(ch=='\\') { slashes++; continue; }
                text.Append('\\',ch=='"' ? slashes*2+1 : slashes); text.Append(ch); slashes=0;
            }
            return text.Append('\\',slashes*2).Append('"').ToString();
        }
        void Terminate()
        {
            try
            {
                if (process == null || process.HasExited) return;
                // EOF reaches the owned supervisor even while Unity's main thread
                // cannot run continuations during domain reload. Let it delete its
                // probe session and close its exact runtime owner before exiting.
                process.StandardInput.Close();
                if (process.WaitForExit(12000)) return;
                // Windows has the verified kill-on-close runtime Job. Linux has
                // no equivalent supervisor-crash promise; never orphan it by Kill.
                if (Environment.OSVersion.Platform == PlatformID.Win32NT)
                { process.Kill(); process.WaitForExit(3000); }
                CleanupComplete = false;
            }
            catch { CleanupComplete = false; }
        }
        public void Dispose()
        {
            if(disposed)return; disposed=true; stopping=true; Ready=false;
            Terminate(); process?.Dispose();
        }
    }
}
