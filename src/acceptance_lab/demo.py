from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from acceptance_lab.models import CandidateOutput, Scenario
from acceptance_lab.reporting import (
    render_compare_markdown,
    render_run_markdown,
)
from acceptance_lab.retrieval import Document, candidate_from_retrieval
from acceptance_lab.scoring import evaluate_candidate
from acceptance_lab.store import EventStore
from acceptance_lab.util import write_text


def _asset_dict(name: str) -> dict[str, Any]:
    resource = resources.files("acceptance_lab.demo_assets").joinpath(name)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object asset: {name}")
    return value


def _asset_list(name: str) -> list[dict[str, Any]]:
    resource = resources.files("acceptance_lab.demo_assets").joinpath(name)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Expected list asset: {name}")
    return value


def _record(
    store: EventStore,
    scenario: Scenario,
    output: CandidateOutput,
    candidate: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    result = evaluate_candidate(
        scenario,
        output,
        candidate,
        metadata=metadata or {},
    )
    store.record_evaluation(
        result,
        scenario_snapshot=scenario.to_dict(),
        output_snapshot=output.to_dict(),
    )
    return result.run_id


def run_demo(workspace: str | Path) -> dict[str, str]:
    root = Path(workspace)
    database = root / "acceptance.db"
    reports = root / "reports"
    inputs = root / "inputs"
    if database.exists():
        database.unlink()
    if reports.exists():
        shutil.rmtree(reports)
    if inputs.exists():
        shutil.rmtree(inputs)
    reports.mkdir(parents=True, exist_ok=True)
    inputs.mkdir(parents=True, exist_ok=True)

    store = EventStore(database)
    store.initialize()

    retrieval_scenario_raw = _asset_dict("current-authority.json")
    trajectory_scenario_raw = _asset_dict("change-with-verification.json")
    corpus_raw = _asset_list("documents.json")
    retrieval_scenario = Scenario.from_dict(retrieval_scenario_raw)
    trajectory_scenario = Scenario.from_dict(trajectory_scenario_raw)
    documents = tuple(Document.from_dict(item) for item in corpus_raw)

    naive = candidate_from_retrieval(
        retrieval_scenario, documents, authority_aware=False
    )
    authority_aware = candidate_from_retrieval(
        retrieval_scenario, documents, authority_aware=True
    )
    unsafe = CandidateOutput.from_dict(_asset_dict("trajectory-bad.json"))
    verified = CandidateOutput.from_dict(_asset_dict("trajectory-good.json"))

    write_text(
        inputs / "current-authority.scenario.json",
        json.dumps(retrieval_scenario_raw, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        inputs / "change-with-verification.scenario.json",
        json.dumps(trajectory_scenario_raw, indent=2, sort_keys=True) + "\n",
    )
    write_text(inputs / "documents.json", json.dumps(corpus_raw, indent=2) + "\n")
    write_text(
        inputs / "retrieval-naive.output.json",
        json.dumps(naive.to_dict(), indent=2, sort_keys=True) + "\n",
    )
    write_text(
        inputs / "retrieval-authority-aware.output.json",
        json.dumps(authority_aware.to_dict(), indent=2, sort_keys=True) + "\n",
    )
    write_text(
        inputs / "trajectory-unsafe.output.json",
        json.dumps(unsafe.to_dict(), indent=2, sort_keys=True) + "\n",
    )
    write_text(
        inputs / "trajectory-verified.output.json",
        json.dumps(verified.to_dict(), indent=2, sort_keys=True) + "\n",
    )

    naive_run = _record(
        store,
        retrieval_scenario,
        naive,
        "retrieval-naive",
        metadata={"demo": True, "mode": "naive"},
    )
    authority_run = _record(
        store,
        retrieval_scenario,
        authority_aware,
        "retrieval-authority-aware",
        metadata={"demo": True, "mode": "authority-aware"},
    )
    unsafe_run = _record(
        store,
        trajectory_scenario,
        unsafe,
        "trajectory-unsafe",
        metadata={"demo": True, "mode": "fixture"},
    )
    verified_run = _record(
        store,
        trajectory_scenario,
        verified,
        "trajectory-verified",
        metadata={"demo": True, "mode": "fixture"},
    )

    run_ids = {
        "retrieval_naive": naive_run,
        "retrieval_authority_aware": authority_run,
        "trajectory_unsafe": unsafe_run,
        "trajectory_verified": verified_run,
    }
    for label, run_id in run_ids.items():
        write_text(reports / f"{label}.md", render_run_markdown(store, run_id))

    write_text(
        reports / "retrieval-comparison.md",
        render_compare_markdown(store, naive_run, authority_run),
    )
    write_text(
        reports / "trajectory-comparison.md",
        render_compare_markdown(store, unsafe_run, verified_run),
    )
    valid, chain_detail = store.verify_chain()
    summary_lines = [
        "# Acceptance Lab deterministic demo",
        "",
        "| Workload | Baseline | Candidate |",
        "| --- | --- | --- |",
        f"| Current authority retrieval | {store.get_run(naive_run)['status']} | {store.get_run(authority_run)['status']} |",
        f"| Bounded change trajectory | {store.get_run(unsafe_run)['status']} | {store.get_run(verified_run)['status']} |",
        "",
        f"Event chain: {'valid' if valid else 'INVALID'} — {chain_detail}",
        "",
        "The failing candidates are intentional. Read the comparison reports for the hard gates that changed state.",
        "",
        "Run IDs:",
        "",
    ]
    summary_lines.extend(f"- `{key}`: `{value}`" for key, value in run_ids.items())
    summary_lines.append("")
    write_text(reports / "summary.md", "\n".join(summary_lines))
    write_text(root / "run-ids.json", json.dumps(run_ids, indent=2, sort_keys=True) + "\n")
    return run_ids
