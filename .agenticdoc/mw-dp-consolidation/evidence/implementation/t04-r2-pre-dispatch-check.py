"""PM-only readonly baseline for authorized original-T04 test-only R2."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

KEY = Path(__file__).resolve().parents[2]
ROOT = KEY.parents[1]
WT = KEY / "implementation-worktree"
OUT = KEY / "evidence/implementation/t04-r2-pre-dispatch-20261026"
assert not OUT.exists(), "refuse overwrite"
CARD = KEY / "tasks/isolated/T04-context-ts-generation-r2.md"
OLD_CARD = KEY / "tasks/isolated/T04-context-ts-generation.md"
OLD_EVIDENCE = KEY / "evidence/implementation/dpc-t04-context-ts-generation"
PM = KEY / "evidence/implementation/t04-pm-handoff-20261026"
TEST = "packages/multi-workers/test_decide_registry_ts_lock.py"
def digest(body):
    return hashlib.sha256(body).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix():digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
check = json.loads((PM / "check.json").read_text(encoding="utf-8"))
expected = json.loads((KEY / "evidence/implementation/t04-pre-dispatch-20261026/mirror-inventory.json").read_text(encoding="utf-8"))
for row in check["files"]:
    expected[row["path"]] = row["sha256"]
assert inventory(WT) == expected, "mirror drift since PM handoff"
assert digest(OLD_CARD.read_bytes()) == "99c0fb85c70193313d734adc044e647c18c47976c72575ab77f35d1a85412200"
text = CARD.read_text(encoding="utf-8")
for section in ("type: coding", "## 上下文", "## 要求", "## 写入允许面", "## 写入禁止面", "## 验收命令", "## 改动历史", "## 交付格式", ".agenticdoc/goal.md:5"):
    assert section in text, section
face = text.split("write_face:\n",1)[1].split("ac_refs:",1)[0]
assert [line.strip()[2:] for line in face.splitlines() if line.strip()] == [".agenticdoc/mw-dp-consolidation/implementation-worktree/"+TEST,".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation/rework-r2/**"]
OUT.mkdir(parents=True)
rows = []
for row in check["files"]:
    rel = row["path"]
    body = (WT / rel).read_bytes()
    live = (ROOT / rel).read_bytes()
    assert body == (PM / "after-bytes" / rel).read_bytes()
    assert not os.path.samefile(WT / rel, ROOT / rel)
    for sub, data in (("before-bytes",body),("live-before-bytes",live)):
        path = OUT / sub / rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        assert path.read_bytes() == data
    diff = subprocess.run(["git","diff","--",rel],cwd=ROOT,capture_output=True)
    assert diff.returncode == 0
    path = OUT / "live-existing-diff" / (rel + ".diff")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(diff.stdout)
    rows.append({"path":rel,"sha256":digest(body),"bytes":len(body),"crlf":body.count(b"\r\n"),"bare_lf":body.count(b"\n")-body.count(b"\r\n"),"live_sha256":digest(live),"samefile_live":False,"writable":rel==TEST})
status = subprocess.run(["git","status","--short","--",*[r["path"] for r in check["files"]]],cwd=ROOT,capture_output=True)
assert status.returncode == 0
(OUT / "live-git-status.txt").write_bytes(status.stdout)
(OUT / "mirror-inventory.json").write_text(json.dumps(expected,indent=2)+"\n",encoding="utf-8")
history = inventory(OLD_EVIDENCE)
assert not any(name.startswith("rework-r2/") for name in history)
(OUT / "original-t04-evidence-inventory.json").write_text(json.dumps(history,indent=2)+"\n",encoding="utf-8")
(OUT / "card-before.md").write_bytes(CARD.read_bytes())
result = {"observed_at":datetime.now(timezone.utc).isoformat(),"files":rows,"mirror_files":len(expected),"card_sha256":digest(CARD.read_bytes()),"original_card_sha256":digest(OLD_CARD.read_bytes()),"original_t04_evidence_files":len(history),"write_face_verified":True,"product_tests_run":False,"product_writes":False,"manual_writer_absence_proven":False,"live_tree_clean_proven":False}
(OUT / "check.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2))
