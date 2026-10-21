# T-10: `usage.render_html` 静态报告渲染器（coding）

- Key: mw-usage-monitor
- type: coding

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机 token/耗时监控 = 框架可观测性面）。
- 需求：`.agenticdoc/mw-usage-monitor/spec.md` §12（v0.4：R11–R14 / AC-018–AC-021）——**以 §12 为准**。
  本任务只做**渲染器**（纯函数），不做 CLI flag、不打开浏览器（T-11 负责）。
- 既有实现（只增量扩展，不重写）：
  - `packages/multi-workers/usage.py:1248` `format_report_text(report, detail=False)`：文本渲染器，语义基准
  - `packages/multi-workers/usage.py:1215` `_format_row(row)`、`usage.py:1234` `_format_coverage(rows)`
  - `usage.py` 里的 `SESSION_WALL_MARK` / `SESSION_WALL_FOOTNOTE`（`*` 脚注）
  - report dict 形态：`generated_at, since, until, window, ledger{path,events,bad_lines,open_runs},
    totals{calls,tokens{4},runs}, groups{model,type,key,project}[row], coverage[{cli,runs,attribution}],
    sources{worker,pm}, runs[(detail row)], runs_total`
  - 明细行字段：`run_id, started_at, ended_at, key, task_key, type, model, calls, tokens{4}, wall_s,
    wall_kind, status, attribution, session_id, open_run`

## 要求

1. **`render_html(report, *, title=None) -> str`**（模块级纯函数，无 I/O、无新依赖）：
   返回完整文档字符串，以 `<!doctype html>` 开头、`</html>` 结尾。必须包含：
   - `<html lang="zh">`、`<meta charset="utf-8">`、`<meta name="viewport" ...>`、
     `<title>`（默认 `mw usage — <since> → <until>`）；
   - **内联** `<style>`（无外链、无 `@import`、无 `<script src>`、无 CDN）；允许少量内联 `<script>`（可选，非必须）；
   - 头部块：生成时间（本地 `%Y-%m-%d %H:%M:%S`）、窗口 `since → until (window)`、
     ledger 路径 + events + bad_lines + open_runs、生效过滤（来自 report 里已有字段；没有就不显示过滤行）、
     coverage 文案；
   - 汇总卡：`runs`（含 `worker/pm` 拆分）、`calls`、`input/output/cacheR/cacheW`；
   - 四张分组表（model / type / key / project，空组不渲染），列：
     name、calls、in、out、cacheR、cacheW、runs、wall p50、wall p90、n、wall_kind；
   - runs 明细表（若 `report["runs"]` 为空则渲染一行「窗口内没有运行」，不要空表头）：
     列 started_at、wall、status、key、task_key、type、model、calls、in、out、cacheR、cacheW、session_id；
     `open_run=True` 的行 status 列显示 `running`（不要显示 `None`）；
   - 表尾脚注：`-` = 无数据/不适用；`*` = PM 会话跨度（沿用 `SESSION_WALL_FOOTNOTE` 原文）；
     有 `wall_kind=session` 行时该行 wall 单元格加 `*`。
2. **语义与文本渲染一致**（AC-020）：同一个 report dict，不得二次取数；`None` ⇒ `-`（不是 `0`）；
   数字缩短沿用现有 `k/M/B` 缩写函数（复用文本渲染器用的那个，别写第二套）。
3. **转义**（AC-021/R14）：所有插值字符串走一个 `_html_escape()`（`& < > " '`）；
   写单测：key 含 `<img src=x onerror=alert(1)>` 时输出里不出现未转义的 `<img`。
4. **可读性**：表格 `border-collapse: collapse`，行斑马纹，`th` 粘顶（`position: sticky`），
   等宽数字（`font-variant-numeric: tabular-nums`），`word-break: break-all` 只用在路径列，
   页面 `max-width: 1400px` 居中；中文用系统字体栈（`-apple-system, "Segoe UI", "Microsoft YaHei", sans-serif`）。
   不使用 emoji；不使用外部字体。
5. **测试**（`packages/multi-workers/test_usage.py` 追加，不改既有断言）：
   - 文档骨架：`<!doctype html>` / `</html>` / `lang="zh"` / `charset="utf-8"`；
   - 无外链：不含 `http://`、`https://`（ledger 路径是本地路径，注意不要引入 `xmlns` URL；
     确需时改用 `<html lang>` 不带 xmlns）；
   - 四张分组表标题按 report 出现，空组不出现；
   - runs 表：`open_run` 行含 `running`；`wall_kind=session` 行含 `*`；
   - `None` 值渲染 `-`（构造一个 tokens 全 None 的行）；
   - 转义用例（key 带 `<img src=x onerror=...>`）；
   - 空窗口（`runs=[]`、groups 全空）渲染「窗口内没有运行」且不抛异常。

## 写入允许面

- `packages/multi-workers/usage.py`
- `packages/multi-workers/test_usage.py`
- `.agenticdoc/mw-usage-monitor/workers/<本任务 key>/report.md`

## 写入禁止面

- `packages/multi-workers/mw.py`（T-11 的写面）、`launcher.py`、`README.md`、`CHANGELOG.md`
- `packages/coding-agent/**`（零 TS 改动）
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest
- 禁止在测试里真正打开浏览器或写用户目录文件（本任务纯字符串渲染）

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_usage.py -q
python -X utf8 -c "import usage,pathlib;r=usage.build_report(since=usage.parse_since('7d'),limit=5,detail=True);h=usage.render_html(r);print(len(h));pathlib.Path('C:/Users/wenbozhou/AppData/Local/Temp/mw-report-preview.html').write_text(h,encoding='utf-8')"
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：`pytest test_usage.py -q` 汇总行、渲染产物字节数、以及 HTML 里四张表标题与 `runs` 表头的真实片段。

## 改动历史

- 2026-10-21 创建（PM）：v0.4 静态 HTML 报告渲染器。
