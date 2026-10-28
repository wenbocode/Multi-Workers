"""Fresh PM evidence only. No source writes, generation writes or service calls."""
from __future__ import annotations
import ast
import difflib
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[2]
ROOT = KEY.parents[1]
WT = KEY / "implementation-worktree"
MW = WT / "packages/multi-workers"
BASE = HERE.parent / "t04-pre-dispatch-20261026"
WORKER = HERE.parent / "dpc-t04-context-ts-generation"
assert not (HERE / "check.json").exists(), "refuse evidence overwrite"
baseline = json.loads((BASE / "check.json").read_text(encoding="utf-8"))
after = json.loads((WORKER / "after/after-manifest.json").read_text(encoding="utf-8"))
allowed = {r["path"] for r in baseline["files"]}
expected = {r["path"]:r for r in after["files"]}
def sha(data):
    return hashlib.sha256(data).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
old = json.loads((BASE / "mirror-inventory.json").read_text(encoding="utf-8"))
current = inventory(WT)
added = sorted(current.keys() - old.keys())
removed = sorted(old.keys() - current.keys())
changed = sorted(k for k in old.keys() & current.keys() if old[k] != current[k])
assert not added and not removed
assert set(changed) <= allowed
rows = []
full_diff = []
for row in baseline["files"]:
    rel = row["path"]
    before = (BASE / "before-bytes" / rel).read_bytes()
    body = (WT / rel).read_bytes()
    live = (ROOT / rel).read_bytes()
    assert sha(before) == row["sha256"]
    assert sha(body) == expected[rel]["after_sha256"]
    assert body == (WORKER / "after" / rel).read_bytes()
    assert sha(live) == row["live_sha256"]
    assert not os.path.samefile(WT / rel, ROOT / rel)
    dest = HERE / "after-bytes" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    assert dest.read_bytes() == body
    diff = list(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True), body.decode("utf-8").splitlines(keepends=True), fromfile="before/"+rel, tofile="after/"+rel))
    if diff:
        full_diff.extend(diff)
        full_diff.append("\n")
    rows.append({"path":rel,"sha256":sha(body),"bytes":len(body),"crlf":body.count(b"\r\n"),"bare_lf":body.count(b"\n")-body.count(b"\r\n"),"diff_hunks":sum(x.startswith("@@") for x in diff),"before_matches":True,"worker_after_matches":True,"live_baseline_matches":True,"samefile_live":False})
# Match worker separator convention: one blank line between files, none after EOF.
(HERE / "pm-full.diff").write_bytes("".join(full_diff[:-1]).encode("utf-8"))
worker_diff = (WORKER / "after/changed-files.diff").read_bytes()
assert (HERE / "pm-full.diff").read_bytes() == worker_diff
# Statically inspected generator path arithmetic and CLI branches; AST validity
# is not TS compilation. Fail before any import/execution on path mismatch.
generator = MW / "scripts/gen_decide_registry_ts.py"
source = generator.read_text(encoding="utf-8")
ast.parse(source)
assert generator.resolve().parent.parent.parent.parent == WT
assert '_REPO_ROOT = _MW_ROOT.parent.parent' in source
assert 'path = output_path()' in source
assert 'if args.check:' in source and 'if args.stdout:' in source
assert not list(WT.rglob("conftest.py"))
for name in ("home", "temp", "project"):
    (HERE / "fixture" / name).mkdir(parents=True, exist_ok=True)
env = {k:os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC") if k in os.environ}
env.update({"PYTHONDONTWRITEBYTECODE":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONIOENCODING":"utf-8","PYTHONUTF8":"1","HOME":str(HERE/"fixture/home"),"USERPROFILE":str(HERE/"fixture/home"),"TEMP":str(HERE/"fixture/temp"),"TMP":str(HERE/"fixture/temp")})
commands = []
def run(label, args):
    argv = [sys.executable, *args]
    started = datetime.now(timezone.utc).isoformat()
    p = subprocess.run(argv, cwd=MW, env=env, capture_output=True)
    (HERE / (label+".stdout")).write_bytes(p.stdout)
    (HERE / (label+".stderr")).write_bytes(p.stderr)
    log = f"argv={argv!r}\ncwd={MW}\nstarted={started}\nrc={p.returncode}\n--- stdout ---\n".encode()+p.stdout+b"\n--- stderr ---\n"+p.stderr
    (HERE / (label+".log")).write_bytes(log)
    commands.append({"label":label,"argv":argv,"started_at":started,"ended_at":datetime.now(timezone.utc).isoformat(),"rc":p.returncode})
    assert p.returncode == 0, label
    return p
run("pm-green", [str(HERE/"probe.py"), "tests"])
run("pm-probe", [str(HERE/"probe.py"), "probe"])
checked = run("pm-generator-check", [str(generator), "--check"])
assert checked.stdout == b"" and checked.stderr == b""
printed = run("pm-generator-stdout", [str(generator), "--stdout"])
# argv --stdout writes evidence capture only; compare exact bytes.
gen_rel = "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts"
stdout_expected = (WT / gen_rel).read_bytes()
stdout_exact_bytes = printed.stdout == stdout_expected
assert printed.stdout == stdout_expected.replace(b"\n", b"\r\n") if os.name == "nt" else stdout_exact_bytes
assert inventory(WT) == current, "PM verification wrote into mirror"
assert not list(WT.rglob("__pycache__"))
result = {"observed_at":datetime.now(timezone.utc).isoformat(),"files":rows,"mirror":{"before":len(old),"after":len(current),"added":added,"removed":removed,"changed":changed,"changed_outside_write_face":sorted(set(changed)-allowed)},"worker_full_diff_matches":True,"stdout_exact_bytes":stdout_exact_bytes,"stdout_windows_text_eol_equivalent":printed.stdout.replace(b"\r\n",b"\n")==stdout_expected,"commands":commands,"minimal_environment_keys":sorted(env),"mirror_unchanged_by_pm_verification":True,"manual_writer_absence_proven":False,"ts_compilation_verified":False,"semantic_handoff_verified":False,"blocker":"new lock test globs all dp*.json then permanently asserts 4; authorized T05 adds 8 cases; synthetic real-assertion probe refuses lawful 12-case listing","product_writes_by_pm":False}
(HERE / "check.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False,indent=2))
