# Bounded authority for the Linux development server

This implementation requires an operator-provisioned grant before a protected
HTTP route can read or mutate data. Environment switches enable capabilities;
they do not grant permission. The grant is evaluated against the proposed route
and configured data root. Gate measurements and receipts cannot create grants.

The constitutional reference is the human-ratified Echo Root OS Charter v1.5.5,
artifact `Echo_Root_OS_Charter_v1_5_5_Ratified_Baseline.docx`, SHA-256
`206ffa82ad3feebe54648ebce8cb7ef8c89e11b0cad78b4795adfea1dfe68c51`.
This document is an implementation contract, not a Charter amendment or a claim
of complete constitutional enforcement. Articles III, VIII, XI, XVII, XIX and
XXI–XXIII inform this first boundary implementation.

## Trust boundary

The local operator provisions the registry outside the repository, data root,
and any served directory. The server never creates or renews grants. Set
`ECHO_NEXUS_GRANTS_FILE` to its absolute path. The registry must be a regular,
non-symlink file owned by the server's effective Unix user, with no group/other
permissions (normally mode 0600). Keep its parent directories, the data root,
imports and memory directories under trusted operator control. This is a trusted
local development setup, not protection against another process with that same
Unix identity, a hostile filesystem owner, or a compromised operator account.

A valid bearer token establishes possession of an operator-provisioned
credential. It does not independently authenticate the named human or establish
that a written human approval reference is truthful. Human authorization and
secure provisioning remain the operator's responsibility. The service has no
public grant-creation, delegation, renewal or permission-request endpoint.

Generate each token from at least 32 random bytes (for example Python's
`secrets.token_urlsafe(32)`). Store only its lowercase SHA-256 in the registry;
deliver the raw token privately to its intended subject. The accepted token
encoding is 43–128 URL-safe alphanumeric, underscore or hyphen characters.
Never put a real token in a URL, command history, committed file or receipt.

## Registry schema

The following is an intentionally revoked example with a placeholder hash and
illustrative dates. It grants nothing as written. The operator must set real
scope and timestamps from a separately authorized grant, not merely copy it.

```json
{
  "schema_version": 1,
  "charter_sha256": "206ffa82ad3feebe54648ebce8cb7ef8c89e11b0cad78b4795adfea1dfe68c51",
  "grants": [
    {
      "grant_id": "example-grant",
      "human_grant_reference": "reference-to-explicit-human-grant",
      "subject": "example-local-client",
      "audience": "echo-nexus",
      "purpose": "synthetic-check",
      "data_root": "/absolute/path/to/synthetic-sandbox",
      "token_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "issued_at": 1790000000,
      "expires_at": 1790000600,
      "revoked": true,
      "actions": ["cipher.log"],
      "import_files": []
    }
  ]
}
```

`issued_at` and `expires_at` are integer Unix seconds; the current clock must be
within `[issued_at, expires_at)`. `revoked` must be explicitly false. The audience
must be `echo-nexus`. The data root must exactly equal the configured absolute
path. Unknown actions, duplicate grant IDs, ambiguous matching tokens, missing
registry files and malformed applicable grants fail closed. Duplicate JSON keys
and nonstandard numeric constants are rejected throughout the registry. There is no wildcard action.

Every protected request supplies `Authorization: Bearer <token>` and
`X-Echo-Purpose: <exact granted purpose>`. Requests without applicable authority
return 403 with `decision: ABORT`. JSON writes require an object and bodies are
limited to 1 MiB. Unknown routes/methods do not gain authority from an existing
grant. Public health/status/console content requires no credentials and does not
read the registry or memory just to render.

The console has token and purpose inputs, with a Clear grant button. It sends
headers only on explicit operations and does not persist credentials in browser
storage. Chat identifies the subject from the grant, not a JSON `user` claim.
Refresh Log is a separate operation requiring its own action permission.

## Action scopes

| Action | Permitted operation within the bound data root |
| --- | --- |
| `cipher.log` | Append caller event data to Cipher memory; caller author labels are data, not authority. |
| `cipher.chat` | Generate a Cipher response and append the submitted message and response to Cipher memory. |
| `vexis.chat` | Generate a Vexis response and append both sides to Vexis memory. |
| `cipher.memory.read` / `vexis.memory.read` | Return up to 200 entries from the respective memory stream. This grants access to that stream, not per-user isolation. |
| `cipher.state.read` | Read imported Cipher state metadata. |
| `cipher.import` / `vexis.import` | Read and return an allowlisted JSON seed and replace the corresponding in-process seed state. |
| `echo.handshake` | Exchange advisory text with Vexis and append the exchange to Vexis memory. |
| `local.context` | Additional permission to supply bounded conversation context to local chat. |
| `local.generate` | Additional permission for finite inference with the operator-configured local model. |
| `receipt.append` | Additional permission to append execution receipts; required for both chat routes and handshake. |
| `external.openai` | Additional permission for chat/handshake text and persona context to be sent to OpenAI; also requires its capability switch. |
| `memory.export` | Additional permission to include recent stored chat context; also requires both external permission and the memory capability switch. |

