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


def workflow_step(name):
    import ast, textwrap
    workflow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
    step=workflow.split('      - name: '+name+'\n',1)[1].split('      - name:',1)[0]
    return ast.parse(textwrap.dedent(step.split('        run: |\n',1)[1]))


def workflow_native_inputs(work, opener):
    """Execute the real CI download/hash/write statements, not a second list."""
    import ast, hashlib, urllib.request
    tree=workflow_step('Signed client approval identity and compiled gates (not Unity)')
    body=next(n for n in ast.walk(tree) if isinstance(n,ast.With)
        and 'TemporaryDirectory' in ast.unparse(n.items[0].context_expr)).body
    start=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='native' for t in n.targets))
    end=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign)
        and any(ast.unparse(t)=="report['native_source_hashes']" for t in n.targets))
    env={'root':ROOT,'work':work,'report':{},'ast':ast,'hashlib':hashlib,
         'importlib':importlib,'urllib':urllib}
    with patch.object(urllib.request,'urlopen',opener):
        exec(compile(ast.Module(body=body[start:end+1],type_ignores=[]),'ci-native-downloads','exec'),env)
    return env


class PortableVerifierTests(unittest.TestCase):
    def test_VP017_workflow_downloads_verified_native_assembly_closure(self):
        import hashlib, io, urllib.request
        # A supplied pinned snapshot avoids network without faking upstream bytes.
        snapshot=Path(os.environ.get('CANDIDATE_PINNED_EDITOR_ROOT',
            '/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity/Editor'))
        prefix='https://raw.githubusercontent.com/CoplayDev/unity-mcp/30d22075093d1d35dfb0091c1c7550e9ad948577/MCPForUnity/Editor/'
        original=urllib.request.urlopen
        payloads={}
        def fetch(url,timeout):
            self.assertTrue(url.startswith(prefix));self.assertEqual(timeout,30)
            name=url[len(prefix):]
            self.assertNotIn(name,payloads,'duplicate download')
            if snapshot.is_dir():payload=(snapshot/name).read_bytes()
            else:
                with original(url,timeout=timeout) as response:payload=response.read()
            payloads[name]=payload
            return io.BytesIO(payload)
        spec=importlib.util.spec_from_file_location('scene_closure',ROOT/'tests/scene_native_source.py')
        assert spec is not None and spec.loader is not None
        scene=importlib.util.module_from_spec(spec);spec.loader.exec_module(scene)
        with tempfile.TemporaryDirectory(prefix='ci-native-closure-') as td:
            work=Path(td)
            env=workflow_native_inputs(work,fetch)
            native=env['native']
            self.assertEqual(set(payloads),set(env['native_hashes']))
            self.assertEqual({p.relative_to(native).as_posix() for p in native.rglob('*') if p.is_file()},set(payloads))
            self.assertEqual({p:hashlib.sha256(b).hexdigest() for p,b in payloads.items()},env['native_hashes'])
            assembled=scene.assemble(native,work/'ManageScene.cs')
            self.assertTrue(set(assembled['find_native_sha256'])<=set(payloads))
            self.assertTrue((work/'ManageScene.cs.packages.cs').is_file())
            for name in payloads:
                with self.subTest(corrupt_download=name), tempfile.TemporaryDirectory(dir=work) as corrupt:
                    def damaged(url,timeout):
                        key=url[len(prefix):]
                        return io.BytesIO(payloads[key]+(b'corrupt' if key==name else b''))
                    with self.assertRaises(AssertionError):workflow_native_inputs(Path(corrupt),damaged)
        self.assertFalse(Path(td).exists())

    def test_VP019_workflow_write_unity_predicate_is_exact_and_fail_closed(self):
        import ast, re
        from types import SimpleNamespace
        tree=workflow_step('Local task-record UI and reload lifecycle (net8 doubles, not Editor)')
        checks: list[ast.stmt]=[n for n in ast.walk(tree) if isinstance(n,ast.Assert) and "report['ids']" in ast.unparse(n)]
        self.assertTrue(checks)
        code=compile(ast.Module(body=checks,type_ignores=[]),'ci-write-unity-predicate','exec')
        complete=[f'WU{i:03d}' for i in range(1,13)]
        for label,ids,exit_code in [('complete',complete,0),('zero',[],0),('missing',complete[:-1],0),
                ('duplicate',complete+[complete[0]],0),('replacement',complete[:-1]+[complete[0]],0),
                ('extra',complete+['WU013'],0),('nonzero_exit',complete,1)]:
            env={'report':{'ids':ids},'result':SimpleNamespace(returncode=exit_code,stdout='',stderr=''),'re':re}
            with self.subTest(case=label):
                if label=='complete':exec(code,env)
                else:
                    with self.assertRaises(AssertionError):exec(code,env)

    def test_VP018_unity_driver_runs_separate_exact_write_unity_group(self):
        import ast, copy
        spec=importlib.util.spec_from_file_location('unity_verifier',ROOT/'tests/verify_unity.py')
        assert spec is not None and spec.loader is not None
        unity=importlib.util.module_from_spec(spec);spec.loader.exec_module(unity)
        tree=ast.parse((ROOT/'tests/verify_unity.py').read_text(encoding='utf-8'))
        loops=[n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.iter,ast.Tuple)
            and any(isinstance(v,ast.Constant) and v.value=='CoreTests' for v in n.iter.elts)]
        self.assertEqual(len(loops),1)
        self.assertIn('WriteUnityCases',ast.literal_eval(loops[0].iter))
        self.assertTrue(callable(getattr(unity,'write_unity_result',None)))
        complete=[f'WU{i:03d}' for i in range(1,13)]
        row={'exit_code':0,'stdout':'','stderr':'','timeout':False,'process_group_absent':True,'pid_absent':True}
        good={'runs':[{**row,'name':'WriteUnityCases-build'},
            {**row,'name':'WriteUnityCases','stdout':''.join('PASS '+i+' fixture\n' for i in complete)}],
            'owned_build_directory_removed':True,'pass_ids':['UC001']}
        for variant in ('complete','zero','missing','duplicate','extra','build_failed','exit_failed',
                'stdout_warning','stderr_warning','compiler_warning','timeout','process_left','pid_left','directory_left','missing_build','missing_run'):
            report=copy.deepcopy(good)
            result=report['runs'][1]
            if variant in ('zero','missing','duplicate','extra'):
                ids={'zero':[],'missing':complete[:-1],'duplicate':complete+[complete[0]],'extra':complete+['WU013']}[variant]
                result['stdout']=''.join('PASS '+i+' fixture\n' for i in ids)
            elif variant=='build_failed':report['runs'][0]['exit_code']=1
            elif variant=='exit_failed':result['exit_code']=1
            elif variant in ('stdout_warning','stderr_warning'):result[variant.split('_')[0]]+='ResourceWarning: fixture\n'
            elif variant=='compiler_warning':report['runs'][0]['stdout']+='warning CS0000: fixture\n'
            elif variant=='timeout':result['timeout']=True
            elif variant=='process_left':result['process_group_absent']=False
            elif variant=='pid_left':result['pid_absent']=False
            elif variant=='directory_left':report['owned_build_directory_removed']=False
            elif variant=='missing_build':report['runs']=report['runs'][1:]
            elif variant=='missing_run':report['runs']=report['runs'][:1]
            with self.subTest(case=variant):
                observed=unity.write_unity_result(report)
                self.assertEqual(observed['passed'],variant=='complete')
                self.assertEqual(report['pass_ids'],['UC001'],'WU must not change the main group')
                if variant=='complete':
                    self.assertEqual(observed['pass_ids'],complete)
                    self.assertEqual(observed['unique_pass_count'],12)
        # The actual main verdict must consume this group, not merely report it.
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        returns=[n for n in main.body if isinstance(n,ast.Return)]
        self.assertEqual(len(returns),1)
        assert returns[0].value is not None
        report: dict={name:True for name in ('all_commands_succeeded','source_unchanged','expected_ids_match',
            'owned_build_directory_removed','clean_warning_free_run','client_binding_ids_match','console_ids_match','scene_ids_match')}
        for passed in (True,False):
            report['write_unity']={'passed':passed}
            self.assertEqual(eval(compile(ast.Expression(returns[0].value),'unity-verdict','eval'),{'report':report}),0 if passed else 1)

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
        expected={f'RT{i:03d}' for i in range(15,37)}
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
                    'scene_native':{'exit_code':0,'ids':[f'NS{i:03d}' for i in range(1,19)]},
                    'console_runtime':[{'method':m,'passed':True} for m in completed]}
                execute(summaries)
                self.assertEqual(env['report']['passed'],label=='complete')

    def test_VP016_compiled_scene_gates_require_eight_read_combination(self):
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
        complete=[f'NS{i:03d}' for i in range(1,19)]
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
        # UA012/UA013 cover the new find scope and UI gate, not optional IDs.
        self.assertIn("{f'UA{i:03d}' for i in range(1, 21)}", unity)
        adapter=(ROOT/'tests/unity-core/AdapterCases.cs').read_text(encoding='utf-8')
        for identifier in ('UA012','UA013','UA014','UA015','UA016','UA017','UA018','UA019','UA020'):
            self.assertIn('PASS '+identifier+' ',adapter)
        self.assertGreaterEqual(workflow.count('tests/test_native_peer_cleanup.py'),3)
        self.assertIn("['NPC001','NPC002','NPC003','NPC004']",workflow)

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
