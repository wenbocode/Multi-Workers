"""Independent PM read-only test/projection probe; no generation writes."""
from __future__ import annotations
import importlib.util
import json
import pathlib
import socket
import sys

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[2]
WT = KEY / "implementation-worktree"
MW = WT / "packages/multi-workers"
def denied(*args, **kwargs):
    raise AssertionError("PM verification forbids network")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
assert sys.dont_write_bytecode
sys.path.insert(0,str(MW))
sys.path.insert(0,str(MW / "scripts"))
if sys.argv[1] == "tests":
    import pytest
    raise SystemExit(pytest.main(["-p","no:cacheprovider","-q",str(MW/"test_decide_registry_ts_lock.py"),"--basetemp",str(HERE/"fixture/temp/pytest")]))
import decision_context
import decision_points as dpts
import gen_decide_registry_ts as gen
spec = importlib.util.spec_from_file_location("pm_t04_r2",MW/"test_decide_registry_ts_lock.py")
assert spec and spec.loader
lock = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lock
spec.loader.exec_module(lock)
for module in (decision_context,dpts,gen,lock):
    assert pathlib.Path(module.__file__).resolve().is_relative_to(WT)
assert gen._REPO_ROOT == WT and gen.output_path() == WT/gen.OUTPUT_RELATIVE_PATH
assert gen.output_path().read_bytes() == gen.render().encode("utf-8")
assert (MW/"decide_registry.json").read_bytes() == dpts.registry_snapshot_text().encode("utf-8")
entries = lock._generated_entries()
assert tuple(entries) == dpts.ACTIVE_DP_IDS and len(entries)==8
assert lock.LEGACY_CASE_FILES == ("dp1.json","dp2.json","dp3.json","dp25.json")
assert lock.ACTIVE_CASE_FILES == tuple(x+".json" for x in dpts.ACTIVE_DP_IDS)
retired = lock._literal_after(lock.RETIRED_ANCHOR)
assert len(retired)==25
assert retired == [{"id":r["id"],"tier":r["tier"],"description":r["description"],"disposition":r["disposition"],"migratedTo":r["migrated_to"],"note":r["note"]} for r in dpts.registry_snapshot()["retired"]]
result = {"imports_copy_local":True,"output_root_copy_local":True,"ts_actual_disk_bytes_equal_render":True,"json_actual_bytes_equal_snapshot":True,"active_ids":list(entries),"retired_full_field_parity":True,"legacy_exact_names":list(lock.LEGACY_CASE_FILES),"active_case_names":list(lock.ACTIVE_CASE_FILES),"network_forbidden":True,"t05_business_generation_run":False,"ts_compile_run":False}
(HERE/"probe.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False,indent=2))
