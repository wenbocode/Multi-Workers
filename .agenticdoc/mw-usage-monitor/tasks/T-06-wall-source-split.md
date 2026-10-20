# T-06: 修正墙钟分位数混源（worker 墙钟 vs PM 会话跨度）

type: coding
phase: execute
key: mw-usage-monitor
覆盖 AC: AC-004, AC-005, AC-013
依据: `.agenticdoc/mw-usage-monitor/design.md` §5/§6；`spec.md` v0.2 §2（墙钟）/§4（AC-004/AC-005）；PM 实测输出（见下）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（可观测性面：回答"每次调用耗时多少"）。
- **PM 实测发现的缺陷**（2026-10-19，真实数据，`mw stats --since 1d --json`）：

  ```
  model timi/deepseek-v4.1-flash calls 5449 runs 55 n 55 p50 557.0 p90 161692.6   # p90 = 44.9 小时
  model timi/glm-5.3-flashx      calls 474  runs 9  n 9  p50 494.0 p90 675.6
  sources {'worker': 0, 'pm': 69}
  ```

  根因：PM 会话的墙钟 = header→末条消息的**整个会话跨度**（`usage.py` 的 `_wall_from_session`），
  实测有跨 25 天的长命窗口（RQ1 §6：max 2,177,539.9 s）。当同一组里既有 worker run 墙钟（spawn→reap，
  秒~分钟级）又有 PM 会话跨度（小时~天级）时，percentile 混在一起 → p90 变成 44h，指标失去意义。
- 已核实起点（自行复核）：
  - `packages/multi-workers/usage.py:890` `_finalize_group`（聚合并算 `wall_p50/wall_p90/n`）、
    `:856` `_wall_from_session`（PM 跨度）、`:836` `_window_events`（把 ledger run 与 session 单元合并进组）、
    `:1197` `format_report_text` / `:1168` `_format_row` / `:1156` `_format_wall`（文本渲染）、
    `:909` `_coverage_rows`（尾行）、`_percentile`（`len<5` → None）。
  - 现有测试：`packages/multi-workers/test_usage.py`（24 用例，含 `test_build_report_wall_percentiles_with_enough_samples`）。
  - spec AC-004 要求「每 run 有 `wall_s`；汇总给 p50/p90」；AC-005 要求「`source=pm` 可统计（模型/tokens/**会话墙钟**）」
    —— 两者必须同时满足，但**不能混在同一个分位数里**。
- 硬约束：`usage.py` 的 JSON 契约键集已由 `test_stats_cli.py` 与 `test_usage.py` 逐层断言（含无金额键）。
  本次**只允许新增键** `wall_kind`，不得删改既有键名/类型。

## 要求

1. `build_report` 的每个组行新增 `wall_kind`，取值 `"run" | "session" | "none"`：
   - 组内存在 worker run 墙钟（ledger `wall_s`）→ 只用这些值算 `wall_p50/wall_p90/n`，`wall_kind="run"`；
   - 组内**没有** run 墙钟但有 PM 会话跨度 → 用会话跨度算，`wall_kind="session"`；
   - 两者都没有（或样本不足）→ `wall_p50/wall_p90=null`、`wall_kind="none"`（`n` 仍报有效样本数）。
2. **绝不混源**：同一组内存在 run 墙钟时，PM 会话跨度不得进入分位数（即使 PM 样本更多）。
3. `format_report_text`：`wall_kind=="session"` 的组行在墙钟单元格末尾加 `*`；只要出现至少一个 `*`，
   在 `coverage:` 行之前插入一行脚注：`* = PM 会话跨度（header→末条），非 worker 墙钟`。
   `wall_kind=="run"` 与既有输出形态保持一致（不出现新符号）。
4. `design.md` 同步：§5 JSON 示例加 `wall_kind`；§6 文本示例说明 `*` 脚注规则（PM 可改文档，若写面不含
   `design.md` 则在 `output.md` 给出建议文本，由 PM 落笔）。
5. 测试（加到 `test_usage.py`，不改既有断言）：
   - 混合组（1 个 worker run wall=100s + 3 个 PM 会话跨度 100000s）→ `wall_kind="run"`、
     `p50/p90` 只来自 run（100），`n==1`（PM 不参与）；
   - 纯 PM 组 → `wall_kind="session"`、分位数来自会话跨度、文本带 `*` 且脚注存在；
   - 纯 worker 组 → `wall_kind="run"`、无 `*`、无脚注；
   - 无墙钟组 → `wall_kind="none"`、`null` → 渲染 `-`；
   - `--source pm` 过滤后仍能拿到 session 墙钟（AC-005 不回归）。
6. 不改 `launcher.py` / `mw.py` / TS / CHANGELOG；不新增依赖；不实现 rollup。

## 写入允许面

- `packages/multi-workers/usage.py`（仅 `_finalize_group`/`_window_events`/`format_report_text`/`_format_row` 及相关小函数）
- `packages/multi-workers/test_usage.py`（新增用例）
- `.agenticdoc/mw-usage-monitor/design.md`（仅 §5/§6 的 `wall_kind` 与脚注说明）

## 写入禁止面

- `launcher.py`、`mw.py`、`mw_common.py`、任何 TS、`CHANGELOG.md`、`README.md`
- 其它 key 目录、`.mw/**`；禁止 `git checkout|restore|stash|reset|add`

## 验收命令

```powershell
cd H:\git\Multi-Workers\packages\multi-workers
python -m py_compile usage.py
python -m pytest test_usage.py test_stats_cli.py -q
# 真实数据复核（不设硬阈值，只看 p90 不再出现 44h 量级）
python -X utf8 mw.py stats --since 1d --json
```

## 改动历史

（首次改动，填写：改了哪几个函数、为什么这样分源、被否决的替代方案（如"把 PM 墙钟拆成独立列"）。）
