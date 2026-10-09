"""Test-only pinned original methods; omitted mutations THROW; not real Unity."""
import hashlib
from pathlib import Path
PINS = {'Tools/ManageScript.cs': '792403cf258942342a4ed0be95c01b9eb38a0e4ae8536c8a313f5596db4b5c11', 'Helpers/AssetPathUtility.cs': 'abe8173a4e88286ee1da7dbef92e8eace02880a8fb8d3c12dd8d48c7407a3f94', 'Helpers/ToolParams.cs': 'f708345c2913672011a7050ddceb96141a22f0880c9dfea65ebfb5b50c792abc', 'Helpers/StringCaseUtility.cs': '5758c84d56fd4a3420aede775ddd1ca7cc8e0854476bedf65a1a9bca437cd411', 'Helpers/ParamCoercion.cs': '69b425c49152a31d68e80d0a6498c78c406989242214a8f9b760b6936b17670b', 'Helpers/Response.cs': 'a1769de32b9c6824841c070f0590ae7e9f44485d2a6c44a0bce3ed3f68e17391', 'Tools/ManageShader.cs': '6f8a845e8f8d8f92648c35c7e38ea4ab5952144dd691b4142312e04732059124'}

PINS['Tools/Animation/ClipCreate.cs']='acda2fcc48fc90ca3fb2c4cca62957486f7fd8105bd7cdd306c014ae5adef37b'

def assemble(root, output):
    root=Path(root);hashes={}
    for name,pin in PINS.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=pin:
            raise ValueError('source_native_pin_drift')
    def methods(path,names):
        lines=(root/path).read_text(encoding='utf-8').splitlines(keepends=True);out=[]
        for name in names:
            starts=[i for i,line in enumerate(lines) if line.startswith('        ') and
                    ('private static ' in line or 'public static ' in line) and (' '+name+'(') in line]
            if len(starts)!=1:raise ValueError('source_native_method_ambiguous')
            start=starts[0];end=next(i for i in range(start+1,len(lines)) if lines[i].rstrip()=='        }')
            part=''.join(lines[start:end+1]);out.append(part);hashes[path+':'+name]=hashlib.sha256(part.encode()).hexdigest()
        return '\n'.join(out)
    text='using System; using System.Collections.Generic; using System.IO; using System.Linq; using System.Text; using System.Text.RegularExpressions; using System.Security.Cryptography; using Newtonsoft.Json.Linq; using UnityEngine; using UnityEditor; using MCPForUnity.Editor.Helpers;\nnamespace MCPForUnity.Editor.Tools { public static class ManageScript {\n'
    text+=methods('Tools/ManageScript.cs',('TryResolveUnderAssets','HandleCommand','ReadScript','ComputeSha256','EncodeBase64','DecodeBase64'))
    text+='\n        static object CreateScript(string a,string b,string c,string d,string e,string f)=>throw new Exception("omitted mutation");\n        static object UpdateScript(string a,string b,string c,string d)=>throw new Exception("omitted mutation");\n        static object DeleteScript(string a,string b)=>throw new Exception("omitted mutation");\n        static object ApplyTextEdits(string a,string b,string c,JArray d,string e,string f,string g)=>throw new Exception("omitted mutation");\n        static object EditScript(string a,string b,string c,JArray d,JObject e)=>throw new Exception("omitted mutation");\n        enum ValidationLevel {Basic,Standard,Strict,Comprehensive}\n        static bool ValidateScriptSyntax(string a,ValidationLevel b,out string[] c)=>throw new Exception("omitted validation");\n    } }\n'
    text+='namespace MCPForUnity.Editor.Tools { public static class ManageShader {\n'+methods('Tools/ManageShader.cs',('HandleCommand','ReadShader','EncodeBase64','DecodeBase64'))
    text+='\n        static object CreateShader(string a,string b,string c,string d)=>throw new Exception("omitted mutation");\n        static object UpdateShader(string a,string b,string c,string d)=>throw new Exception("omitted mutation");\n        static object DeleteShader(string a,string b)=>throw new Exception("omitted mutation");\n    } }\n'
    text+='namespace MCPForUnity.Editor.Helpers { public static class AssetPathUtility {\n'+methods('Helpers/AssetPathUtility.cs',('NormalizeSeparators','SanitizeAssetPath'))+'\n} }'
    text+='namespace MCPForUnity.Editor.Tools.Animation {public static class ClipCreate {\n'+methods('Tools/Animation/ClipCreate.cs',('GetInfo',))+'\n} }'
    Path(output).write_text(text,encoding='utf-8',newline='\n')
    return {'pins':PINS,'method_hashes':hashes,'scope':'Verbatim native parser/dispatch/read/sha; other implementations THROW; Unity API doubles'}
