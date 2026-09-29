"""Windows PEM-to-SSL memory pipes. Uses the already locked pywin32 dependency.

No disk fallback, listener, helper process, reaccept, or remote pipe client.
These one-shot pipes accept only this exact process. Same-user memory access,
process injection, administrator access, and paging are outside this boundary.
"""
from contextlib import ExitStack
import os
import secrets
import threading
import time

import pywintypes
import win32api
import win32event
import win32file
import win32pipe
import win32security


class _PemPipe:
    """One immutable PEM, one client in this process, bounded overlapped I/O."""
    def __init__(self, content, *, timeout=5.0):
        if type(content) is not bytes or not 1 <= len(content) <= 16384:
            raise ValueError('invalid_pem_bytes')
        if type(timeout) not in (int, float) or not 0 < timeout <= 5:
            raise ValueError('invalid_pem_timeout')
        self.deadline = time.monotonic() + timeout
        self.error = None
        self.path = '\\\\.\\pipe\\vrchat-tls-pem-' + secrets.token_hex(24)
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
        try:
            sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, 1)[0])
        finally:
            token.Close()
        attributes = pywintypes.SECURITY_ATTRIBUTES()
        attributes.bInheritHandle = False
        attributes.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            'D:P(A;;GA;;;' + sid + ')(A;;GA;;;SY)', 1)
        self.handle = win32pipe.CreateNamedPipe(self.path,
            win32pipe.PIPE_ACCESS_OUTBOUND | 0x00080000 | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | 0x8,
            1, 16384, 0, 0, attributes)
        self.stop = self.event = None
        try:
            self.stop = win32event.CreateEvent(None, True, False, None)
            self.event = win32event.CreateEvent(None, True, False, None)
            self.worker = threading.Thread(target=self._serve, args=(content,),
                name='vrchat-tls-pem-' + secrets.token_hex(8), daemon=True)
            self.worker.start()
        except BaseException:
            self.handle.Close()
            if self.event is not None: self.event.Close()
            if self.stop is not None: self.stop.Close()
            raise

    def _complete(self, operation):
        remaining = max(0, int((self.deadline - time.monotonic()) * 1000))
        result = win32event.WaitForMultipleObjects([self.event, self.stop], False, remaining)
        if result != 0:
            try:
                # All overlapped operations on this handle were issued by THIS
                # worker thread; the pinned pywin32 exports CancelIo, not CancelIoEx.
                win32file.CancelIo(self.handle)
            except pywintypes.error as error:
                if error.winerror != 1168:  # ERROR_NOT_FOUND: already completed
                    raise
            try:
                # Cancel and drain before releasing OVERLAPPED/event/buffer.
                win32file.GetOverlappedResult(self.handle, operation, True)
            except pywintypes.error as error:
                if error.winerror != 995:  # ERROR_OPERATION_ABORTED
                    raise
            raise TimeoutError('pem_pipe_cancelled_or_expired')
        return win32file.GetOverlappedResult(self.handle, operation, False)

    def _serve(self, content):
        try:
            operation = pywintypes.OVERLAPPED()
            operation.hEvent = self.event
            result = win32pipe.ConnectNamedPipe(self.handle, operation)
            if result != 535:  # Early client connected; no pending I/O in that case.
                self._complete(operation)
            if win32pipe.GetNamedPipeClientProcessId(self.handle) != os.getpid():
                raise PermissionError('foreign_pem_client')
            if win32event.WaitForSingleObject(self.stop, 0) == 0 or time.monotonic() >= self.deadline:
                raise TimeoutError('pem_pipe_cancelled_or_expired')
            win32event.ResetEvent(self.event)
            operation = pywintypes.OVERLAPPED()
            operation.hEvent = self.event
            win32file.WriteFile(self.handle, content, operation)
            if self._complete(operation) != len(content):
                raise OSError('short_pem_write')
        except BaseException as error:
            self.error = type(error).__name__  # Never capture key bytes/raw error.
        finally:
            # CloseHandle permits the client to drain buffered bytes then EOF.
            # DisconnectNamedPipe discards them; FlushFileBuffers may block forever.
            self.handle.Close()
            self.event.Close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        win32event.SetEvent(self.stop)
        self.worker.join(6)
        if self.worker.is_alive():
            # Do not claim cleanup or reuse this run; outer owned supervisor must stop it.
            raise RuntimeError('pem_pipe_cleanup_incomplete')
        self.stop.Close()


def load_windows_pem(context, certificate, private_key):
    with ExitStack() as stack:
        cert = stack.enter_context(_PemPipe(certificate))
        key = stack.enter_context(_PemPipe(private_key))
        def reject_password_prompt():
            raise ValueError('encrypted_tls_key_not_supported')
        context.load_cert_chain(cert.path, key.path, password=reject_password_prompt)
    if cert.error is not None or key.error is not None:
        raise OSError('pem_pipe_load_failed')
