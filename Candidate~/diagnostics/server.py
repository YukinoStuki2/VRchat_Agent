"""Locally captured snapshot only; mature filesystem implementation reused.

No network listener or automatic startup. The local CLI owns capture lifetime
and preview approval. Legacy embedding callers still own that local boundary.
Packaging and real Windows lifecycle validation remain pending.
"""
from pathlib import Path
import os
import shutil
import sys

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError
from fastmcp.server.providers.proxy import ProxyProvider
from fastmcp.server.middleware import Middleware
from fastmcp.server.transforms import Visibility

ENTRY = (Path(__file__).resolve().parents[2] / 'Experiments~/p0.2/filesystem/'
         'fs01-candidate/src/filesystem/dist/index.js')
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


def backend_transport(root):
    if sys.platform == 'win32':
        node = shutil.which('node.exe')
        if not node:
            raise ValueError('local_node_executable_required')
        # SDK keeps only its documented OS environment allowlist, not arbitrary
        # NODE_OPTIONS/API keys. Explicitly relocate profile/temp into this lease.
        env = {key: str(root.parent) for key in ('HOME', 'USERPROFILE', 'APPDATA',
               'LOCALAPPDATA', 'TEMP', 'TMP')}
        env['SYSTEMROOT'] = os.environ.get('SYSTEMROOT', '')
        env['PATH'] = os.path.dirname(node)
        return StdioTransport(command=node, args=[str(ENTRY), str(root)],
                              env=env, cwd=str(root), keep_alive=False)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(root.parent),
           'TMPDIR': str(root.parent), 'LANG': 'C.UTF-8'}
    return StdioTransport(command='/usr/bin/env',
        args=['-i', *[f'{k}={v}' for k, v in env.items()], '/usr/bin/node', str(ENTRY), str(root)],
        env=env, cwd=str(root), keep_alive=False)


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
