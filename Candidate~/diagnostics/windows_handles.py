"""Win32 same-HANDLE reads; local drive paths only, not an administrator sandbox.

Each ancestor stays open without write/delete sharing until reading completes.
No Path.resolve() and no reopening a validated file by name. Linux contract tests
use an injected API; only Windows-only tests can validate kernel enforcement.
"""
from contextlib import ExitStack
import re
import ctypes as c
import os

# Fixed-width Windows ABI types (ctypes.wintypes DWORD differs on Linux).
DWORD = c.c_uint32
HANDLE = c.c_void_p


class FileTime(c.Structure):
    _fields_ = [('dwLowDateTime', DWORD), ('dwHighDateTime', DWORD)]


class FileInfo(c.Structure):
    _fields_ = [('dwFileAttributes', DWORD), ('ftCreationTime', FileTime),
                ('ftLastAccessTime', FileTime), ('ftLastWriteTime', FileTime),
                ('dwVolumeSerialNumber', DWORD), ('nFileSizeHigh', DWORD),
                ('nFileSizeLow', DWORD), ('nNumberOfLinks', DWORD),
                ('nFileIndexHigh', DWORD), ('nFileIndexLow', DWORD)]


class BasicInfo(c.Structure):
    _fields_ = [('CreationTime', c.c_int64), ('LastAccessTime', c.c_int64),
                ('LastWriteTime', c.c_int64), ('ChangeTime', c.c_int64),
                ('FileAttributes', DWORD)]


