"""Fixed-target connection contracts: real installed SDK, mock HTTP only."""
import asyncio
import hashlib
import json
from pathlib import Path
import ssl
import sys
import time
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
HERMES = Path(sys.argv.pop(1)).resolve(strict=True)
sys.path[:0] = [str(HERMES), str(ROOT/'clients'), str(ROOT/'runtime')]
from tools.mcp_tool import sdk_httpx
from tls_context import issue_tls_material
httpx = sdk_httpx()

class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((ROOT/'clients/hermes_connection.py').is_file(), 'missing_fixed_target_connection')
        import hermes_connection
        self.module = hermes_connection
        self.tls = await asyncio.to_thread(issue_tls_material)
        self.kw = dict(port=19443, certificate=self.tls.certificate.decode(), pin=self.tls.pin,
                       bearer='fixture-memory-bearer', expires_at=int(time.time())+60)
        self.requests = []
        self.clients = []
        self.options = []
        native = httpx.AsyncClient
        async def respond(request):
            self.requests.append((request.method, str(request.url)))
            if request.method == 'DELETE': return httpx.Response(200)
            if request.method == 'GET': return httpx.Response(405)
            doc = json.loads(request.content)
            if 'id' not in doc: return httpx.Response(202)
            if doc['method'] == 'initialize':
                result = {'protocolVersion':'2025-11-25', 'capabilities':{'tools':{}},
                          'serverInfo':{'name':'fixture', 'version':'1'}}
            elif doc['method'] == 'tools/list': result = {'tools':[]}
            else: result = {}
            return httpx.Response(200, headers={'mcp-session-id':'contract-session'},
                                  json={'jsonrpc':'2.0', 'id':doc['id'], 'result':result})
        self.respond = respond
        def factory(**options):
            self.options.append(options.copy())
            client = native(**options, transport=httpx.MockTransport(self.respond))
            self.clients.append(client)
            return client
        self.factory = patch.object(httpx, 'AsyncClient', factory)
        self.factory.start()
    async def asyncTearDown(self):
        self.factory.stop()
        self.assertTrue(all(client.is_closed for client in self.clients))

    async def test_HE001_exact_endpoint_exclusive_trust_and_sdk_cleanup(self):
        peer = await self.module.connect(**self.kw)
        try:
            self.assertIsNotNone(peer.session)
            self.assertEqual((await peer.session.list_tools()).tools, [])
            config = self.options[0]
            self.assertIs(config['trust_env'], False)
            self.assertIs(config['follow_redirects'], False)
            context = config['verify']
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertEqual(len(context.get_ca_certs(binary_form=True)), 0)  # leaf, not system CAs
        finally:
            await peer.shutdown()
        self.assertIsNone(peer.session)
        self.assertEqual(sum(method == 'DELETE' for method, _ in self.requests), 1)
        self.assertTrue(all(url == 'https://127.0.0.1:19443/mcp' for _, url in self.requests))
        self.assertNotIn(self.kw['bearer'], repr(peer))
        self.assertNotIn('authorization', self.clients[0].headers)
        await peer.shutdown()
        self.assertEqual(sum(method == 'DELETE' for method, _ in self.requests), 1)

    async def test_HE002_invalid_handoff_rejected_before_http_client(self):
        for key, value in [('port',443),('port',True),('port','19443'),('pin','0'*64),
                           ('certificate',self.kw['certificate']*2),('bearer','bad\nheader'),
                           ('expires_at',True),('expires_at',int(time.time())-1),
                           ('expires_at',int(time.time())+3601)]:
            with self.subTest(field=key):
                try:
                    peer = await self.module.connect(**{**self.kw,key:value})
                except ValueError as exc:
                    self.assertEqual(str(exc),'candidate_handoff_invalid')
                else:
                    await peer.shutdown()
                    self.fail('invalid_handoff_accepted')
        self.assertEqual(self.clients,[])

    async def test_HE003_expiry_closes_idle_session_without_a_tool_call(self):
        peer = await self.module.connect(**{**self.kw,'expires_at':int(time.time())+1})
        try:
            try:
                await asyncio.wait_for(asyncio.shield(peer._task), 1.6)
            except asyncio.TimeoutError:
                self.fail('expired_session_remained_live')
            self.assertIsNone(peer.session)
        finally:
            await peer.shutdown()
        self.assertEqual(sum(m == 'DELETE' for m, _ in self.requests),1)

    async def test_HE004_request_route_replay_and_expiry_denied_before_wire(self):
        for kind in ('foreign','get_retry','resumption','expired','session_change'):
            peer = await self.module.connect(**self.kw)
            try:
                await asyncio.sleep(.02)  # let the SDK's single GET start
                client = self.clients[-1]
                before = len(self.requests)
                url = 'https://127.0.0.1:19443/mcp'
                method = 'POST'; headers = {'mcp-session-id':'contract-session'}
                if kind == 'foreign': url = 'https://127.0.0.1:19444/mcp'
                if kind == 'get_retry': method = 'GET'
                if kind == 'resumption': headers['last-event-id'] = 'opaque'
                if kind == 'session_change': headers['mcp-session-id'] = 'another-session'
                with patch.object(self.module.time, 'time', return_value=self.kw['expires_at']+1 if kind=='expired' else time.time()):
                    with self.assertRaisesRegex(RuntimeError,'candidate_endpoint_policy'):
                        await client.request(method,url,headers=headers,json={'jsonrpc':'2.0','method':'notifications/initialized'})
                self.assertEqual(len(self.requests),before)
            finally:
                try: await peer.shutdown()
                except RuntimeError as exc: self.assertEqual(str(exc),'candidate_connection_failed')

    async def test_HE005_changed_session_receipt_is_terminal(self):
        original = self.respond
        swap = False
        async def replaced(request):
            response = await original(request)
            if swap and request.method == 'POST' and json.loads(request.content).get('method')=='tools/list':
                response.headers['mcp-session-id'] = 'substituted-session'
            return response
        self.respond = replaced
        peer = await self.module.connect(**self.kw)
        swap = True
        try:
            try: await peer.session.list_tools()
            except Exception: pass
            else: self.fail('changed_session_accepted')
        finally:
            with self.assertRaisesRegex(RuntimeError,'candidate_connection_failed'):
                await peer.shutdown()
        self.assertIsNone(peer.session)

    async def test_HE006_failed_delete_never_reports_clean_shutdown(self):
        original = self.respond
        async def refused(request):
            if request.method == 'DELETE': return httpx.Response(500)
            return await original(request)
        self.respond = refused
        peer = await self.module.connect(**self.kw)
        await peer.session.list_tools()  # drain initialized before testing DELETE only
        with self.assertRaisesRegex(RuntimeError,'candidate_connection_failed'):
            await peer.shutdown()
        self.assertIsNone(peer.session)
        self.assertFalse(peer.session_cleanup_confirmed)

    async def test_HE007_ready_waits_for_initialized_ack_before_immediate_close(self):
        original = self.respond
        acknowledged = asyncio.Event()
        async def delayed(request):
            if request.method == 'POST' and json.loads(request.content).get('method')=='notifications/initialized':
                await asyncio.sleep(.05)
                acknowledged.set()
            return await original(request)
        self.respond = delayed
        peer = await self.module.connect(**self.kw)
        try: self.assertTrue(acknowledged.is_set(), 'ready_before_initialized_ack')
        finally: await peer.shutdown()

    async def test_HE008_repeated_cancellation_waits_for_exact_cleanup(self):
        original = self.respond
        entered = asyncio.Event(); release = asyncio.Event()
        async def delayed(request):
            if request.method == 'DELETE':
                entered.set(); await release.wait()
            return await original(request)
        self.respond = delayed
        peer = await self.module.connect(**self.kw)
        closing = asyncio.create_task(peer.shutdown())
        try:
            await asyncio.wait_for(entered.wait(),1)
            closing.cancel(); await asyncio.sleep(.02)
            closing.cancel(); await asyncio.sleep(.02)
            self.assertFalse(closing.done(), 'cancelled_waiter_abandoned_cleanup')
        finally:
            release.set()
            await asyncio.gather(closing, return_exceptions=True)
            await peer.shutdown()
        self.assertTrue(peer.session_cleanup_confirmed)

    async def test_HE009_client_constructor_failure_is_bounded_and_sanitized(self):
        with patch.object(httpx,'AsyncClient',side_effect=RuntimeError('private-constructor-marker')):
            try:
                await asyncio.wait_for(self.module.connect(**self.kw),.3)
            except RuntimeError as exc:
                self.assertEqual(str(exc),'candidate_connection_failed')
            except asyncio.TimeoutError:
                self.fail('startup_waiter_not_released')
            else: self.fail('failed_constructor_accepted')

    async def test_HE010_stateless_server_is_not_admitted(self):
        original = self.respond
        async def stateless(request):
            response = await original(request)
            response.headers.pop('mcp-session-id',None)
            return response
        self.respond = stateless
        try: peer = await self.module.connect(**self.kw)
        except RuntimeError as exc: self.assertEqual(str(exc),'candidate_connection_failed')
        else:
            await peer.shutdown()
            self.fail('stateless_session_accepted')

    async def test_HE011_redirect_never_reaches_second_target(self):
        async def redirect(request):
            self.requests.append((request.method,str(request.url)))
            return httpx.Response(307,headers={'location':'https://127.0.0.1:19444/mcp'})
        self.respond=redirect
        with self.assertRaisesRegex(RuntimeError,'candidate_connection_failed'):
            await self.module.connect(**self.kw)
        self.assertEqual(self.requests,[('POST','https://127.0.0.1:19443/mcp')])

    async def test_HE012_cancelled_startup_releases_all_owned_resources(self):
        original=self.respond;entered=asyncio.Event();release=asyncio.Event()
        async def delayed(request):
            if request.method=='POST' and json.loads(request.content).get('method')=='initialize':
                entered.set();await release.wait()
            return await original(request)
        self.respond=delayed
        starting=asyncio.create_task(self.module.connect(**self.kw))
        await asyncio.wait_for(entered.wait(),1)
        starting.cancel();await asyncio.sleep(.01)
        starting.cancel();await asyncio.sleep(.01)
        self.assertFalse(starting.done())
        release.set()
        result=await asyncio.wait_for(asyncio.gather(starting,return_exceptions=True),2)
        self.assertIsInstance(result[0],(asyncio.CancelledError,RuntimeError))
        self.assertTrue(all(client.is_closed for client in self.clients))
        self.assertEqual(sum(m=='DELETE' for m,_ in self.requests),1)

    async def test_HE013_redirect_with_valid_mcp_body_still_refused(self):
        original=self.respond;redirect=False
        async def answer(request):
            response=await original(request)
            if redirect and request.method=='POST' and json.loads(request.content).get('method')=='tools/list':
                response.status_code=307
                response.headers['location']='https://127.0.0.1:19443/mcp'
            return response
        self.respond=answer
        peer=await self.module.connect(**self.kw)
        redirect=True
        try:
            try: await peer.session.list_tools()
            except Exception: pass
            else: self.fail('redirect_body_accepted_as_mcp_success')
        finally:
            with self.assertRaisesRegex(RuntimeError,'candidate_connection_failed'):
                await peer.shutdown()

    async def test_HE014_ca_certificate_is_not_an_exclusive_leaf(self):
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        key=await asyncio.to_thread(rsa.generate_private_key,public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME,'contract CA')])
        now=datetime.datetime.now(datetime.timezone.utc)
        certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(seconds=1))
            .not_valid_after(now+datetime.timedelta(minutes=10)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
            .sign(key,hashes.SHA256()))
        pem=certificate.public_bytes(serialization.Encoding.PEM).decode()
        pin=hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
        try: peer=await self.module.connect(**{**self.kw,'certificate':pem,'pin':pin})
        except ValueError as exc: self.assertEqual(str(exc),'candidate_handoff_invalid')
        else:
            await peer.shutdown();self.fail('ca_trust_accepted')
        self.assertEqual(self.clients,[])

if __name__ == '__main__': unittest.main(verbosity=2)
