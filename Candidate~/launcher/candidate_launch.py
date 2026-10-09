"""On-demand candidate lifecycle, not an MCP implementation or installer.

MIT, Copyright (c) 2026 Yukino / Hermes Agent. See LICENSE and PROVENANCE.json.
Only the bundled runtime and a fixed OpenSSH reverse-forward command are exposed.
"""
import hashlib
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import stat
import socket
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'
SSH = (Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/OpenSSH/ssh.exe'
       if os.name == 'nt' else Path('/usr/bin/ssh'))


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid integer configuration')
    return value


def validate_config(raw):
    required = {'project', 'parent_pid', 'local_port'}
    if type(raw) is not dict or not required <= raw.keys() or not raw.keys() <= required | {'ssh'}:
        raise ValueError('Invalid configuration fields')
    c = dict(raw)
    if type(c['project']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', c['project']) is None:
        raise ValueError('Invalid native project identity')
    integer(c['parent_pid'], 1, 4294967295)
    integer(c['local_port'], 1024, 65535)
    if 'ssh' in c:
        s = c['ssh']
        if type(s) is not dict or not {'host', 'remote_port'} <= s.keys() or not s.keys() <= {'host', 'user', 'port', 'remote_port'}:
            raise ValueError('Invalid SSH fields')
        s = dict(s)
        # Reused legacy strict host/user allowlists: no aliases, shell, IPv6 or option injection.
        if type(s['host']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}', s['host']) is None:
            raise ValueError('Invalid SSH host')
        s.setdefault('user', '')
        if type(s['user']) is not str or (s['user'] and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}', s['user']) is None):
            raise ValueError('Invalid SSH user')
        s.setdefault('port', 22)
        integer(s['port'], 1, 65535)
        integer(s['remote_port'], 1024, 65535)
        c['ssh'] = s
    return c


def build_commands(raw):
    c = validate_config(raw)
    runtime = [sys.executable, '-B', str(RUNTIME), '--project', c['project'], '--port', str(c['local_port'])]
    ssh = None
    if 'ssh' in c:
        s = c['ssh']
        ssh = [str(SSH), '-F', os.devnull, '-v', '-N', '-T']
        for option in ('BatchMode=yes', 'StrictHostKeyChecking=yes', 'ExitOnForwardFailure=yes',
                       'ServerAliveInterval=15', 'ServerAliveCountMax=2', 'ConnectTimeout=10',
                       'ConnectionAttempts=1', 'ProxyCommand=none', 'ProxyJump=none',
                       'PermitLocalCommand=no', 'ForwardAgent=no', 'ForwardX11=no',
                       'ControlMaster=no', 'ControlPath=none', 'ControlPersist=no',
                       'GatewayPorts=no', 'UpdateHostKeys=no'):
            ssh.extend(['-o', option])
        ssh.extend(['-p', str(s['port']), '-R',
                    f"127.0.0.1:{s['remote_port']}:127.0.0.1:{c['local_port']}",
                    (s['user'] + '@' if s['user'] else '') + s['host']])
    return runtime, ssh


def build_handoff_command(raw):
    """Fixed operator-installed subsystem, never a caller-selected remote shell.

    Same strict SSH host trust and loopback forwarding as the tunnel-only path.
    Credentials travel on redirected stdin, never in this argv or SSH env.
    This builder neither starts a process nor proves delivery/readiness.
    """
    _, command = build_commands(raw)
    if command is None:
        raise ValueError('candidate_ssh_required')
    return [value for value in command[:-1] if value != '-N'] + [
        '-s', command[-1], 'vrchat-agent-handoff']


def make_owner(parent_pid):
    integer(parent_pid, 1, 4294967295)
    if os.name == 'nt':
        from .windows_processes import OwnedProcesses
    elif sys.platform == 'linux':
        from .linux_processes import OwnedProcesses
    else:
        raise OSError('Windows or Linux fixture backend required')
    return OwnedProcesses(parent_pid)


class ProjectLease:
    """One cooperating launcher per exact project and OS user; no PID files.

    Empty lock files persist deliberately: unlinking a locked inode would allow
    a second launcher to lock a replacement. These files contain no credentials.
    """
    def __init__(self, project, *, root=None):
        if root is None:
            root = (Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'VRChatAgent/launcher-locks'
                    if os.name == 'nt' else Path('/tmp') / f'vrchat-agent-launcher-{os.getuid()}')
        root = Path(root)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or (os.name != 'nt' and
                (info.st_uid != os.getuid() or info.st_mode & 0o077)):
            raise OSError('Unsafe lock directory')
        self.fd = os.open(root / (hashlib.sha256(project.encode()).hexdigest() + '.lock'),
                          os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or (os.name != 'nt' and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1)):
                raise OSError('Unsafe lock file')
            if info.st_size == 0:
                os.write(self.fd, b'0')
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


@dataclass
class RuntimeBinding:
    """Trusted LOCAL integration object, never deserialized from launch JSON.

    The integrator supplies runtime-defined credentials and sets ready ONLY after
    authenticated, exact-project readiness. No auth protocol is defined here.
    Observe started/cancelled for probe lifecycle; failed revokes readiness.
    Each instance is single-use. Credentials never go into argv/status/SSH env.
    """
    environment: dict = field(repr=False)
    ready: threading.Event = field(repr=False)
    failed: threading.Event = field(default_factory=threading.Event, repr=False)
    started: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    cancelled: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    used: bool = field(default=False, init=False)
    probe_inflight: threading.Event = field(default_factory=threading.Event,init=False,repr=False)
    reload_control: object = field(default=None, repr=False)  # Local typed owner only.


def child_environment(extra=None, source=None):
    source = os.environ if source is None else source
    permitted = {'PATH', 'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE', 'LOCALAPPDATA',
                 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'SSH_AUTH_SOCK'}
    result = {k: v for k, v in source.items() if k.upper() in permitted}
    result.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', DISABLE_TELEMETRY='true')
    if extra is not None:
        if type(extra) is not dict or not 1 <= len(extra) <= 32:
            raise ValueError('Runtime binding environment required')
        for k, v in extra.items():
            if (type(k) is not str or not re.fullmatch(r'VRCHAT_AGENT_[A-Z0-9_]{1,64}', k)
                    or type(v) is not str or not 1 <= len(v) <= 16384 or '\x00' in v):
                raise ValueError('Invalid runtime binding environment')
        if sum(len(k) + len(v) for k, v in extra.items()) > 65536:
            raise ValueError('Runtime binding too large')
        result.update(extra)
    return result


START_TIMEOUT = 20.0
SSH_TIMEOUT = 30.0


class Progress:
    """Legacy fixed diagnostics adapted to candidate: retain no stderr lines."""
    def __init__(self, component, remote_port=None, local_port=None):
        self.component = component
        self.error = None
        self.ready = False
        self.marker = f'debug1: remote forward success for: listen 127.0.0.1:{remote_port}, connect 127.0.0.1:{local_port}'

    def line(self, text):
        if not isinstance(text, str) or len(text.encode('utf-8', 'replace')) > 4096:
            return
        if self.component == 'ssh':
            if text.rstrip('\r\n') == self.marker:
                self.ready = True
            markers = (('Permission denied', 'SSH_AUTH_FAILED'),
                       ('Host key verification failed', 'SSH_HOSTKEY_FAILED'),
                       ('REMOTE HOST IDENTIFICATION HAS CHANGED', 'SSH_HOSTKEY_FAILED'),
                       ('remote port forwarding failed', 'SSH_FORWARD_FAILED'),
                       ('Connection refused', 'SSH_REFUSED'),
                       ('Connection timed out', 'SSH_TIMEOUT'),
                       ('Could not resolve hostname', 'SSH_REFUSED'))
        else:
            text = text.lower()
            markers = (('modulenotfounderror', 'RUNTIME_DEPENDENCY'),
                       ('no module named', 'RUNTIME_DEPENDENCY'),
                       ('unrecognized arguments', 'RUNTIME_ARGUMENTS'),
                       ('address already in use', 'RUNTIME_PORT_BUSY'))
        for marker, code in markers:
            if marker in text:
                self.error = code
                return


def supervise(raw, *, binding=None, stop=None, report=None):
    """Blocking, explicit start. stop Event/parent exit stop ONLY this run.

    report receives bounded allowlisted status dictionaries, never raw output.
    Return process_cleanup_complete says NOTHING about remote MCP/Unity cleanup.
    Integration must observe cancelled and verify its own session cleanup.
    """
    c = validate_config(raw)
    status = {'phase': 'blocked', 'code': 'BINDING_REQUIRED', 'stage': 'preflight',
              'component': 'launcher', 'exit_code': None, 'process_cleanup_complete': True}
    if not isinstance(binding, RuntimeBinding):
        return status
    if binding.used or binding.ready.is_set() or binding.failed.is_set():
        status['code'] = 'BINDING_INVALID'
        return status
    try:
        # Runtime credentials are mandatory; None is only valid for base/SSH env.
        if type(binding.environment) is not dict:
            raise ValueError('Runtime binding environment required')
        env = child_environment(binding.environment)
    except ValueError:
        status['code'] = 'BINDING_INVALID'
        return status
    binding.used = True
    stop = stop if stop is not None else threading.Event()
    owner = lease = runtime = ssh = None
    runtime_progress = Progress('runtime')
    ssh_progress = Progress('ssh', c.get('ssh', {}).get('remote_port'), c['local_port'])
    failure = None
    def publish():
        if report is not None:
            report(dict(status))
    try:
        lease = ProjectLease(c['project'])
        # Refuse occupied ports; never adopt/kill a listener. This is a preflight
        # only, not proof of ownership/authentication. Integrator supplies proof.
        with socket.socket() as sock:
            if os.name == 'nt':
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                sock.bind(('127.0.0.1', c['local_port']))
            except OSError:
                failure = 'LOCAL_PORT_BUSY'
        if failure is None:
            owner = make_owner(c['parent_pid'])
            if stop.is_set() or not owner.alive():
                status['code'] = 'STOPPED' if stop.is_set() else 'PARENT_EXITED'
            else:
                runtime_argv, ssh_argv = build_commands(c)
                status.update(stage='runtime_starting', component='runtime', phase='starting',
                              code='RUNTIME_STARTING', process_cleanup_complete=False)
                runtime = owner.spawn(runtime_argv, env, runtime_progress.line)
                if binding.reload_control is not None:binding.reload_control.bind(runtime.pid)
                binding.started.set()
                publish()
                deadline = time.monotonic() + START_TIMEOUT
                while True:
                    if stop.is_set() or not owner.alive():
                        status['code'] = 'STOPPED' if stop.is_set() else 'PARENT_EXITED'
                        break
                    if binding.failed.is_set():
                        failure = 'BINDING_FAILED'
                        break
                    exit_code = runtime.poll()
                    if exit_code is not None:
                        status['component'] = 'runtime'
                        status['exit_code'] = exit_code
                        failure = runtime_progress.error or 'PROCESS_EXITED'
                        break
                    if ssh is not None:
                        exit_code = ssh.poll()
                        if ssh_progress.error or exit_code is not None:
                            status.update(component='ssh', exit_code=exit_code)
                            failure = ssh_progress.error or 'PROCESS_EXITED'
                            break
                        if ssh_progress.ready and status['phase'] != 'running':
                            status.update(phase='running', code='FORWARD_ESTABLISHED', stage='running')
                            publish()
                    elif status['phase'] != 'running' and binding.ready.is_set():
                        if ssh_argv is not None:
                            status.update(phase='starting', code='SSH_CONNECTING', stage='ssh_connecting', component='ssh')
                            # Runtime credentials MUST NOT be inherited by ssh.
                            ssh = owner.spawn(ssh_argv, child_environment(), ssh_progress.line)
                            deadline = time.monotonic() + SSH_TIMEOUT
                        else:
                            status.update(phase='running', code='RUNTIME_READY', stage='running')
                        publish()
                    if status['phase'] != 'running' and time.monotonic() >= deadline:
                        failure = 'SSH_TIMEOUT' if ssh is not None else 'START_TIMEOUT'
                        break
                    stop.wait(.05)
    except BlockingIOError:
        failure = 'PROJECT_BUSY'
    except KeyboardInterrupt:
        status['code'] = 'STOPPED'
    except Exception:
        failure = 'INTERNAL_ERROR'
    finally:
        binding.cancelled.set()
        clean = True
        if binding.reload_control is not None:
            try:binding.reload_control.close()
            except Exception:clean=False
        # Cut off remote access first; no MCP allocations or custom protocol here.
        if ssh is not None:
            try:
                ssh.stop()
            except Exception:
                clean = False
        if owner is not None:
            try:
                clean = bool(owner.close()) and clean
            except Exception:
                clean = False
        # Readers can flush a bounded EOF tail during close. Refine ONLY an
        # observed pre-cleanup exit; never repoll closed Win32 handles or convert
        # a user stop to an error based on output produced during termination.
        if failure == 'PROCESS_EXITED':
            progress = ssh_progress if status['component'] == 'ssh' else runtime_progress
            failure = progress.error or failure
        if lease is not None:
            lease.close()
        status['process_cleanup_complete'] = clean
        if failure is not None:
            status['code'] = failure
            status['failure_code'] = failure
        if not clean:
            status['code'] = 'CLEANUP_FAILED'
        status['phase'] = 'error' if failure or not clean else 'stopped'
        try:
            publish()
        except Exception:
            status['code'] = 'REPORT_FAILED'
            status['phase'] = 'error'
    return status