The external destination is fixed to `https://api.openai.com/v1` and the model
remains `gpt-4.1-mini`; `OPENAI_BASE_URL` cannot silently choose another provider.
SDK retries are disabled and the timeout is 15 seconds. A server configured to
use an external backend refuses requests lacking external permission rather
than silently changing execution mode. The same applies to configured memory
export without a `memory.export` grant. Keep external switches off for local-only
synthetic work. These controls are not BOB or cumulative disclosure accounting.

## Handshake and imports

A handshake must additionally have `from` equal to the grant subject, `to` equal
to `Vexis@EchoNexus`, a nonempty string `message`, and this bounded context:

```json
{"scope": "echo.handshake", "ttl": 1790000300}
```

That object goes in `purpose_token`. Its integer TTL must be in the future and
no later than the grant expiry. Any legacy `consent` name is ignored as authority.
The authenticated external subject remains the sender; it is not relabeled as
the human steward. Replies are advisory and explicitly unverified; fabricated
resonance/drift measurements were removed.

Imports now accept `{"file":"seed.json"}`, not a caller-supplied `path`.
The filename must be explicitly in the grant's `import_files`, use the accepted
simple `.json` naming pattern, and exist under `ECHO_NEXUS_ROOT/imports`.
Directory-descriptor reads reject symlink redirection, including a symlinked
imports directory, and accept only regular files containing a JSON object of
at most 1 MiB. Existing legacy seeds are not moved automatically. Operators must
approve seed contents and placement; filename permission is not a content hash.

## Revocation and recovery

The registry is reread at admission and immediately before helper-mediated
memory reads/writes, outbound calls (after client setup), seed-state replacement
and successful protected HTTP responses. Responses use `Cache-Control: no-store`
to prevent ordinary browser/proxy caching of protected output. Removing a grant,
revoking it, expiring it, or changing its content prevents subsequent checks
from succeeding. Update registries by atomic replacement with private permissions
to avoid transient partial JSON. A changed grant cannot silently replace the
permission snapshot within an active request. The shorter handshake TTL is also
rechecked before side effects.

A check and a side effect are not a single atomic transaction: this does not
cancel an in-flight provider request or undo a completed operation. Revocation
between operations can leave partial effects, such as an external call completed
before a subsequent memory append is refused. Client retries can repeat an
operation while its grant remains valid; one-use quotas and idempotency are not
implemented. Expiry depends on a trustworthy host clock. Restoring an old registry
can restore still-valid credentials; an anti-rollback revocation store is future
work. Operators must not restore historical grants as part of data recovery.

Seed parsing restores data only. It does not restore grants, prove semantic
compatibility, or renew authority. Renewal is a new explicit operator action.

## Evidence and remaining work

DESIGNED and IMPLEMENTED: grant admission and the named side-effect checks in
this Linux server. TESTED: synthetic validator and Flask test-client cases,
including denial, expiry/revocation, subject binding, external-action separation
and confined imports. INTEGRATED: the module is wired into these HTTP handlers
only. OBSERVED/VERIFIED for the live Habitat or an end-to-end constitutional
system are not established by this test suite.

Memory entries record grant ID, authenticated subject and purpose separately
from caller event labels. Chat and handshake now also use a separately authorized
hash-linked receipt chain and typed outcomes; see [Execution receipts](EXECUTION_RECEIPTS.md).
Receipts do not establish approval or independently verified success. Other routes
retain their existing behavior. BOB, cumulative-disclosure accounting, semantic
recovery, independent result verification, full Gate/Redivous integration and
Linux filesystem isolation remain follow-up work. HTTP 200 must not be read as
independently verified completion of a task.

Run all tests with the configured virtual-environment Python:

```sh
.venv/bin/python -B -m unittest discover -s Tests -p 'test_*.py' -v
```

No live data, real provider calls or listening service is required by these tests.
The legacy CLI, Windows launchers and separate larger Habitat are outside this
HTTP contract. Do not infer that those entry points gained these controls.
