# T-09: `mw stats` 接线 `--until` / `--detail` / `--limit` + 文档（coding）

- Key: mw-usage-monitor
- type: coding
- 前置已完成：T-08（`usage.parse_until`、`build_report(until=..., limit=..., detail=...)`、`runs[]`/`runs_total`、
  `format_report_text(..., detail=...)` 已在 `usage.py`，`pytest test_usage.py` 38 passed）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「本机 token/耗时监控」可观测性面）。
- 需求：`.agenticdoc/mw-usage-monitor/spec.md` §11（v0.3 增补，R7–R10 / AC-014–AC-017）——**以 §11 为准**。
- 既有骨架（不要重写）：
  - `packages/multi-workers/mw.py:9623` `def cmd_stats(args)`（今天只有 `--since/--key/--type/--model/--project/--source/--json`）
  - `packages/multi-workers/mw.py:9657` `def _parse_args(argv=None)`，`stats` 的 argparse 段在其后（搜 `stats_p.`）
  - `packages/multi-workers/README.md` 的 `## 用量统计（mw stats）` 节 + 顶部 CLI 表格里 `stats` 那一行
  - `packages/multi-workers/CHANGELOG.md` 的 `## [Unreleased] → ### Added` 里已有的 usage bullet
- **已知红灯（本任务要消掉）**：`test_stats_cli.py` 现有 3 个用例因 T-08 的契约扩展而红：
  1. `TOP_KEYS` 精确集合断言缺 `until` / `runs_total` / `runs`
  2. 文本首行断言 `startswith("usage since ")`，新首行是 `usage <since> → <until> (<window>)`
  3. 同上的文本快照类断言
  T-08 的报告写了具体修法：把首行断言改成「含 `→` 且含 window」，`TOP_KEYS` 加上三个新键。

## 要求

1. **argparse**（锚定插入到现有 `stats` 段，保持 4 空格缩进）：
   - `--until`：`default=None`，`help="window upper bound (exclusive): 7d / 24h / 30m / YYYY-MM-DD / YYYY-MM-DDTHH:MM (default: now)"`
   - `--detail`：`action="store_true"`，`help="append the per-run table (key / task / type / model / tokens / wall)"`
   - `--limit`：`type=int`，`default=20`，`help="max runs in the detail table and JSON runs[] (0 = all, default 20)"`
2. **`cmd_stats` 接线**：
   - `--since` 解析后解析 `--until`：`usage.parse_until(args.until)`；`None` ⇒ 不传（= now）。
     `ValueError` ⇒ 与现有 `--since` 失败同一路径（rc=2 + stderr 说明格式），**不要新增另一种报错文案**。
   - `until <= since` ⇒ rc=2，stderr: `mw stats: --until must be after --since`（T-08 内核不抛，CLI 负责）。
   - `--limit` 负数 ⇒ rc=2（`mw stats: --limit must be >= 0`）。
   - 传给 `usage.build_report(...)`；`--json` 原样 `json.dumps` 整个 report（`runs[]`/`runs_total` 自动出现，**不要手工裁剪字段**）。
   - 文本模式：`usage.format_report_text(report, detail=args.detail)`。
3. **测试**（`test_stats_cli.py`）：
   - 先修上面 3 个红灯（契约扩展导致，允许改这三处断言）。
   - 追加：`--until` 让窗口外 run 消失；`--until` 早于 `--since` ⇒ rc=2 且 stderr 含 `--until must be after --since`；
     `--until` 非法值 ⇒ rc=2；`--detail` 文本含 `runs (newest first)`，默认不含；
     `--limit 1` ⇒ 文本含 `showing 1 of`，`--json --limit 1` ⇒ `len(runs)==1 and runs_total>1`；`--limit -1` ⇒ rc=2；
     `--json` 不带 `--detail` 也含 `runs`（R8）。
4. **文档**：
   - README `## 用量统计（mw stats）` 节：补 3 行 flag 说明 + 一段 `--detail` 输出样例（用真实渲染，别手写假数据），
     并把 CLI 表格那一行的 flags 从 `[--json]` 扩到 `[--until] [--detail] [--limit] [--json]`。
   - CHANGELOG：`### Added` 追加一条 bullet：「`mw stats` 增加 `--until` / `--detail` / `--limit`（run 级明细）」+ AC 编号。

## 写入允许面

- `packages/multi-workers/mw.py`（**只做锚定插入**）
- `packages/multi-workers/test_stats_cli.py`
- `packages/multi-workers/README.md`（**只做锚定插入**）
- `packages/multi-workers/CHANGELOG.md`（**只做锚定插入**）
- `.agenticdoc/mw-usage-monitor/workers/<本任务 key>/report.md`

## 并发警告（必读）

`packages/multi-workers/mw.py`、`README.md`、`CHANGELOG.md` 工作区里有**其它会话未提交的改动**
（`mw decide` 子命令 + README decide 章节 + CHANGELOG decide bullet，约 480 行）。

1. **只用精确锚点插入**（`edit` 的小 `oldText`），禁止 `write` 整文件、禁止重排/格式化/删除无关行。
2. 锚点找不到（文件被别人改过）⇒ **停下汇报**，不要猜位置塞进去。
3. 不要 `git add`/`git commit`；PM 会按 hunk 精确入库。
4. 改完自查 `git diff --stat -- packages/multi-workers/mw.py packages/multi-workers/README.md packages/multi-workers/CHANGELOG.md`：
   你的新增行数应约为 `+20 / +12 / +1`；出现大额删除或整体位移 ⇒ 踩到别人的改动，回退并汇报。

## 写入禁止面

- `packages/multi-workers/usage.py`（T-08 写面；API 不够用就**停下汇报**，别自己改）
- `packages/coding-agent/**`（含 `ui-bridge.ts`、`mw-runner.ts`：AC-017 明确零 TS 改动，参数由 `splitCommandLine` 透传）
- `launcher.py`、`.agenticdoc/mw-usage-monitor/` 下除本任务 `report.md` 之外的任何文件
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 pytest/vitest

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_stats_cli.py test_usage.py -q
python mw.py stats --since 7d --until 2026-10-21T23:59 --detail --limit 3 | Select-Object -First 25
python mw.py stats --since 7d --json --limit 2 | python -X utf8 -c "import json,sys;d=json.load(sys.stdin);print(len(d['runs']), d['runs_total'])"
python mw.py stats --since 7d --until 2020-01-01 ; echo "rc=$LASTEXITCODE"   # 期望 rc=2
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据必须包含：`pytest ... -q` 汇总行、`git diff --stat` 自查结果、上面第 2/3/4 条验收命令的真实输出片段。

## 改动历史

- 2026-10-21 创建（PM）：v0.3 增补接线任务，依赖 T-08 的 `usage.py` API。
- 2026-10-21 r2（PM）：卡片段落重排为 T-03 顺序（r1 顺序会被派发器打乱导致 envelope 校验失败），
  并补上 T-08 留下的 3 个 `test_stats_cli.py` 红灯说明。
