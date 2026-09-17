"""Linux-only real resolver test of launcher; never starts Unity or launcher."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile

if not sys.platform.startswith('linux'):raise SystemExit('Linux-only isolated test')
ROOT=Path(__file__).resolve().parents[1]
BIN=os.environ.get('VRC_GET_BINARY')
if not BIN:raise SystemExit('Set VRC_GET_BINARY; no automatic binary download')
ID='com.yukino.vrchat-agent-launcher'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,format,*args):pass
with tempfile.TemporaryDirectory(prefix='launcher-vpm-smoke-') as td:
    t=Path(td);web=t/'web';web.mkdir()
    shutil.copytree(ROOT/'VPM~/packages',web/'packages')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(web)))
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        url='http://127.0.0.1:'+str(server.server_port)+'/index.json'
        index=json.loads((ROOT/'index.json').read_text());index['url']=url
        for package in index['packages'].values():
            for record in package['versions'].values():record['url']=url.replace('index.json','packages/')+record['url'].rsplit('/',1)[1]
        (web/'index.json').write_text(json.dumps(index))
        project=t/'Project'
        for n in ['Assets','Packages','ProjectSettings']:(project/n).mkdir(parents=True)
        (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.22f1\n')
        upstream={'dependencies':{'com.coplaydev.unity-mcp':'https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0','com.unity.nuget.newtonsoft-json':'3.0.2'}}
        (project/'Packages/manifest.json').write_text(json.dumps(upstream))
        (project/'Packages/vpm-manifest.json').write_text('{"dependencies":{},"locked":{}}')
        env=dict(os.environ,HOME=str(t/'home'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
        for key in ['XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR']:env[key]=str(t/key)
        def run(*args):
            assert isinstance(BIN,str)
            p=subprocess.run([BIN,*args],cwd=project,env=env,capture_output=True,text=True,timeout=50)
            print(args,p.returncode,p.stdout,p.stderr,flush=True);assert p.returncode==0
        run('repo','add','--no-update',url)
        run('install',ID,'0.1.0-preview.1','--prerelease','--no-update','-y')
        assert json.loads((project/'Packages'/ID/'package.json').read_text())['version']=='0.1.0-preview.1'
        run('upgrade',ID,'0.1.0-preview.2','--prerelease','--no-update','-y')
        lock=json.loads((project/'Packages/vpm-manifest.json').read_text())['locked']
        assert lock[ID]['version']=='0.1.0-preview.2'
        assert lock['com.yukino.vrchat-readonly-mcp']['version']=='0.1.2'
        assert lock['com.yukino.vrchat-managed-editing']['version']=='0.1.0-preview.2'
        for pid in [ID,'com.yukino.vrchat-readonly-mcp','com.yukino.vrchat-managed-editing']:
            version=lock[pid]['version'];rec=index['packages'][pid]['versions'][version]
            zpath=web/'packages'/rec['url'].rsplit('/',1)[1]
            assert hashlib.sha256(zpath.read_bytes()).hexdigest()==rec['zipSHA256']
            with zipfile.ZipFile(zpath) as z:
                for name in z.namelist():assert (project/'Packages'/pid/name).read_bytes()==z.read(name),name
        assert json.loads((project/'Packages/manifest.json').read_text())==upstream
        run('remove',ID,'--no-update','-y')
        assert not (project/'Packages'/ID).exists()
        print('PASS: real launcher install, readonly dependency, every byte, Git prereq preserved, uninstall; no Unity execution')
    finally:
        server.shutdown();server.server_close();thread.join(5);assert not thread.is_alive()
assert not Path(td).exists()
