using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Local, single-use owner. Never registered as a tool or given model-provided paths.
    internal sealed class EditorOwnerProcess : IDisposable
    {
        // Fixed package-relative entry only; no PATH search or system fallback.
        internal static string ResolvePortablePython(string package)
        {
            if (string.IsNullOrWhiteSpace(package) || !Path.IsPathRooted(package))
                throw new InvalidOperationException("portable_package_required");
            bool windows = Environment.OSVersion.Platform == PlatformID.Win32NT;
            if ((!windows && !RuntimeInformation.IsOSPlatform(OSPlatform.Linux)) ||
                RuntimeInformation.ProcessArchitecture != Architecture.X64)
                throw new InvalidOperationException("portable_platform_unsupported");
            string executable = windows ? "python/python.exe" : "python/bin/python3.11";
            string python = Path.Combine(Path.GetFullPath(package), "Runtime~", executable);
            string runtime = Path.Combine(Path.GetFullPath(package), "Runtime~");
            var descriptor = Parse(new UTF8Encoding(false, true).GetString(
                PortableBytes(Path.Combine(runtime, "portable-launch.json"), 8192)));
            if (!descriptor.Properties().Select(p=>p.Name).OrderBy(x=>x).SequenceEqual(
                new[] {"files", "platform", "python_version", "schema"}) ||
                descriptor["schema"].Type != JTokenType.Integer || (int)descriptor["schema"] != 1 ||
                descriptor["platform"].Type != JTokenType.String ||
                (string)descriptor["platform"] != (windows ? "windows-x86_64" : "linux-x86_64") ||
                descriptor["python_version"].Type != JTokenType.String || (string)descriptor["python_version"] != "3.11.16" ||
                !(descriptor["files"] is JObject files))
                throw new InvalidOperationException("portable_descriptor_invalid");
            var names = new[] {executable, "launcher/editor_owner.py", "launcher/direct_python.py"};
            if (!files.Properties().Select(p=>p.Name).OrderBy(x=>x).SequenceEqual(names.OrderBy(x=>x)))
                throw new InvalidOperationException("portable_file_set_invalid");
            foreach (string name in names)
            {
                if (files[name].Type != JTokenType.String) throw new InvalidOperationException("portable_hash_invalid");
                using (var hash = SHA256.Create())
                {
                    string digest = BitConverter.ToString(hash.ComputeHash(PortableBytes(Path.Combine(runtime, name), 128 * 1024 * 1024))).Replace("-", "").ToLowerInvariant();
                    if (digest != (string)files[name]) throw new InvalidOperationException("portable_entry_drift");
                }
            }
            return python;
        }

        static byte[] PortableBytes(string path, int limit)
        {
            // Reject existing links/junctions, but do not claim OS sandbox/atomic
            // hash-to-exec identity. An actor able to replace the package is trusted.
            for (string current = path; current != null; current = Path.GetDirectoryName(current))
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("portable_reparse_refused");
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (input.Length > limit) throw new IOException("portable_file_oversize");
                using (var output = new MemoryStream())
                {
                    var buffer = new byte[8192]; int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
                    {
                        if (output.Length + count > limit) throw new IOException("portable_file_oversize");
                        output.Write(buffer, 0, count);
                    }
                    return output.ToArray();
                }
            }
        }

        internal static string HermesArguments(JObject settings, bool allowed)
        {
            if (settings == null) return "";
            if (!allowed || !settings.Properties().Select(p=>p.Name).OrderBy(x=>x).SequenceEqual(new[] {"host","port","remote_port","user"}) ||
                settings["host"].Type != JTokenType.String || settings["user"].Type != JTokenType.String ||
                settings["port"].Type != JTokenType.Integer || settings["remote_port"].Type != JTokenType.Integer)
                throw new ArgumentException("owner_ssh_settings_invalid");
            string host=(string)settings["host"], user=(string)settings["user"];
            long port=(long)settings["port"], remote=(long)settings["remote_port"];
            if (!System.Text.RegularExpressions.Regex.IsMatch(host, @"\A[A-Za-z0-9][A-Za-z0-9._-]{0,252}\z") ||
                (user.Length>0 && !System.Text.RegularExpressions.Regex.IsMatch(user, @"\A[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\z")) ||
                port<1 || port>65535 || remote<1024 || remote>65535)
                throw new ArgumentException("owner_ssh_settings_invalid");
            return " --hermes-host "+Quote(host)+" --hermes-user "+Quote(user)+
                " --hermes-port "+port+" --hermes-forward-port "+remote;
        }
        internal static string CodexArguments(string executable, string project, bool allowed)
        {
            if (executable == null && project == null) return "";
            if (!allowed || string.IsNullOrWhiteSpace(executable) || string.IsNullOrWhiteSpace(project) ||
                !Path.IsPathRooted(executable) || !Path.IsPathRooted(project) ||
                !string.Equals(Path.GetExtension(executable), ".exe", StringComparison.OrdinalIgnoreCase) ||
                !File.Exists(executable) || !Directory.Exists(project))
                throw new ArgumentException("owner_codex_settings_invalid");
            return " --codex-executable " + Quote(executable) + " --codex-project " + Quote(project);
        }
        bool remoteHandoff, localCodex;
        Process process;
        Task stderrDrain, monitor, starting;
        Func<Task> disconnect;
        bool used, stopping, disposed;
        public bool Ready { get; private set; }
        public bool CleanupComplete { get; private set; }
        public int OwnerPid { get; private set; }

        internal Task<bool> StartAsync(string python, string entry, string project,
            Func<Uri, string, byte[], Task<bool>> connect, Func<Task> close, bool allowHermes = false, bool allowCodex = false, JObject hermesSsh = null, string codexExecutable = null, string codexProject = null)
        {
            if (used || disposed) throw new InvalidOperationException("owner_single_use");
            used = true; disconnect = close;
            var task = StartCoreAsync(python, entry, project, connect, allowHermes, allowCodex, hermesSsh == null ? null : (JObject)hermesSsh.DeepClone(), codexExecutable, codexProject);
            starting = task;
            return task;
        }
        async Task<bool> StartCoreAsync(string python, string entry, string project,
            Func<Uri, string, byte[], Task<bool>> connect, bool allowHermes, bool allowCodex, JObject hermesSsh, string codexExecutable, string codexProject)
        {
            try
            {
                if (!Path.IsPathRooted(python) || !Path.IsPathRooted(entry) || !File.Exists(python) ||
                    !File.Exists(entry) || string.IsNullOrWhiteSpace(project) || project.Length > 256)
                    throw new InvalidOperationException("owner_path_invalid");
                string sshArguments = HermesArguments(hermesSsh, allowHermes);
                remoteHandoff = hermesSsh != null;
                string codexArguments = CodexArguments(codexExecutable, codexProject, allowCodex);
                localCodex = codexExecutable != null;
                var info = new ProcessStartInfo(python) {
                    Arguments = "-I -B " + Quote(entry) + " --project " + Quote(project) +
                        " --parent-pid " + Process.GetCurrentProcess().Id +
                        (allowHermes ? " --client hermes" : "") + (allowCodex ? " --client codex" : "") + sshArguments + codexArguments,
                    UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = new UTF8Encoding(false, true), StandardErrorEncoding = Encoding.UTF8,
                    WorkingDirectory = Path.GetDirectoryName(entry)
                };
                info.EnvironmentVariables.Clear();
                foreach (string name in new[] {"SystemRoot","WINDIR","PATH","COMSPEC","PATHEXT","TEMP","TMP","HOME","USERPROFILE","SSH_AUTH_SOCK"})
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
                var expected = new[] {"kind","version","owner_pid","project","endpoint","pin","unity_bearer","expires_at","clients"};
                if (!bundle.Properties().Select(p=>p.Name).OrderBy(x=>x).SequenceEqual(expected.OrderBy(x=>x)) ||
                    bundle["version"].Type != JTokenType.Integer || (int)bundle["version"] != 2 ||
                    bundle["owner_pid"].Type != JTokenType.Integer || (int)bundle["owner_pid"] != OwnerPid ||
                    bundle["kind"].Type != JTokenType.String || (string)bundle["kind"] != "unity_binding" ||
                    bundle["project"].Type != JTokenType.String || (string)bundle["project"] != project ||
                    bundle["expires_at"].Type != JTokenType.Integer)
                    throw new InvalidOperationException("owner_bundle_invalid");
                var clients = new JArray();
                if (allowHermes) clients.Add("hermes");
                if (allowCodex) clients.Add("codex");
                if (!JToken.DeepEquals(bundle["clients"], clients))
                    throw new InvalidOperationException("owner_client_selection_mismatch");
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
                JObject ready = Parse(await ReadLineAsync(process.StandardOutput, remoteHandoff ? 36 : 6));
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
                    (bool?)result["probe_session_cleanup_confirmed"] == true &&
                    (!remoteHandoff || (bool?)result["handoff_cleanup_confirmed"] == true) &&
                    (!localCodex || (bool?)result["codex_cleanup_complete"] == true);
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
