# Native-client compatibility — development evidence only

## Candidate host-side conversation binding (not installed)

`clients/hermes_binding.py` now implements per-conversation/per-generation tool
registration, detached snapshots, exact-owner CAS removal, local stale/cross-chat
refusal and owned-call cancellation. It reuses the native connection and registry;
it does not accept credentials or start a client. `clients/README.md` defines the
host contract and HA/HB checks. Prior HS/HR sections below describe the narrower
characterizations; their "not implemented" statements about those test paths do
not describe this new module. Trusted delivery, live conversation construction,
shared-gateway installation and real Unity acceptance are still absent.


## Independently owned Hermes connection shutdown (Linux characterization)

`--hermes-owned` reuses the installed `MCPServerTask.start/shutdown` lifecycle
beside a separately registered read-only probe service in one isolated Hermes
process. The two owners use the same fixture endpoint with different signed
roles and disjoint SDK sessions; this is not two real Unity projects.

HS001–HS004 check concurrent service survival, exact owner shutdown, closed-session
local refusal, and a late/repeated shutdown of generation 1 after generation 2
starts. The observer's registered schema remains byte-identical and it continues
using one session. Server traces require exactly two Hermes status calls and
three observer status calls: the stale-session attempt must never reach the
endpoint. Both owned sessions and the observer are deleted at final cleanup.
On the tested installed MCP 2.0.0 SDK, post-close sends raise `MCPError` with the
exact `CONNECTION_CLOSED` code, rather than leaking an underlying anyio exception.

The owned tasks are deliberately NOT inserted into Hermes's global MCP registry.
This proves the reusable per-object lifecycle, not a production receiver or an
API for removing an arbitrary registered server. Global shutdown appears only
in final cleanup of the test process that owns every connection. No installed
Hermes files/configuration, active gateway, model turn, or real Unity project is
changed. Exact tool registration ownership, conversation-snapshot integration,
trusted delivery and shared-gateway activation remain unimplemented.


The product still lacks a trusted operator-to-client credential handoff. These
checks deliberately do not identify a brand from a bearer token, install a
client configuration, run a model turn, or approve a Unity task.

## Changes

The owner issues a separate finite `probe:<run>` credential for its internal
readiness monitor, rather than using the `hermes:<run>` credential. The server
admits this exact signed principal and only discovers/allows `agent_status` for
it. Prepare, stop, material calls, and native tool calls fail before dispatch.
The Unity audience still rejects the probe credential. RI005, AU006, and AU007
have retained RED/GREEN evidence; existing identity and session checks remain.

## Linux native test

`tests/verify_native_clients.py` uses the installed Hermes `MCPServerTask` and an
official Codex app-server in isolated temporary homes, with only Candidate test
credentials in child environments. No inherited provider keys or real client
configuration is used. Candidate JWT private key and TLS private key remain in
memory. The public CA certificate and non-secret Codex configuration may be
written into the owned temporary home, scanned, then removed.

- Hermes uses an in-memory SSLContext, authenticated HTTP, a real MCP call,
  and `shutdown()`. Its raw discovery catalog is **not** proof that the complete
  agent tool registry applies the configured allowlist. This test calls the
  native MCP session directly, not the whole agent/model loop.
- Codex `app-server --stdio` initializes an ephemeral thread with a read-only
  sandbox and on-request approval, then uses its native MCP status/tool-call
  APIs. No `turn/start` or account login is used. `thread/unsubscribe` and stdin
  EOF end the test. Only `agent_status` and `agent_stop` are configured.
  Native `[features] plugins = false` is explicit in this test-only home: the
  default curated-plugin startup sync otherwise spawns unrelated Git egress.
  A frozen run reproduced a surviving `git ls-remote` process chain targeting
  `https://github.com/openai/plugins.git`; failed evidence and safety cleanup
  are retained. Disabling that unneeded feature is test scoping, **not** a fix
  or acceptance claim for upstream default-plugin process lifetime.
