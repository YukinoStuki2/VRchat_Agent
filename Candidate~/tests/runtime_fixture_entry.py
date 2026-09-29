"""TEST ONLY anonymous synthetic WS fixture; never shipped as the runtime entry."""
import argparse
import asyncio
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='VRchat_Agent本地候选入口（尚未完成Unity端，不用于真实工程）')
    parser.add_argument('--project', required=True, help='Unity原生project hash；禁止自动选择')
    parser.add_argument('--port', required=True, type=int, help='本地未占用端口，仅监听127.0.0.1')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be 1024..65535')
    os.environ['DISABLE_TELEMETRY'] = 'true'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
    native = Path(__file__).resolve().parents[1] / 'native/src'
    sys.path.insert(0, str(native))
    # Isolated source overlay; never patch a shared/installed SDK in place.
    sys.path.insert(0, str(native.parents[1] / 'dependencies/mcp-1.29.1'))
    from candidate_runtime import create_app, create_server
    import uvicorn

    async def serve():
        app = create_app(create_server(args.project))
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port,
            access_log=False, log_level='warning', workers=1,
            timeout_graceful_shutdown=5, limit_concurrency=64,
            ws_max_size=1024 * 1024, ws_max_queue=8)).serve()
    asyncio.run(serve())


if __name__ == '__main__':
    main()
