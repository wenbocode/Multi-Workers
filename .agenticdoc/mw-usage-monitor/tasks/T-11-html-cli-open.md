# T-11: `mw stats --html` 落盘 + `--detail` 自动打开浏览器（coding）

- Key: mw-usage-monitor
- type: coding
- 前置：T-10 已完成（`usage.render_html(report, *, title=None)` 已在 `usage.py`）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机 token/耗时监控 = 框架可观测性面）。
- 需求：`.agenticdoc/mw-usage-monitor/spec.md` §12（v0.4：R11–R13 / AC-018/AC-019）——**以 §12 为准**。
- 用户原话：「窗口上的可读性有限，可以做一次数据刷新后，用一个静态的 html 来展示，并在指令发出 `--detail` 后自动打开」。
  数据新鲜度不是问题（每次调用重取，已实测 26 秒内 calls +3 / output +22833），所以「刷新」= 再调一次本命令。
- 既有骨架（只做锚点插入 / 局部改）：
  - `packages/multi-workers/mw.py:9907` `def cmd_stats(args)`（已有 `--since/--until/--key/--type/--model/--project/--source/--detail/--limit/--json`）
  - `packages/multi-workers/mw.py` 的 `stats_p.add_argument(...)` 段（在 `cmd_stats` 之后的 `_parse_args` 里）
  - `packages/multi-workers/test_stats_cli.py`（当前 33 用例全绿，其中若干调用 `--detail`）
  - `packages/multi-workers/usage.py:137` `usage_dir()`（`MW_USAGE_DIR` → `USERPROFILE` → `HOME` → `~/.mw/usage`）
  - `packages/multi-workers/usage.py:1814` `render_html(report, *, title=None)`（T-10 产出）
  - `packages/multi-workers/usage.py:1510` `format_report_text(report, detail=...)`（文本路径，本任务不改语义）

## 要求

1. **argparse**（锚定插入现有 `stats_p` 段）：
   - `--html [PATH]`：`nargs="?"`, `const=""`, `default=None`, `metavar="PATH"`，
     help="write a static HTML report (default: <usage_dir>/reports/usage-YYYYMMDD-HHMMSS.html)"
   - `--no-open`：`action="store_true"`，help="do not open the HTML report in the browser"
2. **行为**（`cmd_stats` 内）：
   - 需要产出 HTML 的条件：`args.html is not None`（用户显式要，含 `--html` 空值）**或** `args.detail` 为真（R12 自动）。
   - 路径：显式 `--html PATH` ⇒ 用 PATH（`~` 展开、父目录 `mkdir(parents=True, exist_ok=True)`）；
     `--html` 无值或由 `--detail` 触发 ⇒ `usage.usage_dir()/reports/usage-<YYYYMMDD-HHMMSS>.html`。
   - 写文件：`usage.render_html(report)`，`encoding="utf-8"`, `newline="\n"`。
   - 打开浏览器：**默认打开**；抑制条件（任一）：`args.no_open`、环境变量 `MW_STATS_NO_OPEN` 非空且不为 `0`。
     实现用 `webbrowser.open(path.as_uri())`；异常/返回 False ⇒ `print(f"[mw stats] warning: cannot open {path}", file=sys.stderr)`，**rc 仍为 0**（AC-019）。
   - 输出：`--json` 模式下**不能污染 stdout**（HTML 路径写 stderr：`[mw stats] html: <path>`）；
     文本模式下在末尾追加一行 `html: <path>`。
   - 若 report 里没有 `runs` 键（老调用路径），HTML 里明细表渲染「窗口内没有运行」，不得抛异常。
3. **测试**（`test_stats_cli.py`）：
   - **先给已有的 `--detail` 调用加 `--no-open`**（否则 pytest 会真开浏览器）。
   - `--html <tmp>/r.html` ⇒ 文件存在、含四张分组表标题、含 `runs (newest first)` 同义的 HTML 表头；
     `--no-open` 时 monkeypatch `webbrowser.open` 为「被调用即 AssertionError」，断言未被调用。
   - `--detail --no-open` ⇒ 文本照旧 + 生成默认路径文件（用 `MW_USAGE_DIR` 指到 tmp）。
   - `--detail`（不带 `--no-open`）⇒ monkeypatch `webbrowser.open` 记录调用，断言被调用一次且参数是 `file:///...` URI（AC-019）。
   - `MW_STATS_NO_OPEN=1` ⇒ 不调用。
   - `--json --detail --no-open` ⇒ stdout 仍是纯 JSON（`json.loads` 成功），HTML 路径只出现在 stderr。
   - 打开失败（monkeypatch 抛异常）⇒ rc=0，stderr 有 warning。
4. **文档**：
   - README `## 用量统计（mw stats）`：flag 表加 `--html` / `--no-open` 两行；CLI 表格那一行 flags 追加 `[--html]`；
     小节末尾补一句「`--detail` 会自动把同一份数据渲染成 `~/.mw/usage/reports/*.html` 并打开浏览器」。
   - CHANGELOG `### Added`：一条 bullet（静态 HTML + `--detail` 自动打开 + `--no-open`）。

## 写入允许面

- `packages/multi-workers/mw.py`（**只做锚点插入/局部改**）
- `packages/multi-workers/test_stats_cli.py`
- `packages/multi-workers/README.md`（**只做锚点插入**）
- `packages/multi-workers/CHANGELOG.md`（**只做锚点插入**）
- `.agenticdoc/mw-usage-monitor/workers/<本任务 key>/report.md`

## 写入禁止面

- `packages/multi-workers/usage.py`（T-10 写面；`render_html` 不够用就停下汇报）
- `packages/coding-agent/**`（零 TS 改动）
- `launcher.py`、其它 `.agenticdoc` 文件
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest
- 测试里**禁止**真的打开浏览器（必须 monkeypatch）

## 并发警告（必读）

`mw.py`、`README.md`、`CHANGELOG.md` 工作区里有**其它会话未提交的改动**（`mw decide` 相关，约 4700 行）。

1. 只用精确锚点插入（`edit` 的小 `oldText`），禁止 `write` 整文件、禁止重排/格式化。
2. 锚点找不到 ⇒ 停下汇报，不要猜位置。
3. 不要 `git add`/`git commit`。
4. 自查 `git diff --stat`：本任务新增约 `mw.py +45`、`README +12`、`CHANGELOG +1`，出现大额删除 ⇒ 踩到别人改动，回退汇报。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_stats_cli.py test_usage.py -q
set MW_USAGE_DIR=%TEMP%\mwusage-t11 && python mw.py stats --since 3h --detail --no-open --limit 3
dir %TEMP%\mwusage-t11\reports
python mw.py stats --since 3h --json --detail --no-open --limit 2 | python -X utf8 -c "import json,sys;json.load(sys.stdin);print('stdout is pure json')"
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：`pytest ... -q` 汇总行、生成的 HTML 文件路径与字节数、`git diff --stat` 自查、上面 4 条命令的真实输出。

## 改动历史

- 2026-10-21 创建（PM）：v0.4 CLI 接线（`--html` / `--no-open` / `--detail` 自动打开）。
