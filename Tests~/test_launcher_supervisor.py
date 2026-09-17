"""Launcher tests: no real network listeners, SSH, or Unity required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

RUNTIME = Path(__file__).resolve().parents[1] / 'Packages~/com.yukino.vrchat-agent-launcher/Editor/Runtime~'
SPEC = importlib.util.spec_from_file_location('launcher_supervisor', RUNTIME / 'launcher_supervisor.py')
s = importlib.util.module_from_spec(SPEC) if SPEC and SPEC.loader and Path(SPEC.origin).exists() else None
if s:
    sys.modules[SPEC.name] = s
    SPEC.loader.exec_module(s)


def config(**updates):
    raw = dict(parent_pid=123, status_file=r'C:\Temp\launcher.json',
               ssh_path=r'C:\Windows\System32\OpenSSH\ssh.exe',
               ssh_host='example.org', stop_file=r'C:\Temp\launcher.stop',
               uvx_path=r'C:\Tools\uvx.exe', expected_project=r'C:\Projects\Avatar')
    raw.update(updates)
    return raw


class ConfigurationTests(unittest.TestCase):
    def test_fixed_commands_and_strict_configuration(self):
        self.assertIsNotNone(s, 'supervisor implementation missing')
        c = s.validate_config(config())
        bridge, ssh = s.build_commands(c)
        self.assertEqual(bridge, [sys.executable, '-I', str(RUNTIME / 'bridge.py'),
                                '--upstream', 'http://127.0.0.1:18081/mcp', '--listen', '127.0.0.1', '--port', '18082'])
        self.assertIn('127.0.0.1:28082:127.0.0.1:18082', ssh)
        for option in ['BatchMode=yes', 'StrictHostKeyChecking=yes', 'ExitOnForwardFailure=yes']:
            self.assertIn(option, ssh)
        self.assertEqual(ssh[-1], 'example.org')
        self.assertEqual(ssh[1:3], ['-F', s.os.devnull])
        self.assertEqual(s.sidecar_command(c), [c['uvx_path'], '--from', 'mcpforunityserver==10.2.0', 'mcp-for-unity', '--transport', 'http', '--http-url', 'http://127.0.0.1:18081', '--http-host', '127.0.0.1', '--http-port', '18081', '--project-scoped-tools'])
        env = {'UNITY_MCP_HTTP_URL': 'secret', 'unity_mcp_http_extra': 'bad', 'PATH': 'safe'}
        self.assertEqual(s.child_environment(env), {'PATH': 'safe'})
        self.assertIn('UNITY_MCP_HTTP_URL', env)
        self.assertEqual(s.build_commands(s.validate_config(config(ssh_host='example.org', ssh_user='alice', ssh_port=2222, remote_port=30000)))[1][-1], 'alice@example.org')
        for key, value in [('ssh_host', '-oProxyCommand=evil'), ('ssh_host', 'a b'), ('ssh_host', 'a@b'),
                           ('ssh_user', '-root'), ('ssh_user', 'a;b'), ('ssh_port', True), ('remote_port', '28082'),
                           ('remote_port', 28080), ('remote_port', 65536), ('parent_pid', 0), ('password', 'secret'), ('command', ['evil']),
                           ('ssh_path', 'ssh.exe'), ('ssh_path', r'C:\ssh.cmd'),
                           ('uvx_path', 'uvx.exe'), ('uvx_path', r'C:\Tools\other.exe'),
                           ('expected_project', 'relative'), ('stop_file', 'relative.stop'), ('ssh_host', 'a\n')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                s.validate_config(config(**{key: value}))


class FakeHTTP:
    def __init__(self, results, sse=False):
        self.results = iter(results)
        self.calls = []
        self.sse = sse
        self.closed = 0

    def factory(self, host, port, timeout):
        import io
        owner = self
        class Connection:
            sock = Mock()
            def connect(self): pass
            def request(self, method, path, body=None, headers=None):
                self.msg = json.loads(body) if body else None
                owner.calls.append((method, path, self.msg, headers, host, port, timeout))
            def getresponse(self):
                item = next(owner.results)
                code = item if type(item) is int else 200
                obj = {'jsonrpc': '2.0', 'id': self.msg['id'], 'result': item} if code == 200 else None
                data = json.dumps(obj).encode() if obj else b''
                if owner.sse and obj:
                    data = b'event: message\ndata: ' + data + b'\n\n'
                r = io.BytesIO(data)
                r.status = code
                r.getheader = lambda name, default=None: {'Mcp-Session-Id': 'safe-session', 'Content-Type': 'text/event-stream' if owner.sse else 'application/json'}.get(name, default)
                return r
            def close(self): owner.closed += 1
        return Connection()


def initialized(name):
    return {'protocolVersion': '2025-03-26', 'serverInfo': {'name': name}, 'capabilities': {}}


def resource(uri, payload):
    return {'contents': [{'uri': uri, 'text': json.dumps(payload)}]}


class ReadinessTests(unittest.TestCase):
    def test_sidecar_identity_real_initialize_sse_and_cleanup(self):
        self.assertTrue(hasattr(s, 'probe_sidecar'), 'sidecar protocol verification missing')
        for sse in (False, True):
            fake = FakeHTTP([initialized('mcp-for-unity-server'), 202, 204, 404], sse)
            with patch.object(s.http.client, 'HTTPConnection', side_effect=fake.factory):
                self.assertTrue(s.probe_sidecar())
            self.assertEqual([c[0] for c in fake.calls], ['POST', 'POST', 'DELETE', 'POST'])
            self.assertEqual(fake.calls[0][2]['method'], 'initialize')
            self.assertEqual(fake.calls[1][2]['method'], 'notifications/initialized')
            self.assertEqual(fake.calls[2][3]['Mcp-Session-Id'], 'safe-session')
            self.assertEqual(fake.closed, 4)
        fake = FakeHTTP([initialized('not-unity'), 204, 404])
        with patch.object(s.http.client, 'HTTPConnection', side_effect=fake.factory):
            self.assertFalse(s.probe_sidecar())

    def test_exact_single_project_before_tools(self):
        self.assertTrue(hasattr(s, 'probe_project'), 'project check missing')
        uri = 'mcpforunity://instances'
        row = {'id': 'Avatar@123', 'name': 'Avatar'}
        for count, path, good in [(0, r'C:\Projects\Avatar', False), (2, r'C:\Projects\Avatar', False),
                                  (1, r'C:\Other', False), (1, 'c:/projects/avatar/', True)]:
            instances = resource(uri, {'success': True, 'transport': 'http', 'instance_count': count, 'instances': [dict(row,id='Avatar@'+str(i)) for i in range(count)]})
            results = [initialized('mcp-for-unity-server'), 202, instances]
            if count == 1:
                results.append(resource('mcpforunity://project/info', {'success': True, 'data': {'projectRoot': path}}))
                if good: results.append(instances)
            results += [204, 404]
            fake = FakeHTTP(results)
            with patch.object(s.http.client, 'HTTPConnection', side_effect=fake.factory):
                if count > 1 or path == r'C:\Other':
                    with self.assertRaises(s.ProjectIdentityMismatch):s.probe_project(r'C:\Projects\Avatar')
                else:self.assertEqual(s.probe_project(r'C:\Projects\Avatar'), good)
            self.assertFalse(any(c[2] and c[2]['method'].startswith('tools/') for c in fake.calls))

    def test_bridge_complete_catalog_and_inactive_status_no_delete(self):
        self.assertTrue(hasattr(s, 'probe_bridge'), 'bridge protocol readiness missing')
        for active, good in [(False, True), (True, False)]:
            rows = [{'name': name} for name in s.AUDITED_TOOLS]
            status = {'content': [{'type': 'text', 'text': json.dumps({'success': True, 'data': {'active': active, 'permission_changed': False}})}]}
            fake = FakeHTTP([initialized('vrchat-managed-bridge'), 202, {'tools': rows}, status])
            with patch.object(s.http.client, 'HTTPConnection', side_effect=fake.factory):
                self.assertEqual(s.probe_bridge(), good)
            self.assertEqual([c[2]['method'] for c in fake.calls], ['initialize', 'notifications/initialized', 'tools/list', 'tools/call'])
            self.assertEqual(fake.calls[-1][2]['params'], {'name': 'vrchat_me_status', 'arguments': {}})
            self.assertTrue(all(c[0] == 'POST' for c in fake.calls))
        fake = FakeHTTP([initialized('vrchat-managed-bridge'), 202, {'tools': []}])
        with patch.object(s.http.client, 'HTTPConnection', side_effect=fake.factory):
            self.assertFalse(s.probe_bridge())


# Native process-handle ownership is tested separately in test_launcher_windows.py.
# Lifecycle below targets the final controller interface, replacing unfinished
# implementation-specific WindowsJob/Supervisor class sketches.

class LifecycleTests(unittest.TestCase):
    def test_controller_stopfile_reaps_real_fixture_child(self):
        self.assertTrue(hasattr(s, 'supervise'), 'controller missing')
        import os, time
        with tempfile.TemporaryDirectory() as td:
            t=Path(td); c=config(parent_pid=os.getpid(),status_file=str(t/'status.json'),stop_file=str(t/'stop'))
            child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
            class Child:
                def poll(self): return child.poll()
                def stop(self):
                    if child.poll() is None:child.terminate()
                    child.wait(timeout=3)
            class Owner:
                def alive(self):return True
                def spawn(self,args,env,stderr_line_callback=None):
                    if stderr_line_callback:stderr_line_callback('debug1: remote forward success for: listen 127.0.0.1:28082, connect 127.0.0.1:18082')
                    return Child()
                def close(self):Child().stop();return True
            relay=Mock();relay.cleanup.return_value=True
            def pause(_): (t/'stop').touch()
            try:
                with patch.object(s,'port_open',side_effect=lambda p:p==18081),patch.object(s,'probe_sidecar',return_value=True),patch.object(s,'probe_project',return_value=True),patch.object(s,'Relay',return_value=relay),patch.object(s.time,'sleep',side_effect=pause):
                    self.assertEqual(s.supervise(c,Owner()),0)
                status=json.loads((t/'status.json').read_text());self.assertTrue(status['cleanup_complete']);self.assertEqual(status['phase'],'stopped');self.assertIsNotNone(child.poll())
            finally:
                if child.poll() is None:child.terminate();child.wait(timeout=3)
    def test_parent_exit_stops_without_start(self):
        self.assertTrue(hasattr(s,'supervise'),'controller missing')
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);c=config(status_file=str(t/'status.json'),stop_file=str(t/'stop'))
            owner=Mock();owner.alive.return_value=False;owner.close.return_value=True
            self.assertEqual(s.supervise(c,owner),0);owner.spawn.assert_not_called();owner.close.assert_called_once()
    def test_port_conflict_no_unknown_process_stopped(self):
        self.assertTrue(hasattr(s,'supervise'),'controller missing')
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);c=config(status_file=str(t/'status.json'),stop_file=str(t/'stop'))
            owner=Mock();owner.alive.return_value=True;owner.close.return_value=True
            with patch.object(s,'port_open',return_value=True):self.assertEqual(s.supervise(c,owner),1)
            owner.spawn.assert_not_called();self.assertTrue(json.loads((t/'status.json').read_text())['cleanup_complete'])
    def test_remote_ack_must_match_exact_forward(self):
        self.assertTrue(hasattr(s,'SSHProgress'),'ssh readiness missing')
        p=s.SSHProgress(28082)
        p.line('debug1: remote forward success for: listen 127.0.0.1:28080, connect 127.0.0.1:18081');self.assertFalse(p.ready)
        p.line('debug1: remote forward success for: listen 127.0.0.1:28082, connect 127.0.0.1:18082');self.assertTrue(p.ready)
        p.line('Permission denied (publickey).');self.assertEqual(p.error,'SSH_AUTH_FAILED')

class RelayIntegrationTests(unittest.TestCase):
    def test_real_http_bridge_probe_and_session_cleanup(self):
        import threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        active=set()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,format,*args):pass
            def do_POST(self):
                req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                method=req['method'];token=self.headers.get('Mcp-Session-Id');status=200;result={};extra={}
                if method=='initialize':
                    token='test-session';active.add(token);extra['Mcp-Session-Id']=token
                    result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'mcp-for-unity-server','version':'fixture'}}
                elif token not in active:status=404
                elif method=='notifications/initialized':status=202
                elif method=='tools/list':result={'tools':[{'name':n,'inputSchema':{'type':'object','properties':{}}} for n in s.AUDITED_TOOLS]}
                elif method=='tools/call':result={'content':[{'type':'text','text':json.dumps({'success':True,'data':{'active':False,'permission_changed':False}})}]}
                body=json.dumps({'jsonrpc':'2.0','id':req.get('id'),'result':result}).encode() if status==200 else b''
                self.send_response(status)
                for k,v in extra.items():self.send_header(k,v)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_DELETE(self):
                active.discard(self.headers.get('Mcp-Session-Id'));self.send_response(204);self.send_header('Content-Length','0');self.end_headers()
        upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=upstream.serve_forever);t.start()
        relay=s.Relay();relay.server=s._audit._Server(('127.0.0.1',0),'http://127.0.0.1:'+str(upstream.server_port)+'/mcp')
        relay.thread=threading.Thread(target=relay.server.serve_forever);relay.thread.start()
        real=s.http.client.HTTPConnection
        def connect(host,port,**kwargs):return real(host,relay.server.server_port if port==18082 else port,**kwargs)
        try:
            with patch.object(s.http.client,'HTTPConnection',side_effect=connect):self.assertTrue(relay.verify())
            self.assertEqual(len(active),1)
            self.assertTrue(relay.cleanup());self.assertFalse(active)
        finally:
            if relay.thread.is_alive():relay.cleanup()
            upstream.shutdown();upstream.server_close();t.join(3)
        self.assertFalse(t.is_alive());self.assertFalse(relay.thread.is_alive())

class CleanupRegressionTests(unittest.TestCase):
    def test_failed_delete_stays_failed_and_retains_token(self):
        fake=FakeHTTP([initialized('mcp-for-unity-server'),202,500])
        with patch.object(s.http.client,'HTTPConnection',side_effect=fake.factory):
            session=s.MCPSession(18081,'mcp-for-unity-server');session.initialize()
            self.assertFalse(session.close());self.assertFalse(session.close());self.assertIsNotNone(session.token)
        self.assertEqual(len(fake.calls),3)
    def test_started_missing_token_is_unresolved(self):
        session=s.MCPSession(18081,'mcp-for-unity-server');session.started=True
        self.assertFalse(session.close())
    def test_cleanup_failure_propagates_not_retryable(self):
        self.assertTrue(hasattr(s,'CleanupUnresolved'))
        fake=FakeHTTP([initialized('mcp-for-unity-server'),202,500])
        with patch.object(s.http.client,'HTTPConnection',side_effect=fake.factory):
            with self.assertRaises(s.CleanupUnresolved):s.probe_sidecar()
    def test_debt_blocks_final_clean_claim(self):
        self.assertTrue(hasattr(s,'CleanupUnresolved'))
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);c=config(status_file=str(t/'status'),stop_file=str(t/'stop'))
            owner=Mock();owner.alive.return_value=True;owner.close.return_value=True
            with patch.object(s,'port_open',side_effect=lambda p:p==18081),patch.object(s,'probe_sidecar',side_effect=s.CleanupUnresolved()):
                self.assertEqual(s.supervise(c,owner),1)
            self.assertFalse(json.loads((t/'status').read_text())['cleanup_complete']);owner.spawn.assert_not_called()
    def test_identity_changed_after_ssh_never_connected(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);c=config(status_file=str(t/'status'),stop_file=str(t/'stop'))
            child=Mock();child.poll.return_value=None
            owner=Mock();owner.alive.return_value=True;owner.close.return_value=True
            def spawn(args,env,stderr_line_callback=None):
                stderr_line_callback('debug1: remote forward success for: listen 127.0.0.1:28082, connect 127.0.0.1:18082');return child
            owner.spawn.side_effect=spawn;relay=Mock();relay.cleanup.return_value=True
            phases=[];real=s.write_status
            def status(c,p,code,**kw):phases.append(p);real(c,p,code,**kw)
            with patch.object(s,'port_open',side_effect=lambda p:p==18081),patch.object(s,'probe_sidecar',return_value=True),patch.object(s,'probe_project',side_effect=[True,False]),patch.object(s,'Relay',return_value=relay),patch.object(s,'write_status',side_effect=status):
                self.assertEqual(s.supervise(c,owner),1)
            self.assertNotIn('connected',phases);child.stop.assert_called_once()

class ImportDiagnosticTests(unittest.TestCase):
    def test_missing_instance_is_unavailable_not_mismatch(self):
        self.assertTrue(hasattr(s,'ProjectIdentityMismatch'),'specific identity exception missing')
        session=Mock();session.resource.return_value={'success':True,'transport':'http','instance_count':0,'instances':[]};session.close.return_value=True
        with patch.object(s,'MCPSession',return_value=session):self.assertFalse(s.probe_project('F:/VRchat/Yuzuki'))
    def test_observed_different_or_multiple_projects_is_mismatch(self):
        self.assertTrue(hasattr(s,'ProjectIdentityMismatch'),'specific identity exception missing')
        cases=[ [{'transport':'http','instance_count':2,'instances':[{'id':'a'},{'id':'b'}]}], [{'transport':'http','instance_count':1,'instances':[{'id':'a'}]},{'data':{'projectRoot':'F:/Other'}}] ]
        for replies in cases:
            session=Mock();session.resource.side_effect=replies;session.close.return_value=True
            with patch.object(s,'MCPSession',return_value=session):
                with self.assertRaises(s.ProjectIdentityMismatch):s.probe_project('F:/VRchat/Yuzuki')
            session.close.assert_called_once()
    def test_timeout_unavailable_and_cleanup_debt_still_blocks(self):
        session=Mock();session.resource.side_effect=TimeoutError();session.close.return_value=True
        with patch.object(s,'MCPSession',return_value=session):self.assertFalse(s.probe_project('F:/VRchat/Yuzuki'))
        session.close.return_value=False
        with patch.object(s,'MCPSession',return_value=session):
            with self.assertRaises(s.CleanupUnresolved):s.probe_project('F:/VRchat/Yuzuki')
    def test_import_stopfile_after_inflight_probe_wins(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);c=config(status_file=str(t/'status'),stop_file=str(t/'stop'))
            child=Mock();child.poll.return_value=None
            owner=Mock();owner.alive.return_value=True;owner.close.return_value=True
            def spawn(args,env,stderr_line_callback=None):
                stderr_line_callback('debug1: remote forward success for: listen 127.0.0.1:28082, connect 127.0.0.1:18082');return child
            owner.spawn.side_effect=spawn;relay=Mock();relay.cleanup.return_value=True
            count=[0]
            def probe(expected):
                count[0]+=1
                if count[0]==2:(t/'stop').touch();return False
                return True
            with patch.object(s,'port_open',side_effect=lambda p:p==18081),patch.object(s,'probe_sidecar',return_value=True),patch.object(s,'probe_project',side_effect=probe),patch.object(s,'Relay',return_value=relay):
                self.assertEqual(s.supervise(c,owner),0)
            state=json.loads((t/'status').read_text());self.assertEqual(state['code'],'STOPPED');self.assertTrue(state['cleanup_complete'])

if __name__ == '__main__':
    unittest.main()
