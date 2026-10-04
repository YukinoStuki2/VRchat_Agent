"""Test-only exact-method extraction from pinned Coplay ManageScene.

Compiles original parser, dispatch, metadata/hierarchy readers and their helpers. Unrelated method
bodies throw; Unity APIs are fixtures. NOT full-source/Unity compilation proof,
not an installed reader. Refuse any upstream drift before extracting bytes.
"""
import hashlib
from pathlib import Path

PIN = '1fc7de5f27d4213bf3f1173cb9589e6056590c70bcb894c4a86483d789ac8e15'


FIND_PINS = {
    'Helpers/UnityTypeResolver.cs': 'b6c89e35e6eb2120a7a33444497940a4b9980c24d25dabd8388d39db44ffa4e0',
    'Tools/ManagePackages.cs':'314008d7207225eac67ce88ce87557ac771a245a0e00bb6400da899f0bf4b9fc',
    'Resources/MenuItems/GetMenuItems.cs':'8852fa1e2ee6821e485506602e8b5a6097089f20a2d9c348039bf9fa467d82be',
    'Resources/Editor/Selection.cs':'c1fd0a170f00dbeda2fc7ca3649e6589e56f5b14613e88299b4fc516049ae9a8',
    'Resources/Editor/Windows.cs':'3b868b6ad630b5f2d7b1b3b055a5361b83d878d0c0a8777e9ab84172e2e46b4d',
    'Resources/Editor/ActiveTool.cs':'dbcd1909b23c26876f649116f81019a6ad6fb87c845870e1d04bea31eb98bb00',
    'Resources/Editor/GetPrefabStage.cs':'ab28fd6926c8ca1815f3d792a619e66d4c87028abe6dfdc817df2bf0c2facfe3',

    'Resources/Project/ProjectInfo.cs':'98150421e21fa437ef60f9d825b59e61f34f2920cc2d07c3a62a23465f79f5e0',
    'Resources/Project/Tags.cs':'2568cc5bc6dddd2eba9912c545ee3899b002687d872691329a3af7b20b1d6ce2',
    'Resources/Project/Layers.cs':'269850217c0e3b1f23b1658a9c3bf7aeaea043b8b711e043dbafd729d1e823d4',
    'Helpers/RenderPipelineUtility.cs':'f869517a575ecb474860fcfcf82cb647b4eb718394245fcfc79d182a1d4b477c',

    'Tools/Animation/ManageAnimation.cs':'55ee53aa8f6c48f367c8601d2fb66a9e56ca740ed5b69f6bdac52d13d11f3b62',
    'Tools/Animation/AnimatorRead.cs':'4a887975edc5927a0bfb074cdfe4326abbaaf819311d54ee9475e4d55d170bff',
    'Helpers/ObjectResolver.cs':'3b3d50775d4561de23f2fa9de119f2d9cde826da683038269620b4cc2d852f20',

    'Resources/Scene/GameObjectResource.cs':'12b8444f5a48306a2809e1a7be8ee4cd24942d0e4cfea61af45bcf0f6424c96e',
    'Tools/FindGameObjects.cs':'37a62dddc6c504d303eef81a2747b5316fa1c9a8b425d35a653cce92f48ba0ff',
    'Helpers/GameObjectLookup.cs':'c367752fa626a36d508202a5416f30d33e395d9bded606bb1837754f1d3dac69',
    'Helpers/Pagination.cs':'e628e28a82662896dd4ca61d1668e97fd13a793765723953efd6dc483b9c074f'}


def assemble(editor_root, output):
    raw = (Path(editor_root) / 'Tools/ManageScene.cs').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN:
        raise ValueError('scene_native_source_drift')
    find_pins = FIND_PINS
    if any(hashlib.sha256((Path(editor_root)/p).read_bytes()).hexdigest()!=h for p,h in find_pins.items()):
        raise ValueError('find_native_source_drift')
    text = raw.decode('utf-8')
    names = ('ParseFloatArray', 'ToSceneCommand', 'HandleCommand',
             'GetActiveSceneInfo', 'GetBuildSettingsScenes', 'GetLoadedScenes',
             'GetSceneHierarchyPaged', 'ResolveGameObject', 'BuildGameObjectSummary', 'GetGameObjectPath', 'ValidateScene')
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
        static object CaptureScreenshot(SceneCommand c)=>Denied();
        static object FrameSceneView(SceneCommand c)=>Denied();
        static object CloseScene(SceneCommand c)=>Denied();
        static object SetActiveScene(SceneCommand c)=>Denied();
        static object MoveToScene(SceneCommand c)=>Denied();

        static bool IsProjectRooted(string p)=>throw new Exception("ungranted path reached");
        static string GetProjectRoot()=>throw new Exception("ungranted path reached");
    }
}
'''
    pipeline = (Path(editor_root)/'Helpers/RenderPipelineUtility.cs').read_text(encoding='utf-8').splitlines(keepends=True)
    pipeline_pieces=[]
    for marker in ('        internal enum PipelineKind', '        internal static PipelineKind GetActivePipeline()'):
        start=next(i for i,line in enumerate(pipeline) if line.rstrip()==marker)
        end=next(i for i in range(start+1,len(pipeline)) if pipeline[i].rstrip()=='        }')
        part=''.join(pipeline[start:end+1]);pipeline_pieces.append(part)
        hashes[marker.strip()]=hashlib.sha256(part.encode()).hexdigest()
    pipeline_source='\nnamespace MCPForUnity.Editor.Helpers { using UnityEngine.Rendering; internal static class RenderPipelineUtility {\n'+'\n'.join(pipeline_pieces)+'\n} }\n'
    packages = (Path(editor_root)/'Tools/ManagePackages.cs').read_text(encoding='utf-8').splitlines(keepends=True)
    package_pieces=[]
    for name in ('HandleCommand','GetPackageInfo'):
        start=next(i for i,line in enumerate(packages) if (' static object '+name+'(') in line)
        end=next(i for i in range(start+1,len(packages)) if packages[i].rstrip()=='        }')
        part=''.join(packages[start:end+1]);package_pieces.append(part)
        hashes['ManagePackages.'+name]=hashlib.sha256(part.encode()).hexdigest()
    package_source='\nnamespace MCPForUnity.Editor.Tools { using System; using System.Linq; using Newtonsoft.Json.Linq; using MCPForUnity.Editor.Helpers; using PackageInfo=UnityEditor.PackageManager.PackageInfo; public static class ManagePackages {\n'+'\n'.join(package_pieces)
    for name in ('AddPackage','RemovePackage','GetStatus','ListPackages','SearchPackages','AddRegistry','RemoveRegistry','EmbedPackage'):
        package_source+='\nstatic object '+name+'(ToolParams p)=>throw new Exception("ungranted package operation");'
    for name in ('ListRegistries','ResolvePackages','Ping'):
        package_source+='\nstatic object '+name+'()=>throw new Exception("ungranted package operation");'
    package_source+='\n} }\n'
    Path(str(output)+'.packages.cs').write_text(package_source, encoding='utf-8', newline='\n')
    Path(output).write_text(prefix + '\n'.join(pieces) + omitted + pipeline_source, encoding='utf-8', newline='\n')
    return {'upstream_sha256': PIN, 'method_hashes': hashes, 'find_native_sha256': find_pins,
            'scope': 'exact native parser/dispatch/read methods; unrelated bodies excluded; Unity API fixtures'}