- Both clients must reject status when the expected Unity project is absent.
  Stopping a task with no approved plan must report `locally_stopped` and
  `unity_confirmed:false`; this is **not** a stop of an approved real Unity task.
- The server records separate created/deleted session sets per credential,
  checks successful DELETE of exactly each created session, and verifies empty
  runtime session state. Linux outer descendant/listener checks are separate.
- The driver scans captured output and temporary-home files for the generated
  credentials and private-key markers before writing evidence. It rejects
  `ResourceWarning`, source/input drift, residue, and evidence overwrite.

### Fixed Codex input

Official release `openai/codex`, tag `rust-v0.159.2`:

- Archive: `codex-x86_64-unknown-linux-musl.tar.gz`
- Official asset digest: `26586b0d246d41a799b0ef8ee1add370f0fb0721b3709340f28db612381616ea`
- Executable digest: `1748767b230ebfc3d4ab7e4e254920d0c0ad9691fd8c11f190e7d44511a4a92e`

The driver refuses a different executable digest before starting processes.
Installed Hermes MCP entrypoint bytes and the observed MCP package version are
recorded, but its complete transitive environment is **not** locked here.

Reproduce with the separately provisioned real client paths:

```sh
PINNED_CANDIDATE_PYTHON -I -B -W always::ResourceWarning tests/verify_native_clients.py \
  --hermes-python /absolute/installed-hermes/venv/bin/python \
  --hermes-source /absolute/installed-hermes \
  --codex /absolute/verified-codex-binary \
  --output evidence/native-clients-unique-label.json
```

The test does not install those clients or register them in an existing profile.
It is Linux-specific, not Windows native-client acceptance.

## Hermes native tool registry (isolated development slice)

Use `--hermes-registry` instead of `--approved-tasks` to exercise installed
`register_mcp_servers` and `tools.registry.registry.dispatch`, rather than
calling the SDK session directly. Registration occurs only inside a newly
created child process with its own temporary HERMES_HOME; no real profile,
gateway toolset or model prompt is altered, and there is no model turn.

The test config explicitly sets `lazy: false`, `trust: full` for the fixed local
fixture, `tools.include: [agent_status, agent_stop]`, `tools.resources: false`,
`tools.prompts: false`, and disables sampling/elicitation. Server trust here is
not a human task approval. The original test helper incorrectly placed the
resource/prompt switches at top level. A real registry run exposed four extra
utility tools; retained RED evidence captured their exact non-secret names.
Fixing the field locations made the exact-two-tools assertion pass without
changing installed Hermes or Candidate server permissions. SDK-only results
never established that filter boundary.

The independent HR001–HR006 group checks exact registered schemas/toolset,
local unknown-tool rejection, actual dispatch preserving the missing-Unity
error and unapproved-stop response, idempotent same-run registration, complete
shutdown/deregistration and post-stop refusal, and the documented fact that
`enabled: false`/a changed allowlist for an existing name is NOT reconfiguration
or revocation. The parent server observes exactly the two intended tool calls,
one created/deleted Hermes session and no calls for blocked/stale tools.
A native registry success contains `result` plus `structuredContent`; both
are checked against the real response, not confused with the SDK envelope.

**Integration constraints remain:** this global shutdown API is safe here only
because the isolated process owns every registered MCP service. It must NOT be
transplanted into a shared gateway as per-project disconnect. A future receiver
must own the exact lifecycle, avoid same-name credential replacement, and respect
immutable per-conversation tool snapshots. The registry may write non-secret
schema caches; the whole test home is secret-scanned and removed. These tests do
not prove trusted operator-to-client delivery, per-session gateway integration,
chat approval, Windows Hermes, or the full model loop. Existing direct SDK,
Codex and approved-task/pause fixture modes remain separately runnable.

## Explicit local client admission (development slice)

