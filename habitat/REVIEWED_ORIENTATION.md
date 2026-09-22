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

## Status-label guidance

A host trial recalled the verification caution but described an old `verified`
label as indicating past processing. The label alone supports no such inference.
The worker prompt now explicitly separates recorded claims from processing,
success, permission and current health, and says receipts do not renew authority.
Ledger/journal-tail inspection alone is not proof of runtime health.

This is model guidance, not a new enforcement mechanism. Existing grant checks
remain the runtime permission boundary. Responses remain unverified. Host trials
must inspect generated answers for these distinctions; passing code tests cannot
establish semantic compliance or resistance to misleading prompts.

## Output stopping evidence

The local worker retains its 64-new-token limit and records `generation` metadata:
`finish_reason` (`eos`, `length`, or `unknown`), `generated_tokens` (including special
tokens), and `max_new_tokens`. EOS at the last allowed token takes precedence over
length. Unknown means neither EOS nor exhausting the cap explains the stop.
The parent requires this metadata from the subprocess. HTTP responses and
`generation_result` receipts carry it; the independent verifier checks agreement.
Legacy saved exchanges without these fields remain verifiable.

The session prints a warning on length or unknown. `completed_unverified` means
the exchange returned and was recorded; it does not mean the answer is complete.
EOS is a model stop signal, not proof of semantic completeness or correctness.
There is no automatic retry, continuation, grant renewal or output-limit increase.
Short-answer guidance reduces verbosity but does not guarantee compliance.

A subsequent two-question host trial produced EOS at 36 and 32 tokens and consistent
saved evidence, but overstated mandatory reapproval and historical integrity.
The guidance now explicitly allows existing valid applicable grants and limits
hash comparisons to consistency with compared bytes. These refinements still
require host semantic observation; earlier trial results do not validate this
new prompt revision.

A further host answer generalized a valid grant to later tasks of the same type.
The prompt now explicitly requires checking each proposed action against the
actual grant's scope and conditions, rejects inference from task similarity, and
treats missing grant terms as unknown applicability. This is advisory guidance;
the runtime authorization checks remain the enforcement boundary. Independent
single-question sessions are used for the next smoke trial to avoid carryover
from earlier answers. Each session has its own explicit finite operator grant.
