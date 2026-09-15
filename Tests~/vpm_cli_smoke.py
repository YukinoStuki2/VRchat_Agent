"""Real vrc-get resolver in an isolated synthetic Unity project (NOT Unity).
Nothing writes to user HOME/settings/projects or runs editor C#.
"""
from pathlib import Path
import contextlib
import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading

# Linux only: Windows ignores XDG_DATA_HOME and would use real VCC settings.
if os.name != 'posix' or not __import__('sys').platform.startswith('linux'):
    raise SystemExit('Linux-only isolated smoke test. Do not run against Windows VCC settings.')
ROOT=Path(__file__).resolve().parents[1]
BIN=os.environ.get('VRC_GET_BINARY') or shutil.which('vrc-get')
if not BIN:
    raise SystemExit('Set VRC_GET_BINARY to a verified vrc-get executable; this smoke test never installs one.')
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args): pass

with tempfile.TemporaryDirectory(prefix='vpm-isolated-smoke-') as td:
    t=Path(td);web=t/'web';web.mkdir();home=t/'home';home.mkdir();data=t/'data';data.mkdir()
    shutil.copytree(ROOT/'VPM~/packages',web/'packages')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(web)))
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        url='http://127.0.0.1:'+str(server.server_port)+'/index.json'
        index=json.loads((ROOT/'index.json').read_text());index['url']=url
        for row in index['packages'].values():
            for manifest in row['versions'].values():manifest['url']=url.replace('index.json','packages/')+manifest['url'].rsplit('/',1)[1]
        # Historical-version fixture exists only on this loopback test server.
        # It is NOT published as an earlier VPM release.
        import io,zipfile
        ro='com.yukino.vrchat-readonly-mcp'
        cur=index['packages'][ro]['versions']['0.1.2']
        with zipfile.ZipFile(web/'packages'/cur['url'].rsplit('/',1)[1]) as z:
            older={n:z.read(n) for n in z.namelist()}
        old=json.loads(older['package.json']);old['version']='0.1.1'
        old['url']=url.replace('index.json','packages/')+'test-only-readonly-0.1.1.zip'
        older['package.json']=json.dumps(old).encode()
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            for name,content in older.items():z.writestr(name,content)
        (web/'packages/test-only-readonly-0.1.1.zip').write_bytes(b.getvalue())
        index['packages'][ro]['versions']['0.1.1']=dict(old,zipSHA256=hashlib.sha256(b.getvalue()).hexdigest())
        (web/'index.json').write_text(json.dumps(index))
        env=dict(os.environ,HOME=str(home),XDG_DATA_HOME=str(data),XDG_CONFIG_HOME=str(t/'config'))
        env.update(NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
        project=t/'SyntheticProject';(project/'Packages').mkdir(parents=True);(project/'Assets').mkdir();(project/'ProjectSettings').mkdir()
        (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.22f1\n')
        upstream='https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0'
        manifest={'dependencies':{'com.coplaydev.unity-mcp':upstream,'com.unity.nuget.newtonsoft-json':'3.0.2'}}
        (project/'Packages/manifest.json').write_text(json.dumps(manifest))
        (project/'Packages/vpm-manifest.json').write_text(json.dumps({'dependencies':{},'locked':{}}))
        def run(*args,ok=True):
            assert isinstance(BIN, str)
            p=subprocess.run([BIN,*args],env=env,cwd=project,text=True,capture_output=True,timeout=45)
            print('COMMAND',args,'EXIT',p.returncode,'\n'+p.stdout+p.stderr,flush=True)
            if ok: assert p.returncode==0
            return p
        run('repo','add','--no-update',url)
        run('repo','packages','--no-update',url)
        run('install','com.yukino.vrchat-readonly-mcp','0.1.1','--no-update','-y')
        assert json.loads((project/'Packages'/ro/'package.json').read_text())['version']=='0.1.1'
        run('upgrade','com.yukino.vrchat-readonly-mcp','0.1.2','--no-update','-y')
        run('install','com.yukino.vrchat-managed-editing','0.1.0-preview.2','--prerelease','--no-update','-y')
        for package_id,version in [('com.yukino.vrchat-readonly-mcp','0.1.2'),('com.yukino.vrchat-managed-editing','0.1.0-preview.2')]:
            got=json.loads((project/'Packages'/package_id/'package.json').read_text());assert got['version']==version
            assert got['dependencies']['com.coplaydev.unity-mcp']=='10.2.0'
        remaining=json.loads((project/'Packages/manifest.json').read_text());assert remaining['dependencies']['com.coplaydev.unity-mcp']==upstream
        assert remaining['dependencies']['com.unity.nuget.newtonsoft-json']=='3.0.2'
        print('VPM_LOCK', (project/'Packages/vpm-manifest.json').read_text())
        # Fresh synthetic project: installing managed must resolve readonly automatically.
        second=t/'DependencyProject';shutil.copytree(project/'ProjectSettings',second/'ProjectSettings')
        (second/'Packages').mkdir();(second/'Assets').mkdir()
        (second/'Packages/manifest.json').write_text(json.dumps(manifest))
        (second/'Packages/vpm-manifest.json').write_text(json.dumps({'dependencies':{},'locked':{}}))
        project=second
        run('install','com.yukino.vrchat-managed-editing','0.1.0-preview.2','--prerelease','--no-update','-y')
        locked=json.loads((project/'Packages/vpm-manifest.json').read_text())['locked']
        assert locked[ro]['version']=='0.1.2'
        assert locked['com.yukino.vrchat-managed-editing']['version']=='0.1.0-preview.2'
        # Third isolated cache and project: a wrong checksum must fail installation.
        bad=json.loads(json.dumps(index));bad['url']=url.replace('index.json','bad.json');bad['id']='test.only.bad-checksum'
        bad['packages'][ro]['versions']['0.1.2']['zipSHA256']='0'*64
        (web/'bad.json').write_text(json.dumps(bad))
        third=t/'BadHashProject';shutil.copytree(second/'ProjectSettings',third/'ProjectSettings')
        (third/'Packages').mkdir();(third/'Assets').mkdir()
        (third/'Packages/manifest.json').write_text(json.dumps(manifest))
        (third/'Packages/vpm-manifest.json').write_text(json.dumps({'dependencies':{},'locked':{}}))
        project=third;env['XDG_DATA_HOME']=str(t/'bad-data')
        run('repo','add','--no-update',bad['url'])
        failed=run('install',ro,'0.1.2','--no-update','-y',ok=False)
        assert failed.returncode!=0 and 'hash' in (failed.stdout+failed.stderr).lower()
        assert ro not in json.loads((project/'Packages/vpm-manifest.json').read_text())['locked']
        print('TEST_RESULT',json.dumps({'real_vrc_get_installed_both':True,'old_fixture_upgraded_to_012':True,'readonly_dependency_auto_installed':True,'wrong_checksum_rejected':True,'upstream_git_dependency_preserved':True,'unity_executed':False}))
    finally:
        server.shutdown();server.server_close();thread.join(5);assert not thread.is_alive()
assert not Path(td).exists()
print('isolated_state_and_fixture_removed',True)
