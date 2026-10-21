# T-15: 文档补齐 v0.4–v0.6（HTML 报告 / 全量 run / project 字段 / 数据落盘位置）（coding）

- Key: mw-usage-monitor
- type: coding

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机 token/耗时监控 = 框架可观测性面）。
- 已完成但文档未同步的变更（spec §11–§14）：
  - v0.4：`--html [PATH]` 静态单文件 HTML、`--detail` 自动打开、`--no-open` / `MW_STATS_NO_OPEN`（`usage.py:1814` `render_html`）
  - v0.5：HTML 明细恒为窗口内**全量** run（`--limit` 只作用于文本与 JSON `runs[]`）、`runs_all`/`runs_total`（`usage.py` `build_report(include_all_runs=...)`）
  - v0.6：`runs[].project`（台账 `start.project` → 会话 header `cwd` → `null`），文本/HTML 明细都在 `started_at` 后多一列 `project`（basename，HTML 带 `title` 全路径）
- 用户还问过「数据存在哪」，文档里缺这块，一并补。

## 要求

1. **README**（`packages/multi-workers/README.md`，`## 用量统计（mw stats）` 节内，锚点插入）：
   - flag 表：`--limit` 行补「HTML 不受影响，恒为全量」；`--html` 行补「包含窗口内全部 run」；若缺 `--no-open` 行则补一行。
   - 明细说明：加一句「文本与 HTML 明细都在 `started_at` 之后带 `project` 列（路径末段；HTML 悬停 `title` 显示完整路径）」，
     并在 JSON 契约描述处把 `runs[]` 字段清单补上 `project`。
   - **重渲染 `### 明细样例（--detail）` 代码块**：用真实命令输出替换（`python mw.py stats --since 24h --detail --limit 3 --no-open` 的文本尾部，含新的 project 列；
     可以截取到 `coverage:` 行；保持现有 `text` 代码块格式）。**不要手写假数据。**
   - 新增一小节（放在 flag 表之后）`### 数据落在哪`：台账 `~/.mw/usage/runs.jsonl`（append-only，只存运行元数据，不存 token）、
     HTML `~/.mw/usage/reports/usage-YYYYMMDD-HHMMSS.html`（每次新文件）、token 来源 `~/.pi/agent/sessions/**/*.jsonl` 与
     `~/.claude/projects/**/*.jsonl`（只读、查询时 join、不复制）、目录覆盖 `MW_USAGE_DIR` / `MW_PI_SESSIONS_DIR` / `MW_CLAUDE_PROJECTS_DIR`。
2. **CHANGELOG**（`### Added` 里 mw-usage-monitor 那条 bullet 的**末尾追加**，不新建 bullet）：
   一句 `and every run row now carries `project` (ledger project -> session cwd -> null, basename in text/HTML)` 之类的英文表述；
   若 HTML/全量 run 尚未在那条 bullet 里出现，也一并补进同一句。

## 写入允许面

- `packages/multi-workers/README.md`（**只做锚点插入/替换指定块**）
- `packages/multi-workers/CHANGELOG.md`（**只做锚点插入**）
- `.agenticdoc/mw-usage-monitor/workers/um-t15-docs-v04-v06/report.md`

## 写入禁止面

- 任何代码文件（`usage.py`、`mw.py`、`launcher.py`、`test_*.py`、`packages/coding-agent/**`）
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量测试

## 并发警告（必读）

`README.md` / `CHANGELOG.md` 工作区里有**其它会话未提交的改动**（`mw decide` 相关，4700+ 行）。
只用精确锚点（`edit` 小 `oldText`），禁止 `write` 整文件/重排/格式化；锚点找不到就停下汇报；不要 `git add`。
自查新增量约 `README +25`、`CHANGELOG +1`（相对本任务开始前的状态），出现大额删除 ⇒ 回退汇报。

## 验收命令

```bash
cd packages/multi-workers
python mw.py stats --since 24h --detail --limit 3 --no-open | Select-Object -Last 6
python -m pytest test_autopilot_docs.py -q
git diff --stat -- README.md CHANGELOG.md
```

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据贴：README 改后 `### 明细样例` 代码块原文、`### 数据落在哪` 小节原文、`git diff --stat` 自查结果。

## 改动历史

- 2026-10-21 创建（PM）：补齐 v0.4–v0.6 文档（HTML/全量 run/project/数据位置）。
