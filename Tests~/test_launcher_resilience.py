"""Transient health failures must pause forwarding, not restart processes."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'Packages~/com.yukino.vrchat-agent-launcher/Editor/Runtime~/launcher_supervisor.py'
spec=importlib.util.spec_from_file_location('resilience_supervisor',p);s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)

def config(t):return {'parent_pid':123,'status_file':str(t/'status.json'),'stop_file':str(t/'stop'),'ssh_path':r'C:\Windows\ssh.exe','ssh_host':'example.org','uvx_path':r'C:\uvx.exe','expected_project':r'C:\Project'}

class ResilienceTests(unittest.TestCase):
 def test_single_timeout_suspends_and_recovers_same_ssh_without_restart(self):
  self.assertTrue(hasattr(s,'ProjectMonitor'),'held monitor missing')
  with tempfile.TemporaryDirectory() as td:
   t=Path(td);c=config(t);owner=Mock();owner.alive.return_value=True;owner.close.return_value=True
   child=Mock();child.poll.return_value=None
   def spawn(args,env,stderr_line_callback=None):
    stderr_line_callback('debug1: remote forward success for: listen 127.0.0.1:28082, connect 127.0.0.1:18082');return child
   owner.spawn.side_effect=spawn
   mon=Mock();mon.check.side_effect=[False,True,True,True];mon.reason='response_timeout';mon.step='project_info';mon.elapsed_ms=8000;mon.locked_catalog.return_value=True;mon.close.return_value=True
   relay=Mock();relay.cleanup.return_value=True;relay.drain.return_value=True
   phases=[];real=s.write_status;clock=[0];connected=[0]
   def now():return clock[0]
   def pause(_):clock[0]+=10
   def status(c,phase,code,**kw):
    phases.append(phase);real(c,phase,code,**kw)
    if phase=='suspended':
     state=json.loads((t/'status.json').read_text());(t/'resume-ack.json').write_text(json.dumps({'resume_nonce':state['resume_nonce']}))
     self.assertEqual(child.stop.call_count,0)
    if phase=='connected':
     connected[0]+=1
     if connected[0]==2:(t/'stop').touch()
   with patch.object(s,'ProjectMonitor',return_value=mon),patch.object(s,'Relay',return_value=relay),patch.object(s,'port_open',side_effect=lambda p:p==18081),patch.object(s,'probe_sidecar',return_value=True),patch.object(s,'probe_project',return_value=True),patch.object(s.time,'monotonic',side_effect=now),patch.object(s.time,'sleep',side_effect=pause),patch.object(s,'write_status',side_effect=status):
    self.assertEqual(s.supervise(c,owner),0)
   self.assertEqual(owner.spawn.call_count,1);self.assertEqual(connected[0],2);self.assertIn('suspended',phases);relay.pause.assert_called();relay.resume.assert_called_once();child.stop.assert_called_once();mon.close.assert_called_once()
 def test_unavailable_does_not_reset_deadline_and_missing_ack_never_resumes(self):
  self.assertTrue(hasattr(s,'ProjectMonitor'))
  for mode in ('unavailable','no_ack','active_permission','mismatch'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
    t=Path(td);c=config(t);owner=Mock();owner.alive.return_value=True;owner.close.return_value=True
    child=Mock();child.poll.return_value=None
    def spawn(args,env,stderr_line_callback=None):
     stderr_line_callback('debug1: remote forward success for: listen 127.0.0.1:28082, connect 127.0.0.1:18082');return child
    owner.spawn.side_effect=spawn;relay=Mock();relay.cleanup.return_value=True;relay.drain.return_value=True
    mon=Mock();mon.close.return_value=True;mon.reason='response_timeout';mon.step='project_info';mon.elapsed_ms=8000;mon.locked_catalog.return_value=mode!='active_permission'
    count=[0]
    def health():
     count[0]+=1
     if mode=='mismatch':raise s.ProjectIdentityMismatch()
     return mode!='unavailable' and count[0]>1
    mon.check.side_effect=health
    clock=[0];phases=[];real=s.write_status
    def status(c,phase,code,**kw):
     phases.append(phase);real(c,phase,code,**kw)
     if mode=='active_permission' and phase=='suspended':(t/'resume-ack.json').write_text(json.dumps({'resume_nonce':kw['resume_nonce']}))
    def tick(_):clock[0]+=10
    with patch.object(s,'ProjectMonitor',return_value=mon),patch.object(s,'Relay',return_value=relay),patch.object(s,'port_open',side_effect=lambda p:p==18081),patch.object(s,'probe_sidecar',return_value=True),patch.object(s,'probe_project',return_value=True),patch.object(s.time,'monotonic',side_effect=lambda:clock[0]),patch.object(s.time,'sleep',side_effect=tick),patch.object(s,'write_status',side_effect=status):
     self.assertEqual(s.supervise(c,owner),1)
    self.assertEqual(owner.spawn.call_count,1);relay.resume.assert_not_called();child.stop.assert_called_once()
    final=json.loads((t/'status.json').read_text());self.assertEqual(final['code'],'PROJECT_CHANGED' if mode=='mismatch' else 'CONNECTION_UNRESPONSIVE')
    self.assertEqual(phases.count('connected'),1)
 def test_resume_ack_bound_to_exact_local_episode(self):
  self.assertTrue(hasattr(s,'resume_acknowledged'))
  with tempfile.TemporaryDirectory() as td:
   t=Path(td);c=config(t);nonce='a'*64
   self.assertFalse(s.resume_acknowledged(c,nonce))
   (t/'resume-ack.json').write_text(json.dumps({'resume_nonce':'b'*64}));self.assertFalse(s.resume_acknowledged(c,nonce))
   (t/'resume-ack.json').write_text(json.dumps({'resume_nonce':nonce}));self.assertTrue(s.resume_acknowledged(c,nonce))
 def test_monitor_reuses_one_session_and_missing_instance_is_soft(self):
  self.assertTrue(hasattr(s,'ProjectMonitor'))
  session=Mock();session.ready=True;session.close.return_value=True
  with patch.object(s,'MCPSession',return_value=session),patch.object(s,'project_matches',side_effect=[TimeoutError(),True]):
   mon=s.ProjectMonitor(r'C:\Project');self.assertFalse(mon.check());self.assertTrue(mon.check());self.assertTrue(mon.close())
   session.close.assert_called_once()
 def test_real_loopback_response_slower_than_old_two_second_limit(self):
  from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
  import threading,time
  active=[True]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,format,*args):pass
   def do_POST(self):
    req=json.loads(self.rfile.read(int(self.headers['Content-Length'])));method=req['method'];extra={};code=200;result={}
    if method=='initialize':
     extra={'Mcp-Session-Id':'latency-test'};result={'protocolVersion':'2025-03-26','capabilities':{},'serverInfo':{'name':'mcp-for-unity-server'}}
    elif not active[0]:code=404
    elif method=='notifications/initialized':code=202
    elif method=='resources/read':
     time.sleep(2.3);uri=req['params']['uri'];result={'contents':[{'uri':uri,'text':json.dumps({'success':True,'data':{'projectRoot':'C:/Project'}})}]}
    data=json.dumps({'jsonrpc':'2.0','id':req.get('id'),'result':result}).encode() if code==200 else b''
    self.send_response(code)
    for k,v in extra.items():self.send_header(k,v)
    self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
   def do_DELETE(self):
    active[0]=False;self.send_response(204);self.send_header('Content-Length','0');self.end_headers()
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start();real=s.http.client.HTTPConnection
  session=s.MCPSession(18081,'mcp-for-unity-server')
  try:
   with patch.object(s.http.client,'HTTPConnection',side_effect=lambda host,port,**kw:real(host,server.server_port,**kw)):
    session.initialize();self.assertTrue(session.resource('mcpforunity://project/info')['success']);self.assertGreaterEqual(session.elapsed_ms,2200);self.assertTrue(session.close())
  finally:server.shutdown();server.server_close();thread.join(3)
  self.assertFalse(thread.is_alive())
 def test_monitor_reports_real_mismatch_not_transient(self):
  self.assertTrue(hasattr(s,'ProjectMonitor'))
  session=Mock();session.ready=True
  with patch.object(s,'MCPSession',return_value=session),patch.object(s,'project_matches',side_effect=s.ProjectIdentityMismatch()):
   with self.assertRaises(s.ProjectIdentityMismatch):s.ProjectMonitor(r'C:\Project').check()

if __name__=='__main__':unittest.main()
