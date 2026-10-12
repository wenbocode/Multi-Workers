"""Relabel drifted decision-section clocks (same counter drift) and tidy one log entry."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
text = p.read_text(encoding="utf-8")

# decision ids -> corrected wall clock (anchored on worker dir mtimes / dispatched_at)
fixes = {
    "- D-043（2026-10-10 19:45）": "- D-043（2026-10-10 18:05）",
    "- D-044（2026-10-10 19:45）": "- D-044（2026-10-10 18:05）",
    "- D-045（2026-10-10 19:45）": "- D-045（2026-10-10 18:07）",
    "- D-046（2026-10-10 19:55）": "- D-046（2026-10-10 18:22）",
    "- D-047（2026-10-10 20:15）": "- D-047（2026-10-10 18:12）",
    "- D-048（2026-10-10 20:25）": "- D-048（2026-10-10 18:15）",
    "- D-049（2026-10-10 20:35）": "- D-049（2026-10-10 18:17）",
    "- D-050（2026-10-10 20:35）": "- D-050（2026-10-10 18:22）",
    "- D-051（2026-10-10 20:45）": "- D-051（2026-10-10 18:20）",
    "- D-052（2026-10-10 18:24）": "- D-052（2026-10-10 18:22）",
}
for old, new in fixes.items():
    assert text.count(old) == 1, (old, text.count(old))
    text = text.replace(old, new)

# tidy the doubled parenthesis introduced by the relabel pass
old_line = "- 10-10 18:15：**T-01 done + acked**（同时刻 T-05 也已 done：TS 镜像 43/43）（PM 亲跑"
new_line = "- 10-10 18:15：**T-01 done + acked**（同时刻 T-05 也已 done：TS 镜像 43/43；PM 亲跑"
assert text.count(old_line) == 1
text = text.replace(old_line, new_line)

# extend the correction note to cover the decisions section
old_note = "**T-20/T-21（标注 18:30 / 19:30）未逐一重标**"
new_note = "同一次更正也应用于下方 §5 决策区的 D-043~D-052 标签（已改）；**T-20/T-21（标注 18:30 / 19:30）未逐一重标**"
assert text.count(old_note) == 1
text = text.replace(old_note, new_note)

p.write_text(text, encoding="utf-8", newline="\n")
print("ok")
