"""Read-only probe: list production history records with their identity fields."""
from __future__ import annotations

import dataclasses
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "multi-workers"))

import decision_history  # noqa: E402

history = decision_history.load_history(ROOT)
for record in history.records[:2] + history.records[-6:]:
    print(dataclasses.asdict(record) if dataclasses.is_dataclass(record) else record)
