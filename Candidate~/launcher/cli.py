"""Explicit CLI; absent local runtime binding fails closed without processes."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys
import threading
from .candidate_launch import ROOT, supervise, validate_config


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Unknown argv can contain secrets. Do not echo it or print tracebacks.
        raise ValueError('CONFIG_INVALID')


def load_binding(config):
    """One fixed bundled integration point; no arbitrary module/config loading.

    Parent integration owns runtime/launcher_binding.py and its credential schema.
    It exports create_launch_binding(config) and close_launch_binding(binding).
    create returns None if credentials are absent. No auth scheme is invented here.
    """
    path = ROOT / 'runtime/launcher_binding.py'
    if not path.exists():
        return None, None
    if path.is_symlink():
        raise ValueError('BINDING_INVALID')
    spec = importlib.util.spec_from_file_location('candidate_runtime_launcher_binding', path)
    if spec is None or spec.loader is None:
        raise ValueError('BINDING_INVALID')
    adapter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = adapter
    spec.loader.exec_module(adapter)
    if not callable(getattr(adapter, 'close_launch_binding', None)):
        raise ValueError('BINDING_INVALID')
    return adapter.create_launch_binding(dict(config)), adapter.close_launch_binding


def main(argv=None, *, binding=None):
    parser = Parser(description='Explicit candidate launcher; no dependency install; authenticated binding required.', allow_abbrev=False)
    parser.add_argument('--project', required=True)
    parser.add_argument('--parent-pid', required=True, type=int)
    parser.add_argument('--local-port', required=True, type=int)
    parser.add_argument('--ssh-host')
    parser.add_argument('--ssh-user')
    parser.add_argument('--ssh-port', type=int)
    parser.add_argument('--remote-port', type=int)
    emit = lambda value: print(json.dumps(value, separators=(',', ':')), flush=True)
    try:
        args = parser.parse_args(argv)
        raw = {'project': args.project, 'parent_pid': args.parent_pid, 'local_port': args.local_port}
        if args.ssh_host is not None:
            raw['ssh'] = {'host': args.ssh_host, 'remote_port': args.remote_port}
            if args.ssh_user is not None:
                raw['ssh']['user'] = args.ssh_user
            if args.ssh_port is not None:
                raw['ssh']['port'] = args.ssh_port
        elif any(x is not None for x in (args.ssh_user, args.ssh_port, args.remote_port)):
            raise ValueError('CONFIG_INVALID')
        config = validate_config(raw)
    except ValueError:
        emit({'phase': 'blocked', 'code': 'CONFIG_INVALID', 'process_cleanup_complete': True})
        return 2
    close_binding = None
    try:
        if binding is None:
            binding, close_binding = load_binding(config)
    except Exception:
        emit({'phase': 'blocked', 'code': 'BINDING_INVALID', 'process_cleanup_complete': True})
        return 2
    stop = threading.Event()
    previous = {}
    if binding is not None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
        def control():
            # One fixed command, bounded line. EOF/invalid command is a safe stop.
            # Daemon is needed for Windows console reads during parent exit.
            sys.stdin.readline(16)
            stop.set()
        threading.Thread(target=control, name='launcher-local-stop', daemon=True).start()
    try:
        result = supervise(config, binding=binding, stop=stop, report=emit)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if close_binding is not None and binding is not None:
        try:
            result['binding_cleanup_complete'] = close_binding(binding) is True
        except Exception:
            result['binding_cleanup_complete'] = False
        if not result['binding_cleanup_complete']:
            result.update(phase='error', code='BINDING_CLEANUP_FAILED')
    emit(result)
    return 2 if result['phase'] == 'blocked' else (1 if result['phase'] == 'error' else 0)
