"""Replay actual compiled gate receipts through real consumers; Unity APIs are doubles.
Usage: test_compiled_review.py GATE_REPORT MODE [HERMES_ROOT]
"""
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
report_path=Path(sys.argv.pop(1));mode=sys.argv.pop(1)
report=json.loads(report_path.read_text())
assert report['passed'] and report['source_unchanged'] and report['build_root_absent']
for name in ('package/Editor/Core/CandidateGate.cs','tests/unity-core/DiscoveryGateCases.cs'):
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==report['after'][name]
lines=[line for run in report['runs'] for line in run['stdout'].splitlines()]
statuses=[json.loads(line.removeprefix('EFFECT_STATUS ')) for line in lines if line.startswith('EFFECT_STATUS ')]
pauses=[json.loads(line.removeprefix('PAUSE_RECEIPT ')) for line in lines if line.startswith('PAUSE_RECEIPT ')]
assert len(statuses)==4 and len(pauses)==1
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'runtime')]
if mode=='probe':
    from test_owned_launcher import OwnedLauncherTests
    class CompiledProbe(OwnedLauncherTests):
        async def test_RC001_compiled_effect_status_survives_owner_lifecycle(self):
            for status in statuses:
                self.probe_data=status
                result=await self.exercise()
                self.assertEqual(result['code'],'STOPPED',result)
    selected='CompiledProbe.test_RC001_compiled_effect_status_survives_owner_lifecycle'
elif mode=='handoff':
    from unittest.mock import patch
    from hermes_handoff_contracts import HandoffTests,Peer,types
    class CompiledHandoff(HandoffTests):
        async def test_RC002_compiled_effect_status_admitted_without_grant(self):
            for status in statuses:
                async def call(peer,name,arguments):
                    # Runtime adds exact admitted project identity to gate status.
                    return types.CallToolResult(content=[],structuredContent={'success':True,
                        'data':{**status,'project_id':'fixture-project'}})
                with patch.object(Peer,'call_tool',call):
                    async with self.module.Receiver(self.path) as receiver:
                        reader,writer,offered=await self.offer()
                        await receiver.claim(offered['id'],conversation_id='compiled',include=('agent_status',))
                        writer.write(b'stop\n');await writer.drain()
                        self.assertEqual(json.loads(await reader.readline()),{'kind':'closed','clean':True})
    selected='CompiledHandoff.test_RC002_compiled_effect_status_admitted_without_grant'
elif mode=='pause':
    import copy
    from test_runtime_live_effects import RuntimeLiveEffects,CASES
    class CompiledPause(RuntimeLiveEffects):
        async def test_RC003_compiled_pause_preserves_real_sdk_runtime_plan(self):
            await self.ready(CASES[-1])
            runtime=self.server._candidate_runtime
            client,plan=next(iter(runtime.plans.items()))
            receipt=copy.deepcopy(pauses[0]);receipt['data']['plan_id']=plan.plan_id
            self.peer.execute_response=receipt
            result=await self.client.call_tool('get_tests',{'mode':'EditMode'},raise_on_error=False)
            self.assertTrue(result.is_error)
            self.assertIs(runtime.plans[client],plan)
            self.peer.execute_response=None
            result=await self.client.call_tool('get_tests',{'mode':'EditMode'},raise_on_error=False)
            self.assertFalse(result.is_error,str(result))
            self.assertIs(runtime.plans[client],plan)
    selected='CompiledPause.test_RC003_compiled_pause_preserves_real_sdk_runtime_plan'
else:raise ValueError('unknown mode')
unittest.main(argv=[sys.argv[0],selected],verbosity=2)
