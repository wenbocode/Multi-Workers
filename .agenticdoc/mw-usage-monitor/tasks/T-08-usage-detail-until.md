# T-08: usage.py 支持 `--until` 上界与 run 级明细（coding）

- Key: mw-usage-monitor
- type: coding
- 本卡为 r2：r1 的卡片段落顺序被派发器打乱（`## 改动历史` 出现在 `## 上下文` 之前，生成 task.md 时被并入上一段导致 envelope 校验失败）。本卡按 T-03 的顺序重排。

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「本机 token/耗时监控」是框架可观测性面）。本任务只做**查询侧**，不动台账 schema。
- 需求已由 PM 写入 `.agenticdoc/mw-usage-monitor/spec.md` §11（v0.3 增补）——**以 §11 为准**，不要重新设计：
  - R7 `--until` 上界（`[since, until)`，缺省 now，早于 since ⇒ 错误）
  - R8 `--detail` 只控制文本是否渲染明细；**JSON 恒定带 `runs[]`**
  - R9 明细字段逐字见 §11.2
  - R10 `--limit`（默认 20，`0` = 不限），截断要在文本里说清
- 既有实现（不要重写，只增量扩展）：
  - `packages/multi-workers/usage.py:312` `parse_since`（相对/日期解析 + `_local_tz`）
  - `packages/multi-workers/usage.py:717` `load_runs`（已产出 `open_run`、`wall_s`、`spawned`）
  - `packages/multi-workers/usage.py:981` `build_report`（`since=` 关键字参数；返回 `totals/groups/coverage/ledger/window/since`）
  - `packages/multi-workers/usage.py:1215` `_format_row`、`usage.py:1234` `_format_coverage`、`usage.py:1248` `format_report_text`
- 现有 30 个测试在 `packages/multi-workers/test_usage.py`，全绿；不要改它们的断言（除必要的签名兼容）。

## 要求

1. **`parse_until(text, now=None)`**：与 `parse_since` 同语法（`7d|24h|30m|YYYY-MM-DD|YYYY-MM-DDTHH:MM`）。
   **多一个** `YYYY-MM-DDTHH:MM` 形式（用户会写「昨天 14:00 到现在」）。非法值 `ValueError`（CLI 层转 rc=2）。
   相对形式（`24h`）相对 `now` 往前，语义与 `parse_since` 完全一致（复用同一份解析，不要复制两份正则）。
2. **`build_report(..., until=None, limit=20, detail=False, ...)`**：
   - 窗口变半开区间 `[since, until)`；`until` 缺省 = `now`。窗口外 run 从 `totals`/`groups`/`runs` 一起消失。
   - 新增顶层键 **`runs`**（list）与 **`runs_total`**（int，过滤+窗口内、截断前的条数）。
     `runs` 按 `started_at` **倒序**，`limit` 为 `None` 或 `0` 时不截断。
   - 每行字段（逐字，缺值用 `None` 而非空串）：
     `run_id, started_at, ended_at, key, task_key, type, model, calls, tokens{input,output,cache_read,cache_write}, wall_s, wall_kind, status, attribution, session_id, open_run`
   - `open_run=True` ⇒ `wall_s=None`、`wall_kind="none"`（禁止用会话跨度回填，T-06/AC-016）。
   - `calls`/`tokens` 是该 run **会话文件**里的量（join 结果），找不到会话文件 ⇒ `calls=None`、tokens 四项 `None`
     （不要写 0：0 表示真的没有请求，None 表示不可归因）。
   - 明细行不改变 `groups` 的计算：groups 仍由同一批 run 聚合，保证 `sum(runs.tokens) == totals.tokens`（AC-015）。
3. **`format_report_text(report, detail=False)`**：`detail=True` 时在 coverage 之前追加：
   ```
   runs (newest first)
     2026-10-21T08:00  mw-usage-monitor  um-t07-e2e-ledger-smoke  research  timi/deepseek-v4.1-flash  calls 20  in 31k  out 14k  cacheR 503k  cacheW 0  wall 1m51s  done
   ```
   列宽对齐用现有 `_format_row` 的紧凑风格（不引入新依赖）。被 `limit` 截断时，表头下方一行：
   `showing 20 of 137 runs (--limit 0 for all)`；有 `session` 墙钟行时沿用 `SESSION_WALL_FOOTNOTE` 的 `*` 标记规则。
   token 数值单位沿用现有函数（同一套 `k/M` 缩短），不要自造第二套格式化。
4. **首行时间区间**：从 `usage since <date> (<window>)` 扩展为 `usage <since> → <until> (<window>)`；
   向后兼容：`report` 里没有 `until` 键时保持旧文案。
5. **测试**（`test_usage.py`，追加，不改既有断言）：
   - `parse_until` 五种形式 + 非法值。
   - 半开区间：边界 run（刚好 `== since`、刚好 `== until`）分别被纳入/排除。
   - `runs` 倒序、`limit` 截断、`limit=0` 不限、`runs_total` 等于未截断条数。
   - `open_run` 行 `wall_s is None` 且 `wall_kind == "none"`。
   - 会话文件缺失 ⇒ `calls is None`、`tokens` 全 `None`。
   - `sum(run.tokens) == totals.tokens`（同一过滤下，未截断）。
   - 文本渲染：`detail=True` 含 `runs (newest first)` 与截断提示；`detail=False` 不含。
6. 纯函数、无新依赖、无 `import` 副作用；`python -m pytest test_usage.py -q` 全绿。

## 写入允许面

- `packages/multi-workers/usage.py`
- `packages/multi-workers/test_usage.py`
- `.agenticdoc/mw-usage-monitor/workers/<本任务 key>/report.md`

## 写入禁止面

- 其余任何仓库文件；特别是 `packages/multi-workers/mw.py`、`launcher.py`、`README.md`、`CHANGELOG.md`
  与 `packages/coding-agent/**`（含 `ui-bridge.ts`、`mw-runner.ts`）——这些文件当前含其它会话未提交改动。
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_usage.py -q
python -X utf8 -c "import usage,json;r=usage.build_report(since=usage.parse_since('7d'),detail=True);print(len(r['runs']),r['runs_total']);print(json.dumps(r['runs'][0],ensure_ascii=False)[:300])"
```

## 交付格式

- `output.md` 带 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据里必须贴 `pytest test_usage.py -q` 的**最后一行**汇总，以及第二条验收命令的真实输出片段。

## 改动历史

- 2026-10-21 创建（PM）：v0.3 增补（`--until` + run 级明细），spec §11 已记录，尚无实现改动。
- 2026-10-21 r2（PM）：卡片段落重排为 T-03 顺序，修复 r1 envelope 校验失败。
