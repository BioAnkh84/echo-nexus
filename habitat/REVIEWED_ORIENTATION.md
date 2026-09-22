# Reviewed historical orientation

The maintained session launcher accepts `--orientation /absolute/package.json`
and `--orientation-sha256 DIGEST` together. Both are opt-in. Default sessions
continue without historical orientation. Self-test mode does not accept a package.
The operator selects the specific file and independently reviewed digest; package
approval labels are provenance, never credentials or grants. No export directory
is scanned and no archived command is executed.

The launcher reads only that explicit file before startup, using a nonblocking,
no-final-symlink file descriptor, regular-file/size checks and metadata stability
checks. The 32 KiB package must match the supplied SHA256 and contain one to three
historical notes with unique IDs, source-line locators and at most 4096 total text
characters. Intermediate path components can contain symlinks; digest pinning is
the content boundary. The loader checks schema and locator presence, not source
truth or human identity. It saves the exact snapshot in the private session folder.

The finite runtime grant includes `local.orientation` only when a package is
selected. The server requires that action and checks the package against its
operator-configured `ECHO_NEXUS_ORIENTATION_SHA256`; clients cannot select the pin.
Permission is rechecked at worker launch and grant fingerprint checks detect
changes before later effects/disclosure. Revocation cannot undo in-flight work.
The package is sent only to the local model. Historical text is explicitly marked
as evidence, not instructions, authority or current runtime facts. This prompt
label is not an enforceable guarantee of model behavior.

The worker retains the combined 2048 input-token limit (including orientation and
conversation history), 64 new-token limit and 180-second timeout. Oversized input
fails instead of silently truncating. The existing five-message/ten-minute session
and cleanup rules apply. Private message/export text stays out of Git.

`local_model_attempted` receipts add the package SHA256 and ordered note IDs.
The independent verifier requires the exact snapshot when those fields are
present, checks its digest and IDs, and reports `orientation_snapshot_matched`.
CLI verification uses `--orientation /absolute/snapshot.json`. This proves snapshot
consistency with the recorded selection, not that the model used it correctly,
that the source was true, or that the operation had human approval. Receipt tips
still need independent provenance for stronger tamper evidence.

Validation: synthetic parser rejection, digest tampering, nonregular/symlink
files, missing runtime permission, changed permission at launch, missing/altered
verification snapshots, and real loopback lifecycle/cleanup. A real GPU recall
trial is a separate outstanding observation, not implied by these tests.
