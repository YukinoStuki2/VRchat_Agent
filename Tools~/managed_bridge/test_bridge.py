"""Real loopback HTTP tests; every listener has context-managed teardown."""
import contextlib
import http.client
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
VERSION = "2025-03-26"
READERS = (
    "vrchat_ro_project_inventory", "vrchat_ro_avatar_inspect", "vrchat_ro_renderer_mesh",
    "vrchat_ro_blendshapes", "vrchat_ro_materials", "vrchat_ro_animator",
    "vrchat_ro_expressions", "vrchat_ro_dynamics", "vrchat_ro_modular_stack",
    "vrchat_ro_performance", "vrchat_ro_outfit_compatibility", "vrchat_ro_validate",
)
MANAGED = ("vrchat_me_status", "vrchat_me_plan", "vrchat_me_preview", "vrchat_me_apply", "vrchat_me_rollback")
SAFE = READERS + MANAGED
URIS = ("mcpforunity://project/info", "mcpforunity://editor/state", "mcpforunity://instances")


def rpc(method, params=None, request_id=1):
    obj = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        obj["id"] = request_id
    if params is not None:
        obj["params"] = params
    return obj


class Upstream(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self):
        super().__init__(("127.0.0.1", 0), UpstreamHandler)
        self.calls = []
        self.reply = self.default_reply
        self.counter = 0
        self.active_sessions = set()
        self.peak_active = 0
        self.deletes = []
        self.delete_reply = self.default_delete

    def default_delete(self, headers):
        token = headers.get("mcp-session-id")
        if token not in self.active_sessions:
            return 404, {}, b""
        self.active_sessions.remove(token)
        return 204, {}, b""

    def default_reply(self, msg, headers):
        self.counter += 1
        if "id" not in msg:
            return 202, {}, b""
        method = msg["method"]
        extra = {}
        if method == "initialize":
            extra["Mcp-Session-Id"] = f"upstream-{self.counter}"
            result = {"protocolVersion": VERSION, "capabilities": {"tools": {}, "resources": {}},
                      "serverInfo": {"name": "test-upstream", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": name, "description": "upstream documentation",
                                 "inputSchema": {"type": "object", "properties": {}}}
                                for name in SAFE + ("execute_custom_tool", "manage_tools", "unlock")]}
        elif method == "resources/list":
            result = {"resources": [{"uri": uri, "name": uri} for uri in URIS + ("mcpforunity://custom-tools",)]}
        elif method == "resources/read":
            result = {"contents": [{"uri": msg["params"]["uri"], "mimeType": "application/json", "text": "{}"}]}
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": '{"success":true}'}], "isError": False}
        else:
            result = {}
        return 200, {"Content-Type": "application/json", **extra}, json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode()


class UpstreamHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        msg = json.loads(body)
        headers = {k.lower(): v for k, v in self.headers.items()}
        self.server.calls.append((self.path, msg, headers))
        if msg["method"] != "initialize" and headers.get("mcp-session-id") not in self.server.active_sessions:
            status, response_headers, content = 404, {}, b""
        else:
            status, response_headers, content = self.server.reply(msg, headers)
        if msg["method"] == "initialize" and "Mcp-Session-Id" in response_headers:
            self.server.active_sessions.add(response_headers["Mcp-Session-Id"])
            self.server.peak_active = max(self.server.peak_active, len(self.server.active_sessions))
        self.respond(status, response_headers, content)

    def do_DELETE(self):
        headers = {k.lower(): v for k, v in self.headers.items()}
        self.server.deletes.append((self.path, headers))
        self.respond(*self.server.delete_reply(headers))

    def respond(self, status, response_headers, content):
        self.send_response(status)
        for key, value in response_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive(), "test server leaked"


def wait_until(predicate, timeout=2):
    import time
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true before deadline")
        time.sleep(0.01)


