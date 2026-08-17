from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from acceptance_lab.store import EventStore

STATUS_RANK = {"FAIL": 0, "CONDITIONAL": 1, "PASS": 2}


def _format_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def run_payload(store: EventStore, run_id: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    scores = store.get_scores(run_id)
    valid, chain_detail = store.verify_chain()
    return {
        "run": run,
        "scores": scores,
        "event_chain": {"valid": valid, "detail": chain_detail},
    }


def render_run_json(store: EventStore, run_id: str) -> str:
    return json.dumps(run_payload(store, run_id), indent=2, sort_keys=True)


def render_run_markdown(store: EventStore, run_id: str) -> str:
    payload = run_payload(store, run_id)
    run = payload["run"]
    scores = payload["scores"]
    chain = payload["event_chain"]
    lines = [
        f"# Acceptance run: {run['candidate']}",
        "",
        f"- **Run:** `{run['run_id']}`",
        f"- **Scenario:** `{run['scenario_id']}@{run['scenario_version']}`",
        f"- **Status:** **{run['status']}**",
        f"- **Aggregate score:** {_format_score(run['aggregate_score'])}",
        f"- **Event chain:** {'valid' if chain['valid'] else 'INVALID'} — {chain['detail']}",
        f"- **Scenario hash:** `{run['scenario_hash']}`",
        f"- **Output hash:** `{run['output_hash']}`",
        "",
        "## Checks",
        "",
        "| Dimension | Check | Score | Result | Gate | Summary |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for score in scores:
        result = "PASS" if score["passed"] else "FAIL"
        gate = "hard" if score["hard_gate"] else "soft"
        summary = str(score["summary"]).replace("|", "\\|")
        lines.append(
            f"| {score['dimension']} | `{score['check_id']}` | "
            f"{score['score']:.3f} | {result} | {gate} | {summary} |"
        )
    hard_failures = [
        score for score in scores if score["hard_gate"] and not score["passed"]
    ]
    lines.extend(["", "## Promotion decision", ""])
    if hard_failures:
        lines.append("Promotion is blocked by hard-gate failures:")
        lines.append("")
        for score in hard_failures:
            lines.append(f"- `{score['check_id']}` — {score['summary']}")
    elif run["status"] == "CONDITIONAL":
        lines.append(
            "No hard gate failed, but one or more soft acceptance checks require review."
        )
    else:
        lines.append("All declared acceptance checks passed.")
    lines.append("")
    return "\n".join(lines)


def compare_payload(
    store: EventStore, baseline_run_id: str, candidate_run_id: str
) -> dict[str, Any]:
    baseline = store.get_run(baseline_run_id)
    candidate = store.get_run(candidate_run_id)
    if baseline["scenario_id"] != candidate["scenario_id"]:
        raise ValueError("Runs must use the same scenario_id")
    if baseline["scenario_version"] != candidate["scenario_version"]:
        raise ValueError("Runs must use the same scenario_version")
    baseline_scores = {item["check_id"]: item for item in store.get_scores(baseline_run_id)}
    candidate_scores = {item["check_id"]: item for item in store.get_scores(candidate_run_id)}
    check_ids = sorted(set(baseline_scores) | set(candidate_scores))
    checks: list[dict[str, Any]] = []
    regressions: list[str] = []
    improvements: list[str] = []
    for check_id in check_ids:
        before = baseline_scores.get(check_id)
        after = candidate_scores.get(check_id)
        before_score = float(before["score"]) if before else None
        after_score = float(after["score"]) if after else None
        delta = (
            after_score - before_score
            if before_score is not None and after_score is not None
            else None
        )
        before_passed = bool(before["passed"]) if before else False
        after_passed = bool(after["passed"]) if after else False
        if before_passed and not after_passed:
            regressions.append(check_id)
        if not before_passed and after_passed:
            improvements.append(check_id)
        checks.append(
            {
                "check_id": check_id,
                "dimension": (after or before)["dimension"],
                "baseline_score": before_score,
                "candidate_score": after_score,
                "delta": delta,
                "baseline_passed": before_passed,
                "candidate_passed": after_passed,
                "hard_gate": bool((after or before)["hard_gate"]),
            }
        )
    status_delta = STATUS_RANK.get(candidate["status"], -1) - STATUS_RANK.get(
        baseline["status"], -1
    )
    return {
        "scenario_id": baseline["scenario_id"],
        "scenario_version": baseline["scenario_version"],
        "baseline": baseline,
        "candidate": candidate,
        "status_delta": status_delta,
        "checks": checks,
        "regressions": regressions,
        "improvements": improvements,
    }


def render_compare_json(
    store: EventStore, baseline_run_id: str, candidate_run_id: str
) -> str:
    return json.dumps(
        compare_payload(store, baseline_run_id, candidate_run_id),
        indent=2,
        sort_keys=True,
    )


def render_compare_markdown(
    store: EventStore, baseline_run_id: str, candidate_run_id: str
) -> str:
    payload = compare_payload(store, baseline_run_id, candidate_run_id)
    baseline = payload["baseline"]
    candidate = payload["candidate"]
    lines = [
        f"# Acceptance comparison: {payload['scenario_id']}",
        "",
        f"- **Baseline:** {baseline['candidate']} — **{baseline['status']}** "
        f"({_format_score(baseline['aggregate_score'])})",
        f"- **Candidate:** {candidate['candidate']} — **{candidate['status']}** "
        f"({_format_score(candidate['aggregate_score'])})",
        "",
        "| Dimension | Check | Baseline | Candidate | Delta | Gate |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for check in payload["checks"]:
        by_dimension[check["dimension"]].append(check)
    for dimension in sorted(by_dimension):
        for check in by_dimension[dimension]:
            delta = check["delta"]
            delta_text = "—" if delta is None else f"{delta:+.3f}"
            gate = "hard" if check["hard_gate"] else "soft"
            lines.append(
                f"| {dimension} | `{check['check_id']}` | "
                f"{_format_score(check['baseline_score'])} | "
                f"{_format_score(check['candidate_score'])} | {delta_text} | {gate} |"
            )
    lines.extend(["", "## Decision notes", ""])
    if payload["regressions"]:
        lines.append("Regressions:")
        lines.append("")
        for check_id in payload["regressions"]:
            lines.append(f"- `{check_id}` changed from pass to fail")
        lines.append("")
    if payload["improvements"]:
        lines.append("Improvements:")
        lines.append("")
        for check_id in payload["improvements"]:
            lines.append(f"- `{check_id}` changed from fail to pass")
        lines.append("")
    if not payload["regressions"] and not payload["improvements"]:
        lines.append("No check changed pass/fail state.")
        lines.append("")
    if payload["status_delta"] > 0:
        lines.append("The candidate improved the promotion state.")
    elif payload["status_delta"] < 0:
        lines.append("The candidate regressed the promotion state.")
    else:
        lines.append("The promotion state did not change.")
    lines.append("")
    return "\n".join(lines)
