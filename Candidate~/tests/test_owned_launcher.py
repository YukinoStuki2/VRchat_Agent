"""Real supervised runtime + SDK; Unity WS messages are explicit doubles."""
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'runtime'),str(ROOT/'dependencies/mcp-1.29.1')]


class OwnedLauncherTests(unittest.IsolatedAsyncioTestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('launcher.owned_run'),'owned launcher missing')
        return importlib.import_module('launcher.owned_run')

    def config(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        return {'project':'fixture-project','local_port':port,'parent_pid':os.getpid()}

    async def run_peer(self,owner,ready,disconnect):
        import websockets
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=owner.tls.certificate.decode())
        url=f'wss://127.0.0.1:{owner.port}/hub/plugin'
        deadline=time.monotonic()+8
        while True:
            try:
                ws=await websockets.connect(url,ssl=context,proxy=None,
                    additional_headers={'Authorization':'Bearer '+owner.identity.credentials['unity'].token})
                break
            except ConnectionRefusedError:
                if time.monotonic()>deadline:raise
                await asyncio.sleep(.05)
        try:
            await ws.recv()
            await ws.send(json.dumps({'type':'register','project_name':'fixture',
                'project_hash':owner.project,'unity_version':'2022.3.22f1'}))
            registered=json.loads(await ws.recv())
            self.assertEqual(registered['type'],'registered')
            while True:
                message=json.loads(await ws.recv())
                if message['type']=='ping':
                    await ws.send(json.dumps({'type':'pong'}));continue
                self.assertEqual(message['name'],'vrchat_agent_dispatch')
                request=message['params']
                self.assertEqual(request['kind'],'status')
                self.assertEqual(request['project_id'],owner.project)
                self.assertEqual(request['connection_id'],registered['session_id'])
                await ws.send(json.dumps({'type':'command_result','id':message['id'],
                    'result':{'status':'success','result':{'success':True,'data':{'read_only':True}}}}))
                ready.set()
                if disconnect:
                    await asyncio.sleep(.3);await ws.close();return
        except websockets.exceptions.ConnectionClosed:
            return
        finally:
            await ws.close()

    async def exercise(self,disconnect=False):
        module=self.module();raw=self.config();owned=module.create_owned_run(raw)
        stop=threading.Event();reports=[];peer_ready=asyncio.Event()
        loop=asyncio.get_running_loop()
        def report(value):
            reports.append(value)
            if value['phase']=='running' and not disconnect:stop.set()
        task=asyncio.create_task(asyncio.to_thread(module.supervise_owned,raw,
            owned=owned,stop=stop,report=report))
        peer=asyncio.create_task(self.run_peer(owned.owner,peer_ready,disconnect))
        try:
            result=await asyncio.wait_for(asyncio.shield(task),16)
            await asyncio.wait_for(peer,3)
        finally:
            stop.set()
            await asyncio.wait_for(task,8)
            if not peer.done():peer.cancel()
            await asyncio.gather(peer,return_exceptions=True)
        self.assertTrue(peer_ready.is_set())
        self.assertTrue(any(x['phase']=='running' for x in reports),reports)
        self.assertTrue(result['process_cleanup_complete'],result)
        self.assertTrue(result['probe_cleanup_complete'],result)
        self.assertFalse(any(t.name.startswith('vrchat-owned-probe-') for t in threading.enumerate()))
        with socket.socket() as sock:self.assertNotEqual(sock.connect_ex(('127.0.0.1',raw['local_port'])),0)
        self.assertNotIn('PRIVATE KEY',repr(result)+repr(reports))
        return result

    async def test_BL001_exact_authenticated_readiness_and_explicit_stop(self):
        result=await self.exercise()
        self.assertEqual(result['code'],'STOPPED',result)
        self.assertTrue(result.get('probe_session_cleanup_confirmed'),result)

    async def test_BL002_unity_disconnect_revokes_running_without_reconnect(self):
        result=await self.exercise(disconnect=True)
        self.assertEqual(result['code'],'BINDING_FAILED',result)


    async def test_BL003_target_cannot_gain_an_unapproved_ssh_forward(self):
        module=self.module();raw=self.config();owned=module.create_owned_run(raw)
        changed={**raw,'ssh':{'host':'fixture.invalid','remote_port':23456}}
        with patch.object(module,'supervise',side_effect=AssertionError('must refuse before any supervisor call')):
            with self.assertRaisesRegex(ValueError,'owned_target_mismatch'):
                module.supervise_owned(changed,owned=owned)

    async def test_BL004_foreign_certificate_rejected_before_sending_a_bearer(self):
        module=self.module();raw=self.config();owned=module.create_owned_run(raw)
        from tls_context import issue_tls_material,load_tls_context
        from owned_probe import observe_runtime
        received=[]
        async def peer(reader,writer):
            try:received.append(await reader.read(16384))
            finally:
                writer.close()
                await writer.wait_closed()
        context=load_tls_context(issue_tls_material())
        server=await asyncio.start_server(peer,'127.0.0.1',raw['local_port'],ssl=context)
        owned.binding.started.set()
        try:
            with self.assertRaises(ssl.SSLCertVerificationError):
                await observe_runtime(owned.owner,owned.binding,startup_timeout=3)
            self.assertFalse(owned.binding.ready.is_set())
            self.assertEqual(received,[])
        finally:
            server.close();await server.wait_closed()

if __name__=='__main__':unittest.main(verbosity=2)
