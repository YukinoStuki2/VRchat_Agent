"""Manual Windows bridge/SSH supervisor. No sidecar installer or credential API."""
import http.client
import json
import ntpath
import os
from pathlib import Path
import re
import sys

BRIDGE = Path(__file__).resolve().with_name('bridge.py')


def absolute_path(value):
    if (type(value) is not str or not value or any(ord(c) < 32 for c in value)
            or '"' in value or value.startswith(('\\\\', '//'))
            or not (Path(value).is_absolute() or (ntpath.isabs(value) and ntpath.splitdrive(value)[0]))):
        raise ValueError('Expected absolute local path')
    return value


def validate_config(raw):
    required = {'parent_pid', 'stop_file', 'status_file', 'ssh_path', 'ssh_host', 'uvx_path', 'expected_project'}
    if type(raw) is not dict or not required <= raw.keys() or not raw.keys() <= required | {'ssh_user', 'ssh_port', 'remote_port', 'bridge_path'}:
        raise ValueError('Invalid configuration fields')
    c = dict(raw)
    for key, default, maximum in [('parent_pid', None, 4294967295), ('ssh_port', 22, 65535), ('remote_port', 28082, 65535)]:
        value = c.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('Invalid integer configuration')
        c[key] = value
    if c['remote_port'] == 28080:
        raise ValueError('Old direct-forward port is not supported')
    for key in ('stop_file', 'status_file', 'ssh_path', 'uvx_path', 'expected_project'):
        absolute_path(c[key])
    if ntpath.basename(c['uvx_path']).lower() != 'uvx.exe':
        raise ValueError('Expected trusted uvx.exe')
    if not c['ssh_path'].lower().endswith('.exe'):
        raise ValueError('SSH must be a trusted executable, not a shell script')
    if ntpath.normcase(ntpath.normpath(c['stop_file'])) == ntpath.normcase(ntpath.normpath(c['status_file'])):
        raise ValueError('Status and stop paths must differ')
    if type(c['ssh_host']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}', c['ssh_host']) is None:
        raise ValueError('Invalid SSH host')
    user = c.get('ssh_user', '')
    if type(user) is not str or (user and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', user) is None):
        raise ValueError('Invalid SSH user')
    c['ssh_user'] = user
    if 'bridge_path' in c and Path(absolute_path(c['bridge_path'])).resolve() != BRIDGE:
        raise ValueError('Only the bundled bridge is supported')
    return c


def build_commands(config):
    c = validate_config(config)
    bridge = [sys.executable, '-I', str(BRIDGE), '--upstream', 'http://127.0.0.1:18081/mcp', '--listen', '127.0.0.1', '--port', '18082']
    ssh = [c['ssh_path'], '-F', os.devnull, '-v', '-N', '-T']
    for option in ('BatchMode=yes', 'StrictHostKeyChecking=yes', 'ExitOnForwardFailure=yes', 'ServerAliveInterval=15', 'ServerAliveCountMax=2'):
        ssh.extend(['-o', option])
    ssh.extend(['-p', str(c['ssh_port']), '-R', f"127.0.0.1:{c['remote_port']}:127.0.0.1:18082",
                (c['ssh_user'] + '@' if c['ssh_user'] else '') + c['ssh_host']])
    return bridge, ssh


def sidecar_command(config):
    c = validate_config(config)
    return [c['uvx_path'], '--from', 'mcpforunityserver==10.2.0', 'mcp-for-unity',
            '--transport', 'http', '--http-url', 'http://127.0.0.1:18081',
            '--http-host', '127.0.0.1', '--http-port', '18081', '--project-scoped-tools']


def child_environment(source=None):
    source = os.environ if source is None else source
    return {k: v for k, v in source.items() if not k.upper().startswith(('UNITY_MCP_HTTP', 'UNITY_MCP_API_KEY'))
            and k.upper() not in {'UNITY_MCP_DEFAULT_INSTANCE', 'UNITY_MCP_ENABLE_HTTP_SERVER'}}


# Load by absolute filename: -I deliberately excludes the script directory.
import importlib.util
import socket
import threading

_spec = importlib.util.spec_from_file_location('_launcher_audited_bridge', BRIDGE)
_audit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _audit
_spec.loader.exec_module(_audit)
AUDITED_TOOLS = _audit.TOOLS
PROTOCOL = '2025-03-26'
MAX_REPLY = 1024 * 1024
PROBE_ERRORS = (ValueError, KeyError, TypeError, OSError, http.client.HTTPException,
                RecursionError, _audit.Rejected)


def require(value):
    if not value:
        raise ValueError('Readiness check failed')


class MCPSession:
    """Fixed loopback MCP only; no proxy/DNS/redirect or arbitrary method API."""
    def __init__(self, port, identity):
        require((port, identity) in {(18081, 'mcp-for-unity-server'), (18082, 'vrchat-managed-bridge')})
        self.port, self.identity = port, identity
        self.token, self.version = None, PROTOCOL
        self.ready = False
        self.started = False
        self.close_result = None
        self.sequence = 0
        self.last_step = "initialize"
        self.elapsed_ms = 0
        self.deadline_expired = False

    def exchange(self, method, params=None, *, verb='POST', status_only=False):
        started_at = time.monotonic()
        self.deadline_expired = False
        self.sequence += 1
        msg = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if method != 'notifications/initialized':
            msg['id'] = 'launcher-' + str(self.sequence)
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'Connection': 'close', 'MCP-Protocol-Version': self.version}
        if self.token:
            headers['Mcp-Session-Id'] = self.token
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        response = timer = None
        try:
            connection.connect()
            connection.sock.settimeout(8)
            # A total deadline also bounds drip-fed SSE/HTTP bodies.
            def deadline():
                self.deadline_expired = True
                _audit.abort_socket(connection.sock)
            timer = threading.Timer(8, deadline)
            timer.daemon = True
            timer.start()
            connection.request(verb, '/mcp', body=b'' if verb == 'DELETE' else json.dumps(msg).encode(), headers=headers)
            response = connection.getresponse()
            token = response.getheader('Mcp-Session-Id')
            if method == 'initialize' and self.token is None and type(token) is str and re.fullmatch(r'[!-~]{1,256}', token):
                self.token = token  # Capture allocation even if subsequent parsing fails.
            require(token is None or token == self.token)
            require(response.getheader('Content-Encoding') in (None, 'identity'))
            length = response.getheader('Content-Length')
            require(length is None or (re.fullmatch(r'[0-9]{1,9}', length) and int(length) <= MAX_REPLY))
            if status_only:
                require(len(response.read(MAX_REPLY + 1)) <= MAX_REPLY)
                return response.status
            if method == 'notifications/initialized':
                require(response.status == 202 and response.read(1) == b'')
                return None
            require(response.status == 200)
            content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
            if content_type == 'text/event-stream':
                obj = _audit.parse_sse(response, msg, MAX_REPLY)
            else:
                require(content_type == 'application/json')
                raw = response.read(MAX_REPLY + 1)
                require(len(raw) <= MAX_REPLY)
                obj = _audit.validate_response(_audit.decode_json(raw), msg)
            require('result' in obj)
            return obj['result']
        finally:
            if timer:
                timer.cancel()
                timer.join()
            if response is not None:
                response.close()
            connection.close()
            self.elapsed_ms = int((time.monotonic() - started_at) * 1000)

    def initialize(self):
        if self.ready:
            return
        require(not self.started)
        self.started = True
        result = self.exchange('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {},
                                              'clientInfo': {'name': 'vrchat-launcher-readiness', 'version': '1'}})
        require(self.token and result['serverInfo']['name'] == self.identity)
        require(result['protocolVersion'] in _audit.PROTOCOL_VERSIONS and type(result['capabilities']) is dict)
        self.version = result['protocolVersion']
        self.exchange('notifications/initialized')
        self.ready = True

    def resource(self, uri):
        self.last_step = 'instances' if uri == 'mcpforunity://instances' else 'project_info'
        result = self.exchange('resources/read', {'uri': uri})
        rows = result['contents']
        require(type(rows) is list and len(rows) == 1 and rows[0]['uri'] == uri and type(rows[0]['text']) is str)
        payload = _audit.decode_json(rows[0]['text'])
        require(type(payload) is dict and payload.get('success') is True)
        return payload

    def close(self):
        # Sticky result: failed/unknown cleanup is never silently forgotten or retried.
        if self.close_result is not None:return self.close_result
        if self.port == 18082:
            return True  # This session is tracked by our Relay server's TTL/shutdown.
        self.close_result = False
        if not self.started:
            self.close_result = True
        elif self.token:
            try:
                status = self.exchange('ping', verb='DELETE', status_only=True)
                self.close_result = status == 404 or (status in (200,204) and self.exchange('ping', status_only=True) == 404)
            except PROBE_ERRORS:
                pass
        if self.close_result:self.token=None
        return self.close_result


