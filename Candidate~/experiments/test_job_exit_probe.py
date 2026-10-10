"""Probe control-flow tests, not Windows evidence."""
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace


class JobProbeTests(unittest.TestCase):
    def load(self):
        path=Path(__file__).with_name('job_exit_probe.py')
        self.assertTrue(path.exists(), 'missing bounded observer')
        spec=importlib.util.spec_from_file_location('probe',path)
        assert spec is not None and spec.loader is not None
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_JP001_later_empty_job_does_not_replace_false(self):
        module=self.load();rows=[];snapshots=iter([
            {'accounting':{'ActiveProcesses':1}}, {'accounting':{'ActiveProcesses':0}}])
        calls=[]
        observe=module.observer(lambda owner,child:calls.append('original') or False,
            lambda owner:next(snapshots),rows,sleep=lambda delay:calls.append(delay))
        self.assertIs(observe(object(),SimpleNamespace(pid=123)),False)
        self.assertEqual(calls,['original',.02])
        self.assertIs(rows[0]['original_natural_tree_exit'],False)
        self.assertEqual(len(rows[0]['snapshots']),2)
        self.assertEqual(rows[0]['snapshots'][-1]['state']['accounting']['ActiveProcesses'],0)

    def test_JP002_success_has_no_extra_observation(self):
        module=self.load();rows=[]
        def forbidden(*args):raise AssertionError('must not query or wait after success')
        observe=module.observer(lambda owner,child:True,forbidden,rows,sleep=forbidden)
        self.assertIs(observe(object(),SimpleNamespace(pid=1)),True)
        self.assertEqual(rows[0]['snapshots'],[])

    def test_JP006_image_queries_recheck_membership_and_close(self):
        module=self.load();events=[]
        self.assertTrue(hasattr(module,'snapshot_images'),'missing safe image observation')
        def query(handle,flags,buffer,size):
            events.append(('query',handle));buffer.value=r'C:\Windows\System32\conhost.exe';return 1
        def membership(job,handle):
            events.append(('member',handle))
            if handle==12:raise OSError('sensitive error')
        api=SimpleNamespace(k=SimpleNamespace(QueryFullProcessImageNameW=query),
            w=SimpleNamespace(OpenProcess=lambda access,inherit,pid:pid+10),assign=membership,
            checked=lambda result:result,close_handle=lambda handle:events.append(('close',handle)))
        state={'members':[{'pid':1,'member_verified':True},{'pid':2,'member_verified':True}]}
        result=module.snapshot_images(SimpleNamespace(api=api,job=99),lambda owner:state)
        self.assertEqual(result['members'][0]['image_basename'],'conhost.exe')
        self.assertEqual(result['members'][1]['image_error_type'],'OSError')
        self.assertNotIn('image_basename',result['members'][1])
        self.assertEqual(events,[('member',11),('query',11),('close',11),('member',12),('close',12)])

    def test_JP005_modes_have_fixed_limits_and_no_unknown_fallback(self):
        module=self.load()
        self.assertTrue(hasattr(module,'probe_plan'),'missing bounded timing mode')
        self.assertEqual(module.probe_plan('baseline'),(64,20,.02))
        self.assertEqual(module.probe_plan('signal-race'),(512,0,0))
        with self.assertRaises(ValueError):module.probe_plan('unbounded')

    def test_JP004_control_keeps_popen_alive_until_abrupt_exit(self):
        import ast
        import inspect
        import sys
        from unittest.mock import patch
        module=self.load();events=[]
        class Child:
            def __init__(self,*args):events.append('spawn')
            def __del__(self):events.append('released')
        class Exit(BaseException):pass
        def exit_now(code):
            events.append('exit');raise Exit()
        expr=next(n.value for n in ast.walk(ast.parse(inspect.getsource(module.main)))
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='code' for t in n.targets))
        code=eval(compile(ast.Expression(expr),'control-code','eval'),
            {'current':lambda:{'executable':'fixture-python'},'seconds':60})
        namespace={}
        with patch.dict(sys.modules,{'os':SimpleNamespace(_exit=exit_now),'subprocess':SimpleNamespace(Popen=Child)}):
            with self.assertRaises(Exit):exec(code,namespace)
        namespace.clear()
        self.assertEqual(events,['spawn','exit','released'])

    def test_JP003_live_or_unavailable_job_has_bounded_observation(self):
        module=self.load()
        for state in ({'accounting':{'ActiveProcesses':1}},{'error_type':'OSError'}):
            with self.subTest(state=state):
                rows=[];waits=[]
                observe=module.observer(lambda owner,child:False,lambda owner:state,rows,sleep=waits.append)
                self.assertIs(observe(object(),SimpleNamespace(pid=123)),False)
                self.assertEqual(len(rows[0]['snapshots']),11)
                self.assertEqual(waits,[.02]*10)


if __name__=='__main__':unittest.main(verbosity=2)
