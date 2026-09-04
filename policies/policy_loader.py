from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_policy_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "expense_policy.json"


def load_policy_document(policy_path: Path | None = None) -> dict[str, Any]:
    path = policy_path or default_policy_path()
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
