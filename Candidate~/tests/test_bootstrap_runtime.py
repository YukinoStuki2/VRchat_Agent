"""Actual child entry; synthetic credentials, no real client/Unity connection."""
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
def child_environment(home):
    keep = {k: os.environ[k] for k in ('SystemRoot','WINDIR','COMSPEC','PATHEXT') if k in os.environ}
    return {**keep,'PATH':os.environ.get('PATH',''),'HOME':str(home),'USERPROFILE':str(home),
        'LANG':'C.UTF-8','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','DISABLE_TELEMETRY':'true'}
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'dependencies/mcp-1.29.1')]


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_BR001_unbound_cli_exits_without_listener(self):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='bootstrap-unbound-') as home:
            process = await asyncio.create_subprocess_exec(sys.executable, '-B', str(ROOT/'runtime'),
                '--project', 'fixture-project', '--port', str(port),
                env=child_environment(home),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                try:
                    out, err = await asyncio.wait_for(process.communicate(), 4)
                except TimeoutError:
                    self.fail('unbound CLI remained alive instead of refusing to start')
                self.assertNotEqual(process.returncode, 0)
                self.assertIn(b'BINDING_REQUIRED', err)
                self.assertNotIn(b'Traceback', err)
            finally:
                if process.returncode is None: process.kill()
                await process.communicate()
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(('127.0.0.1', port)), 0)
            self.assertFalse(Path('/proc', str(process.pid)).exists())


    async def test_BR002_bound_cli_serves_tls_and_rejects_wrong_roles(self):
        self.assertIsNotNone(importlib.util.find_spec('owner_bootstrap'), 'missing local owner bootstrap')
        bootstrap = importlib.import_module('owner_bootstrap')
        import httpx
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
        owner = bootstrap.new_local_run('fixture-project', port,clients=('hermes','codex'))
        env = owner.take_environment()
        self.assertNotIn(owner.identity.credentials['hermes'].token, json.dumps(env))
        self.assertNotIn(owner.identity.credentials['codex'].token, json.dumps(env))
        self.assertNotIn(owner.identity.credentials['unity'].token, json.dumps(env))
        context = ssl.create_default_context(cadata=owner.tls.certificate.decode())
        with tempfile.TemporaryDirectory(prefix='bootstrap-bound-') as home:
            process = await asyncio.create_subprocess_exec(sys.executable, '-B', str(ROOT/'runtime'),
                '--project', 'fixture-project', '--port', str(port),
                env={**child_environment(home),**env},
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                deadline = time.monotonic()+12
                while True:
                    if process.returncode is not None:
                        out, err=await process.communicate()
                        self.fail('bound CLI failed: '+err.decode()[-1800:])
                    try:
                        reader, writer=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',port,ssl=context),1)
                        writer.close(); await writer.wait_closed(); break
                    except (OSError, TimeoutError):
                        if time.monotonic()>deadline:self.fail('bound TLS did not become ready')
                        await asyncio.sleep(.05)
                async with httpx.AsyncClient(verify=context,trust_env=False) as http:
                    for headers in ({},{'Authorization':'Bearer '+owner.identity.credentials['unity'].token}):
                        result=await http.post(f'https://127.0.0.1:{port}/mcp',headers=headers,json={})
                        self.assertEqual(result.status_code,401)
                def factory(**kwargs):
                    kwargs.update(verify=context,trust_env=False,follow_redirects=False)
                    return httpx.AsyncClient(**kwargs)
                async with Client(StreamableHttpTransport(f'https://127.0.0.1:{port}/mcp',
                        headers={'Authorization':'Bearer '+owner.identity.credentials['hermes'].token},
                        httpx_client_factory=factory)) as client:
                    self.assertIn('agent_status',[tool.name for tool in await client.list_tools()])
                    from fastmcp.exceptions import ToolError
                    with self.assertRaisesRegex(ToolError,'expected_project_not_connected'):
                        await client.call_tool('agent_status',{})
                process.terminate()
                out,err=await asyncio.wait_for(process.communicate(),8)
                self.assertNotIn(b'Traceback',err)
                for credential in owner.identity.credentials.values():
                    self.assertNotIn(credential.token.encode(),out+err)
                self.assertNotIn(b'PRIVATE KEY',out+err)
                self.assertFalse(list(Path(home).rglob('*.pem')))
            finally:
                if process.returncode is None:process.kill()
                await process.communicate()
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)

    async def test_BR003_duplicate_fields_refused_and_material_consumed(self):
        from owner_bootstrap import new_local_run, consume_environment, ENVIRONMENT_KEY
        owner=new_local_run('fixture-project',18081)
        env=owner.take_environment()
        raw=env[ENVIRONMENT_KEY]
        env[ENVIRONMENT_KEY]=raw[:-1]+',"project":"fixture-project"}'
        with self.assertRaisesRegex(ValueError,'BINDING_INVALID'):
            consume_environment('fixture-project',18081,environment=env)
        self.assertNotIn(ENVIRONMENT_KEY,env)

    async def test_BR004_invalid_fields_and_wrong_binding_fail_closed(self):
        from owner_bootstrap import new_local_run, consume_environment, ENVIRONMENT_KEY
        owner=new_local_run('fixture-project',18081)
        good=json.loads(owner.take_environment()[ENVIRONMENT_KEY])
        mutations=[dict(good,project='other'),dict(good,port=18082),dict(good,expires_at=0),
            dict(good,expires_at=int(time.time())+3700),dict(good,version=True),
            dict(good,issuer='foreign'),dict(good,extra='unaccepted'),dict(good,port=True)]
        for doc in mutations:
            env={ENVIRONMENT_KEY:json.dumps(doc)}
            with self.assertRaisesRegex(ValueError,'BINDING_INVALID'):
                consume_environment('fixture-project',18081,environment=env)
            self.assertNotIn(ENVIRONMENT_KEY,env)
        for raw in ('[','[]','x'*16385,'['*1500+']'*1500):
            with self.assertRaisesRegex(ValueError,'BINDING_INVALID'):
                consume_environment('fixture-project',18081,environment={ENVIRONMENT_KEY:raw})
        with self.assertRaisesRegex(ValueError,'already_consumed'):owner.take_environment()

    async def test_BR005_invalid_pem_refused_without_secret_trace(self):
        from owner_bootstrap import new_local_run, ENVIRONMENT_KEY
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        owner=new_local_run('fixture-project',port)
        env=owner.take_environment();doc=json.loads(env[ENVIRONMENT_KEY])
        doc['tls_private_key']='synthetic-DO-NOT-PRINT-secret'
        env[ENVIRONMENT_KEY]=json.dumps(doc)
        child=await asyncio.create_subprocess_exec(sys.executable,'-B',str(ROOT/'runtime'),
            '--project','fixture-project','--port',str(port),
            env={**child_environment(tempfile.gettempdir()),**env},
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,err=await asyncio.wait_for(child.communicate(),8)
            self.assertNotEqual(child.returncode,0)
            self.assertIn(b'BINDING_INVALID',err)
            self.assertNotIn(b'DO-NOT-PRINT',out+err);self.assertNotIn(b'Traceback',err)
        finally:
            if child.returncode is None:child.kill()
            await child.communicate()
        with socket.socket() as sock:self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)

    async def test_BR006_runtime_exits_at_local_run_expiry(self):
        from owner_bootstrap import new_local_run, ENVIRONMENT_KEY
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        owner=new_local_run('fixture-project',port)
        env=owner.take_environment();doc=json.loads(env[ENVIRONMENT_KEY])
        doc['expires_at']=int(time.time())+4
        env[ENVIRONMENT_KEY]=json.dumps(doc)
        child=await asyncio.create_subprocess_exec(sys.executable,'-B',str(ROOT/'runtime'),
            '--project','fixture-project','--port',str(port),
            env={**child_environment(tempfile.gettempdir()),**env},
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,err=await asyncio.wait_for(child.communicate(),10)
            self.assertEqual(child.returncode,0,err.decode())
            self.assertNotIn(b'Traceback',err)
        finally:
            if child.returncode is None:child.kill()
            await child.communicate()
        with socket.socket() as sock:self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
