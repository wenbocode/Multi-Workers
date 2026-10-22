# RQ4 — 档案行归属判据与"零行即跳过"的可行性

- type: research
- owner key: mw-signoff-decide-only
- 唯一证据文件：`.agenticdoc/mw-signoff-decide-only/evidence/research/spec-archive-scan-20261022.md`

## 上下文

项目目标见 `.agenticdoc/goal.md`。本 key 要把签收要求绑定到"该 key 档案里有 ≥1 条真实 jev 决策行"。门禁将对**每个** key 执行，所以必须证明这个判据在大仓库里足够便宜且不会误判。

现状锚点：

- `packages/multi-workers/decide_signoff.py` — `collect()`、`_row_matches_key()`、`_ROW_FIELDS`、`SIGNOFF_DP_ID` 排除逻辑
- `packages/multi-workers/decide_archive.py` — `ARCHIVE_RELATIVE_PATH`、`iter_rows`
- `.agents/skills/agentic-task/scripts/advance_phase.py:271` `_decision_signoff_problems`、`:233` `_load_decide_signoff`

## 要求（只读）

1. 给出 `decide_signoff.collect()` 的精确语义：读哪个文件、哪些行算"该 key 的决策行"、哪些被排除（含 dp25 自身行），逐条给 `path:line`。
2. 用真实档案（`.agenticdoc/_autopilot/decisions.jsonl`，若不存在则说明）统计：总行数、`kind=decide` 行数、按 key 分组的前 10 名、每行平均字节数。给出测量命令与输出。据此估算一次 `collect()` 的耗时（可实测 5 次取中位数）。
3. 回答"零行即跳过"的误判风险：
   - 档案文件不存在（新项目 / 没装 mw）→ 当前 `collect()` 返回什么？
   - 行里 `key` 列缺失但 `decision_id` 以 `:<key>` 结尾 → 是否算命中？
   - `kind` 不是 `decide` 的行（如 `authority-change`）是否会被误算？
   - `key` 为空字符串时 `_row_matches_key` 的行为（给行号）。
4. 给出在 `advance_phase.py` 内**不导入 `decide_signoff`** 也能复刻同一判据的最小实现（读 jsonl、逐行 json.loads、三个字段判断），并列出它与权威实现的已知差异（若有）。
5. 找出档案写入方：`decide_archive.append_*` 的调用点，确认行里一定带 `key` 或 `decision_id:<key>`（给 `path:line`）；若存在不带 key 的写入路径，指出它。
6. 评估：把"是否要求签收"的判据从 `decision-scope.md` 换成"有 jev 行"后，`mw-decision-substitution`（唯一有标记的 key）行为是否改变——给该 key 的实际行数。

## 写入允许面

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-archive-scan-20261022.md`
- `.agenticdoc/mw-signoff-decide-only/workers/sdo-rq4-archive/**`

## 交付格式

Markdown，六节对应上面 6 条；第 2、3 条必须附命令与真实输出（可截断，但保留数字）。最后 `## 结论` ≤6 行：这个判据能不能直接当门禁条件。
