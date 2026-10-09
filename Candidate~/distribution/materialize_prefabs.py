"""Pinned native Prefab readers, additive and unregistered; no host edits.
The caller owns trusted review and task approval. This reader is not a sandbox.
"""
from pathlib import Path
import hashlib
import json
import re
import uuid

from distribution.materialize_reflection import method, ASM_GUID, COMMIT

PINS = {
    'Editor/Tools/Prefabs/ManagePrefabs.cs': '24c4a1c342c96169cd2c8fcc67c776c0737d5cdd542efdf48d343dba26dba77a',
    'Editor/Helpers/PrefabUtilityHelper.cs': '4435daae74b7efe335c6db4189b35ac7d10f308dd79cfe3700a72b4f3b6bf95b',
}
READERS = ('GetInfo', 'GetHierarchy', 'BuildHierarchyItems', 'BuildHierarchyItemsRecursive')
HELPERS = ('GetPrefabGUID', 'GetVariantInfo', 'GetComponentTypeNames', 'CountChildrenRecursive',
           'GetNestedPrefabPath', 'GetPrefabNestingDepth', 'GetParentPrefabPath')

PREAMBLE = '''using System;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Runtime.Helpers;
namespace MCPForUnity.Editor.Tools.Prefabs
{
    // No registry or initialization hook. Exact per-call instance; no global state.
    public sealed class CandidateScopedPrefabs
    {
        readonly Func<bool> authorized;
        bool attempted, loadStarted, unloadStarted, unloaded;
        GameObject owned;
        string exactPath,expectedGuid;
        readonly HashSet<Transform> visited=new HashSet<Transform>();
        void Visit(Transform value,int depth)
        {
            Check();
            if(value==null || depth>64 || !visited.Add(value) || visited.Count>1000 || value.childCount>1000)
                throw new InvalidOperationException("prefab_traversal_budget");
        }
        CandidateScopedPrefabs(Func<bool> authorized) { this.authorized=authorized; }
        void Check()
        {
            if(authorized==null || !authorized())throw new InvalidOperationException("prefab_authorization_changed");
            if(exactPath!=null && (expectedGuid==null || !System.Text.RegularExpressions.Regex.IsMatch(expectedGuid,@"\\A[a-f0-9]{32}\\z") ||
                AssetDatabase.AssetPathToGUID(exactPath)!=expectedGuid || AssetDatabase.GUIDToAssetPath(expectedGuid)!=exactPath))
                throw new InvalidOperationException("prefab_identity_changed");
        }
        GameObject LoadContents(string path)
        {
            Check();attempted=true;loadStarted=true;
            owned=PrefabUtility.LoadPrefabContents(path);
            // Do not throw between obtaining the handle and native try/finally.
            return owned;
        }
        void UnloadContents(GameObject value)
        {
            // Revocation prevents new work, not cleanup of this exact owned handle.
            if(!ReferenceEquals(value,owned))throw new InvalidOperationException("prefab_owner_mismatch");
            unloadStarted=true;PrefabUtility.UnloadPrefabContents(value);unloaded=true;
        }
        GameObject LoadAsset(string path) { Check();attempted=true;var value=AssetDatabase.LoadAssetAtPath<GameObject>(path);Check();return value; }
        static bool PathAllowed(string path) => path!=null && path.Length<=490 && path.StartsWith("Assets/",StringComparison.Ordinal) && path.EndsWith(".prefab",StringComparison.Ordinal) &&
            !path.Any(ch=>char.IsControl(ch) || "\\\\:%<>\\\"|?*".Contains(ch)) &&
            path.Split('/').All(p=>p.Length>0 && p!="." && p!=".." && p==p.Trim() && !p.EndsWith(".",StringComparison.Ordinal) &&
                !System.Text.RegularExpressions.Regex.IsMatch(p.Split('.')[0],@"\\A(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\\z"));
        public static JObject Read(JObject args,Func<bool> authorized) => new CandidateScopedPrefabs(authorized).Run(args);
        JObject Run(JObject args)
        {
            string action=null;
            try
            {
                if(args==null || args.Count!=2 || args["action"]?.Type!=JTokenType.String || args["prefabPath"]?.Type!=JTokenType.String || !PathAllowed((string)args["prefabPath"]))throw new InvalidOperationException();
                action=(string)args["action"];
                if(action!="get_info" && action!="get_hierarchy")throw new InvalidOperationException();
                Check();exactPath=(string)args["prefabPath"];expectedGuid=AssetDatabase.AssetPathToGUID(exactPath);Check();
                var result=JObject.FromObject(action=="get_info" ? GetInfo(args) : GetHierarchy(args));
                Check();
                if(result["success"]?.Type!=JTokenType.Boolean || !(bool)result["success"] || !(result["data"] is JObject data))throw new InvalidOperationException();
                data["candidate_effects"]=Receipt(action);
                if(System.Text.Encoding.UTF8.GetByteCount(result.ToString(Newtonsoft.Json.Formatting.None))>262144)throw new InvalidOperationException("prefab_response_budget");
                return result;
            }
            catch
            {
                // Neither callback changes nor a failed native load are rolled back.
                return new JObject { ["success"]=false,["error"]="prefab_read_unconfirmed",["data"]=new JObject {
                    ["read_only"]=false,["effects_may_have_occurred"]=attempted,["candidate_effects"]=Receipt(action) } };
            }
        }
        JObject Receipt(string action) => new JObject {
            ["kind"]=action=="get_hierarchy" ? "prefab_contents_callbacks" : "asset_load_callbacks",
            ["version"]=1,["read_only"]=false,["all_mutations_observed"]=false,["callback_effects_path_bounded"]=false,
            ["load_started"]=loadStarted,["unload_started"]=unloadStarted,["cleanup_confirmed"]=!loadStarted || unloaded
        };
'''


