"""Offline .NET and real SDK/HTTP/WS verification; Unity remains a fixture.
No install, user configuration, Unity process, commit or publishing. All builds
are fresh in a temporary directory. Original review evidence is never replaced.
"""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests/unity-core'
DOTNET = Path('/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet')
PYTHON = '/home/ubuntu/.cache/uv/archive-v0/7z4PORN2YM2xSubx/bin/python'

def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted([*(ROOT / 'package/Editor').rglob('*.cs'),
                *(ROOT / 'runtime').glob('*.py'), *(ROOT / 'tests/unity-core').glob('*.cs'),
                *(ROOT / 'dependencies/mcp-1.29.1/mcp').rglob('*.py'),
                ROOT / 'catalog/native-inventory.json', ROOT / 'tests/test_runtime_lifecycle.py', ROOT / 'tests/test_client_binding.py',
                ROOT / 'tests/test_runtime_unity_auth.py', ROOT / 'tests/test_runtime_material.py',
                *(ROOT / 'tests/unity-core').glob('*.csproj'), ROOT / 'tests/verify_unity.py'])}

def main(label):
    output = ROOT / 'evidence' / ('unity-parent-' + label + '.json')
    if output.exists():
        raise SystemExit('Refusing to overwrite earlier evidence')
    report = {'scope': 'local fixture verification, not independent review or Unity acceptance',
              'hashes_before': hashes(), 'runs': [], 'full_product_accepted': False}
    with tempfile.TemporaryDirectory(prefix='vragent-parent-dotnet-') as td:
        work = Path(td)
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'TMPDIR': str(work), 'LANG': 'C.UTF-8',
               'DOTNET_ROOT': str(DOTNET.parent), 'DOTNET_CLI_HOME': str(work),
               'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1',
               'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1', 'MSBUILDDISABLENODEREUSE': '1',
               'PYTHONPATH': str(ROOT / 'dependencies/mcp-1.29.1'),
               'PYTHONWARNINGS': 'always::ResourceWarning', 'FASTMCP_CHECK_FOR_UPDATES': 'off'}
        targets = work / 'References.targets'
        upstream = work / 'ReviewUpstreamApi/bin/Release/net8.0/MCPForUnity.Editor.dll'
        targets.write_text('<Project><Target Name="ParentReference" BeforeTargets="ResolveAssemblyReferences">'
            '<ItemGroup><Reference Condition="\'%(Reference.Identity)\' == \'MCPForUnity.Editor\'">'
            f'<HintPath>{upstream}</HintPath></Reference></ItemGroup></Target></Project>')
        def save():
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        def run(name, argv):
            started = time.monotonic()
            proc = subprocess.Popen([str(x) for x in argv], cwd=ROOT, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            timed_out = False
            try:
                stdout, stderr = proc.communicate(timeout=90)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate(timeout=5)
            group_remaining = False
            try:
                os.killpg(proc.pid, 0)
                group_remaining = True
            except ProcessLookupError:
                pass
            if group_remaining:
                os.killpg(proc.pid, signal.SIGKILL)
            row = {'name': name, 'argv': [str(x) for x in argv], 'exit_code': proc.returncode,
                   'stdout': stdout, 'stderr': stderr, 'timeout': timed_out, 'pid': proc.pid,
                   'process_group_absent': not group_remaining,
                   'pid_absent': not Path(f'/proc/{proc.pid}').exists()}
            row['elapsed_seconds'] = time.monotonic() - started
            report['runs'].append(row)
            save()
            print(json.dumps({'name': name, 'exit_code': row['exit_code']}, ensure_ascii=False), flush=True)
            return row['exit_code'] == 0 and not timed_out and not group_remaining
        def dll(name):
            return work / name / 'bin/Release/net8.0' / (name + '.dll')
        def build(name):
            return run(name + '-build', [DOTNET, 'build', TESTS / (name + '.csproj'),
                '--configuration', 'Release', '--disable-build-servers', '-p:UseSharedCompilation=false',
                '-p:BaseIntermediateOutputPath=' + str(work/name/'obj') + '/',
                '-p:BaseOutputPath=' + str(work/name/'bin') + '/',
                '-p:RestoreConfigFile=' + str(TESTS/'ReviewNuGet.Config'),
                '-p:CustomAfterMicrosoftCommonTargets=' + str(targets),
                '-p:NuGetAudit=false', '-p:RestoreSources='])
        try:
            if build('ReviewUpstreamApi'):
                build('ReviewExternalAssembly')
            for name in ('CoreTests', 'AdapterTests', 'ConsoleNativeCases', 'FixOutputCases', 'ReviewLeakCases',
                         'FixIdentityAbsent', 'FixIdentityCases', 'LifecycleCases', 'OwnedGateCases', 'ContinuityCases', 'EditorBootstrapCases', 'WirePeer'):
                if not build(name):
                    continue
                if name == 'FixIdentityCases':
                    for i, path in enumerate(('/tmp/fixture-only-A/Assets', 'C:/Fixture Only 中文/Assets',
                                             '/tmp/fixture-only-A/Assets/')):
                        run(name + '-' + str(i), [DOTNET, dll(name), path])
                elif name == 'EditorBootstrapCases':
                    run('CS007',[DOTNET,dll(name),'--client-admission-tests',PYTHON,ROOT/'launcher/direct_python.py'])
                elif name == 'WirePeer':
                    loader = ('import importlib.util,unittest; from pathlib import Path; '
                        's=importlib.util.spec_from_file_location("wire_parent",' + repr(str(ROOT/'tests/test_wire_integration.py')) + '); '
                        'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.DLL=Path(' + repr(str(dll(name))) + '); '
                        'r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(m));'
                        'raise SystemExit(not r.wasSuccessful())')
                    run('WI001', [PYTHON, '-B', '-c', loader])
                    # Each server uses its own PROCESS: do not reset private
                    # uvicorn/SSE globals to mask cross-test shutdown leakage.
                    tree=ast.parse((ROOT/'tests/test_runtime_lifecycle.py').read_text())
                    methods=[node.name+'.'+m.name for node in tree.body if isinstance(node,ast.ClassDef)
                        for m in node.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test_LC')]
                    assert len(methods)==7 and {m.split('.test_')[1].split('_')[0] for m in methods}=={f'LC{i:03d}' for i in range(1,8)}
                    report['lifecycle_isolated_methods']=methods
                    for method in methods:
                        lifecycle = ('import unittest,warnings; warnings.simplefilter("always",ResourceWarning); from pathlib import Path; '
                            'import tests.test_runtime_lifecycle as m; m.WIRE_DLL=Path(' + repr(str(dll(name))) + '); '
                            's=unittest.defaultTestLoader.loadTestsFromName('+repr(method)+',m);assert s.countTestCases()==1; '
                            'r=unittest.TextTestRunner(verbosity=2).run(s); '
                            'raise SystemExit(not r.wasSuccessful() or bool(r.skipped))')
                        run(method.split('.test_')[1].split('_')[0],[PYTHON,'-B','-c',lifecycle])
                    binding_tree=ast.parse((ROOT/'tests/test_client_binding.py').read_text())
                    binding_methods=[node.name+'.'+m.name for node in binding_tree.body if isinstance(node,ast.ClassDef)
                        for m in node.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test_CB')]
                    assert len(binding_methods)==7 and {m.split('.test_')[1].split('_')[0] for m in binding_methods}=={f'CB{i:03d}' for i in range(1,8)}
                    report['client_binding_methods']=binding_methods
                    for method in binding_methods:
                        binding=('import sys,unittest;from pathlib import Path;sys.path.insert(0,'+repr(str(ROOT/'tests'))+');'
                            'import test_client_binding as m;m.WIRE_DLL=Path('+repr(str(dll(name)))+');m.DOTNET=Path('+repr(str(DOTNET))+');'
                            's=unittest.defaultTestLoader.loadTestsFromName('+repr(method)+',m);assert s.countTestCases()==1;'
                            'r=unittest.TextTestRunner(verbosity=2).run(s);raise SystemExit(not r.wasSuccessful() or bool(r.skipped))')
                        run(method.split('.test_')[1].split('_')[0],[PYTHON,'-B','-c',binding])
                else:
                    run(name, [DOTNET, dll(name)])
        finally:
            report['hashes_after'] = hashes()
            report['source_unchanged'] = report['hashes_before'] == report['hashes_after']
            save()
    report['owned_build_directory_removed'] = not Path(td).exists()
    report['continuity_pass_ids'] = sorted(set(re.findall(r'^PASS (PC\d{3}) ',
        '\n'.join(r.get('stdout','') for r in report['runs']),re.M)))
    assert report['continuity_pass_ids'] == [f'PC{i:03d}' for i in range(1,11)]
    report['client_selection_csharp_ids'] = sorted(set(re.findall(r'^PASS (CS00[789]|CS010) ', '\n'.join(r.get('stdout','') for r in report['runs']),re.M)))
    assert report['client_selection_csharp_ids'] == ['CS007','CS008','CS009','CS010']
    report['all_commands_succeeded'] = bool(report['runs']) and all(
        r['exit_code'] == 0 and not r['timeout'] and r['process_group_absent'] and r['pid_absent']
        for r in report['runs'])
    report['pass_ids'] = sorted(set(re.findall(r'^PASS ((?:UC|UA|UF|CLC|OI)\d{3})',
        '\n'.join(r.get('stdout','') for r in report['runs']), re.M)))
    # Per-type material rows are subcases of UF017/UF018, not new unique IDs.
    report['pass_ids'] += sorted(set(m.group(1) for r in report['runs'] for m in re.finditer(
        r'"test_id":"(UR\d{3})[^"\n]*"[^\n]*"outcome":"PASS"', r.get('stdout',''))))
    if any(r['name'] == 'WI001' and r['exit_code'] == 0 for r in report['runs']):
        report['pass_ids'].append('WI001')
    for row in report['runs']:
        if re.fullmatch(r'LC00[1-7]',row['name']) and row['exit_code'] == 0:
            report['pass_ids'] += sorted(set(re.findall(r'^test_(LC\d{3})_', row['stderr'], re.M)))
    report['unique_pass_count'] = len(set(report['pass_ids']))
    report['console_pass_ids']=sorted(set(re.findall(r'^PASS (NC\d{3}) ', '\n'.join(r.get('stdout','') for r in report['runs']),re.M)))
    report['console_ids_match']=report['console_pass_ids']==[f'NC{i:03d}' for i in range(1,5)]
    report['client_binding_pass_ids'] = sorted(r['name'] for r in report['runs'] if re.fullmatch(r'CB00[1-7]',r['name']) and r['exit_code']==0)
    report['client_binding_ids_match'] = report['client_binding_pass_ids'] == [f'CB{i:03d}' for i in range(1,8)]
    expected = ({f'UC{i:03d}' for i in range(1, 16)} | {f'UA{i:03d}' for i in range(1, 10)} |
                {f'UF{i:03d}' for i in range(1, 25)} | {'UR002', 'UR003', 'WI001', 'CLC001', 'CLC002'} |
                {f'LC{i:03d}' for i in range(1, 8)} | {f'OI{i:03d}' for i in range(1, 11)})
    report['expected_ids_match'] = set(report['pass_ids']) == expected
    report['resource_warning_lines'] = [line for row in report['runs']
        for line in row['stderr'].splitlines() if 'ResourceWarning:' in line]
    report['clean_warning_free_run'] = not report['resource_warning_lines']
    save()
    print(json.dumps({k: report[k] for k in ('all_commands_succeeded','unique_pass_count',
        'source_unchanged','owned_build_directory_removed','expected_ids_match')}, ensure_ascii=False))
    return 0 if (report['all_commands_succeeded'] and report['source_unchanged'] and
                 report['expected_ids_match'] and report['owned_build_directory_removed'] and
                 report['clean_warning_free_run'] and report['client_binding_ids_match'] and report['console_ids_match']) else 1

if __name__ == '__main__':
    if len(sys.argv) != 2 or re.fullmatch(r'[a-z0-9-]+', sys.argv[1]) is None:
        raise SystemExit('one evidence label required')
    raise SystemExit(main(sys.argv[1]))
