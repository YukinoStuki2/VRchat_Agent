"""Published package layout and UI reachability regression. Not a visual Unity test."""
from pathlib import Path
from zipfile import ZipFile
import sys, re

def check(src):
    assert 'GUILayout.Toolbar(' in src and all('"'+s+'"' in src for s in ['连接','权限','任务']), 'No connection-first, three-page navigation'
    assert src.count('EditorGUILayout.BeginScrollView(')==src.count('EditorGUILayout.EndScrollView(')==1
    def body(name):
        start=src.index('void '+name+'('); end=src.index('\n        }', start); return src[start:end]
    main=body('OnGUI'); assert 'DrawQuickActions();' in main and 'DrawConnection();' in main and 'DrawPermissions();' in main and 'DrawTasks();' in main
    assert main.index('GUILayout.Toolbar(')<main.index('BeginScrollView(')<main.index('DrawConnection();')<main.index('EndScrollView();')<main.index('DrawQuickActions();')
    assert 'StartLocal();' not in main and 'Approve(' not in main and 'SetCapability(' not in main
    first=body('DrawConnection');assert all(s not in first for s in ['SetAssetCallbacks','ConfirmLocal','Approve(','DrawCatalog','MaterialCandidateSession.Draw()']);assert 'if (advancedConnection)' in first
    quick=body('DrawQuickActions');assert 'if (GUILayout.Button("停止连接并撤权（不回退）")) StopLocal();' in quick and 'gate.StopAll(' in quick
    assert 'if (GUILayout.Button("批准此清单"))' in body('DrawTasks') and 'gate.Approve(' in body('DrawTasks')
    assert all(x in src for x in ('DrawCatalog();','MaterialCandidateSession.Draw();','ScriptCandidateSession.Draw();','VisualCaptureSession.Draw();','BeginReload();','OnDestroy()','ConfirmLocal(pluginTrustToken)','SetProjectJobMaintenance(maintenance)'))
    print('PASS: connection-first, scrollable pages; retained approvals, stop and revoke')
if __name__=='__main__':
    with ZipFile(sys.argv[1]) as z: check(z.read('Editor/CandidateWindow.cs').decode())
