#!/usr/bin/env python3
"""Rebuild the sanitized 2026-08-20 evaluation campaign.

The committed reports intentionally omit evaluation wall-clock timestamps and
event UUIDs.  A disposable EventStore is still exercised on every run so the
append-only recording and projection path is checked without making generated
artifacts nondeterministic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from acceptance_lab.adapters import candidate_from_trace
from acceptance_lab.models import CandidateOutput, Scenario
from acceptance_lab.scoring import evaluate_candidate
from acceptance_lab.store import EventStore
from acceptance_lab.util import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "2026-08-20"
CASES = ("local-inference-manifest", "takeover-current-state")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def stable_report(case: str) -> tuple[dict, dict]:
    directory = CAMPAIGN / case
    scenario_raw = load(directory / "scenario.json")
    observation_raw = load(directory / "candidate-observation.json")
    trace_raw = load(directory / "trace.json")
    output_raw = candidate_from_trace(observation_raw, trace_raw)

    scenario = Scenario.from_dict(scenario_raw)
    output = CandidateOutput.from_dict(output_raw)
    result = evaluate_candidate(
        scenario,
        output,
        case,
        run_id=f"campaign-2026-08-20:{case}",
        metadata={"campaign": "2026-08-20", "case": case},
    )

    with tempfile.TemporaryDirectory(prefix="acceptlab-campaign-") as temp:
        store = EventStore(Path(temp) / "events.db")
        store.record_evaluation(
            result,
            scenario_snapshot=scenario_raw,
            output_snapshot=output_raw,
        )
        valid, detail = store.verify_chain()
        if not valid:
            raise RuntimeError(detail)
        store.rebuild_projections()

    report = {
        "schema_version": 1,
        "campaign": "2026-08-20",
        "case": case,
        "run_id": result.run_id,
        "candidate": result.candidate,
        "scenario_id": result.scenario_id,
        "scenario_version": result.scenario_version,
        "status": result.status,
        "aggregate_score": result.aggregate_score,
        "scenario_sha256": sha256_text(canonical_json(scenario_raw)),
        "candidate_observation_sha256": sha256_text(canonical_json(observation_raw)),
        "trace_sha256": sha256_text(canonical_json(trace_raw)),
        "candidate_output_sha256": sha256_text(canonical_json(output_raw)),
        "event_store_gate": detail,
        "scores": [score.to_dict() for score in result.scores],
    }
    return output_raw, report


def markdown(report: dict) -> str:
    lines = [
        f"# Acceptance campaign case: {report['case']}",
        "",
        f"- Status: **{report['status']}**",
        f"- Aggregate score: {report['aggregate_score']:.3f}",
        f"- Scenario: `{report['scenario_id']}@{report['scenario_version']}`",
        f"- Scenario SHA-256: `{report['scenario_sha256']}`",
        f"- Candidate-output SHA-256: `{report['candidate_output_sha256']}`",
        f"- Disposable event-store gate: {report['event_store_gate']}",
        "",
        "| Dimension | Check | Score | Result | Gate |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for score in report["scores"]:
        lines.append(
            f"| {score['dimension']} | `{score['check_id']}` | "
            f"{score['score']:.3f} | {'PASS' if score['passed'] else 'FAIL'} | "
            f"{'hard' if score['hard_gate'] else 'soft'} |"
        )
    lines.append("")
    return "\n".join(lines)


def emit_or_check(path: Path, content: str, *, write: bool) -> None:
    if write:
        path.write_text(content, encoding="utf-8")
        return
    actual = path.read_text(encoding="utf-8")
    if actual != content:
        raise SystemExit(f"generated artifact is stale: {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for case in CASES:
        directory = CAMPAIGN / case
        output, report = stable_report(case)
        emit_or_check(
            directory / "candidate-output.json",
            json.dumps(output, indent=2, sort_keys=True) + "\n",
            write=args.write,
        )
        emit_or_check(
            directory / "evaluation.json",
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            write=args.write,
        )
        emit_or_check(
            directory / "evaluation.md",
            markdown(report),
            write=args.write,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
