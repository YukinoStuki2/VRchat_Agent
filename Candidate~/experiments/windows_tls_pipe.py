"""Bounded synthetic feasibility experiment; NOT a product loader.

Can CPython 3.11/OpenSSL consume PEM through Windows named pipes without a
filesystem file? Parent bounds the entire child process to 20 seconds. No real
credentials, Unity, client config, network listener, or persistent private key.
"""
import json
import os
from pathlib import Path
import subprocess
import sys


def child():
    import datetime
    import ipaddress
    import secrets
    import ssl
    import threading
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import pywintypes
    import win32api
    import win32event
    import win32file
    import win32pipe
    import win32security

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'synthetic-loopback')])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(private.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-datetime.timedelta(seconds=30))
        .not_valid_after(now+datetime.timedelta(minutes=5))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private, hashes.SHA256())).public_bytes(serialization.Encoding.PEM)
    key = private.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
    try:
        sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, 1)[0])
    finally:
        token.Close()
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.bInheritHandle = False
    sa.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        'D:P(A;;GA;;;' + sid + ')(A;;GA;;;SY)', 1)
    handles = []
    workers = []
    outcomes = []
    names = []

    def serve(handle, content):
        event = win32event.CreateEvent(None, True, False, None)
        try:
            ov = pywintypes.OVERLAPPED()
            ov.hEvent = event
            try:
                win32pipe.ConnectNamedPipe(handle, ov)
            except pywintypes.error as error:
                if error.winerror != 535:  # ERROR_PIPE_CONNECTED
                    raise
                win32event.SetEvent(event)
            if win32event.WaitForSingleObject(event, 5000) != 0:
                raise RuntimeError('pipe_connect_timeout')
            if win32pipe.GetNamedPipeClientProcessId(handle) != os.getpid():
                raise RuntimeError('wrong_pipe_client')
            win32event.ResetEvent(event)
            ov = pywintypes.OVERLAPPED()
            ov.hEvent = event
            win32file.WriteFile(handle, content, ov)
            if win32event.WaitForSingleObject(event, 5000) != 0:
                raise RuntimeError('pipe_write_timeout')
            count = win32file.GetOverlappedResult(handle, ov, False)
            if count != len(content):
                raise RuntimeError('short_pipe_write')
            # CloseHandle only: no DisconnectNamedPipe (which discards unread data).
            outcomes.append('served-own-process')
        except Exception as error:
            outcomes.append(type(error).__name__)
        finally:
            handle.Close()
            event.Close()

    for data in (certificate, key):
        name = '\\\\.\\pipe\\vrchat-tls-probe-' + secrets.token_hex(24)
        handle = win32pipe.CreateNamedPipe(name,
            win32pipe.PIPE_ACCESS_OUTBOUND | 0x00080000 | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | 0x8,
            1, 16384, 0, 0, sa)
        handles.append(handle)
        names.append(name)
        worker = threading.Thread(target=serve, args=(handle, data), daemon=True)
        workers.append(worker)
        worker.start()
    # The TLS data itself is sufficient for the real parser check below;
    # this extra synthetic peer deliberately delays every read until server close.
    delayed_name = '\\\\.\\pipe\\vrchat-drain-probe-' + secrets.token_hex(24)
    delayed_handle = win32pipe.CreateNamedPipe(delayed_name,
        win32pipe.PIPE_ACCESS_OUTBOUND | 0x00080000 | win32file.FILE_FLAG_OVERLAPPED,
        win32pipe.PIPE_TYPE_BYTE | 0x8, 1, 16384, 0, 0, sa)
    delayed_thread = threading.Thread(target=serve, args=(delayed_handle, b'synthetic-drain'), daemon=True)
    delayed_thread.start()
    delayed_client = win32file.CreateFile(delayed_name, win32file.GENERIC_READ, 0, None,
        win32file.OPEN_EXISTING, 0, None)
    try:
        delayed_thread.join(3)
        assert not delayed_thread.is_alive(), 'server close did not complete before read'
        assert win32file.ReadFile(delayed_client, 100)[1] == b'synthetic-drain', 'close discarded unread bytes'
    finally:
        delayed_client.Close()
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_2
    server.load_cert_chain(names[0], names[1])
    for worker in workers:
        worker.join(6)
    assert all(not worker.is_alive() for worker in workers), 'worker_remains'
    assert outcomes == ['served-own-process'] * 3, outcomes
    for name in names:
        try:
            unexpected = win32file.CreateFile(name, win32file.GENERIC_READ, 0, None,
                win32file.OPEN_EXISTING, 0, None)
        except pywintypes.error as error:
            assert error.winerror == 2, 'unexpected_pipe_remnant'
        else:
            unexpected.Close()
            raise AssertionError('pipe_remains')
    client = ssl.create_default_context(cadata=certificate.decode('ascii'))
    sin, sout, cin, cout = [ssl.MemoryBIO() for _ in range(4)]
    peer = server.wrap_bio(sin, sout, server_side=True)
    caller = client.wrap_bio(cin, cout, server_side=False, server_hostname='127.0.0.1')
    done = [False, False]
    for _ in range(100):
        for index, actor in enumerate((peer, caller)):
            if not done[index]:
                try:
                    actor.do_handshake()
                    done[index] = True
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    pass
        data = sout.read()
        if data: cin.write(data)
        data = cout.read()
        if data: sin.write(data)
        if all(done): break
    assert all(done), 'TLS_handshake_not_complete'
    print(json.dumps({'pipe_pem_load': True, 'TLS_handshake': True, 'close_without_flush_retains_bytes': True,
                      'own_pid_checked': True, 'pipes_absent': True,
                      'worker_threads_absent': True, 'openssl': ssl.OPENSSL_VERSION}))


if __name__ == '__main__':
    if os.name != 'nt':
        print('Actual Windows required; not verified here')
        raise SystemExit(2)
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        child()
    else:
        result = subprocess.run([sys.executable, '-I', '-B', '-W', 'always::ResourceWarning',
            __file__, '--child'], text=True, capture_output=True, timeout=20)
        report = {'scope': 'synthetic named-pipe PEM feasibility only; not product acceptance',
                  'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                  'passed': result.returncode == 0 and 'ResourceWarning' not in result.stdout + result.stderr}
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        raise SystemExit(0 if report['passed'] else 1)
