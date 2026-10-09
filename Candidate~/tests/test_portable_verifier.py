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
    def test_VP023_handoff_suite_inventory_and_explicit_utf8(self):
        import ast
        tree=workflow_step('Real Windows owned handoff pipes and editor delivery contracts')

        assignment=next(n for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='suites' for t in n.targets))
        namespace={};exec(compile(ast.Module(body=[assignment],type_ignores=[]),'ci-suite-declarations','exec'),namespace)
        for path,expected in namespace['suites']:
            source=ast.parse((ROOT.parent/path).read_bytes())
            actual=sorted(m.name.split('_')[1] for cls in source.body if isinstance(cls,ast.ClassDef)
                for m in cls.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test_'))
            self.assertEqual(sorted(expected),actual,path)
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='subprocess.run')
        assert isinstance(call.args[0],ast.List)
        values=[n.value for n in call.args[0].elts if isinstance(n,ast.Constant)]
        self.assertIn('utf8',values)
        self.assertIn('-X',values)
        self.assertEqual(next(ast.literal_eval(k.value) for k in call.keywords if k.arg=='encoding'),'utf-8')

    def test_VP022_windows_suite_inventory_matches_current_tests(self):
        import ast, re
        flow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        for filename, marker, prefix in (
                ('test_owned_launcher.py','Owned launcher suite incomplete','BL'),
                ('test_editor_owner.py','Editor owner tests incomplete or warning','EB')):
            with self.subTest(filename=filename):
                tree=ast.parse((ROOT/'tests'/filename).read_bytes())
                ids=sorted(m.name.split('_')[1] for cls in tree.body if isinstance(cls,ast.ClassDef)
                    for m in cls.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test_'+prefix))
                predicate=next(line for line in flow.splitlines() if marker in line)
                self.assertEqual(re.findall(r"Ran (\d+) tests",predicate),[str(len(ids))])
                if prefix=='BL':
                    declared=re.search(r"-ne '(BL[0-9,BL]+)'",predicate)
                    assert declared is not None
                    self.assertEqual(declared.group(1).split(','),ids)

    def test_VP021_workflow_runs_and_checks_reload_group(self):
        import ast, copy
        self.assertIn('      - name: Local reload grant transfer (net8, not authenticated reattach)\n',(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8'),'missing reload CI step')
        tree=workflow_step('Local reload grant transfer (net8, not authenticated reattach)')
        self.assertTrue(any(isinstance(n,ast.Constant) and n.value=='tests/unity-core/ReloadCases.csproj' for n in ast.walk(tree)))
        checks=[n for n in ast.walk(tree) if isinstance(n,ast.Assert) and "report['ids']" in ast.unparse(n)]
        self.assertEqual(len(checks),1)
        code=compile(ast.Module(body=checks,type_ignores=[]),'ci-reload-predicate','exec')
        ids=[f'RH{i:03d}' for i in range(1,10)]
        for fault,got,exit_code in [('complete',ids,0),('missing',ids[:-1],0),('duplicate',ids+[ids[0]],0),('zero',[],0),('extra',ids+['RH999'],0),('exit',ids,1)]:
            env={'report':{'ids':got,'exit_code':exit_code}}
            with self.subTest(fault=fault):
                if fault=='complete':exec(code,env)
                else:
                    with self.assertRaises(AssertionError):exec(code,env)
        flow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        for name in ('ReloadCases.cs','ReloadCases.csproj'):
            self.assertEqual(flow.count("'Candidate~/tests/unity-core/"+name+"'"),3,'trigger and before/after hash lists')

    def test_VP020_reload_group_is_executed_exact_and_consumed(self):
        import ast, copy
        spec=importlib.util.spec_from_file_location('unity_reload_verifier',ROOT/'tests/verify_unity.py')
        assert spec is not None and spec.loader is not None
        unity=importlib.util.module_from_spec(spec);spec.loader.exec_module(unity)
        self.assertTrue(callable(getattr(unity,'reload_result',None)), 'reload result gate missing')
        tree=ast.parse((ROOT/'tests/verify_unity.py').read_text(encoding='utf-8'))
        loops=[n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.iter,ast.Tuple)
            and any(isinstance(v,ast.Constant) and v.value=='CoreTests' for v in n.iter.elts)]
        self.assertIn('ReloadCases',ast.literal_eval(loops[0].iter))
        row={'exit_code':0,'stdout':'','stderr':'','timeout':False,'process_group_absent':True,'pid_absent':True}
        ids=[f'RH{i:03d}' for i in range(1,10)]
        good={'runs':[{**row,'name':'ReloadCases-build'},
            {**row,'name':'ReloadCases','stdout':''.join('PASS '+i+' case\n' for i in ids)}],
            'owned_build_directory_removed':True}
        for fault in ('none','missing','duplicate','extra','zero','exit','build_exit','warning','timeout','pid','group','directory','no_build','no_tests'):
            report=copy.deepcopy(good);test=report['runs'][1]
            if fault in ('missing','duplicate','extra','zero'):
                selected={'missing':ids[:-1],'duplicate':ids+[ids[0]],'extra':ids+['RH999'],'zero':[]}[fault]
                test['stdout']=''.join('PASS '+i+' case\n' for i in selected)
            if fault=='exit':test['exit_code']=1
            if fault=='build_exit':report['runs'][0]['exit_code']=1
            if fault=='warning':test['stdout']+='warning CS0649: case\n'
            if fault=='timeout':test['timeout']=True
            if fault=='pid':test['pid_absent']=False
            if fault=='group':test['process_group_absent']=False
            if fault=='directory':report['owned_build_directory_removed']=False
            if fault=='no_build':report['runs']=report['runs'][1:]
            if fault=='no_tests':report['runs']=report['runs'][:1]
            with self.subTest(fault=fault):self.assertEqual(unity.reload_result(report)['passed'],fault=='none')
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        verdict=next(n.value for n in main.body if isinstance(n,ast.Return))
        values={name:True for name in ('all_commands_succeeded','source_unchanged','expected_ids_match','owned_build_directory_removed','clean_warning_free_run','client_binding_ids_match','console_ids_match','scene_ids_match')}
        values['write_unity']={'passed':True}
        values['source_reads']={'passed':True}
        for passed in (False,True):
            values['reload']={'passed':passed}
            self.assertEqual(eval(compile(ast.Expression(verdict),'reload-verdict','eval'),{'report':values}),0 if passed else 1)

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
        complete=[f'WU{i:03d}' for i in range(1,14)]
        for label,ids,exit_code in [('complete',complete,0),('zero',[],0),('missing',complete[:-1],0),
                ('duplicate',complete+[complete[0]],0),('replacement',complete[:-1]+[complete[0]],0),
                ('extra',complete+['WU014'],0),('nonzero_exit',complete,1)]:
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
        complete=[f'WU{i:03d}' for i in range(1,14)]
        row={'exit_code':0,'stdout':'','stderr':'','timeout':False,'process_group_absent':True,'pid_absent':True}
        good={'runs':[{**row,'name':'WriteUnityCases-build'},
            {**row,'name':'WriteUnityCases','stdout':''.join('PASS '+i+' fixture\n' for i in complete)}],
            'owned_build_directory_removed':True,'pass_ids':['UC001']}
        for variant in ('complete','zero','missing','duplicate','extra','build_failed','exit_failed',
                'stdout_warning','stderr_warning','compiler_warning','timeout','process_left','pid_left','directory_left','missing_build','missing_run'):
            report=copy.deepcopy(good)
            result=report['runs'][1]
            if variant in ('zero','missing','duplicate','extra'):
                ids={'zero':[],'missing':complete[:-1],'duplicate':complete+[complete[0]],'extra':complete+['WU014']}[variant]
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
                    self.assertEqual(observed['unique_pass_count'],13)
        # The actual main verdict must consume this group, not merely report it.
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        returns=[n for n in main.body if isinstance(n,ast.Return)]
        self.assertEqual(len(returns),1)
        assert returns[0].value is not None
        report: dict={name:True for name in ('all_commands_succeeded','source_unchanged','expected_ids_match',
            'owned_build_directory_removed','clean_warning_free_run','client_binding_ids_match','console_ids_match','scene_ids_match')}
        for passed in (True,False):
            report['write_unity']={'passed':passed}
            report['reload']={'passed':True}
            report['source_reads']={'passed':True}
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
        expected={f'RT{i:03d}' for i in range(15,43)}
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
                    'source_native':{'exit_code':0,'ids':[f'ST{i:03d}' for i in range(1,12)]},
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
        import ast
        expected=[f'PC{i:03d}' for i in range(1,15)]
        for identifier in expected:self.assertIn(identifier,workflow)
        self.assertIn('WriteUnityCases.csproj',workflow)
        for number in ('WU011','WU012'):self.assertIn(number,workflow)
        checks=[n for n in ast.walk(ast.parse(unity)) if isinstance(n,ast.Assert)
                and "report['continuity_pass_ids']" in ast.unparse(n.test)]
        self.assertEqual(len(checks),1)
        gate=compile(ast.Module(body=checks,type_ignores=[]),'actual-continuity-gate','exec')
        exec(gate,{'report':{'continuity_pass_ids':expected}})
        for invalid in [[],expected+['PC015'],expected+[expected[0]]]+[expected[:i]+expected[i+1:] for i in range(len(expected))]:
            with self.assertRaises(AssertionError):exec(gate,{'report':{'continuity_pass_ids':invalid}})

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
        self.assertIn("['OC001','OC002','OC003']", workflow)
        self.assertGreaterEqual(workflow.count("'Candidate~/catalog'"),2)
        unity=(ROOT/'tests/verify_unity.py').read_text(encoding='utf-8')
        # UA012/UA013 cover the new find scope and UI gate, not optional IDs.
        self.assertIn("{f'UA{i:03d}' for i in range(1, 22)}", unity)
        adapter=(ROOT/'tests/unity-core/AdapterCases.cs').read_text(encoding='utf-8')
        for identifier in ('UA012','UA013','UA014','UA015','UA016','UA017','UA018','UA019','UA020','UA021'):
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

    def test_VP022_handoff_ci_exact_method_gate_rejects_false_green(self):
        import ast
        flow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        name='Authenticated reload handoff isolated methods'
        self.assertIn('      - name: '+name+'\n',flow,'handoff tests are not executed by CI')
        tree=workflow_step(name)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='case_passed')
        ns={'re':__import__('re')};exec(compile(ast.Module(body=[fn],type_ignores=[]),'handoff-gate','exec'),ns)
        method='RuntimeHandoffTests.test_HF001_example'
        row={'exit_code':0,'timed_out':False,'stdout':'','stderr':'test_HF001_example (fixture.RuntimeHandoffTests.test_HF001_example) ... ok\n\nRan 1 test in 0.1s\n\nOK\n'}
        self.assertTrue(ns['case_passed'](row,method))
        for change in ({'exit_code':1},{'timed_out':True},{'stderr':''},{'stderr':row['stderr'].replace('Ran 1','Ran 0')},
                       {'stderr':row['stderr'].replace('test_HF001','test_HF002')},{'stderr':row['stderr']*2},
                       {'stdout':'ResourceWarning: leaked handle'},{'stderr':row['stderr']+'skipped=1'}):
            self.assertFalse(ns['case_passed']({**row,**change},method),change)
        self.assertIn('test_runtime_handoff.py',ast.unparse(tree))

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


    def test_VP023_peer_verifier_rejects_missing_duplicate_skipped_and_leaked_runs(self):
        import copy
        path=ROOT/'tests/verify_peer.py'
        self.assertTrue(path.is_file(),'bounded peer verification missing')
        spec=importlib.util.spec_from_file_location('peer_verifier',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        methods=['runtime_fix_tests.PeerIdentityTests.test_PI001_fixture','runtime_fix_tests.PeerIdentityTests.test_PI002_fixture']
        good={'exit_code':0,'timed_out':False,'natural_tree_exit':True,'cleanup_complete':True,
            'temporary_home_absent':True,'stdout':'','stderr':'','result':{'ids':methods,'tests':2,'skipped':[],'failures':[],'errors':[]}}
        for fault in ('complete','missing','duplicate','zero','extra','count','skip','fail','error','exit','timeout','tree','cleanup','home','warning'):
            row=copy.deepcopy(good);result=row['result']
            if fault=='missing':result['ids']=methods[:-1]
            if fault=='duplicate':result['ids']=methods+[methods[0]]
            if fault=='zero':result['ids']=[];result['tests']=0
            if fault=='extra':result['ids']=methods+['runtime_fix_tests.Foreign.test_PI999_fixture']
            if fault=='count':result['tests']=3
            if fault=='skip':result['skipped']=[(methods[0],'not available')]
            if fault=='fail':result['failures']=[methods[0]]
            if fault=='error':result['errors']=[methods[0]]
            if fault=='exit':row['exit_code']=1
            if fault=='timeout':row['timed_out']=True
            if fault=='tree':row['natural_tree_exit']=False
            if fault=='cleanup':row['cleanup_complete']=False
            if fault=='home':row['temporary_home_absent']=False
            if fault=='warning':row['stderr']='ResourceWarning: leaked stream'
            with self.subTest(fault=fault):self.assertEqual(module.case_passed(row,methods),fault=='complete')

    def test_VP024_peer_ci_invocation_receipt_and_byte_freeze_are_consumed(self):
        import ast,copy
        flow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        name='Held OS peers and private byte channels (not Editor reload)'
        self.assertIn('      - name: '+name+'\n',flow,'peer channel CI missing')
        tree=workflow_step(name)
        constants={node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
        self.assertIn('tests/verify_peer.py',constants)
        self.assertIn('peer-checked-ci-peer.json',constants)
        for path in ('launcher/peer_identity.py','launcher/peer_channel.py','tests/test_peer_identity.py','tests/test_peer_channel.py','tests/verify_peer.py'):
            self.assertEqual(flow.count("'Candidate~/"+path+"'"),3,'trigger and both source hash lists')
        checks=[node for node in ast.walk(tree) if isinstance(node,ast.Assert) and "report['passed']" in ast.unparse(node)]
        self.assertEqual(len(checks),1)
        code=compile(ast.Module(body=checks,type_ignores=[]),'peer-ci-consumption','exec')
        from types import SimpleNamespace
        base={'passed':True,'platform':'win32','source_before':{'a':'b'},'source_after':{'a':'b'}}
        for fault in ('none','failed','exit','kernel','drift'):
            report=copy.deepcopy(base)
            if fault=='failed':report['passed']=False
            if fault=='kernel':report['platform']='linux'
            if fault=='drift':report['source_after']={'a':'c'}
            env={'report':report,'sys':SimpleNamespace(platform='win32'),'result':SimpleNamespace(returncode=1 if fault=='exit' else 0)}
            with self.subTest(fault=fault):
                if fault=='none':exec(code,env)
                else:
                    with self.assertRaises(AssertionError):exec(code,env)

    def test_VP025_owner_control_methods_are_isolated_and_ci_consumed(self):
        import ast,importlib.util
        path=ROOT/'tests/verify_peer.py'
        spec=importlib.util.spec_from_file_location('peer_owner_verifier',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.SUITES.get('test_reload_control.py'),('OC',15),'owner control regression absent')
        tree=ast.parse(path.read_bytes())
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='run_case']
        self.assertEqual(len(calls),1)
        self.assertTrue(any(k.arg=='filters' for k in calls[0].keywords),'SDK tests must run individually')
        self.assertIn('tests/test_reload_control.py',module.SOURCES)
        for file in ('runtime/reload_control.py','launcher/reload_owner.py','runtime/__main__.py',
            'launcher/owned_run.py','runtime/owned_probe.py','runtime/unity_ingress.py'):
            self.assertIn(file,module.SOURCES)
        flow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        for file in ('runtime/reload_control.py','launcher/reload_owner.py','tests/test_reload_control.py'):
            self.assertEqual(flow.count("'Candidate~/"+file+"'"),3,'trigger and both frozen hash lists')

    def test_VP026_compiled_wire_verifier_exact_sets_and_ci_consumption(self):
        import ast,copy,importlib.util,textwrap
        path=ROOT/'tests/verify_editor_wire.py'
        self.assertTrue(path.is_file(),'compiled wire verifier missing')
        spec=importlib.util.spec_from_file_location('compiled_wire_verifier',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.SUITES,{'rw':('test_reload_wire.py','WirePeer','RW',3),'ep':('test_editor_peer.py','EditorPeerCases','EP',6),'ce':('test_editor_control.py','EditorBootstrapCases','CE',4),'er':('test_editor_reload.py','WirePeer','ER',5),'ec':('test_editor_orchestration.py','WriteUnityCases','EC',7)})
        for suite,(_,_,prefix,count) in module.SUITES.items():
            methods=module.select_methods(suite,())
            self.assertEqual(sorted(m.split('.test_')[1].split('_')[0] for m in methods),[f'{prefix}{i:03}' for i in range(1,count+1)])
            with self.assertRaises(ValueError):module.select_methods(suite,('MISSING',))
            with self.assertRaises(ValueError):module.select_methods(suite,(prefix+'001',prefix+'001'))
        flow=(ROOT.parent/'.github/workflows/candidate-dependencies.yml').read_text(encoding='utf-8')
        block=flow.split('      - name: Compiled reload bytes and CSharp OS peer channel',1)[1].split('      - name:',1)[0]
        body=block.split('run: |',1)[1];tree=ast.parse(textwrap.dedent(body))
        constants={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertIn('tests/verify_editor_wire.py',constants)
        self.assertTrue({'rw','ep','ce','er','ec'}.issubset(constants))
        checks=[n for n in ast.walk(tree) if isinstance(n,ast.Assert) and "report['passed']" in ast.unparse(n)]
        self.assertEqual(len(checks),1)
        code=compile(ast.Module(body=checks,type_ignores=[]),'compiled-wire-ci','exec')
        from types import SimpleNamespace
        good={'passed':True,'full_suite':True,'platform':'win32','source_before':{'a':'b'},'source_after':{'a':'b'}}
        for fault in ('none','failed','partial','kernel','drift','exit'):
            report=copy.deepcopy(good)
            if fault=='failed':report['passed']=False
            if fault=='partial':report['full_suite']=False
            if fault=='kernel':report['platform']='linux'
            if fault=='drift':report['source_after']={'a':'c'}
            env={'report':report,'sys':SimpleNamespace(platform='win32'),'result':SimpleNamespace(returncode=1 if fault=='exit' else 0)}
            if fault=='none':exec(code,env)
            else:
                with self.assertRaises(AssertionError):exec(code,env)
        for name in ('tests/verify_editor_wire.py','tests/test_reload_wire.py','tests/test_editor_peer.py',
            'package/Editor/EditorPeerChannel.cs','tests/unity-core/EditorPeerCases.cs',
            'tests/unity-core/EditorPeerCases.csproj','tests/unity-core/EditorPeerNetStandard.csproj',
            'tests/test_editor_control.py','tests/test_editor_reload.py','tests/test_editor_orchestration.py',
            'tests/unity-core/EditorOrchestrationCases.cs','tests/unity-core/EditorRestoreCases.cs','package/Editor/CandidateReload.cs'):
            self.assertEqual(flow.count("'Candidate~/"+name+"'"),3,'trigger + both source hash lists')

    def test_VP027_compiled_wire_receipt_rejects_exception_and_missing_results(self):
        import ast,copy
        tree=ast.parse((ROOT/'tests/verify_editor_wire.py').read_bytes())
        assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(ast.unparse(t)=="report['passed']" for t in n.targets)]
        self.assertEqual(len(assignments),1)
        code=compile(ast.Module(body=assignments,type_ignores=[]),'compiled-wire-verdict','exec')
        base={'build_passed':True,'build_root_absent':True,'dll_unchanged':True,'source_unchanged':True,'rows':[{'passed':True}]}
        for fault in ('none','exception','build_passed','build_root_absent','dll_unchanged','source_unchanged','missing','failed'):
            report=copy.deepcopy(base)
            if fault=='exception':report['error_type']='RuntimeError'
            elif fault in base and fault!='rows':report[fault]=False
            elif fault=='missing':report['rows']=[]
            elif fault=='failed':report['rows'][0]['passed']=False
            exec(code,{'report':report,'expected':['method']})
            self.assertEqual(report['passed'],fault=='none',fault)

    def test_VP028_editor_orchestration_response_is_pinned(self):
        import io
        spec=importlib.util.spec_from_file_location('editor_wire_response',ROOT/'tests/verify_editor_wire.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(callable(getattr(module,'response_source',None)),'portable pinned Response input missing')
        with tempfile.TemporaryDirectory(prefix='editor-response-fixture-') as td:
            upstream=module.response_source(Path(td)).read_bytes()
            destination=module.response_source(Path(td),lambda url,timeout:io.BytesIO(upstream))
            self.assertEqual(destination.read_bytes(),upstream)
            for invalid in (b'',upstream+b'changed'):
                with self.assertRaises(ValueError):module.response_source(Path(td),lambda url,timeout:io.BytesIO(invalid))

    def test_VP029_source_read_exact_ids_cleanup_and_warning_gate(self):
        import copy
        spec=importlib.util.spec_from_file_location('unity_source_verifier',ROOT/'tests/verify_unity.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        row={'exit_code':0,'timeout':False,'process_group_absent':True,'pid_absent':True,'stderr':''}
        base={'owned_build_directory_removed':True,'runs':[
            dict(row,name='SourceReadCases-build',stdout=''),
            dict(row,name='SourceReadCases',stdout=''.join(f'PASS ST{i:03d} case\n' for i in range(1,12)))]}
        self.assertTrue(module.compiled_group_result(base,'SourceReadCases','ST',11)['passed'])
        for fault in ('missing','duplicate','extra','warning','cleanup','exit'):
            value=copy.deepcopy(base)
            if fault=='missing':value['runs'][1]['stdout']=value['runs'][1]['stdout'].replace('PASS ST009 case\n','')
            elif fault=='duplicate':value['runs'][1]['stdout']+='PASS ST009 case\n'
            elif fault=='extra':value['runs'][1]['stdout']+='PASS ST012 case\n'
            elif fault=='warning':value['runs'][0]['stderr']='warning CS0001: fixture'
            elif fault=='cleanup':value['owned_build_directory_removed']=False
            elif fault=='exit':value['runs'][1]['exit_code']=1
            self.assertFalse(module.compiled_group_result(value,'SourceReadCases','ST',11)['passed'],fault)

    def test_VP030_actual_source_verdict_requires_clip_read_ids(self):
        import importlib.util, ast, copy
        path=ROOT/'tests/verify_unity.py'
        spec=importlib.util.spec_from_file_location('clip_verifier_contract',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        tree=ast.parse(path.read_text(encoding='utf-8'))
        expressions=[n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Subscript) and isinstance(x.slice,ast.Constant) and x.slice.value=='source_reads' for x in n.targets)]
        self.assertEqual(len(expressions),1)
        row={'exit_code':0,'timeout':False,'process_group_absent':True,'pid_absent':True,'stdout':'','stderr':''}
        base={'owned_build_directory_removed':True,'runs':[dict(row,name='SourceReadCases-build'),dict(row,name='SourceReadCases',stdout=''.join(f'PASS ST{i:03d} case\n' for i in range(1,12)))]}
        predicate=compile(ast.Expression(expressions[0]),'actual-source-verdict','eval')
        self.assertTrue(eval(predicate,{'report':base,'compiled_group_result':module.compiled_group_result})['passed'])
        for ident in ('ST008','ST009','ST010','ST011'):
            value=copy.deepcopy(base);value['runs'][1]['stdout']=value['runs'][1]['stdout'].replace(f'PASS {ident} case\n','')
            self.assertFalse(eval(predicate,{'report':value,'compiled_group_result':module.compiled_group_result})['passed'])

if __name__ == '__main__': unittest.main(verbosity=2)
