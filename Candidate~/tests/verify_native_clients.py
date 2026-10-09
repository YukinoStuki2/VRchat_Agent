"""Real native-client compatibility (Linux); not trusted delivery or Unity approval.
Only public certificates and non-secret test-home metadata may be written.
Credentials use child env or memory.
No model request, account login or existing configuration edit. Optional registry
mode registers only within an owned isolated Hermes process.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'native/src'),
               str(ROOT/'dependencies/mcp-1.29.1'), str(ROOT/'tests')]
from owned_descendants import Descendants
from test_bootstrap_runtime import child_environment
from owner_bootstrap import new_local_run, consume_environment
from candidate_runtime import create_app, create_server
from tls_context import load_tls_context
import uvicorn

async def run(args, report):
    watcher = Descendants()
    done = asyncio.Event()
    watching = asyncio.create_task(watcher.watch(os.getpid(), done))
    try:
        with tempfile.TemporaryDirectory(prefix='candidate-native-clients-') as temporary:
            home = Path(temporary)
            report['temporary_root'] = str(home)
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
                watcher.ports.add(port)
                owner = new_local_run('fixture-project' if args.approved_tasks else 'native-client-fixture',port,clients=('hermes','codex'))
                child = consume_environment(owner.project,port,environment=owner.take_environment())
                mcp_auth,unity_auth = child.verifiers()
                mcp = create_server(owner.project,mcp_auth=mcp_auth)
                app = create_app(mcp,unity_auth=unity_auth)
                created={}; deleted={}; request_counts={}; tool_calls={}; response_counts={}
                async def recording(scope, receive, send):
                    role='anonymous'
                    if scope['type']=='http':
                        bearer=dict(scope['headers']).get(b'authorization',b'')
                        for label,credential in owner.identity.credentials.items():
                            if bearer==('Bearer '+credential.token).encode():role=label
                        key=role+':'+scope['method'];request_counts[key]=request_counts.get(key,0)+1
                    async def recorded(message):
                        if message['type']=='http.response.start':
                            key=role+':'+scope['method']+':'+str(message['status'])
                            response_counts[key]=response_counts.get(key,0)+1
                        if message['type']=='http.response.start' and message['status']==200:
                            sid=dict(message.get('headers',[])).get(b'mcp-session-id')
                            if scope['method']=='POST' and sid:created.setdefault(role,set()).add(sid)
                            if scope['method']=='DELETE':
                                sid=dict(scope['headers']).get(b'mcp-session-id')
                                if sid:deleted.setdefault(role,set()).add(sid)
                        await send(message)
                    body=bytearray()
                    async def recorded_receive():
                        message=await receive()
                        if scope.get('method')=='POST' and message['type']=='http.request':
                            body.extend(message.get('body',b''))
                            assert len(body)<=65536
                            if not message.get('more_body',False) and body:
                                request=json.loads(body)
                                if request.get('method')=='tools/call':
                                    tool_calls.setdefault(role,[]).append(request['params']['name'])
                        return message
                    await app(scope,recorded_receive,recorded)
                config=uvicorn.Config(recording,log_level='error',access_log=False,timeout_graceful_shutdown=3)
                config.load();config.ssl=load_tls_context(owner.tls)
                server=uvicorn.Server(config)
                task=asyncio.create_task(server.serve(sockets=[listener]))
                processes=[]; captured=[]
                try:
                    async with asyncio.timeout(8):
                        while not server.started:
                            if task.done():await task;raise AssertionError('server_start_failed')
                            await asyncio.sleep(.02)
                    endpoint=f'https://127.0.0.1:{port}/mcp'
                    if args.approved_tasks:
                        from native_approved_tasks import check_approved_tasks
                        await check_approved_tasks(args, home, endpoint, owner, mcp._candidate_runtime,
                            processes, captured, report, created, deleted)
                    else:
                        hermes_home=home/'hermes';hermes_home.mkdir()
                        if (args.hermes_conversation or args.hermes_connection):
                            (hermes_home/'config.yaml').write_text('model:\n  context_length: 131072\n',encoding='utf-8')
                        env={**child_environment(hermes_home),'HERMES_HOME':str(hermes_home),
                             'VRCHAT_AGENT_TEST_TOKEN':owner.identity.credentials['hermes'].token}
                        if args.hermes_owned or args.hermes_binding or (args.hermes_conversation or args.hermes_connection):
                            env['VRCHAT_AGENT_TEST_PROBE_TOKEN']=owner.identity.credentials['probe'].token
                        process=await asyncio.create_subprocess_exec(args.hermes_python,'-I','-B',
                            str(ROOT/'tests/native_hermes_peer.py'),args.hermes_source,cwd=hermes_home,env=env,
                            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                        processes.append(process)
                        doc={'endpoint':endpoint,'certificate':owner.tls.certificate.decode(),
                             'registry':args.hermes_registry,'owned':args.hermes_owned,'binding':args.hermes_binding,'conversation':(args.hermes_conversation or args.hermes_connection)}
                        if args.hermes_connection:
                            from tls_context import issue_tls_material
                            other = issue_tls_material()
                            doc['fixed_connection']={'certificate':owner.tls.certificate.decode(),
                                'pin':owner.tls.pin,'expires_at':owner.identity.expires_at,
                                'other_certificate':other.certificate.decode(),'other_pin':other.pin}
                        out,err=await asyncio.wait_for(process.communicate((json.dumps(doc)+'\n').encode()),25)
                        captured.extend((out,err))
                        for line in out.decode().splitlines():
                            try: record=json.loads(line)
                            except ValueError: continue
                            if 'registry_diagnostic' in record:
                                report['hermes_registry_diagnostic']=record['registry_diagnostic']
                        if process.returncode:
                            report['hermes_failure']=json.loads(out.decode().splitlines()[-1])
                            raise AssertionError('native_hermes_failed')
                        report['hermes']=json.loads(out.decode().splitlines()[-1])
                        if args.hermes_registry:
                            assert report['hermes'].get('registry_verified') is True
                            assert report['hermes']['pass_ids']==[f'HR{i:03d}' for i in range(1,7)]
                            assert tool_calls.get('hermes')==['agent_status','agent_stop']
                            report['hermes_wire_tools']=tool_calls['hermes']
                        if args.hermes_owned or args.hermes_binding or (args.hermes_conversation or args.hermes_connection):
                            if (args.hermes_conversation or args.hermes_connection):
                                assert report['hermes'].get('conversation_verified') is True
                                prefix = 'HT' if args.hermes_connection else 'HN'
                                assert report['hermes']['pass_ids']==[f'{prefix}{i:03d}' for i in range(1,9 if args.hermes_connection else 6)]
                                if args.hermes_connection: assert report['hermes']['fixed_connection_verified']
                            elif args.hermes_binding:
                                assert report['hermes'].get('binding_verified') is True
                                assert report['hermes']['pass_ids']==[f'HB{i:03d}' for i in range(1,6)]
                            else:
                                assert report['hermes'].get('owned_shutdown_verified') is True
                                assert report['hermes']['pass_ids']==[f'HS{i:03d}' for i in range(1,5)]
                            assert len(created.get('probe',set()))==1
                            assert deleted.get('probe')==created['probe']
                            assert created['probe'].isdisjoint(created['hermes'])
                            assert tool_calls.get('hermes')==(['agent_status','agent_stop','agent_status'] if args.hermes_binding or (args.hermes_conversation or args.hermes_connection) else ['agent_status','agent_status'])
                            assert tool_calls.get('probe')==['agent_status']*3
                            report['hermes_owned_wire_tools']={role:tool_calls[role] for role in ('hermes','probe')}
                        assert len(created.get('hermes',set()))==(3 if args.hermes_connection else 2 if args.hermes_owned or args.hermes_binding or (args.hermes_conversation or args.hermes_connection) else 1)
                        assert deleted.get('hermes')==created['hermes']
                        if args.hermes_connection:
                            assert request_counts.get('anonymous:POST')==1
                            assert not created.get('anonymous')
                        codex_home=home/'codex';codex_home.mkdir()
                        ca=codex_home/'public-ca.pem';ca.write_bytes(owner.tls.certificate)
                        text='''[features]
    plugins = false
    [analytics]
    enabled = false
    [feedback]
    enabled = false
    [mcp_servers.candidate]
    url = ENDPOINT
    bearer_token_env_var = "VRCHAT_AGENT_TEST_TOKEN"
    startup_timeout_sec = 8
    tool_timeout_sec = 8
    enabled_tools = ["agent_status", "agent_stop"]
    required = true
    '''.replace('ENDPOINT',json.dumps(endpoint))
                        (codex_home/'config.toml').write_text(text,encoding='utf-8')
                        env={**child_environment(codex_home),'CODEX_HOME':str(codex_home),
                            'CODEX_CA_CERTIFICATE':str(ca),
                            'VRCHAT_AGENT_TEST_TOKEN':owner.identity.credentials['codex'].token}
                        process=await asyncio.create_subprocess_exec(args.codex,'app-server','--stdio',
                            cwd=codex_home,env=env,stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                        processes.append(process)
                        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
                        errors=asyncio.create_task(process.stderr.read())
                        async def request(number,method,params):
                            process.stdin.write((json.dumps({'id':number,'method':method,'params':params})+'\n').encode())
                            await process.stdin.drain()
                            async with asyncio.timeout(20):
                                while True:
                                    line=await process.stdout.readline()
                                    if not line:raise AssertionError('codex_eof')
                                    captured.append(line)
                                    value=json.loads(line)
                                    if value.get('id')==number:
                                        if 'error' in value:
                                            report['codex_error_code']=value['error'].get('code')
                                            raise AssertionError('codex_rpc_error')
                                        return value['result']
                        try:
                            await request(1,'initialize',{'clientInfo':{'name':'candidate-verifier','version':'1'},
                                                         'capabilities':{'experimentalApi':True}})
                            process.stdin.write(b'{"method":"initialized"}\n');await process.stdin.drain()
                            thread=await request(2,'thread/start',{'cwd':str(codex_home),'ephemeral':True,
                                'approvalPolicy':'on-request','sandbox':'read-only'})
                            thread_id=thread['thread']['id']
                            data=await request(3,'mcpServerStatus/list',{'detail':'toolsAndAuthOnly',
                                'serverName':'candidate','threadId':thread_id})
                            report['codex_inventory']=[{'name':v['name'],'tools':sorted(v['tools']),
                                'has_tools_error':v.get('toolsError') is not None, 'auth_status':v['authStatus']} for v in data['data']]
                            assert data['nextCursor'] is None and len(data['data'])==1
                            assert set(data['data'][0]['tools'])=={'agent_status','agent_stop'}
                            assert data['data'][0]['authStatus']=='bearerToken'
                            call=await request(4,'mcpServer/tool/call',{'threadId':thread_id,'server':'candidate',
                                'tool':'agent_status','arguments':{}})
                            assert call.get('isError') is True
                            assert any('expected_project_not_connected' in x.get('text','') for x in call['content'])
                            report['codex_missing_unity_refused']=True
                            stopped=await request(5,'mcpServer/tool/call',{'threadId':thread_id,'server':'candidate',
                                'tool':'agent_stop','arguments':{'task_id':'no-approved-plan'}})
                            assert not stopped.get('isError')
                            assert stopped['structuredContent']=={'success':True,'data':{'status':'locally_stopped','unity_confirmed':False}}
                            report['codex_unapproved_stop_local_only']=True
                            await request(6,'thread/unsubscribe',{'threadId':thread_id})
                        finally:
                            process.stdin.close()
                            try:await asyncio.wait_for(process.wait(),12)
                            except TimeoutError:process.kill();await process.wait();raise
                            captured.append(await errors)
                        assert process.returncode==0
                        report['codex_unrelated_plugin_sync_disabled']=not (codex_home/'.tmp/plugins.sync.lock').exists()
                        assert report['codex_unrelated_plugin_sync_disabled']
                        assert len(created.get('codex',set()))==1
                        assert deleted.get('codex')==created['codex']
                        assert created['hermes'].isdisjoint(created['codex'])
                        report['session_cleanup']={role:{'created':len(created[role]),'deleted':len(deleted[role])}
                                                   for role in (('hermes','codex','probe') if args.hermes_owned or args.hermes_binding or (args.hermes_conversation or args.hermes_connection) else ('hermes','codex'))}
                    report['requests']=request_counts
                finally:
                    report['requests']=dict(request_counts)
                    report['response_codes_before_safety_cleanup']=dict(response_counts)
                    report['session_counts_before_safety_cleanup']={role:{'created':len(created.get(role,set())),
                        'deleted':len(deleted.get(role,set()))} for role in ('hermes','codex')}
                    for process in processes:
                        if process.returncode is None:
                            process.kill();await process.communicate()
                    server.should_exit=True
                    await asyncio.wait_for(task,8)
                    report['runtime_sessions_empty']=not mcp._candidate_runtime.sessions
                    # Scan before preserving any reports or removing the test homes.
                    needles=[v.token.encode() for v in owner.identity.credentials.values()]+[b'PRIVATE KEY']
                    material=captured+[p.read_bytes() for p in home.rglob('*') if p.is_file()]
                    report['secret_scan_clean']=not any(n in b for b in material for n in needles)
                    assert report['secret_scan_clean']
                    for block in captured:
                        for line in block.splitlines():
                            try: failure=json.loads(line)
                            except (ValueError,UnicodeError): continue
                            if type(failure) is dict and set(failure)=={'handoff_diagnostic'}:
                                report['handoff_diagnostic']=failure['handoff_diagnostic']
                            if type(failure) is dict and set(failure)=={'error_type','frames'}:
                                report.setdefault('native_failure_frames',[]).append(failure)
                    report['resource_warnings_absent']=not any(b'ResourceWarning:' in b for b in captured)
                    assert report['resource_warnings_absent']
            with socket.socket() as check:
                assert check.connect_ex(('127.0.0.1',port))!=0
    finally:
        done.set();await watching
        report['descendants']=await watcher.finish()
        report['temporary_root_absent']=not Path(report.get('temporary_root','/')).exists()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--hermes-python',required=True);p.add_argument('--hermes-source',required=True)
    p.add_argument('--codex',required=True);p.add_argument('--output',required=True)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--approved-tasks',action='store_true',help='real clients, compiled gate/file fixture; not Unity')
    modes.add_argument('--hermes-registry',action='store_true',help='isolated native in-memory registry and dispatch; no model turn')
    modes.add_argument('--hermes-owned',action='store_true',help='native owned-task close beside a separate registered service; no shared gateway changes')
    modes.add_argument('--hermes-binding',action='store_true',help='candidate conversation-bound adapter and normal Hermes dispatch; no model turn')
    modes.add_argument('--hermes-conversation',action='store_true',help='new native AIAgent construction/executor with fixture tool messages; no model request')
    modes.add_argument('--hermes-connection',action='store_true',help='fixed-target SDK connection plus native AIAgent; fixture handoff, not gateway')
    p.add_argument('--hermes-handoff',action='store_true',help='with approved-tasks: real local IPC relay, fixture host selection; no SSH/gateway')
    p.add_argument('--hermes-chat',action='store_true',help='relocated plugin/native hooks and AIAgent; platform doubles, no model or platform traffic')
    p.add_argument('--hermes-ssh',action='store_true',help='with handoff: real loopback SSH auth/reverse-forward, not Windows/WAN')
    p.add_argument('--dotnet',default='/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet')
    args=p.parse_args()
    if args.hermes_chat and not args.hermes_handoff: p.error("chat requires handoff")
    if args.hermes_ssh and not args.hermes_handoff: p.error("SSH requires handoff")
    if args.hermes_handoff and not args.approved_tasks: p.error("handoff requires approved-tasks")
    if Path(args.output).exists():raise FileExistsError(args.output)
    report={'passed':False,'independent_approval':False,'trusted_delivery_verified':False,
        'unity_editor_verified':False,'codex_scope':'native MCP call in ephemeral thread; no model turn',
        'codex_ca_scope':'custom CA is additional trust, not exclusive certificate pinning'}
    paths=sorted(p for folder in ('runtime','launcher','native','dependencies','tests','package','clients','catalog')
        for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts
        and p.suffix in {'.py','.json','.cs','.csproj'})
    external={'codex_binary':Path(args.codex),'hermes_mcp_entry':Path(args.hermes_source)/'tools/mcp_tool.py'}
    if args.hermes_handoff or args.hermes_registry or args.hermes_owned or args.hermes_binding or (args.hermes_conversation or args.hermes_connection):
        for name in ('registry','mcp_schema_cache'):
            external['hermes_'+name]=Path(args.hermes_source)/('tools/'+name+'.py')
    if args.hermes_handoff or args.hermes_binding or (args.hermes_conversation or args.hermes_connection):
        external['hermes_model_tools']=Path(args.hermes_source)/'model_tools.py'
    if (args.hermes_conversation or args.hermes_connection):
        for name in ('run_agent.py','agent/agent_init.py','agent/tool_executor.py','tools/tool_search.py','toolsets.py'):
            external['hermes_'+name]=Path(args.hermes_source)/name
    if args.approved_tasks:
        import xml.etree.ElementTree as ET
        response=ET.parse(ROOT/'tests/unity-core/WirePeer.csproj').find('.//CandidateResponseSource').text
        external.update(dotnet_binary=Path(args.dotnet),upstream_response=Path(response))
        native_element=ET.parse(ROOT/'tests/unity-core/WirePeer.csproj').find('.//CandidateNativeRoot')
        assert native_element is not None and native_element.text
        native=Path(native_element.text)
        for name in ('Tools/ReadConsole.cs','Tools/ManageScene.cs','Tools/ManagePackages.cs','Helpers/ToolParams.cs','Helpers/ParamCoercion.cs','Helpers/StringCaseUtility.cs'):
            external['upstream_'+name]=native/name
    external_before={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in external.items()}
    report['native_inputs']=external_before
    report['expected_codex_version']='0.159.2'
    report['hermes_scope']=('installed public memory registration and tool-registry dispatch' if args.hermes_registry else 'installed native MCP engine')+'; not whole agent/model loop'
    if args.hermes_binding:
        report['hermes_scope']='candidate adapter through installed handle_function_call and registry; no model turn or live gateway'
    if (args.hermes_conversation or args.hermes_connection):
        report['hermes_scope']='candidate new AIAgent construction and native executor with fixture tool messages; no model request or live gateway'
    report['hermes_dependencies_fully_locked']=False
    before={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
    try:
        assert external_before['codex_binary']=='1748767b230ebfc3d4ab7e4e254920d0c0ad9691fd8c11f190e7d44511a4a92e', 'unreviewed_codex_binary'
        asyncio.run(run(args,report))
        report['passed']=bool(report['descendants']['clean'] and report['runtime_sessions_empty']
            and (not args.approved_tasks or (report.get('native_approved_pass_ids')==[f'NA{i:03d}' for i in range(1,7)] and report.get('native_console_pass_ids')==['NQ001','NQ002']
                and report.get('native_job_pass_ids')==['NJE001','NJE002']
                and report.get('native_live_pass_ids')==['NLE001','NLE002','NLE003','NLE004','NLE005','NLE006','NLE007','NLE008','NLE009','NLE010','NLE011','NLE012']
                and report.get('native_scene_pass_ids')==['NE001','NE002']
                and report.get('native_validate_pass_ids')==['NV001','NV002']
                and report.get('native_find_pass_ids')==['NF001','NF002']
                and report.get('native_object_pass_ids')==['NO001','NO002']
                and report.get('native_animator_pass_ids')==['NI001','NI002']
                and report.get('native_project_metadata_pass_ids')==['NMD001','NMD002']
                and report.get('native_editor_metadata_pass_ids')==['NEM001','NEM002']
                and report.get('native_menu_metadata_pass_ids')==['NMN001','NMN002']
                and report.get('native_package_metadata_pass_ids')==['NPK001','NPK002']
                and report.get('native_reflection_pass_ids')==['NRF001','NRF002']
                and report.get('native_clip_pass_ids')==['NCL001','NCL002'] and report.get('native_source_pass_ids')==['NSRC001','NSRC002']
                and report.get('native_hierarchy_pass_ids')==['NH001','NH002'])))
    except BaseException as exc:
        report['error_type']=type(exc).__name__
        import traceback
        report['error_frames']=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name}
            for f in traceback.extract_tb(exc.__traceback__)[-8:]]
    after={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
    report['source_unchanged']=before==after;report['source_hashes']=before
    report['native_inputs_unchanged']=external_before=={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in external.items()}
    report['passed']=bool(report['passed'] and report['source_unchanged'] and report.get('temporary_root_absent') and report['native_inputs_unchanged'])
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_hashes'}));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
