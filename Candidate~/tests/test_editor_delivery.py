"""Editor entry orchestration, runtime/SSH doubles; no Unity acceptance."""
import asyncio
import os
from pathlib import Path
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'runtime')]
from launcher import editor_owner,owned_run,hermes_delivery

class EditorDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_ED001_remote_receipt_precedes_runtime_shutdown(self):
        events=[];runtime_stop=[];asked=asyncio.Event();delivered=asyncio.Event()
        identity=SimpleNamespace(clients=('hermes',),expires_at=2000000000,
            credentials={'unity':SimpleNamespace(token='fixture-unity')})
        owned=SimpleNamespace(owner=SimpleNamespace(identity=identity,tls=SimpleNamespace(pin='a'*64)),
            transport_ready=threading.Event(),binding=SimpleNamespace(ready=threading.Event()))
        args=SimpleNamespace(project='fixture-delivery',parent_pid=os.getppid(),client=['hermes'],
            hermes_host='fixture.invalid',hermes_user='fixture',hermes_port=22,hermes_forward_port=18088)
        def supervise(raw,*,owned,stop):
            self.assertNotIn('ssh',raw,'no duplicate tunnel-only SSH')
            runtime_stop.append(stop);owned.transport_ready.set();owned.binding.ready.set()
            stop.wait(8);events.append('runtime-stop')
            return {'phase':'stopped','process_cleanup_complete':True,'probe_cleanup_complete':True,
                    'probe_session_cleanup_confirmed':True}
        async def control(stop,timeout=None):
            if timeout is not None:return b'start\n'
            await asked.wait();return b'stop\n'
        async def deliver(raw,local_run,*,stop,offered):
            self.assertIs(local_run,owned.owner)
            self.assertEqual(raw['ssh']['host'],'fixture.invalid')
            self.assertTrue(owned.binding.ready.is_set())
            events.append('offered');offered.set();delivered.set()
            while not stop.is_set():await asyncio.sleep(.01)
            self.assertFalse(runtime_stop[0].is_set(),'runtime killed before remote DELETE')
            events.append('remote-close')
            return {'code':'STOPPED','process_cleanup_complete':True,'remote_cleanup_confirmed':True}
        def emit(value):
            events.append(value)
            if value['kind']=='ready':asked.set()
        with patch.object(owned_run,'create_owned_run',return_value=owned), \
                patch.object(owned_run,'supervise_owned',supervise), \
                patch.object(editor_owner,'read_control',control), \
                patch.object(editor_owner,'emit',emit), \
                patch.object(hermes_delivery,'deliver',deliver):
            async with asyncio.timeout(10):result=await editor_owner.run(args)
        self.assertTrue(delivered.is_set(),'editor never started selected remote delivery')
        self.assertEqual(result,0)
        self.assertLess(events.index('remote-close'),events.index('runtime-stop'))
        final=events[-1]
        self.assertTrue(final['handoff_cleanup_confirmed'])

    async def test_ED002_explicit_zero_ssh_port_rejected_before_runtime(self):
        args=SimpleNamespace(project='fixture-delivery',parent_pid=os.getppid(),client=['hermes'],
            hermes_host='fixture.invalid',hermes_user='fixture',hermes_port=0,hermes_forward_port=18088)
        async def control(*args,**kwargs):return b'start\n'
        with patch.object(editor_owner,'read_control',control), \
                patch.object(owned_run,'create_owned_run',side_effect=AssertionError('runtime_must_not_start')):
            with self.assertRaises(ValueError):await editor_owner.run(args)

    async def test_ED003_manual_window_wires_structured_remote_fields(self):
        window=(ROOT/'package/Editor/CandidateWindow.cs').read_text(encoding='utf-8')
        session=(ROOT/'package/Editor/CandidateSession.cs').read_text(encoding='utf-8')
        self.assertIn('hermesHost = EditorGUILayout.TextField',window)
        self.assertIn('hermesPort = EditorGUILayout.IntField',window)
        self.assertIn('hermesForwardPort = EditorGUILayout.IntField',window)
        self.assertIn('allowCodex, hermesSsh',window)
        self.assertIn('JObject hermesSsh = null',session)
        self.assertIn('allowCodex, hermesSsh, codexExecutable',session)
        self.assertNotIn('EditorPrefs.Set',window)

    async def test_ED004_local_codex_starts_after_unity_and_closes_before_runtime(self):
        from launcher import codex_local
        events=[];asked=asyncio.Event();runtime_stop=[]
        identity=SimpleNamespace(clients=('codex',),expires_at=2000000000,
            credentials={'unity':SimpleNamespace(token='fixture-unity')})
        owned=SimpleNamespace(owner=SimpleNamespace(identity=identity,tls=SimpleNamespace(pin='a'*64)),
            transport_ready=threading.Event(),binding=SimpleNamespace(ready=threading.Event()))
        args=SimpleNamespace(project='fixture-codex',parent_pid=os.getppid(),client=['codex'],
            codex_executable=sys.executable,codex_project=str(ROOT))
        def supervise(raw,*,owned,stop):
            runtime_stop.append(stop);owned.transport_ready.set();owned.binding.ready.set()
            stop.wait(6);events.append('runtime-stop')
            return {'phase':'stopped','process_cleanup_complete':True,'probe_cleanup_complete':True,
                    'probe_session_cleanup_confirmed':True}
        async def control(stop,timeout=None):
            if timeout is not None:return b'start\n'
            await asked.wait();return b'stop\n'
        async def serve(local_run,executable,project,*,stop,started):
            self.assertIs(local_run,owned.owner);self.assertTrue(owned.binding.ready.is_set())
            self.assertEqual(executable,sys.executable);self.assertEqual(project,str(ROOT))
            events.append('codex-start');started.set()
            while not stop.is_set():await asyncio.sleep(.01)
            self.assertFalse(runtime_stop[0].is_set(),'runtime stopped before client cleanup')
            events.append('codex-stop')
            return {'code':'STOPPED','process_cleanup_complete':True,'profile_cleanup_complete':True}
        def emit(value):
            events.append(value)
            if value['kind']=='ready':asked.set()
        with patch.object(owned_run,'create_owned_run',return_value=owned), \
                patch.object(owned_run,'supervise_owned',supervise), \
                patch.object(editor_owner,'read_control',control), \
                patch.object(editor_owner,'emit',emit), \
                patch.object(codex_local,'serve',serve):
            async with asyncio.timeout(9):result=await editor_owner.run(args)
        self.assertEqual(result,0)
        self.assertIn('codex-start',events,'Editor never launched selected local Codex')
        self.assertLess(events.index('codex-stop'),events.index('runtime-stop'))
        self.assertTrue(events[-1]['codex_cleanup_complete'])

    async def test_ED005_local_codex_ui_requires_explicit_native_path(self):
        window=(ROOT/'package/Editor/CandidateWindow.cs').read_text(encoding='utf-8')
        session=(ROOT/'package/Editor/CandidateSession.cs').read_text(encoding='utf-8')
        self.assertIn('codexExecutable = EditorGUILayout.TextField',window)
        self.assertIn('allowCodex ? codexExecutable : null',window)
        self.assertIn('string codexExecutable = null',session)
        self.assertNotIn('EditorPrefs.Set',window)

if __name__=='__main__':unittest.main()
