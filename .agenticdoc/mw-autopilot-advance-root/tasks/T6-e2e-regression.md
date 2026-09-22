# T6: e2e hermetic + 回归收尾

> Key: mw-autopilot-advance-root | AC-005, AC-008 | 依赖：T1..T5

## 目标

1. e2e hermetic：临时项目目录（framework 之外）建 `.agenticdoc/<key>/{spec.md 过 design 门禁, _index.parallel}`；调 `autopilot.advance.advance(key, "design", tmp_project)` → exit 0，`tmp_project/.agenticdoc/<key>/pm-state.md` 推进；断言 framework clone 所在仓库 `.agenticdoc` 无新目录。
2. 回归：`packages/multi-workers` pytest 相关用例全绿；`npm run check` 0/0/0；无新增失败。
3. 质量门禁 + achieved.md + 收尾。

## 证据

- e2e 脚本输出（exit 0 / pm-state 片段 / mw `.agenticdoc` 目录对照）。
- pytest 汇总 + check 输出。
- `evidence/quality-gate-report-2026-09-22.md`。
