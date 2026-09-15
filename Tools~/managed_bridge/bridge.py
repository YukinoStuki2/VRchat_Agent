"""Restrictive MCP HTTP frontend. Production entry point is main()."""
import json
import logging
import base64
import http.client
import re
import secrets
import socket
import struct
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

UPSTREAM = "http://127.0.0.1:18081/mcp"
PROTOCOL_VERSIONS = frozenset({"2025-03-26", "2025-06-18"})
READERS = frozenset({
    "vrchat_ro_project_inventory", "vrchat_ro_avatar_inspect", "vrchat_ro_renderer_mesh",
    "vrchat_ro_blendshapes", "vrchat_ro_materials", "vrchat_ro_animator",
    "vrchat_ro_expressions", "vrchat_ro_dynamics", "vrchat_ro_modular_stack",
    "vrchat_ro_performance", "vrchat_ro_outfit_compatibility", "vrchat_ro_validate",
})
MANAGED = frozenset({"vrchat_me_status", "vrchat_me_plan", "vrchat_me_preview", "vrchat_me_apply", "vrchat_me_rollback"})
TOOLS = READERS | MANAGED
READ_ONLY = READERS | {"vrchat_me_status", "vrchat_me_plan"}
NOTIFICATIONS = {"notifications/initialized", "notifications/cancelled"}
METHODS = {"initialize", "ping", "tools/list", "tools/call", "resources/list", "resources/read"} | NOTIFICATIONS
RESOURCES = frozenset({"mcpforunity://project/info", "mcpforunity://editor/state", "mcpforunity://instances"})


class Rejected(Exception):
    def __init__(self, status=400, code=-32600, message="Request rejected"):
        self.status, self.code, self.message = status, code, message


def require(condition):
    if not condition:
        raise Rejected()


def decode_json(data):
    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj)
            obj[key] = value
        return obj

    def nonfinite(value):
        raise Rejected()

    return json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite)


def valid_id(value):
    return type(value) is int or (type(value) is str and 0 < len(value) <= 128)


def validate_request(msg):
    require(type(msg) is dict and set(msg) <= {"jsonrpc", "id", "method", "params"})
    require(msg.get("jsonrpc") == "2.0" and type(msg.get("method")) is str)
    method = msg["method"]
    require(method in METHODS)
    require(("id" not in msg) if method in NOTIFICATIONS else valid_id(msg.get("id")))
    params = msg.get("params", {})
    require(type(params) is dict)
    if "_meta" in params:
        # The SDK emits an empty metadata object even for legacy handshakes.
        # No progress tokens, routing metadata or new features are accepted.
        require(type(params["_meta"]) is dict and not params["_meta"])
        params = {k: v for k, v in params.items() if k != "_meta"}
        msg["params"] = params
    if method in {"ping", "tools/list", "resources/list", "notifications/initialized"}:
        require(not params)
    elif method == "initialize":
        require(set(params) == {"protocolVersion", "capabilities", "clientInfo"})
        require(type(params["protocolVersion"]) is str and type(params["capabilities"]) is dict)
        require(type(params["clientInfo"]) is dict)
    elif method == "notifications/cancelled":
        require(set(params) <= {"requestId", "reason"} and valid_id(params.get("requestId")))
        require(type(params.get("reason", "")) is str)
    elif method == "resources/read":
        require(set(params) == {"uri"} and type(params["uri"]) is str and params["uri"] in RESOURCES)
    elif method == "tools/call":
        require(set(params) <= {"name", "arguments"})
        require(type(params.get("name")) is str and params["name"] in TOOLS)
        require(type(params.get("arguments", {})) is dict)
    return msg


def safe_argument_name(key):
    # Coplay normalizes camelCase; block instance/transport selectors BEFORE forwarding.
    blocked = {"unityinstance", "url", "uri", "host", "port", "upstream", "headers", "authorization",
               "command", "method", "code", "script", "filepath", "toolname", "tool", "unlock", "grant", "extend"}
    return (type(key) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) is not None
            and key.replace("_", "").lower() not in blocked)


