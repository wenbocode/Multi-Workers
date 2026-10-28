"""PM-only readonly T04 verification; synthetic case-list probe is not T05 generation."""
from __future__ import annotations
import hashlib
import json
import pathlib
import socket
import sys
import traceback
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
WT = HERE.parents[2] / "implementation-worktree"
MW = WT / "packages/multi-workers"
sys.path.insert(0, str(MW))
sys.path.insert(0, str(MW / "scripts"))


def deny_network(*args, **kwargs):
    raise AssertionError("PM verification forbids network")

socket.socket.connect = deny_network
socket.create_connection = deny_network
import gen_decide_registry_ts as gen
import decision_points as dpts
import decision_context as ctx
import test_decide_registry_ts_lock as lock

for module in (gen, dpts, ctx, lock):
    assert pathlib.Path(module.__file__).resolve().is_relative_to(WT)
assert gen._REPO_ROOT == WT
assert gen.output_path() == WT / gen.OUTPUT_RELATIVE_PATH

if sys.argv[1] == "tests":
    import pytest
    raise SystemExit(pytest.main(["-p", "no:cacheprovider", "-q", str(MW / "test_decide_registry_ts_lock.py")]))

snapshot = dpts.registry_snapshot()
entries = lock._generated_entries()
retired = lock._literal_after(lock.RETIRED_ANCHOR)
result = {
    "imports": {m.__name__: str(pathlib.Path(m.__file__).resolve()) for m in (gen, dpts, ctx, lock)},
    "repo_root": str(gen._REPO_ROOT),
    "output_path": str(gen.output_path()),
    "active_ids": list(entries),
    "retired_ids": [r["id"] for r in retired],
    "ts_bytes_equal_fresh_render": gen.output_path().read_bytes() == gen.render().encode("utf-8"),
    "json_bytes_equal_snapshot": (MW / "decide_registry.json").read_bytes() == dpts.registry_snapshot_text().encode("utf-8"),
}
assert result["ts_bytes_equal_fresh_render"] and result["json_bytes_equal_snapshot"]
assert tuple(entries) == dpts.ACTIVE_DP_IDS
expected_retired = [{"id": r["id"], "tier": r["tier"], "description": r["description"], "disposition": r["disposition"], "migratedTo": r["migrated_to"], "note": r["note"]} for r in snapshot["retired"]]
assert retired == expected_retired
result["retired_full_field_parity"] = True
result["field_count"] = sum(len(p.get(k, [])) for p in snapshot["points"] for k in ("required_state_fields", "optional_state_fields"))
result["roles"] = {k: v["roleScope"] for k,v in entries.items()}
result["slots"] = {k: v["contextSlots"] for k,v in entries.items()}

# Invoke the existing real assertion with ONLY its directory listing replaced.
# No extra file, T05 generation, business request or product write is performed.
class Case:
    def __init__(self, name, body):
        self.name = name
        self.body = body
    def read_bytes(self):
        return self.body
    def __lt__(self, other):
        return self.name < other.name

real_glob = pathlib.Path.glob
old_cases = sorted((MW / "decide_cases").glob("dp*.json"))
assert len(old_cases) == 4
synthetic_listing = [Case(p.name, p.read_bytes()) for p in old_cases] + [Case(dp + ".json", b"synthetic listing only; NOT a generated case") for dp in dpts.ACTIVE_DP_IDS]
def glob_with_future_cases(path, pattern, *args, **kwargs):
    if path == MW / "decide_cases" and pattern == "dp*.json":
        return iter(synthetic_listing)
    return real_glob(path, pattern, *args, **kwargs)

with patch.object(pathlib.Path, "glob", glob_with_future_cases):
    try:
        lock.test_check_and_stdout_modes_write_nothing()
    except AssertionError as exc:
        result["post_t05_synthetic_listing"] = {"kind": "synthetic directory listing, not actual T05 generation", "entries": len(synthetic_listing), "accepted": False, "error": str(exc), "traceback": traceback.format_exc()}
    else:
        result["post_t05_synthetic_listing"] = {"entries": len(synthetic_listing), "accepted": True}
assert result["post_t05_synthetic_listing"]["accepted"] is False
(HERE / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
