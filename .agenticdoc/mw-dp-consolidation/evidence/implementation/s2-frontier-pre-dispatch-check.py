"""PM-only fresh original-DAG frontier baseline; no product imports or tests."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
KEY=Path(__file__).resolve().parents[2]
ROOT=KEY.parents[1]
WT=KEY/"implementation-worktree"
OUT=KEY/"evidence/implementation/s2-frontier-pre-dispatch-20261026"
assert not OUT.exists()
def sha(body):
    return hashlib.sha256(body).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
d=json.loads((KEY/"implementation-isolated-dag.json").read_text(encoding="utf-8"))
assert len(d["tasks"])==36 and len(d["stages"])==7
byid={t["id"]:t for t in d["tasks"]}
assert byid["T03"]["semantic_handoff_verified"] and byid["T04"]["semantic_handoff_verified"]
assert byid["T04"]["rework_attempt"]["status"]=="done"
assert byid["T04"]["rework_attempt"]["acked"]
old=json.loads((KEY/"evidence/implementation/t04-r2-pre-dispatch-20261026/mirror-inventory.json").read_text(encoding="utf-8"))
latest=json.loads((KEY/"evidence/implementation/t04-r2-pm-handoff-20261026/check.json").read_text(encoding="utf-8"))
for row in latest["files"]:
    old[row["path"]]=row["sha256"]
assert inventory(WT)==old
OUT.mkdir(parents=True)
rows=[]
allfaces=set()
for tid in ("T06","T07","T08"):
    t=byid[tid]
    assert t["status"]=="not-queued" and t["deps"]==["T03","T04"]
    card=KEY/t["card"]
    text=card.read_text(encoding="utf-8")
    front=text.split("write_face:\n",1)[1].split("ac_refs:",1)[0]
    face=[line.strip()[2:] for line in front.splitlines() if line.strip()]
    products=[x for x in face if "/implementation-worktree/" in x]
    assert not (set(products)&allfaces)
    allfaces.update(products)
    assert set(products)==set(t["product_write_face"])
    for section in ("type: coding","## 上下文","## 要求","## 交付格式","## 写入允许面","## 写入禁止面","## 验收命令","## 改动历史"):
        assert section in text
    copied=OUT/"cards"/(tid+".md")
    copied.parent.mkdir(parents=True,exist_ok=True)
    copied.write_bytes(card.read_bytes())
    files=[]
    for product in products:
        rel=product.split("/implementation-worktree/",1)[1]
        path=WT/rel
        live=ROOT/rel
        info={"path":rel,"exists":path.exists(),"live_exists":live.exists()}
        for label,p in (("before-bytes",path),("live-before-bytes",live)):
            if not p.exists():
                continue
            body=p.read_bytes()
            dest=OUT/label/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(body)
            info[label]={"sha256":sha(body),"bytes":len(body),"crlf":body.count(b"\r\n"),"bare_lf":body.count(b"\n")-body.count(b"\r\n")}
        if path.exists() and live.exists():
            assert not os.path.samefile(path,live)
            info["samefile_live"]=False
        p=subprocess.run(["git","diff","--",rel],cwd=ROOT,capture_output=True)
        assert p.returncode==0
        dest=OUT/"live-existing-diff"/(rel+".diff")
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(p.stdout)
        files.append(info)
    rows.append({"id":tid,"task_key":t["task_key"],"card":t["card"],"card_sha256":sha(card.read_bytes()),"write_face":face,"files":files})
(OUT/"mirror-inventory.json").write_text(json.dumps(old,indent=2)+"\n",encoding="utf-8")
result={"observed_at":datetime.now(timezone.utc).isoformat(),"tasks":rows,"mirror_files":len(old),"unordered_product_write_overlaps":0,"t03_t04_semantic_prerequisite_verified":True,"stage_is_plan_wave_not_live_autopilot":True,"product_tests_run":False,"product_writes":False,"manual_writer_absence_proven":False}
(OUT/"check.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False,indent=2))
