"""Rebuild the CS7036 preview from the authenticated-by-digest prior public ZIP. No payload execution."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
ID = 'com.yukino.vrchat-agent'
OLD, NEW = '0.2.0-preview.2', '0.2.0-preview.3'
SOURCE = 'Editor/ScopedTests/CandidateDiscoveryJob.cs'
TAG = 'hermes-preview-'+NEW
FEED = 'https://raw.githubusercontent.com/YukinoStuki2/VRchat_Agent/vpm/index.json'
FILE = ID+'-'+NEW+'.zip'
URL = 'https://github.com/YukinoStuki2/VRchat_Agent/releases/download/'+TAG+'/'+FILE

def sha(b): return hashlib.sha256(b).hexdigest()
def js(obj): return (json.dumps(obj, ensure_ascii=False, indent=2)+'\n').encode()

def build(old, out):
    assert sha(old.read_bytes()) == '8b2a8c189f2a27516d3c15a009bb752a21c691aa4c0ca867f6615ebd563ff425'
    patch=(ROOT/'CandidateDiscoveryJob.cs').read_bytes()
    assert sha(patch)=='555b86489eca283fdc4c67d901f96ff3fe63b1def88ca893d8f4353f766d8f85'
    out.mkdir(exist_ok=False)
    with zipfile.ZipFile(old) as src:
        assert src.testzip() is None and len(src.namelist())==len(set(src.namelist()))==13350
        assert sha(src.read(SOURCE))=='1fffd0c61651048b0b650895a37e202938397b0c477a9cf6850bd702bf316c9b'
        manifest=json.loads(src.read('package.json'))
        assert (manifest['name'],manifest['version'])==(ID,OLD)
        manifest.update(version=NEW,url=URL,documentationUrl='https://github.com/YukinoStuki2/VRchat_Agent/releases/tag/'+TAG)
        notes=(ROOT/'release-notes.md').read_bytes()
        changes={SOURCE:patch,'package.json':js(manifest),'README.md': notes+b'\n---\n\n'+src.read('README.md'), 'CANDIDATE_STATUS.md': src.read('CANDIDATE_STATUS.md')+b'\n'+notes}
        dest=out/FILE
        with zipfile.ZipFile(dest,'x') as z:
            for info in src.infolist():
                data=changes[info.filename] if info.filename in changes else src.read(info.filename)
                z.writestr(copy.copy(info), data)
        with zipfile.ZipFile(dest) as z:
            assert z.testzip() is None and src.namelist()==z.namelist()
            assert {n for n in z.namelist() if sha(z.read(n))!=sha(src.read(n))}==set(changes)
            assert all(z.read(n)==b for n,b in changes.items())
    (out/'vpm-entry.json').write_bytes(js(dict(manifest,zipSHA256=sha(dest.read_bytes()))))
    print('verified 13350 members; exactly four changed; '+FILE)

if __name__=='__main__': build(Path(sys.argv[1]),Path(sys.argv[2]))
