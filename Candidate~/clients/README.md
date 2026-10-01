# Hermes conversation-bound adapter — uninstalled candidate module

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
   conversation builder is not implemented in this module.
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
user-facing separate client binding, live conversation snapshot installation and
shared-gateway activation, real Unity tasks, reload continuation, final independent
review and complete VPM/ALCOM acceptance. No plugin manifest, startup hook or MCP
configuration is installed by this change.
