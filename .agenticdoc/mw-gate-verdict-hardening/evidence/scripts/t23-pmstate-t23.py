"""pm-state: D-057 (T-23 done + PM live G3 E2E) + process log 19:05 + Next Action."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

d56 = next(i for i, l in enumerate(lines) if l.startswith("- D-056（2026-10-10 18:58）"))
lines.insert(
    d56 + 1,
    "- D-057（2026-10-10 19:05）：**T-23 完成 + G3 首次真正“活”起来（PM 亲测端到端）**。"
    "T-23 交付 `conductor.py::_freeze_contract_first_sight`（`:2644`，调用点 `:2768` = tick 的 **step 2c**，"
    "在 enabled/paused 检查（`:2761`）与 2b 提醒之后、step 3 goal 检测之前；未碰 L3 段与 `_done_transaction`）、"
    "`mw.py::_ap_contract_freeze`（`:3977`，argparse `:5691`）、`timeline.py::EVENT_TYPES += \"contract-frozen\"`（`:110`）、"
    "新测试 `test_autopilot_contract_freeze.py`（12 例）。PM 亲跑：新文件 **12 passed**；回归集（conductor/closure/contract_guard/cli/done_guard）"
    "**121 passed**。**PM 独立端到端（不经 worker 用例，脚本 `evidence/scripts/pm-g3-live-check.py`）**："
    "① Python `EVENT_TYPES` = **27** 且含 `contract-frozen`；② 临时项目跑 `mw autopilot contract-freeze --json` ⇒ `ac/written`（AC-001/002）+ `vc/written`；"
    "③ 再跑 ⇒ `unchanged` 且文件**字节不变**；④ 改写一条 AC ⇒ `evaluate.ok=False`、`changed_ids=('AC-001',)`、`no_anchor=False`"
    "（**G3 真活**：T-10 的 done 前守卫据此即可拒绝）；⑤ CLI 对已变更块 ⇒ `exit=1` + `status=refused` + **零写**；"
    "⑥ 真实仓库 `.agenticdoc/**` 下 sidecar 数量仍为 **0**（未污染）。",
)

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 18:58：**T-12 done + acked**"))
lines.insert(
    i + 1,
    "- 10-10 19:05：**T-23 done + acked**（G3 锚点接活：tick step 2c 自动锚 + `contract-freeze` CLI + `contract-frozen` 事件；"
    "PM 亲跑 12 + 121 全绿，并做**独立端到端**确认 `evaluate.ok=False / changed_ids=('AC-001',)`（G3 不再休眠）、"
    "重复冻结字节不变、真实仓库零 sidecar）。⇒ 立派 **T-14**（计数锁收口：reason_code 12→14、timeline 23→**27**、TS `EVENT_TYPES` += `contract-frozen`、"
    "配置 17→20 + 语料重冻）。记 D-057。在跑 = **T-14**（本 key 最后一张改测试的卡）。",
)

na = next(i for i, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: **G1~G6 的生产实现 + 锚点全部落地并逐一核销**（T-01~T-13 除 T-16 外全部 done+acked；T-08b 为假 failed 引发的重复派发、已人工终止）。"
    "**当前在跑 = T-14**（计数锁与语料重冻：`reason_code` 12→14、timeline 23→**27**、TS `EVENT_TYPES` += `contract-frozen`、"
    "配置键 17→20 + 语料重冻；PM 已把 4 红基线交给它）。"
    "**T-14 done ⇒ 只剩 T-16**（文档/CHANGELOG + 重建 `dist`/bundle = 运行时切换；届时 T-01~T-14/T-15/T-17~T-23 的改动才真正生效）"
    "⇒ 之后跑全量 Python 套件 + TS 套件做**收口验证**，再看是否 `advance_phase(verify)`。"
    "**每次派发后必须跑** `evidence/scripts/t23-normalize-whole-queue.py`（D-046）。"
    "**待用户决定**：① 运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）；"
    "② 残留 R18 是否单独开卡；③ T-23 的 `--force` 语义是否认可（PM 已按“默认拒绝、`--force` 才重冻并打印被替换 id”实现并亲测）。"
    "**已知残留**：R18（spawn 竞态不得静默判终态）、R19（错过 design/plan 边界的 key 无锚 ⇒ 需人显式 `contract-freeze`）、"
    "R20（`monitorCtx` 只由 `autoStartMonitor` 写）、D-038（`autopilot/dispatch.py` 未接 `run.json`）。"
)
upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 19:05"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok")
