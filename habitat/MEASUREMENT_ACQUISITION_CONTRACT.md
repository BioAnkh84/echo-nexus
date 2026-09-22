# Measurement acquisition and full Gate boundary: design contract

Status: DESIGNED ONLY. This document introduces no runtime policy, threshold,
grant, collector or executable integration. `assessment.py` and `binding.py`
remain partial and non-executing; their successful paths remain PAUSE.

Authority baseline: human-ratified Echo Root Charter v1.5.5, SHA256
`206ffa82ad3feebe54648ebce8cb7ef8c89e11b0cad78b4795adfea1dfe68c51`.
Articles II, III, V, XIV and XVII provide the measurement, consent, drift,
evidence-quality and separation requirements. Article XI restricts carry-forward
to a still-valid grant. The artifact hash was rechecked during this design review.

## Responsibility boundaries

| Role | Produces | Must not do |
| --- | --- | --- |
| Model/proposer | Action, resource, purpose and proposed plan | Supply authoritative approval, collector results, CS-state or evidence truth flags |
| Operator-configured collector | Bounded observation and acquisition provenance | Infer permission from availability, write target state, or choose its own trust root |
| Gate measurement component | Versioned rho, gamma_0, delta and CS-state with evidence references | Execute, authenticate itself by declaring confidence, or silently substitute unknown values |
| Authority resolver | Applicable registry grant under actual scope/conditions | Manufacture permission from measurements, notes, receipts or task similarity |
| Redivous/enforcement | Effective thresholds, CS modulation, decision and reasons | Alter Gate measurements or proceed from missing/invalid policy |
| Future bounded executor | One specifically authorized effect | Reuse an old binding as permanent authorization |
| Independent verifier | Claim-specific observed-result verdict | Turn hash agreement or receipt existence into semantic success |

Grant resolution supplies consent/scope evidence used to derive gamma_0; this
relationship is not permission for the proposer to set gamma_0. Passing Gate
measurements alone do not authorize anything. Relational gamma_r may shape
presentation, never permission, threshold evaluation or classification.

## Operator-selected acquisition profile

A future profile must pin: collector identity and code/version digest; allowed
observation type; exact source selector and permitted read scope; source identity
verification method; maximum bytes/time; parser/schema version; required evidence
age; time source and clock-error policy; policy/Charter fingerprint; and rejection
behavior. These are operator-controlled inputs, not model-selected arguments.
A profile's existence is configuration, not an authenticated human grant.

Start with one local immutable synthetic observation. Do not add network fetches,
archive traversal, model-generated metrics or live hardware actions in that slice.
The existing offline binder's explicit `now` is a reproducibility input, not a
trusted clock; future live acquisition needs a separately reviewed clock policy.

## Proposed observation envelope

All fields are design requirements until a schema and collector implement them:

- Schema version, observation ID, exact proposal digest and claim being observed.
- Collector identity, code/version digest, acquisition-profile digest.
- Source identifier and identity-verification result; raw snapshot digest, size
  and content-addressed evidence reference. Paths must not originate in model text.
- Acquisition start/end, observation time, validity bound, clock provenance and
  uncertainty. Freshness validity and grant expiry remain separate conditions.
- Parser version and result; integrity check method/result; scope and relevance
  result; contradiction references; receipt support and replay instructions.
- Measurement derivation method/version and input digests. No unexplained numeric
  confidence, caller `proven=true`, or success flag is accepted as a measurement.
- Explicit unknowns and failure reasons; no secrets or unnecessary private payload
  in public reports. Any disclosure needs its own applicable authority and bounds.

An independently acquired source means the collector read the selected source,
not that the source is truthful or independent of the proposer. The profile must
state source control/independence assumptions. Hashes need a trusted reference to
support stronger integrity claims; they cannot authenticate their own provenance.

## Baseline versus unresolved policy

The ratified baseline is rho >= 0.70; binary gamma_0, with zero requiring ABORT;
delta <= 0.30 potentially admissible only if all other gates pass;
0.30 < delta <= 0.40 requires PAUSE; delta > 0.40 requires ABORT.
These are thresholds, not measurement algorithms.

The following are unresolved and block any full Gate/PROCEED implementation:

1. Rho derivation: weighting or aggregation of plan validity, evidence strength,
   source integrity, freshness, compatibility, consistency, contradiction risk
   and rollback availability. No invented formula or universal scalar is supplied.
2. Delta derivation: calibrated definition of path instability for the specific
   action/environment, with source evidence and reproducible computation.
3. CS policy: admissible states, measurement method, transition table, prohibited
   transitions, state persistence/recovery, threshold modulation, override order
   and version compatibility. CS labels such as CS0 must not be assigned meanings
   or numeric effects without the approved policy source.
4. Evidence prerequisites: claim-specific freshness, integrity, receipt and
   relevance rules, including how unknowns affect assessment.
5. Trusted identity/time roots and operating assumptions, including offline and
   recovery behavior. No implicit inherited authority from restored state.

No complete CS transition/modulation table was located in this bounded review of
the ratified artifact, legacy redivous.py, self_proposal.py, policy.ve.psl and
ve_habitat_constitution.py. This is not proof that no such policy exists elsewhere.
Locate and reconcile prior policy before proposing a new one. A new policy cannot
be ratified by this specification or by passing tests.

## Enforcement and effect-boundary requirements

Gate output must bind the proposal digest, evidence/profile versions, policy
identity, measured values and measurement timestamp. Enforcement records effective
thresholds and reasons separately, without modifying those values. Missing CS
policy cannot be represented as a default healthy state.

An implemented enforcement component returning invalid/undefined/no decision must
block execution and enter SAFE_MODE with a failure record, per Article XVII.
That requirement is distinct from a design-time partial offline assessment that
explicitly remains PAUSE. Do not claim the current offline functions implement
SAFE_MODE enforcement.

Before any later effect, reevaluate grant applicability and evidence freshness,
confirm proposal/policy/resource identity and reject changed scope or state.
Document unavoidable race windows; snapshot binding alone is not an atomic
check-and-execute mechanism. No executor is authorized or implemented here.

## Acceptance matrix for future implementation

| Case | Required result |
| --- | --- |
| Model substitutes collector/profile/approval fields | Reject untrusted authority inputs; no effect |
| Source bytes match but source identity is unknown | Preserve limited consistency; no promotion to proven |
| Stale/future observation, clock uncertainty or missing freshness policy | Explicit unknown/blocked outcome under reviewed policy |
| Valid grant expires or is revoked after measurement | Recheck rejects effect |
| Grant remains valid but action/resource/purpose changes | Reject prior binding; reassess applicability |
| Policy/CS version changes between assessment and effect | Reject old assessment; reconcile semantics |
| Missing/invalid CS-state or undefined enforcement result | No default PROCEED; enforcement failure enters SAFE_MODE |
| gamma_r changes while all governing inputs stay fixed | Permission/classification unchanged |
| Receipt exists but effect differs from claim | Verification does not report success |
| Same input snapshots/profile/policy | Reproducible measurements; authority still separately checked |

Recommended next deliverable: a read-only inventory of prior CS/measurement policy
artifacts and their version/provenance, followed by a proposed profile for one
synthetic collector. No production executor until the unresolved policy inputs
and enforcement contract have independently reviewable answers.
