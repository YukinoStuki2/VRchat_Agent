using System;
using System.Reflection;
using MCPForUnity.Editor.Tools;

namespace Yukino.VRChatAgent
{
    // Explicit public bridge for pinned CoplayDev 30d2207. Its identity type is
    // internal, so use .NET reflection on that exact assembly/type/public method.
    // Reuse the SAME getter as WebSocketTransportClient.StartAsync registration;
    // never reimplement its hash/cache/fallback or create a persistent session.
    public static class CoplayProjectIdentity
    {
        public static string GetProjectHash()
        {
            try
            {
                var type = typeof(CommandRegistry).Assembly.GetType("MCPForUnity.Editor.Helpers.ProjectIdentityUtility", false);
                var method = type?.GetMethod("GetProjectHash", BindingFlags.Public | BindingFlags.Static,
                    null, Type.EmptyTypes, null);
                if (method == null || method.ReturnType != typeof(string)) return "";
                string hash = (string)method.Invoke(null, null);
                return string.IsNullOrEmpty(hash) || hash == "default" ? "" : hash;
            }
            catch { return ""; } // Unsupported upstream/runtime: binding fails closed.
        }
    }
}
