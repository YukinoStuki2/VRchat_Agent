"""Linux IPC contracts. Real UNIX streams/registry; MCP peer doubles explicit."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HERMES = Path(sys.argv.pop(1)).resolve(strict=True)
sys.path[:0] = [str(HERMES), str(ROOT/'clients'), str(ROOT/'runtime')]
from tools.registry import registry
from model_tools import handle_function_call  # Complete native registration before baseline.
from tls_context import issue_tls_material
from mcp import types


class Peer:
    def __init__(self):
        self.session = self
        self.closed = False
    async def list_tools(self):
        return types.ListToolsResult(tools=[types.Tool(name='agent_status', description='Unity status', inputSchema={'type':'object'})])
    async def call_tool(self, name, arguments):
        return types.CallToolResult(content=[], structuredContent={'success':True,
            'data':{'read_only':True,'project_id':'fixture-project'}})
    async def shutdown(self):
        self.closed = True
        self.session = None


class HandoffTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((ROOT/'clients/hermes_handoff.py').is_file(), 'missing_trusted_local_handoff_receiver')
        self.module = importlib.import_module('hermes_handoff')
        self.home = tempfile.TemporaryDirectory(prefix='vrc-handoff-')
        self.addCleanup(self.home.cleanup)
        self.path = Path(self.home.name)/'receiver.sock'
        tls = issue_tls_material()
        self.doc = {'version':1, 'project':'fixture-project', 'role':'hermes', 'port':18443, 'server_port':18443,
                    'certificate':tls.certificate.decode(), 'pin':tls.pin,
                    'bearer':'fixture-memory-secret', 'expires_at':int(time.time())+60}
        self.peers = []
        async def connect(**kwargs):
            self.assertEqual(kwargs['bearer'], self.doc['bearer'])
            peer = Peer(); self.peers.append(peer); return peer
        self.connector = patch('hermes_connection.connect', connect)
        self.connector.start(); self.addCleanup(self.connector.stop)
        self.baseline = set(registry.get_all_tool_names())
        self.writers = []
    async def asyncTearDown(self):
        for writer in self.writers:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass  # Capacity rejection can reset an unread sender.
        self.assertTrue(all(p.closed for p in self.peers))
        self.assertEqual(set(registry.get_all_tool_names()), self.baseline)
        self.assertFalse(self.path.exists())
    async def offer(self, doc=None):
        reader, writer = await asyncio.open_unix_connection(str(self.path))
        self.writers.append(writer)
        writer.write(json.dumps(self.doc if doc is None else doc).encode()+b'\n'); await writer.drain()
        reply = json.loads(await asyncio.wait_for(reader.readline(),2))
        return reader, writer, reply

    async def test_HD020_effectful_status_can_be_claimed_without_grant(self):
        for effect in ('asset_load_callbacks','prefab_contents_callbacks','test_discovery_callbacks','project_test_job_maintenance'):
            async def status(peer,name,arguments):
                return types.CallToolResult(content=[],structuredContent={'success':True,
                    'data':{'project_id':'fixture-project','read_only':False,effect:True}})
            with self.subTest(effect=effect),patch.object(Peer,'call_tool',status):
                async with self.module.Receiver(self.path) as receiver:
                    reader,writer,offered=await self.offer()
                    binding=await receiver.claim(offered['id'],conversation_id='effects',include=('agent_status',))
                    self.assertEqual(len(binding.snapshot()),1)
                    writer.write(b'stop\n');await writer.drain()
                    self.assertEqual(json.loads(await reader.readline()),{'kind':'closed','clean':True})

    async def test_HD021_frozen_unready_or_malformed_status_denies_claim(self):
        for delta in ({'ready':False},{'status':'planned_reload_frozen'},{'read_only':0}):
            async def status(peer,name,arguments):
                return types.CallToolResult(content=[],structuredContent={'success':True,
                    'data':{'project_id':'fixture-project','read_only':True,**delta}})
            with self.subTest(delta=delta),patch.object(Peer,'call_tool',status):
                async with self.module.Receiver(self.path) as receiver:
                    reader,writer,offered=await self.offer()
                    with self.assertRaisesRegex(RuntimeError,'candidate_claim_failed'):
                        await receiver.claim(offered['id'],conversation_id='invalid',include=('agent_status',))
                    self.assertEqual(set(registry.get_all_tool_names()),self.baseline)

    async def test_HD019_failed_receiver_start_closes_owned_socket(self):
        receiver=self.module.Receiver(self.path)
        try:
            with patch.object(Path,'chmod',side_effect=OSError('fixture chmod failure')):
                with self.assertRaises(OSError):await receiver.__aenter__()
            self.assertFalse(receiver._server.is_serving(),'failed start left a live listener')
            self.assertFalse(self.path.exists(),'failed start left its socket')
        finally:
            await receiver.__aexit__(None,None,None)
            # RED safety cleanup only; never remove a foreign replacement.
            if self.path.exists():self.path.unlink()

    async def test_HD001_private_offer_claim_dispatch_and_source_stop(self):
        from model_tools import handle_function_call
        async with self.module.Receiver(self.path) as receiver:
            reader, writer, accepted = await self.offer()
            self.assertEqual(accepted['kind'], 'offered')
            offer_id = accepted['id']
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(receiver.offers(), [{'id':offer_id, 'project':'fixture-project', 'claimed':False}])
            self.assertNotIn(self.doc['bearer'], repr(receiver)+repr(receiver.offers()))
            binding = await receiver.claim(offer_id, conversation_id='conversation-a', include=('agent_status',))
            name = binding.snapshot()[0]['function']['name']
            result = json.loads(await asyncio.to_thread(handle_function_call, name, {}, session_id='conversation-a', enabled_tools=[name]))
            self.assertNotIn('error',result)
            wrong = json.loads(await asyncio.to_thread(handle_function_call, name, {}, session_id='conversation-b', enabled_tools=[name]))
            self.assertEqual(wrong['error'],'candidate_wrong_conversation')
            writer.write(b'stop\n'); await writer.drain()
            closed = json.loads(await asyncio.wait_for(reader.readline(),2))
            self.assertEqual(closed, {'kind':'closed','clean':True})
            self.assertEqual(receiver.offers(), [])
            self.assertTrue(self.peers[0].closed)
            self.assertEqual(set(registry.get_all_tool_names()), self.baseline)


    async def test_HD002_strict_envelope_rejected_before_offer_or_connect(self):
        # Freeze validation time: a precomputed now+3601 becomes valid if the
        # earlier subcases cross the next second. Do not loosen the real limit.
        with patch('hermes_connection.time.time', return_value=time.time()):
            await self._invalid_envelopes()

    async def _invalid_envelopes(self):
        async with self.module.Receiver(self.path) as receiver:
            invalid = [(key, value) for key, value in [
                ('version', True), ('role','codex'), ('project','bad\nproject'),
                ('port',True), ('port',443), ('server_port',True), ('server_port',443), ('expires_at',int(time.time())-1),
                ('expires_at',int(time.time())+3601), ('bearer','bad\nheader'),
                ('certificate', self.doc['certificate']*2), ('pin','0'*64), ('extra',1)]]
            for key, value in invalid:
                with self.subTest(field=key):
                    reader, writer, result = await self.offer({**self.doc,key:value})
                    if result.get('kind') == 'offered':
                        writer.write(b'stop\n'); await writer.drain(); await reader.readline()
                    self.assertEqual(result, {'kind':'closed','clean':False})
                    self.assertEqual(receiver.offers(),[])
            self.assertEqual(self.peers,[])

    async def test_HD003_expiry_releases_idle_unclaimed_offer(self):
        async with self.module.Receiver(self.path) as receiver:
            reader, writer, offered = await self.offer({**self.doc,'expires_at':int(time.time())+1})
            self.assertEqual(offered['kind'],'offered')
            try:
                closed = json.loads(await asyncio.wait_for(reader.readline(),2))
            except asyncio.TimeoutError:
                self.fail('expired_offer_retained_until_sender_disconnect')
            self.assertEqual(closed,{'kind':'closed','clean':True})
            self.assertEqual(receiver.offers(),[])

    async def test_HD004_source_stop_during_catalog_never_publishes_late_binding(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class DelayedPeer(Peer):
            async def list_tools(inner):
                entered.set()
                await release.wait()
                return await super().list_tools()
        async def connect(**kwargs):
            peer=DelayedPeer(); self.peers.append(peer); return peer
        with patch('hermes_connection.connect',connect):
            async with self.module.Receiver(self.path) as receiver:
                reader, writer, offer = await self.offer()
                claim = asyncio.create_task(receiver.claim(offer['id'], conversation_id='a', include=('agent_status',)))
                try:
                    await asyncio.wait_for(entered.wait(),1)
                    writer.write(b'stop\n'); await writer.drain()
                    closed=json.loads(await asyncio.wait_for(reader.readline(),2))
                    release.set()
                    result=(await asyncio.gather(claim,return_exceptions=True))[0]
                    if hasattr(result,'close'):
                        await result.close()
                    self.assertIsInstance(result,BaseException,'withdrawn_offer_published_late_binding')
                    self.assertTrue(self.peers[0].closed)
                    self.assertEqual(closed,{'kind':'closed','clean':True})
                finally:
                    release.set(); await asyncio.gather(claim,return_exceptions=True)

    async def test_HD005_failed_claim_is_terminal_and_never_retries_credentials(self):
        calls=[]
        async def failed(**kwargs):
            calls.append(1)
            raise RuntimeError('fixture-secret-error-never-returned')
        with patch('hermes_connection.connect',failed):
            async with self.module.Receiver(self.path) as receiver:
                reader, writer, offered=await self.offer()
                with self.assertRaisesRegex(RuntimeError,'candidate_claim_failed'):
                    await receiver.claim(offered['id'],conversation_id='a',include=('agent_status',))
                with self.assertRaisesRegex(ValueError,'candidate_offer_unavailable'):
                    await receiver.claim(offered['id'],conversation_id='a',include=('agent_status',))
                self.assertEqual(len(calls),1)
                self.assertEqual(receiver.offers(),[])
                self.assertEqual(json.loads(await asyncio.wait_for(reader.readline(),2)),{'kind':'closed','clean':False})

    async def test_HD006_duplicate_keys_and_capacity_fail_closed(self):
        async with self.module.Receiver(self.path) as receiver:
            reader,writer=await asyncio.open_unix_connection(str(self.path)); self.writers.append(writer)
            raw=json.dumps(self.doc)
            writer.write((raw[:-1]+',"role":"hermes"}\n').encode()); await writer.drain()
            reply=json.loads(await asyncio.wait_for(reader.readline(),2))
            if reply.get('kind')=='offered':
                writer.write(b'stop\n'); await writer.drain(); await reader.readline()
            self.assertEqual(reply,{'kind':'closed','clean':False},'duplicate_fields_accepted')
            offers=[await self.offer() for _ in range(8)]
            self.assertEqual(len(receiver.offers()),8)
            reader,writer,reply=await self.offer()
            self.assertEqual(reply,{'kind':'closed','clean':False},'unbounded_incoming_channels')
            self.assertEqual(len(receiver.offers()),8)
            for reader,writer,_ in offers:
                writer.write(b'stop\n'); await writer.drain(); await reader.readline()

    async def test_HD007_repeated_exit_cancellation_waits_for_peer_cleanup(self):
        entered, release=asyncio.Event(),asyncio.Event()
        class SlowPeer(Peer):
            async def shutdown(inner):
                entered.set(); await release.wait(); await super().shutdown()
        async def connect(**kwargs):
            peer=SlowPeer(); self.peers.append(peer); return peer
        with patch('hermes_connection.connect',connect):
            receiver=await self.module.Receiver(self.path).__aenter__()
            reader,writer,offered=await self.offer()
            await receiver.claim(offered['id'],conversation_id='a',include=('agent_status',))
            closing=asyncio.create_task(receiver.__aexit__(None,None,None))
            try:
                await asyncio.wait_for(entered.wait(),1)
                closing.cancel(); await asyncio.sleep(0)
                closing.cancel(); await asyncio.sleep(0.02)
                premature=closing.done()
            finally:
                release.set(); await asyncio.gather(closing,return_exceptions=True)
                for peer in self.peers:
                    if not peer.closed: await peer.shutdown()
                if self.path.exists(): self.path.unlink()
            self.assertFalse(premature,'receiver_exit_finished_before_owned_shutdown')
            self.assertTrue(self.peers[0].closed)

    async def test_HD008_project_identity_mismatch_rejects_before_registration(self):
        async with self.module.Receiver(self.path) as receiver:
            reader,writer,offered=await self.offer({**self.doc,'project':'foreign-project'})
            try:
                binding=await receiver.claim(offered['id'],conversation_id='a',include=('agent_status',))
            except RuntimeError as exc:
                self.assertEqual(str(exc),'candidate_claim_failed')
            else:
                await binding.close()
                self.fail('unverified_project_label_admitted')
            self.assertEqual(set(registry.get_all_tool_names()),self.baseline)
            self.assertEqual(receiver.offers(),[])

    async def test_HD009_stdio_relay_uses_private_ipc_and_never_echoes_secret(self):
        entry=ROOT/'clients/hermes_handoff_relay.py'
        self.assertTrue(entry.is_file(),'missing_stdio_relay')
        async with self.module.Receiver(self.path) as receiver:
            process=await asyncio.create_subprocess_exec(sys.executable,str(entry),str(self.path),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try:
                process.stdin.write(json.dumps(self.doc).encode()+b'\n'); await process.stdin.drain()
                offered=json.loads(await asyncio.wait_for(process.stdout.readline(),2))
                self.assertEqual(offered['kind'],'offered')
                await receiver.claim(offered['id'],conversation_id='relay-a',include=('agent_status',))
                process.stdin.write(b'stop\n'); await process.stdin.drain()
                closed=json.loads(await asyncio.wait_for(process.stdout.readline(),2))
                self.assertEqual(closed,{'kind':'closed','clean':True})
                self.assertEqual(await asyncio.wait_for(process.wait(),2),0)
                self.assertEqual(await process.stderr.read(),b'')
                self.assertEqual(receiver.offers(),[])
                self.assertTrue(self.peers[0].closed)
            finally:
                if process.returncode is None: process.kill()
                await process.wait()
                process.stdin.close(); await process.stdin.wait_closed()

    async def test_HD010_unsafe_receiver_paths_rejected_without_replacement(self):
        foreign=Path(self.home.name)/'foreign'; foreign.write_text('preserved')
        with self.assertRaises(ValueError):
            async with self.module.Receiver(foreign): pass
        self.assertEqual(foreign.read_text(),'preserved')
        link=Path(self.home.name)/'link'; link.symlink_to(foreign)
        with self.assertRaises(ValueError):
            async with self.module.Receiver(link): pass
        self.assertTrue(link.is_symlink())
        unsafe=Path(self.home.name)/'unsafe'; unsafe.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            async with self.module.Receiver(unsafe/'s'): pass
        self.assertFalse((unsafe/'s').exists())

    async def test_HD011_same_offer_claim_is_one_shot_and_other_offer_survives(self):
        async with self.module.Receiver(self.path) as receiver:
            ra,wa,a=await self.offer(); rb,wb,b=await self.offer()
            bound=await receiver.claim(a['id'],conversation_id='a',include=('agent_status',))
            other=await receiver.claim(b['id'],conversation_id='b',include=('agent_status',))
            with self.assertRaises(ValueError):
                await receiver.claim(a['id'],conversation_id='c',include=('agent_status',))
            wa.write(b'stop\n'); await wa.drain(); await ra.readline()
            name=other.snapshot()[0]['function']['name']
            result=json.loads(await asyncio.to_thread(handle_function_call,name,{},session_id='b',enabled_tools=[name]))
            self.assertNotIn('error',result)
            self.assertEqual([v['id'] for v in receiver.offers()],[b['id']])
            wb.write(b'stop\n'); await wb.drain(); await rb.readline()

    async def test_HD012_receiver_exit_during_source_cleanup_waits_and_reports_failure(self):
        entered,release=asyncio.Event(),asyncio.Event()
        class FailedClose(Peer):
            async def shutdown(inner):
                entered.set(); await release.wait(); await super().shutdown()
                raise RuntimeError('fixture_cleanup_failure')
        async def connect(**kwargs):
            peer=FailedClose(); self.peers.append(peer); return peer
        with patch('hermes_connection.connect',connect):
            receiver=await self.module.Receiver(self.path).__aenter__()
            reader,writer,offered=await self.offer()
            await receiver.claim(offered['id'],conversation_id='a',include=('agent_status',))
            writer.write(b'stop\n'); await writer.drain()
            await asyncio.wait_for(entered.wait(),1)
            closing=asyncio.create_task(receiver.__aexit__(None,None,None))
            await asyncio.sleep(.02); premature=closing.done()
            release.set(); result=(await asyncio.gather(closing,return_exceptions=True))[0]
            self.assertFalse(premature,'source_cleanup_cancelled_by_receiver_exit')
            self.assertIsInstance(result,RuntimeError)
            self.assertEqual(str(result),'candidate_receiver_cleanup_failed')
            self.assertEqual(json.loads(await asyncio.wait_for(reader.readline(),2)),{'kind':'closed','clean':False})

    async def test_HD013_fixed_ssh_subsystem_reuses_strict_forward_policy(self):
        sys.path.insert(0,str(ROOT))
        from launcher import candidate_launch
        self.assertTrue(hasattr(candidate_launch,'build_handoff_command'),'missing_fixed_handoff_command')
        raw={'project':'fixture-project','parent_pid':os.getpid(),'local_port':18443,
             'ssh':{'host':'127.0.0.1','user':'ubuntu','port':22222,'remote_port':18444}}
        command=candidate_launch.build_handoff_command(raw)
        old=candidate_launch.build_commands(raw)[1]
        self.assertEqual(command, [v for v in old[:-1] if v != '-N']+['-s',old[-1],'vrchat-agent-handoff'])
        self.assertIn('StrictHostKeyChecking=yes',command)
        self.assertIn('BatchMode=yes',command)
        self.assertIn('ForwardAgent=no',command)
        self.assertIn('127.0.0.1:18444:127.0.0.1:18443',command)
        self.assertNotIn(self.doc['bearer'],repr(command))
        with self.assertRaises(ValueError):
            candidate_launch.build_handoff_command({k:v for k,v in raw.items() if k!='ssh'})
        with self.assertRaises(ValueError):
            candidate_launch.build_handoff_command({**raw,'ssh':{**raw['ssh'],'host':'bad;command'}})

    async def test_HD014_real_ssh_subsystem_auth_offer_and_stop(self):
        sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
        from handoff_ssh_fixture import ssh_relay
        report={}
        try:
            async with self.module.Receiver(self.path) as receiver:
                async with ssh_relay(self.path,self.doc,report) as process:
                    offered=json.loads(await asyncio.wait_for(process.stdout.readline(),8))
                    self.assertEqual(offered['kind'],'offered')
                    await receiver.claim(offered['id'],conversation_id='ssh-a',include=('agent_status',))
                    process.stdin.write(b'stop\n'); await process.stdin.drain()
                    self.assertEqual(json.loads(await asyncio.wait_for(process.stdout.readline(),5)),{'kind':'closed','clean':True})
                    self.assertEqual(await asyncio.wait_for(process.wait(),5),0)
                    self.assertEqual(receiver.offers(),[])
            self.assertTrue(report['ssh_authenticated'])
        finally:
            print(json.dumps({'ssh_fixture':report}))

    async def test_HD015_real_ssh_refuses_wrong_host_and_missing_client_key(self):
        sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
        from handoff_ssh_fixture import ssh_relay
        for options in ({'wrong_host':True},{'no_key':True}):
            with self.subTest(options=options):
                report={}
                async with self.module.Receiver(self.path) as receiver:
                    async with ssh_relay(self.path,self.doc,report,**options) as process:
                        self.assertEqual(await asyncio.wait_for(process.stdout.read(),8),b'')
                        self.assertEqual(await asyncio.wait_for(process.wait(),5),255)
                        self.assertEqual(receiver.offers(),[])
                        self.assertEqual(self.peers,[])
                self.assertFalse(report['ssh_authenticated'])
                self.assertTrue(report['ssh_descendants']['clean'])

    async def test_HD016_real_ssh_client_death_revokes_bound_offer(self):
        sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
        from handoff_ssh_fixture import ssh_relay
        report={}
        async with self.module.Receiver(self.path) as receiver:
            async with ssh_relay(self.path,self.doc,report) as process:
                offered=json.loads(await asyncio.wait_for(process.stdout.readline(),8))
                bound=await receiver.claim(offered['id'],conversation_id='ssh-b',include=('agent_status',))
                process.kill();await process.wait()
                async with asyncio.timeout(5):
                    while receiver.offers() or not self.peers[0].closed: await asyncio.sleep(.02)
                self.assertEqual(set(registry.get_all_tool_names()),self.baseline)
        self.assertTrue(report['ssh_descendants']['clean'])

    async def test_HD017_owned_sender_real_ssh_delivers_and_confirms_stop(self):
        import importlib.util,threading
        sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
        self.assertIsNotNone(importlib.util.find_spec('launcher.hermes_delivery'))
        from launcher import hermes_delivery
        from handoff_ssh_fixture import ssh_relay
        from types import SimpleNamespace
        report={};stop=threading.Event();offered=threading.Event()
        identity=SimpleNamespace(clients=('hermes',),project=self.doc['project'],
            expires_at=self.doc['expires_at'],credentials={'hermes':SimpleNamespace(token=self.doc['bearer'])})
        tls=SimpleNamespace(certificate=self.doc['certificate'].encode(),pin=self.doc['pin'])
        local_run=SimpleNamespace(project=self.doc['project'],port=self.doc['port'],identity=identity,tls=tls)
        async with self.module.Receiver(self.path) as receiver:
            async with ssh_relay(self.path,self.doc,report,launch=False) as transport:
                with patch.object(hermes_delivery,'build_handoff_command',return_value=transport['command']), \
                        patch.object(hermes_delivery,'child_environment',return_value=transport['environment']):
                    task=asyncio.create_task(hermes_delivery.deliver(transport['raw'],local_run,stop=stop,offered=offered))
                    try:
                        async with asyncio.timeout(5):
                            while not offered.is_set() and not task.done():await asyncio.sleep(.01)
                        self.assertTrue(offered.is_set(),task.result() if task.done() else None)
                        self.assertEqual(len(receiver.offers()),1)
                        stop.set();result=await asyncio.wait_for(task,10)
                        self.assertEqual(result['code'],'STOPPED')
                        self.assertTrue(result['remote_cleanup_confirmed'])
                        self.assertTrue(result['process_cleanup_complete'])
                        self.assertEqual(receiver.offers(),[])
                    finally:
                        stop.set()
                        if not task.done():await asyncio.wait_for(task,10)
        self.assertTrue(report['ssh_descendants']['clean'])

    async def test_HD018_host_withdraw_waits_for_source_and_never_reoffers(self):
        async with self.module.Receiver(self.path) as receiver:
            self.assertTrue(hasattr(receiver,'withdraw'),'missing_host_withdraw')
            reader,writer,accepted=await self.offer()
            binding=await receiver.claim(accepted['id'],conversation_id='chat',include=('agent_status',))
            entered=asyncio.Event();release=asyncio.Event();peer=self.peers[0]
            original=peer.shutdown
            async def slow_close():entered.set();await release.wait();await original()
            peer.shutdown=slow_close
            task=asyncio.create_task(receiver.withdraw(accepted['id']))
            await entered.wait();task.cancel();task.cancel();await asyncio.sleep(.02)
            try:self.assertFalse(task.done(),'withdraw_abandoned_cleanup')
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(peer.closed)
            self.assertEqual(json.loads(await reader.readline()),{'kind':'closed','clean':True})
            self.assertEqual(receiver.offers(),[])
            self.assertFalse(await receiver.withdraw(accepted['id']))

if __name__ == '__main__':
    unittest.main(verbosity=2)
