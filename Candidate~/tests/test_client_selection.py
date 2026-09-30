"""Local client selection; roles are permissions, not executable attestation."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'runtime'),str(ROOT/'native/src'),str(ROOT/'dependencies/mcp-1.29.1'),str(ROOT),str(ROOT/'tests')]
import run_identity
from owner_bootstrap import new_local_run,consume_environment,ENVIRONMENT_KEY

class ClientSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_CS001_default_signs_only_internal_roles(self):
        identity=run_identity.issue_run_identity()
        self.assertEqual(set(identity.credentials),{'unity','probe'})
        owner=new_local_run('selection-fixture',18081)
        self.assertEqual(set(owner.identity.credentials),{'unity','probe'})

    async def test_CS002_selection_is_exact_immutable_and_checked_before_issuance(self):
        from dataclasses import FrozenInstanceError
        for selected in ((),('hermes',),('codex',),('codex','hermes')):
            identity=run_identity.issue_run_identity(clients=selected)
            self.assertEqual(set(identity.credentials),{'unity','probe',*selected})
            self.assertEqual(identity.clients,tuple(r for r in ('hermes','codex') if r in selected))
            with self.assertRaises(FrozenInstanceError):identity.clients=('hermes','codex')
        with patch.object(run_identity.rsa,'generate_private_key',side_effect=AssertionError('keygen')) as keygen:
            for selected in (None,True,'hermes',['hermes'],{'hermes'},('hermes','hermes'),('probe',),('unity',),('Hermes',),('hermes ',),(1,),([],)):
                with self.subTest(selected=repr(selected)),self.assertRaisesRegex(ValueError,'invalid_client_selection'):
                    run_identity.issue_run_identity(clients=selected)
            keygen.assert_not_called()

    async def test_CS003_child_rejects_even_valid_signed_unselected_roles(self):
        # Trusted owner policy is narrowed while keeping the same actual signer.
        # A token is not accepted solely because its signature/audience are valid.
        owner=new_local_run('selection-fixture',18081,clients=('hermes','codex'))
        doc=json.loads(owner.take_environment()[ENVIRONMENT_KEY])
        self.assertEqual(doc.get('clients'),['hermes','codex'])
        for selected in ([],['hermes'],['codex'],['hermes','codex']):
            env={ENVIRONMENT_KEY:json.dumps(dict(doc,clients=selected))}
            config=consume_environment(owner.project,owner.port,environment=env)
            self.assertEqual(config.clients,tuple(selected));self.assertFalse(env)
            mcp,unity=config.verifiers()
            for role,credential in owner.identity.credentials.items():
                self.assertEqual(await mcp.verify_token(credential.token) is not None,role in selected or role=='probe')
                self.assertEqual(await unity.verify_token(credential.token) is not None,role=='unity')
        one=new_local_run('selection-fixture',18081,clients=('hermes',))
        self.assertEqual(set(one.identity.credentials),{'hermes','probe','unity'})
        raw=one.take_environment()[ENVIRONMENT_KEY]
        for credential in one.identity.credentials.values():self.assertNotIn(credential.token,raw)

    async def test_CS004_malformed_or_legacy_policy_is_consumed_and_refused(self):
        owner=new_local_run('selection-fixture',18081)
        good=json.loads(owner.take_environment()[ENVIRONMENT_KEY])
        mutations=[dict(good,clients=x) for x in (None,True,'hermes',{},[1],[[]],['Hermes'],['probe'],['hermes','hermes'],['codex','hermes'])]
        mutations += [dict(good,version=1),{k:v for k,v in good.items() if k!='clients'}]
        for doc in mutations:
            env={ENVIRONMENT_KEY:json.dumps(doc)}
            with self.assertRaisesRegex(ValueError,'BINDING_INVALID'):
                consume_environment(owner.project,owner.port,environment=env)
            self.assertFalse(env)

    async def test_CS005_owned_launcher_passes_exact_selection_without_tokens_to_runtime(self):
        import os
        from launcher.owned_run import create_owned_run
        raw={'project':'selection-fixture','local_port':18081,'parent_pid':os.getpid()}
        for selected in ((),('hermes',),('codex',),('hermes','codex')):
            owned=create_owned_run(raw,clients=selected)
            self.assertEqual(owned.owner.identity.clients,selected)
            self.assertEqual(set(owned.owner.identity.credentials),{'unity','probe',*selected})
            data=consume_environment('selection-fixture',18081,environment=owned.binding.environment)
            self.assertEqual(data.clients,selected)
        self.assertEqual(create_owned_run(raw).owner.identity.clients,())

    async def test_CS006_private_entry_selection_receipt_and_cleanup(self):
        import asyncio,os,socket
        from urllib.parse import urlparse
        from test_editor_owner import EXECUTABLE,ENTRY,environment
        for selected in ((),('hermes',),('codex',),('hermes','codex')):
            flags=[part for role in selected for part in ('--client',role)]
            p=await asyncio.create_subprocess_exec(EXECUTABLE,'-I','-B',str(ENTRY),
                '--project','selection-pipe-'+str(os.getpid()),'--parent-pid',str(os.getpid()),*flags,
                env=environment(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            port=None
            try:
                p.stdin.write(b'start\n');await p.stdin.drain()
                line=await asyncio.wait_for(p.stdout.readline(),10)
                self.assertTrue(line,'private entry must emit binding')
                bundle=json.loads(line)
                self.assertEqual(bundle.get('clients'),list(selected))
                self.assertEqual(bundle.get('version'),2)
                self.assertEqual(bundle['owner_pid'],p.pid)
                self.assertEqual(set(bundle),{'kind','version','owner_pid','project','endpoint','pin','unity_bearer','expires_at','clients'})
                self.assertEqual(bundle['kind'],'unity_binding')
                port=urlparse(bundle['endpoint']).port
                p.stdin.close();out,err=await asyncio.wait_for(p.communicate(),12)
                final=json.loads(out.decode().splitlines()[-1])
                self.assertTrue(final['process_cleanup_complete']);self.assertTrue(final['probe_cleanup_complete'])
                self.assertNotIn(bundle['unity_bearer'].encode(),out+err)
                self.assertNotIn(b'PRIVATE KEY',line+out+err)
            finally:
                if p.returncode is None:
                    p.stdin.close()
                    try:await asyncio.wait_for(p.communicate(),12)
                    except TimeoutError:p.kill();await p.communicate();raise
            if port is not None:
                with socket.socket() as sock:self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)

    async def test_CS008_local_ui_defaults_closed_and_forwards_both_explicit_flags(self):
        window=(ROOT/'package/Editor/CandidateWindow.cs').read_text(encoding='utf-8')
        session=(ROOT/'package/Editor/CandidateSession.cs').read_text(encoding='utf-8')
        self.assertIn('bool allowHermes, allowCodex;',window)
        self.assertIn('allowHermes = EditorGUILayout.ToggleLeft(',window)
        self.assertIn('allowCodex = EditorGUILayout.ToggleLeft(',window)
        self.assertIn('externalPython ? python : null, allowHermes, allowCodex',window)
        self.assertIn('bool allowHermes = false, bool allowCodex = false',session)
        self.assertIn('ConnectOwnedAsync, StopOwnedAsync, allowHermes, allowCodex',session)
        self.assertLess(window.index('BeginDisabledGroup(CandidateSession.HasLocalOwner)'),window.index('allowHermes = EditorGUILayout.ToggleLeft('))
        self.assertLess(window.index('allowCodex = EditorGUILayout.ToggleLeft('),window.index('EditorGUI.EndDisabledGroup();'))

    async def test_CS009_real_tls_http_rejects_unselected_signed_token(self):
        import asyncio,socket,ssl
        import httpx,uvicorn
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport
        from candidate_runtime import create_server,create_app
        from tls_context import load_tls_context
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
            owner=new_local_run('selection-http',port,clients=('hermes','codex'))
            doc=json.loads(owner.take_environment()[ENVIRONMENT_KEY]);doc['clients']=['hermes']
            child=consume_environment(owner.project,port,environment={ENVIRONMENT_KEY:json.dumps(doc)})
            mcp_auth,unity_auth=child.verifiers()
            mcp=create_server(owner.project,mcp_auth=mcp_auth)
            config=uvicorn.Config(create_app(mcp,unity_auth=unity_auth),log_level='error',access_log=False,timeout_graceful_shutdown=3)
            config.load();config.ssl=load_tls_context(owner.tls)
            server=uvicorn.Server(config);task=asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(8):
                    while not server.started:
                        if task.done():await task;self.fail('server stopped')
                        await asyncio.sleep(.02)
                context=ssl.create_default_context(cadata=owner.tls.certificate.decode())
                url=f'https://127.0.0.1:{port}/mcp'
                async with httpx.AsyncClient(verify=context,trust_env=False,timeout=3) as http:
                    denied=await http.post(url,headers={'Authorization':'Bearer '+owner.identity.credentials['codex'].token},json={})
                    self.assertEqual(denied.status_code,401)
                    self.assertFalse(mcp._candidate_runtime.sessions)
                def factory(**kw):
                    kw.update(verify=context,trust_env=False,follow_redirects=False)
                    return httpx.AsyncClient(**kw)
                async with Client(StreamableHttpTransport(url,headers={'Authorization':'Bearer '+owner.identity.credentials['hermes'].token},httpx_client_factory=factory)) as client:
                    self.assertIn('agent_prepare',[t.name for t in await client.list_tools()])
                self.assertFalse(mcp._candidate_runtime.sessions)
            finally:
                server.should_exit=True;await asyncio.wait_for(task,8)
        with socket.socket() as check:self.assertNotEqual(check.connect_ex(('127.0.0.1',port)),0)
        self.assertFalse(mcp._candidate_runtime.plans);self.assertFalse(mcp._candidate_runtime.material.plans)

    async def test_CS010_bad_cli_selection_emits_no_binding(self):
        import asyncio,os
        from test_editor_owner import EXECUTABLE,ENTRY,environment
        for flags in (['--client','probe'],['--client','Hermes'],['--client','hermes','--client','hermes']):
            p=await asyncio.create_subprocess_exec(EXECUTABLE,'-I','-B',str(ENTRY),'--project','selection-invalid-'+str(os.getpid()),'--parent-pid',str(os.getpid()),*flags,
                env=environment(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try:out,err=await asyncio.wait_for(p.communicate(b'start\n'),5)
            finally:
                if p.returncode is None:p.kill();await p.communicate()
            self.assertNotEqual(p.returncode,0)
            self.assertNotIn(b'unity_bearer',out+err);self.assertNotIn(b'PRIVATE KEY',out+err);self.assertNotIn(b'Traceback',out+err)

if __name__=='__main__':unittest.main(verbosity=2)
