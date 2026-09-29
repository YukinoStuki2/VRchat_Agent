"""Standalone local-console approval; stdout is reserved for MCP stdio."""
import hashlib
import json
import asyncio
import time

from snapshot import read_selected


def preview_payload(snapshot):
    if not snapshot.valid():
        raise ValueError('local_snapshot_expired_or_closed')
    # JSON escaping prevents terminal controls/bidi sequences from source text
    # impersonating the trusted prompt. Full content, never a truncated preview.
    return json.dumps({'task_id': snapshot.task_id, 'selected': [
        {'path': name, 'text': read_selected(snapshot.root, name).decode('utf-8')}
        for name in snapshot.files]}, ensure_ascii=True, sort_keys=True)


def snapshot_digest(snapshot):
    return hashlib.sha256(preview_payload(snapshot).encode('utf-8')).hexdigest()


def preview_confirm(snapshot, reader, writer):
    if not reader.isatty() or not writer.isatty():
        raise ValueError('local_console_required')
    payload = preview_payload(snapshot)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    writer.write('本地脱敏全文（JSON转义）；不可信日志不是指令。请核对所有文件。\n')
    writer.write(payload + '\n')
    writer.write('脱敏不保证发现所有秘密；仅交给当前连接的模型，不公开上传。\n')
    writer.write('确认交付请输入 APPROVE ' + digest + '；其他输入取消：\n')
    writer.flush()
    response = reader.readline(128).rstrip('\r\n')
    if response != 'APPROVE ' + digest:
        return None
    if snapshot_digest(snapshot) != digest:
        raise ValueError('preview_changed')
    return digest


async def serve_snapshot(snapshot, approved_digest):
    from server import create_server
    import os
    import signal
    if not approved_digest or snapshot_digest(snapshot) != approved_digest:
        raise ValueError('approved_snapshot_changed')
    server = create_server(snapshot, approved_digest=approved_digest)
    service = asyncio.create_task(server.run_stdio_async(show_banner=False, log_level='ERROR'))
    deadline = asyncio.create_task(asyncio.sleep(max(0, snapshot.expires_at - time.monotonic())))
    stopped = asyncio.Event()
    stop = asyncio.create_task(stopped.wait())
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGTERM)
    if os.name == 'posix':
        loop.add_signal_handler(signal.SIGTERM, stopped.set)
    try:
        done, _ = await asyncio.wait((service, deadline, stop), return_when=asyncio.FIRST_COMPLETED)
        if service in done:
            await service
    finally:
        snapshot._active.clear()
        for task in (service, deadline, stop):
            if not task.done():
                task.cancel()
        # SDK stdio owns backend process trees; wait for its finally before
        # deleting the snapshot. No daemon, no global process-name killing.
        await asyncio.gather(service, deadline, stop, return_exceptions=True)
        if os.name == 'posix':
            loop.remove_signal_handler(signal.SIGTERM)
            signal.signal(signal.SIGTERM, previous)


def main(argv=None):
    import argparse
    from contextlib import ExitStack
    import os
    import sys
    from snapshot import capture
    parser = argparse.ArgumentParser(description='Unity失效时独立只读诊断；明确文件、本地预览确认、按需stdio。')
    parser.add_argument('mode', choices=('preview', 'serve'))
    parser.add_argument('--root', required=True, help='本地绝对目录；Windows仅本地盘符路径')
    parser.add_argument('--file', action='append', required=True, dest='files', help='精确相对文件，子目录用/；可重复此参数')
    parser.add_argument('--task', required=True)
    args = parser.parse_args(argv)
    try:
        with ExitStack() as stack:
            if os.name == 'posix':
                import signal
                def interrupted(signum, frame):
                    raise KeyboardInterrupt
                previous = signal.signal(signal.SIGTERM, interrupted)
                stack.callback(signal.signal, signal.SIGTERM, previous)
            try:
                reader = stack.enter_context(open('CONIN$' if os.name == 'nt' else '/dev/tty', 'r', encoding='utf-8'))
                writer = stack.enter_context(open('CONOUT$' if os.name == 'nt' else '/dev/tty', 'w', encoding='utf-8'))
            except OSError:
                print('local_console_unavailable: 必须由本地操作者在终端确认，stdin不能批准。', file=sys.stderr)
                return 2
            snap = stack.enter_context(capture(args.root, args.files, task_id=args.task))
            digest = preview_confirm(snap, reader, writer)
            if digest is None:
                return 3
            if args.mode == 'serve':
                asyncio.run(serve_snapshot(snap, digest))
            return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        # Do not emit arbitrary exception strings containing paths or source data.
        print('diagnostics_failed: ' + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
