"""Real Windows-only script file contracts; synthetic fixture, not Unity acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run():
    output = Path(sys.argv[1]).absolute()
    if output.exists():
        raise SystemExit('evidence_exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = sorted([*ROOT.glob('package/Editor/Core/*.cs'),
                      *ROOT.glob('tests/unity-core/Script*.cs'),
                      *ROOT.glob('tests/unity-core/Script*.csproj'),
                      ROOT/'tests/unity-core/ReviewNuGet.Config', Path(__file__)])
    hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report = {'scope': 'real Windows HANDLE synthetic fixtures only; NOT Unity or release approval',
              'windows_kernel': os.name == 'nt', 'before': hashes(), 'runs': []}
    if os.name != 'nt':
        report['passed'] = False
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        return False
    dotnet = shutil.which('dotnet')
    if not dotnet:
        report.update(passed=False, error='dotnet_required')
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        return False
    try:
        return execute(dotnet, sources, hashes, report, output)
    except Exception as ex:
        report.update(passed=False, error=type(ex).__name__)
        if isinstance(ex, subprocess.TimeoutExpired):
            report['timeout_stdout'] = (ex.stdout or b'').decode('utf-8', errors='replace') if isinstance(ex.stdout, bytes) else ex.stdout
            report['timeout_stderr'] = (ex.stderr or b'').decode('utf-8', errors='replace') if isinstance(ex.stderr, bytes) else ex.stderr
        output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        return False


def execute(dotnet, sources, hashes, report, output):
    work = None
    try:
      with tempfile.TemporaryDirectory(prefix='vragent-script-ci-') as tmp:
          work = Path(tmp)
          env = {key: os.environ[key] for key in ('PATH', 'SystemRoot', 'SystemDrive', 'WINDIR', 'COMSPEC', 'PATHEXT',
                 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA') if os.environ.get(key)}
          env.update(HOME=tmp, USERPROFILE=tmp, TEMP=tmp, TMP=tmp, APPDATA=tmp, LOCALAPPDATA=tmp,
                     DOTNET_CLI_HOME=tmp, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
                     DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1', MSBUILDDISABLENODEREUSE='1')
          for name, prefix, count in [('ScriptPathCases', 'WP', 8), ('ScriptWriteCases', 'SW', 13)]:
              build = subprocess.run([dotnet, 'build', str(ROOT/'tests/unity-core'/(name+'.csproj')),
                  '-c', 'Release', '--disable-build-servers', '-p:UseSharedCompilation=false', '-p:NuGetAudit=false',
                  '-p:RestoreSources=', '-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),
                  '-p:BaseIntermediateOutputPath='+str(work/name/'obj')+os.sep,
                  '-p:BaseOutputPath='+str(work/name/'bin')+os.sep], cwd=ROOT, env=env,
                  capture_output=True, text=True, encoding='utf-8', timeout=90)
              row = {'suite': name, 'build_exit': build.returncode, 'build_stdout': build.stdout, 'build_stderr': build.stderr}
              if build.returncode == 0:
                  result = subprocess.run([dotnet, str(work/name/'bin/Release/net8.0'/(name+'.dll'))],
                      cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
                  ids = re.findall(r'^PASS ('+prefix+r'\d{3}) ', result.stdout, re.M)
                  row.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr, ids=ids,
                             expected=[f'{prefix}{i:03d}' for i in range(1, count+1)])
                  row['passed'] = (result.returncode == 0 and ids == row['expected'] and
                      not re.search(r'(?i)ResourceWarning|\bwarning [A-Z]+\d+:|skipped|WINDOWS_KERNEL_NOT_EXECUTED',
                                    build.stdout+build.stderr+result.stdout+result.stderr))
              else:
                  row['passed'] = False
              report['runs'].append(row)
    finally:
        report['temporary_directory_removed'] = work is not None and not work.exists()
    report.update(temporary_directory_removed=not work.exists(), after=hashes())
    report['passed'] = report['before'] == report['after'] and report['temporary_directory_removed'] and all(r['passed'] for r in report['runs'])
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'suites': [{k: v for k, v in row.items() if k in ('suite', 'passed', 'ids')} for row in report['runs']]}))
    return report['passed']


if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
