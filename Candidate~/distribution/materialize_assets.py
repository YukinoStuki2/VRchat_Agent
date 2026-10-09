"""Additive asset metadata source: native reader preserved, pagination before load.
Not an authorization boundary or registered tool. Candidate gate/UI integration
must separately approve callbacks before this helper can be reached over MCP.
"""
from pathlib import Path
import hashlib
import json
import re
import uuid
from distribution.materialize_reflection import method, ASM_GUID, COMMIT

SOURCE='Editor/Tools/ManageAsset.cs'
PIN='2b2dd181e92f38522938468dcf3b2682fa4ea40caa166c8c2dbeb00d7c86799e'
TYPE='CandidateScopedAssets'


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('native_asset_anchor_drift')
    return text.replace(old,new)


def materialize(upstream,destination):
    upstream,destination=Path(upstream),Path(destination)
    if destination.exists() or destination.is_symlink():raise FileExistsError('additive_destination_must_be_new')
    raw=(upstream/SOURCE).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError('native_asset_input_drift')
    meta=(upstream/'Editor/MCPForUnity.Editor.asmdef.meta').read_text(encoding='utf-8')
    asm=json.loads((upstream/'Editor/MCPForUnity.Editor.asmdef').read_bytes())
    if re.findall(r'^guid: ([0-9a-f]{32})$',meta,re.M)!=[ASM_GUID] or asm.get('name')!='MCPForUnity.Editor':
        raise ValueError('pinned_editor_assembly_required')
    original=raw.decode('utf-8')
    names=('SearchAssets','GetAssetInfo','AssetExists','GetAssetData')
    pieces={n:method(original,n) for n in names}
    search=pieces['SearchAssets']
    search=replace_once(search,'List<object> results = new List<object>();','List<string> paths = new List<string>();')
    search=replace_once(search,'results.Add(GetAssetData(assetPath, generatePreview));','paths.Add(assetPath);')
    search=replace_once(search,'var pagedResults = results.Skip(startIndex).Take(pageSize).ToList();',
        'var pagedResults = paths.Skip(startIndex).Take(pageSize).Select(path => GetAssetData(path, generatePreview)).ToList();')
    search=replace_once(search,'''                    McpLog.Warn(
                        $"Search path '{folderScope[0]}' is not a valid folder. Searching entire project."
                    );
                    folderScope = null; // Search everywhere if path isn't a folder''',
        '                    return new ErrorResponse("asset_scope_invalid");')
    search=replace_once(search,'List<string> paths = new List<string>();','if (guids == null || guids.Length > 4096) return new ErrorResponse("asset_match_budget");\n                List<string> paths = new List<string>();')
    search=replace_once(search,'SearchAssets(JObject @params)','SearchAssets(JObject @params, Func<bool> authorized)')
    search=replace_once(search,'var pagedResults = paths.Skip(startIndex).Take(pageSize).Select(path => GetAssetData(path, generatePreview)).ToList();','''var pagedResults = new List<object>();
                foreach (string selected in paths.Skip(startIndex).Take(pageSize))
                {
                    if (!authorized()) return new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");
                    string expectedGuid = resolvedGuids[selected];
                    if (AssetDatabase.GUIDToAssetPath(expectedGuid) != selected || AssetDatabase.AssetPathToGUID(selected) != expectedGuid)
                        return new ErrorResponse("asset_identity_changed; effects_may_have_occurred=true");
                    var row = GetAssetData(selected, false);
                    if (AssetDatabase.GUIDToAssetPath(expectedGuid) != selected || AssetDatabase.AssetPathToGUID(selected) != expectedGuid)
                        return new ErrorResponse("asset_identity_changed; effects_may_have_occurred=true");
                    if (!authorized()) return new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");
                    pagedResults.Add(row);
                }
                if (!authorized()) return new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");''')
    search=replace_once(search,'int totalFound = 0;', 'int totalFound = 0;\n                var seenPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);\n                var resolvedGuids = new Dictionary<string,string>(StringComparer.Ordinal);')
    search=replace_once(search,'''                    if (string.IsNullOrEmpty(assetPath))
                        continue;''','''                    if (!PathAllowed(assetPath) || !assetPath.StartsWith(pathScope + "/", StringComparison.Ordinal) || !seenPaths.Add(assetPath))
                        return new ErrorResponse("asset_resolution_changed");
                    resolvedGuids.Add(assetPath,guid);''')
    search=replace_once(search,'catch (Exception e)','catch (Exception)')
    search=replace_once(search,'return new ErrorResponse($"Error searching assets: {e.Message}");',
        'return new ErrorResponse("asset_read_failed; effects_may_have_occurred=true");')
    pieces['SearchAssets']=search
    prefix='''// Derived from pinned Coplay ManageAsset. See PROVENANCE.json and LICENSE.md.
// Additive helper only: no registration, no startup hooks, no permission grant.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;
using MCPForUnity.Editor.Helpers;
namespace MCPForUnity.Editor.Tools
{
    public static class CandidateScopedAssets
    {
'''
    suffix='''
        static bool PathAllowed(string path) => path != null && path.Length <= 512 &&
            path.StartsWith("Assets/", StringComparison.Ordinal) && !path.Any(char.IsControl) &&
            path.IndexOfAny(new[] { (char)92, ':', '*', '?', '"', '<', '>', '|', '%' }) < 0 &&
            path.Split('/').All(p => p.Length > 0 && p != "." && p != ".." && p.Trim() == p && !p.EndsWith(".", StringComparison.Ordinal));
        static bool Integer(JToken value, int max) => value != null && value.Type == JTokenType.Integer &&
            (decimal)value >= 1 && (decimal)value <= max;
        public static object Query(JObject args, Func<bool> authorized = null)
        {
            if (authorized == null || !authorized()) return new ErrorResponse("asset_callbacks_not_authorized");
            string[] keys = { "path", "pageNumber", "pageSize", "generatePreview", "searchPattern", "filterType", "filterDateAfter" };
            if (args == null || args.Properties().Any(p => !keys.Contains(p.Name)) ||
                args["path"]?.Type != JTokenType.String || !PathAllowed((string)args["path"]) ||
                !Integer(args["pageNumber"], 1000000) || !Integer(args["pageSize"], 50) ||
                args["generatePreview"]?.Type != JTokenType.Boolean || (bool)args["generatePreview"] ||
                new[] { "searchPattern", "filterType", "filterDateAfter" }.Any(k => args[k] != null &&
                    (args[k].Type != JTokenType.String || ((string)args[k]).Length > 128 || ((string)args[k]).Any(char.IsControl))))
                return new ErrorResponse("asset_params_invalid");
            string date = (string)args["filterDateAfter"];
            if (!string.IsNullOrEmpty(date) && !DateTime.TryParse(date, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out _))
                return new ErrorResponse("asset_date_invalid");
            return SearchAssets(args, authorized);
        }
        public static object Info(string path, Func<bool> authorized = null)
        {
            if (authorized == null || !authorized()) return new ErrorResponse("asset_callbacks_not_authorized");
            if (!PathAllowed(path)) return new ErrorResponse("asset_path_invalid");
            string expectedGuid = AssetDatabase.AssetPathToGUID(path);
            if (string.IsNullOrEmpty(expectedGuid) || AssetDatabase.GUIDToAssetPath(expectedGuid) != path)
                return new ErrorResponse("asset_identity_unavailable");
            var result = GetAssetInfo(path, false);
            if (AssetDatabase.GUIDToAssetPath(expectedGuid) != path || AssetDatabase.AssetPathToGUID(path) != expectedGuid)
                return new ErrorResponse("asset_identity_changed; effects_may_have_occurred=true");
            if (!(result is SuccessResponse)) return new ErrorResponse("asset_read_failed; effects_may_have_occurred=true");
            return authorized() ? result : new ErrorResponse("asset_authorization_revoked; effects_may_have_occurred=true");
        }
    }
}
'''
    text=prefix+'\n'.join(pieces.values())+suffix
    for name in ('GetAssetInfo','AssetExists','GetAssetData'):
        if method(text,name)!=method(original,name):raise ValueError('native_asset_reader_changed')
    files={TYPE+'.cs':text.encode('utf-8'),
        'CandidateAssets.asmref':(json.dumps({'reference':'GUID:'+ASM_GUID},indent=2)+'\n').encode(),
        'LICENSE.md':(upstream.parent/'LICENSE').read_bytes()}
    record={'upstream_commit':COMMIT,'upstream_path':SOURCE,'upstream_sha256':PIN,'additive_type':TYPE,
        'source_sha256':hashlib.sha256(files[TYPE+'.cs']).hexdigest(),
        'original_method_hashes':{n:hashlib.sha256(method(original,n).encode()).hexdigest() for n in names},
        'assembly_reference_guid':ASM_GUID,'installed_upstream_files_modified':False,
        'native_parser_and_mutation_handlers_included':False,'unity_import_verified':False,'registered_tool':False}
    files['PROVENANCE.json']=(json.dumps(record,indent=2)+'\n').encode()
    for name in tuple(files):
        guid=uuid.uuid5(uuid.NAMESPACE_URL,'https://github.com/YukinoStuki2/VRchat_Agent/assets/'+name)
        files[name+'.meta']=('fileFormatVersion: 2\nguid: '+guid.hex+'\n').encode()
    destination.mkdir(parents=True)
    for name,data in files.items():(destination/name).write_bytes(data)
    return record