class BridgeTests(unittest.TestCase):
    @contextlib.contextmanager
    def pair(self, **limits):
        self.assertIsNotNone(importlib.util.find_spec("bridge"), "runnable bridge module is missing")
        import bridge
        import inspect
        for name in limits:
            self.assertIn(name, inspect.signature(bridge._Server).parameters, f"missing {name} limit")
        with running(Upstream()) as upstream:
            url = f"http://127.0.0.1:{upstream.server_port}/mcp"
            # Private constructor is the only ephemeral-port test seam. CLI stays fixed.
            with running(bridge._Server(("127.0.0.1", 0), url, **limits)) as front:
                yield front, upstream

    def request(self, front, obj=None, *, token=None, path="/mcp", method="POST", headers=None, raw=None):
        hdr = {"Content-Type": "application/json", "MCP-Protocol-Version": VERSION}
        if token:
            hdr["Mcp-Session-Id"] = token
        hdr.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", front.server_port, timeout=4)
        try:
            body = raw if raw is not None else json.dumps(obj).encode()
            conn.request(method, path, body=body, headers=hdr)
            response = conn.getresponse()
            content = response.read()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, json.loads(content) if content else None
        finally:
            conn.close()

    def initialize(self, front):
        request = rpc("initialize", {"protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        status, headers, data = self.request(front, request)
        self.assertEqual(status, 200, data)
        return headers["mcp-session-id"]

    def ready(self, front):
        token = self.initialize(front)
        self.assertEqual(self.request(front, rpc("notifications/initialized", request_id=None), token=token)[0], 202)
        return token

    def test_initialize_maps_session_and_roundtrips_ping(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            status, _, data = self.request(front, rpc("ping", request_id="p"), token=token)
            self.assertEqual((status, data), (200, {"jsonrpc": "2.0", "id": "p", "result": {}}))
            upstream_token = upstream.calls[-1][2]["mcp-session-id"]
            self.assertNotEqual(token, upstream_token)
            self.assertGreaterEqual(len(token), 32)
            self.assertEqual(upstream.calls[-1][2]["mcp-protocol-version"], VERSION)

    def test_new_offer_negotiates_only_audited_versions_truthfully(self):
        for chosen in (VERSION, "2025-06-18", "2025-11-25"):
            with self.subTest(chosen=chosen), self.pair() as (front, upstream):
                base = upstream.default_reply
                def negotiate(msg, headers):
                    status, hdr, raw = base(msg, headers)
                    if msg["method"] == "initialize":
                        obj = json.loads(raw)
                        obj["result"]["protocolVersion"] = chosen
                        raw = json.dumps(obj).encode()
                    return status, hdr, raw
                upstream.reply = negotiate
                initial = rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {"sampling": {}},
                                             "clientInfo": {"name": "new-client", "version": "1"}})
                status, headers, obj = self.request(front, initial, headers={"MCP-Protocol-Version": "2025-11-25"})
                self.assertEqual(status, 502 if chosen == "2025-11-25" else 200)
                self.assertEqual(upstream.calls[0][1]["params"]["protocolVersion"], "2025-06-18")
                self.assertEqual(upstream.calls[0][1]["params"]["capabilities"], {})
                if status != 200:
                    continue
                self.assertEqual(obj["result"]["protocolVersion"], chosen)
                token = headers["mcp-session-id"]
                self.assertEqual(self.request(front, rpc("ping"), token=token,
                                             headers={"MCP-Protocol-Version": chosen})[0], 200)
                self.assertEqual(upstream.calls[-1][2]["mcp-protocol-version"], chosen)
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("ping"), token=token,
                                             headers={"MCP-Protocol-Version": "2025-11-25"})[0], 400)
                self.assertEqual(len(upstream.calls), before)

    def test_tools_list_exposes_only_exact_audited_names(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            status, _, data = self.request(front, rpc("tools/list"), token=token)
            self.assertEqual(status, 200)
            self.assertEqual({x["name"] for x in data["result"]["tools"]}, set(SAFE))
            for row in data["result"]["tools"]:
                read_only = row["name"] in READERS + ("vrchat_me_status", "vrchat_me_plan")
                self.assertIs(row["annotations"]["readOnlyHint"], read_only)
                self.assertEqual(row["inputSchema"]["type"], "object")
            for name in SAFE:
                self.assertEqual(self.request(front, rpc("tools/call", {"name": name, "arguments": {}}), token=token)[0], 200)
                self.assertEqual(upstream.calls[-1][1]["params"]["name"], name)

    def test_all_client_bypass_paths_are_denied_before_upstream(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            bad_names = ["execute_custom_tool", "manage_tools", "read_console", "manage_gameobject", "batch_execute",
                         "execute_menu_item", "vrchat_me_unlock", "vrchat_ro_future", "VRCHAT_ME_APPLY", "vrchat_me_apply ",
                         "mcp__unity__vrchat_me_apply", "vrchat_me_apply/../manage_tools", "vrchat_me_аpply"]
            requests = [rpc("tools/call", {"name": n, "arguments": {}}) for n in bad_names]
            requests += [rpc(m) for m in ("prompts/list", "prompts/get", "sampling/createMessage", "roots/list", "resources/templates/list",
                         "resources/subscribe", "logging/setLevel", "completion/complete", "tools/manage", "unknown")]
            requests += [[rpc("ping")], [], {}, {"jsonrpc": "2.0", "id": 1, "result": {}},
                         rpc("ping", {"command": "writer"}), rpc("tools/list", {"cursor": "http://evil"}),
                         rpc("tools/call", {"name": SAFE[0], "arguments": {}, "command": "writer"}),
                         rpc("tools/call", {"name": SAFE[0], "arguments": []}),
                         rpc("tools/call", {"name": SAFE[0], "arguments": {}, "_meta": {"unity_instance": "9999"}}),
                         {**rpc("ping"), "url": "http://127.0.0.1:18081/api/command"},
                         rpc("tools/call", {"name": SAFE[0]}, request_id=None),
                         rpc("ping", request_id=True), rpc("notifications/initialized", request_id=9)]
            for value in requests:
                with self.subTest(value=value):
                    before = len(upstream.calls)
                    status, _, _ = self.request(front, value, token=token)
                    self.assertGreaterEqual(status, 400)
                    self.assertEqual(len(upstream.calls), before)
            for path in ("/api/command", "/register-tools", "/hub", "/ws", "/mcp/", "/mcp?url=http://evil", "/%6dcp", "http://evil/mcp"):
                with self.subTest(path=path):
                    before = len(upstream.calls)
                    self.assertGreaterEqual(self.request(front, rpc("ping"), token=token, path=path)[0], 400)
                    self.assertEqual(len(upstream.calls), before)
            for method in ("GET", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "HEAD"):
                with self.subTest(method=method):
                    before = len(upstream.calls)
                    self.assertGreaterEqual(self.request(front, rpc("ping"), token=token, method=method)[0], 400)
                    self.assertEqual(len(upstream.calls), before)
            for raw in (b'{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/list"}', b'{"a":NaN}', b'bad json'):
                before = len(upstream.calls)
                self.assertGreaterEqual(self.request(front, token=token, raw=raw)[0], 400)
                self.assertEqual(len(upstream.calls), before)
            for headers in ({"Origin": "http://evil"}, {"Host": "evil.example"}, {"Transfer-Encoding": "chunked"}, {"Content-Type": "text/plain"}):
                before = len(upstream.calls)
                self.assertGreaterEqual(self.request(front, rpc("ping"), token=token, headers=headers)[0], 400)
                self.assertEqual(len(upstream.calls), before)

    def test_session_boundaries_negotiation_and_expiry(self):
        import time
        with self.pair(session_ttl=0.25, max_sessions=2) as (front, upstream):
            token_a = self.ready(front)
            token_b = self.ready(front)
            self.assertNotEqual(token_a, token_b)
            for token in (None, "unknown", "upstream-1"):
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 404)
                self.assertEqual(len(upstream.calls), before)
            before = len(upstream.calls)
            self.assertEqual(self.request(front, rpc("ping"), token=token_a, headers={"MCP-Protocol-Version": "evil"})[0], 400)
            self.assertEqual(len(upstream.calls), before)
            seen = []
            for token in (token_a, token_b, token_a):
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 200)
                seen.append(upstream.calls[-1][2]["mcp-session-id"])
            self.assertEqual(seen[0], seen[2])
            self.assertNotEqual(seen[0], seen[1])
            initial = rpc("initialize", {"protocolVersion": VERSION, "capabilities": {"sampling": {}, "roots": {}}, "clientInfo": {"name": "same", "version": "1"}})
            before = len(upstream.calls)
            self.assertEqual(self.request(front, initial)[0], 503)
            self.assertEqual(self.request(front, initial, token=token_a)[0], 400)
            self.assertEqual(len(upstream.calls), before)
            time.sleep(0.35)
            self.assertEqual(self.request(front, rpc("ping"), token=token_a)[0], 404)
            status, _, data = self.request(front, initial)
            self.assertEqual(status, 200)
            self.assertEqual(upstream.calls[-1][1]["params"]["capabilities"], {})
            self.assertEqual(data["result"]["capabilities"], {"tools": {}, "resources": {"subscribe": False, "listChanged": False}})
        with self.pair() as (front, upstream):
            token = self.initialize(front)
            before = len(upstream.calls)
            self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 409)
            self.assertEqual(len(upstream.calls), before)
            self.assertEqual(self.request(front, rpc("notifications/initialized", request_id=None), token=token)[0], 202)
            self.assertEqual(self.request(front, rpc("notifications/cancelled", {"requestId": 123}, request_id=None), token=token)[0], 202)

    def test_ttl_stress_and_shutdown_terminate_exact_owned_sessions(self):
        import bridge
        import socket
        baseline = set(threading.enumerate())
        with running(Upstream()) as upstream:
            with running(bridge._Server(("127.0.0.1", 0), f"http://127.0.0.1:{upstream.server_port}/mcp",
                                       session_ttl=0.06, max_sessions=1)) as front:
                for _ in range(6):
                    token = self.ready(front)
                    owned = upstream.calls[-1][2]["mcp-session-id"]
                    self.assertEqual(self.request(front, method="DELETE", token="arbitrary-upstream",
                                                 path="/mcp?url=http://evil")[0], 501)
                    wait_until(lambda: not upstream.active_sessions and not front.cleanup_debt)
                    self.assertEqual(upstream.deletes[-1][0], "/mcp")
                    self.assertEqual(upstream.deletes[-1][1]["mcp-session-id"], owned)
                    self.assertNotEqual(owned, token)
                    self.assertEqual(upstream.deletes[-1][1]["mcp-protocol-version"], VERSION)
                self.assertEqual(upstream.peak_active, 1)
                self.assertEqual(len(upstream.deletes), 6)
                front.session_ttl = 300
                self.ready(front)
                front_port = front.server_port
            self.assertEqual(upstream.active_sessions, set(), "shutdown must confirm termination")
            self.assertEqual(len(upstream.deletes), 7)
            self.assertEqual(len({h["mcp-session-id"] for _, h in upstream.deletes}), 7)
            self.assertEqual(front.sessions, {})
            self.assertEqual(front.cleanup_debt, {})
        self.assertFalse(set(threading.enumerate()) - baseline, "cleanup threads leaked")
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", front_port)), 0)

    def test_cleanup_failure_debt_stays_capped_without_delete_retries(self):
        import time
        for mode in ("unsupported", "error", "false-success", "redirect", "oversize", "timeout"):
            with self.subTest(mode=mode), self.assertLogs("bridge", level="WARNING") as logs:
                with self.pair(session_ttl=0.06, max_sessions=1, cleanup_timeout=0.05) as (front, upstream):
                    def fail_delete(headers):
                        if mode == "timeout":
                            time.sleep(0.15)
                            return 500, {}, b""
                        return {"unsupported": (405, {}, b""), "error": (500, {}, b""),
                                "false-success": (204, {}, b""),
                                "redirect": (307, {"Location": "http://evil/mcp"}, b""),
                                "oversize": (200, {}, b"x" * 4097)}[mode]
                    upstream.delete_reply = fail_delete
                    token = self.ready(front)
                    wait_until(lambda: bool(upstream.deletes))
                    initial = rpc("initialize", {"protocolVersion": VERSION, "capabilities": {}, "clientInfo": {}})
                    for _ in range(8):
                        status, _, obj = self.request(front, initial)
                        self.assertEqual(status, 503, obj)
                        self.assertIn("cleanup", obj["error"]["message"])
                        time.sleep(0.02)
                    self.assertEqual(upstream.peak_active, 1)
                    self.assertEqual(len(upstream.active_sessions), 1)
                    self.assertEqual(len(front.cleanup_debt), 1)
                    self.assertEqual(front.pending_initializations, 0)
                    self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 404)
                self.assertEqual(len(upstream.deletes), 1, "shutdown must not repeat an uncertain DELETE")
                self.assertFalse(front.cleanup_thread.is_alive())
                self.assertEqual(len(logs.output), 1)
                self.assertNotIn(token, logs.output[0])

    def test_failed_initialization_cleans_allocated_exact_session(self):
        for mode in ("bad-json", "bad-version"):
            with self.subTest(mode=mode), self.pair(max_sessions=1) as (front, upstream):
                base = upstream.default_reply
                def broken(msg, headers):
                    status, hdr, raw = base(msg, headers)
                    if msg["method"] == "initialize":
                        if mode == "bad-json":
                            raw = b"not-json"
                        else:
                            obj = json.loads(raw)
                            obj["result"]["protocolVersion"] = "2025-11-25"
                            raw = json.dumps(obj).encode()
                    return status, hdr, raw
                upstream.reply = broken
                initial = rpc("initialize", {"protocolVersion": VERSION, "capabilities": {}, "clientInfo": {}})
                self.assertEqual(self.request(front, initial)[0], 502)
                wait_until(lambda: not upstream.active_sessions)
                self.assertEqual(len(upstream.deletes), 1)
                wait_until(lambda: not front.cleanup_debt)
                upstream.reply = base
                self.ready(front)

    def test_unknown_allocation_reserves_capacity_without_guessing_delete(self):
        with self.assertLogs("bridge", level="WARNING") as logs:
            with self.pair(max_sessions=1) as (front, upstream):
                def lost_token(msg, headers):
                    upstream.active_sessions.add("unrecoverable-fixture-session")
                    return 200, {"Content-Type": "application/json"}, b"not-json"
                upstream.reply = lost_token
                initial = rpc("initialize", {"protocolVersion": VERSION, "capabilities": {}, "clientInfo": {}})
                self.assertEqual(self.request(front, initial)[0], 502)
                for _ in range(4):
                    self.assertEqual(self.request(front, initial)[0], 503)
                self.assertEqual(len(upstream.calls), 1)
                self.assertEqual(upstream.deletes, [])
                self.assertEqual(len(front.cleanup_debt), 1)
            self.assertEqual(len(logs.output), 1)

    def test_cleanup_does_not_expire_initializing_or_busy_sessions(self):
        import concurrent.futures
        import time
        with self.pair(session_ttl=0.08) as (front, upstream):
            base = upstream.default_reply
            entered = threading.Event()
            def slow(msg, headers):
                if msg["method"] == "initialize" or msg.get("id") == "busy":
                    entered.set()
                    time.sleep(0.18)
                return base(msg, headers)
            upstream.reply = slow
            token = self.ready(front)
            entered.clear()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.request, front, rpc("ping", request_id="busy"), token=token)
                self.assertTrue(entered.wait(1))
                time.sleep(0.12)
                self.assertEqual(upstream.deletes, [])
                self.assertEqual(future.result()[0], 200)
            self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 200)
            wait_until(lambda: not upstream.active_sessions and not front.cleanup_debt)

    def test_bind_failure_leaves_no_cleanup_worker(self):
        import bridge
        baseline = set(threading.enumerate())
        with running(Upstream()) as occupied:
            with self.assertRaises(OSError):
                bridge._Server(("127.0.0.1", occupied.server_port))
        self.assertFalse(set(threading.enumerate()) - baseline)

    def test_tool_schemas_and_arguments_fail_closed(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            before = len(upstream.calls)
            self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0], "arguments": {}}), token=token)[0], 409)
            self.assertEqual(len(upstream.calls), before)
            base = upstream.default_reply
            def schema_reply(msg, headers):
                status, hdr, raw = base(msg, headers)
                if msg["method"] == "tools/list":
                    obj = json.loads(raw)
                    obj["result"]["tools"][0]["inputSchema"] = {"type": "object", "properties": {
                        "max_items": {"type": "integer", "minimum": 1, "maximum": 500},
                        "target": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}},
                        "required": ["max_items"], "additionalProperties": True}
                    obj["result"]["tools"][0]["description"] = "execute_custom_tool unlock manage_tools"
                    return status, hdr, json.dumps(obj).encode()
                return status, hdr, raw
            upstream.reply = schema_reply
            status, _, obj = self.request(front, rpc("tools/list"), token=token)
            self.assertEqual(status, 200)
            self.assertNotIn("unlock", json.dumps(obj))
            for args in ({}, {"max_items": True}, {"max_items": 0}, {"max_items": 501}, {"max_items": "1"},
                         {"max_items": 1, "target": []}, {"max_items": 1, "url": "http://evil"},
                         {"max_items": 1, "unity_instance": "9999"}, {"max_items": 1, "unityInstance": "Other@deadbeef"}):
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0], "arguments": args}), token=token)[0], 400)
                self.assertEqual(len(upstream.calls), before)
            self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0], "arguments": {"max_items": 2, "target": None}}), token=token)[0], 200)
            def malformed(schema=None, duplicate=False, missing=False, cursor=False):
                def reply(msg, headers):
                    status, hdr, raw = base(msg, headers)
                    if msg["method"] != "tools/list":
                        return status, hdr, raw
                    obj = json.loads(raw)
                    if schema is not None:
                        obj["result"]["tools"][0]["inputSchema"] = schema
                    if duplicate:
                        obj["result"]["tools"].append(obj["result"]["tools"][0])
                    if missing:
                        obj["result"]["tools"].pop(0)
                    if cursor:
                        obj["result"]["nextCursor"] = "http://evil/page"
                    return status, hdr, json.dumps(obj).encode()
                return reply
            for bad in (malformed([]), malformed({"type": "array"}), malformed({"type": "object", "$ref": "http://evil"}),
                        malformed({"type": "object", "properties": {"unityInstance": {"type": "string"}}}),
                        malformed(duplicate=True), malformed(missing=True), malformed(cursor=True)):
                upstream.reply = bad
                self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 502)
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0], "arguments": {}}), token=token)[0], 409)
                self.assertEqual(len(upstream.calls), before)

    def test_nullable_array_composition_retains_item_restrictions(self):
        detail_schema = {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]}
        item_schema = {"type": "object", "properties": {
            "target": {"type": "string"}, "details": detail_schema}, "required": ["target"]}
        array_schema = {"type": "array", "items": item_schema}
        nullable_schema = {"anyOf": [array_schema, {"type": "null"}]}
        intersected_schema = {"type": "array", "anyOf": nullable_schema["anyOf"],
                              "items": {"type": "object", "properties": {
                                  "target": {"type": "string", "enum": ["Avatar"]},
                                  "details": detail_schema}}}
        for mode, schema in (("nullable", nullable_schema), ("direct", array_schema),
                             ("intersected", intersected_schema)):
            with self.subTest(mode=mode), self.pair() as (front, upstream):
                token = self.ready(front)
                base = upstream.default_reply
                def reply(msg, headers):
                    status, hdr, raw = base(msg, headers)
                    if msg["method"] == "tools/list":
                        obj = json.loads(raw)
                        obj["result"]["tools"][0]["inputSchema"] = {
                            "type": "object", "properties": {"options": schema},
                            "required": ["options"]}
                        raw = json.dumps(obj).encode()
                    return status, hdr, raw
                upstream.reply = reply
                self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 200)
                accepted = [[{"target": "Avatar"}], [],
                            [{"target": "Avatar", "details": {"target": "Child"}}]]
                if mode == "nullable":
                    accepted.append(None)
                if mode != "intersected":
                    accepted.append([{"target": "Other"}])
                for value in accepted:
                    with self.subTest(accepted=value):
                        params = {"name": SAFE[0], "arguments": {"options": value}}
                        before = len(upstream.calls)
                        status, _, obj = self.request(front, rpc("tools/call", params), token=token)
                        self.assertEqual(status, 200, obj)
                        self.assertEqual(len(upstream.calls), before + 1)
                        self.assertEqual(upstream.calls[-1][1]["params"], params)
                denied = [{"target": "Avatar"}, "Avatar", 1, True, ["Avatar"], [None], [{}],
                          [{"target": 1}], [{"target": True}],
                          [{"target": "Avatar", "details": {"target": 1}}]]
                for key in ("url", "unity_instance", "unityInstance", "unexpected"):
                    denied.append([{"target": "Avatar", key: "blocked"}])
                    denied.append([{"target": "Avatar", "details": {
                        "target": "Child", key: "blocked"}}])
                if mode != "nullable":
                    denied.append(None)
                if mode == "intersected":
                    denied.append([{"target": "Other"}])
                for value in denied:
                    with self.subTest(denied=value):
                        before = len(upstream.calls)
                        status, _, obj = self.request(front, rpc("tools/call", {
                            "name": SAFE[0], "arguments": {"options": value}}), token=token)
                        self.assertEqual(status, 400, obj)
                        self.assertEqual(len(upstream.calls), before)

    def test_nullable_object_composition_retains_branch_key_restrictions(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            base = upstream.default_reply
            def reply(msg, headers):
                status, hdr, raw = base(msg, headers)
                if msg["method"] == "tools/list":
                    obj = json.loads(raw)
                    obj["result"]["tools"][0]["inputSchema"] = {"type": "object", "properties": {
                        "options": {"anyOf": [{"type": "object", "properties": {"target": {"type": "string"}},
                                               "required": ["target"]}, {"type": "null"}]}}}
                    raw = json.dumps(obj).encode()
                return status, hdr, raw
            upstream.reply = reply
            self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 200)
            for value in ({"target": "Avatar"}, None):
                status, _, obj = self.request(front, rpc("tools/call", {"name": SAFE[0], "arguments": {"options": value}}), token=token)
                self.assertEqual(status, 200, obj)
                self.assertEqual(upstream.calls[-1][1]["params"]["arguments"], {"options": value})
            for value in ({}, {"target": 1}, {"target": "Avatar", "extra": True}, {"url": "http://evil"}, []):
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0], "arguments": {"options": value}}), token=token)[0], 400)
                self.assertEqual(len(upstream.calls), before)

    def test_resources_are_exact_finite_and_cannot_dispatch_commands(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            status, _, obj = self.request(front, rpc("resources/list"), token=token)
            self.assertEqual(status, 200)
            self.assertEqual({x["uri"] for x in obj["result"]["resources"]}, set(URIS))
            for uri in URIS:
                status, _, obj = self.request(front, rpc("resources/read", {"uri": uri}), token=token)
                self.assertEqual(status, 200)
                self.assertEqual(obj["result"]["contents"][0]["uri"], uri)
            for uri in ("file:///etc/passwd", "http://127.0.0.1:18081/api/command", "mcpforunity://custom-tools",
                        "mcpforunity://editor/state?command=clear", "mcpforunity://project/info/", "mcpforunity://execute/clear", "MCPFORUNITY://instances"):
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("resources/read", {"uri": uri}), token=token)[0], 400)
                self.assertEqual(len(upstream.calls), before)
            base = upstream.default_reply
            def wrong_resource(msg, headers):
                status, hdr, raw = base(msg, headers)
                obj = json.loads(raw)
                obj["result"] = {"contents": [{"uri": "mcpforunity://custom-tools", "text": "secret"}]}
                return status, hdr, json.dumps(obj).encode()
            upstream.reply = wrong_resource
            status, _, obj = self.request(front, rpc("resources/read", {"uri": URIS[0]}), token=token)
            self.assertEqual(status, 502)
            self.assertNotIn("secret", json.dumps(obj))

    def test_sse_is_parsed_to_json_never_a_server_call(self):
        with self.pair() as (front, upstream):
            base = upstream.default_reply
            def sse(msg, headers):
                status, hdr, raw = base(msg, headers)
                if status == 202:
                    return status, hdr, raw
                hdr["Content-Type"] = "text/event-stream; charset=utf-8"
                notice = b'data: {"jsonrpc":"2.0","method":"notifications/message","params":{"data":"ignored"}}\r\n\r\n'
                return status, hdr, b": heartbeat\r\n\r\n" + notice + b"event: message\r\nid: 1\r\ndata: " + raw + b"\r\n\r\n"
            upstream.reply = sse
            token = self.ready(front)
            status, hdr, obj = self.request(front, rpc("tools/list", request_id="list"), token=token)
            self.assertEqual(status, 200)
            self.assertEqual(hdr["content-type"], "application/json")
            self.assertEqual(obj["id"], "list")
            self.assertEqual({x["name"] for x in obj["result"]["tools"]}, set(SAFE))
            invalid = [b'data: {"jsonrpc":"2.0","id":1,"method":"sampling/createMessage","params":{}}\n\n',
                       b'data: [{"jsonrpc":"2.0","id":1,"result":{}}]\n\n',
                       b'data: {"jsonrpc":"2.0","id":2,"result":{}}\n\n',
                       b'event: endpoint\ndata: http://evil/api/command\n\n', b'data: not json\n\n',
                       b'data: {"jsonrpc":"2.0","id":1,"result":{},"method":"ping"}\n\n']
            for raw in invalid:
                upstream.reply = lambda msg, hdr, raw=raw: (200, {"Content-Type": "text/event-stream"}, raw)
                status, _, obj = self.request(front, rpc("ping"), token=token)
                self.assertEqual(status, 502)
                self.assertNotIn("method", obj)
            for obj in ({"jsonrpc": "2.0", "id": True, "result": {}}, {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}},
                        {"jsonrpc": "2.0", "id": 1, "method": "roots/list"}, [{"jsonrpc": "2.0", "id": 1, "result": {}}]):
                upstream.reply = lambda msg, hdr, obj=obj: (200, {"Content-Type": "application/json"}, json.dumps(obj).encode())
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 502)
            upstream.reply = lambda msg, hdr: (200, {"Content-Type": "application/json"}, b'{"jsonrpc":"2.0","id":1,"error":{"code":-32603,"message":"upstream-secret","data":"secret"}}')
            status, _, obj = self.request(front, rpc("ping"), token=token)
            self.assertEqual(status, 200)
            self.assertEqual(obj["error"]["code"], -32603)
            self.assertNotIn("secret", json.dumps(obj))

    def test_network_redirect_proxy_and_byte_time_limits(self):
        import os
        import time
        from unittest.mock import patch
        with self.pair(max_request_bytes=512, max_upstream_bytes=10000, max_result_bytes=12000, call_timeout=0.12) as (front, upstream):
            token = self.ready(front)
            before = len(upstream.calls)
            self.assertEqual(self.request(front, token=token, raw=b" " * 513)[0], 413)
            self.assertEqual(len(upstream.calls), before)
            with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""}):
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 200)
            for code in (301, 302, 303, 307, 308):
                before = len(upstream.calls)
                upstream.reply = lambda msg, hdr, code=code: (code, {"Location": f"http://127.0.0.1:{upstream.server_port}/api/command"}, b"")
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 502)
                self.assertEqual(len(upstream.calls), before + 1)
            for content_type, raw in (("application/json", b" " * 10001), ("text/event-stream", b":" + b"x" * 10000 + b"\n\n"),
                                      ("text/html", b"secret")):
                upstream.reply = lambda msg, hdr, ct=content_type, raw=raw: (200, {"Content-Type": ct}, raw)
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 502)
            def slow(msg, hdr):
                time.sleep(0.3)
                return upstream.default_reply(msg, hdr)
            upstream.reply = slow
            start = time.monotonic()
            status, _, obj = self.request(front, rpc("ping"), token=token)
            self.assertEqual(status, 504)
            self.assertLess(time.monotonic() - start, 0.27)
            self.assertNotIn("Traceback", json.dumps(obj))
        with self.pair(max_result_bytes=1500) as (front, upstream):
            token = self.ready(front)
            self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 502)

    def test_every_tool_result_rejects_malformed_or_nontext_content(self):
        bad_results = [
            None, [], "not-an-object", {}, {"content": "not-an-array", "isError": "not-a-boolean"},
            {"content": [], "isError": 1}, {"content": [], "structuredContent": []},
            {"content": [None]}, {"content": [{"type": "text", "text": 42}]},
            {"content": [{"type": "text", "text": "secret", "method": "sampling/createMessage"}]},
            {"content": [], "task": {"taskId": "secret"}},
            {"content": [{"type": "image", "mimeType": "image/png", "data": "secret"}]},
            {"content": [{"type": "audio", "mimeType": "audio/wav", "data": "secret"}]},
            {"content": [{"type": "resource", "resource": {"uri": "file:///secret", "text": "secret"}}]},
            {"content": [{"type": "resource_link", "uri": "http://evil", "name": "secret"}]},
        ]
        with self.pair() as (front, upstream):
            token = self.ready(front)
            self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 200)
            for name in SAFE:
                for result in bad_results:
                    with self.subTest(name=name, result=result):
                        upstream.reply = lambda msg, hdr, result=result: (200, {"Content-Type": "application/json"},
                            json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode())
                        before = len(upstream.calls)
                        status, _, obj = self.request(front, rpc("tools/call", {"name": name}), token=token)
                        self.assertEqual(status, 502)
                        self.assertEqual(len(upstream.calls), before + 1, "never retry a mutation")
                        self.assertIn("mutation may have executed", obj["error"]["message"])
                        self.assertNotIn("secret", json.dumps(obj))
            for result in ({"content": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}],
                            "structuredContent": {"success": True}, "isError": False},
                           {"content": [{"type": "text", "text": "tool failed"}], "isError": True}):
                upstream.reply = lambda msg, hdr, result=result: (200, {"Content-Type": "application/json"},
                    json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode())
                status, _, obj = self.request(front, rpc("tools/call", {"name": READERS[0]}), token=token)
                self.assertEqual(status, 200)
                self.assertEqual(obj["result"], result)

    def test_preview_images_are_validated_and_removed_from_text(self):
        import base64
        import struct
        import zlib
        def png(width=2, height=2):
            def chunk(name, data):
                return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * (width * 4)) * height)) + chunk(b"IEND", b""))
        encoded = base64.b64encode(png()).decode()
        image = {"label": "before", "mime_type": "image/png", "data_base64": encoded}
        with self.pair() as (front, upstream):
            token = self.ready(front)
            self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 200)
            def result_reply(images):
                def reply(msg, hdr):
                    payload = {"success": True, "message": "isolated preview only", "data": {"renderer_id": 12, "preview_images": images}}
                    result = {"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": payload, "isError": False}
                    return 200, {"Content-Type": "application/json"}, json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode()
                return reply
            upstream.reply = result_reply([image, {**image, "label": "after"}])
            status, _, obj = self.request(front, rpc("tools/call", {"name": "vrchat_me_preview", "arguments": {}}), token=token)
            self.assertEqual(status, 200)
            blocks = obj["result"]["content"]
            self.assertEqual([x["data"] for x in blocks if x["type"] == "image"], [encoded, encoded])
            self.assertTrue(all(x["mimeType"] == "image/png" for x in blocks if x["type"] == "image"))
            text = json.dumps([x for x in blocks if x["type"] == "text"])
            self.assertNotIn(encoded, text)
            self.assertNotIn(encoded, json.dumps(obj["result"]["structuredContent"]))
            self.assertEqual(obj["result"]["structuredContent"]["data"]["renderer_id"], 12)
            for images in ([image] * 3, [image, image], [{**image, "label": "arbitrary"}], [{**image, "mime_type": "image/jpeg"}],
                           [{**image, "data_base64": "not-base64"}], [{**image, "data_base64": base64.b64encode(b"notPNG").decode()}],
                           [{**image, "data_base64": base64.b64encode(png(513)).decode()}],
                           [{**image, "data_base64": base64.b64encode(png(0)).decode()}],
                           [{**image, "data_base64": base64.b64encode(b"x" * 1048576).decode()}]):
                upstream.reply = result_reply(images)
                status, _, obj = self.request(front, rpc("tools/call", {"name": "vrchat_me_preview", "arguments": {}}), token=token)
                self.assertEqual(status, 502)
                self.assertNotIn("data_base64", json.dumps(obj))
                self.assertLess(len(json.dumps(obj)), 400)
            upstream.reply = result_reply([image])
            status, _, obj = self.request(front, rpc("tools/call", {"name": READERS[0], "arguments": {}}), token=token)
            self.assertEqual(status, 200)
            self.assertFalse(any(x["type"] == "image" for x in obj["result"]["content"]))

    def test_cli_requires_fixed_explicit_endpoint_and_runs(self):
        import socket
        import subprocess
        import sys
        import time
        args = [sys.executable, str(ROOT / "bridge.py")]
        fixed = ["--upstream", "http://127.0.0.1:18081/mcp", "--listen", "127.0.0.1", "--port", "18082"]
        for flags in ([], ["--listen", "0.0.0.0"], [*fixed, "--url", "http://evil"],
                      ["--upstream", "http://localhost:18081/mcp", "--listen", "127.0.0.1", "--port", "18082"],
                      ["--upstream", "http://127.0.0.1:18081/mcp", "--listen", "127.0.0.1", "--port", "18081"]):
            completed = subprocess.run(args + flags, cwd=ROOT, capture_output=True, timeout=3)
            self.assertNotEqual(completed.returncode, 0, flags)
        probe = socket.socket()
        if sys.platform != "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", 18082))
        except OSError:
            self.skipTest("fixed smoke-test port 18082 is occupied; do not touch the existing service")
        finally:
            probe.close()
        process = subprocess.Popen(args + fixed, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 3
            while True:
                self.assertIsNone(process.poll(), "CLI exited before accepting traffic")
                conn = http.client.HTTPConnection("127.0.0.1", 18082, timeout=0.2)
                try:
                    conn.request("POST", "/mcp", body=json.dumps(rpc("ping")), headers={"Content-Type": "application/json", "MCP-Protocol-Version": VERSION})
                    response = conn.getresponse()
                    self.assertEqual(response.status, 404)
                    self.assertIn("error", json.loads(response.read()))
                    break
                except (ConnectionRefusedError, TimeoutError):
                    self.assertLess(time.monotonic(), deadline, "CLI did not become ready")
                    time.sleep(0.02)
                finally:
                    conn.close()
        finally:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
            self.assertIsNotNone(process.poll())

    def test_slow_clients_and_worker_saturation_are_bounded(self):
        import socket
        import time
        with self.pair(client_timeout=0.18, max_workers=2) as (front, upstream):
            slow = socket.create_connection(("127.0.0.1", front.server_port), timeout=1)
            try:
                slow.sendall(b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{")
                start = time.monotonic()
                try:
                    data = slow.recv(1024)
                except ConnectionResetError:
                    data = b""
                self.assertLess(time.monotonic() - start, 0.5)
                self.assertEqual(len(upstream.calls), 0)
                self.assertNotIn(b"200 OK", data)
            finally:
                slow.close()
            for raw in (b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n\r\n{}",
                        b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}"):
                conn = socket.create_connection(("127.0.0.1", front.server_port), timeout=1)
                try:
                    conn.sendall(raw)
                    self.assertIn(b"400", conn.recv(4096).split(b"\r\n")[0])
                    self.assertEqual(len(upstream.calls), 0)
                finally:
                    conn.close()
            holds = [socket.create_connection(("127.0.0.1", front.server_port), timeout=1) for _ in range(2)]
            try:
                for hold in holds:
                    hold.sendall(b"POST /mcp HTTP/1.1\r\n")
                time.sleep(0.03)
                conn = socket.create_connection(("127.0.0.1", front.server_port), timeout=1)
                try:
                    conn.sendall(b"POST /mcp HTTP/1.1\r\n")
                    self.assertIn(b"503", conn.recv(1024))
                finally:
                    conn.close()
            finally:
                for hold in holds:
                    hold.close()

    def test_sessions_do_not_block_each_other_and_busy_calls_do_not_queue(self):
        import concurrent.futures
        import time
        with self.pair() as (front, upstream):
            token = self.ready(front)
            started = threading.Event()
            base = upstream.default_reply
            def slow_initialize(msg, hdr):
                if msg["method"] == "initialize":
                    started.set()
                    time.sleep(0.35)
                return base(msg, hdr)
            upstream.reply = slow_initialize
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                future = pool.submit(self.initialize, front)
                self.assertTrue(started.wait(1))
                start = time.monotonic()
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 200)
                self.assertLess(time.monotonic() - start, 0.25)
                self.assertNotEqual(future.result(), token)
            started.clear()
            def slow_ping(msg, hdr):
                if msg.get("id") == "slow":
                    started.set()
                    time.sleep(0.25)
                return base(msg, hdr)
            upstream.reply = slow_ping
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                future = pool.submit(self.request, front, rpc("ping", request_id="slow"), token=token)
                self.assertTrue(started.wait(1))
                before = len(upstream.calls)
                self.assertEqual(self.request(front, rpc("ping"), token=token)[0], 503)
                self.assertEqual(len(upstream.calls), before)
                self.assertEqual(future.result()[0], 200)

    def test_poisoned_catalog_never_authorizes_calls(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            base = upstream.default_reply
            def poison(msg, hdr):
                status, headers, raw = base(msg, hdr)
                obj = json.loads(raw)
                obj["result"]["tools"][0]["inputSchema"] = {"type": "object", "properties": {"query": {"type": "string", "enum": ["unlock", "execute_custom_tool"]}}}
                return status, headers, json.dumps(obj).encode()
            upstream.reply = poison
            status, _, obj = self.request(front, rpc("tools/list"), token=token)
            self.assertEqual(status, 502)
            self.assertNotIn("unlock", json.dumps(obj))
            before = len(upstream.calls)
            self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0]}), token=token)[0], 409)
            self.assertEqual(len(upstream.calls), before)
        with self.pair(max_result_bytes=1500) as (front, upstream):
            token = self.ready(front)
            self.assertEqual(self.request(front, rpc("tools/list"), token=token)[0], 502)
            before = len(upstream.calls)
            self.assertEqual(self.request(front, rpc("tools/call", {"name": SAFE[0]}), token=token)[0], 409)
            self.assertEqual(len(upstream.calls), before)

    def test_raw_path_alias_is_rejected_not_normalized(self):
        with self.pair() as (front, upstream):
            token = self.ready(front)
            before = len(upstream.calls)
            status, _, _ = self.request(front, rpc("ping"), token=token, path="//mcp")
            self.assertEqual(status, 400)
            self.assertEqual(len(upstream.calls), before)

    def test_foreign_and_upstream_session_mismatches_are_denied(self):
        with self.pair() as (front_a, upstream_a), self.pair() as (front_b, upstream_b):
            token_a = self.ready(front_a)
            token_b = self.ready(front_b)
            before = len(upstream_a.calls)
            self.assertEqual(self.request(front_a, rpc("ping"), token=token_b)[0], 404)
            self.assertEqual(len(upstream_a.calls), before)
            original = upstream_a.calls[-1][2]["mcp-session-id"]
            base = upstream_a.default_reply
            def collide(msg, hdr):
                status, headers, raw = base(msg, hdr)
                headers["Mcp-Session-Id"] = original
                return status, headers, raw
            upstream_a.reply = collide
            initial = rpc("initialize", {"protocolVersion": VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
            with self.assertLogs("bridge", level="WARNING"):
                self.assertEqual(self.request(front_a, initial)[0], 502)
            self.assertEqual(upstream_a.deletes, [], "duplicate token must never delete the existing session")
            def mismatch(msg, hdr):
                status, headers, raw = base(msg, hdr)
                headers["Mcp-Session-Id"] = "other-upstream-session"
                return status, headers, raw
            upstream_a.reply = mismatch
            self.assertEqual(self.request(front_a, rpc("ping"), token=token_a)[0], 502)
            upstream_a.reply = base
            status, _, _ = self.request(front_a, rpc("ping"), token=token_a, headers={"Authorization": "secret", "X-Unity-Instance": "9999", "X-API-Key": "secret", "X-Upstream": "http://evil"})
            self.assertEqual(status, 200)
            self.assertFalse({"authorization", "x-unity-instance", "x-api-key", "x-upstream"} & set(upstream_a.calls[-1][2]))


if __name__ == "__main__":
    unittest.main()
