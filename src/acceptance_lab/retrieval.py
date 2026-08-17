from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from acceptance_lab.models import CandidateOutput, Citation, Scenario

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]*", re.IGNORECASE)
CURRENT_STATUSES = {"ratified", "current"}


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    status: str
    valid_from: date
    valid_to: date | None
    authority: str
    body: str
    facts: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Document":
        valid_to = value.get("valid_to")
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            status=str(value["status"]),
            valid_from=date.fromisoformat(str(value["valid_from"])),
            valid_to=date.fromisoformat(str(valid_to)) if valid_to else None,
            authority=str(value.get("authority", "unknown")),
            body=str(value["body"]),
            facts=tuple(str(item) for item in value.get("facts", [])),
        )

    def is_admissible(self, as_of: date) -> bool:
        return (
            self.status in CURRENT_STATUSES
            and self.valid_from <= as_of
            and (self.valid_to is None or as_of < self.valid_to)
        )


def load_documents(path: str | Path) -> tuple[Document, ...]:
    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Corpus must be a JSON list: {source}")
    return tuple(Document.from_dict(item) for item in value)


def tokenize(value: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(value)]


def bm25_scores(documents: Iterable[Document], query: str) -> list[tuple[Document, float]]:
    docs = tuple(documents)
    if not docs:
        return []
    tokenized = [tokenize(f"{document.title} {document.body}") for document in docs]
    query_terms = tokenize(query)
    average_length = sum(len(tokens) for tokens in tokenized) / len(tokenized)
    document_frequency: dict[str, int] = {}
    for tokens in tokenized:
        for token in set(tokens):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    k1 = 1.5
    b = 0.75
    scored: list[tuple[Document, float]] = []
    for document, tokens in zip(docs, tokenized, strict=True):
        frequencies: dict[str, int] = {}
        for token in tokens:
            frequencies[token] = frequencies.get(token, 0) + 1
        score = 0.0
        for term in query_terms:
            tf = frequencies.get(term, 0)
            if tf == 0:
                continue
            df = document_frequency.get(term, 0)
            idf = math.log(1.0 + (len(docs) - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (
                1.0 - b + b * len(tokens) / max(average_length, 1.0)
            )
            score += idf * ((tf * (k1 + 1.0)) / denominator)
        scored.append((document, score))
    return sorted(scored, key=lambda item: (-item[1], item[0].id))


def retrieve(
    documents: Iterable[Document],
    query: str,
    *,
    as_of: date,
    authority_aware: bool,
    limit: int = 3,
) -> list[tuple[Document, float]]:
    candidates = tuple(documents)
    if authority_aware:
        candidates = tuple(document for document in candidates if document.is_admissible(as_of))
    return bm25_scores(candidates, query)[:limit]


def candidate_from_retrieval(
    scenario: Scenario,
    documents: Iterable[Document],
    *,
    authority_aware: bool,
) -> CandidateOutput:
    query = scenario.inputs.get("query")
    as_of_raw = scenario.inputs.get("as_of")
    if not isinstance(query, str) or not isinstance(as_of_raw, str):
        raise ValueError("retrieval scenario inputs require string query and as_of")
    as_of = date.fromisoformat(as_of_raw)
    results = retrieve(
        documents,
        query,
        as_of=as_of,
        authority_aware=authority_aware,
        limit=1,
    )
    if not results or results[0][1] <= 0:
        return CandidateOutput(
            schema_version="1",
            answer="Insufficient admissible evidence.",
            facts=(),
            citations=(),
            abstained=True,
            trajectory=(),
            metrics={"latency_ms": 2.0, "cost_usd": 0.0},
            metadata={"retrieval_mode": "authority-aware" if authority_aware else "naive"},
        )
    document, score = results[0]
    answer = " ".join(document.facts)
    citation = Citation(id=document.id, supports=document.facts)
    return CandidateOutput(
        schema_version="1",
        answer=answer,
        facts=document.facts,
        citations=(citation,),
        abstained=False,
        trajectory=(),
        metrics={"latency_ms": 3.0 if authority_aware else 2.0, "cost_usd": 0.0},
        metadata={
            "retrieval_mode": "authority-aware" if authority_aware else "naive",
            "retrieval_score": score,
            "selected_status": document.status,
            "selected_authority": document.authority,
        },
    )
