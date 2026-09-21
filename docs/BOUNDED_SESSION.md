# Bounded operator-run terminal session

`habitat/session.py` maintains the terminal session launcher in the repository.
It starts a single-process loopback HTTP server on an OS-selected port, provisions
a temporary bounded grant for the explicitly authorized session, and sends chat
requests through the same authority, worker, receipt and verification code as
other clients. It does not install a service, download a model or load older
Habitat memory.

Run from a Linux terminal with CUDA device access, using the Python environment
containing the local-model dependencies and Flask (see LOCAL_MODEL.md):

```sh
/path/to/gpu-environment/bin/python -B habitat/session.py \
  --output-dir /absolute/existing/session-output-directory \
  --model /absolute/existing/local-model-directory \
  --grant-reference 'reference to the operator authorization for this session' \
  --expected-commit REVIEWED_COMMIT_SHA
```

The commit must match HEAD and the checkout must be clean. This prevents accidental
execution of a changed checkout; it does not authenticate review or the operator's
reference. A reference string is not itself human approval. Run only within the
operator's actual authority to use the model and save these messages. The launcher
binds the temporary grant to a new data root and fixed local-operator subject.
It never loads or renews an earlier session's grant.

The chosen output directory must already exist and be authorized for these writes.
Each session creates a unique private (0700) subdirectory. Messages, replies,
receipts and the final report remain there. Credentials live in a temporary private
subdirectory and are removed on normal cleanup; raw tokens are never printed.
Keep the evidence directory outside the repository so retained private messages
do not enter Git. Output-path ancestors remain under trusted operator control.

## Limits and exit behavior

- Five input attempts, with at most five submitted messages; blank or oversized
  input also consumes an attempt. `/quit` or EOF exits.
- Ten-minute grant, with admission stopping 190 seconds early to reserve the
  worker's time budget. Both wall-clock expiry and a monotonic session deadline
  bound admission. No silent extension or retry.
- Current session context only: at most three completed exchanges and 4096
  characters; oldest complete pairs are evicted with a notice. The model's total
  input-token limit still applies.
- Worker failure or non-200 HTTP response stops the session and returns exit 1.
  Partial effects are preserved. No error reply is promoted to completed success.
- Ctrl-C and SIGTERM enter shutdown. Repeated signals are ignored during cleanup;
  an in-flight bounded worker may take up to its timeout to finish. SIGKILL, power
  loss and OS failure cannot guarantee cleanup.
- Cleanup attempts grant revocation and registry removal, then server shutdown
  even if grant-file cleanup fails. It verifies completed exchanges only after
  the server stops. Evidence failures preserve files and return exit 1.

The report distinguishes `exchange_evidence_consistent` from task success. Its
tip comes from the stopped-server snapshot, not a separately trusted anchor.
It cannot prove event truth, human authority, model correctness or context origin.
If interrupted before a response is captured, receipts/memory may contain an
incomplete exchange; preserve them rather than treating missing responses as proof
of no effects. Failure during startup or report writing may leave evidence without
a final report; a report is not fabricated on those paths.

## Synthetic lifecycle check

```sh
/path/to/python-with-flask -B habitat/session.py --self-test \
  --output-dir /absolute/existing/test-output-directory \
  --grant-reference 'authorization for this synthetic lifecycle check'
```

Self-test explicitly selects the local stub, runs one fixed message, and needs no
GPU or model. It allows an uncommitted development checkout and records that fact;
interactive mode does not. It cannot establish GPU behavior. Unit tests include
real loopback sessions with mocked generation, normal quit/EOF, interruption,
timeout of input, five-attempt/context limits, generation failure and evidence
failure. The separate previously observed host GPU trials remain scoped evidence
for the underlying model path, not a claim of full constitutional enforcement.