class CleanupUnresolved(Exception):
    """Direct upstream allocation was not confirmed absent; do not allocate again."""


def probe_sidecar():
    session = MCPSession(18081, 'mcp-for-unity-server')
    good = False
    try:
        session.initialize()
        good = True
    except PROBE_ERRORS:
        pass
    if not session.close():raise CleanupUnresolved()
    return good


class ProjectUnavailable(ValueError):
    def __init__(self, reason):self.reason=reason


class ProjectIdentityMismatch(ValueError):
    """Only observed different path or multiple valid instances, not timeouts."""


def project_matches(session, expected):
    instances = session.resource('mcpforunity://instances')
    rows = instances['instances']
    require(instances.get('transport') == 'http' and type(instances.get('instance_count')) is int)
    require(type(rows) is list and len(rows) == instances['instance_count'])
    require(all(type(row) is dict and type(row.get('id')) is str and bool(row['id']) for row in rows))
    require(len({row['id'] for row in rows}) == len(rows))
    if len(rows) > 1:raise ProjectIdentityMismatch()
    if not rows:raise ProjectUnavailable("no_instance")
    require(len(rows) == 1)
    project = session.resource('mcpforunity://project/info')
    actual = absolute_path(project['data']['projectRoot'])
    if ntpath.normcase(ntpath.normpath(actual)) != ntpath.normcase(ntpath.normpath(expected)):
        raise ProjectIdentityMismatch()
    # Reject concurrent changes while reading project information.
    after = session.resource('mcpforunity://instances')
    if after != instances:raise ProjectUnavailable("instance_snapshot_changed")
    return True


