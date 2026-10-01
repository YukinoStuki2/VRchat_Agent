# Hermes host connection and conversation — uninstalled candidate modules

## Current handoff/plugin slice (uninstalled)

The Linux receiver, fixed SSH subsystem relay, owned editor delivery, per-chat
new AIAgent, opt-in plugin entry and standalone-plugin in-memory layout now exist.
See `INSTALL.md` for the manual operator boundary and deployment prerequisites.
The relocated plugin is exercised through the real PluginManager/hook path, with
platform authorization/replies and model messages explicitly test-driven. No live
gateway activation, real model turn, Windows Hermes, cross-host deployment or
Unity Editor acceptance is claimed. Local Codex user entry, task reload, final
independent review and full VPM/ALCOM delivery remain open. Older sections describe
their narrower historical scopes; they do not negate the current source work.

`clients/hermes_binding.py` is host-side code for the installed Hermes environment,
not a sidecar dependency or an installed plugin. Importing it starts no process,
opens no endpoint, reads no credentials and registers no tools. It is deliberately
not copied into the Unity package's `Runtime~` source payload.

## Host contract

1. The trusted host supplies an **already authenticated, exclusively owned** native
   `MCPServerTask`, on the same running event loop that started it. TLS policy,
   endpoint/project verification, finite credentials and trusted delivery are the
   host's responsibility; this API accepts no credential/configuration document.
2. `await bind(peer, registry, conversation_id=..., include=(...))` transfers that
   peer to one binding. The runtime conversation ID is mandatory and the exact
   nonempty allowlist must exist in a complete, duplicate-free catalog. Failure
   closes the newly transferred peer. Trying to adopt an already owned peer is
   rejected **without** closing its existing owner.
3. Use `binding.snapshot()` only when constructing a **new** conversation. It
   returns a detached copy. It does not patch an existing agent's tool list,
   refresh a gateway or authorize a project task. Installation into a real
   conversation builder is provided separately below, not installed in a gateway.
4. Hermes normal `handle_function_call` supplies `session_id` as trusted dispatch
   metadata. The handler does not use `task_id` or a model argument named
   `session_id` as identity. The schema contains the remote tool's original
   arguments only. New generations have distinct random tool names, so old
   snapshots cannot silently route to the new generation.
5. Dispatch from a worker while the owned event loop runs. Same-loop synchronous
   dispatch fails locally instead of deadlocking. Calls use the captured exact
   native session: a changed/reconnected session is rejected, not adopted.
6. Await `binding.close()` on the owned loop before stopping that loop. It marks
   the binding closed, removes only its still-current ToolEntry objects via the
   native `restore_registration` compare-and-swap, cancels owned in-flight calls,
   and shuts down only the owned peer. A cancelled close waiter does not cancel
   shared cleanup; a later close waits for the same result. Cleanup errors remain
   errors, even though peer shutdown is still attempted. No global MCP shutdown
   or name-only deregistration is used.

Responses retain the complete MCP envelope under `mcp`; `isError` additionally
sets the fixed `candidate_remote_error` category. Timeouts, interruption and
transport exceptions report a fixed category plus `outcome_unknown:true`, never
raw exception text or success. There are no retries and no rollback. A late reply
after stop is uncertain, even if it contains success. Transport exceptions/timeouts
close this generation; ordinary remote tool denials retain server-side semantics.
Already-executed remote mutations cannot be cancelled retroactively.

## Reuse and compatibility boundary

Uses native `MCPServerTask`, public `ToolRegistry` registration/snapshot/CAS APIs,
and its existing `_convert_mcp_schema` helper rather than another schema normalizer
or HTTP transport. That underscored helper and MCP 2.0 result interfaces are
version-sensitive; native input hashes are recorded in integration evidence.
The adapter does not modify installed Hermes. Do not install it into another
version without rerunning the contract and actual-dispatch checks.

The native task is slotted and cannot be weak-referenced. Ownership tracking uses
weak **Binding** values keyed by the live peer identity; bindings retain their peer
while live. This avoids retaining credentials forever in a module-global owner
map. It is a host lifecycle guard, not protection against arbitrary same-process
Python code or another OS process running as the same user.

## Verification

```
INSTALLED_HERMES_PYTHON -I -B -W always::ResourceWarning \
  tests/hermes_binding_contracts.py /absolute/installed-hermes

PINNED_CANDIDATE_PYTHON -I -B -W always::ResourceWarning \
  tests/verify_native_clients.py --hermes-binding \
  --hermes-python /absolute/installed-hermes/venv/bin/python \
  --hermes-source /absolute/installed-hermes \
  --codex /absolute/verified-codex-binary \
  --output evidence/unique-binding-run.json
```

