"""Linux fixture owner. Windows production ownership is in windows_processes.

Linux pidfd pins the parent; process groups cover non-escaping descendants.
This is NOT a Linux kill-on-supervisor-crash guarantee or an execution sandbox.
"""
import os
import select
import signal
import subprocess
import time
from .windows_processes import NativeProcess


class Process(NativeProcess):
    def __init__(self, proc, readfd, callback):
        super().__init__(None, None, None, readfd, callback)
        self.proc, self.pid = proc, proc.pid

    def poll(self):
        if self.proc.returncode is not None:
            return self.proc.returncode
        # Leave an exited leader unreaped until the last group signal, so its
        # numeric PID/PGID cannot be recycled underneath owned cleanup.
        info = os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if info is None:
            return None
        return info.si_status if info.si_code == os.CLD_EXITED else -info.si_status

    def stop(self):
        # Only the new session created by this owner; never look up a port/name.
        if self.proc.returncode is not None:
            return
        try:
            os.killpg(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def close(self):
        super().close()


class OwnedProcesses:
    def __init__(self, parent_pid):
        if not hasattr(os, 'pidfd_open'):
            raise OSError('Linux pidfd required for fixture ownership')
        self.parent = os.pidfd_open(parent_pid)
        self.children = []
        self.closed = False
        self.clean = False

    def alive(self):
        return not self.closed and not select.select([self.parent], [], [], 0)[0]

    def spawn(self, args, env, stderr_line_callback=None):
        if not self.alive():
            raise OSError('Parent unavailable')
        readfd, writefd = os.pipe() if stderr_line_callback else (None, None)
        try:
            proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=writefd if writefd is not None else subprocess.DEVNULL,
                start_new_session=True, shell=False, close_fds=True)
        except BaseException:
            if readfd is not None:
                os.close(readfd)
            raise
        finally:
            if writefd is not None:
                os.close(writefd)
        child = Process(proc, readfd, stderr_line_callback)
        self.children.append(child)
        child.start_reader()
        return child

    def close(self):
        if self.closed:
            return self.clean
        self.closed = True
        clean = True
        for child in reversed(self.children):
            try:
                child.stop()
                deadline = time.monotonic() + 2
                while child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                # Root exit does not imply its descendants have exited.
                # Signal BEFORE reap: keep the group leader PID pinned.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                clean = False
            except OSError:
                clean = False
            try:
                child.close()
                os.killpg(child.pid, 0)
                clean = False  # Includes zombies: do not claim the group is gone.
            except ProcessLookupError:
                pass
            except OSError:
                clean = False
        os.close(self.parent)
        self.clean = clean
        return clean
