"""Compile COMPLETE pinned native job sources; Unity APIs alone are doubles.
Each case has a fresh process to exercise static initialization. No source patch,
MCP exposure, real Unity, user data, or independent-review claim. The single-job
scope probe is intentionally expected to fail and is retained as RED evidence.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from verify_unity import DOTNET, TESTS, hashes
NATIVE = Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity/Editor')
PINS = {
    'Services/TestJobManager.cs': '80be4984f63398ba8d3484a514e131f131b9a562757e713b07d0ac73fc164476',
    'Services/TestRunStatus.cs': '694f3b51f0e55b19db823c0e2fed2393b104c0a33c6d5be13e9b7e3f391a2954',
    'Tools/GetTestJob.cs': 'b9c4a46c7b73cee8ddd7e832cf388c1c9da7a60b2153bfb3ea376fd154193d83',
    'Helpers/Response.cs': 'a1769de32b9c6824841c070f0590ae7e9f44485d2a6c44a0bce3ed3f68e17391',
    'Helpers/ToolParams.cs': 'f708345c2913672011a7050ddceb96141a22f0880c9dfea65ebfb5b50c792abc',
    'Helpers/ParamCoercion.cs': '69b425c49152a31d68e80d0a6498c78c406989242214a8f9b760b6936b17670b',
    'Helpers/StringCaseUtility.cs': '5758c84d56fd4a3420aede775ddd1ca7cc8e0854476bedf65a1a9bca437cd411',
}

def native_hashes():
    return {name: hashlib.sha256((NATIVE / name).read_bytes()).hexdigest() for name in PINS}


def main(label):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', label):
        raise ValueError('invalid evidence label')
    output = ROOT / 'evidence' / ('native-job-effects-' + label + '.json')
    if output.exists():
        raise FileExistsError('refusing to overwrite evidence')
    before = hashes()
    before[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report = {'scope': 'full pinned C# native characterization; Unity APIs are doubles',
              'upstream_commit': '30d22075093d1d35dfb0091c1c7550e9ad948577',
              'native_before': native_hashes(), 'candidate_before': before, 'runs': [],
              'product_accepted': False, 'single_job_scope_supported': False}
    assert report['native_before'] == PINS, 'pinned source drift'
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        with tempfile.TemporaryDirectory(prefix='vragent-native-job-') as td:
            work = Path(td)
            env = {'PATH': '/usr/bin:/bin', 'HOME': td, 'TMPDIR': td, 'LANG': 'C.UTF-8',
                   'DOTNET_ROOT': str(DOTNET.parent), 'DOTNET_CLI_HOME': td,
                   'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1',
                   'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1', 'MSBUILDDISABLENODEREUSE': '1'}
            def run(name, argv):
                proc = subprocess.Popen([str(v) for v in argv], cwd=ROOT, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
                timeout = False
                try:
                    stdout, stderr = proc.communicate(timeout=90 if name == 'build' else 15)
                except subprocess.TimeoutExpired:
                    timeout = True
                    os.killpg(proc.pid, signal.SIGKILL)
                    stdout, stderr = proc.communicate(timeout=10)
                remaining = False
                try:
                    os.killpg(proc.pid, 0)
                    remaining = True
                except ProcessLookupError:
                    pass
                if remaining:
                    os.killpg(proc.pid, signal.SIGKILL)
                row = {'name': name, 'exit_code': proc.returncode, 'timeout': timeout,
                       'stdout': stdout, 'stderr': stderr, 'pid': proc.pid,
                       'pid_absent': not Path(f'/proc/{proc.pid}').exists(),
                       'process_group_absent': not remaining}
                report['runs'].append(row)
                save()
                print(json.dumps({k: row[k] for k in ('name', 'exit_code', 'timeout')}), flush=True)
                return row
            build = run('build', [DOTNET, 'build', TESTS / 'NativeJobEffects.csproj',
                '-c', 'Release', '--disable-build-servers', '-p:UseSharedCompilation=false',
                '-p:BaseIntermediateOutputPath=' + str(work / 'obj') + '/',
                '-p:BaseOutputPath=' + str(work / 'bin') + '/',
                '-p:RestoreConfigFile=' + str(TESTS / 'ReviewNuGet.Config'),
                '-p:NuGetAudit=false', '-p:RestoreSources='])
            if build['exit_code'] == 0:
                dll = work / 'bin/Release/net8.0/NativeJobEffects.dll'
                run('single-job-scope-red', [DOTNET, dll, 'NJ002', '--assert-single-job'])
                for number in range(1, 11):
                    case = f'NJ{number:03d}'
                    run(case, [DOTNET, dll, case])
        report['owned_build_directory_removed'] = not Path(td).exists()
    finally:
        report['native_after'] = native_hashes()
        report['candidate_after'] = hashes()
        report['candidate_after'][str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report['source_unchanged'] = report['native_after'] == PINS and report['candidate_after'] == before
        save()
    report['pass_ids'] = re.findall(r'^PASS (NJ\d{3}) ', '\n'.join(r['stdout'] for r in report['runs']), re.M)
    report['expected_ids_match'] = report['pass_ids'] == [f'NJ{i:03d}' for i in range(1, 11)]
    red = [r for r in report['runs'] if r['name'] == 'single-job-scope-red']
    report['single_job_scope_red_reproduced'] = len(red) == 1 and red[0]['exit_code'] == 1 and 'SINGLE_JOB_SCOPE_VIOLATED' in red[0]['stderr']
    report['warning_lines'] = [line for r in report['runs'] for line in (r['stdout'] + '\n' + r['stderr']).splitlines()
                              if re.search(r'ResourceWarning|(?i:\bwarning\s+[A-Z]+\d+:)', line)]
    report['characterization_passed'] = (
        len(report['runs']) == 12 and report['expected_ids_match'] and report['single_job_scope_red_reproduced']
        and report['source_unchanged'] and report['owned_build_directory_removed'] and not report['warning_lines']
        and all(not r['timeout'] and r['pid_absent'] and r['process_group_absent']
                and r['exit_code'] == (1 if r['name'] == 'single-job-scope-red' else 0) for r in report['runs']))
    save()
    print(json.dumps({k: report[k] for k in ('characterization_passed', 'single_job_scope_red_reproduced',
          'expected_ids_match', 'source_unchanged', 'owned_build_directory_removed')}, ensure_ascii=False))
    return 0 if report['characterization_passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
