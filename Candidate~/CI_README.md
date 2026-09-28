# Candidate CI source, NOT an ALCOM release

This branch incrementally carries isolated candidate source and real Windows
kernel checks. It is not an installable or reviewed complete product. No package
ZIP, version tag or live VPM index is published by this workflow.

Initial CI scope: stdlib-only Windows Job Object/process HANDLE ownership and
explicitly synthetic child-process tests. The job creates no Unity project,
SSH connection, MCP registration, public listener or credentials. The copied
Windows process module keeps its original bytes; provenance and MIT license are
under `launcher/`.

Four executed tests with no failures/skips/resource warnings plus exact source
hashes are required; a GitHub job or one output line alone is not acceptance.
The unittest cases assert observed process/descendant exit and close their owned
HANDLEs and readers in finally. A failed check must be preserved, not converted
into a skip or ignored by a later command. CI cancellation/timeout is no verdict.

User authorization for this branch and GitHub Actions was confirmed on
2026-09-28. This does not authorize updating main, replacing a published version,
changing the public VPM index or installing into a real authoring project.
Other incomplete modules remain under development and receive separate checks;
passing these tests is NOT Unity, ALCOM GUI, client-binding or product approval.
