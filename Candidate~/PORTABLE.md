# Portable Python development build — not a VPM release

The build uses Astral `python-build-standalone`, release `20260929`, CPython `3.11.16`. Exact HTTPS release URLs, downloaded SHA-256 values, executable paths and publisher metadata are in `distribution/python-standalone.lock.json`. The supported target set in this candidate is Windows x86-64 and Linux GNU x86-64; other targets fail before extraction. This is not proof of every Windows desktop, glibc system, Unity editor or client combination.

## Original bytes and notices

The install-only archives were downloaded and hashed from the publisher's release. Every regular file in each install-only archive was byte-compared with the corresponding path in its full distribution: Linux 3,858; Windows 3,969. The full distribution additionally has developer/test files; the two archive layouts are not equal. `distribution/python-licenses/<platform>/PYTHON.json` is the exact parsed publisher metadata, formatted as JSON, and the 19 license texts per platform are original file bytes from that matching full archive. Hashes bind both the metadata and texts. Git's final `-text` rule deliberately preserves the Windows CRLF bodies. Checks must inspect staged/committed bytes, not only the working directory.

Publisher metadata identifies Linux dynamic glibc requirements and Windows `vcruntime:140`. Linux `_dbm` includes Berkeley DB under Sleepycat; the original notice is retained. Copying license texts is evidence of their inclusion, not a legal conclusion or a completed redistribution review. The installed interpreter's bundled pip/setuptools notices are retained along with all other original install-only files.

## Assembly and scope

`portable_python.build(archive, destination, wheelhouse=None)` is a **local developer assembly**, not a ZIP/release command:

1. Read the fixed source inventory and all pinned notice bytes.
2. Refuse a pre-existing output path; hash the archive before any extraction. Reuse `tarfile.data_filter`, plus portable name/duplicate checks.
3. Copy the real source payload into `package/`, place the runtime under the Unity-ignored `Runtime~/python/`, and check exact Python version and prefix.
4. Install exact locked wheels into only this new interpreter using pip's hash enforcement, binary-only artifacts, isolated configuration, no cache and no compile step. By default use the fixed PyPI index. An explicit `wheelhouse` instead uses `--no-index --find-links` with that directory; every pip-reported file URI must stay directly in that resolved directory, be a regular non-symlink wheel, and match the exact locked version/hash and read-back bytes. Ambient proxies, Python paths and credentials are not inherited. A developer may populate this cache separately through an existing approved proxy from the fixed official wheel URLs; that does not give the runtime a proxy or credentials.
5. Check installed versions/imports and `pip check`; collect the current platform's actual LICENSE/NOTICE bytes. Read back pip's native report and match every selected wheel's version/hash to its own lock entry.
6. Copy Python and wheel notices next to the runtime. Failure removes only the newly allocated output directory. No existing Python/client environment, project, gateway, VPM index or release is changed.

The final product packer's independent-review and implementation-completeness gates remain closed. This developer directory must not be offered as the complete ALCOM candidate.

## Actual execution test

`tests/verify_portable.py` accepts `--archive`, `--dotnet`, optional `--wheelhouse`, and a new `--output` evidence path. It builds in a private temporary directory, relocates the entire assembled tree, then uses that moved interpreter for:

- actual C# `EditorOwnerProcess` startup, private pipes, TLS/MCP readiness, graceful stop and Dispose;
- run-identity, authenticated bootstrap, owned launcher, editor-owner and OS-specific memory-TLS regressions;
- pre/post payload and source hashes, plus temporary-directory cleanup. Linux also performs outer pidfd descendant and listener tracking.

The Windows **compilation step only** receives ProgramFiles/ProgramFiles(x86)/ProgramData and task-owned APPDATA/LOCALAPPDATA paths required by NuGet; runtime subprocesses keep their original restrictive environment. Reports observe TemporaryDirectory cleanup after both success and failure while propagating the original failure.

Unity traffic is explicitly synthetic in this C# fixture. It does not prove Unity import/Mono behavior, actual Hermes/Codex brand/session binding or task continuation. `.github/workflows/candidate-portable.yml` executes the Windows path on a real Windows runner and uploads raw failures as well as successful evidence. Never replace an unsuccessful Windows run with a Linux result.
