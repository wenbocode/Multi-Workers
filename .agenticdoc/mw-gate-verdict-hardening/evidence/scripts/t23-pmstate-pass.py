"""pm-state: D-061 quality-gate PASS (needed by the done gate) + process log."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

d60 = next(i for i, l in enumerate(lines) if l.startswith("- D-060（2026-10-10 19:25）"))
lines.insert(
    d60 + 1,
    "- D-061（2026-10-10 19:40）：**质量门 = PASS（verify → done 放行）**。"
    "报告 `evidence/quality-gate-report-20261010.md`（25 AC 矩阵 + 47 VC 矩阵 + 19 条非空洞对照索引 + 未验证清单 + 残留去向 + 复现命令）。"
    "证据基线（PM 本人复跑，非复用 worker 输出）：Python 全量 **2 failed / 1523 passed / 10 deselected**（两红=`verify-baseline.md` 同名同集合，**新增红 = 0**）；"
    "TS 13 suite **340 passed**；`npm run check` **exit 0**；G3 端到端 `evidence/scripts/pm-g3-live-check.py` 6 项全绿。"
    "**AC 25/25 PASS、VC 47/47 PASS（源码+测试级）**。结案口径诚实标注：**运行时未切换 ⇒ 本轮改动尚未在运行中生效**（R21），"
    "故 done 不代表已上线；`achieved.md` 的「遗留」逐项给出 R18/R19/R20/R21/D-038 与去向。"
    "PASS 判据不含“已被运行时观测”，只含源码 + 测试 + 独立端到端脚本三项。",
)

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 19:25：**T-16 done + acked"))
lines.insert(
    i + 1,
    "- 10-10 19:40：**verify 阶段质量门 = PASS**（`evidence/quality-gate-report-20261010.md`；PM 复跑 Python 2 failed/1523 passed（新增红 0）、"
    "TS 340 passed、`npm run check` exit 0、G3 端到端 6/6）；写 `achieved.md`（含「系统行为变化」/「遗留」）并 `advance_phase(done)`。记 D-061。"
    "**唯一未生效项**：运行时切换（R21，runbook 已就绪，待用户批准）。",
)

na = next(i for i, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: **本 key 已 done**（T-01~T-23 全部核销；质量门 PASS，`achieved.md` + `evidence/quality-gate-report-20261010.md` 已落）。"
    "**done 不代表已上线**：唯一未生效项 = 运行时切换（R21）——runbook `evidence/runs/runtime-cutover-runbook.md`（含 bundle sha256 `52187720…`、"
    "9 个 pre-11:40 窗口 PID、验证与回滚）**待用户批准后由 PM 直执**：`mw build --install --allow-dirty` + 重启 launcher/serve + 一律重启那 9 个窗口。"
    "**其它待用户决定**：R18 是否单开小卡；T-23 `--force` 语义是否认可；E2Feature reflect 台账是否回写（本 key 已实现其根因修复）。"
    "**残留**：R18（spawn 竞态不得静默判终态）、R19（错过边界的 key 无锚）、R20（`monitorCtx`）、R21（运行时切换）、D-038（`dispatch.py` 未接 `run.json`）。"
)
upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 19:40"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok, PASS count now:", "\n".join(lines).count("PASS"))
