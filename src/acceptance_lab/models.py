from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

ALLOWED_DIMENSIONS = {"mechanism", "quality", "authority", "economics"}


class ModelValidationError(ValueError):
    """Raised when a scenario or candidate record violates the local contract."""


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ModelValidationError(f"{field_name} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class CheckSpec:
    id: str
    type: str
    dimension: str
    threshold: float = 1.0
    hard_gate: bool = False
    params: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CheckSpec":
        check_id = _require_string(value.get("id"), "check.id")
        check_type = _require_string(value.get("type"), f"check[{check_id}].type")
        dimension = _require_string(
            value.get("dimension"), f"check[{check_id}].dimension"
        )
        if dimension not in ALLOWED_DIMENSIONS:
            allowed = ", ".join(sorted(ALLOWED_DIMENSIONS))
            raise ModelValidationError(
                f"check[{check_id}].dimension must be one of: {allowed}"
            )
        threshold_raw = value.get("threshold", 1.0)
        if not isinstance(threshold_raw, (int, float)):
            raise ModelValidationError(f"check[{check_id}].threshold must be numeric")
        threshold = float(threshold_raw)
        if not 0.0 <= threshold <= 1.0:
            raise ModelValidationError(
                f"check[{check_id}].threshold must be between 0 and 1"
            )
        params = value.get("params", {})
        if not isinstance(params, dict):
            raise ModelValidationError(f"check[{check_id}].params must be an object")
        # A check must declare a non-empty subject.
        #
        # Every list-valued parameter a scorer reads -- `facts`, `evidence_ids`,
        # `tools` -- is the subject the check is about. An empty one asserts nothing,
        # and the scorers then divide by a zero denominator and report 1.000: a check
        # that demands nothing is trivially satisfied and looks in the record exactly
        # like a check that was met. That is the same vacuous truth as an empty
        # candidate subject, arriving from the other side.
        #
        # It is refused here, at the contract, rather than in each scorer, because it
        # is a defect in the scenario rather than in the run. A malformed check is not
        # a candidate's failure to score against, and the scorers already raise on
        # malformed params (see `_abstention_match`, `_max_metric`). Refusing it here
        # also keeps the fix out of the thirteen locked behaviours: no scorer revision
        # moves for an input that can no longer reach a scorer.
        for param_name, param_value in params.items():
            if not isinstance(param_value, list):
                continue
            # Blank entries count as absent, because `_params_list` discards them:
            # `{"facts": ["  "]}` reaches the scorer as an empty requirement and would
            # otherwise slip past this rule with the vacuous score intact.
            if not [
                item
                for item in param_value
                if not isinstance(item, str) or item.strip()
            ]:
                raise ModelValidationError(
                    f"check[{check_id}].params.{param_name} is empty; a check must "
                    "declare a non-empty subject, because an empty one is satisfied "
                    "by any candidate at all"
                )
        hard_gate = value.get("hard_gate", False)
        if not isinstance(hard_gate, bool):
            raise ModelValidationError(f"check[{check_id}].hard_gate must be boolean")
        return cls(
            id=check_id,
            type=check_type,
            dimension=dimension,
            threshold=threshold,
            hard_gate=hard_gate,
            params=params,
        )


@dataclass(frozen=True)
class Scenario:
    schema_version: str
    id: str
    version: str
    title: str
    workload: str
    description: str
    inputs: Mapping[str, Any]
    checks: tuple[CheckSpec, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Scenario":
        schema_version = _require_string(
            value.get("schema_version", "1"), "scenario.schema_version"
        )
        scenario_id = _require_string(value.get("id"), "scenario.id")
        version = _require_string(value.get("version"), f"scenario[{scenario_id}].version")
        title = _require_string(value.get("title"), f"scenario[{scenario_id}].title")
        workload = _require_string(
            value.get("workload"), f"scenario[{scenario_id}].workload"
        )
        description = value.get("description", "")
        if not isinstance(description, str):
            raise ModelValidationError(
                f"scenario[{scenario_id}].description must be a string"
            )
        inputs = value.get("inputs", {})
        metadata = value.get("metadata", {})
        checks_raw = value.get("checks")
        if not isinstance(inputs, dict):
            raise ModelValidationError(f"scenario[{scenario_id}].inputs must be an object")
        if not isinstance(metadata, dict):
            raise ModelValidationError(
                f"scenario[{scenario_id}].metadata must be an object"
            )
        if not isinstance(checks_raw, list) or not checks_raw:
            raise ModelValidationError(
                f"scenario[{scenario_id}].checks must be a non-empty list"
            )
        checks = tuple(CheckSpec.from_dict(item) for item in checks_raw)
        ids = [check.id for check in checks]
        if len(ids) != len(set(ids)):
            raise ModelValidationError(
                f"scenario[{scenario_id}] contains duplicate check ids"
            )
        return cls(
            schema_version=schema_version,
            id=scenario_id,
            version=version,
            title=title,
            workload=workload,
            description=description.strip(),
            inputs=inputs,
            checks=checks,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Citation:
    id: str
    supports: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Citation":
        citation_id = _require_string(value.get("id"), "citation.id")
        return cls(
            id=citation_id,
            supports=_string_list(value.get("supports", []), f"citation[{citation_id}].supports"),
        )


@dataclass(frozen=True)
class TrajectoryStep:
    seq: int
    tool: str
    action: str
    effect: bool = False
    effect_id: str | None = None
    verifies: tuple[str, ...] = ()
    receipt: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TrajectoryStep":
        seq = value.get("seq")
        if not isinstance(seq, int) or seq < 1:
            raise ModelValidationError("trajectory.step.seq must be a positive integer")
        tool = _require_string(value.get("tool"), f"trajectory[{seq}].tool")
        action = _require_string(value.get("action"), f"trajectory[{seq}].action")
        effect = value.get("effect", False)
        if not isinstance(effect, bool):
            raise ModelValidationError(f"trajectory[{seq}].effect must be boolean")
        effect_id = value.get("effect_id")
        if effect_id is not None and not isinstance(effect_id, str):
            raise ModelValidationError(f"trajectory[{seq}].effect_id must be a string")
        receipt = value.get("receipt")
        if receipt is not None and not isinstance(receipt, str):
            raise ModelValidationError(f"trajectory[{seq}].receipt must be a string")
        return cls(
            seq=seq,
            tool=tool,
            action=action,
            effect=effect,
            effect_id=effect_id.strip() if isinstance(effect_id, str) and effect_id.strip() else None,
            verifies=_string_list(value.get("verifies", []), f"trajectory[{seq}].verifies"),
            receipt=receipt.strip() if isinstance(receipt, str) and receipt.strip() else None,
        )


@dataclass(frozen=True)
class CandidateOutput:
    schema_version: str
    answer: str
    facts: tuple[str, ...]
    citations: tuple[Citation, ...]
    abstained: bool
    trajectory: tuple[TrajectoryStep, ...]
    metrics: Mapping[str, float]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CandidateOutput":
        schema_version = _require_string(
            value.get("schema_version", "1"), "candidate.schema_version"
        )
        answer = value.get("answer", "")
        if not isinstance(answer, str):
            raise ModelValidationError("candidate.answer must be a string")
        abstained = value.get("abstained", False)
        if not isinstance(abstained, bool):
            raise ModelValidationError("candidate.abstained must be boolean")
        citations_raw = value.get("citations", [])
        trajectory_raw = value.get("trajectory", [])
        metrics_raw = value.get("metrics", {})
        metadata = value.get("metadata", {})
        if not isinstance(citations_raw, list):
            raise ModelValidationError("candidate.citations must be a list")
        if not isinstance(trajectory_raw, list):
            raise ModelValidationError("candidate.trajectory must be a list")
        if not isinstance(metrics_raw, dict):
            raise ModelValidationError("candidate.metrics must be an object")
        if not isinstance(metadata, dict):
            raise ModelValidationError("candidate.metadata must be an object")
        metrics: dict[str, float] = {}
        for key, raw in metrics_raw.items():
            if not isinstance(key, str) or not isinstance(raw, (int, float)):
                raise ModelValidationError("candidate.metrics values must be numeric")
            metrics[key] = float(raw)
        trajectory = tuple(TrajectoryStep.from_dict(item) for item in trajectory_raw)
        seqs = [step.seq for step in trajectory]
        if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
            raise ModelValidationError(
                "candidate.trajectory seq values must be unique and ascending"
            )
        return cls(
            schema_version=schema_version,
            answer=answer.strip(),
            facts=_string_list(value.get("facts", []), "candidate.facts"),
            citations=tuple(Citation.from_dict(item) for item in citations_raw),
            abstained=abstained,
            trajectory=trajectory,
            metrics=metrics,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreResult:
    check_id: str
    check_type: str
    # The exact revision of the scorer that produced this score. A score without one is
    # not interpretable later: the same check_type can mean two different things a month
    # apart, and nothing in the record would say which one ran.
    scorer_revision: int
    dimension: str
    score: float
    passed: bool
    hard_gate: bool
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationResult:
    run_id: str
    scenario_id: str
    scenario_version: str
    candidate: str
    status: str
    aggregate_score: float
    started_at: str
    completed_at: str
    scores: tuple[ScoreResult, ...]
    # The revisions of the scorers this evaluation actually used, keyed by check type.
    # Deliberately what was *used* rather than the whole registry: adding a fourteenth
    # scorer does not change what a run that used three of them means, and a digest over
    # the registry would report those two runs as incomparable when they are not.
    scorer_revisions: Mapping[str, int] = field(default_factory=dict)
    # The revision of the code that turned those scores into this status and aggregate.
    # A run that pins its scorers but not this still cites a moving target.
    harness_revision: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelValidationError(f"{field_name} must be an object")
    return value


def normalized_set(values: Iterable[str]) -> set[str]:
    return {" ".join(value.lower().split()) for value in values if value.strip()}
