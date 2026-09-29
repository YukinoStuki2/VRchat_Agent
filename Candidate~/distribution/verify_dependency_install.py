"""Read back a hash-locked fresh installation; not runtime/Unity acceptance."""
import importlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import sys

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def inspect_installation():
    declarations = []
    for line in (ROOT / 'distribution/requirements.lock').read_text().splitlines():
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9_.-]*==', line):
            continue
        declaration = Requirement(line.removesuffix('\\').strip())
        if declaration.marker is None or declaration.marker.evaluate():
            declarations.append(declaration)
    assert declarations, 'empty lock'
    names = [d.name.lower().replace('_', '-') for d in declarations]
    assert len(names) == len(set(names)), 'duplicate active lock entry'
    installed = {}
    for dependency in declarations:
        actual = version(dependency.name)
        assert dependency.specifier.contains(actual, prereleases=True), dependency.name
        installed[dependency.name] = actual
    imports = ('httpx', 'fastmcp', 'mcp', 'pydantic', 'tomli', 'fastapi',
               'uvicorn', 'click', 'websockets', 'cryptography', 'joserfc')
    for name in imports:
        importlib.import_module(name)
    return {'scope': 'fresh dependency installation only; not application or Unity acceptance',
            'python': sys.version, 'platform': platform.platform(),
            'all_active_lock_versions_match': True, 'active_lock_count': len(installed),
            'installed': installed, 'direct_imports': list(imports), 'passed': True}


if __name__ == '__main__':
    result = inspect_installation()
    output = Path(sys.argv[1])
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'installed'}))
