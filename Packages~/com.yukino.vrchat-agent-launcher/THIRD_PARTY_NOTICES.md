# Third-party notices

This launcher and bundled restrictive bridge are original project code licensed under the accompanying MIT LICENSE (Yukino / Hermes Agent).

CoplayDev Unity MCP 10.2.0 is a separately installed dependency, not redistributed here. The adapter calls pinned public APIs and validates a small set of exact private fields for its own connection lifecycle and read-only manager-busy checks; names and protocol contracts are interoperability references, not a copied upstream implementation.
Source: https://github.com/CoplayDev/unity-mcp/tree/v10.2.0

CPython, uv/uvx, OpenSSH and Unity are separate prerequisites and are not included in this ZIP. Their own licenses and distribution terms apply. The subprocess supervisor uses the CPython standard library and Windows system APIs; it does not embed an SSH implementation, credentials or upstream package archive.