def probe_project(expected):
    session = MCPSession(18081, 'mcp-for-unity-server')
    good = False
    mismatch = False
    try:
        session.initialize()
        good = project_matches(session, expected)
    except ProjectIdentityMismatch:
        mismatch = True
    except PROBE_ERRORS:
        pass
    if not session.close():raise CleanupUnresolved()
    if mismatch:raise ProjectIdentityMismatch()
    return good


class ProjectMonitor:
    def __init__(self, expected):
        self.expected=expected
        self.session=MCPSession(18081,'mcp-for-unity-server')
        self.reason='none';self.step='initialize';self.elapsed_ms=0
    def open(self):
        self.session.initialize()  # no repeated allocations on an uncertain handshake
    def check(self):
        started=time.monotonic()
        try:
            self.session.initialize()
            good=project_matches(self.session,self.expected)
            self.reason='none'
            return good
        except ProjectIdentityMismatch:
            self.reason='identity_changed'
            raise
        except ProjectUnavailable as exc:
            self.reason=exc.reason
            return False
        except PROBE_ERRORS as exc:
            self.reason='response_timeout' if isinstance(exc,TimeoutError) or self.session.deadline_expired is True else 'transport_or_invalid_response'
            return False
        finally:
            self.step=self.session.last_step
            self.elapsed_ms=int((time.monotonic()-started)*1000)
    def locked_catalog(self):
        try:
            catalog=self.session.exchange('tools/list')
            _audit.filter_tools(catalog)
            result=self.session.exchange('tools/call',{'name':'vrchat_me_status','arguments':{}})
            require(result.get('isError',False) is False)
            value=_audit.validate_tool_result(result)
            blocks=value['content'];require(len(blocks)==1 and blocks[0]['type']=='text')
            status=_audit.decode_json(blocks[0]['text']);data=status.get('data',{})
            require(status.get('success') is True)
            return data.get('active') is False and data.get('capabilities')=='None' and data.get('permission_changed') is False
        except PROBE_ERRORS:
            return False
    def close(self):return self.session.close()


