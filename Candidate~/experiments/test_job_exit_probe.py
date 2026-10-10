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