def sanitize_schema(schema, depth=0):
    require(type(schema) is dict and depth <= 12)
    supported = {"type", "properties", "required", "items", "anyOf", "enum", "additionalProperties",
                 "minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength", "title", "description", "default"}
    require(set(schema) <= supported)
    out = {k: v for k, v in schema.items() if k not in {"title", "description", "default", "additionalProperties"}}
    if "anyOf" in out:
        require(type(out["anyOf"]) is list and 1 <= len(out["anyOf"]) <= 8)
        out["anyOf"] = [sanitize_schema(s, depth + 1) for s in out["anyOf"]]
    typ = out.get("type")
    require(typ in {None, "object", "array", "string", "integer", "number", "boolean", "null"})
    if typ == "object":
        props = out.get("properties", {})
        require(type(props) is dict and all(safe_argument_name(k) for k in props))
        out["properties"] = {k: sanitize_schema(v, depth + 1) for k, v in props.items()}
        required = out.get("required", [])
        require(type(required) is list and all(type(k) is str and k in props for k in required))
        require(len(set(required)) == len(required))
        out["additionalProperties"] = False
    else:
        require("properties" not in out and "required" not in out)
    if "items" in out:
        require(typ == "array")
        out["items"] = sanitize_schema(out["items"], depth + 1)
    if "enum" in out:
        require(type(out["enum"]) is list and 0 < len(out["enum"]) <= 128)
        require(all(type(x) in {str, int, float, bool, type(None)} for x in out["enum"]))
    for key in {"minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength"} & set(out):
        require(type(out[key]) in {int, float})
    return out


def validate_arguments(value, schema, depth=0):
    require(depth <= 24)
    if isinstance(value, dict):
        require(all(safe_argument_name(k) for k in value))
    if "anyOf" in schema:
        for choice in schema["anyOf"]:
            try:
                validate_arguments(value, choice, depth + 1)
                break
            except Rejected:
                continue
        else:
            raise Rejected()
    typ = schema.get("type")
    types = {"object": (dict,), "array": (list,), "string": (str,), "integer": (int,),
             "number": (int, float), "boolean": (bool,), "null": (type(None),)}
    if typ:
        require(type(value) in types[typ])
    if "enum" in schema:
        require(any(type(value) is type(x) and value == x for x in schema["enum"]))
    # Composition-only wrappers have no independent object property set.
    # The selected branch still closes its own object keys recursively.
    if type(value) is dict and (typ == "object" or "anyOf" not in schema):
        props = schema.get("properties", {})
        require(set(value) <= set(props) and set(schema.get("required", [])) <= set(value))
        for key, item in value.items():
            validate_arguments(item, props[key], depth + 1)
    if type(value) is list and (typ == "array" or "anyOf" not in schema):
        for item in value:
            validate_arguments(item, schema.get("items", {}), depth + 1)
    for key, lower in (("minimum", True), ("maximum", False), ("minItems", True), ("maxItems", False), ("minLength", True), ("maxLength", False)):
        if key in schema:
            actual = value if key in {"minimum", "maximum"} else len(value)
            require(actual >= schema[key] if lower else actual <= schema[key])


def filter_tools(result):
    require(type(result) is dict and type(result.get("tools")) is list and not result.get("nextCursor"))
    rows, seen = [], set()
    for tool in result["tools"]:
        require(type(tool) is dict and type(tool.get("name")) is str)
        name = tool["name"]
        if name not in TOOLS:
            continue
        require(name not in seen)
        seen.add(name)
        schema = sanitize_schema(tool.get("inputSchema"))
        require(schema.get("type") == "object")
        rows.append({"name": name, "inputSchema": schema,
                     "description": "Audited read-only query." if name in READ_ONLY else "Managed Unity mutation; requires a local operator lease.",
                     "annotations": {"readOnlyHint": name in READ_ONLY, "openWorldHint": False}})
    require(seen == TOOLS)
    serialized = json.dumps(rows).lower()
    require(not any(word in serialized for word in ("unlock", "execute_custom_tool", "manage_", "batch_execute")))
    return {"tools": rows}


