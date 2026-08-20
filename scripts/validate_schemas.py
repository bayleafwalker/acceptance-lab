from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def validate_group(root: Path, schema_name: str, example_globs: tuple[str, ...]) -> None:
    schema_path = root / "schemas" / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for pattern in example_globs:
        for path in sorted(root.glob(pattern)):
            value = json.loads(path.read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
            if errors:
                location = ".".join(str(item) for item in errors[0].path) or "<root>"
                raise SystemExit(f"{path}:{location}: {errors[0].message}")
            print(f"PASS {path}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    validate_group(
        root,
        "scenario.schema.json",
        ("examples/scenarios/*.json", "campaigns/*/*/scenario.json"),
    )
    validate_group(
        root,
        "candidate-output.schema.json",
        ("examples/outputs/*.json", "campaigns/*/*/candidate-output.json"),
    )


if __name__ == "__main__":
    main()
