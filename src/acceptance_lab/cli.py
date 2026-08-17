from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from acceptance_lab.demo import run_demo
from acceptance_lab.models import CandidateOutput, Scenario
from acceptance_lab.reporting import (
    compare_payload,
    render_compare_json,
    render_compare_markdown,
    render_run_json,
    render_run_markdown,
)
from acceptance_lab.scoring import evaluate_candidate
from acceptance_lab.store import EventStore
from acceptance_lab.util import load_json, write_text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acceptlab",
        description="Executable acceptance records for agent systems.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize an event store")
    init.add_argument("--db", required=True, type=Path)

    evaluate = sub.add_parser("evaluate", help="Score one candidate output")
    evaluate.add_argument("--db", required=True, type=Path)
    evaluate.add_argument("--scenario", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    evaluate.add_argument("--candidate", required=True)
    evaluate.add_argument("--run-id")
    evaluate.add_argument(
        "--no-fail",
        action="store_true",
        help="Return zero even when a hard acceptance gate fails",
    )

    report = sub.add_parser("report", help="Render one evaluation run")
    report.add_argument("--db", required=True, type=Path)
    report.add_argument("--run-id", required=True)
    report.add_argument("--format", choices=("markdown", "json"), default="markdown")
    report.add_argument("--out", type=Path)

    compare = sub.add_parser("compare", help="Compare two runs of one scenario")
    compare.add_argument("--db", required=True, type=Path)
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--format", choices=("markdown", "json"), default="markdown")
    compare.add_argument("--out", type=Path)
    compare.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Return non-zero when a previously passing check fails",
    )

    verify = sub.add_parser("verify-store", help="Verify the event hash chain")
    verify.add_argument("--db", required=True, type=Path)

    rebuild = sub.add_parser("rebuild", help="Rebuild disposable projections")
    rebuild.add_argument("--db", required=True, type=Path)

    list_runs = sub.add_parser("list-runs", help="List projected runs")
    list_runs.add_argument("--db", required=True, type=Path)

    demo = sub.add_parser("demo", help="Run the deterministic example suite")
    demo.add_argument("--workspace", type=Path, default=Path(".demo"))

    return parser


def _emit(value: str, destination: Path | None) -> None:
    if destination is None:
        print(value)
    else:
        write_text(destination, value.rstrip() + "\n")
        print(destination)


def _evaluate(args: argparse.Namespace) -> int:
    scenario_dict = load_json(args.scenario)
    output_dict = load_json(args.output)
    scenario = Scenario.from_dict(scenario_dict)
    output = CandidateOutput.from_dict(output_dict)
    result = evaluate_candidate(
        scenario,
        output,
        args.candidate,
        run_id=args.run_id,
        metadata={
            "scenario_path": str(args.scenario),
            "output_path": str(args.output),
        },
    )
    store = EventStore(args.db)
    store.record_evaluation(
        result,
        scenario_snapshot=scenario_dict,
        output_snapshot=output_dict,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "status": result.status,
                "aggregate_score": result.aggregate_score,
            },
            sort_keys=True,
        )
    )
    return 0 if args.no_fail or result.status != "FAIL" else 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            EventStore(args.db).initialize()
            print(args.db)
            return 0
        if args.command == "evaluate":
            return _evaluate(args)
        if args.command == "report":
            store = EventStore(args.db)
            value = (
                render_run_markdown(store, args.run_id)
                if args.format == "markdown"
                else render_run_json(store, args.run_id)
            )
            _emit(value, args.out)
            return 0
        if args.command == "compare":
            store = EventStore(args.db)
            value = (
                render_compare_markdown(store, args.baseline, args.candidate)
                if args.format == "markdown"
                else render_compare_json(store, args.baseline, args.candidate)
            )
            _emit(value, args.out)
            payload = compare_payload(store, args.baseline, args.candidate)
            return 3 if args.fail_on_regression and payload["regressions"] else 0
        if args.command == "verify-store":
            valid, detail = EventStore(args.db).verify_chain()
            print(detail)
            return 0 if valid else 4
        if args.command == "rebuild":
            EventStore(args.db).rebuild_projections()
            print("projections rebuilt")
            return 0
        if args.command == "list-runs":
            print(json.dumps(EventStore(args.db).list_runs(), indent=2, sort_keys=True))
            return 0
        if args.command == "demo":
            run_ids = run_demo(args.workspace)
            print(args.workspace / "reports" / "summary.md")
            print(json.dumps(run_ids, indent=2, sort_keys=True))
            return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f"acceptlab: {exc}", file=sys.stderr)
        return 1
    parser.error(f"Unhandled command: {args.command}")
    return 1
