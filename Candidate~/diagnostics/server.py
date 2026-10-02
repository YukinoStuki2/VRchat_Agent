"""Locally captured snapshot only; mature filesystem implementation reused.

No network listener or automatic startup. The local CLI owns capture lifetime
and preview approval. Legacy embedding callers still own that local boundary.
Packaging and real Windows lifecycle validation remain pending.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import sys

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError
from fastmcp.server.providers.proxy import ProxyProvider
from fastmcp.server.middleware import Middleware
from fastmcp.server.transforms import Visibility

ENTRY = Path(__file__).resolve().parents[1] / 'diagnostics-backend/filesystem/dist/index.js'
READ_TOOLS = {'read_text_file', 'list_directory', 'get_file_info'}


class LocalSnapshotLease(Middleware):
    def __init__(self, snapshot, approved_digest=None):
        self.snapshot = snapshot
        self.client = None
        self.approved_digest = approved_digest

    def verify_preview(self):
        if self.approved_digest is not None:
            from cli import snapshot_digest
            try:
                matched = snapshot_digest(self.snapshot) == self.approved_digest
            except (OSError, ValueError):
                matched = False
            if not matched:
                self.snapshot._active.clear()
                raise ToolError('approved_snapshot_changed')

    async def on_request(self, context, call_next):
        # Initialize/ping are handled locally by FastMCP, not proxied. No backend
        # process or file access is needed before binding a data/catalog request.
        if context.method in ('initialize', 'ping'):
            return await call_next(context)
        if not self.snapshot.valid():
            raise ToolError('local_snapshot_expired_or_closed')
        self.verify_preview()
        ctx = context.fastmcp_context
        if ctx is None or not ctx.session_id:
            raise ToolError('session_required')
        if self.client is None:
            self.client = ctx.session_id
        if self.client != ctx.session_id:
            raise ToolError('snapshot_bound_to_other_session')
        result = await call_next(context)
        if not self.snapshot.valid():
            raise ToolError('local_snapshot_expired_or_closed')
        self.verify_preview()
        return result


def bundled_node():
    """Payload integrity, not an OS sandbox or an independent approval signature."""
    base = ENTRY.parents[2]
    try:
        inventory = json.loads((base/'inventory.json').read_bytes())
        key = 'windows-x86_64' if sys.platform == 'win32' else 'linux-x86_64'
        pins = json.loads((Path(__file__).resolve().parents[1]/'distribution/diagnostics-backend.lock.json').read_bytes())
        executable = 'node/node.exe' if sys.platform == 'win32' else 'node/node'
        if (inventory['schema'] != 1 or inventory['platform'] != key or
                inventory['node_archive_sha256'] != pins['platforms'][key]['sha256'] or
                inventory['source_inputs'] != pins['inputs'] or
                inventory['node_version'] != pins['node_version'] or
                inventory['upstream_commit'] != pins['upstream_commit'] or
                inventory['node_executable'] != executable or
                inventory['entry'] != 'filesystem/dist/index.js' or
                inventory['missing_notice_packages'] != []):
            raise ValueError()
        files = inventory['files']
        if not isinstance(files,dict) or not {executable,'filesystem/dist/index.js'} <= files.keys():
            raise ValueError()
        if base.is_symlink() or any(p.is_symlink() for p in base.rglob('*')):
            raise ValueError()
        actual = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
        if actual != set(files) | {'inventory.json'}:
            raise ValueError()
        for name,digest in files.items():
            path=PurePosixPath(name)
            if (str(path)!=name or path.is_absolute() or '..' in path.parts or
                    '\\' in name or ':' in name or
                    hashlib.sha256((base/path).read_bytes()).hexdigest()!=digest):
                raise ValueError()
        return base/executable
    except (OSError, KeyError, TypeError, ValueError):
        raise ValueError('bundled_diagnostic_backend_invalid') from None


def backend_transport(root):
    node = bundled_node()
    # Native executable on both platforms; no env shell or PATH fallback.
    # SDK merges only OS essentials; NODE_OPTIONS/credentials are not inherited.
    env = {key: str(root.parent) for key in ('HOME','USERPROFILE','APPDATA',
        'LOCALAPPDATA','TEMP','TMP','TMPDIR')}
    env['PATH'] = str(node.parent)
    env['LANG'] = 'C.UTF-8'
    if sys.platform == 'win32':
        env['SYSTEMROOT'] = os.environ.get('SYSTEMROOT','')
    return StdioTransport(command=str(node),args=[str(ENTRY),str(root)],
        env=env,cwd=str(root),keep_alive=False)

def create_server(snapshot, *, approved_digest=None):
    if not snapshot.valid() or not ENTRY.is_file():
        raise ValueError('snapshot_or_pinned_backend_unavailable')
    root = snapshot.root
    backend = Client(backend_transport(root), roots=[root.as_uri()])
    # Reuse the mature provider, without FastMCPProxy's eager upstream initialize
    # and forwarded ping. These otherwise run before lease and session checks.
    proxy = FastMCP(name='vrchat-agent-diagnostic-snapshot')
    proxy.provider_error_strategy = 'raise'
    proxy.add_provider(ProxyProvider(lambda: backend.new()))
    proxy.add_transform(Visibility(False, match_all=True))
    proxy.add_transform(Visibility(True, names=READ_TOOLS | {'agent_diagnostics_status'}, components={'tool'}))
    proxy.add_middleware(LocalSnapshotLease(snapshot, approved_digest))

    @proxy.tool(name='agent_diagnostics_status')
    def status() -> dict:
        return {'task_id': snapshot.task_id, 'root': str(root),
                'selected': list(snapshot.files), 'read_only': True,
                'notice': '本地选定的脱敏快照，非实时工程；脱敏不保证发现所有秘密。'}

    return proxy
