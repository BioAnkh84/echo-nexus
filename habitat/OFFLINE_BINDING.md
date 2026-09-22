# Offline proposal/evidence/grant binding

`binding.bind` is an opt-in read-only library, not a route or executor. The caller
must provide operator-controlled record path/digest, source path, registry path,
credential, data root and explicit evaluation time separately from model content.
Never populate these arguments from a proposal or generated reply.

The partial assessment must have valid baseline measurements and current evidence
metadata. A separately provisioned record pins the canonical proposal digest,
measurements, evidence metadata and raw source SHA256. The checker acquires both
files itself through bounded regular-file descriptors, rejects final symlinks,
and checks metadata stability during reads. It checks the current registry before
reading evidence and again afterward, rejecting changed grant fingerprints.

Evidence paths are explicitly authorized by the operator calling this read-only
checker; the proposed action's grant does not itself authorize arbitrary file
reads. Paths are not taken from proposal text. Intermediate directory symlinks are
not prohibited; byte pinning is the content boundary. Sources are limited to 64 KiB.
Files can change after reading; returned digests describe the acquired snapshots.

Only proposals whose resource exactly equals the separately selected data root
are supported. The existing registry action/purpose/root checks are reused; no
per-file permission, custom condition, human identity proof or semantic scope
extension is inferred. Unsupported extra contract fields are rejected.

`now` is an explicit evaluation time for offline reproducibility, not a trusted
live clock. Registry state is reread, but this is not execution-time authorization
and it cannot guarantee validity after acquisition. A future executor must obtain
fresh authority/evidence and evaluate full Gate/CS policy at its own boundary.

Success reports offline_binding_consistent with PAUSE and execution_authorized=false.
It means only that the pinned record, acquired source bytes and evaluated registry
scope match. Acquisition is separate from model text, but semantic evidence truth
is not independently verified. An operator pin is a trust input, not authenticated
human identity. The nested partial assessment still marks authority unevaluated;
the outer result separately reports the limited registry match.

No original Habitat/VE code is imported, no log or memory is written, and no
receipt is promoted to approval. Tests use synthetic local fixtures. No live
integration or whole-Charter enforcement is claimed.

Next design stage: [Measurement acquisition contract](MEASUREMENT_ACQUISITION_CONTRACT.md). Its unresolved policy requirements do not change this module's PAUSE/no-execution behavior.
