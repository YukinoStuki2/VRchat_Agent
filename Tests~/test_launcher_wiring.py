"""Source/package guardrails only; NOT Unity runtime or Windows validation."""
import json
import re
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'Packages~' / 'com.yukino.vrchat-agent-launcher'

class LauncherWiring(unittest.TestCase):
    def source(self, name):
        path = PKG / 'Editor' / name
        self.assertTrue(path.is_file(), name + ' implementation missing')
        return path.read_text()

    def test_preview_editor_only_package(self):
        self.assertTrue((PKG / 'package.json').is_file(), 'launcher package missing')
        p = json.loads((PKG / 'package.json').read_text())
        self.assertEqual(p['version'], '0.1.0-preview.3')
        self.assertEqual(p['dependencies']['com.coplaydev.unity-mcp'], '10.2.0')
        self.assertNotIn('com.coplaydev.unity-mcp',p['vpmDependencies'])
        for field in ('dependencies', 'vpmDependencies'):
            self.assertEqual(p[field]['com.yukino.vrchat-readonly-mcp'], '0.1.2')
            self.assertEqual(p[field]['com.yukino.vrchat-managed-editing'], '0.1.0-preview.2')
        a = json.loads((PKG / 'Editor/Yukino.VRChatAgentLauncher.Editor.asmdef').read_text())
        self.assertEqual(a['includePlatforms'], ['Editor'])
        self.assertIn('MCPForUnity.Editor', a['references'])

    def test_manual_window_has_no_tool_or_automatic_connect(self):
        s = self.source('LauncherWindow.cs')
        for token in ('Tools/Yukino/Agent Connection Manager', '一键连接', '断开连接', '设置', '直接主机名', '准备 Coplay 本地设置'):
            self.assertIn(token, s)
        self.assertNotIn('McpForUnityTool', s)
        self.assertNotIn('GrantLocally', s)
        enable = re.search(r'void OnEnable\(\)\s*\{([^}]+)', s).group(1)
        self.assertNotIn('Connect', enable)
        self.assertIn('OnDisable', s)

    def test_owned_supervisor_contract_and_cleanup(self):
        s = self.source('LauncherSession.cs')
        for token in ('launcher_supervisor.py', '--config ', 'uvx_path', 'expected_project', 'sidecar_ready', 'SessionState', 'beforeAssemblyReload', 'EditorApplication.quitting', 'UseShellExecute = false', 'RedirectStandardInput = true', 'BeginOutputReadLine', 'BeginErrorReadLine', 'Guid.NewGuid()', 'File.WriteAllText', 'cleanup_complete'):
            self.assertIn(token, s)
        for forbidden in ('.Kill(', 'GetProcessById', 'WaitForExit', '.Wait()', '.Result', 'Server.Start', 'Server.Stop', 'AssetDatabase.Refresh'):
            self.assertNotIn(forbidden, s)
        self.assertIn('RequestStop', s)
        self.assertIn('ConnectionCleanupComplete', s)
        self.assertIn('ConnectOperation', s)
        self.assertIn('processStarted', s)
        self.assertIn('LastRun = Run', s)
        self.assertNotIn('async void ConnectUnity', s)

    def test_pinned_adapter_narrow_transport_and_revoke(self):
        s = self.source('CoplayAdapter.cs')
        for token in ('10.2.0', 'new WebSocketTransportClient(MCPServiceLocator.ToolDiscovery)', 'GetClient(TransportMode.Http)', '_httpStartTask', '_lifecycleCts', '_socket', 'MCPForUnity.Editor', 'Yukino.VRChatManagedEditing.Editor', 'Yukino.VRChatManagedEditing.ManagedSession', '"Revoke"', 'Type.EmptyTypes', 'MCPForUnity.AutoStartOnLoad', '18081'):
            self.assertIn(token, s)
        for forbidden in ('GrantLocally', 'StartLocalHttpServer', 'StopLocalHttpServer', 'Configure(', 'SetToolEnabled', 'ForceStop(', 'CancelPendingResume', 'CancelPendingReconnect', 'StartAsync(TransportMode.Http)'):
            self.assertNotIn(forbidden, s)

    def test_config_not_freeform_shell_or_credentials(self):
        s = self.source('LauncherSettings.cs')
        for token in ('28082', '28080', 'python.exe', 'uvx.exe', 'ssh.exe', 'Path.IsPathRooted', 'Regex.IsMatch', 'QuoteArgument'):
            self.assertIn(token, s)
        self.assertNotIn('Password', s)
        self.assertNotIn('private_key', s)

    def test_recovery_optin_and_cancel_boundaries(self):
        settings=self.source('LauncherSettings.cs')
        self.assertIn('autoRecoverAfterImport = false',settings)
        session=self.source('LauncherSession.cs')
        for token in ('compilationStarted', 'BeforeReload', 'OnQuit', 'RecoveryState', 'preserveRecovery', 'recovery.Consume()', 'cleanup_complete', 'ConnectionCleanupComplete', 'WindowOpen', 'RecoveryPending', 'PROJECT_UNAVAILABLE'):
            self.assertIn(token,session)
        window=self.source('LauncherWindow.cs')
        for token in ('导入／重编译后恢复连接', 'OnDestroy', 'WindowClosed', 'autoRecoverAfterImport'):
            self.assertIn(token,window)
        self.assertNotIn('GrantLocally',session)

if __name__ == '__main__': unittest.main()
