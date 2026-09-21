# Echo Nexus
Local AI Habitat for Cipher & Vexis
A trust-gated operating environment designed for autonomous collaboration, memory-anchored reasoning, and ethical AI deployment.

## Linux local development (Python 3.12)

The Flask development server is for local development only. It is not a
production server or an authenticated multi-user service. The supported launcher
binds only to 127.0.0.1:5000, with debug and the reloader disabled. Do not expose
this app through another server, proxy, tunnel, or Flask CLI binding.

Create a dedicated environment from the repository root when installation is
explicitly authorized:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If venv reports missing ensurepip, your Linux Python installation needs its
matching venv support package before this step can succeed. The manifest pins
only direct dependencies (Flask and openai); it is not a hash-locked transitive
set.

Before the authority changes, Linux runtime verification succeeded in a Python 3.12.3 virtual environment:
all 12 Tests/test_linux_runtime.py tests passed with no skips. The one-shot
launcher started with debug mode off and bound to 127.0.0.1:5000.
GET /healthz returned {"status": "ok"} without OPENAI_API_KEY being provided.
The process was stopped after that bounded check. This historical result is not
a live verification of the new authority contract.

One-shot startup from any directory (replace the path with your checkout):

```sh
sh /absolute/path/to/echo-nexus/habitat/run_cipher_server.sh
```

The launcher uses .venv/bin/python and exec, does not install anything or restart,
and propagates signals and exit status. It and the Python entry point do not
load .env files. No data directory is created at startup.

```sh
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:5000/healthz
```

/healthz returns only {"status":"ok"}, without memory access, writes, or backend
calls. /echo/status remains a legacy static status response; neither endpoint
proves backend readiness. Console access performs no automatic memory fetch.

### Capability configuration and bounded grants

Capability settings are read once at process startup. Flags accept only literal
1; all other values leave the capability disabled. These switches do not grant
authority. Every protected request also needs an operator-provisioned bounded
grant. See [Bounded authority](docs/BOUNDED_AUTHORITY.md) for provisioning, action
scopes, request headers, revocation and implementation limits.

| Environment variable | Default | Meaning |
| --- | --- | --- |
| ECHO_NEXUS_ROOT | unset (no data root) | Explicit absolute POSIX data-root path; relative and Windows drive/UNC paths are rejected. |
| ECHO_NEXUS_GRANTS_FILE | unset | Absolute path to the private operator-provisioned grant registry; missing or invalid grants fail closed. |
| ECHO_NEXUS_ENABLE_DATA_ROUTES | 0 | Enable protected import, state, memory, log, chat, and handshake routes. Requires an explicit root. |
| ECHO_NEXUS_ENABLE_OPENAI | 0 | Enable external capability for submitted messages; a grant must also permit external.openai; client is created lazily on the first model request. |
| ECHO_NEXUS_SEND_MEMORY_TO_OPENAI | 0 | Enable stored-context capability; a grant must also permit memory.export; also requires data routes and OpenAI enabled. |
| OPENAI_API_KEY | unset | SDK credential required only for enabled external calls; supply securely through the process environment, never commit it. |

The configured model remains gpt-4.1-mini. No credentials are needed for health
checks or disabled-backend operation. Enabling and authorizing external calls can transmit the
submitted message and persona prompt and incur charges; memory context is
excluded unless the separate memory permission is enabled. API errors return a
generic response rather than exposing SDK error details.

Protected-route opt-in example, using a dedicated synthetic sandbox:

```sh
ECHO_NEXUS_ROOT=/absolute/path/to/synthetic-sandbox \
ECHO_NEXUS_ENABLE_DATA_ROUTES=1 \
ECHO_NEXUS_GRANTS_FILE=/absolute/path/to/private/operator-grants.json \
sh /absolute/path/to/echo-nexus/habitat/run_cipher_server.sh
```

Protected routes now require bearer authentication and an applicable bounded
grant. Imports accept only explicitly granted filenames under the dedicated
`imports` directory, not arbitrary paths. Chat/log/handshake still write memory
as part of their documented action scope. The data root must remain under trusted
operator control; this is not a general filesystem sandbox. Existing data is
never migrated automatically. Memory streams remain under `memory/streams`.

External calls additionally require the OpenAI switch, server-side SDK credential
and `external.openai` grant action. Stored context also requires the memory
switch and `memory.export` action. Restart to change capability settings; registry
revocation and expiry are reevaluated without restart. The console accepts grant
token/purpose inputs without browser storage; missing grants cannot use it to
access memory or chat.

### Verification without live data or API calls

```sh
PYTHONPYCACHEPREFIX=/tmp/echo-nexus-test-cache \
.venv/bin/python -m unittest discover -s Tests -p 'test_*.py' -v
```

Tests use synthetic temporary fixtures and mocked backend responses. Tests that
need Flask are skipped explicitly when it is absent; no dependency is installed
by the test suite. No listening service is started. The CLI, Windows launcher,
and dashboard are separate legacy entry points and are not changed by this port.

### Execution evidence

Chat and handshake additionally require `receipt.append`. They return typed
execution outcomes and hash-linked receipt references; returned output remains
unverified. Provider failures return 502/503, and receipt failures stop execution
with possible partial effects. See [Execution receipts](docs/EXECUTION_RECEIPTS.md)
for scope, grant compatibility, verification and recovery limits.

An independent [exchange evidence checker](docs/EXCHANGE_VERIFICATION.md) compares
a captured response and memory snapshot against a supplied receipt-chain tip.
It reports evidence consistency while keeping authority and task success unverified.

The optional [local model adapter](docs/LOCAL_MODEL.md) uses an explicitly granted,
finite GPU worker and preserves typed outcomes and exchange receipts.

[Session context](docs/SESSION_CONTEXT.md) is optional and requires `local.context`;
it never implicitly loads older Habitat memory.
