"""Record plan.md section 7.7 = W-13 absorption (PM-side refusal audit, AC-003)."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

ADD = """
### 7.7 W-13 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/write-face-pm-gate.test.ts` = **22 passed**（基线 19，只加 3 条，既有 19 条未改未放）。
- **PM 读码核对消费点**（卡面要求的实质）：`pm/pm-orchestrator.ts:981`（修复路径）与 `:1325`（常规路径）都是 `if (outcome.ok) { queued += 1 / result.queued.push } else { reportWriteFaceRefusal(...) }` —— 对**任意非 ok** 统一处理，**没有**硬编码 `code`；审计走既有 `recordDispatchAlarm` → `.agenticdoc/_autopilot/auto-decisions.jsonl`（`phase:"dispatch-alarm"`, `kind:"write-face-refusal"`, `detail="${taskKey}: ${reason}"`），best-effort 不破派发；`onRefusal → deliverPmAlert` 为生产接线（`:1761`）。⇒ **AC-003 在 PM 通道闭合**，且计数不诚实（被拒仍 `queued += 1`，会污染 `dispatch-quota`）同批修掉。
- **D-008 一致性**：PM 侧审计出口仍是"派发返回值"，本卡只是让调用方把它变成持久行——未新建 `.autopilot/timeline.jsonl` 写者（这是我先前 (b) 方案的修正，已写入 `design.md` 裁定）。
- **设计取舍（接受）**：`write-face-refusal` 是 per-task、**未做 session 去重**——长期被拒的任务每轮 `agent_settled` 扫描各落一行（conductor 侧 `_write_face_audit` 同为每次尝试一行）。若将来要求"同类同 task 每 session 一行"，需把去重集合并入 `DispatchScanOptions`（当前不做，避免越面）。
- **新发现的收口障碍（B4 必须处理）**：`test/suite/mwds-t23-cutover-recheck.test.ts` 的 requirement 4 断言 `packages/multi-workers/dist/extensions/agent-team-loop.js` 的 sha 等于卡面记录值，实测 `expected 975D4066…` vs `received 9544D8A4…`；该 bundle mtime `2026-10-14 08:38:48`（早于本会话）、开工前即 `git status = M`、且是**禁止面**（`packages/multi-workers/**` 只读）⇒ 与本 key 无关，但**它是本 key DONE 前的质量门障碍**：B4 必须重建两侧 `dist`（同步别人已改的 source）并重新同步该卡面记录的 sha，或明确由该文件归属方处理。
- **其余既有红（无关，报基线不修）**：`worker-file-tool` 2 条（`trace.log` 污染）、`mwds-t02` 1 条（别 key task book 语料漂移）；`dispatch-recovery-terminal` 全绿。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.7 W-13 终态吸收" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended 7.7")
else:
    print("plan: already has 7.7")
print(f"plan.md lines={len(PLAN.read_text(encoding='utf-8').splitlines())}")
