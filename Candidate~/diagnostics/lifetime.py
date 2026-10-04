"""On-demand snapshot lifetime owner; no listener, daemon or source-file access.

A fixed helper owns TemporaryDirectory cleanup even if its capture caller dies.
EOF or the fixed deadline closes it. This is NOT power-loss/all-process-kill
cleanup or a same-user sandbox. Original capture/ACL/read boundaries are reused.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import stat
import subprocess
import sys
import tempfile
import threading
import time

TTL = 300
CLEANUP_RETRY_SECONDS = 5.0
CLEANUP_RETRY_INTERVAL = 0.05


def _cleanup_record(root):
    targets = [root]
    if sys.platform == 'win32':
        targets.append(root.parent)
    return ([(path, _stamp(path)) for path in targets],
            [(path, _stamp(path)) for path in targets[-1].parents])


def _cleanup_owned(record):
    """Retry only recorded directories; never follow a replaced ancestor.

    This is a bounded post-expiry deletion budget, not a renewed snapshot TTL.
    The outer Windows ACL container is removed only if empty, never swept.
    """
    targets, parents = record
    deadline = time.monotonic() + CLEANUP_RETRY_SECONDS
    while True:
        try:
            for index, (path, expected) in enumerate(targets):
                # Check top-down, including the outer ACL directory before root.
                for parent, identity in reversed(parents):
                    try:
                        actual = _stamp(parent)
                    except FileNotFoundError:
                        raise ValueError('guard_directory_replaced') from None
                    if actual != identity:
                        raise ValueError('guard_directory_replaced')
                for parent, identity in reversed(targets[index + 1:]):
                    try:
                        actual = _stamp(parent)
                    except FileNotFoundError:
                        continue  # An already removed owned outer is harmless.
                    if actual != identity:
                        raise ValueError('guard_directory_replaced')
                try:
                    actual = _stamp(path)
                except FileNotFoundError:
                    continue
                if actual != expected:
                    raise ValueError('guard_directory_replaced')
                if index == 0:
                    tempfile.TemporaryDirectory._rmtree(str(path))
                else:
                    path.rmdir()
            return
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('snapshot_guard_cleanup_failed') from None
            time.sleep(min(CLEANUP_RETRY_INTERVAL, remaining))


@contextmanager
def _retrying_private_container(temp_parent):
    from snapshot import private_container
    container = private_container(temp_parent)
    private = container.__enter__()
    record = None
    try:
        record = _cleanup_record(Path(private))
        yield private
    finally:
        try:
            container.__exit__(None, None, None)
        except OSError:
            # TemporaryDirectory may already have removed root while the outer
            # ACL directory is still locked. Keep ownership of both identities.
            if record is None:
                raise
            _cleanup_owned(record)


def _worker():
    # -I ignores the script directory. Import only the installed sibling module.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raw = sys.stdin.buffer.readline(8193)
    if len(raw) > 8192 or not raw.endswith(b'\n'):
        raise ValueError('invalid_guard_start')
    config = json.loads(raw)
    if set(config) != {'temp_parent'} or (config['temp_parent'] is not None and not isinstance(config['temp_parent'], str)):
        raise ValueError('invalid_guard_start')
    # The helper reads no project files or selected names and receives no secret.
    with _retrying_private_container(config['temp_parent']) as private:
        deadline = time.monotonic() + TTL
        print(json.dumps({'root': private, 'deadline': deadline}), flush=True)
        # Never delete while capture is still writing: it could recreate parents.
        # EOF during capture still cleans immediately; R seals capture once.
        if os.read(0, 1) != b'R':
            return 0
        stop = threading.Event()
        def eof():
            try:
                os.read(0, 1)
            finally:
                stop.set()
        threading.Thread(target=eof, daemon=True, name='snapshot-owner-eof').start()
        stop.wait(max(0, deadline - time.monotonic()))
    return 0


def _stamp(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise ValueError('guard_directory_invalid')
    return info.st_dev, info.st_ino


@contextmanager
def guarded_container(temp_parent=None):
    """Yield an owned directory, absolute deadline, and a process-liveness check.

    Capture callers never inherit the keeper's stdin into other children. A
    keeper failure invalidates snapshot.valid(); the caller cleans its exact
    recorded directory on ordinary unwind as a second ownership path.
    """
    if sys.platform not in ('linux', 'win32') or ((sys.platform == 'win32') != (os.name == 'nt')):
        raise OSError('snapshot_lifetime_platform_unavailable')
    env = {k: os.environ[k] for k in ('SystemRoot', 'SYSTEMROOT', 'WINDIR') if k in os.environ}
    # No credential/proxy/Python/Node environment inherited. Fixed stdlib helper.
    env.update({k: str(Path(temp_parent or tempfile.gettempdir())) for k in
                ('HOME', 'USERPROFILE', 'TEMP', 'TMP', 'TMPDIR')})
    env['PATH'] = os.defpath
    flags = subprocess.DETACHED_PROCESS if sys.platform == 'win32' else 0
    # No venv redirector: this helper needs stdlib and sibling HANDLE/ACL code only.
    executable = getattr(sys, '_base_executable', sys.executable)
    process = subprocess.Popen([executable, '-I', '-B', str(Path(__file__).resolve())],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        close_fds=True, env=env, creationflags=flags,
        start_new_session=sys.platform != 'win32')
    ready = queue.Queue()
    assert process.stdin is not None and process.stdout is not None
    thread = threading.Thread(target=lambda: ready.put(process.stdout.readline(8193)), daemon=True)
    thread.start()
    root = identity = outer = outer_identity = None
    try:
        message = json.dumps({'temp_parent': os.fspath(temp_parent) if temp_parent is not None else None}).encode() + b'\n'
        if len(message) > 8192:
            raise ValueError('guard_start_too_large')
        process.stdin.write(message)
        process.stdin.flush()
        line = ready.get(timeout=10)
        record = json.loads(line)
        if set(record) != {'root', 'deadline'} or type(record['root']) is not str or type(record['deadline']) not in (int, float):
            raise ValueError('guard_readiness_invalid')
        root = Path(record['root'])
        identity = _stamp(root)
        if sys.platform == 'win32':
            outer = root.parent
            outer_identity = _stamp(outer)
        deadline = record['deadline']
        now = time.monotonic()
        # Compare absolute endpoints: subtracting same-tick floats can round
        # (created + TTL) - now just above TTL, rejecting a live keeper.
        if not now < deadline <= now + TTL or process.poll() is not None:
            raise ValueError('guard_not_live')
        sealed = False
        def seal():
            nonlocal sealed
            if sealed or time.monotonic() >= deadline or process.poll() is not None:
                raise ValueError('snapshot_expired_before_publish')
            process.stdin.write(b'R')
            process.stdin.flush()
            sealed = True
        yield root, deadline, lambda: process.poll() is None, seal
    finally:
        # EOF is the sole stop signal; no renewed deadline or remote control API.
        try:
            output, error = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            output, error = process.communicate(timeout=5)
        finally:
            thread.join(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            # Reuse the pinned stdlib's readonly-file/symlink-safe cleanup. Do not
            # scan glob patterns or sweep unknown historical diagnostics folders.
            for path, expected in ((root, identity), (outer, outer_identity)):
                if path is not None and expected is not None and path.exists():
                    if _stamp(path) != expected:
                        raise ValueError('guard_directory_replaced')
                    tempfile.TemporaryDirectory._rmtree(str(path))
        if thread.is_alive() or process.returncode != 0 or output or error:
            raise RuntimeError('snapshot_guard_cleanup_failed')


if __name__ == '__main__':
    try:
        raise SystemExit(_worker())
    except Exception as error:
        print('snapshot_guard_failed:' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
