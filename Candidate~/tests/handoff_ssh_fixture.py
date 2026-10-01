"""Test-only real OpenSSH loopback subsystem/forward. No host configuration edits.

Ephemeral client key enters a dedicated ssh-agent on stdin; host private key
lives in a sealed memfd. Only public keys, host trust and config touch disk.
This is real SSH on ONE Linux host, not Windows, WAN or operator approval.
"""
import asyncio
from contextlib import asynccontextmanager
import fcntl
import json
import os
from pathlib import Path
import pwd
import shlex
import socket
import sys
import tempfile
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from owned_descendants import Descendants

ROOT = Path(__file__).resolve().parents[1]


def key_pair():
    key = Ed25519PrivateKey.generate()
    return (key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()),
            key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                         serialization.PublicFormat.OpenSSH))


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


async def ready(process, path=None, port=None):
    async with asyncio.timeout(5):
        while True:
            if process.returncode is not None:
                raise RuntimeError('fixture_ssh_service_exited')
            try:
                if path is not None:
                    reader, writer = await asyncio.open_unix_connection(str(path))
                else:
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                writer.close()
                await writer.wait_closed()
                return
            except (FileNotFoundError, ConnectionRefusedError):
                await asyncio.sleep(.02)


@asynccontextmanager
async def ssh_relay(receiver, document, report, *, wrong_host=False, no_key=False, launch=True):
    from launcher.candidate_launch import build_handoff_command, child_environment
    watcher = Descendants()
    done = asyncio.Event()
    watching = asyncio.create_task(watcher.watch(os.getpid(), done))
    children = []
    readers = []
    host_fd = None
    relay_errors = None
    client_private, client_public = key_pair()
    host_private, host_public = key_pair()
    secrets = (client_private, host_private, document['bearer'].encode())
    try:
        with tempfile.TemporaryDirectory(prefix='vrc-ssh-', dir=ROOT/'evidence') as directory:
            home = Path(directory)
            try:
                env = child_environment(source={'PATH':os.defpath,'HOME':directory,'LANG':'C.UTF-8'})
                agent_path = home/'agent.sock'
                agent = await asyncio.create_subprocess_exec('/usr/bin/ssh-agent','-D','-a',str(agent_path),
                    env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                assert agent.stderr is not None
                children.append(agent); readers.append(asyncio.create_task(agent.stderr.read()))
                await ready(agent, path=agent_path)
                env['SSH_AUTH_SOCK'] = str(agent_path)
                add = await asyncio.create_subprocess_exec('/usr/bin/ssh-add','-t','120','-', env=env,
                    stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                children.append(add)
                out, err = await asyncio.wait_for(add.communicate(client_private),5)
                assert add.returncode == 0, 'fixture_add_key_failed'
                assert not any(value in out+err for value in secrets)
                host_fd = os.memfd_create('candidate-test-ssh-host',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
                os.fchmod(host_fd,0o600); os.write(host_fd,host_private)
                # Linux UAPI, same standalone-CPython compatibility as tls_context.
                fcntl.fcntl(host_fd,getattr(fcntl,'F_ADD_SEALS',1033),0x000F)
                ssh_port, remote_port = free_port(), free_port()
                while remote_port in (ssh_port, document['port']): remote_port = free_port()
                watcher.ports.update((ssh_port,remote_port))
                public = home/'client.pub'; public.write_bytes(client_public+b'\n')
                authorized = home/'authorized_keys'
                authorized.write_bytes(client_public+b'\n'); authorized.chmod(0o600)
                known = home/'known_hosts'
                trust = key_pair()[1] if wrong_host else host_public
                known.write_bytes(f'[127.0.0.1]:{ssh_port} '.encode()+trust+b'\n')
                relay_command = shlex.join([sys.executable,'-I','-B',str(ROOT/'clients/hermes_handoff_relay.py'),str(receiver)])
                config = home/'sshd_config'
                config.write_text('\n'.join((
                    f'Port {ssh_port}','ListenAddress 127.0.0.1',
                    f'HostKey /proc/{os.getpid()}/fd/{host_fd}',f'AuthorizedKeysFile {authorized}',
                    'PidFile none','StrictModes yes','UsePAM no','PasswordAuthentication no',
                    'KbdInteractiveAuthentication no','AuthenticationMethods publickey',
                    f'AllowUsers {pwd.getpwuid(os.getuid()).pw_name}',
                    'AllowTcpForwarding remote','GatewayPorts no',f'PermitListen 127.0.0.1:{remote_port}',
                    'PermitTTY no','X11Forwarding no','AllowAgentForwarding no','PermitUserRC no',
                    'PrintMotd no','LogLevel ERROR',
                    'Subsystem vrchat-agent-handoff '+relay_command,'ForceCommand '+relay_command))+'\n')
                daemon = await asyncio.create_subprocess_exec('/usr/sbin/sshd','-D','-e','-f',str(config),
                    env=env,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
                assert daemon.stderr is not None
                children.append(daemon); readers.append(asyncio.create_task(daemon.stderr.read()))
                await ready(daemon,port=ssh_port)
                raw={'project':document['project'],'parent_pid':os.getpid(),'local_port':document['port'],
                     'ssh':{'host':'127.0.0.1','user':pwd.getpwuid(os.getuid()).pw_name,
                            'port':ssh_port,'remote_port':remote_port}}
                command=build_handoff_command(raw)
                # Test-only trust/key location; no change to the production host policy.
                command[1:1]=['-o','UserKnownHostsFile='+str(known),'-o','GlobalKnownHostsFile=/dev/null',
                    '-o','IdentitiesOnly=yes','-o','IdentityAgent='+('none' if no_key else str(agent_path)),
                    '-o','IdentityFile='+str(public)]
                report['ssh_scope']='real loopback OpenSSH auth + subsystem + reverse TCP; same Linux host'
                if launch:
                    relay=await asyncio.create_subprocess_exec(*command,env=env,
                        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    children.append(relay)
                    assert relay.stdin is not None and relay.stdout is not None and relay.stderr is not None
                    relay_errors=asyncio.create_task(relay.stderr.read());readers.append(relay_errors)
                    relay.stdin.write(json.dumps({**document,'port':remote_port}).encode()+b'\n')
                    await relay.stdin.drain()
                    yield relay
                else:
                    yield {'command':command,'environment':env,'raw':raw}
            finally:
                for process in reversed(children):
                    if process.stdin is not None:
                        process.stdin.close()
                    if process.returncode is None:
                        if process is children[-1]:
                            try: await asyncio.wait_for(process.wait(),5)
                            except TimeoutError: pass
                        if process.returncode is None:
                            process.terminate()
                            try: await asyncio.wait_for(process.wait(),5)
                            except TimeoutError:
                                process.kill();await process.wait()
                outputs=await asyncio.gather(*readers)
                report['ssh_secret_output_clean']=not any(value in output for output in outputs for value in secrets)
                report['ssh_secret_files_clean']=not any(value in file.read_bytes() for file in home.rglob('*')
                    if file.is_file() for value in secrets)
                report['ssh_process_exit_codes']=[p.returncode for p in children]
                # Test logs contain no credentials; retain a bounded diagnostic only on failure.
                report['ssh_daemon_diagnostic']=outputs[1].decode('utf-8','replace')[-2000:] if len(outputs)>1 else ''
                if relay_errors is not None:
                    report['ssh_authenticated']='Authenticated to 127.0.0.1' in relay_errors.result().decode('utf-8','replace')
                    if children[-1].returncode != 0:
                        report['ssh_client_diagnostic']=relay_errors.result().decode('utf-8','replace')[-4500:]
                assert report['ssh_secret_output_clean'] and report['ssh_secret_files_clean']
        report['ssh_temporary_root_absent']=not Path(directory).exists()
    finally:
        if host_fd is not None: os.close(host_fd)
        done.set();await watching
        report['ssh_descendants']=await watcher.finish()
        if sys.exc_info()[0] is None:
            assert report['ssh_descendants']['clean'], 'fixture_ssh_residue'
