# Independent exchange evidence verification

`habitat/verify_exchange.py` is a read-only offline checker. It does not import
the HTTP server, receipt writer or their verification helpers. It evaluates a
bounded claim: a supported completed exchange has a coherent event sequence,
matching recorded memory entries, and a matching captured response.

Run it only on separately authorized, quiescent evidence snapshots under trusted
operator control. Explicit file paths are inputs to a local operator tool, not
an HTTP grant or permission to read arbitrary live data. No grants are created,
restored or renewed. No runtime outcome or receipt is promoted or rewritten.

```sh
python habitat/verify_exchange.py \
  --ledger /absolute/snapshot/execution.jsonl \
  --memory /absolute/snapshot/root_memory.jsonl \
  --response /absolute/snapshot/response.json \
  --request-id REQUEST_ID \
  --expected-tip SEPARATELY_RETAINED_LEDGER_TIP
```

For Vexis chat or handshake, supply the corresponding Vexis memory snapshot.
The expected tip refers to the entire ledger snapshot, which can include later
exchanges. The response receipt must refer to the selected exchange's final event.
The tool requires a tip but cannot authenticate its provenance. Supplying a tip
copied from the same untrusted ledger provides no independent anchor.

Exit 0 and `exchange_evidence_consistent` mean that the hash chain, selected
request's event ordering, stable grant metadata, unverified outcome fields,
two unique memory-entry byte hashes in order, recorded reply and captured
response agree. Exit 1 and `not_verified` cover unavailable, malformed,
incomplete, inconsistent or unsupported evidence. Files are bounded to 8 MiB,
final symlinks and nonregular files are refused, and changes detectable during
a single file read are refused. This is not an atomic snapshot across files;
freeze or export the evidence first. The tool never repairs or truncates data.

Both `authority_verified` and `task_success_verified` remain false on a match.
Hash agreement does not establish event truth, human approval, receipt origin,
model correctness, delivery to a particular client, durable future persistence
or semantic task success. The original request body and provider payload are
not supplied or independently checked. A filesystem owner can rewrite evidence;
trusted external anchors and source provenance remain necessary. Duplicate
matching memory entries are treated as ambiguous and refused.

Only the current completed Cipher/Vexis chat and handshake event forms are
supported. Failed/incomplete exchanges and future schemas fail closed. This is
a scoped evidence check, not the full Charter evidence-strength state machine.
A Gate does not create authority; receipts and verification do not turn a
proposal into permission or external AI into authority. Recovery does not renew
a grant. BOB, Difference Makers, full Gate integration and semantic carry-forward
remain outstanding.

DESIGNED/IMPLEMENTED as an independent offline checker; TESTED with synthetic
HTTP handler output and deliberately changed evidence. It is not integrated into
live Habitat, and its tests do not establish OBSERVED/VERIFIED task success.
Next: bounded exported-evidence trial, then a local model adapter under the
existing grant and execution-outcome contract. Domain-specific task correctness
requires its own independently specified acceptance criteria and verifier.

The optional local-model backend adds `local_model_attempted` before the generation
result; the checker supports that event form without attesting model byte identity.
