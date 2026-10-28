"""Append MDC plan §7.3: M-05 TS half absorption (PM verification)."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\plan.md")

ADD = """
### 7.3 M-05 TS 半边吸收（VC-107 面板三量 + VC-108 两侧 parity；PM 独立复核，2026-10-14）

- **卡**：`tasks/T-C-M05-tests-ts.md`；**只新增一个测试文件**，零生产改动：`packages/coding-agent/test/suite/autopilot-concurrency-panel.test.ts`（405 行）。
- **PM 亲跑（三条验收命令全绿，与自报一致）**：新文件 **4 passed**；四文件联跑（新文件 + `config-parity` + `config-sync` + `monitor`）**36 passed**；`npx tsgo --noEmit` **exit 0**。
- **"没偷改生产代码"的独立证据（比口头声明硬）**：`monitor.ts` mtime `16:35:09`、`status-model.ts` `16:31:43`、`shared/worker-store.ts` `12:26:06`，**均早于该 worker 的起跑时刻（本地 17:27）** ⇒ 本卡未触碰生产文件。
- **测试诚实性（PM 读码判定，防自证）**：文件直接 import 真实 `readMonitorState`/`renderMonitorLines`/`validateConfigData`/`DEFAULT_CONFIG`/`INT_RANGES`；期望值**推导**而非写死（`cap ∈ {8,1}` 循环 + `slotsEffective === min(slotsCap, frontierSize)` 双向断言）；边界正反例都断言了**反事实**（`pending` 行 `inFlight=0` 却占槽、`manual` 行可见为 worker 但 `slotsUsed=0`、终态行释放）；语料具名 case 用 `requireCase` **fail-closed**（缺 case 直接抛错，不是静默跳过）；渲染行逐字比对 `autopilot: cap C | eff E (frontier F)`。禁用模式 `.skip(`/`.only(`/`.todo(`/`xit(`/`xdescribe(` **0 命中**。
- **口径依据与 PM 先前结论一致**：README 注释即写明 `workerBelongsToKey` 内含 `origin === "conductor"`（D-019）⇒ `pending` 计入、`manual` 不占槽，与 Python `mw_common.row_belongs_to` 同形（正是 §7.1 我一度怀疑、实查后否掉的那条）。
- **残留（PM 判定）**：① 面板 `frontierSize` 仍是 conductor 真实 `|F|` 的上界（TS 不读 claim）——已在 spec/注释口径内，非本卡缺陷；② VC-108 **故意不**断言语料整体 sha256（避免重冻变脆），改断言具名 case 判决 + 两条非空反例（`range-max-parallel-below-floor` reject）⇒ 判据非空洞；③ 测试锚定的生产行号若后续迁移需同步（预期维护成本）。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.3" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended §7.3 (M-05 TS half)")
else:
    print("plan: §7.3 already present")
