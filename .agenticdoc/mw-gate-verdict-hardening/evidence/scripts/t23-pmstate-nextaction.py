"""Refresh pm-state Next Action + Updated stamp."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

na = next(i for i, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: **D-014 已解除 ⇒ 恢复 worker 派发；波 0~2 已全部核销**"
    "（T-01/T-02/T-03/T-04/T-05/T-06/T-07/T-08/T-09/T-10/T-11/T-13 done+acked；"
    "T-08b = 假 failed 引发的重复派发，PM 已止损终止）。"
    "**当前在跑 = T-12**（G3 gate-writer `--authorizes` 闭集 + G4 `autoStartMonitor` 重臂，含 T-04 R1 的 TS 镜像硬要求）"
    "**+ T-23**（AC-025：G3 锚点建立——`mw autopilot contract-freeze` CLI + conductor 在 design/plan 边界自动锚 + `contract-frozen` 留痕；"
    "写面零重叠：TS vs `mw.py`+`conductor.py`）。"
    "**既定顺序**：T-12 / T-23 → **T-14**（计数锁与语料重冻：timeline **23→27**、TS `EVENT_TYPES` += `contract-frozen`、"
    "`reason_code` 12→14、配置键 17→20；卡已追记）→ **T-16**（重建 `dist`/bundle = 运行时切换，届时 T-15/T-17/T-18/T-19/T-20/T-21/T-22 与 T-01~T-14 的改动才真正生效）。"
    "**每次派发后必须跑一遍** `evidence/scripts/t23-normalize-whole-queue.py`（运行时装 bundle 的全表 9 列重写，D-046；"
    "证据 `evidence/runs/t23-runtime-writeback-observation.md`）。"
    "**待用户决定**：① 运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）；"
    "② 残留 R18（spawn 竞态下“刚派发的行不得被静默判终态”）是否单独开卡。"
    "**已知残留**：R18（同上）、R19（错过 design/plan 边界的 key 无锚 ⇒ 需人显式 `mw autopilot contract-freeze`）、"
    "D-038（`autopilot/dispatch.py` 未接 `run.json`）。"
)
upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 18:55"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok", lines[na][:60], "|", lines[upd])
