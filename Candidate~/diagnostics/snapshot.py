"""Local text snapshot exporter: Linux descriptors / Windows locked HANDLEs.

Sources are selected locally. Windows adapter and ACL code have portable ABI
contract tests; a real Windows kernel run remains a separate mandatory gate.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from pathlib import Path
import os
import re
import stat
import sys
import tempfile
import threading
import time

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_FILES = 64


def redact_text(data):
    text = data.decode('utf-8', errors='strict')
    if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
        raise ValueError('not permitted text')
    if re.search(r'-----BEGIN [^-]*PRIVATE KEY-----', text):
        raise ValueError('private key content not exportable')
    text = re.sub(r'(?i)https?://[^\s<>"\']+', '[REDACTED]', text)
    text = re.sub(r'(?im)(\b(?:authorization|cookie|set-cookie|password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret)\b["\']?\s*[:=]\s*)[^\r\n]+', r'\1[REDACTED]', text)
    return text.encode('utf-8')


@dataclass(frozen=True)
class Snapshot:
    root: Path
    task_id: str
    files: tuple
    expires_at: float
    _active: threading.Event

    def valid(self):
        return self._active.is_set() and time.monotonic() < self.expires_at


def relative_name(name):
    if (type(name) is not str or not name or len(name) > 512 or name.startswith('/')
            or any(c in name for c in '\\:\x00')
            or any(p in ('', '.', '..') or p != p.strip() for p in name.split('/'))):
        raise ValueError('invalid selected relative path')
    if any(p.startswith('.') or any(s in p.casefold() for s in ('credential', 'secret', 'password', 'id_rsa', 'id_ed25519'))
           or p.casefold() in ('config.json', 'auth.json') for p in name.split('/')):
        raise ValueError('sensitive name not exportable')
    if Path(name).suffix.casefold() not in {'.cs', '.log', '.txt', '.json', '.yaml', '.yml', '.md', '.shader', '.controller', '.mat', '.meta'}:
        raise ValueError('unapproved text type')
    return name.split('/')


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def owned_fd(stack, name, flags, *, parent=None):
    fd = os.open(name, flags, dir_fd=parent)
    stack.callback(os.close, fd)
    return fd


def read_selected(root, name):
    if sys.platform == 'win32':
        from windows_handles import read_selected as windows_read
        return windows_read(os.fspath(root), relative_name(name), MAX_FILE_BYTES)
    if sys.platform != 'linux':
        raise OSError('platform boundary not implemented')
    absolute = os.fspath(root)
    if not absolute.startswith('/') or '\x00' in absolute or any(p in ('.', '..', '') for p in absolute[1:].split('/')):
        raise ValueError('explicit absolute root without aliases required')
    components = relative_name(name)
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        parent = owned_fd(stack, '/', flags | os.O_DIRECTORY)
        chain = []
        for part in absolute[1:].split('/') + components[:-1]:
            child = owned_fd(stack, part, flags | os.O_DIRECTORY, parent=parent)
            info = os.fstat(child)
            chain.append((parent, part, child, info.st_dev, info.st_ino))
            parent = child
        fd = owned_fd(stack, components[-1], flags | os.O_NONBLOCK, parent=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('selected file must be regular and singly linked')
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError('file byte limit')
        # Read the very descriptor that was validated, never reopen a pathname.
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('file byte limit')
        after = os.fstat(fd)
        named = os.stat(components[-1], dir_fd=parent, follow_symlinks=False)
        if identity(before) != identity(after) or identity(after) != identity(named):
            raise ValueError('source replaced or changed while exporting')
        for ancestor, part, child, dev, ino in chain:
            named = os.stat(part, dir_fd=ancestor, follow_symlinks=False)
            opened = os.fstat(child)
            if (named.st_dev, named.st_ino) != (dev, ino) or (opened.st_dev, opened.st_ino) != (dev, ino) or not stat.S_ISDIR(named.st_mode):
                raise ValueError('source ancestor replaced while exporting')
        return data


@contextmanager
def private_container(temp_parent):
    if sys.platform != 'win32':
        with tempfile.TemporaryDirectory(prefix='diagnostics-', dir=temp_parent) as private:
            yield private
        return
    from windows_handles import create_private_directory
    from uuid import uuid4
    outer = Path(temp_parent or tempfile.gettempdir()) / ('diagnostics-acl-' + uuid4().hex)
    create_private_directory(outer)
    try:
        # Reuse stdlib's Windows readonly-file cleanup inside an already private
        # ACL parent. No insecure chmod-only directory ever holds snapshot bytes.
        with tempfile.TemporaryDirectory(prefix='capture-', dir=outer) as private:
            yield private
    finally:
        outer.rmdir()


@contextmanager
def capture(root, files, *, task_id, temp_parent=None):
    if (type(task_id) is not str or not task_id or len(task_id) > 128
            or task_id != task_id.strip() or any(ord(c) < 32 for c in task_id)):
        raise ValueError('explicit local task id required')
    if type(files) not in (list, tuple) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('file count limit')
    names = tuple(files)
    for name in names:
        relative_name(name)
    keys = [n.casefold() for n in names] if sys.platform == 'win32' else names
    if len(set(keys)) != len(names):
        raise ValueError('duplicate selection')
    with private_container(temp_parent) as private:
        target = Path(private) / 'snapshot'
        target.mkdir(mode=0o700)
        total = 0
        for name in names:
            data = read_selected(root, name)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError('total byte limit')
            data = redact_text(data)
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            output.chmod(0o400)
        for folder in sorted(target.rglob('*'), reverse=True):
            if folder.is_dir():
                folder.chmod(0o500)
        target.chmod(0o500)
        active = threading.Event()
        active.set()
        try:
            yield Snapshot(target, task_id, names, time.monotonic() + 300, active)
        finally:
            active.clear()
