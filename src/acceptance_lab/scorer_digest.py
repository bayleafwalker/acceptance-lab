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


#: Bumped when the digest *algorithm* changes, so a moved digest can be read.
#:
#: Without it, regenerating the lock after an algorithm change is indistinguishable in
#: the diff from thirteen scorers all changing behaviour at once, and a reviewer has no
#: way to tell which happened. Unknown is not equal.
DIGEST_ALGORITHM = 2

PACKAGE = "acceptance_lab"


def _called_names(tree: ast.AST) -> set[str]:
    """Every global name this source calls, including through a module attribute."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            names.add(f"{func.value.id}.{func.attr}")
    return names


def _resolve(name: str, namespace: Mapping[str, Any]) -> Any:
    head, _, attr = name.partition(".")
    obj = namespace.get(head)
    return getattr(obj, attr, None) if attr else obj


def closure_functions(function: Any) -> list[Any]:
    """The package-local functions this one calls, transitively, in a stable order.

    Resolved through `__globals__` rather than by matching names in the syntax tree,
    because a name only means something relative to the namespace it is looked up in,
    and guessing that is how a lock ends up pinning the wrong thing.

    The boundary is this package. Standard-library and third-party callees are excluded:
    locking them would claim a guarantee this file cannot keep, since their source can
    change under a dependency bump this repository never sees.

    **Classes are deliberately excluded**, and that is a residual gap rather than a
    decision that costs nothing. A dataclass field rename in `models` can change what a
    scorer reads while every digest here stays still. Including them would make every
    model edit bump all thirteen digests, and a lock that cries wolf gets regenerated
    without being read, which is the failure it exists to prevent. The narrower claim is
    the one worth being able to trust.
    """
    seen: dict[tuple[str, str], Any] = {}
    pending = [function]
    while pending:
        current = pending.pop()
        namespace = getattr(current, "__globals__", {})
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(current)))
        except (OSError, TypeError, SyntaxError):
            continue
        for name in _called_names(tree):
            candidate = _resolve(name, namespace)
            if not inspect.isfunction(candidate):
                continue
            module = getattr(candidate, "__module__", "") or ""
            if module != PACKAGE and not module.startswith(f"{PACKAGE}."):
                continue
            key = (module, candidate.__qualname__)
            if key in seen or candidate is function:
                continue
            seen[key] = candidate
            pending.append(candidate)
    return [seen[key] for key in sorted(seen)]


def scorer_digest(function: Any) -> str:
    """A stable digest of what a scorer computes, including the helpers it computes with.

    The function's own name is inside the digest, deliberately. Renaming a scorer is a
    change to the thing an evaluation cites by name, and the failure direction of
    including it -- one unnecessary revision bump -- is the harmless one.

    Until 2026-08-30 this digested the scorer's own source and nothing else, which left
    the lock open exactly where it mattered: ten of the thirteen scorers reach their
    verdict through `_ratio`, so editing that one function would have changed what all
    ten measure while every digest stayed green and the drift test passed. A lock that
    covers the caller but not the computation locks the signature, not the meaning.
    """
    sources = [inspect.getsource(function)]
    sources += [inspect.getsource(helper) for helper in closure_functions(function)]
    return digest_source("\n".join(sources))


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


def recorded_algorithm() -> int:
    """The algorithm the committed digests were taken with.

    Read separately from the digests so a mismatch reports the real cause. A digest that
    moved because the algorithm changed and one that moved because a scorer changed look
    identical in the lock, and only one of them means a revision should bump.
    """
    text = resources.files("acceptance_lab").joinpath(LOCK_FILENAME).read_text(encoding="utf-8")
    value = json.loads(text).get("digest_algorithm")
    if not isinstance(value, int):
        raise ValueError(f"{LOCK_FILENAME} must carry an integer 'digest_algorithm'")
    return value


def lock_document() -> dict[str, Any]:
    return {
        "schema_version": "acceptance-lab/scorer-lock/v1",
        "description": (
            "Behavioural digest per scorer, over the parsed syntax with docstrings "
            "removed, covering the scorer and the package-local functions it calls. "
            "Regenerate with: python -m acceptance_lab.scorer_digest"
        ),
        "digest_algorithm": DIGEST_ALGORITHM,
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
