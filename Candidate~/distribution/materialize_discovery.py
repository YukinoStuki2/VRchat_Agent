"""Additive native non-cache provider and collector; no installed source changes."""
from pathlib import Path
import hashlib,json,re,uuid
PINS = {'UnityEditor.TestRunner/TestRunner/Utils/TestListProvider.cs': '64c1413ba11a1b2b34d65f9cd7ad8b90dfb872a51255b7fe04a2e63304666916', 'UnityEditor.TestRunner/UnityEditor.TestRunner.asmdef': 'bfd5a30e7779218ec0a51022c81a1a9fc1c5f1d94c205057c864a0d3e201ea36', 'UnityEditor.TestRunner/UnityEditor.TestRunner.asmdef.meta': 'db240d872a959268149b59f14d032e0aac8d20f6018fc2a111e87eb9a6fdc1f4', 'LICENSE.md': '075062af29ac0be77c0f8d46adc3f408f449100be142372bd4a5a03c065367aa'}
COPLAY_SHA = 'b5f25bffbcee394d746f4a67b7cfaba1bf3e24279f581d79fec7c20098d6ee23'
ASM_GUID = '0acc523941302664db1f4e527237feb3'
def materialize(framework,coplay,destination):
    framework,coplay,destination=Path(framework),Path(coplay),Path(destination)
    if destination.exists() or destination.is_symlink():raise FileExistsError('additive_destination_must_be_new')
    originals={n:(framework/n).read_bytes() for n in PINS}
    if any(hashlib.sha256(originals[n]).hexdigest()!=h for n,h in PINS.items()):raise ValueError('test_framework_source_drift')
    native=(coplay/'Editor/Services/TestRunnerService.cs').read_bytes()
    if hashlib.sha256(native).hexdigest()!=COPLAY_SHA:raise ValueError('coplay_test_source_drift')
    if json.loads(originals['UnityEditor.TestRunner/UnityEditor.TestRunner.asmdef'])['name']!='UnityEditor.TestRunner' or re.findall(r'^guid: ([a-f0-9]{32})\r?$',originals['UnityEditor.TestRunner/UnityEditor.TestRunner.asmdef.meta'].decode(),re.M)!=[ASM_GUID]:raise ValueError('test_assembly_identity')
    provider=originals['UnityEditor.TestRunner/TestRunner/Utils/TestListProvider.cs'].decode().replace('TestListProvider','CandidateLiveTestListProvider').replace('ICandidateLiveTestListProvider','ITestListProvider')
    provider=provider.replace('\r\n','\n')
    provider=provider.replace('var assembliesTask = m_AssemblyProvider.GetAssembliesGroupedByTypeAsync(platform);','using (var assembliesTask = m_AssemblyProvider.GetAssembliesGroupedByTypeAsync(platform)) {')
    provider=provider.replace('var test =  m_AssemblyBuilder.BuildAsync(assemblies.Select(a => a.Item1).ToArray(), assemblies.Select(a => a.Item2).ToArray(), settings);','using (var test = m_AssemblyBuilder.BuildAsync(assemblies.Select(a => a.Item1).ToArray(), assemblies.Select(a => a.Item2).ToArray(), settings)) {')
    provider=provider.replace('yield return test.Current;','yield return test.Current;\n            } }')
    matches=re.findall(r'^        private static void CollectFromNode\([^)]*\)\n        \{\n.*?^        \}',native.decode(),re.M|re.S)
    if len(matches)!=1:raise ValueError('native_collector_anchor_drift')
    collector=matches[0]
    collected=collector.replace('private static void','private void').replace('ITestAdaptor','ITest').replace('TestMode mode','string mode').replace('node.HasChildren','node.Tests.Count > 0').replace('node.Children','node.Tests')
    collected=collected.replace('if (!hasChildren)','if (!hasChildren && !node.IsSuite)')
    collected=collected.replace('if (!string.IsNullOrEmpty(fullName) && seen.Add(key))','if (string.IsNullOrEmpty(fullName) || !seen.Add(key))throw new InvalidOperationException("discovery_incomplete");\n                else')
    collected=collected.replace('if (node == null)\n            {\n                return;\n            }','if (node == null)throw new InvalidOperationException("discovery_incomplete");')
    collected=collected.replace('List<string> path)','List<string> path, int depth=0)').replace('CollectFromNode(child, mode, output, seen, path);','CollectFromNode(child, mode, output, seen, path, depth+1);')
    collected=collected.replace('bool hasName =','if(!Allowed() || depth>64 || ++visited>4096)throw new InvalidOperationException("discovery_depth_budget");\n            bool hasName =')
    collected='using System;\nusing System.Collections.Generic;\nusing NUnit.Framework.Interfaces;\nnamespace UnityEditor.TestTools.TestRunner { public sealed partial class CandidateDiscoveryJob {\n'+collected+'\n}}\n'
    files={'CandidateLiveTestListProvider.cs':provider.encode(),'CandidateDiscoveryCollector.cs':collected.encode(),'CandidateTests.asmref':(json.dumps({'reference':'GUID:'+ASM_GUID},indent=2)+'\n').encode(),'LICENSE-Unity.md':originals['LICENSE.md'],'LICENSE-Coplay.md':(coplay.parent/'LICENSE').read_bytes()}
    proof={'schema':1,'unity_test_framework':'1.1.31','framework_inputs':PINS,'coplay_test_runner_sha256':COPLAY_SHA,'collector_before_sha256':hashlib.sha256(collector.encode()).hexdigest(),'outputs':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()},'installed_upstream_files_modified':False,'registered_tool':False,'not_a_callback_sandbox':True}
    files['PROVENANCE.json']=(json.dumps(proof,indent=2)+'\n').encode()
    destination.mkdir(parents=True)
    for name,data in files.items():
        (destination/name).write_bytes(data)
        guid=uuid.uuid5(uuid.NAMESPACE_URL,'https://github.com/YukinoStuki2/VRchat_Agent/candidate/ScopedTests/'+name).hex
        (destination/(name+'.meta')).write_text('fileFormatVersion: 2\nguid: '+guid+'\n',encoding='utf-8',newline='\n')
    return proof
