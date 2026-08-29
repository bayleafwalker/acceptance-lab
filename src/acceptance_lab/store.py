from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from acceptance_lab.models import EvaluationResult
from acceptance_lab.util import canonical_json, sha256_text

ZERO_HASH = "0" * 64


class StoreIntegrityError(RuntimeError):
    """Raised when the append-only event chain cannot be verified."""


class EventStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    stream_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );

                CREATE INDEX IF NOT EXISTS idx_events_stream
                    ON events(stream_id, seq);
                CREATE INDEX IF NOT EXISTS idx_events_type
                    ON events(event_type, seq);

                CREATE TABLE IF NOT EXISTS projection_runs (
                    run_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    scenario_version TEXT NOT NULL,
                    candidate TEXT NOT NULL,
                    status TEXT,
                    aggregate_score REAL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata_json TEXT NOT NULL,
                    scenario_hash TEXT NOT NULL,
                    output_hash TEXT NOT NULL,
                    scorer_revisions_json TEXT NOT NULL DEFAULT '{}',
                    harness_revision INTEGER
                );

                CREATE TABLE IF NOT EXISTS projection_scores (
                    run_id TEXT NOT NULL,
                    check_id TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    hard_gate INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    scorer_revision INTEGER,
                    PRIMARY KEY (run_id, check_id),
                    FOREIGN KEY (run_id) REFERENCES projection_runs(run_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_projection_scores_dimension
                    ON projection_scores(run_id, dimension);
                """
            )
            self._widen_projections(connection)
            connection.commit()

    # Projections are disposable by design, so a store written before the scorer columns
    # existed is widened in place and rebuilt rather than migrated. The event log is the
    # authority and is never touched here.
    _PROJECTION_COLUMNS = (
        ("projection_runs", "scorer_revisions_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("projection_runs", "harness_revision", "INTEGER"),
        ("projection_scores", "scorer_revision", "INTEGER"),
    )

    def _widen_projections(self, connection: sqlite3.Connection) -> bool:
        widened = False
        for table, column, declaration in self._PROJECTION_COLUMNS:
            existing = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
                widened = True
        return widened

    @staticmethod
    def _event_hash(
        *,
        previous_hash: str,
        event_id: str,
        stream_id: str,
        event_type: str,
        occurred_at: str,
        payload_json: str,
    ) -> str:
        material = canonical_json(
            {
                "previous_hash": previous_hash,
                "event_id": event_id,
                "stream_id": stream_id,
                "event_type": event_type,
                "occurred_at": occurred_at,
                "payload_json": payload_json,
            }
        )
        return sha256_text(material)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        stream_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        occurred_at: str | None = None,
    ) -> str:
        last = connection.execute(
            "SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(last["event_hash"]) if last else ZERO_HASH
        event_id = str(uuid4())
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
        payload_json = canonical_json(dict(payload))
        event_hash = self._event_hash(
            previous_hash=previous_hash,
            event_id=event_id,
            stream_id=stream_id,
            event_type=event_type,
            occurred_at=timestamp,
            payload_json=payload_json,
        )
        connection.execute(
            """
            INSERT INTO events(
                event_id, stream_id, event_type, occurred_at, payload_json,
                previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                stream_id,
                event_type,
                timestamp,
                payload_json,
                previous_hash,
                event_hash,
            ),
        )
        return event_id

    def append_event(
        self,
        *,
        stream_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> str:
        self.initialize()
        with self.connect() as connection:
            with connection:
                return self._append_event(
                    connection,
                    stream_id=stream_id,
                    event_type=event_type,
                    payload=payload,
                )

    def record_evaluation(
        self,
        result: EvaluationResult,
        *,
        scenario_snapshot: Mapping[str, Any],
        output_snapshot: Mapping[str, Any],
    ) -> None:
        self.initialize()
        scenario_record = dict(scenario_snapshot)
        output_record = dict(output_snapshot)
        scenario_hash = sha256_text(canonical_json(scenario_record))
        output_hash = sha256_text(canonical_json(output_record))
        with self.connect() as connection:
            with connection:
                self._append_event(
                    connection,
                    stream_id=result.run_id,
                    event_type="run.started",
                    occurred_at=result.started_at,
                    payload={
                        "run_id": result.run_id,
                        "scenario_id": result.scenario_id,
                        "scenario_version": result.scenario_version,
                        "candidate": result.candidate,
                        "started_at": result.started_at,
                        "metadata": dict(result.metadata),
                        "scenario_hash": scenario_hash,
                        "output_hash": output_hash,
                        "scorer_revisions": dict(result.scorer_revisions),
                        "harness_revision": result.harness_revision,
                        "scenario_snapshot": scenario_record,
                        "output_snapshot": output_record,
                    },
                )
                for score in result.scores:
                    self._append_event(
                        connection,
                        stream_id=result.run_id,
                        event_type="score.recorded",
                        payload={"run_id": result.run_id, **score.to_dict()},
                    )
                self._append_event(
                    connection,
                    stream_id=result.run_id,
                    event_type="run.completed",
                    occurred_at=result.completed_at,
                    payload={
                        "run_id": result.run_id,
                        "status": result.status,
                        "aggregate_score": result.aggregate_score,
                        "completed_at": result.completed_at,
                    },
                )
        self.rebuild_projections()

    def events(self, *, stream_id: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        query = "SELECT * FROM events"
        params: tuple[Any, ...] = ()
        if stream_id is not None:
            query += " WHERE stream_id = ?"
            params = (stream_id,)
        query += " ORDER BY seq"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def verify_chain(self) -> tuple[bool, str]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY seq").fetchall()
        expected_previous = ZERO_HASH
        for row in rows:
            if row["previous_hash"] != expected_previous:
                return False, (
                    f"event seq={row['seq']} has previous_hash={row['previous_hash']} "
                    f"but expected {expected_previous}"
                )
            expected_hash = self._event_hash(
                previous_hash=row["previous_hash"],
                event_id=row["event_id"],
                stream_id=row["stream_id"],
                event_type=row["event_type"],
                occurred_at=row["occurred_at"],
                payload_json=row["payload_json"],
            )
            if row["event_hash"] != expected_hash:
                return False, (
                    f"event seq={row['seq']} hash mismatch: "
                    f"stored={row['event_hash']} expected={expected_hash}"
                )
            expected_previous = row["event_hash"]
        return True, f"verified {len(rows)} event(s)"

    def assert_chain(self) -> None:
        valid, detail = self.verify_chain()
        if not valid:
            raise StoreIntegrityError(detail)

    def rebuild_projections(self) -> None:
        self.initialize()
        self.assert_chain()
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY seq").fetchall()
            with connection:
                connection.execute("DELETE FROM projection_scores")
                connection.execute("DELETE FROM projection_runs")
                for row in rows:
                    payload = json.loads(row["payload_json"])
                    event_type = row["event_type"]
                    if event_type == "run.started":
                        connection.execute(
                            """
                            INSERT INTO projection_runs(
                                run_id, scenario_id, scenario_version, candidate,
                                status, aggregate_score, started_at, completed_at,
                                metadata_json, scenario_hash, output_hash,
                                scorer_revisions_json, harness_revision
                            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, NULL, ?, ?, ?, ?, ?)
                            """,
                            (
                                payload["run_id"],
                                payload["scenario_id"],
                                payload["scenario_version"],
                                payload["candidate"],
                                payload["started_at"],
                                canonical_json(payload.get("metadata", {})),
                                payload["scenario_hash"],
                                payload["output_hash"],
                                # A run recorded before revisions were pinned has none,
                                # and rebuilding must not invent one. An empty map reads
                                # as "unrecorded", which is the truth about that run and
                                # is what makes it refuse to compare against a pinned one.
                                canonical_json(payload.get("scorer_revisions", {})),
                                payload.get("harness_revision"),
                            ),
                        )
                    elif event_type == "score.recorded":
                        connection.execute(
                            """
                            INSERT INTO projection_scores(
                                run_id, check_id, check_type, dimension, score,
                                passed, hard_gate, summary, details_json,
                                scorer_revision
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                payload["run_id"],
                                payload["check_id"],
                                payload["check_type"],
                                payload["dimension"],
                                payload["score"],
                                int(payload["passed"]),
                                int(payload["hard_gate"]),
                                payload["summary"],
                                canonical_json(payload.get("details", {})),
                                payload.get("scorer_revision"),
                            ),
                        )
                    elif event_type == "run.completed":
                        connection.execute(
                            """
                            UPDATE projection_runs
                            SET status = ?, aggregate_score = ?, completed_at = ?
                            WHERE run_id = ?
                            """,
                            (
                                payload["status"],
                                payload["aggregate_score"],
                                payload["completed_at"],
                                payload["run_id"],
                            ),
                        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projection_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown run_id: {run_id}")
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item

    def get_scores(self, run_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM projection_scores
                WHERE run_id = ?
                ORDER BY dimension, check_id
                """,
                (run_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["passed"] = bool(item["passed"])
            item["hard_gate"] = bool(item["hard_gate"])
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    def list_runs(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projection_runs ORDER BY started_at, run_id"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result