def filter_resources(msg, result):
    require(type(result) is dict and not result.get("nextCursor"))
    if msg["method"] == "resources/list":
        require(type(result.get("resources")) is list)
        rows, seen = [], set()
        for row in result["resources"]:
            require(type(row) is dict and type(row.get("uri")) is str)
            uri = row["uri"]
            if uri in RESOURCES:
                require(uri not in seen)
                seen.add(uri)
                rows.append({"uri": uri, "name": uri.rsplit("://", 1)[-1], "mimeType": "application/json"})
        return {"resources": rows}
    require(type(result.get("contents")) is list and len(result["contents"]) == 1)
    row = result["contents"][0]
    require(type(row) is dict and row.get("uri") == msg["params"]["uri"] and type(row.get("text")) is str)
    return {"contents": [{"uri": row["uri"], "text": row["text"], "mimeType": "application/json"}]}


def validate_response(obj, msg):
    require(type(obj) is dict and obj.get("jsonrpc") == "2.0")
    require(set(obj) in ({"jsonrpc", "id", "result"}, {"jsonrpc", "id", "error"}))
    require(type(obj["id"]) is type(msg["id"]) and obj["id"] == msg["id"])
    if "error" in obj:
        require(type(obj["error"]) is dict and type(obj["error"].get("code")) is int)
        return {"jsonrpc": "2.0", "id": msg["id"],
                "error": {"code": obj["error"]["code"], "message": "Upstream reported an error"}}
    require(type(obj["result"]) is dict)
    return obj


def parse_sse(response, msg, max_bytes):
    data, event = [], "message"
    consumed = 0
    while True:
        line = response.readline(max_bytes - consumed + 1)
        consumed += len(line)
        require(consumed <= max_bytes)
        require(bool(line))
        line = line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                require(event == "message")
                obj = decode_json("\n".join(data))
                require(type(obj) is dict)
                if "method" not in obj:
                    return validate_response(obj, msg)
                require(set(obj) <= {"jsonrpc", "method", "params"} and obj.get("jsonrpc") == "2.0")
                require(obj["method"] in {"notifications/message", "notifications/progress", "notifications/tools/list_changed", "notifications/resources/list_changed"})
                # These are advisory data, never delivered to the frontend client.
            data, event = [], "message"
        elif line.startswith(":"):
            continue
        else:
            key, sep, value = line.partition(":")
            require(bool(sep) and key in {"data", "event", "id", "retry"})
            value = value[1:] if value.startswith(" ") else value
            if key == "data":
                data.append(value)
            elif key == "event":
                event = value


def preview_image(image):
    require(type(image) is dict and set(image) == {"label", "mime_type", "data_base64"})
    require(image["label"] in {"before", "after"} and image["mime_type"] == "image/png")
    encoded = image["data_base64"]
    require(type(encoded) is str and len(encoded) <= 1398104)
    raw = base64.b64decode(encoded, validate=True)
    require(33 <= len(raw) < 1048576 and base64.b64encode(raw).decode("ascii") == encoded)
    require(raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[8:16] == b"\x00\x00\x00\rIHDR")
    width, height = struct.unpack(">II", raw[16:24])
    require(0 < width <= 512 and 0 < height <= 512)
    meta = {"label": image["label"], "mime_type": "image/png", "width": width, "height": height, "bytes": len(raw)}
    return meta, {"type": "image", "mimeType": "image/png", "data": encoded}


def validate_tool_result(result):
    # Audited tools return text plus optional structured data, never content
    # resources, links, audio, server callbacks or upstream-native images.
    require(type(result) is dict and set(result) <= {"content", "structuredContent", "isError"})
    require(type(result.get("content")) is list)
    require(type(result.get("isError", False)) is bool)
    if "structuredContent" in result:
        require(type(result["structuredContent"]) is dict)
    for block in result["content"]:
        require(type(block) is dict and set(block) == {"type", "text"})
        require(block["type"] == "text" and type(block["text"]) is str)
    return result


