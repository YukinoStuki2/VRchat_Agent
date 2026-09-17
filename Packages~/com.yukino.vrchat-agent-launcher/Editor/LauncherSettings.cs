using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgentLauncher
{
    [Serializable]
    internal sealed class LauncherSettings
    {
        public string python = "", uvx = "", ssh = "", host = "", user = "";
        public int sshPort = 22, remotePort = 28082;
        private static string PreferenceKey => "Yukino.AgentLauncher.Settings." + Application.dataPath;
        internal static LauncherSettings Load()
        {
            try { return JsonUtility.FromJson<LauncherSettings>(EditorPrefs.GetString(PreferenceKey, "{}")) ?? new LauncherSettings(); }
            catch { return new LauncherSettings(); }
        }
        internal void Save() { EditorPrefs.SetString(PreferenceKey, JsonUtility.ToJson(this)); }
        internal void Detect()
        {
            // File discovery only: never run PATH candidates, install runtimes or contact a network.
            if (string.IsNullOrEmpty(python)) python = Find("python.exe");
            if (string.IsNullOrEmpty(uvx)) uvx = Find("uvx.exe");
            if (string.IsNullOrEmpty(ssh)) ssh = Find("ssh.exe");
        }
        private static string Find(string executable)
        {
            var dirs = new List<string>((Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator));
            string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            dirs.Add(Path.Combine(home, ".local", "bin"));
            dirs.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "OpenSSH"));
            string pythonRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python");
            try { if (Directory.Exists(pythonRoot)) dirs.AddRange(Directory.GetDirectories(pythonRoot).OrderByDescending(x => x)); } catch { }
            foreach (string dir in dirs)
            {
                try
                {
                    string path = Path.GetFullPath(Path.Combine(dir.Trim('"'), executable));
                    if (!path.Contains("WindowsApps") && File.Exists(path)) return path;
                }
                catch { }
            }
            return "";
        }
        internal string Validate()
        {
            if (Application.platform != RuntimePlatform.WindowsEditor) return "此预览仅支持 Windows Editor + CPython 3.11+。";
            if (!Executable(python) || !Executable(uvx) || !Executable(ssh)) return "请选择可信的本地绝对路径 .exe；不要填写命令参数或网络路径。";
            if (!string.Equals(Path.GetFileName(uvx), "uvx.exe", StringComparison.OrdinalIgnoreCase)) return "uvx 路径必须指向 uvx.exe。";
            if (host.Length > 253 || !Regex.IsMatch(host, @"\A[A-Za-z0-9][A-Za-z0-9._-]*\z")) return "填写直接 DNS 主机名或 IPv4；不支持 SSH 别名、@、空格或 IPv6。";
            if (user.Length > 64 || (user.Length > 0 && !Regex.IsMatch(user, @"\A[A-Za-z0-9_][A-Za-z0-9_.-]*\z"))) return "SSH 用户名格式无效。";
            if (sshPort < 1 || sshPort > 65535 || remotePort < 1 || remotePort > 65535 || remotePort == 28080) return "端口必须为 1–65535；28080 保留给旧只读链路，请使用 28082。";
            return "";
        }
        private static bool Executable(string path)
        {
            return !string.IsNullOrWhiteSpace(path) && Path.IsPathRooted(path) && !path.StartsWith(@"\\", StringComparison.Ordinal) &&
                path.IndexOfAny(new[] { '\r', '\n', '\0', '"' }) < 0 && path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && File.Exists(path);
        }
        // Windows CRT/CommandLineToArgvW quoting; ProcessStartInfo never uses a shell.
        internal static string QuoteArgument(string value)
        {
            var b = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') { b.Append('\\', slashes * 2 + 1); b.Append(c); slashes = 0; continue; }
                b.Append('\\', slashes); slashes = 0; b.Append(c);
            }
            b.Append('\\', slashes * 2); b.Append('"');
            return b.ToString();
        }
    }
}
