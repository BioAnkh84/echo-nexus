# Offline partial proposal assessment

`assessment.assess(proposal, now=...)` is a pure function. It does not import old
VE/Habitat code, read registries, access files/network, append receipts, run tools,
or integrate with live routes. It is the first data-contract slice of a future
adapter, not a completed Gate or enforcement layer.

Schema 1 accepts only proposal_id, action, resource, purpose, charter_sha256,
measurements and evidence plus schema_version. Identity strings are bounded to
512 characters. Measurements must contain rho, gamma_0 and delta only; evidence
metadata contains source_ref, observed_at and valid_until. Exact source policy
is the human-ratified Charter v1.5.5 pinned by SHA256.

Baseline rules transcribed from that artifact: confidence at least 0.70; gamma_0
is exactly integer 0 or 1; gamma_0=0 implies ABORT; delta greater than 0.40 implies
ABORT; 0.30 < delta <= 0.40 requests attention. Relational gamma is deliberately
excluded. Invalid or stale metadata produces unknown evidence. Evidence is stale
at valid_until; future observations are invalid. These timestamps are evidence
metadata, not grant expiry or an authenticated clock. `now` is explicit trusted
caller input for deterministic evaluation, not a proposal field.

Inputs remain supplied claims: a source reference or measurement value is not
proof of its truth. Missing inputs never default to consent. Extra approval,
caller-decision or evidence-truth fields are rejected. Valid supplied hard denials
remain ABORT even when evidence metadata is missing/stale. An ABORT is only this
non-executing function's assessment, not proof of an independently measured risk.

Even passing baseline measurements returns PAUSE: authority and full Gate/CS-state
are not evaluated. Every result explicitly says execution_authorized=false,
execution_attempted=false and evidence_truth_verified=false. There is no PROCEED
or implicit mapping from a legacy decision. Difference Makers explain the limited
assessment; they do not replace authenticated evidence or enforcement.

The separate legacy signal/contract documents reinforce evidence-versus-authority
separation but contain no authorization to inherit authority. The ratified Charter
wins over conflicting legacy threshold/default semantics. Old pipeline code and
uncommitted repositories remain untouched.

Tests cover exact thresholds, consent denial, expiry boundary, future timestamps,
nonfinite/bool/oversized numeric inputs, caller approval spoofing, policy mismatch,
reproducibility and non-mutation. No runtime compatibility or real-world evidence
acquisition is established. Next work must define a trusted measurement/authority
interface and full policy state before any executable adapter is considered.