def resume_acknowledged(config, nonce):
    try:
        path=Path(config['status_file']).parent/'resume-ack.json'
        if path.is_symlink() or path.stat().st_size>256:return False
        data=_audit.decode_json(path.read_bytes())
        return type(data) is dict and set(data)=={'resume_nonce'} and data['resume_nonce']==nonce
    except (OSError,ValueError,TypeError,_audit.Rejected):return False


def probe_bridge(session=None):
    session = session or MCPSession(18082, 'vrchat-managed-bridge')
    try:
        session.initialize()
        catalog = session.exchange('tools/list')
        rows = catalog['tools']
        require(type(rows) is list and len(rows) == len(AUDITED_TOOLS) and not catalog.get('nextCursor'))
        require({row['name'] for row in rows} == AUDITED_TOOLS)
        result = session.exchange('tools/call', {'name': 'vrchat_me_status', 'arguments': {}})
        require(result.get('isError', False) is False)
        blocks = result['content']
        require(type(blocks) is list and len(blocks) == 1 and blocks[0]['type'] == 'text')
        status = _audit.decode_json(blocks[0]['text'])
        require(status['success'] is True and status['data']['active'] is False
                and status['data']['permission_changed'] is False)
        require('structuredContent' not in result or result['structuredContent'] == status)
        return True
    except PROBE_ERRORS:
        return False


# Manual controller. The audited bridge is hosted in this process so its exact
# session cleanup runs even when Unity launched Python without a console.
import time
import tempfile
import secrets


class Cancelled(Exception):
    pass


class LaunchError(Exception):
    pass


MESSAGES = {
    'STARTING': '检查环境并启动固定版 MCP（首次下载可能需要一段时间）。',
    'SIDECAR_READY': '基础 MCP 握手通过，等待 Unity Connect 和工程身份确认。',
    'BRIDGE_READY': '受限入口 17 工具及权限锁定状态验证通过。',
    'SSH_CONNECTING': '连接 SSH，核验受限反向转发。',
    'CONNECTED': '受限连接已建立；连接不代表编辑授权。',
    'MONITOR_PAUSED': '工程回应暂时不可用：已暂停工具转发，保留隧道并有限复查。编辑权限会撤销。',
    'PERMISSION_WAIT': '工程已回应，等待本地撤销授权确认后恢复；不恢复原编辑权限。',
    'CONNECTION_UNRESPONSIVE': '等待同工程恢复超过60秒，已停止自有连接；请检查诊断，不自动重启。',
    'SIDECAR_STARTING': '正在启动固定版基础 MCP；等待本机18081监听。',
    'SIDECAR_PROBING': '基础端口已可用，正在验证 MCP 握手。',
    'STOPPED': '自有连接已停止，进程与端口已清理。',
    'CLEANUP': '关闭隧道并清理受限会话；最坏可能需要数分钟。',
    'BRIDGE_PORT_BUSY': '18082 已被占用；请先关闭手动 Bridge，不会自动杀进程。',
    'SIDECAR_INVALID': '18081 服务身份或握手不匹配；未接管已有服务。',
    'START_TIMEOUT': 'MCP 启动超时；请核对 uvx、缓存/下载网络和固定版本。',
    'PROJECT_TIMEOUT': 'Unity 尚未连接唯一目标工程，或项目身份不一致。',
    'BRIDGE_INVALID': '受限入口工具列表/锁定状态未通过，请保持编辑权限关闭。',
    'SSH_AUTH_FAILED': 'SSH 密钥认证失败；请在本机配置默认密钥或 ssh-agent。',
    'SSH_HOSTKEY_FAILED': 'SSH 主机指纹尚未信任或已变更；请在本机人工核对。',
    'SSH_FORWARD_FAILED': '远端转发被拒绝或端口已占用，请关闭旧手动隧道或核对 SSH 转发权限。',
    'SSH_REFUSED': 'SSH 服务拒绝连接，请检查主机与服务端口。',
    'SSH_TIMEOUT': 'SSH 连接超时，请检查地址、端口与网络。',
    'PROCESS_EXITED': '本次启动的进程意外退出，正在清理；不自动重启。',
    'PROJECT_CHANGED': '检测到不同工程或多个实例，已停止隧道，不自动恢复。',
    'PROJECT_UNAVAILABLE': '暂时无法确认工程（可能正在导入／编译或连接中断），已停止隧道；不代表工程已更换。',
    'CLEANUP_FAILED': '清理尚未完全确认；不允许自动重试，请本地检查。',
    'INTERNAL_ERROR': '启动器遇到错误；已请求清理，请检查 Python 3.11+ 和本地程序路径。'
}


