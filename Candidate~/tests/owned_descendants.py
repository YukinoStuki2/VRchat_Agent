"""Linux outer-fixture evidence. Track exact descendants with pidfds; no broad kill.
Not production ownership, not Windows proof. Dedicated verifier process only.
"""
import asyncio
import ctypes
import os
from pathlib import Path
import select
import signal
import socket
import time


class Descendants:
    def __init__(self):
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), 'subreaper_required')
        self.pinned = {}
        self.ports = set()

    def scan(self, root):
        rows = {}
        for path in Path('/proc').glob('[0-9]*/stat'):
            try:
                fields = path.read_text().rsplit(')', 1)[1].split()
                rows[int(path.parent.name)] = (int(fields[1]), fields[19])
            except (OSError, ValueError, IndexError):
                pass
        known = {root} | {pid for pid, (stamp, _) in self.pinned.items()
                               if pid in rows and rows[pid][1] == stamp}
        while True:
            added = {pid for pid, (parent, _) in rows.items() if parent in known} - known
            if not added:
                break
            known |= added
        inodes = set()
        for pid in known - {root}:
            try:
                if pid not in self.pinned:
                    fd = os.pidfd_open(pid)
                    self.pinned[pid] = (rows[pid][1], fd)
                for link in Path(f'/proc/{pid}/fd').iterdir():
                    try:
                        target = os.readlink(link)
                        if target.startswith('socket:['): inodes.add(target[8:-1])
                    except OSError: pass
            except (OSError, KeyError): pass
        for file in ('/proc/net/tcp', '/proc/net/tcp6'):
            for line in Path(file).read_text().splitlines()[1:]:
                fields = line.split()
                if fields[3] == '0A' and fields[9] in inodes:
                    self.ports.add(int(fields[1].split(':')[1], 16))

    async def watch(self, root, done):
        while not done.is_set():
            self.scan(root)
            await asyncio.sleep(.01)

    def living(self):
        for pid in self.pinned:
            try: os.waitpid(pid, os.WNOHANG)
            except ChildProcessError: pass
        return [pid for pid, (_, fd) in self.pinned.items() if not select.select([fd], [], [], 0)[0]]

    async def finish(self):
        deadline = time.monotonic() + 8
        while self.living() and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        remaining = self.living()
        open_ports = []
        for port in self.ports:
            with socket.socket() as probe:
                probe.settimeout(.1)
                if probe.connect_ex(('127.0.0.1', port)) == 0: open_ports.append(port)
        row = {'tracked_descendants': len(self.pinned), 'tracked_listeners': len(self.ports),
               'residual_pids': remaining, 'residual_ports': open_ports,
               'clean': bool(self.pinned) and bool(self.ports) and not remaining and not open_ports}
        # Failing evidence retains original residue; safety cleanup is NOT a pass.
        for pid in remaining:
            signal.pidfd_send_signal(self.pinned[pid][1], signal.SIGKILL)
        for _ in range(100):
            if not self.living(): break
            await asyncio.sleep(.02)
        self.living()
        row['safety_cleanup_complete'] = not self.living()
        for _, fd in self.pinned.values(): os.close(fd)
        return row
