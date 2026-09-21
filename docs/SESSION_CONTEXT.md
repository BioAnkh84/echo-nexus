# Explicit local session context

Local Cipher and Vexis chat accept an optional `context` array only with the
additional `local.context` grant action. Each entry is exactly `{role, content}`.
At most three complete user/assistant pairs, alternating in that order, and
4096 total content characters are allowed. Invalid roles, order, shape or size
are rejected before execution. External and handshake routes reject this field.

The caller supplies context; the server does not read historical memory for this
feature. The bounded terminal launcher holds only completed exchanges from its
current invocation and evicts oldest complete pairs to stay within the bounds.
Starting a new launcher does not restore context or renew any prior grant.

Context is untrusted message data, not a system instruction, approval or authority.
A caller holding this action could supply invented dialogue: provenance is not
authenticated. The worker adds its fixed system instruction separately. Grant
permission is checked at admission and rechecked before launching with nonempty
context. Existing grant-fingerprint checks prevent mid-request scope changes.

`local_model_attempted` receipts now include `context_entries` and `context_sha256`.
The existing independent verifier checks chain/exchange consistency; it does not
independently verify supplied context content or model compliance. The worker's
2048 total input-token bound still applies; long combined inputs fail rather than
silently exceeding it. Context does not add tools, personal memory ingestion or
cross-session access. Existing chat memory writes remain part of chat authority.

Validation includes separate-permission denial, exact forwarding/hash recording,
no history-file read, invalid context rejection and grant changes before launch.
GPU contextual recall remains a host-terminal trial, not established by mocks.