def write_status(config, phase, code, cleanup_complete=False, **diagnostic):
    target=Path(config['status_file'])
    payload={'phase':phase,'message':MESSAGES.get(code,MESSAGES['INTERNAL_ERROR']),
             'code':code,'cleanup_complete':bool(cleanup_complete)}
    for key in ('resume_nonce','reason','step','elapsed_ms','retry_count'):
        if key in diagnostic:payload[key]=diagnostic[key]
    with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.status-',delete=False,mode='w',encoding='utf-8') as f:
        temporary=Path(f.name)
        json.dump(payload,f,ensure_ascii=False)
    try:os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1',port))==0


class SSHProgress:
    def __init__(self, remote_port):
        self.ready=False
        self.error=None
        self.marker=f'debug1: remote forward success for: listen 127.0.0.1:{remote_port}, connect 127.0.0.1:18082'
    def line(self,text):
        if isinstance(text,bytes):text=text.decode('utf-8','replace')
        if text.rstrip('\r\n')==self.marker:self.ready=True
        for marker,code in [('Permission denied','SSH_AUTH_FAILED'),('Host key verification failed','SSH_HOSTKEY_FAILED'),
                            ('remote port forwarding failed','SSH_FORWARD_FAILED'),('Connection refused','SSH_REFUSED'),
                            ('Connection timed out','SSH_TIMEOUT'),('Could not resolve hostname','SSH_REFUSED')]:
            if marker in text:self.error=code


class Relay:
    def __init__(self):
        self.server=None
        self.thread=None
    def start(self):
        # All limits and routes are the immutable audited bridge defaults.
        spec=importlib.util.spec_from_file_location('_launcher_admission',BRIDGE.with_name('admission_gate.py'))
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        self.server=gate.make_server_class(_audit)(('127.0.0.1',18082))
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.1},name='restricted-bridge')
        self.thread.start()
    def verify(self):
        return probe_bridge()
    def pause(self):self.server.pause()
    def drain(self):return self.server.drain()
    def resume(self):self.server.resume()
    def cleanup(self):
        if self.server is None:return True
        if self.thread is not None and self.thread.is_alive():self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:self.thread.join(2)
        with self.server.session_lock:
            return not self.server.cleanup_debt and not self.server.sessions and not (self.thread and self.thread.is_alive())