HA001–HA015 use the real native registry with deterministic peer doubles. HB001–HB005
use real TLS/MCP sessions, the actual adapter and installed `handle_function_call`,
next to a separately registered read-only service. Traces require exactly the
allowed calls, two Hermes sessions and one observer session, each with matching
DELETE; no denied/stale call reaches the endpoint. The endpoint/Unity backend and
conversation metadata remain fixtures; **there is no model turn or real gateway
activation**. The unit/native groups are Linux evidence, not Windows Hermes.
Windows portable CI separately compiles adapter syntax and exercises the existing
sidecar regression; it does not import Hermes or run HA/HB there.

Still missing: trusted operator credential delivery, authenticated remote topology,
user-facing separate client binding and shared-gateway activation, real Unity tasks, reload continuation, final independent
review and complete VPM/ALCOM acceptance. No plugin manifest, startup hook or MCP
configuration is installed by this change.

## New-conversation constructor (candidate, not installed)

`hermes_conversation.conversation(peer, include=(...), options={...})` is an async
context manager for one **new** native `AIAgent`. The trusted host first verifies
and starts the exclusively owned peer on the same running loop. The context
manager creates a fresh random runtime `session_id`, binds the peer, and passes
only its unique registered toolset through native `enabled_toolsets`. It compares
the resulting schemas, tool names, scope and identity to native assembly, then
detaches the schema list **before any turn**. It neither hot-replaces an existing
agent nor restores prior messages, session identity or task authorization.

