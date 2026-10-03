"""Test-only exact-method extraction from pinned Coplay ManageScene.

Compiles original parser, dispatch and three original readers. Unrelated method
bodies throw; Unity APIs are fixtures. NOT full-source/Unity compilation proof,
not an installed reader. Refuse any upstream drift before extracting bytes.
"""
import hashlib
from pathlib import Path

PIN = '1fc7de5f27d4213bf3f1173cb9589e6056590c70bcb894c4a86483d789ac8e15'


def assemble(editor_root, output):
    raw = (Path(editor_root) / 'Tools/ManageScene.cs').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN:
        raise ValueError('scene_native_source_drift')
    text = raw.decode('utf-8')
    names = ('ParseFloatArray', 'ToSceneCommand', 'HandleCommand',
             'GetActiveSceneInfo', 'GetBuildSettingsScenes', 'GetLoadedScenes')
    lines = text.splitlines(keepends=True)
    pieces = []
    hashes = {}
    for name in names:
        starts = [i for i, line in enumerate(lines) if line.startswith('        ')
                  and ('private static ' in line or 'public static ' in line)
                  and (' ' + name + '(') in line]
        if len(starts) != 1:
            raise ValueError('scene_native_method_ambiguous')
        start = starts[0]
        end = next(i for i in range(start + 1, len(lines)) if lines[i].rstrip() == '        }')
        part = ''.join(lines[start:end + 1])
        pieces.append(part)
        hashes[name] = hashlib.sha256(part.encode('utf-8')).hexdigest()
    if len(hashes) != len(names):
        raise ValueError('scene_native_methods_missing')
    prefix = text[:text.index('        private static float[] ParseFloatArray')]
    # Fail closed if a disallowed route reaches any omitted implementation.
    omitted = '''
        static object Denied() => throw new Exception("omitted native mutation reached");
        static object CreateScene(string a,string b)=>Denied();
        static object CreateSceneFromTemplate(string a,string b,string c)=>Denied();
        static object LoadScene(string a)=>Denied();
        static object LoadScene(int a)=>Denied();
        static object LoadSceneAdditive(string a)=>Denied();
        static object SaveScene(string a,string b)=>Denied();
        static object GetSceneHierarchyPaged(SceneCommand c)=>Denied();
        static object CaptureScreenshot(SceneCommand c)=>Denied();
        static object FrameSceneView(SceneCommand c)=>Denied();
        static object CloseScene(SceneCommand c)=>Denied();
        static object SetActiveScene(SceneCommand c)=>Denied();
        static object MoveToScene(SceneCommand c)=>Denied();
        static object ValidateScene(bool b)=>Denied();
        static bool IsProjectRooted(string p)=>throw new Exception("ungranted path reached");
        static string GetProjectRoot()=>throw new Exception("ungranted path reached");
    }
}
'''
    Path(output).write_text(prefix + '\n'.join(pieces) + omitted, encoding='utf-8', newline='\n')
    return {'upstream_sha256': PIN, 'method_hashes': hashes,
            'scope': 'exact native parser/dispatch/read methods; unrelated bodies excluded; Unity API fixtures'}
