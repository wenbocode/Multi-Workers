# decision-scope：本 key 启用决策签收门禁

标记文件只做一件事：让 `advance_phase.py` 的 `GATES["done"]` 对本 key 启用 `decision_signoff` 检查
（其它 key 没有这个文件，行为零变化）。

- 依据：`docs/decision-substitution.md` §5.2/§5.3、design D-014/D-015，以及 2026-10-21 用户裁定
  「签收取向 = (a) `mw decide sign` + (b) `continue` 需 `N≥1` 且每行 engine 为真 jev」。
- 本 key 的授权口径：`.mw/decide.json` = `enabled/true`、`transport=timi-decisions`、`model=jev-latest`；
  `.mw/decide-points.json` 由 `mw decide dp refresh` 于 2026-10-21 生成（24 行，authority-change 已入档）。
- 门禁要求：`evidence/review/sign-final.md` 存在、`conclusion:` 机器行可解析、
  `counted_rows` / `rows_sha256` 与权威档案重算一致；`continue` 还要求 N≥1 且每行
  `transport=timi-decisions` / `model=jev-latest` / `confidence_source=api`。
- 签名只能由人在 agent 会话外执行：`mw decide sign --project .agenticdoc/mw-decision-substitution --conclusion <x>`。
