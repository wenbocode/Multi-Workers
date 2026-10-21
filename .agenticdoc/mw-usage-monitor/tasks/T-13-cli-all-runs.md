# T-13: HTML 走全量 run（CLI 侧接线）+ `--json` 不自动开浏览器（coding）

- Key: mw-usage-monitor
- type: coding
- 前置：T-11（`--html` / `--no-open` / `_publish_stats_html`）与 T-12（`build_report(include_all_runs=...)`、
  `render_html` 优先 `runs_all`）已完成。

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机 token/耗时监控 = 框架可观测性面）。
- 需求：`.agenticdoc/mw-usage-monitor/spec.md` §13（v0.5 R15–R17 / AC-022–AC-024）——HTML 明细展示窗口内**全部** run。
- 现状缺口（本任务要补的两点）：
  1. `packages/multi-workers/mw.py:9907` `cmd_stats` 调 `usage.build_report(...)` 时**没有**传 `include_all_runs`，
     所以 HTML 里仍是被 `--limit` 截断的 `runs`（实测 `--detail --limit 3` 生成的 HTML 只有 3 行 + `showing 3 of 6 runs`）。
  2. `packages/multi-workers/mw.py` 的 `_publish_stats_html(...)`：`--json` 只影响路径打印，**仍会自动打开浏览器**；
     脚本/CI 场景不该弹窗。
- 既有骨架（锚点插入）：
  - `cmd_stats` 里构造 report 的调用（含 `until=until, limit=args.limit, detail=args.detail`）
  - `cmd_stats` 末尾的 `if args.html is not None or args.detail: _publish_stats_html(...)`
  - `_publish_stats_html(..., no_open=..., as_json=...)`

## 要求

1. **全量接线**：`cmd_stats` 计算 `needs_html = args.html is not None or args.detail`（与现有 `_publish_stats_html` 的触发条件一致），
   给 `usage.build_report(...)` 传 `include_all_runs=needs_html and not args.json`：
   - `--json` 时不构建 `runs_all`（JSON 体积不回归，AC-023 的 CLI 侧）；
   - 文本 + HTML（或仅 `--html`）时构建，HTML 明细 = 全量（AC-022）。
   - `--json --html` 的极端组合：以 JSON 纯度优先，不构建 `runs_all`（HTML 显示 `--limit` 行，并在 stderr 提示一次
     `[mw stats] note: --json suppresses the full run table`）。
2. **`--json` 不自动打开**：`--json` 且**未显式** `--html PATH` 时视为 `no_open`（等价 `--no-open`），
   文件仍写（除非 `--json` 且没有 `--detail`/`--html`，此时原本就不写）。
   显式 `--json --html <PATH>` 保持「写 + 开」（用户明确要了文件）。
3. **测试**（`test_stats_cli.py` 追加，monkeypatch `webbrowser`，不改既有断言）：
   - `--detail --no-open --limit 3` 生成的 HTML：run 行数 == `runs_total` 且不含 `showing`（AC-022 的 CLI 端到端）。
   - `--json --detail --no-open`：`runs_all` 不出现（`"runs_all" not in report`）且 stdout 仍是纯 JSON。
   - `--json --detail`（无 `--no-open`）：`webbrowser.open` **未被调用**；stderr 有 `html:` 路径。
   - `--json --detail --html <tmp>/r.html`：`webbrowser.open` 被调用一次。
4. **文档**：README 用量统计节把「`--limit` 明细行数」的表述改准（`--limit` 只影响文本与 JSON `runs[]`，
   HTML 恒为全量），`--html` 那一行补「包含全部 run」；CHANGELOG 在上一轮 bullet 后**追加**一句
   「HTML 明细展示窗口内全部 run（`--limit` 仅作用于文本/JSON）」。不要新建 bullet。

## 写入允许面

- `packages/multi-workers/mw.py`（**只做锚点插入/局部改**）
- `packages/multi-workers/test_stats_cli.py`
- `packages/multi-workers/README.md`（**只做锚点插入**）
- `packages/multi-workers/CHANGELOG.md`（**只做锚点插入**）
- `.agenticdoc/mw-usage-monitor/workers/um-t13-cli-all-runs/report.md`

## 写入禁止面

- `packages/multi-workers/usage.py`（T-12 写面；`include_all_runs` 不够用就停下汇报）
- `packages/coding-agent/**`、`launcher.py`
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest
- 测试里禁止真开浏览器

## 并发警告（必读）

`mw.py`、`README.md`、`CHANGELOG.md` 工作区里有**其它会话未提交的改动**（`mw decide` 相关，4700+ 行）。
只用精确锚点插入（`edit` 小 `oldText`），禁止 `write` 整文件/格式化；锚点找不到就停下汇报；不要 `git add`。
自查新增量约 `mw.py +12`、`README +4`、`CHANGELOG +1`。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_stats_cli.py test_usage.py -q
set MW_USAGE_DIR=%TEMP%\mwusage-t13 && python mw.py stats --since 3h --detail --no-open --limit 2
python -X utf8 -c "import pathlib,re;h=pathlib.Path(r'%TEMP%/mwusage-t13/reports').glob('*.html').__next__().read_text(encoding='utf-8');print('rows',h.count('<tbody')[1:] and h.split('runs (newest first)')[1].count('<tr>'),'showing' in h)"
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：pytest 汇总行、`git diff --stat` 自查、生成的 HTML 行数与标题片段、`--json` 不弹窗的 monkeypatch 断言结果。

## 改动历史

- 2026-10-21 创建（PM）：v0.5 CLI 侧接线（HTML 全量 + `--json` 不自动打开）。
