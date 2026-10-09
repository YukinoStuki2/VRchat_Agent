"""Generate an additive, fixed-type native metadata reader; never edit the host.

Original native read/formatting methods remain verbatim. Only lookup and
extension-discovery paths are restricted. Engine types are explicit compile-time
references: no user/plugin types, assembly scans or caller-selected loaders.
Real Unity/Mono acceptance is separate from this source transformation.
"""
from pathlib import Path
import hashlib
import json
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'Editor/Tools/UnityReflect.cs'
TYPE = 'CandidateScopedUnityReflect'
PIN = 'b42f5b8de353eec2e6ce26bbfa72a4e235ecedcf7fabffbda548244f10f838ef'
COMMIT = '30d22075093d1d35dfb0091c1c7550e9ad948577'
ASM_GUID = '98f702da6ca044be59a864a9419c4eab'
TYPES = ('Object', 'Component', 'GameObject', 'Transform', 'Animator',
         'RuntimeAnimatorController', 'AnimationClip', 'Material', 'Shader',
         'SkinnedMeshRenderer', 'Vector3', 'Quaternion', 'Color')


def method(text, name):
    matches = list(re.finditer(r'^        private static [^\n]+\b' + re.escape(name)
                              + r'\([^\n]*\)\n        \{\n.*?^        \}', text, re.M | re.S))
    if len(matches) != 1:
        raise ValueError('native_method_anchor_drift:' + name)
    return matches[0].group()


def materialize(upstream, destination):
    upstream, destination = Path(upstream), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('additive_destination_must_be_new')
    original = (upstream / SOURCE).read_bytes()
    if hashlib.sha256(original).hexdigest() != PIN:
        raise ValueError('native_reflection_input_drift')
    meta = (upstream / 'Editor/MCPForUnity.Editor.asmdef.meta').read_text(encoding='utf-8')
    asm = json.loads((upstream / 'Editor/MCPForUnity.Editor.asmdef').read_text(encoding='utf-8'))
    if re.findall(r'^guid: ([0-9a-f]{32})$', meta, re.M) != [ASM_GUID] or asm.get('name') != 'MCPForUnity.Editor':
        raise ValueError('pinned_editor_assembly_required')
    text = original.decode('utf-8')
    text = text.replace('using MCPForUnity.Runtime.Helpers;\n', '')
    text = text.replace('[McpForUnityTool("unity_reflect", AutoRegister = false, Group = "docs")]\n    ', '')
    text = text.replace('public static class UnityReflect', 'public static class ' + TYPE)
    text = text.replace('        [InitializeOnLoadMethod]\n' + method(text, 'OnLoad'), '')
    text = text.replace(method(text, 'InvalidateCache'), '')
    text = text.replace('        private static readonly ConcurrentDictionary<Type, string[]> ExtensionMethodCache = new();\n', '')
    text = re.sub(r'        private static readonly string\[\] NamespacePrefixes =\n        \{.*?^        \};\n', '', text, flags=re.M | re.S)
    replacement = '''        private static Dictionary<string, Type[]> GetAssemblyTypeCache()
        {
            lock (CacheLock)
            {
                if (_assemblyTypeCache == null)
                {
                    // Only these trusted engine identities; no assembly enumeration.
                    var types = new Type[] { TYPES };
                    _assemblyTypeCache = types.GroupBy(t => t.Assembly.FullName)
                        .ToDictionary(g => g.Key, g => g.ToArray());
                }
                return _assemblyTypeCache;
            }
        }'''.replace('TYPES', ', '.join('typeof(UnityEngine.' + t + ')' for t in TYPES))
    text = text.replace(method(text, 'GetAssemblyTypeCache'), replacement)
    text = text.replace(method(text, 'ResolveType'), '''        private static Type ResolveType(string className)
        {
            return GetAssemblyTypeCache().Values.SelectMany(types => types)
                .FirstOrDefault(t => t.FullName == className || t.Name == className);
        }''')
    for name, result_type in [('FindExtensionMethods', 'string'), ('FindExtensionMethodInfos', 'MethodInfo')]:
        old = method(text, name)
        signature = old.split('\n', 1)[0]
        text = text.replace(old, signature + '\n        {\n            // Extension discovery is deliberately unsupported, not globally empty.\n            return Array.Empty<' + result_type + '>();\n        }')
    for name in ('GetTypeInfo', 'GetMemberInfo', 'SearchTypes', 'FormatTypeName', 'FormatMethodDetail', 'FormatMethodSignature', 'GetObsoleteMembers'):
        if method(original.decode(), name) != method(text, name):
            raise ValueError('native_reader_body_changed:' + name)
    files = {TYPE + '.cs': text.encode('utf-8'),
             'CandidateReflection.asmref': (json.dumps({'reference': 'GUID:' + ASM_GUID}, indent=2) + '\n').encode(),
             'LICENSE.md': (upstream.parent / 'LICENSE').read_bytes()}
    record = {'upstream_commit': COMMIT, 'upstream_path': SOURCE, 'upstream_sha256': PIN,
              'additive_type': TYPE, 'source_sha256': hashlib.sha256(files[TYPE + '.cs']).hexdigest(),
              'allowed_types': ['UnityEngine.' + t for t in TYPES], 'extension_discovery': False,
              'assembly_reference_guid': ASM_GUID, 'installed_upstream_files_modified': False,
              'unity_import_verified': False}
    files['PROVENANCE.json'] = (json.dumps(record, indent=2) + '\n').encode()
    for name in tuple(files):
        guid = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/YukinoStuki2/VRchat_Agent/reflection/' + name)
        files[name + '.meta'] = ('fileFormatVersion: 2\nguid: ' + guid.hex + '\n').encode()
    destination.mkdir(parents=True)
    for name, data in files.items():
        (destination / name).write_bytes(data)