The local Unity window has independent Hermes/Codex role toggles, both off by
default and disabled while an owner exists. Starting snapshots those booleans;
it does not connect either client, deliver credentials, attest executable brands,
or grant a task. To change the selection, stop the current owner and create a
new run; that does not restore stopped grants. The choices are not persisted.

The issuer creates only selected client credentials plus the internal unity/probe
roles. The child verifier admits only that same selected set plus the read-only
probe, even if an unselected role somehow presents an otherwise valid signed
same-run token. Child configuration and the private Unity receipt are version 2;
legacy/missing/malformed selections fail closed, never default to both clients.
The private receipt carries only public selection labels and Unity's credential,
not client credentials. Existing protocol-only fixtures opt in to both explicitly.

CS001–CS006/CS008–CS010 exercise issuer/policy boundaries, actual TLS/HTTP and
owned private subprocesses. CS007 freshly compiles the C# receipt consumer with a
synthetic owner pipe, checking every selection against missing/wrong/legacy/type
mismatches before connect. The existing UA006 UI-double case checks default-off,
independent toggles and disabled changes during an owner run. These are not a
real Unity UI test, trusted client handoff or the full client model loop.

## Same-connection local pause (development slice)

The existing Unity windows now expose exact-plan Pause and evidence-revalidated
Resume. No MCP client receives those controls. The same plan/digest/task/client,
connection and absolute expiry are retained; no TTL renewal, implicit approval,
rollback or automatic reconnect occurs. Stopped, expired, replaced, disconnected,
reloaded, evidence-changed or locally revoked grants cannot be resumed. A material
pause retains the existing project-wide single writer. Calls while paused return
an explicit error, not fabricated successful work; only an exact live-plan paused
response is retained by the runtime. Other failure paths still revoke.

`ContinuityCases` PC001–PC005 and `test_runtime_pause.py` PR001–PR005 cover
identity/expiry, relevant-state conflicts, local-only controls and strict error
classification. The native `--approved-tasks` mode adds a **separate** NP001–NP004
group: both Hermes/Codex exercise read and material calls while fixture-paused,
then continue under the identical locally resumed plan. These are not cross-reload
continuation, real human clicks or real Unity execution. The existing adapter UI
test uses Unity API doubles; source seams do not replace Editor acceptance.

## Known boundaries, not production approval

Codex's `CODEX_CA_CERTIFICATE` is **additional** trust; upstream retains native
roots. It is not an exclusive certificate pin. The in-memory Hermes context has
only the provided public CA, but this does not solve a trusted handoff itself.
Environment possession is not process attestation, credentials are not brand
identity, and a test-owned home is not a sandbox against the same OS user.

Still required: trusted client delivery beyond the implemented local role selection;
remote topology and endpoint authentication; real-Unity approved-task stop/revocation
and cross-reload/reconnection continuity; full Hermes model-loop and Windows Codex verification;
actual Unity import/runtime/human checks; final independent review; complete
Candidate packaging and real VPM/ALCOM acceptance. No production configuration,
main branch, historical release, or public VPM index is changed by these tests.

References inspected:

- https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- https://developers.openai.com/codex/mcp
- https://github.com/openai/codex/tree/rust-v0.159.2/codex-rs/app-server-protocol
- https://github.com/openai/codex/blob/rust-v0.159.2/codex-rs/http-client/src/client_tls.rs

## Authenticated approval identity (development slice)

Authenticated calls now bind Unity's existing `client_id` field to the canonical
JSON tuple `[verified access-token client_id, exact SDK session_id]`. It is built
from the pinned verifier's request context, not tool arguments, MCP `_meta`, a
client name or a claim supplied by the model. The tuple is only an opaque identity
key on the existing protocol: task, connection, plan/digest, target and capability
checks remain in place. No additional approval button or field-level grant is added.

