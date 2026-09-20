# Execution outcomes and receipts

Cipher chat, Vexis chat and the advisory handshake now require `receipt.append`
in the same applicable grant as their route action. Existing grants without it
are refused; this change does not provision or renew any grant. Other routes
retain their existing scopes and do not produce these receipts.

The constitutional reference remains the exact human-ratified v1.5.5 artifact
and hash in [BOUNDED_AUTHORITY.md](BOUNDED_AUTHORITY.md). A Gate determines
whether a boundary may open under applicable authority; it does not create
authority. These receipts record grant evaluation, with Gate measurement marked
`not_performed`. A proposal is not permission; a receipt is not approval.
External AI output remains evidence, never authority.

## HTTP outcomes

Successful exchanges retain their reply fields and add `execution` and `receipt`.
The latter contains a request ID and the last event's chain tip.

| Result | HTTP | Execution state | Transmission |
| --- | --- | --- | --- |
| Stub or provider returned; local writes returned | 200 | `completed_unverified` | `not_attempted` for stub, `response_received` for provider |
| Provider client initialization failed | 503 | `failed` | `not_attempted` |
| Provider request raised an error | 502 | `outcome_unknown` | `unknown` |
| Provider response has no usable text | 502 | `failed` | `response_received` |
| Receipt or memory I/O failed | 503 | `incomplete` | Earlier effects may have occurred |
| Authority expired, changed or was revoked | 403 | `incomplete` if exchange began | Earlier effects may have occurred |

All execution outcomes have `verification: not_performed`. HTTP 200 records
that the handler reached its completion point, not independent task success.
Provider errors are no longer stored as normal assistant replies. Error bodies
do not expose provider exception text. A timeout cannot prove non-transmission.

## Local evidence chain

`ECHO_NEXUS_ROOT/receipts/execution.jsonl` contains ordered JSON events with
sequence, UTC timestamp, request/event IDs, grant ID/fingerprint, subject,
purpose, route action, event details, `hash_prev` and `hash_self`. SHA-256 uses
sorted compact ASCII JSON, excluding `hash_self` when calculating that hash.
The first previous hash is 64 zeroes.

Events cover authority evaluation, generation attempt/result, outbound attempt,
memory append attempt/result, and response preparation or I/O interruption.
Memory hashes cover exact UTF-8 JSONL entry bytes, including their newline;
request hashes cover the raw HTTP body. The response hash covers the canonical
payload before adding its receipt reference. Actual client delivery is unknown.
The ledger omits raw message/reply text and bearer tokens. Grant metadata and
hashes can still be sensitive, and hashes do not conceal guessable inputs.

The append helper checks the existing chain under a nonblocking exclusive file
lock, refuses symlinked receipt directories/files and nonregular or nonprivate
ledger files, appends without truncating, and fsyncs the file and receipt
directory. Limits are 16 KiB per event and 8 MiB total. Contention, capacity or
integrity failure stops the exchange; automatic repair and rotation are absent.
The data root and its ancestors must remain under trusted operator control.

A pre-execution receipt failure prevents provider/memory effects. Failure after
an effect cannot undo it. A partial append remains in place and blocks later
appends. Revocation can leave a valid but unfinished chain: the server does not
mint fresh authority merely to finish the audit. No cross-file transaction,
exactly-once execution, crash-proof recovery or immutable audit store is claimed.

Read-only integrity verification:

```sh
python habitat/receipts.py /absolute/sandbox/receipts/execution.jsonl
python habitat/receipts.py /absolute/sandbox/receipts/execution.jsonl --expected-tip TRUSTED_TIP
```

Without a separately trusted tip, a valid-prefix truncation or a full chain
rewrite by the filesystem owner cannot be detected. Even an anchored chain
does not prove event truth, human approval, memory persistence or task success.
The verifier always reports `task_success_verified: false`. Recovery must
preserve damaged evidence and obtain applicable authority for subsequent work;
restoring data or a receipt never renews an expired or revoked grant.

## Evidence level and next work

DESIGNED and IMPLEMENTED for these three server routes. TESTED using temporary
fixtures, mocked providers, revocation/TTL cases and injected I/O failures.
INTEGRATED within this development server only. Live Habitat OBSERVED or VERIFIED
claims, real provider behavior and an independent task-success verifier are not
established by these tests. This is not the full Charter evidence-strength state
model. BOB, Difference Makers, cumulative disclosure accounting, full Gate
integration, durable trusted anchors and semantic carry-forward remain open.

Next: review this slice, then run a separately authorized finite loopback trial;
implement independent result verification before promoting task-success claims.
A local model adapter can follow with the same authority and outcome boundaries.
