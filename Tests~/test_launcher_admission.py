"""Real loopback requests prove suspended calls do not reach the fixture upstream."""
import importlib.util,json,sys,threading,unittest,http.client
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'Packages~/com.yukino.vrchat-agent-launcher/Editor/Runtime~'
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);assert spec and spec.loader
 m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
bridge=module('admission_audit',RUNTIME/'bridge.py');fixture=module('admission_fixture',ROOT/'Tools~/managed_bridge/test_bridge.py')
class AdmissionTests(unittest.TestCase):
 def request(self,server,method,params=None,token=None):
  headers={'Content-Type':'application/json','MCP-Protocol-Version':'2025-03-26'}
  if token:headers['Mcp-Session-Id']=token
  msg={'jsonrpc':'2.0','method':method,'params':params or {}}
  if method!='notifications/initialized':msg['id']=1
  c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
  try:
   c.request('POST','/mcp',body=json.dumps(msg),headers=headers);r=c.getresponse();raw=r.read();return r.status,r.getheader('Mcp-Session-Id'),json.loads(raw) if raw else None
  finally:c.close()
 def ready(self,front):
  status,token,_=self.request(front,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'test','version':'1'}});self.assertEqual(status,200)
  self.assertEqual(self.request(front,'notifications/initialized',token=token)[0],202)
  self.assertEqual(self.request(front,'tools/list',token=token)[0],200);return token
 def serverclass(self):
  self.assertTrue((RUNTIME/'admission_gate.py').exists(),'admission gate missing')
  return module('launcher_admission_test',RUNTIME/'admission_gate.py').make_server_class(bridge)
 def test_pause_blocks_tools_and_resources_but_preserves_session(self):
  cls=self.serverclass()
  with fixture.running(fixture.Upstream()) as upstream:
   with fixture.running(cls(('127.0.0.1',0),'http://127.0.0.1:'+str(upstream.server_port)+'/mcp')) as front:
    token=self.ready(front);front.pause();before=len(upstream.calls)
    for method,args in [('tools/call',{'name':'vrchat_me_apply','arguments':{}}),('resources/read',{'uri':'mcpforunity://project/info'})]:
     result=self.request(front,method,args,token);self.assertEqual(result[0],503);self.assertIn('not forwarded',result[2]['error']['message'])
    self.assertEqual(len(upstream.calls),before)
    self.assertEqual(self.request(front,'ping',token=token)[0],200)
    self.assertTrue(front.drain());front.resume()
    self.assertEqual(self.request(front,'tools/call',{'name':'vrchat_me_status','arguments':{}},token)[0],200)
    self.assertEqual(self.request(front,'tools/call',{'name':'execute_custom_tool','arguments':{}},token)[0],400)
 def test_inflight_finishes_once_new_paused_request_is_not_queued(self):
  cls=self.serverclass();entered=threading.Event();release=threading.Event()
  with fixture.running(fixture.Upstream()) as upstream:
   default=upstream.reply
   def slow(msg,headers):
    if msg['method']=='tools/call':entered.set();release.wait(3)
    return default(msg,headers)
   upstream.reply=slow
   with fixture.running(cls(('127.0.0.1',0),'http://127.0.0.1:'+str(upstream.server_port)+'/mcp')) as front,ThreadPoolExecutor(1) as pool:
    token=self.ready(front);future=pool.submit(self.request,front,'tools/call',{'name':'vrchat_me_status','arguments':{}},token)
    try:
     self.assertTrue(entered.wait(2));front.pause();count=len(upstream.calls)
     self.assertEqual(self.request(front,'tools/call',{'name':'vrchat_me_status','arguments':{}},token)[0],503)
     self.assertEqual(len(upstream.calls),count)
    finally:release.set()
    self.assertEqual(future.result(4)[0],200);self.assertTrue(front.drain());front.resume()
    self.assertEqual(sum(1 for _,msg,_ in upstream.calls if msg['method']=='tools/call'),1)
if __name__=='__main__':unittest.main()
