using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Services.Transport;
using WebSocketTransportClient = MCPForUnity.Editor.Services.Transport.Transports.CandidateOwnedWebSocketTransportClient;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgent
{
    [InitializeOnLoad]
    internal static class CandidateSession
    {
        // No process startup, EditorPrefs writes, or persistent approval on import.
        internal static readonly CandidateGate Gate = new CandidateGate(
            () => EditorApplication.timeSinceStartup, CoplayProjectIdentity.GetProjectHash,
            LiveConnection, Evidence, NativeRead);
        static CandidateSession()
        {
            EditorApplication.update += Gate.Observe;
            EditorApplication.quitting += Revoke;
            AssemblyReloadEvents.beforeAssemblyReload += Revoke;
            EditorApplication.playModeStateChanged += _ => Revoke();
        }
        static EditorOwnerProcess localOwner;
        static Task localStop;
        internal static bool HasLocalOwner => localOwner != null;
        internal static bool LocalOwnerReady => localOwner != null && localOwner.Ready && LiveConnection() != "";
        internal static string LocalOwnerStatus { get; private set; } = "未启动";
        internal static async Task<bool> StartLocalOwnerAsync(string python)
        {
            if (localOwner != null || ownedClient != null || EditorApplication.isCompiling ||
                EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode) return false;
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(CandidateSession).Assembly);
            string entry = package == null ? "" : Path.Combine(package.resolvedPath, "Runtime~", "launcher", "editor_owner.py");
            if (!Path.IsPathRooted(python) || !File.Exists(python) || !File.Exists(entry))
            { LocalOwnerStatus = "固定运行时或Python缺失，未启动"; return false; }
            var owner = new EditorOwnerProcess(); localOwner = owner; localStop = null;
            LocalOwnerStatus = "正在通过私有管道绑定；没有授予任务权限";
            bool ready = await owner.StartAsync(python, entry, CoplayProjectIdentity.GetProjectHash(), ConnectOwnedAsync, StopOwnedAsync);
            if (!ReferenceEquals(localOwner, owner) || !owner.Ready) ready = false;
            LocalOwnerStatus = ready ? "本地门控已连接；客户端尚需单独绑定" : "启动失败或已撤权；清理未确认时禁止重连";
            return ready;
        }
        internal static Task StopLocalOwnerAsync()
        {
            if (localOwner == null) return StopOwnedAsync();
            Gate.StopAll("本地停止，不回退文件");
#if UNITY_EDITOR
            MaterialCandidateSession.Gate.StopAll("本地停止，不回退文件");
#endif
            LocalOwnerStatus = "正在关闭本轮会话及进程";
            return localStop ?? (localStop = CloseLocalOwnerAsync(localOwner));
        }
        static async Task CloseLocalOwnerAsync(EditorOwnerProcess owner)
        {
            try
            {
                await owner.StopAsync(); await StopOwnedAsync();
                if (owner.CleanupComplete && ReferenceEquals(localOwner, owner))
                { owner.Dispose(); localOwner = null; LocalOwnerStatus = "已停止，清理已确认；权限不恢复"; }
                else LocalOwnerStatus = "清理未确认，禁止重连";
            }
            catch { LocalOwnerStatus = "清理失败，禁止重连"; }
        }
        static async void Revoke()
        {
            ownedRevoked = true;
            Gate.StopAll("编辑器生命周期变化，需重新批准");
#if UNITY_EDITOR
            MaterialCandidateSession.Gate.StopAll("编辑器生命周期变化，需重新批准");
#endif
            ownedClient?.ForceStop(); // Revoke before any bounded process cleanup wait.
            localOwner?.Dispose();
            if (localOwner != null) LocalOwnerStatus = "生命周期已撤权；不自动重连或恢复批准";
            try { await StopOwnedAsync(); }
            catch { Gate.StopAll("连接清理未确认，禁止重新连接"); }
        }
        static WebSocketTransportClient ownedClient;
        static Uri ownedEndpoint;
        static string ownedSession;
        static bool ownedRevoked;
        static Task ownedCleanup;
        static Task<bool> ownedStart;
        // Local bootstrap caller only; never exposed as an MCP command. Values must
        // come from the owner-launched sidecar, not a discovered port or model input.
        internal static async Task<bool> ConnectOwnedAsync(Uri endpoint, string bearer, byte[] certificatePin)
        {
            if (ownedClient != null || EditorApplication.isCompiling || EditorApplication.isUpdating ||
                EditorApplication.isPlayingOrWillChangePlaymode) return false;
            WebSocketTransportClient client = null;
            client = new WebSocketTransportClient(endpoint, bearer, certificatePin,
                (command, args) => DispatchOwned(client, command, args));
            ownedClient = client; ownedEndpoint = endpoint; ownedRevoked = false; ownedCleanup = null; ownedSession = null;
            try
            {
                ownedStart = client.StartAsync();
                if (await ownedStart)
                {
                    var deadline = System.Diagnostics.Stopwatch.StartNew();
                    while (ReferenceEquals(ownedClient, client) && !ownedRevoked && client.IsConnected && deadline.Elapsed.TotalSeconds < 5)
                    {
                        if (LiveConnection() != "") return true;
                        await Task.Delay(20);
                    }
                }
            }
            catch { }
            if (ReferenceEquals(ownedClient, client)) await StopOwnedAsync();
            return false;
        }
        internal static Task StopOwnedAsync()
        {
            ownedRevoked = true;
            Gate.StopAll("连接已撤权，不回退");
#if UNITY_EDITOR
            MaterialCandidateSession.Gate.StopAll("连接已撤权，不回退");
#endif
            if (ownedClient == null) return Task.CompletedTask;
            return ownedCleanup ?? (ownedCleanup = CloseOwnedAsync(ownedClient));
        }
        static async Task CloseOwnedAsync(WebSocketTransportClient client)
        {
            var starting = ownedStart;
            bool pendingStart = starting != null && !starting.IsCompleted;
            await client.StopAsync(); // Cancel before waiting for a late connect.
            if (pendingStart)
            {
                try { await starting; } catch { }
                await client.StopAsync();
            }
            client.Dispose();
            if (ReferenceEquals(ownedClient, client)) { ownedClient = null; ownedEndpoint = null; }
        }
        internal static string LiveConnection()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode) return "";
            var client = ownedClient; var state = client?.State;
            if (ownedRevoked || client == null || !client.IsConnected || state == null || !state.IsConnected ||
                string.IsNullOrEmpty(state.SessionId) || state.SessionId == "pending" ||
                ownedEndpoint == null || state.Details != ownedEndpoint.AbsoluteUri)
            { if (ownedSession != null) ownedRevoked = true; return ""; }
            if (ownedSession != null && ownedSession != state.SessionId) { ownedRevoked = true; return ""; }
            ownedSession = state.SessionId;
            return ownedSession;
        }
        static object DispatchOwned(WebSocketTransportClient source, string command, JObject args)
        {
            if (!ReferenceEquals(source, ownedClient) || LiveConnection() == "")
                return new ErrorResponse("owned_connection_required");
            JObject result;
            if (command == "vrchat_agent_dispatch") result = Gate.Dispatch(args);
#if UNITY_EDITOR
            else if (command == "vrchat_agent_material_dispatch") result = MaterialCandidateSession.Gate.Dispatch(args);
#endif
            else return new ErrorResponse("candidate_command_required");
            if ((bool?)result["success"] == true) return new SuccessResponse("受控候选操作", result["data"]);
            return new ErrorResponse((string)result["error"] ?? "candidate_denied", result["data"]);
        }
        static JObject NativeRead(string command, JObject args)
        {
            // This registry API rejects asynchronous handlers before executing them.
            // CandidateGate restricts command/action/targets; no arbitrary command route.
            object response = CommandRegistry.GetHandler(command)(args);
            JObject result = response as JObject ?? JObject.FromObject(response);
            // Validate only native success data here; the core sanitizes every
            // failure and revokes. Unknown/partial output is never a success.
            if (result["success"]?.Type == JTokenType.Boolean && (bool)result["success"] &&
                !NativeReadContract.Valid(command, result))
                return new JObject { ["success"] = false };
            return result;
        }
        static string Evidence(string assetPath)
        {
            string project = Directory.GetParent(Application.dataPath).FullName;
            string full = Path.GetFullPath(Path.Combine(project, assetPath));
            if (!full.StartsWith(Path.GetFullPath(Application.dataPath) + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new IOException("target_outside_assets");
            string current = full;
            while (current != project)
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new IOException("reparse_target_unsupported");
                current = Path.GetDirectoryName(current);
            }
            // Evidence, not an OS sandbox. Bounded target + .meta raw disk hashes catch
            // external edits even before Unity import. Dependency hash is Unity's own
            // imported-dependency view; full unimported dependency evidence is still pending.
            var state = new StringBuilder();
            state.Append(assetPath).Append('|').Append(HashFile(full)).Append('|').Append(HashFile(full + ".meta"));
            state.Append('|').Append(AssetDatabase.AssetPathToGUID(assetPath));
            state.Append('|').Append(AssetDatabase.GetAssetDependencyHash(assetPath).ToString());
            var objects = AssetDatabase.LoadAllAssetsAtPath(assetPath);
            if (objects == null || objects.Length == 0 || objects.Length > 4096) throw new IOException("asset_evidence_unavailable");
            foreach (var obj in objects.OrderBy(o => o.GetInstanceID()))
            {
                if (obj == null) throw new IOException("null_asset_evidence");
                string memory = EditorJsonUtility.ToJson(obj);
                if (memory.Length > 4 * 1024 * 1024 || state.Length + memory.Length > 16 * 1024 * 1024) throw new IOException("evidence_too_large");
                state.Append('|').Append(obj.GetInstanceID()).Append(':').Append(memory);
            }
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(state.ToString())));
        }
        static string HashFile(string path)
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("reparse_target_unsupported");
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (input.Length > 16 * 1024 * 1024) throw new IOException("evidence_too_large");
                using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(input));
            }
        }
    }

    // Compatibility tombstone: deliberately absent from global tool discovery.
    public static class VrchatAgentDispatch
    {
        public static object HandleCommand(JObject parameters)
        {
            return new ErrorResponse("owned_connection_required");
        }
    }
}
