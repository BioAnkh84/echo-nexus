# Bounded local model adapter

The Linux HTTP server can opt into the existing local Safetensors model with:

```sh
export ECHO_NEXUS_ENABLE_LOCAL_MODEL=1
export ECHO_NEXUS_LOCAL_MODEL_PATH=/absolute/path/to/model
```

Keep `ECHO_NEXUS_ENABLE_OPENAI` off. Enabling both backends or omitting the model
path refuses startup. Existing data-root and private grant requirements remain.
The configured model directory and its parents must be trusted operator-controlled
files. `local.generate` grants use of that configured model; no model download or
per-request model selection is supported. Model byte identity is not attested.

Cipher chat, Vexis chat and handshake additionally require `local.generate` and
`receipt.append` in the same applicable grant. No grant is automatically updated.
Admission, receipt appends, worker launch, memory writes and successful response
disclosure recheck authority. A local backend capability switch is not permission.

Each request launches a finite GPU worker using the server's Python interpreter.
The worker uses local-only files, Safetensors, `trust_remote_code=False`, and an
isolated Python invocation with a minimal environment excluding inherited API
keys and proxies. It imports neither Habitat nor its memory/tool code. Offline
library settings are not an OS network or filesystem sandbox.

Only the current message and a small advisory system prompt reach the model.
Stored memory export is not implemented for this backend. The usual authorized
chat memory writes happen after generation. Limits: 4096 input characters, 2048
input tokens, 64 new tokens, one worker per server process, and a 180-second
subprocess timeout. CUDA is required; there is no CPU or cloud fallback. Multiple
server processes could each launch a worker, so use a single process for this
prototype. The model reloads each request; persistent serving is future work.

Use the tested Python 3.12 stack: torch 2.8.0 CUDA 12.8 build, transformers 4.56.2,
accelerate 1.10.1, and Flask 3.1.2. GPU packages remain optional and are not added
to the default server requirements. Host-terminal access is needed where an
agent sandbox hides NVIDIA device files.

Receipts identify `local_model`, add `local_model_attempted` with configured path
and input hash, and retain `completed_unverified`. The offline verifier recognizes
the new event form. `transmission: not_attempted` refers to external-provider
transmission, not absence of local computation. Worker failures return typed 503
errors; provider exception text and ordinary error replies are not recorded as
chat. A timeout terminates the direct worker. Revocation cannot undo in-flight
computation but prevents subsequent checks from succeeding. No result is promoted
to independently verified task success or human approval.

Validation covers worker denial, environment isolation, timeout, malformed output,
lock contention, revocation at launch, no external/history calls, and independent
verification of mocked local exchanges. These tests do not establish integrated
GPU operation. The earlier standalone GPU smoke test established only that the
existing weights can generate on the host's RTX 4090. A bounded synthetic HTTP
GPU trial is required to observe the combined path. No live Habitat deployment,
BOB, full Gate enforcement or semantic recovery is claimed.
