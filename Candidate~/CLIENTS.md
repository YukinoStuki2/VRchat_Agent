# Native-client compatibility — development evidence only

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

## Known boundaries, not production approval

Codex's `CODEX_CA_CERTIFICATE` is **additional** trust; upstream retains native
roots. It is not an exclusive certificate pin. The in-memory Hermes context has
only the provided public CA, but this does not solve a trusted handoff itself.
Environment possession is not process attestation, credentials are not brand
identity, and a test-owned home is not a sandbox against the same OS user.

Still required: trusted client delivery and explicit per-client selection;
remote topology and endpoint authentication; approved-task stop/revocation and
pause/resume continuity; full Hermes model-loop and Windows Codex verification;
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
holding it is Hermes/Codex. End-user handoff, real native-client approved task
stop/resume, Windows Unity and final independent review remain separate gates.
