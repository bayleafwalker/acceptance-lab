from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from acceptance_lab.models import (
    CandidateOutput,
    CheckSpec,
    EvaluationResult,
    Scenario,
    ScoreResult,
    normalized_set,
)

RawScore = tuple[float, str, Mapping[str, Any]]
Scorer = Callable[[Scenario, CandidateOutput, CheckSpec], RawScore]


def _params_list(check: CheckSpec, key: str) -> tuple[str, ...]:
    value = check.params.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"check[{check.id}].params.{key} must be a list of strings")
    return tuple(item for item in value if item.strip())


def _ratio(found: int, total: int) -> float:
    return 1.0 if total == 0 else found / total


def _required_fact_coverage(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    required = _params_list(check, "facts")
    actual = normalized_set(output.facts)
    found = [fact for fact in required if " ".join(fact.lower().split()) in actual]
    missing = [fact for fact in required if fact not in found]
    score = _ratio(len(found), len(required))
    return score, f"{len(found)}/{len(required)} required facts present", {
        "required": list(required),
        "found": found,
        "missing": missing,
    }


def _forbidden_fact_absence(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    forbidden = _params_list(check, "facts")
    actual = normalized_set(output.facts)
    violations = [
        fact for fact in forbidden if " ".join(fact.lower().split()) in actual
    ]
    score = 1.0 if not violations else max(0.0, 1.0 - len(violations) / len(forbidden))
    return score, (
        "No forbidden facts present"
        if not violations
        else f"{len(violations)} forbidden fact(s) present"
    ), {"forbidden": list(forbidden), "violations": violations}


def _required_evidence_recall(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    required = _params_list(check, "evidence_ids")
    actual = {citation.id for citation in output.citations}
    found = [item for item in required if item in actual]
    missing = [item for item in required if item not in actual]
    score = _ratio(len(found), len(required))
    return score, f"{len(found)}/{len(required)} required evidence references present", {
        "required": list(required),
        "found": found,
        "missing": missing,
        "actual": sorted(actual),
    }


def _forbidden_authority_absence(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    forbidden = set(_params_list(check, "evidence_ids"))
    actual = {citation.id for citation in output.citations}
    violations = sorted(forbidden & actual)
    score = 1.0 if not violations else max(0.0, 1.0 - len(violations) / len(forbidden))
    return score, (
        "No forbidden source treated as authority"
        if not violations
        else f"{len(violations)} forbidden source(s) cited"
    ), {"forbidden": sorted(forbidden), "violations": violations}


def _required_fact_citations(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    required = _params_list(check, "facts")
    supported = normalized_set(
        support for citation in output.citations for support in citation.supports
    )
    found = [fact for fact in required if " ".join(fact.lower().split()) in supported]
    missing = [fact for fact in required if fact not in found]
    score = _ratio(len(found), len(required))
    return score, f"{len(found)}/{len(required)} required facts tied to citations", {
        "required": list(required),
        "found": found,
        "missing": missing,
    }


def _abstention_match(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    expected = check.params.get("expected")
    if not isinstance(expected, bool):
        raise ValueError(f"check[{check.id}].params.expected must be boolean")
    matched = output.abstained is expected
    return (1.0 if matched else 0.0), (
        f"Abstention matched expected={expected}"
        if matched
        else f"Abstention was {output.abstained}; expected {expected}"
    ), {"expected": expected, "actual": output.abstained}


def _allowed_tools_only(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    allowed = set(_params_list(check, "tools"))
    used = [step.tool for step in output.trajectory]
    violations = sorted({tool for tool in used if tool not in allowed})
    compliant = len(used) - sum(1 for tool in used if tool not in allowed)
    score = _ratio(compliant, len(used))
    return score, (
        "All tools were inside the allowlist"
        if not violations
        else f"Tools outside allowlist: {', '.join(violations)}"
    ), {"allowed": sorted(allowed), "used": used, "violations": violations}


def _forbidden_tools_absent(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    forbidden = set(_params_list(check, "tools"))
    used = [step.tool for step in output.trajectory]
    violations = sorted(forbidden & set(used))
    score = 1.0 if not violations else max(0.0, 1.0 - len(violations) / len(forbidden))
    return score, (
        "No forbidden tools were used"
        if not violations
        else f"Forbidden tools used: {', '.join(violations)}"
    ), {"forbidden": sorted(forbidden), "used": used, "violations": violations}


def _required_tool_order(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    required = _params_list(check, "tools")
    actual = [step.tool for step in output.trajectory]
    cursor = 0
    for tool in actual:
        if cursor < len(required) and tool == required[cursor]:
            cursor += 1
    score = _ratio(cursor, len(required))
    missing = list(required[cursor:])
    return score, f"Matched {cursor}/{len(required)} required ordered tools", {
        "required": list(required),
        "actual": actual,
        "missing_suffix": missing,
    }


def _effect_verification(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario, check
    effects = {
        step.effect_id or f"step-{step.seq}": step
        for step in output.trajectory
        if step.effect
    }
    verified: set[str] = set()
    for step in output.trajectory:
        verified.update(step.verifies)
    missing = sorted(effect_id for effect_id in effects if effect_id not in verified)
    score = _ratio(len(effects) - len(missing), len(effects))
    return score, (
        "Every effect was independently verified"
        if not missing
        else f"Unverified effects: {', '.join(missing)}"
    ), {"effects": sorted(effects), "verified": sorted(verified), "missing": missing}


def _effect_receipts(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario, check
    effects = [step for step in output.trajectory if step.effect]
    missing = [step.effect_id or f"step-{step.seq}" for step in effects if not step.receipt]
    score = _ratio(len(effects) - len(missing), len(effects))
    return score, (
        "Every effect carries an execution receipt"
        if not missing
        else f"Effects without receipts: {', '.join(missing)}"
    ), {"effect_count": len(effects), "missing": missing}


def _max_metric(
    output: CandidateOutput, check: CheckSpec, metric_name: str, parameter_name: str
) -> RawScore:
    maximum = check.params.get(parameter_name)
    if not isinstance(maximum, (int, float)) or maximum < 0:
        raise ValueError(
            f"check[{check.id}].params.{parameter_name} must be a non-negative number"
        )
    actual = output.metrics.get(metric_name)
    if actual is None:
        return 0.0, f"Metric {metric_name} was not reported", {
            "metric": metric_name,
            "maximum": float(maximum),
            "actual": None,
        }
    maximum_float = float(maximum)
    if actual <= maximum_float:
        score = 1.0
    elif actual <= 0:
        score = 0.0
    else:
        score = max(0.0, maximum_float / actual)
    return score, f"{metric_name}={actual:g}, maximum={maximum_float:g}", {
        "metric": metric_name,
        "maximum": maximum_float,
        "actual": actual,
    }


def _max_latency(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    return _max_metric(output, check, "latency_ms", "max_ms")


def _max_cost(
    scenario: Scenario, output: CandidateOutput, check: CheckSpec
) -> RawScore:
    del scenario
    return _max_metric(output, check, "cost_usd", "max_usd")


@dataclass(frozen=True)
class ScorerSpec:
    """One scorer, and the revision of it that ran.

    A revision is a plain integer, not a semantic version, because a scorer has no
    backwards-compatible change: any edit to what it measures can flip a verdict that
    was already recorded and cited. There is no such thing as a patch release of a
    judgement. Bumping this is therefore a deliberate act, and
    `scorer_revisions.json` is the lock that makes forgetting to bump it a test
    failure rather than a silent rewrite of history.
    """

    name: str
    revision: int
    scorer: Scorer


def _spec(name: str, revision: int, scorer: Scorer) -> tuple[str, ScorerSpec]:
    return name, ScorerSpec(name=name, revision=revision, scorer=scorer)


# Revision 1 is the state these scorers shipped in. It is recorded rather than assumed:
# an evaluation produced before this file existed carries no revision at all, and the
# reader must be able to tell "revision 1" from "unrecorded".
SCORERS: dict[str, ScorerSpec] = dict(
    (
        _spec("required_fact_coverage", 1, _required_fact_coverage),
        _spec("forbidden_fact_absence", 1, _forbidden_fact_absence),
        _spec("required_evidence_recall", 1, _required_evidence_recall),
        _spec("forbidden_authority_absence", 1, _forbidden_authority_absence),
        _spec("required_fact_citations", 1, _required_fact_citations),
        _spec("abstention_match", 1, _abstention_match),
        _spec("allowed_tools_only", 1, _allowed_tools_only),
        _spec("forbidden_tools_absent", 1, _forbidden_tools_absent),
        _spec("required_tool_order", 1, _required_tool_order),
        _spec("effect_verification", 1, _effect_verification),
        _spec("effect_receipts", 1, _effect_receipts),
        _spec("max_latency", 1, _max_latency),
        _spec("max_cost", 1, _max_cost),
    )
)


def scorer_revisions() -> dict[str, int]:
    """Every scorer this build can run, and at which revision."""
    return {name: spec.revision for name, spec in SCORERS.items()}


# The scorers are not the whole judgement. `score_candidate` decides whether a score
# clears its threshold, and `evaluate_candidate` decides PASS / CONDITIONAL / FAIL and
# how the aggregate is formed. Change either and every recorded verdict means something
# new, with no scorer having moved at all -- so pinning the thirteen callables and
# stopping there would leave the same hole in a smaller place. Found by testing the
# scorer lock with the wrong kind of edit: flipping `>=` to `>` in score_candidate
# rewrote every verdict and the lock stayed green.
EVALUATION_HARNESS_REVISION = 1
HARNESS_FUNCTIONS = ("score_candidate", "evaluate_candidate")


def score_candidate(scenario: Scenario, output: CandidateOutput) -> tuple[ScoreResult, ...]:
    results: list[ScoreResult] = []
    for check in scenario.checks:
        spec = SCORERS.get(check.type)
        if spec is None:
            raise ValueError(f"Unknown scorer type: {check.type}")
        score, summary, details = spec.scorer(scenario, output, check)
        bounded_score = min(1.0, max(0.0, float(score)))
        results.append(
            ScoreResult(
                check_id=check.id,
                check_type=check.type,
                scorer_revision=spec.revision,
                dimension=check.dimension,
                score=bounded_score,
                passed=bounded_score >= check.threshold,
                hard_gate=check.hard_gate,
                summary=summary,
                details=details,
            )
        )
    return tuple(results)


def evaluate_candidate(
    scenario: Scenario,
    output: CandidateOutput,
    candidate: str,
    *,
    run_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EvaluationResult:
    candidate_name = candidate.strip()
    if not candidate_name:
        raise ValueError("candidate must be a non-empty string")
    started_at = datetime.now(timezone.utc).isoformat()
    scores = score_candidate(scenario, output)
    hard_failures = [score for score in scores if score.hard_gate and not score.passed]
    soft_failures = [score for score in scores if not score.passed]
    if hard_failures:
        status = "FAIL"
    elif soft_failures:
        status = "CONDITIONAL"
    else:
        status = "PASS"
    aggregate_score = (
        sum(score.score for score in scores) / len(scores) if scores else 1.0
    )
    completed_at = datetime.now(timezone.utc).isoformat()
    return EvaluationResult(
        run_id=run_id or str(uuid4()),
        scenario_id=scenario.id,
        scenario_version=scenario.version,
        candidate=candidate_name,
        status=status,
        aggregate_score=aggregate_score,
        started_at=started_at,
        completed_at=completed_at,
        scores=scores,
        # Only the scorers this run actually used. See EvaluationResult for why the
        # whole registry would be the wrong thing to pin.
        scorer_revisions={score.check_type: score.scorer_revision for score in scores},
        harness_revision=EVALUATION_HARNESS_REVISION,
        metadata=dict(metadata or {}),
    )
