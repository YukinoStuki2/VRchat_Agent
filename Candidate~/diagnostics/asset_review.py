"""One local selected review file -> private stdout bytes. No approval or MCP.

Only the bounded stable reader is reused, NOT capture/redaction/snapshot serving.
A trusted local caller still owns selection, timeouts/cleanup and record review.
This helper cannot establish a reviewer's identity or current Unity context.
"""
import json
from pathlib import Path
import sys

# Explicit package sibling under -I; never search the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot import read_selected

MAX_RECORD_BYTES = 262144
MAX_REQUEST_BYTES = 8192


def read_local_record(root, name):
    if type(root) is not str or type(name) is not str or not name.endswith('.json'):
        raise ValueError('review_selection_invalid')
    data = read_selected(root, name, limit=MAX_RECORD_BYTES)
    if not data or data.startswith(b'\xef\xbb\xbf'):
        raise ValueError('review_encoding_invalid')
    data.decode('utf-8', errors='strict')
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_selection_key')
        result[key] = value
    return result


def main():
    peer = None
    watcher = None
    done = None
    try:
        if sys.stdin.isatty() or sys.stdout.isatty():
            raise ValueError('private_pipe_required')
        if len(sys.argv) != 1:
            import os
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from launcher.editor_owner import private_pipes
            from launcher.peer_identity import PeerProcess
            if (len(sys.argv) != 3 or sys.argv[1] != '--owned-parent' or
                    not sys.argv[2].isascii() or not sys.argv[2].isdecimal() or
                    int(sys.argv[2]) != os.getppid() or not private_pipes()):
                raise ValueError('exact_local_parent_required')
            peer = PeerProcess(int(sys.argv[2]))
            # The stable reader must run on the main thread (Linux file lease).
            # This fixed no-child helper owns only its memory, pipe and file HANDLEs.
            # Self-exit releases them even if input/read/output is stalled; no PID kill.
            import threading
            import time
            done = threading.Event()
            deadline = time.monotonic() + 10
            def watch():
                while not done.wait(0.05):
                    try:
                        if peer.alive() and time.monotonic() < deadline:
                            continue
                    except Exception:
                        pass
                    os._exit(2)
            watcher = threading.Thread(target=watch, name='local-review-lifetime', daemon=False)
            watcher.start()
        data = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError('selection_limit')
        request = json.loads(data.decode('utf-8', errors='strict'), object_pairs_hook=unique_object)
        if type(request) is not dict or request.keys() != {'root', 'name'}:
            raise ValueError('selection_fields')
        result = read_local_record(request['root'], request['name'])
        if peer is not None and not peer.alive():
            raise ValueError('local_parent_exited')
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # No path, record, parser excerpt or arbitrary exception text in diagnostics.
        sys.stderr.write('local_review_file_refused\n')
        return 2
    finally:
        if done is not None:
            done.set()
        if watcher is not None and watcher.ident is not None:
            watcher.join()
        if peer is not None:
            peer.close()


if __name__ == '__main__':
    raise SystemExit(main())
