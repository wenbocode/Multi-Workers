"""pm-state: D-056 (T-12 done + PM USAGE fix) + process log 18:58 + Next Action refresh."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

# 1. new decision D-056 after D-055
d55 = next(i for i, l in enumerate(lines) if l.startswith("- D-055（2026-10-10 18:50）"))
lines.insert(
    d55 + 1,
    "- D-056（2026-10-10 18:58）：**T-12 完成 + PM 关闭其 USAGE 交接**。T-12 交付：`gate-writer.ts` 的 `authorizes` "
    "（唯一闭集声明 `AUTHORIZES_ACTIONS` 从 `status-model.ts` **import**，未复制一份；写前 fail-closed；"
    "**门文件无 `authorizes:` 行 ⇒ 拒绝 + 提示**）+ `console.ts` 的 `cmdGate --authorizes <a,b>` 与 `autoStartMonitor` "
    "ctx 变化重臂 + `status-model.ts` 的 `GATE_JSON_LIST_FIELDS` += `authorizes` / 未知字段检查放宽（`:829`）/ 40 名顺序未动（PM 亲数 = **40**）；"
    "PM 亲跑 5 文件 = **273 passed**（`VC-012: closed_set=2 listed_only=true`、`VC-023: rearmed=true panel_present=true`）；"
    "`npm run check` = **exit 0**。**PM 直执小改**：`console.ts` 顶层 `USAGE`（`:100`）与文件头命令表（`:12`）补 `--authorizes`"
    "（T-12 受“只两处”写面约束未动；无测试断言该字符串 ⇒ 我改后重跑 2 文件 228 passed + 全仓 check exit 0 复核）。",
)

# 2. process log entry after the 18:45 one
i45 = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 18:45：**T-11 done + acked**"))
lines.insert(
    i45 + 1,
    "- 10-10 18:58：**T-12 done + acked**（三条 `[VERIFY]` 40/190/43 全绿，四组非空洞对照转红并逐字节还原；"
    "PM 亲跑 5 文件 **273 passed**；`npm run check` exit 0）；PM **直执关闭其交接①**（顶层 `USAGE` + 文件头命令表补 "
    "`--authorizes`，改后 228 passed + check exit 0）。记 D-056。在跑 = **T-23**（G3 锚点）；T-14 仍等 T-23 的事件名落地。",
)

# 3. Next Action + Updated
na = next(i for i, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: **波 0~2 全部核销**（T-01~T-13 done+acked，T-08b 为假 failed 引发的重复派发、已人工终止）。"
    "**当前在跑 = T-23**（AC-025：G3 锚点建立——`mw autopilot contract-freeze` CLI + conductor 在 design/plan 边界自动锚 "
    "+ `contract-frozen` 留痕；写面 `mw.py`/`conductor.py`/`timeline.py` + 新测试文件）。"
    "**T-23 一 done ⇒ 立刻派 T-14**（计数锁与语料重冻：timeline **23→27**、TS `EVENT_TYPES` += `contract-frozen`、"
    "`reason_code` 12→14、配置键 17→20；卡已追记）**→ 再 T-16**（重建 `dist`/bundle = 运行时切换）。"
    "**每次派发后必须跑** `evidence/scripts/t23-normalize-whole-queue.py`（D-046）。"
    "**待用户决定**：① 运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）；"
    "② 残留 R18 是否单独开卡；③ T-23 的 `--force` 语义是否认可。"
    "**已知残留**：R18（spawn 竞态不得静默判终态）、R19（错过边界的 key 无锚 ⇒ 需人显式 `contract-freeze`）、"
    "R20（`monitorCtx` 只由 `autoStartMonitor` 写，`cmdMonitor on` 不更新 ⇒ 最坏多一次无害 stop+start）、"
    "D-038（`autopilot/dispatch.py` 未接 `run.json`）。"
)
upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 18:58"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok")
