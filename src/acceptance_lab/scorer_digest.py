"""The behavioural identity of a scorer, so a silent edit cannot pass for the same one.

Pinning a revision only helps if the revision moves whenever the scorer does. Nothing
makes that true by itself: an author edits a comparison, forgets to bump the integer,
and every historical verdict that cited that revision now means something it did not
mean when it was recorded. The record would still look pinned. That is worse than an
unpinned record, because it claims a guarantee it no longer provides.

So each scorer's source is digested and locked in `scorer_revisions.json`, and a test
compares the two. Editing a scorer without bumping its revision fails; bumping without
editing fails; both together require updating the lock, which puts the decision in the
diff where a reviewer sees it.

The digest is taken over the parsed syntax with docstrings removed, not over the raw
text, so reformatting and rewording do not force a revision bump. What survives that
normalisation is what the scorer computes -- which is exactly the thing a revision is
supposed to track.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
from importlib import resources
from typing import Any, Mapping

LOCK_FILENAME = "scorer_revisions.json"


def _strip_docstrings(node: ast.AST) -> ast.AST:
    for child in ast.walk(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            continue
        body = getattr(child, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            child.body = body[1:] or [ast.Pass()]
    return node


def digest_source(source: str) -> str:
    """A stable digest of what this source computes.

    Split out from `scorer_digest` so the digest's own sensitivity is testable on source
    text: two functions defined in a test to differ only in a comparison must otherwise
    also differ in name, and a test that cannot hold the name fixed cannot show that the
    comparison is what moved the digest.
    """
    tree = _strip_docstrings(ast.parse(textwrap.dedent(source)))
    # `ast.unparse`, not `ast.dump`. Dumping the tree is the obvious move and it is
    # wrong here: the dump names node fields, and those change between Python releases,
    # so every digest shifted between 3.12 and 3.14 and the lock failed on CI while
    # passing locally. A lock that depends on the interpreter locks nothing. Unparsing
    # emits normalised source instead -- the same text on both, verified across 3.12 and
    # 3.14 -- which is also the representation a reader can inspect for themselves.
    return hashlib.sha256(ast.unparse(tree).encode()).hexdigest()


def scorer_digest(function: Any) -> str:
    """A stable digest of what a scorer computes.

    The function's own name is inside the digest, deliberately. Renaming a scorer is a
    change to the thing an evaluation cites by name, and the failure direction of
    including it -- one unnecessary revision bump -- is the harmless one.
    """
    return digest_source(inspect.getsource(function))


def current_lock() -> dict[str, dict[str, Any]]:
    """The lock as this build's scorers actually are, in registry order."""
    from acceptance_lab.scoring import SCORERS

    return {
        name: {"revision": spec.revision, "digest": scorer_digest(spec.scorer)}
        for name, spec in SCORERS.items()
    }


def current_harness_lock() -> dict[str, Any]:
    """The lock for the code that turns scores into a verdict.

    Locked alongside the scorers because it decides the same thing they do. A threshold
    comparison and a status rule are judgements; a run that cites a scorer revision but
    not this one is still citing a moving target, just a smaller one.
    """
    from acceptance_lab import scoring

    return {
        "revision": scoring.EVALUATION_HARNESS_REVISION,
        "digest": hashlib.sha256(
            "".join(
                digest_source(inspect.getsource(getattr(scoring, name)))
                for name in scoring.HARNESS_FUNCTIONS
            ).encode()
        ).hexdigest(),
    }


def recorded_harness_lock() -> Mapping[str, Any]:
    text = resources.files("acceptance_lab").joinpath(LOCK_FILENAME).read_text(encoding="utf-8")
    value = json.loads(text).get("evaluation_harness")
    if not isinstance(value, dict):
        raise ValueError(f"{LOCK_FILENAME} must carry an 'evaluation_harness' object")
    return value


def recorded_lock() -> Mapping[str, Mapping[str, Any]]:
    """The lock as committed."""
    text = resources.files("acceptance_lab").joinpath(LOCK_FILENAME).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("scorers"), dict):
        raise ValueError(f"{LOCK_FILENAME} must be an object with a 'scorers' object")
    return value["scorers"]


def lock_document() -> dict[str, Any]:
    return {
        "schema_version": "acceptance-lab/scorer-lock/v1",
        "description": (
            "Behavioural digest per scorer, over the parsed syntax with docstrings "
            "removed. Regenerate with: python -m acceptance_lab.scorer_digest"
        ),
        "scorers": current_lock(),
        "evaluation_harness": current_harness_lock(),
    }


def main() -> int:
    path = resources.files("acceptance_lab").joinpath(LOCK_FILENAME)
    with open(str(path), "w", encoding="utf-8") as handle:
        json.dump(lock_document(), handle, indent=2, sort_keys=False)
        handle.write("\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
