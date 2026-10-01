"""Uninstalled, single-session SDK transport for a trusted in-memory handoff.

No receiver, identity attestation, gateway installation, or credential persistence.
The host must authenticate the source of every argument before calling connect.
"""
import asyncio
import ssl
import hashlib
import re
import time


class Connection:
    """Own one SDK task; compatible with the candidate binding's peer contract."""
    def __init__(self):
        self.session = None
        self.session_cleanup_confirmed = False
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._failed = False
        self._task = None

    async def _run(self, *, port, context, bearer, expires_at):
        client = None
        session_id = None
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
            from tools.mcp_tool import sdk_httpx
            httpx = sdk_httpx()
            deadline = asyncio.get_running_loop().time() + max(0, expires_at - time.time())
            url = f'https://127.0.0.1:{port}/mcp'
            get_started = False
            def refuse():
                self.session = None
                self._failed = True
                self._stop.set()
                raise RuntimeError('candidate_endpoint_policy')
            async def before(request):
                nonlocal get_started
                if (str(request.url) != url or request.method not in ('GET','POST','DELETE')
                        or 'last-event-id' in request.headers
                        or (session_id is not None and request.headers.get('mcp-session-id') != session_id)):
                    refuse()
                if request.method != 'DELETE' and (self._stop.is_set() or time.time() >= expires_at
                        or asyncio.get_running_loop().time() >= deadline):
                    refuse()
                if request.method == 'GET':
                    if get_started:
                        refuse()
                    get_started = True
            async def after(response):
                nonlocal session_id
                if 300 <= response.status_code < 400:
                    refuse()
                if (response.request.method == 'DELETE' and response.status_code == 200
                        and session_id is not None and response.request.headers.get('mcp-session-id') == session_id):
                    self.session_cleanup_confirmed = True
                current = response.headers.get('mcp-session-id')
                if current:
                    if session_id is not None and current != session_id:
                        refuse()
                    session_id = current
            client = httpx.AsyncClient(verify=context, trust_env=False, follow_redirects=False,
                headers={'Authorization':'Bearer '+bearer}, timeout=httpx.Timeout(8, read=30),
                event_hooks={'request':[before], 'response':[after]})
            async with client:
                async with streamable_http_client(url, http_client=client) as streams:
                    async with ClientSession(streams[0], streams[1], read_timeout_seconds=8) as session:
                        async with asyncio.timeout(8):
                            await session.initialize()
                            if session_id is None:
                                refuse()
                            await session.list_tools()  # round trip drains initialized before admission
                        self.session = session
                        self._ready.set()
                        try:
                            await asyncio.wait_for(self._stop.wait(), max(0, deadline - asyncio.get_running_loop().time()))
                        except asyncio.TimeoutError:
                            pass
                        self.session = None
        except Exception:
            self._failed = True
        finally:
            self.session = None
            if client is not None:
                client.headers.clear()
            if session_id is not None and not self.session_cleanup_confirmed:
                self._failed = True
            self._ready.set()

    async def shutdown(self):
        self.session = None
        self._stop.set()
        cancelled = None
        while not self._task.done():
            try:
                await asyncio.shield(self._task)
            except asyncio.CancelledError as exc:
                cancelled = exc
        self._task.result()
        if self._failed:
            raise RuntimeError('candidate_connection_failed')
        if cancelled is not None:
            raise cancelled


async def connect(*, port, certificate, pin, bearer, expires_at):
    """Start one owned SDK session, then transfer it to the trusted caller."""
    try:
        now = time.time()
        if (type(port) is not int or not 1024 <= port <= 65535
                or type(expires_at) is not int or not now < expires_at <= now + 3600
                or type(bearer) is not str or re.fullmatch(r'[A-Za-z0-9._~-]{1,8192}', bearer) is None
                or type(pin) is not str or re.fullmatch(r'[0-9a-f]{64}', pin) is None
                or type(certificate) is not str or len(certificate) > 16384
                or re.fullmatch(r'-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\r?\n?', certificate) is None
                or hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest() != pin):
            raise ValueError()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=certificate)
        if context.get_ca_certs():
            raise ValueError()  # accept only the owner's one-run leaf, not a CA trust grant
    except (ValueError, TypeError, ssl.SSLError):
        raise ValueError('candidate_handoff_invalid') from None
    peer = Connection()
    peer._task = asyncio.create_task(peer._run(port=port, context=context,
        bearer=bearer, expires_at=expires_at))
    try:
        await peer._ready.wait()
        if peer.session is None:
            raise RuntimeError('candidate_connection_failed')
        return peer
    except BaseException:
        await peer.shutdown()
        raise
