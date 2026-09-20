"""Execution reports preserve uncertainty; no result here is self-verified."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ExecutionOutcome:
    state: str
    backend: str
    transmission: str
    reason: str | None = None
    verification: str = "not_performed"

    def as_dict(self):
        return asdict(self)


class BackendFailure(Exception):
    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(outcome.reason)
