"""Patch a digest-pinned public archive; do not execute payload. Python without -O."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

ID='com.yukino.vrchat-agent'
OLD='0.2.0-preview.3'
NEW='0.2.0-preview.4'
TAG='hermes-preview-'+NEW
BASE='https://github.com/YukinoStuki2/VRchat_Agent/releases/'
NAME=f'{ID}-{NEW}.zip'
SOURCE='Editor/ScopedAssets/CandidateScopedAssets.cs'
PROOF='Editor/ScopedAssets/PROVENANCE.json'
GEN='Runtime~/distribution/materialize_assets.py'
STRAY='Runtime~.meta'

def sha(data): return hashlib.sha256(data).hexdigest()
def dump(value): return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
def with_import(data):
    anchor=b'using MCPForUnity.Editor.Helpers;\n'
    runtime=b'using MCPForUnity.Runtime.Helpers;\n'
    assert data.count(anchor)==1 and runtime not in data
    return data.replace(anchor,anchor+runtime)

def build(previous, output):
    assert __debug__ and sha(previous.read_bytes())=='0be6452af64b4334d81055c581039e4c13da6470d9fcb929b8fb423085bf6835'
    with ZipFile(previous) as src:
        names=src.namelist(); assert len(names)==len(set(names)) and len(names)==13350
        assert STRAY in names and b'folderAsset: yes' in src.read(STRAY)
        assert 'Runtime~/python/python.exe' in names and 'Runtime~/launcher/editor_owner.py' in names
        source=src.read(SOURCE); new_source=with_import(source); proof=json.loads(src.read(PROOF))
        assert proof['source_sha256']==sha(source) and proof['registered_tool'] is False
        proof['source_sha256']=sha(new_source)
        manifest=json.loads(src.read('package.json'))
        assert (manifest['name'],manifest['version'])==(ID,OLD) and manifest['vpmDependencies']=={'com.coplaydev.unity-mcp':'=10.2.0'}
        manifest.update(version=NEW,url=BASE+'download/'+TAG+'/'+NAME,documentationUrl=BASE+'tag/'+TAG)
        notes=Path(__file__).with_name('release-notes.md').read_bytes()
        changes={SOURCE:new_source, GEN:with_import(src.read(GEN)), PROOF:dump(proof), 'package.json':dump(manifest), 'README.md':notes+b'\n---\n\n'+src.read('README.md'), 'CANDIDATE_STATUS.md':src.read('CANDIDATE_STATUS.md')+b'\n'+notes}
        output.mkdir(exist_ok=False); dest=output/NAME
        with ZipFile(dest,'x') as z:
            for info in src.infolist():
                n=info.filename
                if n!=STRAY: z.writestr(copy.copy(info),changes[n] if n in changes else src.read(n))
        with ZipFile(dest) as z:
            assert z.testzip() is None and z.namelist()==[n for n in names if n!=STRAY]
            assert {n for n in z.namelist() if src.read(n)!=z.read(n)}==set(changes)
            assert all(z.read(n)==data for n,data in changes.items())
            assert json.loads(z.read(PROOF))['source_sha256']==sha(z.read(SOURCE))
    (output/'vpm-entry.json').write_bytes(dump(dict(manifest,zipSHA256=sha(dest.read_bytes()))))
    print('verified package: six changed members, one removed; all other member bytes retained')

if __name__=='__main__': build(Path(sys.argv[1]),Path(sys.argv[2]))
