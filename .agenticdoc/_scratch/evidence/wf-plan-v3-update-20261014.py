"""Update mw-write-face-guard/plan.md: refresh the frozen-corpus fingerprint to v3
and append the third-round execution record (V58 + the two fix cards + the
wfg-i03 incident pointer)."""

import hashlib
import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")
OLD_SHA = "sha256=1ca66a899fcc2041b477bf7be79791345026b652a23e6ca3e96849bb82a6b530"
NEW_SHA = "sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62"

SECTION = """

## 7. 执行记录（2026-10-14 第三轮：语料 v3 + 两张修正卡）

- **语料 v3 冻结**：`packages/multi-workers/test/fixtures/write-face-corpus.json` 现为 `sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`、`bytes=19996`、`counts={parse:23, overlap:59}`（kind 直方图 overlap 34 / none 13 / reject 8 / serial_only 1 / unsupported 3）。新增行 **V58**（`[huge, "src/x.ts"]` × 同，`huge="x/"*300+"x"`，601 字符）锁的是 D-111 overlap 期"状态机回退只延迟那一对、不中止整轮"。补丁脚本（可复核、含 `--check`）：`_scratch/evidence/wf-corpus-v58-20261014.py`（另有两次 trailing-comma 修复脚本 `wf-corpus-v58-repair-20261014.py` / `-repair2-`）。
- **V58 两侧实测**（`_scratch/evidence/wf-v58-probe-20261014.py` + `wf-v58-ts-out.json`）：TS `Conflict sample="src/x.ts"`（109 passed，已把 TS 测试计数同步到 23/59）；Python 现状 `Unsupported(glob-product-state-limit)` ⇒ 修复前基线 `python -m pytest test_write_face.py -q` = **2 failed, 127 passed**。
- **W-03 收尾**：任务真身（pid 95260）34 分钟后正常 `done`，交付完整（`test/test_write_face_dispatch.py` 25 passed、`evidence/W-03-dispatch-refusal.md` 19,849 B 存在）。**但该任务被重复激活 12 次**，把 12 块假 `failed` 写进 `output.md`，一度误导 PM。完整取证与 RF-1..RF-4 待修项见 `_scratch/evidence/wfg-i03-duplicate-activation-20261014.md` + `_pitfalls.md` P-034；**属框架级缺陷，不在本 key 的处理面**（需要独立 key：激活期唯一性闸 / run.json 写前置条件 / 产物归属校验 / 重复激活告警）。
- **第三轮两张卡（并行、写面不相交）**：
  - `T-W-I06-operator-py-defer`（W-06）：`autopilot/write_face.py` + `test_write_face.py`——按对延迟 + 冲突优先 + 与 TS `writeFacesOverlap` 同族；验收 `129 passed`。
  - `T-W-I07-render-comma-safe`（W-07）：`autopilot/dispatch.py` + `test/test_write_face_dispatch.py`——D-113 含逗号条目回退块列表载体，锁 `parse(render(E)) == E`（含 16 条语料的往返锁 + 真实 dispatch 端到端）；验收 ≥28 passed。
- 两张卡都过了 spawn 阶段自检（`inspect_envelope` + `type_extras_missing` 均空 + 种子 `goal.md` 与 `name.ext:NNN` 齐备，见 `_scratch/evidence/precheck-cards-20261014.py`）。
"""

raw = PLAN.read_text(encoding="utf-8")
assert OLD_SHA in raw, "v2 fingerprint not found"
assert "overlap:58}" in raw and "bytes=17812" in raw, "counts/bytes anchor missing"
assert "overlap 33 / none 13" in raw, "histogram anchor missing"
patched = raw.replace(OLD_SHA, NEW_SHA)
patched = patched.replace("bytes=17812", "bytes=19996")
patched = patched.replace("overlap:58}", "overlap:59}")
patched = patched.replace("overlap 33 / none 13", "overlap 34 / none 13")
if "## 7. 执行记录（2026-10-14 第三轮" not in patched:
    patched = patched.rstrip() + "\n" + SECTION
PLAN.write_text(patched, encoding="utf-8")
print("plan lines", len(patched.splitlines()), "bytes", len(patched.encode("utf-8")))
print("new sha present:", NEW_SHA in patched, "| v3 counts:", "overlap:59}" in patched)
print("section 7 added:", "## 7. 执行记录（2026-10-14 第三轮" in patched)
print("plan sha256", hashlib.sha256(patched.encode("utf-8")).hexdigest())
