# Candidate owned transport delta (not installed)

Pinned upstream v10.2.0 commit and SHA-256 values are in `PROVENANCE.json`.
Only the transport source is patched; default upstream constructor keeps its legacy behavior.
The new explicit constructor takes a loopback `wss://.../hub/plugin` endpoint, a one-run bearer, an exact SHA-256 certificate pin and a private main-thread callback. The pin array is copied; no global URL/API-key preferences or discovery service are used. Unity certificate-callback API compatibility still needs real Unity/Mono acceptance.

Private path: only `vrchat_agent_dispatch` / `vrchat_agent_material_dispatch`, no global dispatcher; no session EditorPrefs writes, no reconnect, duplicate/empty session rejects, and a stopped instance cannot restart. A queued callback rechecks cancellation and ownership before mutation. Generic errors on the private path omit exception content.

## Evidence and boundary
`tests/verify_owned_transport.py` fresh-compiles the actual pinned C# transport and native interfaces against explicit Unity API substitutes. It performs real TLS/WS, wrong-pin rejection, one-use/duplicate-registration checks, and a real FastMCP SDK -> candidate auth/hub -> C# -> readback flow. It is **not a Unity editor test** and its callback is synthetic, not the material/native candidate gate.

No product endpoint is enabled. The owner bootstrap still must safely provide the pin/credentials; TLS possession by itself does not prove this is the owner-launched sidecar. Product secrets must not copy the fixture's temp-PEM/environment transport. The installed `CandidateSession` global command path still needs removal in favor of the private callback. The UI, launcher and lifecycle are not integrated. Do not publish or package as completed.

Test TLS keys are synthetic, task-owned and removed with the temporary directory. Upstream MIT license must accompany any distribution of the patched source; no full package is produced here.
