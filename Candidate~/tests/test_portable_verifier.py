"""CI driver boundaries only; not runtime or Windows kernel acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def driver():
    spec = importlib.util.spec_from_file_location('portable_verifier', ROOT/'tests/verify_portable.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableVerifierTests(unittest.TestCase):
    def test_VP015_ci_executes_exact_read_method_and_completion_gates(self):
        import ast, textwrap
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        step=workflow.split('      - name: Signed client approval identity and compiled gates (not Unity)\n',1)[1].split('      - name:',1)[0]
        tree=ast.parse(textwrap.dedent(step.split('        run: |\n',1)[1]))
        assignments=sorted([n for n in ast.walk(tree) if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id in {'expected_console_ids','console_methods'} for t in n.targets)],key=lambda n:n.lineno)
        checks=[n for n in ast.walk(tree) if isinstance(n,ast.Assert)
            and any(isinstance(x,ast.Name) and x.id=='console_methods' for x in ast.walk(n))]
        summaries=[n for n in ast.walk(tree) if isinstance(n,ast.Assign)
            and any(ast.unparse(t)=="report['passed']" for t in n.targets)]
        self.assertTrue(checks, 'actual pre-loop execution gate missing')
        self.assertEqual(len(summaries),1)
        env={'root':ROOT,'ast':ast}
        def execute(nodes):
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'ci-read-execution-gates','exec'),env)
        execute(assignments)
        methods=env['console_methods']
        expected={f'RT{i:03d}' for i in range(15,25)}
        self.assertEqual(len(methods),len(expected))
        self.assertEqual({m.split('.test_')[1].split('_')[0] for m in methods},expected)
        variants={'complete':methods,'zero':[],'missing':methods[:-1],
            'missing_hierarchy':[m for m in methods if not any(x in m for x in ('RT022','RT023'))],
            'duplicate':methods+[methods[0]],'duplicate_replacing_missing':methods[:-1]+[methods[0]],
            'wrong_id':methods[:-1]+['RuntimeTests.test_RT999_unexpected'],
            'duplicate_id_new_method':methods[:-1]+[methods[0]+'_duplicate']}
        for label, selected in variants.items():
            with self.subTest(gate='selection',case=label):
                env['console_methods']=selected
                if label=='complete':execute(checks)
                else:
                    with self.assertRaises(AssertionError):execute(checks)
        # Only neutral fixtures for unrelated suites: execute the real final predicate.
        env.update(methods=['binding-fixture'],console_methods=methods)
        for label, completed in {**variants,'wrong_method_same_id':methods[:-1]+[methods[-1]+'_renamed']}.items():
            with self.subTest(gate='completion',case=label):
                env['report']={'owned_build_directory_absent':True,'rows':[{'passed':True}],
                    'console_native':{'exit_code':0,'ids':[f'NC{i:03d}' for i in range(1,5)]},
                    'scene_native':{'exit_code':0,'ids':[f'NS{i:03d}' for i in range(1,9)]},
                    'console_runtime':[{'method':m,'passed':True} for m in completed]}
                execute(summaries)
                self.assertEqual(env['report']['passed'],label=='complete')

    def test_VP016_compiled_scene_gates_require_seven_read_combination(self):
        import ast, textwrap
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        step=workflow.split('      - name: Signed client approval identity and compiled gates (not Unity)\n',1)[1].split('      - name:',1)[0]
        tree=ast.parse(textwrap.dedent(step.split('        run: |\n',1)[1]))
        checks: list[ast.stmt]=[n for n in ast.walk(tree) if isinstance(n,ast.Assert) and "report['scene_native']['ids']" in ast.unparse(n)]
        unity=ast.parse((ROOT/'tests/verify_unity.py').read_text(encoding='utf-8'))
        summaries: list[ast.stmt]=[n for n in ast.walk(unity) if isinstance(n,ast.Assign) and any(ast.unparse(t)=="report['scene_ids_match']" for t in n.targets)]
        self.assertEqual(len(checks),1)
        self.assertEqual(len(summaries),1)
        from types import SimpleNamespace
        complete=[f'NS{i:03d}' for i in range(1,9)]
        for ids in (complete,[],complete[:-1],complete[:-1]+[complete[0]],complete+[complete[0]]):
            env={'result':SimpleNamespace(returncode=0),'report':{'scene_native':{'ids':ids},'scene_pass_ids':ids}}
            with self.subTest(gate='workflow',ids=ids):
                code=compile(ast.Module(body=checks,type_ignores=[]),'ci-scene-gate','exec')
                if ids==complete:exec(code,env)
                else:
                    with self.assertRaises(AssertionError):exec(code,env)
            with self.subTest(gate='verify_unity',ids=ids):
                exec(compile(ast.Module(body=summaries,type_ignores=[]),'unity-scene-gate','exec'),env)
                self.assertEqual(env['report']['scene_ids_match'],ids==complete)

    def test_VP014_owned_relocation_alias_is_canonicalized_before_comparison(self):
        import sys
        from types import SimpleNamespace
        spec=importlib.util.spec_from_file_location('diagnostic_verifier',ROOT/'tests/verify_diagnostic_backend.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(prefix='owned-relocation-alias-') as td:
            actual=Path(td)/'real';actual.mkdir()
            # The driver passes only its own build output, never a source-root claim.
            claimed=actual/'..'/'real'
            server=SimpleNamespace(ENTRY=actual.resolve()/'diagnostics-backend/filesystem/dist/index.js')
            def reached_backend():raise RuntimeError('reached_bundle_validation')
            server.bundled_node=reached_backend
            previous=list(sys.path)
            try:
                with patch.dict(sys.modules,{'server':server,'snapshot':SimpleNamespace()}):
                    with self.assertRaisesRegex(RuntimeError,'reached_bundle_validation'):
                        m.verify_payload(claimed,Path(td),{})
            finally:sys.path[:]=previous

    def test_VP013_windows_portable_requires_pinned_diagnostic_payload(self):
        workflow=(ROOT.parent/'.github/workflows/candidate-portable.yml').read_text(encoding='utf-8')
        self.assertIn('--node-archive $nodeArchive',workflow)
        self.assertIn('diagnostics-backend.lock.json',workflow)
        self.assertIn('$result.build.diagnostics_included',workflow)
        self.assertIn('$result.diagnostic.result.native_read_write_denial_revoke_passed',workflow)
        self.assertIn('node_archive_absent',workflow)

    def test_VP012_linux_never_counts_windows_console_as_executed(self):
        m=driver()
        self.assertTrue(hasattr(m,'regression_arguments'), 'platform-specific test selection missing')
        with patch.object(m.sys,'platform','linux'):
            selected=m.regression_arguments('test_private_process_pipes.py')
        self.assertEqual(selected, [
            'PrivatePipes.test_PP001_owned_child_roundtrip_preserves_private_pipe_ownership',
            'PrivatePipes.test_PP002_reader_is_bounded_and_cancellable',
            'PrivatePipes.test_PP003_visible_console_is_explicit_and_never_mixed_with_stdio'])
        with patch.object(m.sys,'platform','win32'):
            self.assertEqual(m.regression_arguments('test_private_process_pipes.py'), [])
        self.assertEqual(m.regression_arguments('test_editor_owner.py'), [])

    def test_VP006_ci_exercises_new_private_pipe_and_delivery_contracts(self):
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        self.assertTrue(workflow.count('tests/test_private_process_pipes.py') >= 3, 'pipe suite must run and be hash-frozen before/after')
        self.assertTrue(workflow.count('tests/test_editor_delivery.py') >= 3, 'delivery suite must run and be hash-frozen before/after')
        self.assertIn("['PP001','PP002','PP003','PP004']",workflow)
        self.assertIn("['ED001','ED002','ED003','ED004','ED005']",workflow)

    def test_VP008_ci_runs_local_codex_and_new_editor_contracts(self):
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        self.assertTrue(workflow.count('tests/test_codex_local.py')>=3,'local Codex must run and be hash-frozen')
        self.assertIn("['ED001','ED002','ED003','ED004','ED005']",workflow)
        self.assertIn("['CX001','CX002','CX003','CX004','CX005','CX006','CX007']",workflow)
        for number in ('CS008','CS009','CS010'):self.assertIn(number,workflow)

    def test_VP009_ci_executes_recovery_and_editor_record_lifecycle(self):
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        unity=(ROOT/'tests/verify_unity.py').read_text(encoding='utf-8')
        for number in range(1,11):self.assertIn('PC'+str(number).zfill(3), workflow)
        self.assertIn('WriteUnityCases.csproj',workflow)
        for number in ('WU011','WU012'):self.assertIn(number,workflow)
        self.assertIn("range(1,11)",unity)

    def test_VP011_ci_accepts_one_executed_catalog_test_not_zero(self):
        import ast,re,textwrap
        from types import SimpleNamespace
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        step=workflow.split('      - name: Real Windows owned handoff pipes and editor delivery contracts\n',1)[1].split('      - name:',1)[0]
        code=textwrap.dedent(step.split('        run: |\n',1)[1])
        assignments=[node for node in ast.walk(ast.parse(code)) if isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='passed' for t in node.targets)]
        self.assertEqual(len(assignments),1)
        for count in (0,1,2):
            env={'re':re,'ids':['OC001'],'expected':['OC001'],
                'run':SimpleNamespace(returncode=0,stdout='',stderr=f'Ran {count} test'+('s' if count!=1 else '')+' in 0.1s\nOK\n')}
            exec(compile(ast.Module(body=assignments,type_ignores=[]),'exact-ci-result-check','exec'),env)
            self.assertEqual(bool(env['passed']),count==1)

    def test_VP010_ci_executes_catalog_and_freezes_inventory(self):
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        self.assertGreaterEqual(workflow.count('tests/test_operation_catalog.py'),3)
        self.assertIn("['OC001']", workflow)
        self.assertGreaterEqual(workflow.count("'Candidate~/catalog'"),2)
        unity=(ROOT/'tests/verify_unity.py').read_text(encoding='utf-8')
        self.assertIn("{f'UA{i:03d}' for i in range(1, 12)}", unity)

    def test_VP007_compiled_peer_separates_boot_from_request_deadline(self):
        source=(ROOT/'tests/unity-core/WirePeer.cs').read_text(encoding='utf-8')
        self.assertTrue('fixture_started' in source,'peer startup handshake missing')
        python=(ROOT/'tests/test_client_binding.py').read_text(encoding='utf-8')
        self.assertTrue("process.stdout.readline(), START_TIMEOUT" in python,'startup must use bounded owner startup budget')
        self.assertTrue("process.stdout.readline(), 3" in python,'per-request 3s bound must stay unchanged')

    def test_VP005_ci_auth_count_tracks_actual_frozen_methods(self):
        import ast, textwrap
        source=ROOT/'tests/test_runtime_auth.py'
        methods=[node.name+'.'+method.name for node in ast.parse(source.read_text(encoding='utf-8')).body
            if isinstance(node,ast.ClassDef) for method in node.body
            if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)) and method.name.startswith('test_')]
        workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        step=workflow.split('      - name: Actual authenticated probe and client separation\n',1)[1].split('      - name:',1)[0]
        code=textwrap.dedent(step.split('        run: |\n',1)[1])
        checks=[node for node in ast.parse(code).body if isinstance(node,ast.Assert)
            and 'len(methods)' in ast.unparse(node.test)]
        self.assertEqual(len(checks),1)
        self.assertTrue(methods)
        exec(compile(ast.Module(body=checks,type_ignores=[]),'ci-auth-count','exec'),{'methods':methods})

    def test_VP004_compile_timeout_preserves_partial_output_and_error(self):
        m = driver()
        self.assertTrue(hasattr(m, 'compile_fixture'), 'bounded build evidence missing')
        report = {'passed': False}
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            m.compile_fixture([m.sys.executable, '-I', '-B', '-c',
                'import time; print("fixture-build-started", flush=True); time.sleep(10)'],
                dict(os.environ), report, timeout=0.5)
        self.assertFalse(report['passed'])
        self.assertTrue(report['csharp_build']['timed_out'])
        self.assertIn('fixture-build-started', report['csharp_build']['stdout'])
        self.assertIsNone(report['csharp_build']['code'])

    def test_VP001_nuget_system_paths_are_build_only(self):
        m = driver()
        self.assertTrue(hasattr(m, 'compile_environment'), 'NuGet environment helper missing')
        runtime = {'HOME': '/owned', 'USERPROFILE': '/owned', 'PATH': '/system'}
        fixed = dict(runtime)
        additions = {'ProgramFiles': 'C:/Program Files', 'ProgramFiles(x86)': 'C:/Program Files (x86)', 'ProgramData': 'C:/ProgramData'}
        with patch.object(m.sys, 'platform', 'win32'), patch.dict(os.environ, {**additions, 'GH_TOKEN':'fixture-secret', 'HTTPS_PROXY':'fixture-proxy', 'APPDATA':'C:/private/roaming', 'LOCALAPPDATA':'C:/private/local'}, clear=True):
            actual = m.compile_environment(runtime)
        owned_appdata = {'APPDATA': str(Path(runtime['USERPROFILE'])/'AppData/Roaming'), 'LOCALAPPDATA': str(Path(runtime['USERPROFILE'])/'AppData/Local')}
        self.assertEqual(actual, {**runtime, **additions, **owned_appdata})
        self.assertEqual(runtime, fixed)
        with patch.object(m.sys, 'platform', 'linux'):
            self.assertEqual(m.compile_environment(runtime), runtime)

    def test_VP002_failure_records_cleanup_and_propagates(self):
        m = driver()
        self.assertTrue(hasattr(m, 'recorded_directory'), 'post-cleanup evidence helper missing')
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'report.json'
            report = {'passed':False, 'failure_marker':'fixture'}
            with self.assertRaisesRegex(RuntimeError, 'original_failure'):
                with m.recorded_directory(report, output) as work:
                    (work/'fixture').write_bytes(b'not-runtime')
                    raise RuntimeError('original_failure')
            observed = json.loads(output.read_bytes())
            self.assertFalse(observed['passed'])
            self.assertEqual(observed['failure_marker'], 'fixture')
            self.assertTrue(observed['temporary_root_absent'])
            self.assertFalse(Path(observed['temporary_root']).exists())

    def test_VP003_success_records_cleanup_after_exit(self):
        m = driver()
        self.assertTrue(hasattr(m, 'recorded_directory'), 'post-cleanup evidence helper missing')
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'report.json'; report = {'passed':False}
            with m.recorded_directory(report, output) as work:
                self.assertTrue(work.is_dir())
                self.assertFalse(output.exists())
                report['passed'] = True
            self.assertTrue(json.loads(output.read_bytes())['temporary_root_absent'])


if __name__ == '__main__': unittest.main(verbosity=2)
