"""Owned TLS readiness observer; no installer, endpoint discovery, or reconnect.

Before the first connection only ECONNREFUSED is retried while the owned child
starts. After TLS admission the SDK connection is single-use. A missing Unity
peer may arrive during startup; after readiness ANY loss revokes readiness.
"""
import asyncio
import hashlib
import ssl
import time


async def observe_runtime(owner, binding, *, stop=None, receipt=None, startup_timeout=12):
    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.exceptions import ToolError
    receipt = {} if receipt is None else receipt
    def cancelled():
        return binding.cancelled.is_set() or (stop is not None and stop.is_set())
    started = time.monotonic()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=owner.tls.certificate.decode('ascii'))
    deadline = started + startup_timeout
    while not binding.started.is_set():
        if cancelled():return
        if time.monotonic() >= deadline:raise TimeoutError('owned_start_missing')
        await asyncio.sleep(.05)
    while not cancelled():
        if time.monotonic() >= deadline:raise TimeoutError('owned_start_timeout')
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                '127.0.0.1',owner.port,ssl=context,ssl_handshake_timeout=2),3)
            try:
                cert = writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
                if hashlib.sha256(cert).hexdigest() != owner.tls.pin:
                    raise PermissionError('owned_server_pin_mismatch')
            finally:
                writer.close()
                await writer.wait_closed()
            break
        except ConnectionRefusedError:
            await asyncio.sleep(.05)
    if cancelled():return
    session_id = None
    async def record_response(response):
        nonlocal session_id
        if response.request.method == 'POST' and response.is_success:
            current = response.headers.get('mcp-session-id')
            if current:
                session_id = current
                receipt['session_created'] = True
        if (response.request.method == 'DELETE' and response.status_code == 200
                and session_id is not None and response.request.headers.get('mcp-session-id') == session_id):
            receipt['session_cleanup_confirmed'] = True
    def factory(**kwargs):
        kwargs.update(verify=context,trust_env=False,follow_redirects=False,timeout=httpx.Timeout(3),event_hooks={"response":[record_response]})
        return httpx.AsyncClient(**kwargs)
    transport = StreamableHttpTransport(f'https://127.0.0.1:{owner.port}/mcp',
        headers={'Authorization':'Bearer '+owner.identity.credentials['hermes'].token},
        httpx_client_factory=factory)
    async with Client(transport, timeout=3) as client:
        while not cancelled():
            if time.time() >= owner.identity.expires_at:raise TimeoutError('owned_run_expired')
            try:
                result = await client.call_tool('agent_status',{})
            except ToolError as exc:
                if (not binding.ready.is_set() and str(exc)=='expected_project_not_connected'
                        and time.monotonic()<deadline):
                    await asyncio.sleep(.1)
                    continue
                raise
            data = result.data
            if (type(data) is not dict or data.get('success') is not True
                    or type(data.get('data')) is not dict or data['data'].get('read_only') is not True):
                raise PermissionError('owned_gate_status_invalid')
            binding.ready.set()
            await asyncio.sleep(.2)