def convert_preview(result):
    require(type(result) is dict and type(result.get("content")) is list and len(result["content"]) == 1)
    block = result["content"][0]
    require(type(block) is dict and block.get("type") == "text" and type(block.get("text")) is str)
    payload = decode_json(block["text"])
    require(type(payload) is dict and type(payload.get("success")) is bool)
    if "structuredContent" in result:
        require(result["structuredContent"] == payload)
    data = payload.get("data")
    require(data is None or type(data) is dict)
    if not data or "preview_images" not in data:
        return result
    images = data.pop("preview_images")
    require(type(images) is list and len(images) <= 2)
    converted = [preview_image(image) for image in images]
    require(len({meta["label"] for meta, image in converted}) == len(converted))
    data["preview_images"] = [meta for meta, image in converted]
    text = json.dumps(payload, allow_nan=False)
    require("data_base64" not in text and all(image["data"] not in text for meta, image in converted))
    blocks = [{"type": "text", "text": text}]
    for meta, image in converted:
        blocks.extend([{"type": "text", "text": meta["label"] + " (isolated preview)"}, image])
    return {"content": blocks, "structuredContent": payload, "isError": result.get("isError", False)}


@contextmanager
def exclusive_session(lock):
    if not lock.acquire(False):
        raise Rejected(503, -32000, "Session busy; no request was queued")
    try:
        yield
    finally:
        lock.release()


def abort_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


@dataclass
class _Session:
    upstream: str
    version: str
    touched: float = field(default_factory=time.monotonic)
    ready: bool = False
    schemas: dict = field(default_factory=dict)
    lock: object = field(default_factory=threading.Lock)
    cleanup_attempted: bool = False


