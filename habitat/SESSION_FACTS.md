# Current request facts

Opt in with `habitat/session.py --session-facts` alongside the normal local-model
session arguments. The launcher grants `local.session_facts` for that finite
session and enables `ECHO_NEXUS_ENABLE_SESSION_FACTS`. Default sessions are unchanged;
self-test and nonlocal backends reject this option. The launcher also supplies its
checked commit as `ECHO_NEXUS_SESSION_COMMIT`; this field is explicitly labeled
launcher-reported, not independently attested.

For each request, after authority admission, the server creates a small snapshot
from configuration and the inputs actually selected for that request. It includes
OS family, configured local subprocess inference, external-model calls disabled
for that backend, no model tools/live Habitat interface, context and orientation
counts, timestamp and request ID. It contains no registry path, bearer credential,
personal message, machine inventory, or model directory. Hardware health, other
processes and whole-Habitat state remain explicit unknowns. No process/OS sandbox
or global network isolation is claimed. Persistent personal-memory retrieval is
not enabled in this maintained session; response logging is separate.

Clients cannot submit `session_facts`. The server requires the separate action
before generating them and rechecks it at worker launch. Existing grant fingerprint
checks remain authoritative before later effects/disclosure. Snapshot contents
never authorize execution, renew a grant, or override an expired/revoked grant.
The snapshot describes configuration at request time, not mutable global state
or a future guarantee. This small set has no asynchronously refreshed data source;
it is not a general atomic control-plane snapshot or TOCTOU solution.

The worker receives the snapshot separately from historical orientation and
conversation context, with instructions to avoid inferring capabilities or health.
The complete prompt still shares the existing 2048-token input limit and 64-token
output limit. It fails on oversized input; no silent truncation or automatic retry.

The successful response preserves the exact snapshot. The local-model-attempt
receipt records its canonical JSON digest. Independent verification checks the
response/snapshot digest binding, request ID, source, timestamp type, context count,
and orientation count, reporting `session_facts_snapshot_matched`. It does not
independently inspect the host, prove model use, authenticate human authority, or
prove semantic correctness. Saved responses are the snapshot artifacts; no separate
private data scan or export import is performed.

Synthetic tests cover missing/revoked permission, client spoofing, snapshot
binding even when a response hash is recomputed, per-request freshness of IDs and
context counts, response persistence, and loopback lifecycle cleanup. Host semantic
trials remain necessary to observe whether the model describes its setting accurately.

The initial three-session host trial confirmed snapshot/receipt binding and local
Linux grounding but exposed source confusion: the model omitted supplied historical
summaries from its access description and called current facts historical evidence.
The prompt now explicitly distinguishes server-derived current configuration,
separately supplied historical summaries, and user messages. No source is promoted
to permission, direct archive access, or health proof. The same fixed questions are
retained for comparison; the revised prompt still needs host semantic observation.
