# T-07: usage 台账端到端冒烟（research）

- Key: mw-usage-monitor
- type: research
- 写面：只读仓库；只写唯一证据文件（+ 本任务目录 `report.md` 兜底），不写其它任何文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「mw 后台服务（LLM 代理 + 任务调度器），常驻运行」「文件驱动的去中心化协调」；本 key 交付框架可观测性面：本机 token/耗时监控）。
- 本 key 已交付（已提交 `744e95b97`）：
  - `packages/multi-workers/usage.py`（台账读写 + 报告聚合）
  - `packages/multi-workers/launcher.py`（spawn 成功写 `start`、reap 写 `end`，并给 pi worker 显式分配 `--session-id`）
  - `packages/multi-workers/mw.py:7016` `cmd_stats`（`mw stats` 子命令）
- 本次派发本身就是验证样本：**你就是被记录的那次运行**。serve 已用新代码重启（PID 4416，commit `744e95b97`）。

## 要求

1. 读 `.agenticdoc/goal.md`，用一句话说明本 key 与该 goal 的对齐点（不允许复述整篇）。
2. 读 `packages/multi-workers/usage.py`，列出 `build_report` 之前的所有模块级函数名（`def ` 行），并在 `packages/multi-workers/mw.py:7016` 附近确认 `cmd_stats` 的默认窗口值（`--since` 的 default）。
3. 读 `C:\Users\wenbozhou\.mw\usage\runs.jsonl`（只读；若不存在或为空，如实写「不存在/空」并给出 `dir` 是否存在）。用 `task_key` + `pid` 定位**你自己这一行**（`event=start`），原样贴出该 JSON 行（允许截断到 400 字符）；若找不到你这一行，贴出最后 2 行并说明差异。
4. 不要运行 `mw stats`（PM 会跑），不要改任何代码。

## 唯一证据文件

`.agenticdoc/mw-usage-monitor/evidence/research/verify-e2e-ledger-20261021.md`

（框架写面允许 `<key>/evidence/**`；同时可用 `worker_file` 写本任务目录 `report.md` 兜底。**不得写其它任何文件**。）

## 交付格式

- `## 结论`（≤4 条，每条带 `文件:行号` 或台账行）
- `## 证据`（命令 + 原样输出片段）
- `## 残留与未验证`
- `## 上下文来源`
- 末尾一行 `[VERIFY] <你实际执行的命令数> …`

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest。只读命令允许；临时文件放 `%TEMP%`。
