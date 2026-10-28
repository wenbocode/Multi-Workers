"""Resolve the design.md open item (AC-003 on the PM channel) as option (a'): the
PM's durable audit row reuses the existing `recordDispatchAlarm` ledger
(`.agenticdoc/_autopilot/auto-decisions.jsonl`) instead of adding a second
`.autopilot/timeline.jsonl` writer."""

import pathlib

DESIGN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\design.md")

OLD_MARKER = "- **未决（AC-003 在 PM 通道的落地方式，需用户/后续 key 定夺）**"
NEW = """- **AC-003 在 PM 通道的落地方式 —— 已裁定（2026-10-14，PM；取代本节原"未决"两条候选）**：采用 **(a')**：由调用方消费 `DispatchOutcome`，并把拒绝落成 `.agenticdoc/_autopilot/auto-decisions.jsonl` 的一行（复用**既有** `pm/pm-orchestrator.ts:556` 的 `recordDispatchAlarm`，`phase: "dispatch-alarm"` 家族，best-effort）。理由：**D-008 早就把 PM 侧的审计出口定为派发返回值**，缺的只是"有人消费它"；原候选 (b)（TS 另写 `.autopilot/timeline.jsonl`）会新增该文件的第二个写者并与 Python 侧的 timeline 轮转（`.1/.2`）冲突，代价与风险都高于收益。同一次修复顺带修掉计数不诚实：`pm-orchestrator.ts:1243→1254` 的"无条件 `queued += 1`"（`dispatchTask` 拒绝不抛异常）改为按 `ok !== true` 判定。落地卡：`wfg-i13-pm-refusal-audit`（T-W-I13）。原两条候选记录如下，仅供追溯：
"""

text = DESIGN.read_text(encoding="utf-8")
if "AC-003 在 PM 通道的落地方式 —— 已裁定" in text:
    print("design.md: already resolved")
else:
    if OLD_MARKER not in text:
        raise SystemExit("marker not found; aborting without writing")
    text = text.replace(OLD_MARKER, NEW, 1)
    DESIGN.write_text(text, encoding="utf-8")
    print("design.md: open item resolved as (a')")
print(f"design.md lines={len(DESIGN.read_text(encoding='utf-8').splitlines())}")
