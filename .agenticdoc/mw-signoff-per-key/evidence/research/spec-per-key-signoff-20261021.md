# research declaration — 签收点的 key 维度

- key: mw-signoff-per-key
- date: 2026-10-21
- 类型: 零研究声明（zero-research declaration）

## 为什么不需要外部调研

本 key 的规格来自用户裁定 + 本仓既有实现，没有需要外部检索的未知量：

1. **key 从哪来**：`decide_signoff.collect(project_dir, key)`（`packages/multi-workers/decide_signoff.py:285`）与
   `auto_conclusion(project_dir, key)`（同文件 `:380`）都是显式收参；`_row_matches_key`（`:221`）按行过滤。
   `mw decide sign --key` 的 argparse 定义在 `packages/multi-workers/mw.py:10884`。
2. **表的写入面**：`_dp_refresh`（`mw.py:2215-2264`）只 `append` 缺失行，`_dp_row_for`（`mw.py:1770`）产出注册表默认值；
   翻开关的 `dp on|off|set|apply` 是另一条路径（`mw.py:2152` 起、`mw.py:2990` 起）。
3. **守卫的现有口径**：`TABLE_WRITE_CLI_RE` 在 `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:371`
   明列 `on|off|set|refresh|apply`，理由写在同文件 `:364-370`。

## 已核实的既有事实（不构成新研究）

- dp25 在 `decision_points.py:824-855` 已登记为 P2 + 回显 executor；`REQUIRED_STATE_FIELDS` 含 `key`（`:1184-1191`）。
- 注册表铁律"只有 P2 默认开"在 `decision_points.py:378`，P2 必须有 executor 在 `:398`。
- 签收门禁比对的是档案口径（`counted_rows`/`rows_sha256`），不是表 sha；GATE 复跑 `check_gate("done")` 为 True。

## 结论

无需额外证据文件；本 key 的判定材料就是上述源码行 + `pm-state.md` 里的运行验证记录 + QG review 的独立复核。
