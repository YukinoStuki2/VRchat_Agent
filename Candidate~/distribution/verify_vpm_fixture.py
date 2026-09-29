"""Exercise official vrc-get on throwaway synthetic packages, NOT Candidate.

Derived from the existing isolated smoke_vpm.py workflow; stdlib only.
Does not import build_candidate, publish, run Unity, or touch a real project.
"""
import argparse
import functools
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import zipfile


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def verify(binary, expected_hash):
    binary = Path(binary).resolve(strict=True)
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected_hash
    result = {'scope': 'synthetic VPM resolver only', 'candidate_tested': False,
              'unity_executed': False, 'commands': [], 'checks': {},
              'vrc_get_sha256': expected_hash, 'passed': False}
    package = 'com.example.candidate-distribution-fixture'
    with tempfile.TemporaryDirectory(prefix='candidate-vpm-fixture-') as td:
        base = Path(td)
        web = base / 'web'; web.mkdir()
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
            functools.partial(Quiet, directory=str(web)))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        port = server.server_port
        url = f'http://127.0.0.1:{port}'
        pids = []
        try:
            index = {'name': 'Synthetic resolver fixture; NOT Candidate',
                'id': 'com.example.candidate-distribution-fixture.repo',
                'url': url + '/index.json', 'packages': {package: {'versions': {}}}}
            for version in ('1.0.0', '1.0.1'):
                manifest = {'name': package, 'version': version, 'unity': '2022.3',
                    'displayName': 'Synthetic test only', 'url': f'{url}/{version}.zip'}
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for name, body in {'package.json': json.dumps(manifest),
                        'README.md': 'TEST ONLY; contains no Candidate code.'}.items():
                        archive.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), body)
                data = stream.getvalue()
                (web / f'{version}.zip').write_bytes(data)
                index['packages'][package]['versions'][version] = dict(manifest,
                    zipSHA256=hashlib.sha256(data).hexdigest())
            (web / 'index.json').write_text(json.dumps(index))
            bad = json.loads(json.dumps(index))
            bad['id'] += '.bad'; bad['url'] = url + '/bad.json'
            bad['packages'][package]['versions']['1.0.1']['zipSHA256'] = '0' * 64
            (web / 'bad.json').write_text(json.dumps(bad))

            def setup(name):
                root = base / name
                home = root / 'home'; home.mkdir(parents=True)
                project = root / 'project'
                for folder in ('Assets', 'Packages', 'ProjectSettings'):
                    (project / folder).mkdir(parents=True)
                (project / 'ProjectSettings/ProjectVersion.txt').write_text(
                    'm_EditorVersion: 2022.3.22f1\n')
                (project / 'Packages/manifest.json').write_text('{"dependencies":{}}')
                (project / 'Packages/vpm-manifest.json').write_text(
                    '{"dependencies":{},"locked":{}}')
                (project / 'Assets/user-kept.txt').write_text('unrelated fixture asset')
                env = {'PATH': '/usr/bin:/bin', 'HOME': str(home),
                    'XDG_DATA_HOME': str(root / 'data'),
                    'XDG_CONFIG_HOME': str(root / 'config'),
                    'XDG_CACHE_HOME': str(root / 'cache'),
                    'TMPDIR': str(root), 'LANG': 'C.UTF-8',
                    'HTTP_PROXY': 'http://127.0.0.1:1',
                    'HTTPS_PROXY': 'http://127.0.0.1:1',
                    'ALL_PROXY': 'http://127.0.0.1:1',
                    'NO_PROXY': '127.0.0.1,localhost'}
                return project, env

            def run(project, env, *args, success=True):
                with subprocess.Popen([str(binary), *args], cwd=project, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
                    pids.append(process.pid)
                    try:
                        out, err = process.communicate(timeout=40)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.communicate(); raise
                    result['commands'].append({'argv': list(args), 'exit': process.returncode,
                        'stdout': out, 'stderr': err, 'pid': process.pid})
                    assert (process.returncode == 0) == success, result['commands'][-1]
                    return out + err

            project, env = setup('normal')
            run(project, env, 'repo', 'add', '--no-update', url + '/index.json')
            def version_is(version):
                installed = json.loads((project / 'Packages' / package / 'package.json').read_text())
                locked = json.loads((project / 'Packages/vpm-manifest.json').read_text())
                return installed['version'] == version and locked['locked'][package]['version'] == version
            run(project, env, 'install', package, '1.0.0', '--no-update', '-y')
            assert version_is('1.0.0'); result['checks']['fresh_install'] = True
            run(project, env, 'upgrade', package, '1.0.1', '--no-update', '-y')
            assert version_is('1.0.1'); result['checks']['upgrade'] = True
            run(project, env, 'downgrade', package, '1.0.0', '--no-update', '-y')
            assert version_is('1.0.0'); result['checks']['downgrade'] = True
            run(project, env, 'remove', package, '--no-update', '-y')
            locked = json.loads((project / 'Packages/vpm-manifest.json').read_text())
            assert not (project / 'Packages' / package).exists()
            assert package not in locked['locked'] and package not in locked['dependencies']
            assert (project / 'Assets/user-kept.txt').read_text() == 'unrelated fixture asset'
            assert json.loads((project / 'Packages/manifest.json').read_text()) == {'dependencies': {}}
            result['checks']['remove_preserves_unrelated'] = True
            project, env = setup('bad-hash')
            before = (project / 'Packages/vpm-manifest.json').read_bytes()
            run(project, env, 'repo', 'add', '--no-update', url + '/bad.json')
            out = run(project, env, 'install', package, '1.0.1', '--no-update', '-y', success=False)
            assert 'hash' in out.lower()
            assert (project / 'Packages/vpm-manifest.json').read_bytes() == before
            assert not (project / 'Packages' / package).exists()
            result['checks']['wrong_hash_rejected_without_install'] = True
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
            result['server_thread_stopped'] = not thread.is_alive()
            result['vrc_processes_absent'] = all(not Path(f'/proc/{pid}').exists() for pid in pids)
            with socket.socket() as probe:
                probe.settimeout(1)
                result['listener_closed'] = probe.connect_ex(('127.0.0.1', port)) != 0
    result['fixture_removed'] = not Path(td).exists()
    result['passed'] = (len(result['checks']) == 5 and all(result['checks'].values())
        and result['server_thread_stopped'] and result['vrc_processes_absent']
        and result['listener_closed'] and result['fixture_removed'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = verify(args.binary, args.sha256)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'commands'}))
    raise SystemExit(0 if result['passed'] else 1)
