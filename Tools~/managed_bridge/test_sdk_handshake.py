"""Optional REAL installed Python MCP client against loopback fixtures, not Unity.
Run independently with the Hermes development venv (contains mcp/anyio).
"""
import json
import threading
import unittest

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from test_bridge import Upstream, running, SAFE, URIS
import bridge


class SdkHandshakeTest(unittest.TestCase):
    def test_real_sdk_can_negotiate_list_and_read_status(self):
        baseline = set(threading.enumerate())
        for chosen in ("2025-03-26", "2025-06-18"):
            with self.subTest(chosen=chosen), running(Upstream()) as upstream:
                base = upstream.default_reply
                def negotiate(msg, headers):
                    status, hdr, raw = base(msg, headers)
                    if msg["method"] == "initialize":
                        obj = json.loads(raw)
                        obj["result"]["protocolVersion"] = chosen
                        raw = json.dumps(obj).encode()
                    return status, hdr, raw
                upstream.reply = negotiate
                with running(bridge._Server(("127.0.0.1", 0), f"http://127.0.0.1:{upstream.server_port}/mcp")) as front:
                    async def connect():
                        with anyio.fail_after(10):
                            # Frontend DELETE remains denied: lifecycle is internal.
                            async with streamable_http_client(f"http://127.0.0.1:{front.server_port}/mcp", terminate_on_close=False) as streams:
                                read, write = streams
                                async with ClientSession(read, write) as session:
                                    result = await session.initialize()
                                    self.assertEqual(result.protocol_version, chosen)
                                    tools = await session.list_tools()
                                    self.assertEqual({tool.name for tool in tools.tools}, set(SAFE))
                                    resources = await session.list_resources()
                                    self.assertEqual({str(row.uri) for row in resources.resources}, set(URIS))
                                    response = await session.call_tool("vrchat_me_status", {})
                                    self.assertFalse(response.is_error)
                    anyio.run(connect)
                    self.assertEqual(upstream.calls[0][1]["params"]["protocolVersion"], "2025-06-18")
                    for _, msg, headers in upstream.calls[1:]:
                        self.assertEqual(headers["mcp-protocol-version"], chosen)
                        self.assertNotIn("_meta", msg.get("params", {}))
                self.assertEqual(upstream.active_sessions, set())
                self.assertEqual(front.sessions, {})
                self.assertEqual(front.cleanup_debt, {})
                self.assertEqual(len(upstream.deletes), 1)
        self.assertFalse(set(threading.enumerate()) - baseline, "SDK or cleanup thread leaked")


if __name__ == "__main__":
    unittest.main()
