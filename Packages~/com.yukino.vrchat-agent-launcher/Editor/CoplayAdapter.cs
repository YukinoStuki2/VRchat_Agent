using System;
using System.Linq;
using System.Net.WebSockets;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Services.Transport;
using MCPForUnity.Editor.Services.Transport.Transports;
using UnityEditor;

namespace Yukino.VRChatAgentLauncher
{
    internal static class CoplayAdapter
    {
        internal const string Endpoint = "http://127.0.0.1:18081";
        private const string AutoStart = "MCPForUnity.AutoStartOnLoad";
        private static Assembly CoplayAssembly => typeof(MCPServiceLocator).Assembly;
        private static FieldInfo Field(string name) => typeof(WebSocketTransportClient).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
        private static FieldInfo ManagerStart => typeof(TransportManager).GetField("_httpStartTask", BindingFlags.Instance | BindingFlags.NonPublic);
        internal static string Prerequisite()
        {
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(CoplayAssembly);
            if (CoplayAssembly.GetName().Name != "MCPForUnity.Editor" || package == null || package.version != "10.2.0") return "需要官方 Coplay 10.2.0。";
            if (Field("_lifecycleCts")?.FieldType != typeof(CancellationTokenSource) || Field("_socket")?.FieldType != typeof(ClientWebSocket) || Field("_endpointUri")?.FieldType != typeof(Uri) || ManagerStart?.FieldType != typeof(Task<bool>)) return "固定版连接 API 不匹配，拒绝启动。";
            return ManagedRevoke() == null ? "需要受控编辑 0.1.0-preview.2 代码依赖（不会授予权限）。" : "";
        }
        internal static bool SettingsReady()
        {
            var config = EditorConfigurationCache.Instance; config.Refresh();
            return config.UseHttpTransport && !HttpEndpointUtility.IsRemoteScope() &&
                string.Equals(HttpEndpointUtility.GetBaseUrl().TrimEnd('/'), Endpoint, StringComparison.Ordinal) && !EditorPrefs.GetBool(AutoStart, false);
        }
        internal static bool Pending => SessionState.GetBool("MCPForUnity.ResumeHttpAfterReload", false) || SessionState.GetBool("HttpAutoStartHandler.ConnectPending", false);
        internal static bool ManagerBusy
        {
            get
            {
                var manager = MCPServiceLocator.TransportManager;
                var task = ManagerStart?.GetValue(manager) as Task;
                var client = manager.GetClient(TransportMode.Http);
                // An existing lifecycle can be reconnecting even when IsConnected is false.
                bool live = client is WebSocketTransportClient ws && Field("_lifecycleCts")?.GetValue(ws) != null;
                return Pending || (task != null && !task.IsCompleted) || client?.IsConnected == true || live;
            }
        }
        internal static bool ClientConnected => LauncherSession.OwnedConnected;
        internal static string SessionId => LauncherSession.OwnedSessionId;
        internal static void SetupExplicitly()
        {
            if (Prerequisite().Length != 0 || ManagerBusy || LauncherSession.Busy) throw new InvalidOperationException("先断开 Coplay 面板连接并等待重连结束。");
            var config = EditorConfigurationCache.Instance;
            config.SetUseHttpTransport(true); config.SetHttpTransportScope("local"); config.SetHttpBaseUrl(Endpoint);
            EditorPrefs.SetBool(AutoStart, false);
            if (!SettingsReady()) throw new InvalidOperationException("设置回读失败。");
        }
        internal static WebSocketTransportClient CreateOwned()
        {
            if (Prerequisite().Length != 0 || !SettingsReady() || ManagerBusy) throw new InvalidOperationException("连接前设置已变更，或 Coplay 面板已有连接。请人工断开后再试。");
            return new WebSocketTransportClient(MCPServiceLocator.ToolDiscovery);
        }
        internal static Task<bool> StartOwned(WebSocketTransportClient client)
        {
            // Fresh pinned client: StopAsync sees null lifecycle and completes synchronously;
            // upstream captures its endpoint before the first asynchronous connection await.
            if (!SettingsReady() || ManagerBusy || Field("_lifecycleCts").GetValue(client) != null) throw new InvalidOperationException("本地连接前提已变更。");
            Task<bool> task = client.StartAsync();
            Uri endpoint = Field("_endpointUri").GetValue(client) as Uri;
            if (endpoint == null || endpoint.AbsoluteUri != "ws://127.0.0.1:18081/hub/plugin")
            { AbortOwned(client); throw new InvalidOperationException("实际连接地址不匹配。"); }
            return task;
        }
        internal static bool AbortOwned(WebSocketTransportClient client)
        {
            if (client == null) return true;
            try
            {
                var cts = Field("_lifecycleCts").GetValue(client) as CancellationTokenSource;
                var socket = Field("_socket").GetValue(client) as ClientWebSocket;
                cts?.Cancel(); socket?.Abort();
                return (cts == null || cts.IsCancellationRequested) && (socket == null || socket.State == WebSocketState.Aborted || socket.State == WebSocketState.Closed);
            }
            catch { return false; }
        }
        private static MethodInfo ManagedRevoke()
        {
            Assembly assembly = AppDomain.CurrentDomain.GetAssemblies().SingleOrDefault(a => a.GetName().Name == "Yukino.VRChatManagedEditing.Editor");
            if (assembly == null) return null;
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(assembly);
            if (package == null || package.name != "com.yukino.vrchat-managed-editing" || package.version != "0.1.0-preview.2") return null;
            MethodInfo method = assembly.GetType("Yukino.VRChatManagedEditing.ManagedSession", false)?.GetMethod("Revoke", BindingFlags.Static | BindingFlags.NonPublic, null, Type.EmptyTypes, null);
            return method != null && method.ReturnType == typeof(void) ? method : null;
        }
        internal static void RevokeManaged()
        {
            MethodInfo method = ManagedRevoke(); if (method == null) throw new InvalidOperationException("撤销接口不匹配。"); method.Invoke(null, null);
        }
    }
}