The runtime refuses missing authentication and a different principal in an already
bound SDK session. Native-read and material plans retain that identity when the
SDK request context disappears, so DELETE/cancellation cleanup revokes the exact
approved plan. Canonical tuple encoding avoids delimiter ambiguity. The explicit
anonymous test-fixture mode retains its old session-only keys; installed startup
remains authenticated-only.

`tests/test_client_binding.py` separates real signed-token/MCP/websocket tests,
small request-context unit tests, and a freshly compiled net8 gate/file-backend
fixture. The compiled case approves separate clients locally, changes only its
synthetic material candidate, checks cross-client stop rejection, and proves one
session exit removes its two plans without undoing candidate bytes or another
client's native-read approval. It is **not** a real Unity or human approval test.

This closes the missing authenticated-principal propagation into a plan, **not**
the operator-to-client credential handoff or client-software authentication gap.
A signed role (including a `hermes:` or `codex:` role) does not prove the program
holding it is Hermes/Codex. End-user handoff, real-Unity approved-task stop/resume,
Windows native clients/Unity and final independent review remain separate gates.

## Approved-task native-client verification (Linux fixture)

Add `--approved-tasks` to the reproduction command to run both installed native
clients concurrently against authenticated TLS and a **freshly compiled net8**
`WirePeer` containing the production read and material gates. Optional `--dotnet`
selects the separately provisioned compiler/runtime. The verifier records the
compiler, upstream Response.cs, native client inputs and runtime/gate/test source
hashes before/after; it never accepts an old DLL supplied by the caller.

`tests/native_approved_tasks.py` reuses the existing owner, TLS, session recorder,
compiled gate fixture and outer descendant/secret scanner. Its exact local
approval pipe belongs to the test driver, not either MCP client. The Hermes test
peer's additional NDJSON mode only forwards seven fixed test tools through the
installed MCP engine; it cannot approve, execute arbitrary tools or run a model.
None of these test files are part of the shipped source payload.

The six case IDs are a separate group, not added to the existing C# or SDK totals:

- NA001: each local plan contains the corresponding signed principal and exact
  native MCP session, not the program's self-reported brand/name.
- NA002: one client's local read approval does not authorize the other client.
- NA003: material editing retains the existing **single-writer per project**
  rule. Another client cannot prepare over or stop the active write plan. After
  exact stop, the other client may prepare its own separately approved candidate.
- NA004: both real native clients explicitly stop approved read/material work;
  stopped grants reject reuse, candidate bytes stay changed, original bytes stay
  unchanged, and stopping A's read leaves B's independently approved read usable.
- NA005: fresh read plans after stopping are pending and cannot reuse approval.
- NA006: fresh material-edit plans require local approval again. Each native
  client's actual session DELETE revokes both its read and material plans with
  compiled-gate acknowledgements, without undoing files. Closing A leaves B's
  read usable; finally both gate plans, runtime sessions and histories are empty.

The first harness incorrectly expected concurrent material writers. Production
correctly rejected it with `project_write_busy`; the fixture was corrected to
exercise the existing serial-write contract, **not** to relax the production gate.
A separate retained RED demonstrated the old fixture readback could only select
one candidate; a fixed two-candidate fixture selector now checks both exact files.
Expected denied calls may produce fixed rejection/stop-unconfirmed warnings when
a gate already removed an unapproved plan. Positive approved-task stop and DELETE
acknowledgements are asserted separately, not inferred from the overall exit code.

This establishes **real native MCP calls against fixture-approved production gates**,
not a model-loop turn, trusted operator-to-client credential delivery, software
attestation, a real human click, Windows native-client acceptance or Unity Editor
execution. Re-preparing after stop requires new approval; it is **not** the still
missing cross-reload/reconnection task-continuation workflow. No secret/private key is
written; generated child output and owned test-home files are scanned before
report persistence, and tracked descendants/listeners and temporary roots must be
absent. The original no-Unity compatibility mode remains separately runnable.
