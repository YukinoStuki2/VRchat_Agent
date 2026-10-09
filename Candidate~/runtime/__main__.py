"""One owned, finite, authenticated loopback TLS run; no anonymous CLI mode."""
import argparse
import asyncio
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description='VRchat_Agent受控候选入口（需本地所有者引导）')
    parser.add_argument('--project', required=True, help='精确Unity原生project hash')
    parser.add_argument('--port', required=True, type=int, help='仅监听127.0.0.1')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be 1024..65535')
    # Import no server components and open no socket until binding validates.
    from owner_bootstrap import consume_environment
    try:
        binding = consume_environment(args.project, args.port)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    control_locator = os.environ.pop('VRCHAT_AGENT_RELOAD', None)
    if control_locator is not None:
        import json,re
        from reload_control import decode,keys
        try:
            control_locator=decode(control_locator)
            keys(control_locator,'version','address','parent_pid','expires_at')
            if (type(control_locator['version']) is not int or control_locator['version']!=1
                or type(control_locator['parent_pid']) is not int or control_locator['parent_pid']!=os.getppid()
                or type(control_locator['expires_at']) is not int or control_locator['expires_at']!=binding.expires_at
                or type(control_locator['address']) is not str
                or re.fullmatch('vrchat-local-[0-9a-f]{48}',control_locator['address']) is None):raise ValueError()
        except Exception:raise SystemExit('LOCAL_CONTROL_INVALID') from None
    os.environ['DISABLE_TELEMETRY'] = 'true'
    native = Path(__file__).resolve().parents[1] / 'native/src'
    sys.path.insert(0, str(native))
    sys.path.insert(0, str(native.parents[1] / 'dependencies/mcp-1.29.1'))
    from candidate_runtime import create_app, create_server
    from tls_context import load_tls_context
    import uvicorn
    try:
        mcp_auth, unity_auth = binding.verifiers()
        context = load_tls_context(binding.tls)
    except Exception:
        raise SystemExit('BINDING_INVALID') from None

    async def serve():
        mcp = create_server(args.project, mcp_auth=mcp_auth)
        app = create_app(mcp, unity_auth=unity_auth)
        config = uvicorn.Config(app, host='127.0.0.1', port=args.port,
            access_log=False, log_level='warning', workers=1,
            timeout_graceful_shutdown=5, limit_concurrency=64,
            ws_max_size=1024 * 1024, ws_max_queue=8)
        config.load()
        config.ssl = context
        server = uvicorn.Server(config)
        async def expiry():
            await asyncio.sleep(max(0,binding.expires_at-time.time()))
            server.should_exit = True
        control_task=None
        async def local_control():
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
            from launcher.peer_identity import PeerProcess
            from launcher.peer_channel import PeerChannel
            from reload_control import serve_channel,joined_worker
            import json,threading
            channel=None
            halt=threading.Event()
            try:
                with PeerProcess(os.getppid()) as peer:
                    def connect():
                        nonlocal channel
                        channel=PeerChannel.connect(control_locator['address'],peer,stop=halt,
                            deadline=time.monotonic()+max(0,binding.expires_at-time.time()))
                    await joined_worker(halt,connect)
                    await joined_worker(halt,channel.send,json.dumps({'kind':'control_ready','version':1,
                        'project_id':args.project},separators=(',',':')).encode('utf-8'))
                    await serve_channel(mcp._candidate_runtime,channel,reusable=True)
            finally:
                if channel is not None:channel.stop.set();channel.close()
                server.should_exit=True
        if control_locator is not None:control_task=asyncio.create_task(local_control())
        timer = asyncio.create_task(expiry())
        try:
            await server.serve()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)
            if control_task is not None:
                control_task.cancel()
                await asyncio.gather(control_task,return_exceptions=True)
    asyncio.run(serve())


if __name__ == '__main__':
    main()
