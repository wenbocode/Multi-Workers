# T-07 — DRQ-3｜漂移自检设计（serve.meta 身份 / 新鲜进程侧入口 / 边界）

type: research
phase: design
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/design-drq3-drift-selfcheck-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`；本次事故实证：运行中的 serve（PID 116368，启动 `2026-09-26 10:30:42`，408 h）比源码早 **15 天**，`ab546bb64` 引入的提醒守护从未在该进程里存在 ⇒ 212,609 条 timeline 事件里 `gate-reminder` = 0。
- 已核实事实（RQ-3）：
  - `serve.meta` 唯一 writer `packages/multi-workers/mw.py:122-131`（字段 `pid`/`started_at_ms`/`code_dir`，**非原子写**），写于 `:273`、删于 `:398`；4 个读取点**只读 `started_at_ms`**（`mw-runner.ts:207-216`、`monitor.ts:340-355`、`mw.py:5362-5390`）；`code_dir` **无任何读者**；`mw_common` **没有** serve.meta helper。
  - 版本可得性：只有 `_framework_version()`（`mw.py:4354`/`launcher.py:953` = `0.83.0`），从不落盘；无 commit/bundle hash。最小采集 = 复用 `_git_head_short`(`:5187`) + `_git_dirty`(`:5175`) + `_mw_code_newest_mtime`(`:5131`)，但 `_git()`(`:4097`) **今天没有 `timeout` 也没有 `CREATE_NO_WINDOW`**，必须补 + None 降级；比对环节建议**纯文件读** `.git/HEAD`→loose→`packed-refs` 免 spawn；**只靠 commit 会漏 dirty 开发机**（本仓当前就是 dirty）。
  - TS 侧判据 = **纯 mtime**（`mw-runner.ts:224-256`：最新 `.py|.json` mtime vs `started_at_ms + 2000`）；Python 等价物只有 `mw update-env` A3（`mw.py:5112/:5131`），`mw doctor`/`mw status` 完全没有。
  - 分工约定（待你评估）：Python 拥有持久记录（stderr + timeline）+ serve 生命周期限频；TS 只保留交互恢复，不新增周期通知；Python 不自动重启。
  - 上游请求 P2 还要求：重启后复核 pending 门禁未被新自动裁决意外改写。
- 允许自行扩大取证（含 `E:\CLI_workspace\FeatureMigrator\.mw\` 真实 meta 与它的 `AUTOPILOT-HANDOFF.md:454`）。

## 要求

1. **`serve.meta` 身份字段设计**：加什么字段（commit、dirty、模块 mtime、framework version？）、原子写怎么做、旧 meta（缺字段）如何兼容、写入点/删除点要不要动。
2. **比对与告警**：在哪些时刻比对（启动/每 tick/按需）、比对失败的分类（漂移 / 无法判定 / dirty 允许）、告警文案要素、"漂移时长"怎么算、限频键与去重（会话级 vs 持久）。
3. **新鲜进程侧入口**（关键）：既然"运行中的 serve 不可自证"，请设计**至少一个不依赖该进程的入口**（例如 `mw doctor`/`mw status` 从外部比对进程 StartTime 与 `.git` 状态、或面板侧），并给出它如何被自动化验证。
4. **边界与反例**：Windows 无 git bash、`timeout` 缺失会怎样、多 worktree、dirty 工作区、`_mw_code_newest_mtime` 的 skip 集、以及"合并新守护后必须重启 serve"如何变成机器可检（而不是检查单）。
5. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

证据文件必须含以下**四个 H2 段**（逐字）：
`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
