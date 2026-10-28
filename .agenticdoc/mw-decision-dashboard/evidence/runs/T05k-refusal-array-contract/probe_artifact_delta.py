"""T05k artifact delta: the regenerated JSON/TS differ from the pre-T05k render
only by the three ``p0_open`` array bounds (no unrelated folding).

The checked-in artifacts were regenerated with the generator after the source
change; this probe re-renders them with the three new keys temporarily removed
and reports the textual delta, so the report can claim "generated, no hand
edits, no unrelated drift" instead of assuming it.
"""

from __future__ import annotations

import difflib
import importlib.util
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
MW = REPO / "packages" / "multi-workers"
sys.path.insert(0, str(MW))

import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

JSON_PATH = MW / "decide_registry.json"
TS_PATH = (
    REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "decide-registry.generated.ts"
)
NEW_KEYS = ("max_items", "item_type", "item_max_bytes")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_decide_registry_ts", MW / "scripts" / "gen_decide_registry_ts.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _without_bounds():
    # ``STATE_FIELD_DESCRIPTIONS`` is a read-only mapping proxy; swap the module
    # global for a plain copy for this in-process render only.
    mapping = dict(dpts.STATE_FIELD_DESCRIPTIONS)
    spec = dict(mapping["p0_open"])
    for key in NEW_KEYS:
        spec.pop(key, None)
    mapping["p0_open"] = spec
    dpts.STATE_FIELD_DESCRIPTIONS = mapping


def _diff(label: str, before: str, after: str) -> tuple[int, int]:
    lines = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(), fromfile=f"{label} (without T05k)", tofile=f"{label} (now)", lineterm=""
        )
    )
    added = [line for line in lines if line.startswith("+") and not line.startswith("+++")]
    removed = [line for line in lines if line.startswith("-") and not line.startswith("---")]
    print(f"{label}: {len(added)} added lines, {len(removed)} removed lines")
    for line in lines:
        print(line)
    return len(added), len(removed)


def main() -> None:
    json_now = JSON_PATH.read_text(encoding="utf-8")
    gen = _load_generator()
    ts_now = TS_PATH.read_text(encoding="utf-8")
    _without_bounds()
    json_before = dpts.registry_snapshot_text(mw._dp_export_doc()[0])
    ts_before = gen.render()
    json_counts = _diff("decide_registry.json", json_before, json_now)
    ts_counts = _diff("decide-registry.generated.ts", ts_before, ts_now)
    print()
    ok = json_counts == ts_counts == (3, 0)
    print(
        f"json (added, removed)={json_counts} ts={ts_counts}"
    )
    print(
        "only the three p0_open bounds were folded (no unrelated drift)"
        if ok
        else "UNEXPECTED extra delta"
    )


main()
