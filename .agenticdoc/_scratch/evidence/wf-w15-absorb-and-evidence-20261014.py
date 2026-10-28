"""Record plan.md 7.11 (W-15 absorption) and append PASS evidence rows to pm-state.md."""

import pathlib

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
PLAN = ROOT / ".agenticdoc/mw-write-face-guard/plan.md"
STATE = ROOT / ".agenticdoc/mw-write-face-guard/pm-state.md"

ADD = """
### 7.11 W-15 终态吸收（AC-006 收口，PM 独立复核，2026-10-14）

- **PM 自跑复核（全部与 worker 自报一致）**：`test/test_write_face_doctor.py` **15 passed**；既有 `test_write_face.py`+`test/test_write_face_dispatch.py`+`test/test_write_face_e2e.py` **166 passed**；相邻 doctor 面 7 个套件 **155 passed**（87s，我复跑）；`python mw.py doctor --project H:/git/Multi-Workers --json` 的 `write_face` 段 = `{"total":0,"by_code":{},"by_source":{"conductor":0,"pm":0},"recent":[]}`，`summary.issues` 里**只有**预先存在的 `STALE CODE`（活动 serve PID 151032 落后工作树代码），`write_face` 不入 issues。
- **PM 读码核对只读纪律**：新增 5 个函数（`_write_face_detail_parts` / `_parse_write_face_event` / `_parse_write_face_ledger_row` / `_doctor_write_face` / `_format_write_face_doctor_line`）逐个体检**零** `write_text`/`open(...,"w")`/`acquire_lock`/`summary[...]`/`issues.append`/`mkdir` 命中；挂载点只有 `mw.py:621`（`report["write_face"] = ...`）与 `:641`（非 `--json` 打印）。⇒ AC-006 的"只读面 + 0 不报错 + 不进 issues"三项成立。
- **本仓库 `mw doctor` 退出码 = 1 的口径**：唯一 issue 是 `STALE CODE`（另一 session 的活动 serve 落后于工作树），与写面无关；worker 用"干净项目 + live pid + 3 条拒绝"证明同一 CLI 路径在 N=3 时仍 **exit 0 / healthy / 不入 issues**。⇒ PM 判定：**不影响 AC-006 判定**（AC-006 要的是"显示 0 而非报错"，本仓库的 1 来自别的既有 issue；写面段自身恒不产 issue）。
- **新残留（PM 记录，接受）**：① `mw doctor --json` 的 `write_face` 段**目前无 TS 侧消费者**（`/mw doctor` 只透传 JSON），要接线进 UI 属另一面；② `recent` 的跨源定序口径——conductor 事件有秒级 `ts`，PM ledger 行**没有 `ts`**，PM 行按"最旧"参与并集（仅在时间戳事件不足 5 条时占窗）；③ 读不出的 `code` 归 `unknown` 桶但**仍计数**。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.11 W-15 终态吸收" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended 7.11")
else:
    print("plan: already has 7.11")

ROWS = """| 日期 | 命令 / 判据 | 结果 | 对应 AC/VC |
|------|------------|------|-----------|
| 2026-10-14 | `python -m pytest test_write_face.py test/test_write_face_dispatch.py test/test_write_face_e2e.py -q` | **PASS** — 166 passed（130+29+7） | AC-001/002/005/007/008/012/014 |
| 2026-10-14 | `node vitest --run test/suite/write-face.test.ts`（PM 亲跑） | **PASS** — 113 passed | AC-001/002/007 |
| 2026-10-14 | `node vitest --run test/suite/write-face-pm-gate.test.ts`（PM 亲跑） | **PASS** — 25 passed（含跨通道 reason 逐字节） | AC-003/007 |
| 2026-10-14 | `node vitest --run test/suite/write-face-runtime.test.ts` | **PASS** — 18 passed（write/edit + bash 两路径） | AC-004/010/011/013 |
| 2026-10-14 | `node vitest --run test/suite/mwds-t03-bash-write-scope.test.ts` | **PASS** — 63 passed（VC-024 新口径重写） | AC-004/011/013, VC-024 |
| 2026-10-14 | `node vitest --run test/suite/write-face-e2e.test.ts test/suite/mwds-t03-*.test.ts` | **PASS** — 71 passed | AC-005/007/013 |
| 2026-10-14 | B3 双通道装置：82 行语料 × 5 字段 | **PASS** — 410 次对照 0 不一致；base 错对齐 before=4 → 对齐 after=0 | AC-002/007 |
| 2026-10-14 | AC-005 反证：绕过闸门直写队列行后复算 | **PASS** — 实派 0 对 → 绕过 1 对（检测器不自证） | AC-005/012 |
| 2026-10-14 | `python -m pytest test/test_write_face_doctor.py -q`（PM 亲跑） | **PASS** — 15 passed | AC-006 |
| 2026-10-14 | `python mw.py doctor --project H:/git/Multi-Workers --json` | **PASS** — `write_face.total=0`，不进 issues（唯一 issue 是既有 STALE CODE） | AC-006 |
| 2026-10-14 | 干净项目 + live pid + 3 条拒绝：`mw.py doctor --json` | **PASS** — exit 0 / healthy / `total=3` | AC-006 |
| 2026-10-14 | `python -m pytest` 相邻 doctor 7 套件（PM 亲跑） | **PASS** — 155 passed | AC-006（相邻面） |
| 2026-10-14 | `npx tsgo --noEmit` | **PASS** — exit 0 | AC-004/007/011 |
| 2026-10-14 | PM 读码：`dispatch.py` 取锁 `:1435` → task.md `:1461/:1462` → 队列行 `:1478` | **PASS** — 全在锁内 | AC-014 |
| 2026-10-14 | PM 探针：面内/面外 bash 写目标（含面内目录目标、`..` 逃逸、仓外绝对） | **PASS** — 真写族拦、假写族 0 误拦 | AC-004/013 |
| 2026-10-14 | `python .agents/skills/agentic-task/scripts/audit_phase.py mw-write-face-guard` | **PASS** — design/plan/tasks/execute 四门 PASS | 相位门 |
"""

state = STATE.read_text(encoding="utf-8")
placeholder = "## 3. Evidence Ledger\n*(empty)*"
if "write-face.test.ts" in state:
    print("pm-state: evidence rows already present")
elif placeholder in state:
    state = state.replace(placeholder, "## 3. Evidence Ledger\n" + ROWS)
    STATE.write_text(state, encoding="utf-8")
    print("pm-state: ledger rows written")
else:
    print("pm-state: PLACEHOLDER NOT FOUND — not modified")
print(f"pm-state bytes={STATE.stat().st_size}")
