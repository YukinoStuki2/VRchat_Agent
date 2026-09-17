using System;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgentLauncher
{
    public sealed class LauncherWindow : EditorWindow
    {
        private LauncherSettings settings;
        private Vector2 scroll;
        private bool safetyAcknowledged;
        private string notice = "";
        [MenuItem("Tools/Yukino/Agent Connection Manager")]
        private static void Open() { GetWindow<LauncherWindow>("Agent 连接管理"); }
        private void OnEnable()
        {
            settings = LauncherSettings.Load();
            LauncherSession.WindowOpen = true;
            minSize = new Vector2(510, 570);
            EditorApplication.update += Repaint;
        }
        private void OnDisable()
        {
            EditorApplication.update -= Repaint;
            LauncherSession.WindowClosed();
        }
        private void OnDestroy() { LauncherSession.WindowClosed(true); }
        private void OnGUI()
        {
            if (settings == null) settings = LauncherSettings.Load();
            scroll = EditorGUILayout.BeginScrollView(scroll);
            EditorGUILayout.LabelField("Yukino Agent 连接管理 · Preview", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox("点击连接才会启动：固定版基础 MCP → Unity Connect → 受限 Bridge → SSH。不会开启 Preview/Apply 权限。关闭窗口或退出会取消恢复；可选导入后恢复连接，权限仍关闭。更新前请先断开。", MessageType.Info);
            EditorGUILayout.LabelField("启动阶段", LauncherSession.Phase);
            EditorGUILayout.HelpBox(LauncherSession.Message, MessageType.None);
            try
            {
                EditorGUILayout.LabelField("Unity HTTP", CoplayAdapter.ClientConnected ? "已连接" : "未连接");
                EditorGUILayout.LabelField("Unity 注册", CoplayAdapter.SessionId);
            }
            catch { EditorGUILayout.LabelField("Unity HTTP", "未能读取；请核对 Coplay 版本"); }
            EditorGUILayout.Space();
            using (new EditorGUI.DisabledScope(LauncherSession.Busy || LauncherSession.RecoveryPending))
            {
                EditorGUILayout.LabelField("设置（仅本机，不写入工程 Git）", EditorStyles.boldLabel);
                settings.python = Executable("Python 3.11+", settings.python);
                settings.uvx = Executable("uvx.exe", settings.uvx);
                settings.ssh = Executable("ssh.exe", settings.ssh);
                if (GUILayout.Button("自动查找已安装程序（不安装）")) settings.Detect();
                settings.host = EditorGUILayout.TextField("SSH 直接主机名 / IPv4", settings.host);
                settings.user = EditorGUILayout.TextField("SSH 用户名", settings.user);
                settings.sshPort = EditorGUILayout.IntField("SSH 服务端口", settings.sshPort);
                settings.remotePort = EditorGUILayout.IntField("管理机受限转发端口", settings.remotePort);
                EditorGUILayout.LabelField("本机固定端口", "MCP 18081 → 受限 Bridge 18082");
                settings.autoRecoverAfterImport = EditorGUILayout.ToggleLeft("导入／重编译后恢复连接（默认关闭，不恢复编辑权限）", settings.autoRecoverAfterImport);
                if (GUILayout.Button("保存设置")) { settings.Save(); notice = "已保存到本机 EditorPrefs。"; }
                if (GUILayout.Button("准备 Coplay 本地设置"))
                {
                    if (EditorUtility.DisplayDialog("本机连接设置", "将 Coplay 切换到本地 HTTP 18081，并关闭其开机自动启动。此设置可能影响同一 Windows 用户的其他工程。不会修改模型。已连接时请先在 Coplay 面板断开。", "确认设置", "取消"))
                    {
                        try { CoplayAdapter.SetupExplicitly(); notice = "Coplay 本地设置已写入并回读验证。"; }
                        catch (Exception e) { notice = "设置失败：" + e.GetType().Name; }
                    }
                }
                EditorGUILayout.HelpBox("首次需要在系统配置 SSH 密钥 / ssh-agent，并人工确认主机指纹。本包不保存密码，不安装密钥，不使用 SSH config 别名或额外转发。首次 uvx 可能下载固定版本运行环境。", MessageType.Warning);
                safetyAcknowledged = EditorGUILayout.ToggleLeft("我已关闭旧 28080 直通和手动 Bridge/SSH，服务器 GatewayPorts 为 no", safetyAcknowledged);
                using (new EditorGUI.DisabledScope(!safetyAcknowledged))
                    if (GUILayout.Button("一键连接", GUILayout.Height(32))) { settings.Save(); LauncherSession.Start(settings); }
            }
            using (new EditorGUI.DisabledScope(!LauncherSession.Busy && !LauncherSession.RecoveryPending))
                if (GUILayout.Button("断开连接（撤销权限并清理自有进程）")) LauncherSession.RequestStop();
            if (GUILayout.Button("刷新状态")) LauncherSession.Tick();
            using (new EditorGUI.DisabledScope(string.IsNullOrEmpty(LauncherSession.LastRun)))
                if (GUILayout.Button("查看本次诊断文件夹")) EditorUtility.RevealInFinder(LauncherSession.LastRun);
            if (notice.Length != 0) EditorGUILayout.HelpBox(notice, MessageType.Info);
            EditorGUILayout.HelpBox("ALCOM 更新此包即可同步更新窗口和内置 Bridge。此预览尚待 Windows / Unity 实机验收；请先备份或使用临时工程。", MessageType.Warning);
            EditorGUILayout.EndScrollView();
        }
        private static string Executable(string label, string value)
        {
            EditorGUILayout.BeginHorizontal();
            value = EditorGUILayout.TextField(label, value);
            if (GUILayout.Button("选择", GUILayout.Width(48)))
            {
                string path = EditorUtility.OpenFilePanel(label, "", "exe");
                if (!string.IsNullOrEmpty(path)) value = path;
            }
            EditorGUILayout.EndHorizontal(); return value;
        }
    }
}