class _Server(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, address, upstream=UPSTREAM, *, session_ttl=300, max_sessions=32,
                 max_request_bytes=65536, max_upstream_bytes=8388608, max_result_bytes=4194304, call_timeout=15,
                 client_timeout=5, max_workers=16, cleanup_timeout=1):
        self.upstream = upstream
        self.upstream_port = urlsplit(upstream).port
        self.max_request_bytes = max_request_bytes
        self.max_upstream_bytes = max_upstream_bytes
        self.max_result_bytes = max_result_bytes
        self.call_timeout = call_timeout
        self.client_timeout = client_timeout
        self.workers = threading.BoundedSemaphore(max_workers)
        self.sessions = {}
        self.pending_initializations = 0
        self.session_ttl = session_ttl
        self.max_sessions = max_sessions
        self.session_lock = threading.RLock()
        self.cleanup_timeout = cleanup_timeout
        self.cleanup_debt = {}
        self.cleanup_event = threading.Event()
        self.closing = False
        self.cleanup_stopping = False
        self.cleanup_thread = threading.Thread(target=self.cleanup_loop, name="managed-bridge-cleanup")
        super().__init__(address, _Handler)
        self.cleanup_thread.start()

    def process_request(self, request, client_address):
        if not self.workers.acquire(False):
            try:
                request.settimeout(0.1)
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.workers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.workers.release()

    def handle_error(self, request, client_address):
        # Never log payloads, session tokens, or traceback data from requests.
        pass

    def server_close(self):
        with self.session_lock:
            self.closing = True
        super().server_close()
        with self.session_lock:
            self.cleanup_debt.update(self.sessions)
            self.sessions.clear()
            self.cleanup_stopping = True
            self.cleanup_event.set()
        if self.cleanup_thread.ident is not None:
            self.cleanup_thread.join()

    def service_actions(self):
        with self.session_lock:
            for token, session in list(self.sessions.items()):
                if time.monotonic() - session.touched > self.session_ttl and session.lock.acquire(False):
                    try:
                        del self.sessions[token]
                        self.cleanup_debt[token] = session
                        self.cleanup_event.set()
                    finally:
                        session.lock.release()

    def cleanup_loop(self):
        # One worker, at most max_sessions debts, no unbounded queue or retry.
        while True:
            self.cleanup_event.wait()
            self.cleanup_event.clear()
            while True:
                with self.session_lock:
                    candidate = next(((key, value) for key, value in self.cleanup_debt.items()
                                      if not value.cleanup_attempted), None)
                    if candidate is None:
                        if self.cleanup_stopping:
                            return
                        break
                    key, session = candidate
                    session.cleanup_attempted = True
                if self.terminate_session(session):
                    with self.session_lock:
                        del self.cleanup_debt[key]
                else:
                    logging.getLogger(__name__).warning("Upstream session cleanup unverified; capacity retained; operator check required")

    def cleanup_request(self, method, session):
        # Internal protocol lifecycle only: no client URL, token or body selector.
        headers = {"Mcp-Session-Id": session.upstream, "MCP-Protocol-Version": session.version,
                   "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Connection": "close"}
        body = b"" if method == "DELETE" else b'{"jsonrpc":"2.0","id":"cleanup-check","method":"ping"}'
        connection = http.client.HTTPConnection("127.0.0.1", self.upstream_port, timeout=self.cleanup_timeout)
        timer, response = None, None
        try:
            connection.connect()
            timer = threading.Timer(self.cleanup_timeout, abort_socket, args=(connection.sock,))
            timer.start()
            connection.request(method, "/mcp", body=body, headers=headers)
            response = connection.getresponse()
            require(len(response.headers.get_all("Mcp-Session-Id", [])) <= 1)
            require(response.headers.get("Mcp-Session-Id") in {None, session.upstream})
            require(len(response.headers.get_all("Content-Length", [])) <= 1)
            require(response.headers.get("Content-Encoding") in {None, "identity"})
            length = response.headers.get("Content-Length")
            if length is not None:
                require(re.fullmatch(r"[0-9]+", length) is not None and int(length) <= 4096)
            require(len(response.read(4097)) <= 4096)
            return response.status
        except (Rejected, ValueError, OSError, http.client.HTTPException):
            return None
        finally:
            if timer:
                timer.cancel()
                timer.join()
            if response:
                response.close()
            connection.close()

    def terminate_session(self, session):
        status = self.cleanup_request("DELETE", session)
        # 404 itself verifies absence; success needs an exact read-only probe.
        return status == 404 or (status in {200, 204} and self.cleanup_request("POST", session) == 404)

    def exchange(self, msg, session=None, allocation=None):
        # Direct fixed-IP HTTPConnection: no environment proxy, DNS, redirect or URL dispatch.
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "Connection": "close"}
        if session:
            headers["Mcp-Session-Id"] = session.upstream
            headers["MCP-Protocol-Version"] = session.version
        connection = http.client.HTTPConnection("127.0.0.1", self.upstream_port, timeout=self.call_timeout)
        timer, response = None, None
        expired = threading.Event()
        try:
            connection.connect()
            sock = connection.sock
            def deadline():
                expired.set()
                abort_socket(sock)
            timer = threading.Timer(self.call_timeout, deadline)
            timer.start()
            connection.request("POST", "/mcp", body=json.dumps(msg, allow_nan=False).encode(), headers=headers)
            response = connection.getresponse()
            if allocation is not None:
                tokens = response.headers.get_all("Mcp-Session-Id", [])
                if len(tokens) == 1 and re.fullmatch(r"[!-~]{1,256}", tokens[0]) is not None:
                    # Capture before body parsing: even a broken reply can allocate.
                    allocation.upstream = tokens[0]
            require(len(response.headers.get_all("Content-Length", [])) <= 1)
            require(len(response.headers.get_all("Mcp-Session-Id", [])) <= 1)
            require(response.headers.get("Content-Encoding") in {None, "identity"})
            length = response.headers.get("Content-Length")
            if length is not None:
                require(re.fullmatch(r"[0-9]+", length) is not None and int(length) <= self.max_upstream_bytes)
            if session:
                require(response.headers.get("Mcp-Session-Id") in {None, session.upstream})
            if "id" not in msg:
                require(response.status == 202 and not response.read(1))
                return 202, response.headers, None
            require(response.status == 200)
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type == "text/event-stream":
                obj = parse_sse(response, msg, self.max_upstream_bytes)
            else:
                require(content_type == "application/json")
                raw = response.read(self.max_upstream_bytes + 1)
                require(len(raw) <= self.max_upstream_bytes)
                obj = validate_response(decode_json(raw), msg)
            return response.status, response.headers, obj
        except (Rejected, ValueError, KeyError, TypeError, RecursionError, OSError, http.client.HTTPException):
            if expired.is_set():
                raise Rejected(504, -32002, "Upstream deadline exceeded; mutation may have executed, do not retry automatically") from None
            raise Rejected(502, -32002, "Upstream rejected or unavailable; mutation may have executed, do not retry automatically") from None
        finally:
            if timer:
                timer.cancel()
                timer.join()
            if response:
                response.close()
            connection.close()

    def dispatch(self, msg, token, version):
        self.service_actions()
        method = msg["method"]
        if method == "initialize":
            require(token is None)
            requested = msg["params"]["protocolVersion"]
            require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", requested) is not None)
            require(version is None or version == requested)
            offered = requested if requested in PROTOCOL_VERSIONS else "2025-06-18"
            # Do not advertise client sampling, roots, experimental features or routing metadata.
            msg["params"] = {"protocolVersion": offered, "capabilities": {},
                             "clientInfo": {"name": "managed-bridge", "version": "1"}}
            with self.session_lock:
                require(not self.closing)
                if len(self.sessions) + len(self.cleanup_debt) + self.pending_initializations >= self.max_sessions:
                    message = "Session capacity reached"
                    if self.cleanup_debt:
                        message += "; cleanup unresolved, operator check required"
                    raise Rejected(503, -32000, message)
                self.pending_initializations += 1
            allocation = _Session("", offered)
            registered = False
            try:
                status, headers, obj = self.exchange(msg, allocation=allocation)
                negotiated = obj["result"]["protocolVersion"]
                require(status == 200 and negotiated in PROTOCOL_VERSIONS)
                allocation.version = negotiated
                upstream_token = headers.get("Mcp-Session-Id")
                require(type(upstream_token) is str and re.fullmatch(r"[!-~]{1,256}", upstream_token) is not None)
                with self.session_lock:
                    require(upstream_token not in {s.upstream for s in (*self.sessions.values(), *self.cleanup_debt.values())})
                    token = secrets.token_urlsafe(32)
                    while token == upstream_token or token in self.sessions:
                        token = secrets.token_urlsafe(32)
                    allocation.touched = time.monotonic()
                    self.sessions[token] = allocation
                    registered = True
                obj["result"] = {"protocolVersion": negotiated,
                                 "capabilities": {"tools": {}, "resources": {"subscribe": False, "listChanged": False}},
                                 "serverInfo": {"name": "vrchat-managed-bridge", "version": "0.1.0"}}
                return status, obj, token
            except (Rejected, KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, Rejected) and exc.status in {502, 504}:
                    raise
                raise Rejected(502, -32002, "Invalid upstream initialization or duplicate session") from None
            finally:
                with self.session_lock:
                    self.pending_initializations -= 1
                    if not registered:
                        # An unidentifiable or duplicate token must never select a
                        # different live session for DELETE. Keep an unknown debt.
                        if not allocation.upstream or allocation.upstream in {
                                s.upstream for s in (*self.sessions.values(), *self.cleanup_debt.values())}:
                            allocation.upstream = ""
                            allocation.cleanup_attempted = True
                            logging.getLogger(__name__).warning("Upstream initialization allocation unknown; capacity retained; operator check required")
                        debt_key = secrets.token_urlsafe(32)
                        while debt_key in self.sessions or debt_key in self.cleanup_debt:
                            debt_key = secrets.token_urlsafe(32)
                        self.cleanup_debt[debt_key] = allocation
                        self.cleanup_event.set()
        with self.session_lock:
            session = self.sessions.get(token)
        if session is None:
            raise Rejected(404, -32001, "Unknown or expired session")
        require(version == session.version)
        with exclusive_session(session.lock):
            with self.session_lock:
                if self.sessions.get(token) is not session:
                    raise Rejected(404, -32001, "Unknown or expired session")
            if not session.ready and method not in {"notifications/initialized", "ping"}:
                raise Rejected(409, -32000, "Session not initialized")
            if method == "tools/call":
                if not session.schemas:
                    raise Rejected(409, -32000, "A complete audited tools/list is required")
                validate_arguments(msg["params"].get("arguments", {}), session.schemas[msg["params"]["name"]])
            if method == "tools/list":
                session.schemas.clear()
            try:
                status, headers, obj = self.exchange(msg, session)
                if method == "notifications/initialized":
                    require(status == 202)
                    session.ready = True
                if method == "tools/list":
                    try:
                        obj["result"] = filter_tools(obj["result"])
                        require(len(json.dumps(obj, allow_nan=False).encode()) <= self.max_result_bytes)
                        session.schemas = {row["name"]: row["inputSchema"] for row in obj["result"]["tools"]}
                    except (Rejected, ValueError, KeyError, TypeError, RecursionError):
                        raise Rejected(502, -32002, "Invalid or incomplete upstream tool catalog") from None
                if method == "tools/call" and "result" in obj:
                    try:
                        obj["result"] = validate_tool_result(obj["result"])
                        if msg["params"]["name"] == "vrchat_me_preview":
                            obj["result"] = convert_preview(obj["result"])
                    except (Rejected, KeyError, ValueError, TypeError, RecursionError, struct.error):
                        raise Rejected(502, -32002, "Invalid upstream tool result; mutation may have executed, do not retry automatically") from None
                if method in {"resources/list", "resources/read"}:
                    try:
                        obj["result"] = filter_resources(msg, obj["result"])
                    except (Rejected, KeyError, TypeError, ValueError):
                        raise Rejected(502, -32002, "Invalid upstream resource result") from None
                return status, obj, token
            finally:
                session.touched = time.monotonic()


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def handle(self):
        self.request.settimeout(self.server.client_timeout)
        self.input_timer = threading.Timer(self.server.client_timeout, abort_socket, args=(self.request,))
        self.input_timer.start()
        try:
            super().handle()
        except OSError:
            pass
        finally:
            self.input_timer.cancel()
            self.input_timer.join()

    def reply(self, status, obj=None, token=None):
        body = b"" if obj is None else json.dumps(obj, allow_nan=False).encode()
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        if token:
            self.send_header("Mcp-Session-Id", token)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "HTTP request rejected"}})

    def do_POST(self):
        request_id = None
        try:
            require(self.path == "/mcp" and self.requestline.split()[1] == "/mcp")
            require(self.headers.get("Origin") is None)
            require(re.fullmatch(r"127\.0\.0\.1(?::[0-9]{1,5})?", self.headers.get("Host", "")) is not None)
            require(self.headers.get("Transfer-Encoding") is None)
            require(self.headers.get("Content-Type", "").split(";")[0].strip().lower() == "application/json")
            for name in ("Host", "Content-Length", "Content-Type", "Mcp-Session-Id", "MCP-Protocol-Version"):
                require(len(self.headers.get_all(name, [])) <= 1)
            length = self.headers.get("Content-Length", "")
            require(re.fullmatch(r"[0-9]+", length) is not None)
            if int(length) > self.server.max_request_bytes:
                raise Rejected(413, -32600, "Request body too large")
            msg = validate_request(decode_json(self.rfile.read(int(length))))
            self.input_timer.cancel()
            self.input_timer.join()
            request_id = msg.get("id")
            status, obj, token = self.server.dispatch(msg, self.headers.get("Mcp-Session-Id"), self.headers.get("MCP-Protocol-Version"))
            if len(json.dumps(obj, allow_nan=False).encode()) > self.server.max_result_bytes:
                raise Rejected(502, -32002, "Result byte limit exceeded; do not automatically retry mutations")
            self.reply(status, obj, token)
        except Rejected as exc:
            self.reply(exc.status, {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}})
        except (ValueError, KeyError, TypeError, RecursionError):
            self.reply(400, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid request"}})

    def log_message(self, format, *args):
        pass


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Loopback-only restrictive VRChat MCP frontend (candidate).", allow_abbrev=False)
    parser.add_argument("--upstream", required=True, choices=[UPSTREAM])
    parser.add_argument("--listen", required=True, choices=["127.0.0.1"])
    parser.add_argument("--port", required=True, choices=["18082"])
    args = parser.parse_args(argv)
    with _Server((args.listen, int(args.port)), args.upstream) as server:
        print("Restricted MCP frontend: http://127.0.0.1:18082/mcp; disconnect every old 28080->18081 tunnel first.", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
