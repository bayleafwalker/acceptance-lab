from __future__ import annotations

import json
from importlib import resources
from typing import Any


def asset_dict(name: str) -> dict[str, Any]:
    value = json.loads(
        resources.files("acceptance_lab.demo_assets")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise AssertionError(f"Expected object fixture: {name}")
    return value


def asset_list(name: str) -> list[dict[str, Any]]:
    value = json.loads(
        resources.files("acceptance_lab.demo_assets")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
    if not isinstance(value, list):
        raise AssertionError(f"Expected list fixture: {name}")
    return value
