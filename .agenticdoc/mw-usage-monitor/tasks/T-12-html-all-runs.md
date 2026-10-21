# T-12: HTML 明细展示全量 run（coding）

- Key: mw-usage-monitor
- type: coding

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机 token/耗时监控 = 框架可观测性面）。
- 需求：`.agenticdoc/mw-usage-monitor/spec.md` §13（v0.5：R15–R17 / AC-022–AC-024）——**以 §13 为准**。
  用户原话：「都 html 了就把 run 都展示吧」。
- 现状（本任务要改的两处，都是既有实现）：
  - `packages/multi-workers/usage.py:1814` `render_html(report, *, title=None)`：目前明细表读 `report["runs"]`，
    而 `runs` 已被 `--limit` 截断（默认 20），所以 HTML 也只显示 20 行。
  - `packages/multi-workers/usage.py` 的 `build_report(..., limit=20, detail=False)`：`runs_total` 是全量条数，
    `runs` 是截断视图；不返回全量列表。
  - 文本渲染 `usage.py:1510` `format_report_text`：`showing N of M runs (--limit 0 for all)` 只属于文本，保持不变。
- 并行约束：另一个 worker（T-11）正在改 `mw.py` / `test_stats_cli.py` / `README.md` / `CHANGELOG.md`。
  **本任务只碰 `usage.py` 与 `test_usage.py`**，不要动 CLI，也不要改文本输出。

## 要求

1. **`build_report(..., include_all_runs=False)`**：
   - `include_all_runs=False`（默认）：行为与返回键**完全不变**（不得新增 `runs_all` 键，JSON 体积不回归，AC-023）。
   - `include_all_runs=True`：额外返回 `runs_all`，内容为**窗口内全部** run（与 `runs` 同 schema、同排序），
     因此 `len(runs_all) == runs_total`；`runs` 仍按 `limit` 截断（JSON/文本契约不变）。
   - 实现要求：不要为了全量再扫一遍会话文件——内部已经算出全量行，只是最后才截断；
     让截断发生在「产出 `runs`」这一步，`runs_all` 直接引用未截断列表。
2. **`render_html`**：
   - 明细表数据源优先级：`report["runs_all"]` → `report["runs"]`（旧调用路径回退，不抛异常）。
   - 标题行改为含总数，例如 `runs (newest first) · 184`；**不出现** `showing N of M`。
   - 若总数很大（>2000 行），仍然全量渲染（不做二次截断），但要在表格上方加一句
     `共 N 行，可用浏览器 Ctrl+F 搜索 key / task_key`（中文即可）。
3. **一致性**：`runs_all[:k]` 必须与 `build_report(limit=k)["runs"]` 逐字段相等（AC-024）；
   `render_html` 不得自行排序或二次计算 token。
4. **测试**（`test_usage.py` 追加，不改既有断言）：
   - `include_all_runs=True` ⇒ `len(runs_all) == runs_total`，且默认调用**没有** `runs_all` 键。
   - `runs_all[:3]` 与 `build_report(limit=3)["runs"]` 深比较相等（同一 fixture）。
   - `render_html` 用 `runs_all` 时 `<tbody>` 行数 == `runs_total`；不出现 `showing`；
     标题含 `runs (newest first) · `。
   - 只有 `runs`（无 `runs_all`）的 report 仍能渲染且行数 == `len(runs)`。
   - 全量 > 2000 时出现 `Ctrl+F` 提示（用 fixture 造 3 行即可测提示开关的判据实现，若判据是 >2000 则补一个 mock 大列表的轻量用例）。

## 写入允许面

- `packages/multi-workers/usage.py`
- `packages/multi-workers/test_usage.py`
- `.agenticdoc/mw-usage-monitor/workers/um-t12-html-all-runs/report.md`

## 写入禁止面

- `packages/multi-workers/mw.py`、`test_stats_cli.py`、`README.md`、`CHANGELOG.md`（T-11 正在写，冲突）
- `packages/coding-agent/**`、`launcher.py`
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest
- 禁止真正打开浏览器、禁止写用户目录

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_usage.py -q
python -X utf8 -c "import usage;r=usage.build_report(since=usage.parse_since('24h'),limit=3,include_all_runs=True);h=usage.render_html(r);print('runs_total',r['runs_total'],'runs_all',len(r['runs_all']),'tbody_rows',h.count('<tr class=\"row\">') or h.count('<tr>'))"
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：`pytest test_usage.py -q` 汇总行、上面第二条命令的真实输出、HTML 标题行片段。

## 改动历史

- 2026-10-21 创建（PM）：v0.5 — HTML 展示全量 run，`--limit` 只留文本/JSON。
