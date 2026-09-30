"""Exact paused-response classification; real native pause integration is separate."""
import copy
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'runtime'),str(ROOT/'native/src')]
from candidate_runtime import Runtime, Invocation, Plan, _CURRENT
from material_runtime import MaterialPlan

class PauseResponseTests(unittest.TestCase):
    def context(self, material=False):
        runtime=Runtime('project-A')
        plan=(MaterialPlan('task-A','connection-A',time.monotonic()+60,{},'plan-A') if material
              else Plan('task-A','connection-A',time.monotonic()+60,frozenset(),frozenset(),'plan-A'))
        invocation=Invocation(runtime,'client-A','material_execute' if material else 'manage_material',{},plan)
        (runtime.material.plans if material else runtime.plans)['client-A']=plan
        result={'success':False,'error':'plan_paused','data':{'status':'paused','reason':'plan_paused','plan_id':'plan-A'}}
        return runtime,invocation,result

    def test_PR001_exact_pause_is_not_success_but_keeps_the_current_plan(self):
        runtime,invocation,result=self.context()
        self.assertTrue(runtime.paused_response(invocation,result))
        token=_CURRENT.set(invocation)
        try:runtime.command_failed(result)
        finally:_CURRENT.reset(token)
        self.assertIs(runtime.plans['client-A'],invocation.plan)
        self.assertIsNone(invocation.revoked_plan)
        self.assertIs(result['success'],False)

    def test_PR002_malformed_pauses_still_revoke_on_failure(self):
        variants=[None,{}, {'success':True}, {'success':False,'error':'plan_paused'},
                  {'success':False,'error':'native_read_failed','data':{'status':'paused','reason':'plan_paused','plan_id':'plan-A'}}]
        _,_,base=self.context()
        for key,value in [('status','stopped'),('reason','other'),('plan_id','plan-B'),('extra',True)]:
            result=copy.deepcopy(base);result['data'][key]=value;variants.append(result)
        for result in variants:
            runtime,invocation,_=self.context()
            self.assertFalse(runtime.paused_response(invocation,result))
            token=_CURRENT.set(invocation)
            try:runtime.command_failed(result)
            finally:_CURRENT.reset(token)
            self.assertNotIn('client-A',runtime.plans)
            self.assertIs(invocation.revoked_plan,invocation.plan)

    def test_PR003_pause_never_restores_expired_replaced_or_cancelled_mapping(self):
        for change in ('expired','replaced','removed','cancelled','inactive'):
            runtime,invocation,result=self.context()
            if change=='expired':object.__setattr__(invocation.plan,'expires_at',time.monotonic()-1)
            if change=='replaced':runtime.plans['client-A']=object()
            if change=='removed':runtime.plans.pop('client-A')
            if change=='cancelled':invocation.cancelled=True
            if change=='inactive':invocation.active=False
            self.assertFalse(runtime.paused_response(invocation,result),change)

    def test_PR004_material_pause_requires_the_material_mapping(self):
        runtime,invocation,result=self.context(True)
        self.assertTrue(runtime.paused_response(invocation,result))
        runtime.material.plans.pop('client-A');runtime.plans['client-A']=invocation.plan
        self.assertFalse(runtime.paused_response(invocation,result))

    def test_PR005_local_window_has_pause_and_exact_revalidation_controls(self):
        for path,prefix in [('package/Editor/CandidateWindow.cs','gate'),('package/Editor/MaterialCandidateSession.cs','Gate')]:
            source=(ROOT/path).read_text(encoding='utf-8')
            self.assertIn(prefix+'.Pause((string)plan["plan_id"], (string)plan["digest"])',source)
            self.assertIn(prefix+'.Resume((string)plan["plan_id"], (string)plan["digest"])',source)
            self.assertIn('暂停',source);self.assertIn('核验后继续',source)

if __name__=='__main__':unittest.main(verbosity=2)