def materialize(upstream, destination):
    upstream, destination = Path(upstream), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('additive_destination_must_be_new')
    originals = {p: (upstream / p).read_bytes() for p in PINS}
    if any(hashlib.sha256(originals[p]).hexdigest() != h for p, h in PINS.items()):
        raise ValueError('native_prefab_source_drift')
    meta = (upstream / 'Editor/MCPForUnity.Editor.asmdef.meta').read_text(encoding='utf-8')
    asm = json.loads((upstream / 'Editor/MCPForUnity.Editor.asmdef').read_bytes())
    if re.findall(r'^guid: ([0-9a-f]{32})$', meta, re.M) != [ASM_GUID] or asm.get('name') != 'MCPForUnity.Editor':
        raise ValueError('pinned_editor_assembly_required')
    native = originals['Editor/Tools/Prefabs/ManagePrefabs.cs'].decode('utf-8')
    helpers = originals['Editor/Helpers/PrefabUtilityHelper.cs'].decode('utf-8').replace('public static ', 'private static ')
    pieces = [method(native, name) for name in READERS] + [method(helpers, name) for name in HELPERS]
    method_hashes = {name: hashlib.sha256((piece.replace('private static ', 'public static ', 1) if name in HELPERS else piece).encode()).hexdigest() for name, piece in zip(READERS + HELPERS, pieces)}
    text = '\n'.join(pieces).replace('private static ', 'private ').replace('PrefabUtilityHelper.', '')
    text = text.replace('string sanitizedPath = AssetPathUtility.SanitizeAssetPath(prefabPath);', 'string sanitizedPath = prefabPath;')
    text = text.replace('AssetDatabase.LoadAssetAtPath<GameObject>(sanitizedPath)', 'LoadAsset(sanitizedPath)')
    text = text.replace('PrefabUtility.LoadPrefabContents(sanitizedPath)', 'LoadContents(sanitizedPath)')
    text = text.replace('PrefabUtility.UnloadPrefabContents(prefabContents)', 'UnloadContents(prefabContents)')
    text = text.replace('List<object> items)\n        {\n            if (transform == null) return;',
                        'List<object> items, int depth=0)\n        {\n            Visit(transform,depth);')
    text = text.replace('BuildHierarchyItemsRecursive(child, mainPrefabRoot, mainPrefabPath, path, items);',
                        'BuildHierarchyItemsRecursive(child, mainPrefabRoot, mainPrefabPath, path, items, depth+1);')
    text = text.replace('CountChildrenRecursive(Transform transform)\n        {',
                        'CountChildrenRecursive(Transform transform, int depth=0)\n        {\n            Visit(transform,depth);')
    text = text.replace('CountChildrenRecursive(transform.GetChild(i))', 'CountChildrenRecursive(transform.GetChild(i),depth+1)')
    text = text.replace('var components = obj.GetComponents<Component>();',
                        'Check();var components = obj.GetComponents<Component>();Check();\n                if(components==null || components.Length>256 || components.Any(x=>x==null))throw new InvalidOperationException("prefab_components_incomplete");')
    text = text.replace('return (true, null, null);', 'throw new InvalidOperationException("prefab_parent_unresolved");')
    text = text.replace('var sourcePrefab = PrefabUtility.GetCorrespondingObjectFromSource(gameObject);',
                        'Check();var sourcePrefab = PrefabUtility.GetCorrespondingObjectFromSource(gameObject);Check();\n                if(sourcePrefab==null)throw new InvalidOperationException("prefab_nested_unresolved");')
    text, caught = re.subn(r'            catch \(Exception ex\)\n            \{.*?^            \}',
                          '            catch { throw new InvalidOperationException("prefab_metadata_unconfirmed"); }', text, flags=re.M | re.S)
    if caught != 4:
        raise ValueError('prefab_helper_catch_anchor_drift')
    source = (PREAMBLE + text + '\n    }\n}\n').encode('utf-8')
    proof = {'schema': 1, 'upstream_commit': COMMIT, 'input_hashes': PINS, 'method_hashes_before_adaptation': method_hashes,
             'source_sha256': hashlib.sha256(source).hexdigest(), 'registered_tool': False,
             'installed_upstream_files_modified': False, 'not_a_callback_sandbox': True}
    destination.mkdir(parents=True)
    files = {'CandidateScopedPrefabs.cs': source, 'CandidatePrefabs.asmref': (json.dumps({'reference': 'GUID:' + ASM_GUID}, indent=2)+'\n').encode(),
             'PROVENANCE.json': (json.dumps(proof, indent=2)+'\n').encode(), 'LICENSE.md': (upstream.parent / 'LICENSE').read_bytes()}
    for name, data in files.items():
        (destination / name).write_bytes(data)
        guid = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/YukinoStuki2/VRchat_Agent/candidate/ScopedPrefabs/' + name).hex
        (destination / (name + '.meta')).write_text('fileFormatVersion: 2\nguid: ' + guid + '\n', encoding='utf-8', newline='\n')
    return proof