class Win32:
    def __init__(self, *, library=None):
        if library is None:
            if os.name != 'nt':
                raise OSError('Windows kernel required')
            library = c.WinDLL('kernel32', use_last_error=True)
        self.lib = library
        signatures = {
            'CreateFileW': (HANDLE, [c.c_wchar_p, DWORD, DWORD, HANDLE, DWORD, DWORD, HANDLE]),
            'CloseHandle': (c.c_int32, [HANDLE]),
            'GetFileType': (DWORD, [HANDLE]),
            'GetDriveTypeW': (DWORD, [c.c_wchar_p]),
            'GetFileInformationByHandle': (c.c_int32, [HANDLE, c.POINTER(FileInfo)]),
            'GetFileInformationByHandleEx': (c.c_int32, [HANDLE, c.c_int32, HANDLE, DWORD]),
            'ReadFile': (c.c_int32, [HANDLE, HANDLE, DWORD, c.POINTER(DWORD), HANDLE]),
            'GetFinalPathNameByHandleW': (DWORD, [HANDLE, c.c_wchar_p, DWORD, DWORD]),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(library, name)
            fn.restype, fn.argtypes = result, args

    @staticmethod
    def check(ok):
        if not ok:
            # Never include the selected path/content in error diagnostics.
            raise OSError(getattr(c, 'get_last_error', lambda: 0)(), 'Windows handle operation failed')

    def local_drive(self, drive):
        return self.lib.GetDriveTypeW(drive) == 3  # DRIVE_FIXED; no UNC/removable/network.

    def open(self, path, *, directory):
        handle = self.lib.CreateFileW('\\\\?\\' + path,
            0x80 if directory else 0x80000000,  # attributes / GENERIC_READ
            1, None, 3, 0x02200000, None)  # SHARE_READ, OPEN_EXISTING, NOFOLLOW+BACKUP
        self.check(handle is not None and handle != c.c_void_p(-1).value)
        return handle

    def close(self, handle):
        self.check(self.lib.CloseHandle(handle))

    def disk(self, handle):
        return self.lib.GetFileType(handle) == 1

    def info(self, handle):
        info, basic = FileInfo(), BasicInfo()
        self.check(self.lib.GetFileInformationByHandle(handle, c.byref(info)))
        self.check(self.lib.GetFileInformationByHandleEx(handle, 0, c.byref(basic), c.sizeof(basic)))
        return (info.dwFileAttributes, info.nNumberOfLinks,
                (info.nFileSizeHigh << 32) | info.nFileSizeLow,
                info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow,
                (info.ftLastWriteTime.dwHighDateTime << 32) | info.ftLastWriteTime.dwLowDateTime,
                basic.ChangeTime)

    def final_path(self, handle):
        length = self.lib.GetFinalPathNameByHandleW(handle, None, 0, 0)
        self.check(0 < length <= 32768)
        buffer = c.create_unicode_buffer(length)
        actual = self.lib.GetFinalPathNameByHandleW(handle, buffer, length, 0)
        self.check(0 < actual < length)
        return buffer.value

    def read(self, handle, limit):
        chunks = []
        while limit:
            size = min(limit, 65536)
            buffer, count = c.create_string_buffer(size), DWORD()
            self.check(self.lib.ReadFile(handle, buffer, size, c.byref(count), None))
            if not count.value:
                break
            self.check(count.value <= size)
            chunks.append(buffer.raw[:count.value])
            limit -= count.value
        return b''.join(chunks)


class SecurityAttributes(c.Structure):
    _fields_ = [('nLength', DWORD), ('lpSecurityDescriptor', HANDLE), ('bInheritHandle', c.c_int32)]


def create_private_directory(path, *, kernel=None, security=None):
    """Apply owner+SYSTEM-only inheritable protected DACL at creation, not later."""
    if os.name != 'nt' and (kernel is None or security is None):
        raise OSError('Windows kernel required')
    kernel = kernel or c.WinDLL('kernel32', use_last_error=True)
    security = security or c.WinDLL('advapi32', use_last_error=True)
    convert = security.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.restype, convert.argtypes = c.c_int32, [c.c_wchar_p, DWORD, c.POINTER(HANDLE), c.POINTER(DWORD)]
    kernel.CreateDirectoryW.restype = c.c_int32
    kernel.CreateDirectoryW.argtypes = [c.c_wchar_p, c.POINTER(SecurityAttributes)]
    kernel.LocalFree.restype, kernel.LocalFree.argtypes = HANDLE, [HANDLE]
    descriptor = HANDLE()
    Win32.check(convert('D:P(A;OICI;FA;;;OW)(A;OICI;FA;;;SY)', 1, c.byref(descriptor), None))
    try:
        attributes = SecurityAttributes(c.sizeof(SecurityAttributes), descriptor.value, 0)
        Win32.check(kernel.CreateDirectoryW(str(path), c.byref(attributes)))
    finally:
        kernel.LocalFree(descriptor)


def read_selected(root, components, limit, *, api=None):
    if api is None:
        api = Win32()
    if not isinstance(root, str) or not re.match(r'^[A-Za-z]:\\', root):
        raise ValueError('explicit local drive absolute root required')
    parts = root[3:].split('\\') if root[3:] else []
    if not components or not 0 < limit <= 1024 * 1024:
        raise ValueError('selection or byte limit')
    for part in parts + components:
        if (not part or part in ('.', '..') or part[-1] in '. '
                or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in part)
                or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])', part.split('.')[0])):
            raise ValueError('unsafe Windows path component')
    drive = root[:3]
    if not api.local_drive(drive):
        raise ValueError('only local fixed drives permitted')
    paths = [drive]
    for part in parts + components:
        paths.append(paths[-1].rstrip('\\') + '\\' + part)
    with ExitStack() as stack:
        pinned = []
        for index, path in enumerate(paths):
            directory = index < len(paths) - 1
            handle = api.open(path, directory=directory)
            stack.callback(api.close, handle)
            info = api.info(handle)
            final = api.final_path(handle)
            if (info[0] & 0x400 or bool(info[0] & 0x10) != directory
                    or not api.disk(handle) or final.casefold() != ('\\\\?\\' + path).casefold()):
                raise ValueError('unsafe Windows handle or final path')
            if not directory and info[1] != 1:
                raise ValueError('unsafe hardlink')
            if not directory and info[2] > limit:
                raise ValueError('file byte limit')
            pinned.append((handle, info, final))
        data = api.read(pinned[-1][0], limit + 1)
        if len(data) > limit:
            raise ValueError('file byte limit')
        for index, (handle, before, final) in enumerate(pinned):
            after = api.info(handle)
            # Directory timestamps can change for unrelated siblings; identity,
            # attributes, and final names must stay fixed. Leaf: full evidence.
            indices = range(len(before)) if index == len(pinned) - 1 else (0, 3, 4)
            if (any(before[i] != after[i] for i in indices)
                    or api.final_path(handle) != final):
                raise ValueError('source changed while exporting')
        return data
