# T-14: run 明细增加 `project` 字段（coding）

- Key: mw-usage-monitor
- type: coding

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机 token/耗时监控 = 框架可观测性面）。
- 需求：`.agenticdoc/mw-usage-monitor/spec.md` §14（v0.6：R18–R20 / AC-025–AC-027）——**以 §14 为准**。
- 现状（缺口）：
  - 台账 `start` 行本来就有 `project`（`launcher.py` 写入），`by project` 分组也在用；
    但明细行 `_run_detail_row(...)` / `_pm_detail_row(unit)` 没有这个字段。
  - 分组侧已有现成写法：`usage.py:1404` `"project": (run or {}).get("project") or session.get("cwd")`——**复用它**，别另起一套取值逻辑。
- 关键代码位置（直接用 `path:line` 定位）：
  - `packages/multi-workers/usage.py` 的 `_run_detail_row(run, unit, claude_exact)`：构造 worker 明细行（dict 字面量里列字段）
  - `packages/multi-workers/usage.py` 的 `_pm_detail_row(unit)`：构造 PM 明细行
  - `packages/multi-workers/usage.py:1510` `format_report_text(report, detail=False)`：文本明细表的表头/行渲染
  - `packages/multi-workers/usage.py:1814` `render_html(report, *, title=None)`：HTML 明细表 `<thead>` 与 `<tbody>` 行
  - `packages/multi-workers/usage.py` 的 `_project_matches(...)` 与 `_matches_filters`（`usage.py:776` 一带）：过滤语义，不改
- 上一轮已实现：`include_all_runs`（`runs_all`）、HTML 全量、`--html` / `--no-open`。**不要回退这些**。

## 要求

1. **字段**：`_run_detail_row` 与 `_pm_detail_row` 都新增 `"project"`，取值
   `run.get("project") or (unit or {}).get("project") or (unit or {}).get("cwd") or None`；
   `_pm_detail_row` 用 `unit.get("project") or unit.get("cwd") or None`。保持 `None` 而非空串。
2. **文本渲染**：`--detail` 表在 `started_at` 之后插入 `project` 列，值 = 路径末段（兼容 `\\` 与 `/`），
   `None` ⇒ `-`；列宽按现有对齐逻辑（`_format_row` 同款填充），不要破坏既有列顺序的其余部分。
3. **HTML 渲染**：明细表 `<thead>` 在 `started_at` 之后加 `<th>project</th>`，
   `<td>` 文本是 basename，且带 `title="<完整路径>"`（完整路径做 HTML 转义）；`None` ⇒ `-`，且不要输出 `title`。
4. **一致性**：明细行的 project 与 `by project` 分组用同一取值来源（AC-027）；
   `--project X` 过滤后 `runs[]` 每行都匹配 X（worker 与 PM 都要覆盖，PM 会话的 cwd 也要参与匹配）。
5. **兼容**：旧台账行没有 `project` 时不抛异常；`project` 为 `null` 时 JSON 就是 `null`。
6. **测试**（`test_usage.py` 追加，不改既有断言）：
   - worker 行 project == 台账 `start.project`；PM 行 project == 会话 header `cwd`；两者都缺 ⇒ `None`。
   - 文本明细行含 basename 与 `-` 两种情形。
   - HTML 明细 `<td ... title="...">basename</td>`；`None` 行无 `title`。
   - `--project` 过滤后所有明细行匹配（含 PM 会话行）。

## 写入允许面

- `packages/multi-workers/usage.py`
- `packages/multi-workers/test_usage.py`
- `.agenticdoc/mw-usage-monitor/workers/um-t14-project-field/report.md`

## 写入禁止面

- `packages/multi-workers/mw.py`、`test_stats_cli.py`、`README.md`、`CHANGELOG.md`（`mw.py` 等含别的会话未提交改动）
- `packages/coding-agent/**`、`launcher.py`
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest
- 禁止真正打开浏览器、禁止写用户目录

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_usage.py -q
python -X utf8 -c "import usage;r=usage.build_report(since=usage.parse_since('24h'),limit=3,include_all_runs=True);print([ (x['key'], x['project']) for x in r['runs'] ]);h=usage.render_html(r);print('title_attrs', h.count('title='), 'has_project_th', '<th>project</th>' in h)"
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：`pytest test_usage.py -q` 汇总行、上面第二条命令真实输出、文本明细表 2 行的真实片段。

## 改动历史

- 2026-10-21 创建（PM）：v0.6 — `runs[].project`（取值复用分组侧，文本 basename / HTML basename+title）。
