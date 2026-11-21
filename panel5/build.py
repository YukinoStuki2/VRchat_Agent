"""Build an immutable UI-only preview from the verified public predecessor."""
import copy,hashlib,json,sys
from pathlib import Path
from zipfile import ZipFile

P=Path(__file__).resolve().parent; ID='com.yukino.vrchat-agent'; NEW='0.2.0-preview.5'; OLD='0.2.0-preview.4'; TAG='hermes-preview-'+NEW
NAME=ID+'-'+NEW+'.zip'; BASE='https://github.com/YukinoStuki2/VRchat_Agent/releases/'; UI='Editor/CandidateWindow.cs'
def sha(data):return hashlib.sha256(data).hexdigest()
def dump(data):return (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
def build(src,out):
    assert __debug__ and sha(src.read_bytes())=='e28dd3bdfb214d0eba23d1c240a1e145d3e1c4a4cedd5f38a628bd6c9285e470';out.mkdir(exist_ok=False)
    with ZipFile(src) as a:
        names=a.namelist(); assert len(names)==len(set(names))==13349 and sha(a.read(UI))=='731ec05387bf718759600f70c873cc090cefbe5c7c4abc3e31598495e64c558c'
        manifest=json.loads(a.read('package.json'));assert manifest['version']==OLD and manifest['name']==ID and manifest['vpmDependencies']=={'com.coplaydev.unity-mcp':'=10.2.0'}
        manifest.update(version=NEW,url=BASE+'download/'+TAG+'/'+NAME,documentationUrl=BASE+'tag/'+TAG)
        notes=(P/'release-notes.md').read_bytes();changes={UI:(P/'CandidateWindow.cs').read_bytes(),'package.json':dump(manifest),'README.md':notes+b'\n---\n\n'+a.read('README.md'),'CANDIDATE_STATUS.md':a.read('CANDIDATE_STATUS.md')+b'\n'+notes}
        with ZipFile(out/NAME,'x') as z:
            for info in a.infolist():z.writestr(copy.copy(info),changes[info.filename] if info.filename in changes else a.read(info.filename))
        with ZipFile(out/NAME) as z:
            assert z.namelist()==names and z.testzip() is None and {n for n in names if z.read(n)!=a.read(n)}==set(changes)
            assert all(z.read(n)==v for n,v in changes.items())
    (out/'vpm-entry.json').write_bytes(dump(dict(manifest,zipSHA256=sha((out/NAME).read_bytes()))));print('verified only window C#, manifest and two release documents changed')
if __name__=='__main__':build(Path(sys.argv[1]),Path(sys.argv[2]))
