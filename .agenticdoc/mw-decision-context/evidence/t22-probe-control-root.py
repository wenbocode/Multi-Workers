"""Read-only probe: resolve the control root and inspect the production history snapshot."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "multi-workers"))

import mw_common  # noqa: E402
import decision_history  # noqa: E402

print("project", ROOT)
print("control", mw_common.resolve_control_root(ROOT))
history = decision_history.load_history(ROOT)
print("records", len(history.records))
print("stats", history.stats)
print("warnings", history.warnings[:10])