def supervise(raw, owner):
    c=validate_config(raw)
    relay=None;ssh=None;sidecar=None;monitor=None;error=None;readiness_clean=True
    def cancelled():return Path(c['stop_file']).exists() or not owner.alive()
    def check():
        if cancelled():raise Cancelled()
        if any(child is not None and child.poll() is not None for child in (ssh,sidecar)):raise LaunchError('PROCESS_EXITED')
    def checked_project():
        try:ready=probe_project(c['expected_project'])
        except ProjectIdentityMismatch:
            check()
            raise
        check()  # a local import/reload stop request can arrive during the probe
        return ready
    def wait(predicate,seconds,code):
        end=time.monotonic()+seconds
        while True:
            check()
            if predicate():return
            if time.monotonic()>=end:raise LaunchError(code)
            time.sleep(0.5)
    try:
        write_status(c,'starting','STARTING');check()
        if port_open(18082):raise LaunchError('BRIDGE_PORT_BUSY')
        if port_open(18081):
            if not probe_sidecar():raise LaunchError('SIDECAR_INVALID')
        else:
            write_status(c,'starting_sidecar','SIDECAR_STARTING',step='spawn_sidecar')
            sidecar=owner.spawn(sidecar_command(c),child_environment())
            wait(lambda:port_open(18081),120,'START_TIMEOUT')
            write_status(c,'probing_sidecar','SIDECAR_PROBING',step='initialize')
            if not probe_sidecar():raise LaunchError('SIDECAR_INVALID')
        write_status(c,'sidecar_ready','SIDECAR_READY')
        wait(checked_project,40,'PROJECT_TIMEOUT')
        check();relay=Relay();relay.start()
        if not relay.verify():raise LaunchError('BRIDGE_INVALID')
        write_status(c,'bridge_ready','BRIDGE_READY');check()
        progress=SSHProgress(c['remote_port'])
        write_status(c,'ssh_connecting','SSH_CONNECTING')
        ssh=owner.spawn(build_commands(c)[1],child_environment(),stderr_line_callback=progress.line)
        def forwarded():
            if progress.error:raise LaunchError(progress.error)
            return progress.ready
        wait(forwarded,30,'SSH_TIMEOUT')
        check()
        if not checked_project():raise LaunchError('PROJECT_UNAVAILABLE')
        monitor=ProjectMonitor(c['expected_project']);monitor.open()
        write_status(c,'connected','CONNECTED')
        next_identity=time.monotonic()+10
        suspended=False;episode_deadline=0;nonce='';successes=0;attempts=0
        while True:
            check()
            if progress.error:raise LaunchError(progress.error)
            now=time.monotonic()
            if suspended and now>=episode_deadline:raise LaunchError('CONNECTION_UNRESPONSIVE')
            if now>=next_identity:
                healthy=monitor.check()
                check()
                if not healthy and not suspended:
                    relay.pause()  # deny NEW calls immediately; never replay admitted writes
                    suspended=True;episode_deadline=time.monotonic()+60
                    nonce=secrets.token_hex(32);successes=0;attempts=0
                if suspended:
                    attempts+=1;successes=successes+1 if healthy else 0
                    code='PERMISSION_WAIT' if healthy else 'MONITOR_PAUSED'
                    write_status(c,'suspended',code,resume_nonce=nonce,reason=monitor.reason,
                                 step=monitor.step,elapsed_ms=monitor.elapsed_ms,retry_count=attempts)
                    if successes>=2 and resume_acknowledged(c,nonce):
                        if not relay.drain():raise LaunchError('CONNECTION_UNRESPONSIVE')
                        # Gate stays CLOSED through drain, local revocation proof, and final identity.
                        locked=monitor.locked_catalog()
                        final_identity=monitor.check() if locked else False
                        check()
                        if locked and final_identity and time.monotonic()<episode_deadline:
                            relay.resume();suspended=False
                            write_status(c,'connected','CONNECTED',reason='recovered_locked',step='identity_and_permissions',elapsed_ms=monitor.elapsed_ms,retry_count=attempts)
                        elif not final_identity:successes=0
                next_identity=time.monotonic()+(3 if suspended else 10)
            time.sleep(0.25)
    except (Cancelled,KeyboardInterrupt):pass
    except CleanupUnresolved:
        readiness_clean=False;error='CLEANUP_FAILED'
    except ProjectIdentityMismatch:error='PROJECT_CHANGED'
    except LaunchError as e:error=str(e)
    except Exception:error='INTERNAL_ERROR'
    finally:
        clean=readiness_clean
        try:
            if relay is not None:relay.pause()
        except Exception:clean=False
        try:write_status(c,'error' if error else 'stopping',error or 'CLEANUP')
        except OSError:clean=False
        # Cut remote access first, then drain exact bridge sessions while sidecar is alive.
        try:
            if ssh is not None:ssh.stop()
        except Exception:clean=False
        try:
            if relay is not None:clean=relay.cleanup() and clean
        except Exception:clean=False
        try:
            if monitor is not None:clean=monitor.close() and clean
        except Exception:clean=False
        try:clean=bool(owner.close()) and clean
        except Exception:clean=False
        if not clean:error='CLEANUP_FAILED'
        write_status(c,'error' if error else 'stopped',error or 'STOPPED',cleanup_complete=clean)
    return 1 if error else 0


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args()
    if os.name!='nt' or sys.version_info<(3,11):
        raise SystemExit('Windows CPython 3.11+ required')
    raw=_audit.decode_json(args.config.read_bytes())
    c=validate_config(raw)
    process_spec=importlib.util.spec_from_file_location('_launcher_windows_processes',BRIDGE.with_name('windows_processes.py'))
    module=importlib.util.module_from_spec(process_spec)
    process_spec.loader.exec_module(module)
    try:owner=module.OwnedProcesses(c['parent_pid'])
    except Exception:
        write_status(c,'error','INTERNAL_ERROR',cleanup_complete=True)
        return 1
    return supervise(c,owner)


if __name__=='__main__':
    raise SystemExit(main())

