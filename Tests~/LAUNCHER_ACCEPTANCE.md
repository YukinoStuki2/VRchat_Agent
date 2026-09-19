# Launcher Windows and Unity acceptance

This document is a test procedure, NOT a claim that all steps have passed.

## Automated Windows checks

GitHub Actions workflow `.github/workflows/launcher-preview.yml` runs:

```text
python -B Tests~/launcher_windows_live.py
```

This starts only disposable local Python children, including a grandchild, and checks real Windows handle-based parent-exit detection, explicit stop and Job Object descendant cleanup. It never starts Unity, SSH, or a live MCP server. A Linux skip cannot be counted as Windows success.

## Supervised Unity 2022.3 Windows checks

Use a backed-up disposable copy. Preserve the current project and existing working manual connection until deliberately switching; do not enable Preview or Apply for these tests.

1. Install via ALCOM and open Unity. Verify Console compiles cleanly, no new Python/uvx/SSH process or 18082 listener starts without pressing the menu button.
2. Open **Tools → Yukino → Agent Connection Manager**, fill local program paths and explicit server fields. Close/reopen the window: settings should persist locally, with no connection automatically started.
3. Set up trusted SSH default identity or ssh-agent and known_hosts locally. Missing key/host trust must fail with a sanitized explanation and never prompt through hidden stdin or accept an unverified key.
4. Close manual bridge/tunnel and disconnect Coplay panel's connection. Click explicit Coplay setup if necessary. Check fixed local HTTP18081 and autostart disabled.
5. Click one-key connection. Verify ordered sidecar/Unity/bridge/SSH phases, exact intended project, restricted17tools, and `vrchat_me_status.active=false`. Confirm manager-side old28080 absent and new28082 loopback only.
6. Click disconnect. Verify no owned SSH, supervisor, bridge18082, or launcher-started sidecar remains. A sidecar started manually before launcher must remain alive and must not be killed. A Unity connection created independently must not be stopped by the launcher.
7. Repeat after preoccupying18082: fail without killing the occupant. Repeat with invalid SSH port/key and ensure rollback reaps only owned children. Do not resurrect the old directforward for convenience.
8. Connect, then close launcher window, trigger ordinary script compilation, and quit Unity separately. Each must revoke managed permissions and request/complete owned cleanup. With recovery disabled, reload must not reconnect. With the locally enabled option and a successful manual connection, verify old cleanup first, the same project/window, five idle seconds, at most 180 seconds and one recovery attempt; permissions stay revoked. Window close/manual stop/quit must cancel pending recovery. If cleanup is unconfirmed, a new start stays blocked; record actual diagnostic.
9. While connected change/open another Unity project: periodic identity check should close tunnel. This is bounded polling, not an atomic per-request instance binding; do not deliberately grant editing scope in this negative test.
10. Update through ALCOM only after disconnect/Unity close. Old ZIPs/tags remain immutable, no automatic start on reopen.

11. In preview.3, inject a temporary unavailable/slow response only in a disposable fixture or supervised copy. Expect suspended, no new tools/read requests forwarded, same SSH process/tunnel retained, local managed scope revoked, then same-project/locked verification before resuming. Test missing revoke acknowledgement, active grant, persistent failure and true project mismatch: no resume. Never replay an uncertain Apply. Ordinary import/domain reload still uses the separate opt-in teardown/recovery path.

Record actual version, statuses, Console errors, owned process start/end evidence, remote bind addresses and remaining listeners for each case. Do not include SSH passwords, private key contents or session tokens in logs/screenshots. Runtime model preview/apply/rollback acceptance is separate and not authorized by this checklist.
