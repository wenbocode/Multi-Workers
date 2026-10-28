"""Fresh PM evidence, no source/test/generated writes and no worker evidence edits."""
from __future__ import annotations
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
ROOT = KEY.parents[1]
WT = KEY/"implementation-worktree"
MW = WT/"packages/multi-workers"
BASE = HERE.parent/"t04-r2-pre-dispatch-20261026"
WORKER = HERE.parent/"dpc-t04-context-ts-generation/rework-r2"
OLD_WORKER = WORKER.parent
TEST = "packages/multi-workers/test_decide_registry_ts_lock.py"
assert sys.dont_write_bytecode
assert not (HERE/"check.json").exists(), "refuse evidence overwrite"
def sha(body):
    return hashlib.sha256(body).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
base = json.loads((BASE/"check.json").read_text(encoding="utf-8"))
old = json.loads((BASE/"mirror-inventory.json").read_text(encoding="utf-8"))
current = inventory(WT)
assert current.keys()==old.keys()
changed = sorted(k for k in old if old[k]!=current[k])
assert changed==[TEST]
history = json.loads((BASE/"original-t04-evidence-inventory.json").read_text(encoding="utf-8"))
current_history = {k:v for k,v in inventory(OLD_WORKER).items() if not k.startswith("rework-r2/")}
assert current_history==history
worker_before = (WORKER/"before/allowed-test.bytes.py").read_bytes()
worker_after = (WORKER/"after/allowed-test.bytes.py").read_bytes()
before = (BASE/"before-bytes"/TEST).read_bytes()
body = (WT/TEST).read_bytes()
assert before==worker_before and body==worker_after
assert sha(body)=="26eb0493164bd4ae28c6d1c86b770eaa7d09e4aad90c715009c9262e704c26a2"
diff = list(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True),body.decode("utf-8").splitlines(keepends=True),fromfile="a/"+TEST,tofile="b/"+TEST))
full_diff = "".join(diff).encode("utf-8")
assert full_diff == (WORKER/"after/full.diff").read_bytes()
(HERE/"pm-full.diff").write_bytes(full_diff)
# Preserve every old test definition except the authorized boundary body.
before_ast = ast.parse(before.decode("utf-8"))
after_ast = ast.parse(body.decode("utf-8"))
original_tests = {n.name:ast.dump(n) for n in before_ast.body if isinstance(n,ast.FunctionDef) and n.name.startswith("test_")}
new_tests = {n.name:ast.dump(n) for n in after_ast.body if isinstance(n,ast.FunctionDef) and n.name.startswith("test_")}
for name,definition in original_tests.items():
    assert name in new_tests
    if name != "test_check_and_stdout_modes_write_nothing":
        assert definition==new_tests[name], name
assert not list(WT.rglob("conftest.py"))
assert not list(WT.rglob("__pycache__"))
assert not list(WT.rglob("*.pyc"))
rows=[]
for row in base["files"]:
    rel=row["path"]
    data=(WT/rel).read_bytes()
    live=(ROOT/rel).read_bytes()
    assert live==(BASE/"live-before-bytes"/rel).read_bytes()
    assert not os.path.samefile(WT/rel,ROOT/rel)
    if rel!=TEST:
        assert data==(BASE/"before-bytes"/rel).read_bytes()
    dest=HERE/"after-bytes"/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(data)
    rows.append({"path":rel,"sha256":sha(data),"bytes":len(data),"crlf":data.count(b"\r\n"),"bare_lf":data.count(b"\n")-data.count(b"\r\n"),"live_baseline_matches":True,"samefile_live":False})
# Source was read to EOF in this PM turn; these checks also bind actual script.
generator = MW/"scripts/gen_decide_registry_ts.py"
source=generator.read_text(encoding="utf-8")
ast.parse(source)
assert generator.resolve().parent.parent.parent.parent==WT
assert "_REPO_ROOT = _MW_ROOT.parent.parent" in source
assert "if args.check:" in source and "if args.stdout:" in source
for name in ("home","temp","project","python"):
    (HERE/"fixture"/name).mkdir(parents=True,exist_ok=True)
(HERE/"fixture/python/sitecustomize.py").write_text("import socket\ndef denied(*args, **kwargs):\n    raise AssertionError('PM verification forbids network')\nsocket.socket.connect = denied\nsocket.socket.connect_ex = denied\nsocket.create_connection = denied\n",encoding="utf-8")
env={k:os.environ[k] for k in ("PATH","SYSTEMROOT","WINDIR","COMSPEC") if k in os.environ}
env.update({"PYTHONDONTWRITEBYTECODE":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8","PYTHONPATH":str(HERE/"fixture/python"),"HOME":str(HERE/"fixture/home"),"USERPROFILE":str(HERE/"fixture/home"),"TEMP":str(HERE/"fixture/temp"),"TMP":str(HERE/"fixture/temp")})
commands=[]
def run(label,args):
    argv=[sys.executable,"-B",*args]
    start=datetime.now(timezone.utc).isoformat()
    p=subprocess.run(argv,cwd=MW,env=env,capture_output=True)
    (HERE/(label+".stdout")).write_bytes(p.stdout)
    (HERE/(label+".stderr")).write_bytes(p.stderr)
    (HERE/(label+".log")).write_bytes(f"argv={argv!r}\ncwd={MW}\nstarted={start}\nrc={p.returncode}\n--- stdout ---\n".encode()+p.stdout+b"\n--- stderr ---\n"+p.stderr)
    commands.append({"label":label,"argv":argv,"started_at":start,"ended_at":datetime.now(timezone.utc).isoformat(),"rc":p.returncode})
    assert p.returncode==0,label
    return p
run("pm-green",[str(HERE/"probe.py"),"tests"])
run("pm-probe",[str(HERE/"probe.py"),"probe"])
checked=run("pm-generator-check",[str(generator),"--check"])
assert checked.stdout==checked.stderr==b""
printed=run("pm-generator-stdout",[str(generator),"--stdout"])
ts=(WT/"packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts").read_bytes()
assert printed.stdout.replace(b"\r\n",b"\n")==ts
assert inventory(WT)==current,"PM verification wrote to mirror"
assert {k:v for k,v in inventory(OLD_WORKER).items() if not k.startswith("rework-r2/")}==history
result={"observed_at":datetime.now(timezone.utc).isoformat(),"files":rows,"mirror_before":len(old),"mirror_after":len(current),"changed":changed,"original_t04_evidence_files":len(history),"original_evidence_unchanged":True,"worker_before_after_bytes_match":True,"worker_full_diff_matches":True,"diff_hunks":sum(x.startswith("@@") for x in diff),"diff_added_lines":sum(x.startswith("+") and not x.startswith("+++") for x in diff),"diff_removed_lines":sum(x.startswith("-") and not x.startswith("---") for x in diff),"original_test_definitions_preserved":True,"added_test_function_names":sorted(new_tests.keys()-original_tests.keys()),"stdout_exact_bytes":printed.stdout==ts,"stdout_eol_equivalent":True,"commands":commands,"minimal_environment_keys":sorted(env),"mirror_unchanged_by_pm_verification":True,"current_pyc_absent":True,"worker_reported_transient_pyc_violation":True,"manual_writer_absence_proven":False,"whole_live_tree_clean_proven":False,"ts_compile_verified":False,"product_writes_by_pm":False}
(HERE/"check.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False,indent=2))
