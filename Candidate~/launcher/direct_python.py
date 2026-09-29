"""Pinned CPython 3.11 launcher metadata, no authority or credentials.

Windows venv python.exe is a redirector. Invoke its actual base executable with
CPython's own __PYVENV_LAUNCHER__ hint so the real process keeps the selected
venv and is the exact child held by the editor. Never accept a grandparent PID.
Reference: CPython v3.11.9 Modules/getpath.py, ENV___PYVENV_LAUNCHER__ branch.
This private CPython contract is version-gated and must be tested on Windows.
"""
import json
import os
from pathlib import Path
import sys


def current():
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 11):
        raise RuntimeError('cpython_311_required')
    selected = sys.executable
    executable = sys._base_executable if os.name == 'nt' else selected
    if not all(Path(p).is_absolute() and Path(p).is_file() for p in (selected, executable)):
        raise RuntimeError('interpreter_path_invalid')
    return {'executable': executable, 'selected': selected, 'windows': os.name == 'nt'}


def environment_hint():
    info = current()
    return {'__PYVENV_LAUNCHER__': info['selected']} if info['windows'] else {}


if __name__ == '__main__':
    try:
        print(json.dumps(current(), separators=(',', ':')), flush=True)
    except Exception:
        raise SystemExit(2)