Native progressive disclosure is preserved: in the tested installation the model
sees `tool_search`, `tool_describe` and `tool_call`; their searchable catalog and
call scope contain only this binding's tools. The remote tool names are replaced
by generation-specific opaque names. Search uses the original descriptions (the
fixture's Chinese description contains `Unity`), not an assumed remote raw name.
Scope controls protect this managed path, not arbitrary same-process code.

Run blocking agent operations in a worker while the peer's event loop stays live.
The trusted caller owns any model turn and must await it or coordinate its stop
before leaving the context. **The constructor itself does not call a model.**
It does not sanitize or override trusted provider options, suppress native hooks,
isolate HOME, or make native initialization side-effect-free. The installed
Hermes environment, provider configuration and plugins must be audited by the host.
Ownership keys (`session_id`, toolsets, prefill history) cannot be overridden by
options. No chat command, receiver, gateway hook or credential handoff is installed.

Exit first closes/revokes the binding, then waits for a started constructor and
closes its exact owned agent. A partial constructor is retained for native cleanup;
constructor errors return a fixed category, and cleanup always uses the owned
session ID. Repeated cancellation does not abandon cleanup. Cleanup errors are
not success. This does **not** forcibly terminate a stuck native constructor or
an in-process thread; the host must provide process-level supervision and must
not interpret a hung/failed cleanup as completed. There is no automatic retry,
reconnection, transfer to a new generation, permission restoration or rollback.

### Verification added for construction

```
INSTALLED_HERMES_PYTHON -I -B -W always::ResourceWarning \
  tests/hermes_conversation_contracts.py /absolute/installed-hermes

PINNED_CANDIDATE_PYTHON -I -B -W always::ResourceWarning \
  tests/verify_native_clients.py --hermes-conversation \
  --hermes-python /absolute/installed-hermes/venv/bin/python \
  --hermes-source /absolute/installed-hermes \
  --codex /absolute/verified-codex-binary \
  --output evidence/unique-construction-run.json
```

HC001–HC011 use the real registry/schema assembly and deterministic AIAgent/peer
doubles for failure and cancellation. HN001–HN005 use real native `AIAgent`
construction and its executor, real TLS/MCP, two simultaneous separately scoped
agents and a registered observer. Tool messages are explicitly supplied fixtures,
**not generated model responses**. Search/describe/call deny other bindings;
closing one agent does not break the other or observer; stale calls cannot reach
wire. Created sessions must match DELETE and the outer verifier checks secrets,
process/listener absence and isolated HOME removal.

A Python audit guard in this isolated native test permits only the exact fixture
loopback endpoint. Initial diagnostic runs intercepted four native model-context
metadata lookups (endpoint metadata/Ollama detection, not inference). The test
now writes only a non-secret explicit `model.context_length` in its isolated HOME;
final acceptance requires zero denied network attempts. This does not change
production configuration or promise that native constructor defaults never network.
Windows CI compiles both host modules; HC/HN execute in Linux's installed Hermes,
not Windows Hermes. Final independent review, trusted credential delivery,
user-facing binding/shared-gateway activation, real Unity/model end-to-end work,
reload continuation and complete VPM/ALCOM remain separate incomplete gates.

## Fixed-target connection (candidate, not installed)

`await hermes_connection.connect(port=..., certificate=..., pin=..., bearer=...,
expires_at=...)` creates one owned native SDK session. Pass the returned peer to
`conversation(...)` or `bind(...)` on the same running loop and await its shutdown
on every path. Import is inert. There is no JSON/CLI receiver or gateway hook.

All arguments come from a **trusted, authenticated host handoff**, not a model,
chat message or discovered endpoint. This API does NOT authenticate that handoff,
attest a client's brand/role, verify a remote Unity project, approve a task, start
a tunnel or mint credentials. The endpoint is constructed, never caller-parsed:
`https://127.0.0.1:<port>/mcp`. Remote operation requires a separately verified
loopback tunnel and certificate/role/project binding. No public address is accepted.

The client uses an explicit SSLContext with only the supplied single leaf
certificate, validates its DER SHA-256 against the handoff pin, rejects CA grants,
and keeps normal hostname/chain validation and TLS >= 1.2. This is exclusive leaf
trust, not a separate per-socket certificate-hash hook. No system CA bundle,
proxy environment, redirect, credential file, OAuth flow or fallback is used.
The host must suppress unsafe SDK/debug logging and protect its own arguments;
Python cannot guarantee memory erasure or defend against arbitrary same-process
code. The caller's references are not erased by clearing the client's headers.

Why use the installed SDK directly? The inspected native `MCPServerTask` hard-codes
redirect following and inherits proxy environment; its configuration does not
provide the required fixed-target policy. This module reuses its installed
Streamable HTTP/ClientSession plus Hermes's `sdk_httpx` compatibility helper,
not a second HTTP or MCP protocol implementation and not a patched installation.
The binding's peer interface is `session` plus async `shutdown`; the earlier
MCPServerTask path remains supported and unchanged.

One dedicated task owns all SDK context entry/exit. Admission waits for initialize
and a catalog round trip, requires a stateful session and pins its HTTP session ID.
Request hooks fix URL/method/session, reject resumption and a second GET before
network I/O. Response hooks reject every redirect, even one with a valid MCP body,
and changed session IDs. No automatic session recreation or request replay is
permitted. This does not promise a single TCP socket: the SDK may use separate
HTTP connections for one session. A broken stream can be detected only when the
SDK reports it or attempts its blocked retry; there is no independent heartbeat.

Local expiry uses both per-request wall-clock checks and a monotonic idle deadline.
On expiry or close, `session` is cleared before SDK cleanup; existing bindings then
refuse stale calls. Already dispatched writes may have an unknown outcome, and no
rollback is attempted. DELETE alone remains allowed for cleanup after local expiry.
The server can reject DELETE after actual credential expiry: that is cleanup debt,
not success. A created session needs an exact successful DELETE receipt; failure
raises a fixed error rather than adopting the SDK's swallowed termination failure.
Repeated cancellation waits for owned cleanup, and startup failures expose fixed
categories. Network I/O is bounded; a blocked event loop/native thread still needs
host process supervision. Client HTTP headers are cleared after exit.

### Connection verification

```
INSTALLED_HERMES_PYTHON -I -B -W always::ResourceWarning \
  tests/hermes_connection_contracts.py /absolute/installed-hermes

PINNED_CANDIDATE_PYTHON -I -B -W always::ResourceWarning \
  tests/verify_native_clients.py --hermes-connection \
  --hermes-python /absolute/installed-hermes/venv/bin/python \
  --hermes-source /absolute/installed-hermes \
  --codex /absolute/verified-codex-binary \
  --output evidence/unique-connection-run.json
```

HE001–HE014 use the real installed SDK/HTTP client with mock HTTP responses; negative
cases deliberately generate captured SDK diagnostics. HT001–HT008 use real TLS,
the new connector and real AIAgent construction/executor with fixture tool messages:
two isolated conversations, a native registered observer, blocked wrong certificate
and invalid bearer, poisoned proxy environment, and idle-expiry DELETE. The outer
verifier reconciles three Hermes sessions, observer/Codex sessions, exact calls,
zero forbidden-network attempts, secret scans and process/port/HOME cleanup.
No model request, real Unity instance, remote handoff or gateway activation occurs.
Windows CI only syntax-compiles the host modules; these contracts/native scenarios
remain Linux evidence. Final independent review and complete VPM/ALCOM are pending.
