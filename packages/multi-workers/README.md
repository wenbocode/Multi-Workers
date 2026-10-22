# Multi-Workers — pi 之上的 Agent Team 协作框架

一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目，解决单 Agent 长上下文溢出和无法并行的问题。基于 [pi](https://pi.dev) 扩展系统构建，不 fork pi 核心。

```
PM 窗口 (pi + agent-team-loop, PM 模式)
  ├─ /mw-watch 看板 · /pm-key 认领 key · dispatch 派发
  ▼
mw serve 后台服务 (Python)
  ├─ LLM 代理 (本地隔离端口) · 任务调度 · worker launcher · watchdog
  ▼
Worker 1 (独立 pi 进程)   Worker 2 ...   Worker N
  ├─ agent-team-loop, Worker 模式 (PI_WORKER_TASK 切换)
  └─ .agenticdoc/ 文件协调: task.md → trace.log → output.md → _index.parallel
```

核心性质：

- **进程级隔离**：每个 Worker 是独立 pi 进程，崩溃不影响其他 Worker
- **文件驱动去中心化协调**：无中心调度器，Worker 之间不直接通信，通过 `.agenticdoc/` 下的文件 + 文件锁并发控制
- **Phase 门禁**：沿用 AgenticTask 语义（spec / design / plan / tasks / evidence）
- **凭证隔离**：每个 Worker 只拿到它需要的 API key，其他 provider 凭证从 env 中删除

## 组成

| 组件 | 位置 | 说明 |
|------|------|------|
| mw 服务 | `mw.py` + `launcher.py` + `proxy_multi.py` | 后台常驻：调度器、launcher、看门狗、LLM 代理（可选，见 CLI 参考） |
| agent-team-loop 扩展 | `../coding-agent/src/extensions/agent-team-loop/` | PM 模式（编排）+ Worker 模式（执行），构建后装到 `~/.pi/agent/extensions/` |
| AgenticTask 工作流 | `.agenticdoc/` | spec / design / plan / tasks / trace / evidence 与 `_index.parallel` 索引 |

## 快速开始（新机器一条命令）

```bash
git clone https://github.com/wenbocode/Multi-Workers.git
cd Multi-Workers
python packages/multi-workers/mw.py bootstrap --project .
```

`bootstrap` 按序执行 8 步，全部幂等，可反复重跑：

| 步骤 | 内容 |
|------|------|
| 1 | 前置检查：Python/Node 版本、git，以及**凭据预检**。无可路由凭据不阻断全新安装（此时 `~/.pi/agent/auth.json` 尚不存在）：警告后继续，步骤 2-6 本就无需凭据，**跳过步骤 7**（服务启动），提示配好凭据后用 `bootstrap --fast` 补启 |
| 2 | `npm ci` / `npm install --ignore-scripts` |
| 3 | `npm run build`（根；ai 构建需网络拉取 models.dev） |
| 4 | 全局 link `pi`：已存在则校验链接目标确为本仓库（防 registry 版顶替），失败时提示 `npm uninstall -g` 修复 |
| 5 | `setup`：克隆 AgenticTask 框架 + 全局安装扩展；Windows 上检测并填充 pi 的 `shellPath`（`~/.pi/agent/settings.json`，只在缺失/失效时写入，已有有效值不覆盖） |
| 6 | `init`：创建 `.agenticdoc/` `.mw/` `.pi/extensions/` 脚手架 |
| 7 | `start`：后台启动服务（无凭据路径下跳过，见步骤 1） |
| 8 | `doctor`：全链路诊断，期望 `summary: healthy` |

常用参数：

```bash
--project DIR     控制工作区（默认仓库根）
--from SOURCE     AgenticTask 框架来源（默认远端）
--branch BR       框架分支
--fast            跳过 npm install + 构建（凭据配好后的补启重跑；要求此前完成过一次完整 bootstrap）
--no-start        不启动服务（步骤 1-6 + doctor）
```

## CLI 参考

更新方式总览（版本锚点自检 + 指令矩阵 + 场景最小动作）：见 [UPDATE.md](./UPDATE.md)。

```bash
python mw.py <子命令>
```

| 命令 | 说明 |
|------|------|
| `serve` / `start` | 前台 / 后台运行服务。参数：`--project`（必填）、`--pi-port`（默认 7001）、`--claude-port`（7003）、`--deepseek-port`、`--poll-interval`（2s）、`--max-workers`、`--providers`。LLM 代理按需启动：仅当 claude/claude-cli/deepseek 代理路由有凭证时才拉起（需私有包 `timi-proxy-cli`）；纯 timi/codex 直连路由不起代理、无该包也能正常服务 |
| `stop` / `status` | 停止 / 查看服务 |
| `doctor [--json] [--fix]` | 全链路诊断：服务、代理端口、日志、队列、凭据、bundle、target、pi shellPath |
| `bootstrap` | 新机器一键安装（见上） |
| `init [--no-framework]` | 初始化项目脚手架；`--no-framework` 跳过 AgenticTask 框架安装 |
| `build [--install]` | esbuild 重建扩展 bundle（无 bash 依赖、cwd 无关）；`--install` 同时装到全局扩展目录并重建 pi dist |
| `setup` | 一次性机器初始化：克隆框架 + 全局装扩展 + 自动填充 pi `shellPath`（Windows；幂等，不覆盖已配置值） |
| `pull-agentictask` / `push-agentictask` | 更新 / 推送 AgenticTask 框架 |
| `update-env [--apply] [--json] [--fetch]` | 增量自检（UPDATE.md 锚点：bundle/dist/serve/框架传播）；`--apply` 执行安全修复后复查 |
| `target set/show/clear` | 双工作区配置（见下） |
| `ue-toolchain run/targets/hash` | dual 模式 UE 工具链纪律（见下）：执行模板并留证（错误签名双判 + --watch 前后哈希）、发现 UE 构建目标名、EOL 归一化哈希 |
| `model set/show/clear`、`model set-fallback/clear-fallback` | 派发模型默认值与备用模型链（见下） |
| `decide run/ask/probe/show/set/report/dp` | 决策服务 + 决策替换（见下「决策服务（mw decide）」与 [docs/decision-substitution.md](../../docs/decision-substitution.md)）：DP-1 派发前分诊的旁路调用、人直接问 timi/jev-latest、传输诊断、配置读写、phase 末决策报告、24 个 dp 的授权表指令 |
| `stats [--since W] [--key K] [--type T] [--model M] [--project P] [--all-projects] [--source worker\|pm] [--until W] [--detail] [--limit N] [--json] [--html [PATH]] [--no-open]` | 机器级 token/墙钟台账查询（见下「用量统计（mw stats）」）：model/type/key/project 四组分布 + 覆盖率声明 |
| `run-detached [--cwd DIR] [--run-dir DIR] [--timeout-min N] [--heartbeat-s N] -- <cmd...>` | 后台命令唯一入口：隐藏控制台监督进程 + heartbeat/marker 证据（见下「Windows detached-run checklist」） |

## 用量统计（mw stats）

机器级 token/墙钟台账 + 只读查询面：回答「token 花在哪些模型 / 任务类型 / key / 项目，各占多少，每次
worker 跑了多久」。只统计 token，不读正文。

### 命令

```bash
python mw.py stats [--since 7d] [--until 24h] [--key K] [--type T] [--model M] [--project P] [--all-projects] [--source worker|pm] [--detail] [--limit 20] [--json] [--html [PATH]] [--no-open]
```

pi 窗口内是同一张报表：`/mw stats [<同样的参数>]`。窗口侧是薄包装——扫描、过滤与渲染全部在 Python；
台账是机器级的，窗口面与 CLI 一致，也不追加 `--project`：要收窄就显式传 `--project <dir>`
（`--all-projects` 只是显式声明“不过滤”，与裸跑等价）。

| 参数 | 默认 | 说明 |
|------|------|------|
| `--since` | `7d` | 窗口：`7d` / `24h` / `30m` / `YYYY-MM-DD`（日期 = 本地零点）。非法值 rc=2 并打印可用格式 |
| `--until` | now | 窗口上界，窗口为半开区间 `[since, until)`：`7d` / `24h` / `30m` / `YYYY-MM-DD` / `YYYY-MM-DDTHH:MM`（日期/时刻 = 本地墙钟，相对形式以 now 为基准）。早于 `--since` 或非法值 rc=2 |
| `--key` | 全部 | 只统计该 owner key |
| `--type` | 全部 | 只统计该任务类型（coding / review / research / ...） |
| `--model` | 全部 | `provider/model` 子串匹配（如 `--model glm-5.3`） |
| `--project` | 全机 | 路径或 basename；省略 = 本机所有项目（`/mw stats` 默认也不追加，与本行一致） |
| `--all-projects` | 关 | 显式声明统计全机所有项目（与裸跑等价）；与 `--project` 同时出现 = rc=2 冲突错误 |
| `--source` | 全部 | `worker` = 只 worker 运行；`pm` = 只 PM 窗口会话 |
| `--detail` | 关 | 文本尾部追加 `runs (newest first)` 明细表：一行一次运行（project / key / task_key / type / model / calls / 四个 token 分量 / wall / status）。文本之外还驱动 HTML 报告（见 `--html` / `--no-open`）；JSON 恒有 `runs[]`，不需要 `--detail` |
| `--limit` | `20` | **文本**明细表与 JSON `runs[]` 的最大行数（`0` = 不限），`started_at` 倒序截断；被截断时文本写 `showing N of M runs`、JSON 给 `runs_total`。HTML 明细不受它影响，恒为窗口内全部 run |
| `--json` | 文本 | 输出固定 JSON 契约（`groups` / `totals` / `coverage` / `sources` / `runs[]` / `runs_total`，未知值一律 `null`） |
| `--html [PATH]` | 不生成 | 额外写一份**单文件自包含**静态 HTML（内联 CSS，无外链/无脚本/CDN）：`--html PATH` 写到该路径（父目录自动创建），只写 `--html` 不写值则用默认路径 `<usage_dir>/reports/usage-<YYYYMMDD-HHMMSS>.html`（每次调用一个新文件，不覆盖历史，`MW_USAGE_DIR` 同源）。`--json` 时路径只写 stderr，stdout 仍是纯 JSON；文本模式在末尾追加 `html: <path>`。HTML 明细表包含窗口内**全部** run（标题 `runs (newest first) · N`，不写 `showing N of M`） |
| `--no-open` | 关（打开） | 不调用浏览器。`--html`/`--detail` 默认用 `webbrowser.open(file:///…)` 打开报告；自动化场景用 `--no-open` 或环境变量 `MW_STATS_NO_OPEN=1`（`0` = 恢复打开）抑制。打开/写盘失败只 warn，rc 仍为 0。`--json` 且未显式给 `--html PATH` 时等价 `--no-open`（不弹窗，文件照写；`--json --html PATH` 仍打开） |

### 数据落在哪

| 项 | 路径 | 覆盖 |
|----|------|------|
| 台账 | `~/.mw/usage/runs.jsonl`（append-only，事件 `start` / `end` / `spawn_failed`） | `MW_USAGE_DIR`（整目录） |
| 锁 | `~/.mw/usage/runs.jsonl.lock` | 同上 |
| HTML 报告 | `~/.mw/usage/reports/usage-<YYYYMMDD-HHMMSS>.html`（每次调用一个新文件，不覆盖历史） | `MW_USAGE_DIR`（整目录）；`--html PATH` 只换单次路径 |
| pi 会话（token 真相） | `~/.pi/agent/sessions/**/*.jsonl` | `MW_PI_SESSIONS_DIR` / `PI_CODING_AGENT_SESSION_DIR` / `PI_CODING_AGENT_DIR` |
| claude 会话 | `~/.claude/projects/**/*.jsonl` | `MW_CLAUDE_PROJECTS_DIR` / `CLAUDE_CONFIG_DIR` |

台账只存运行元数据（谁 / 何时 / 哪个模型 / 多久 / 怎么结束），**不存 token**：token 是查询时从会话日志
**只读** join 出来的（现算、不复制、不落第二份）。目录由 launcher 首次写台账时创建
（`USERPROFILE`/`HOME` → `~/.mw/usage`，不用裸 `expanduser`）。
旧 `serve` 进程里的 launcher 不会写台账：升级后需 `/mw restart`。无台账时首屏显式打印 `no ledger yet`
（仍会扫描会话，PM 数据可用）。

### 输出样例

```text
usage 2026-10-12T00:00 → 2026-10-19T00:00 (7d) · ledger 42 events · runs 12 (worker 9 / pm 3)

by model
  timi/glm-5.3             calls 84    in 1.24M  out 310k   cacheR 11.4M   cacheW 42k    wall p50 4m12s  p90 5m30s  n 6
  timi/glm-5.3-flashx      calls 36    in 8.1M   out 920k   cacheR 40.2M   cacheW 305k   wall p50 1h00m  p90 1h00m* n 5

by key
  mw-usage-monitor         calls 84    in 1.24M  out 310k   cacheR 11.4M   cacheW 42k    wall p50 4m12s  p90 5m30s  n 6
  pm                       calls 36    in 8.1M   out 920k   cacheR 40.2M   cacheW 305k   wall p50 1h00m  p90 1h00m* n 5

* = PM 会话跨度（header→末条），非 worker 墙钟

coverage: pi 8 runs (exact) · claude 1 (exact) · codex 1 (未统计)
```

（节选：`by type` / `by project` 与上面同形，四组都输出。`by project` 把临时目录（`%TEMP%` / `/tmp` /
`/var/folders` / `C:\Windows\Temp`）与 `pi-runtime-*` 目录折叠成一行 `(test fixtures)`（`--project "(test fixtures)"`
只选这些行）；折叠只发生在分组表，`--detail` 与 `runs[].project` 仍显示原始路径。）

- 四个 token 分量分列（`in` / `out` / `cacheR` / `cacheW`），`total` 由分项求和；`n<5` 时分位数显 `-`
  （样本不足就不猜，未知 token 也是 `-` 而非 `0`）。
- 墙钟单元格末尾带 `*` 的行：该组分位数来自 **PM 会话跨度**（header → 末条），不是 worker 墙钟。两种样本
  **绝不混源**：组内只要存在 run 墙钟（台账 spawn → reap），会话跨度就不进入分位数（哪怕凑不满 5 也不回填）。
  只要输出里出现 `*`，就在 `coverage:` 之前插入那行脚注。
- `coverage:` 区分「没有运行」与「有运行但未统计」：pi worker / PM 窗口 / claude 精确统计；codex v1 显式
  未统计（无 session id，`token_count` 成对重复），其运行只出现在 coverage，`-` 不计入任何分组。

### 明细样例（`--detail`）

真实渲染（`python mw.py stats --since 24h --detail --limit 3 --no-open`，本机台账 2026-10-21 17:31 快照；
最新 3 行快照时仍在跑，所以 `wall` 是 `-`，`calls`/token 已随会话落盘更新；`by model/type/key/project`
四组在此略去）：

```text
usage 2026-10-20T17:31 → 2026-10-21T17:31 (24h) · ledger 442 events · runs 200 (worker 176 / pm 24)

runs (newest first)
showing 3 of 200 runs (--limit 0 for all)
  2026-10-21T17:31  FeatureMigrator   gui-config-simplify       gcs-059-config-game-path-editable  coding     timi/deepseek-v4.1-flash    calls 3      in 10.2k   out 285     cacheR 12.7k    cacheW 0       wall -       running
  2026-10-21T17:31  FeatureMigrator   gui-config-simplify       gcs-058-project-new-prefill   coding     timi/deepseek-v4.1-flash    calls 6      in 12.5k   out 891     cacheR 52.1k    cacheW 0       wall -       running
  2026-10-21T17:29  E2Feature         feature-llm-semantic-naming  ap-feature-llm-semantic-naming-002-readonly-guard-and-before  phase-writer  timi/deepseek-v4.1-flash    calls 24     in 61.4k   out 10.5k   cacheR 1.12M    cacheW 0       wall -       running

coverage: pi 200 runs (exact)
```

- 一行一次运行，回答「这个 token 是哪次运行 / 哪个 task / 哪个会话烧的」：`calls` 是该运行在窗口内的 provider
  响应数，四个 token 分量同聚合行的口径（未知仍显 `-` 而非 `0`）。
- `started_at` 之后紧跟 `project` 列（路径末段，如 `Multi-Workers`；取不到显 `-`）：文本与 HTML 明细同一列、
  同一取值，HTML 单元格悬停 `title` 给完整路径。JSON `runs[]` 每项含 `project`（台账 `start.project` →
  会话 header `cwd` → `null`），与 `by project` 分组同源。
- JSON `runs[]` 每项：`run_id` / `started_at` / `project` / `ended_at` / `key` / `task_key` / `type` / `model` /
  `calls` / `tokens`（`input` / `output` / `cache_read` / `cache_write`）/ `wall_s` / `wall_kind` / `status` /
  `attribution` / `session_id` / `open_run`；`claims` 只在可测量时出现。
- 倒序（最新在上）；`--limit` 截断时一定有 `showing N of M runs (--limit 0 for all)`，JSON 侧对应 `runs_total`。
- `open_run=true`（有 `start` 无 `end`）的行 `wall` 显 `-`（JSON `wall_s: null` / `wall_kind: "none"`）：台账还没有
  reap，绝不拿会话跨度回填。没有台账行的 PM 会话也占一行，其 `wall` 带 `*`（会话跨度），保证明细 token 之和
  与 `totals` 自洽。

`--detail` 会自动把同一份数据渲染成 `~/.mw/usage/reports/*.html` 并用默认浏览器打开（文本照旧打印，`--no-open`
或 `MW_STATS_NO_OPEN=1` 关闭；`--html <path>` 换路径）。

### 隐私边界

只读会话里的 `usage` / `model` / `provider` / `timestamp` / `message.id` 与 header 的 `id` / `cwd`；
不读、不落盘 prompt/响应正文（`message.content`、`custom_message.data`）。台账只追加运行元数据。
机器级单文件、纯本地、无网络调用。

## Windows detached-run checklist

> 事故依据（2026-10-15 控制台窗口风暴）与实证：`evidence/research/design-win32-console-semantics-20261015.md`（M1/M2/M3）。本清单是 spec AC-009 的文档交付面。

### 三事实（Win32 console 语义）

1. **`DETACHED_PROCESS` × `CREATE_NO_WINDOW` 互斥**：两者都要决定子进程的控制台归属，不能同时表达。
2. **组合时 `DETACHED_PROCESS` 静默生效**：同时传 `DETACHED_PROCESS | CREATE_NO_WINDOW` 时 `CREATE_NO_WINDOW` 被忽略，子进程得到的是「无控制台」而非「隐藏控制台」——不报错，因此极易误判为安全。
3. **后代进程窗口外溢**：一旦祖先处于「无控制台」，孙代（及更深）以 `creationflags=0` 裸 spawn 时，每个进程都会被分配新的可见控制台窗口（1:1 弹窗，owner = `WindowsTerminal.exe` / `OpenConsole.exe` / `conhost.exe`）。

**判据（不要用 `GetConsoleWindow`）**：`GetConsoleWindow()` 对「隐藏控制台」和「无控制台」都返回 0，无法区分。唯一可靠判据是 `GetConsoleProcessList()` 的计数：隐藏控制台 `> 0`，无控制台 `== 0`。差分实测窗口用 EnumWindows 按 hwnd 去重 + owner exe 过滤（AC-001 verify 用此法）。

### `mw run-detached`（后台命令唯一入口）

```bash
python mw.py run-detached [--cwd DIR] [--run-dir DIR] [--timeout-min N] [--heartbeat-s N] -- <cmd...>
```

派发后 stdout 恰 4 行 handoff（调用方按等号解析）：

```
[mw run-detached] pid=<supervisor_pid>
marker=<run_dir>/marker.json
heartbeat=<run_dir>/heartbeat.json
log=<run_dir>/run.log
```

契约（spec AC-003/AC-004）：

- `marker.json` = `{schema:"mw-run/1", rc, timed_out, started_at_ms, ended_at_ms, wall_sec, pid, argv}`，在监督进程退出前原子落盘；timeout 致死 `rc=124` + `timed_out=true`，spawn 失败 `rc=127` + `spawn_failed=true`。PM 轮询 marker 判定完成。
- `heartbeat.json` = `{schema:"mw-heartbeat/1", pid, ts_ms}`，按 `--heartbeat-s`（默认 5s）原子更新；`run.log` 为子进程 stdout+stderr 合流。
- win32 监督进程固定 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`（**绝不使用 `DETACHED_PROCESS`**），用户命令以 `flags=0` 继承其隐藏控制台；posix 用 `start_new_session=True`。
- guard 默认注入（`MW_CONSOLE_GUARD=1` + `PYTHONPATH` 前置 guard 目录，仅 win32）；`MW_CONSOLE_GUARD=0` 显式退出。
- 默认 run_dir：`<cwd>/.mw/runs/run-<YYYYMMDD-HHMMSS>/`；已存在时追加 `-N` 后缀。

**Console guard 机制（L2）**：guard 是随框架发布的 `mw_console_guard/`（sitecustomize 风格），仅在 env 开关 `MW_CONSOLE_GUARD=1` 时激活，对子树内 `subprocess.Popen/run` 的 `creationflags=0` 调用 OR 上 `CREATE_NO_WINDOW`；显式传入 `CREATE_NEW_CONSOLE`/`DETACHED_PROCESS` 的调用原样保留，env 未设时零行为差异（fail-open）。

## 派发模型默认值

`mw model set <role> <provider/model>` 配置各角色的默认模型，未显式指定 `model:` 的任务在派发时逐层回退：

```
task.md model:  >  dispatch.yml [role]  >  当前窗口模型  >  每路由硬编码默认
（显式指定）        （前缀需匹配路由）     （.mw/window-model）  （pi+timi→glm-5.3、codex→gpt-5.6-sol）
```

角色：`main`（PM 主窗口，无显式选择时 session_start 套用）、`coding`（coding/phase-writer/repair/roadmap-writer/无类型）、`review`（review/verifier/reviewer）、`research`。配置存于项目级 `.mw/dispatch.yml`（gitignore，随机器本地）。

模型值用 `前缀/模型 id` 命名空间，前缀选择供应渠道：

| 前缀 | 渠道 | 说明 |
|------|------|------|
| `timi/` | pi + timi 直连 | 默认路由 |
| `claude/` | pi + anthropic 直连 | 不走 mw 代理，ANTHROPIC_API_KEY 直连 |
| `codex/` | pi + openai-codex | 用 codex 自身配置，无需代理凭证 |
| `deepseek/` | pi + deepseek 直连 | 不走 mw 代理 |
| `zai/` | pi + zai-coding-cn 直连 | 不走 mw 代理，ZAI_CODING_CN_API_KEY 直连 |
| `codex_cli/` / `claude_cli/` | CLI 执行器 | 仅匹配对应 cli 的任务 |
| 裸 id（无前缀） | 任务原路由 | 兼容现有行为 |

前缀生效时覆盖任务的 provider 但**不换 cli**（工具白名单/watchdog/模型徽标是 pi worker-mode 功能）；不兼容或未知前缀的默认值跳过落到下一层，显式 task.md `model:` 值不兼容则报错进 worker.log。未配置时 worker 默认与主窗口模型一致（`.mw/window-model` 由主窗口扩展在 session_start/model_select 时记录）。

```bash
python mw.py model set --project . coding timi/glm-5.3
python mw.py model set --project . review timi/glm-5.3-air
python mw.py model show --project .      # 配置 + 窗口模型 + 各角色实际生效值 + 备用链
python mw.py model clear --project . review
python mw.py model set-fallback --project . review timi/deepseek-v4.1-flash,zai/glm-5.3   # 备用链（按序尝试，1..4 个）
python mw.py model clear-fallback --project . review
```

PM 窗口里也可用 `/mw model`（转发到同一 CLI）：`/mw model show` · `/mw model set <role> <prefix/model>` · `/mw model clear <role|all>` · `/mw model set-fallback <task-type> <m1,m2>` · `/mw model clear-fallback <task-type>`。worker 角色下次 spawn 生效（无需重启 serve）；`main` 角色在窗口下次启动时套用。

`mw doctor` 的 `dispatch` 段展示配置状态；配置文件损坏仅降级为建议（不阻断派发，回退窗口模型/硬编码默认）。

### 模型故障降级（fallback_models，mw-model-error-perception）

worker 遇到模型层故障（HTTP 5xx / 拒绝连接 / 流中断）时按「同模型重试 → 备用模型链 → failed」有界收敛，不再伪成功，也不再无限重派。配置写在 `.mw/dispatch.yml` 顶层，用 `mw model set-fallback <task-type> <m1,m2,...>` / `clear-fallback` 写入（或手编 YAML；注意 CLI 写入是 YAML 重新序列化，手写注释不保留）：

```yaml
fallback_models:
  coding: [claude/claude-sonnet-5, deepseek/deepseek-chat]
  review: [timi/glm-5.3-air]
  research: [timi/glm-5.3]
```

- 键是任务类型（`coding`/`phase-writer`/`repair`/`roadmap-writer`/`review`/`verifier`/`reviewer`/`research`/`rag-research`/`vision`/`decide_prepare`；未命中精确键时回退其 role 桶），值是 1..4 个 `前缀/模型 id` 单行字符串（前缀见上表；`*_cli` transport 前缀不接受）。列表内**重复项被接受并去重**（保留首次出现，大小写归一，故 `A/x,a/X` 等价于 `a/x`）；真正的格式错误（未知键 / 超上限 / 非 `前缀/模型` / 空项 / 项内换行）由 `mw model set-fallback` 拒绝写入、由 `mw doctor` 报 issue，route 缺失或凭证不可用报 suggestion；读取失败软降级为「无备用链」，不阻断派发。`main` 角色无 worker fallback。
- 触发：worker 首个「run 内 auto-retry 耗尽」的 error run 即 `exit 3` 并写 `run.json` `model_exhausted: true`（同时写 `[MODEL_ERR]` trace 行、`## Exit Reason` 以 `model unavailable:` 开头）。launcher 在状态映射前拦截：先对**同一模型**按 `PI_WORKER_MODEL_ERR_MAX`（默认 2；`0`=直接切备）重试进程，每次写 `[MODEL_RETRY] <iso> model=<m> attempt=<k>`；预算耗尽后按数组顺序用下一个备用模型重派同一任务（`--model`、`PI_WORKER_FALLBACK_INDEX`+1、`PI_WORKER_TRIED_MODELS` 追加），写 `[MODEL_FALLBACK] <iso> from=<m> to=<n> attempt=<k>`。候选 route/凭证预校验不过则写 `[MODEL_FALLBACK-SKIP]` 并续试下一个；链耗尽 → `failed`（Exit Reason 透传 `model unavailable:` 链）。
- 无备用链的类别：同模型重试耗尽后直接 `failed`。
- 计数以文件为事实源：同模型预算由 trace.log 的 `[MODEL_RETRY]` 推导、链进度由 `[MODEL_FALLBACK]` 推导，launcher/serve 重启后从证据续跑（不重置、不重复）。重派是进程级（task.md + 磁盘产物重播种），不调用 `setModel`、不写全局设置。
- 挂起型模型故障：error 边界事件不喂活动钟，无在飞工具的 idle 击杀改判 `exit 3` 进降级链（`[IDLE_KILL] ... last_model_error=yes|no`）；有在飞工具的挂死仍 `exit 1`。

### 派工类型与模型覆盖门禁（mw-dispatch-role-escape）

`dispatch_worker` 工具与 `/worker` 命令都可显式声明任务类型，直接选择对应的 dispatch.yml role 与 worker 工具白名单：

- `type: coding | review | research`（工具参数 `type`，命令 `--type`；省略时按 cli 推导：pi→coding、claude→review、codex→codex）。此前 pi 任务恒为 `coding`，`review`/`research` 档对 pi 不可达——只能靠手填 `model:` 绕过策略。
- 覆盖 role 默认值必须给出理由：`model_reason`（工具）/ `--reason`（命令），记录为 task.md 的 `model-reason:` 单行；缺理由直接拒绝派发（不建目录、不写队列行）。请求值与 role 默认值相同时不写 `model:` 行（配置保持唯一事实来源，改配置即生效）。
- pi 路由的模型值（显式值或本次生效的 role 默认值）在派发时对照 pi 模型表校验：不在表内（如 `timi/gpt-5.6.sol`）直接拒绝，避免 pi 把它静默当作 custom model id 使用。`codex_cli/`/`claude_cli/` 前缀与 cli ≠ pi 的任务跳过校验；模型表缺少该 provider 时不判错；逃生口是显式 `model` + 理由。
- launcher 在 task.md 显式值偏离 role 默认值时，于原有 `source=task` 行后追加 `[launcher] <key>: model-override task=<X> config:<role>=<Y>` 到 launcher.log（仅证据，解析顺序与派发行为不变）。

## 双工作区：代码目录与工作目录分离

默认 **single 模式**：控制工作区与目标项目是同一个目录。配置 `target.yml` 后进入 **dual 模式**：

```
控制工作区 (control root)                  目标项目 (game root)
├─ .agenticdoc/          ← 所有协调文件    ├── Source/ ...
├─ target.yml            ← 配置本体        └── ProjectX.uproject
├─ _index.parallel                          引擎根 (engine root, 可选)
└─ {key}/workers/{task}/task.md
   └─ trace.log / output.md ← 写回这里
```

- Worker 进程 **cwd = game root**（相对路径、工具链锚定目标项目）
- 一切**协调写入**（trace.log / output.md / phase docs / goal check）通过 `PI_WORKER_TASK` 反推 control root，写回控制工作区——**目标树零框架文件**
- `read_scope` 相对条目按 game root 展开，`ignore.deny_globs` 作为上下文防火墙（deny 优先于 allow）
- 派发时把 toolchain / 防火墙清单 / contract 注入 task.md，Worker 无需感知 target.yml 的存在
- 配置坏时 fail-closed：拒绝派发，不静默下发未注入的 task.md

### 配置方式

CLI（优先级：env > target.yml > single 默认）：

```bash
python mw.py target set --project <控制工作区> \
    --game <UE项目根> \
    [--engine <引擎根>] [--vcs git|p4|none] [--uproject <.uproject>]
python mw.py target show --project <控制工作区>   # 查看解析后的生效视图
python mw.py target clear --project <控制工作区>  # 删除 target.yml，回到 single
```

pi 窗口内（新窗口生效）：

```
/mw target show
/mw target set --game "D:\My Game" --engine D:\UE5 [--vcs git|p4|none] [--uproject <file>]
/mw target clear
```

`set`/`clear` 自**下一次 worker 派发**生效，无需重启 serve（launcher 每次 spawn 重新解析）。带空格的路径用双引号。
环境变量临时覆盖（不落盘）：`MW_TARGET_GAME` / `MW_TARGET_ENGINE`。
`target.yml` 三个手工维护段（`mw target set` 只管理 bootstrap 字段，不碰这些）：

```yaml
toolchain:
  # 带 {game}/{engine}/{uproject} 占位符的命令模板（PM 直执走 mw ue-toolchain run，见下）
ignore:
  deny_globs: ["**/*.uasset", "**/DerivedDataCache/**"]   # L1 上下文防火墙
contract:
  forbidden_paths: [...]
  conventions: |
    项目约定，注入每个 task.md
  docs: [docs/api.md]
```

### 工具链执行纪律（mw ue-toolchain）

**定义域**：dual 模式的 UE 游戏开发项目（游戏仓 + 引擎源码仓 + `.uproject`，MSVC/UBT 工具链）。`run` 的留证/判定纪律和 `hash` 是工具链无关的通用件；`targets` 目标发现（`Source\*.Target.cs`）和 `errors.txt` 错误签名（`error C` / `LNK` / `error :`）是 UE/MSVC 专用。

toolchain 模板不只是注入 task.md 的文档——PM 直执时用 `mw ue-toolchain` 落地[dual 实践指南](./docs/dual-toolchain-practice-guide.md)的通用纪律：

- `python mw.py ue-toolchain run <name> --project <dir> [--args="-MaxParallelActions=16"]`（`--args` 值以 `-` 开头时必须用等号形式）—— 控制工作区根执行渲染后的命令，工件落 `<control>/.mw/toolchain-runs/<时间戳>-<name>/`：`cmd.txt`（逐字命令留档）、`run.log`（UTF-8 合并输出，`.log` 扩展名——质检脚本只扫 `*.log`）、`exit.txt`（退出码）、`errors.txt` + `meta.json`（错误签名扫描 `error C` / `LNK` / `error :`——退出码必要但不充分）；`--watch <file>` 前后 EOL 归一化 sha256，证明命令执行期间无人改被编译源码；`--out` 可把 run 目录指到 key evidence 归档。mw 退出码 0 = exit 0 ∧ 错误行 0 ∧ 无漂移；差分验收（基线本来就红的项目）对比两次 run 的 `errors.txt` 集合。
- `python mw.py ue-toolchain targets --project <dir>` —— 从 `<game>/Source/*.Target.cs` 现查构建目标名（`*Editor` = editor target），勿猜。
- `python mw.py ue-toolchain hash <file>...` —— EOL 归一化 sha256（引擎仓 `core.autocrlf=input` 会在 checkout/rebase 时把 CRLF 翻成 LF，字节级哈希会假漂移）。

## pi 窗口命令

| 命令 | 说明 |
|------|------|
| `/pm-key <key>` | 认领并 watch 一个 AgenticTask key |
| `/pm-save` | 会话快照写入 `pm-state.md` |
| `/mw-watch` | 切换 Worker 进度看板 widget |
| `/worker <claude\|codex\|pi> [--model <id>] <任务描述>` | 派发一个 worker |
| `/mw build \| init \| start \| stop \| status \| doctor [fix] \| update [--apply]` | 服务与 bundle 管理（update = 锚点自检，见 [UPDATE.md](./UPDATE.md)） |
| `/mw target show \| set \| clear` | 双工作区配置（见上） |
| `/mw ack <task-key> \| all` | 确认终态 worker 结果 |

### 实施准入门禁（mw-implementation-gate）

非 trivial 实施（新功能、多文件改动、超出一行修的东西）必须先有 active key——这条纪律现在由 agent-team-loop 扩展的 `tool_call` 硬门机械化执行：write/edit（以及 bash 写目标收窄判定）命中仓库代码路径（`packages/**` 代码扩展名，排除 node_modules/dist/.tmp）且窗口无 active key claim 时拒绝执行，reason 内给出两条合规路径。放行条件（任一）：

1. `_index.parallel` 中存在本窗口 host:pid 的 active claim（写 `.agenticdoc/<key>/spec.md` 即自动 claim）；
2. `PI_WORKER_TASK` 存在（被派发的 worker 预授权）；
3. 新鲜（≤24h）的 `.agenticdoc/<key>/mini-spec.md`（trivial 修复快路径，放行留审计行）。

每次 block 与 mini 放行追加一行到 `.agenticdoc/_impl_gate.log`（best-effort，不影响判定）。bash 侧只判写结构的目标参数、声明非沙箱（`python -c` 内联写等已知漏过，见模块头注释）。生效条件：`mw setup --build` 重建 dist 并重启窗口；旧 bundle 进程重启前不受门禁。

## Autopilot 配置与停滞处置（mw-autopilot-stall-feedback）

`.agenticdoc/_autopilot/config.json`（缺失即默认；存在但非法会 fail-closed 报错）：

| 键 | 默认 | 说明 |
|----|------|------|
| `enabled` / `paused` | false / false | 总开关；`mw serve` 据此启停 conductor |
| `poll_interval_sec` | 4 | tick 周期（1..5，受 AC-019 心跳预算限制） |
| `max_parallel_keys` | 2 | 同时推进的 key 上限 |
| `round_budget` | 2 | L1↔L2 / L3 复评 / 任务重试共用的轮数上限 |
| `advance_stall_ticks` | 5 | 同一 `(key, edge)` 的 phase 推进连续失败次数阀值（1..50）；达阼值即把 key 标 `stalled` 并建门禁 |
| `worker_timeout_min` | 30 | worker 墙钟兜底超时 |
| `launcher_max_workers` | 8 | 单轮并发 spawn 上限（1..64） |
| `dispatch_max_per_scan` | 3 | 每轮自动派发配额（1..64） |
| `queue_alarm_delta` | 50 | 队列突发形态判据阈值（10..10000） |
| `l3_abort_retry_limit` | 1 | L3 流中止独立重掷预算（0..10） |
| `gate_reminder_after_min` | 30 | 待应答门首次提醒阈值（1..1440 分钟） |
| `gate_reminder_max` | 2 | 每门最多提醒次数（1..2） |

停滞处置：

- 每次失败的 `advance` 事件带分类（`class=interface-drift|gate-blocked|timeout-env|other`），连击从 timeline 尾部重派生（无私有状态），因此 conductor 重启不丢。
- `approve` 一个 `stalled` 门禁 = 该 key 回到 `running`，且 L2 / EXECUTE / L3 / repair 四个预算点**各放宽一轮**（额度 = 该 key 已批准的 stalled 门禁数）；该额度**不可复用**——每个回路自己的轮次计数是单调的，用掉那一轮后同一回路会再次到顶、需要新的人工决定；`reject` = 既有 `closed-legacy` 语义。
- `L3 无裁决`：reviewer worker 崩溃（`output.md` 缺失）不再被当成 `below`，而是重派下一轮 L3，停滞原因也写明 worker 状态与 task_key。
- 新增 timeline 事件类型：`resume`（人工 approve 后恢复）、`l3-no-verdict`（reviewer 未交裁决）。
- PM 窗口底部监控面板会展示 tick 新鲜度 / 槽位 / 每 key 相位与状态 / 停滞连击与最近错误，并在 `stalled` 行给出 `/autopilot gate <id> approve|reject` 处置命令；面板的连击派生与 conductor 守卫同口径（只有**同一 edge** 的成功才清除，相邻边界的成功既不打断也不计入），唯一差异是面板会保留 `stalled`/`gate-created` 之后的那一轮连击以便展示。

### G3 契约闸门（mw-gate-verdict-hardening）

`mw autopilot contract-guard [--project P] [--key K] [--json]`：只读判定——冻结的 AC/VC 文本（`<key>/evidence/contract-freeze.json` 内容寻址锚）与已答复授权记录是否一致；无锚点、无 carrier 均按无授权处理。`mw autopilot contract-freeze --project P --key K [--block ac|vc|all] [--force] [--json]`：显式补/重冻锚点（conductor 在 `design`/`plan` 接受边界已幂等自动建立），只有 `--force` 才允许覆盖已变更块。`advance *->done` 前做机械身份检查，未授权改写 ⇒ `contract-refused` 事件 + `contract-unauthorized` stall。

## Autopilot 可观测面与生效动作（mw-autopilot-gate-alarm-liveness）

本 key 把 autopilot 从"靠推送、可能永久静默"改为"状态面恒可见 + 能自动就自动"：pending 门禁与 stage 主闸由**磁盘状态逐帧派生**（无 cap/衰减/去重，不依赖 timeline 事件），提醒按 key 抑制且被抑制也留痕，serve 能自证代码版本，`stage-close` 有确定性证据即自动放行、缺证据回落并点名。完整的 9 个可观测面（逐项 `path:line` 锚点）与失效边界见 **[`docs/autopilot-observability-guide.md`](docs/autopilot-observability-guide.md)**。

**生效动作（必须先看）**：

| 改动面 | 必须执行 |
|--------|----------|
| Python（`autopilot/**.py`、`mw.py`、`mw_common.py`） | **`/mw restart`**（每个项目各一次；conductor 是 serve 子进程，只在启动时 import） |
| TS 扩展（`packages/coding-agent/src/extensions/agent-team-loop/**`） | **`mw build --install`（或 `/mw build`）+ `/mw restart` + `/reload`** |
| 只读 CLI（`mw autopilot gates`、`mw status`、`mw doctor`） | 无需重启（每次新进程读磁盘） |

**运行期实证**：TS 账本（`shared/change-ledger.ts`）修复在**旧 bundle** 下无效——源码改了、bundle 没重建 = 行为没变（T-16 终态仍报 4 条已修误判）。两侧 config schema 互相 fail-closed，触及 schema 的改动必须两侧同版本上线（先 `build --install`，再重启 serve）。

可观测面速查：

- **常驻状态面**：pending 行（id/kind/stage/key/age/抑制原因/scope 可解析性）+ **stage 主闸行**（stage 状态 + 卡在哪道门 + 已等时长 + 被冻结 key 列表）。插入点 `monitor.ts readMonitorState → renderMonitorLines`，stage 行 `deriveMonitorStages`。
- **编码与预算**：`~D`（漂移）、`R:queue/R:flight/R:cap/R:term/R:notdue/R:scope`（原因短码）、紧凑 age、末列 `+N`（压缩掉几个次要字段）、`J`/`P`（blocker 类）、110 列 fit ladder（必显三件套永不丢）。
- **抑制可视**：`key-in-flight / stage-terminal / cap-reached / not-due / unresolved-scope / gate-queue-unreadable` 六值（封闭枚举、派生不落盘、优先级=漏斗序）；被抑制每窗口一条 `phase:"remind-suppressed"` 台账行；cap 用尽只停"打断"、状态面标注"已达打断上限，仍待处理"；发射走 stderr + timeline 双通道。
- **serve 漂移自证**：`.mw/serve.meta` 含 40 位 commit / dirty / `code_digest` / `schema`；`mw status`、`mw doctor`（exit 1）判 `STALE CODE` / `CAPABILITY DRIFT`；digest 相等而 commit 移动只记 `history-only`（不告警）；serve 环路 60s 自查、限频、**不自动重启**。
- **`stage-close` 自动收证放行**：五判据全从磁盘现算（stage 可解析 / key 全终态 / 无在飞 / 无 reconciliation 争议 / dossier + 终态凭据齐备）；`answered_by="conductor-auto:<rule>"` + `phase:"decide"` 台账；缺证据回落并**点名缺失项**；默认 `auto_gate_mode=off` + shadow 门槛。
- **re-attest / reject 二次确认**：re-attest = 新 gate + `context_refs: reattest-of:<id>`（编号不复用、原判定留痕）；`reject` 未 `--confirm-destructive` 在任何写之前拒绝（**状态机内不可逆；恢复 = 人工改 `_roadmap.md` 一行，代价无审计痕迹 + 轮次不退**）。
- **`blocker_class`**：序外标量 `{paperwork, judgment}`（冻结 40 名序之外注册，标量平行集）；parser 保留 `None`、只有判定层折 `judgment`；monitor 以 `J`/`P` 一列显示。
- **合成 claim**：`autopilot@<host>:<pid>` 创建/续期（60s 心跳）/按 serve 身份失效回收；人工 `switch_key` 优先且 conductor 让位留痕；外机合成 claim 不抢不覆盖；窗口重启复认领会落 `tookOverFromConductor` 痕迹。
- **回收契约**：writeless 角色只把声明交付物当写入意向、`<key>/evidence/**` 新鲜交付物走磁盘通道、未展开变量 `malformed`；infra 白名单收窄为**文件级 basename**；声明了但磁盘不存在的路径走 **`## Ledger Unresolvable`** warn 段（不进 `extra`，也不静默）。

## xkey 验证命令（mw autopilot verify）

`mw autopilot verify` 是 conductor 的 xkey 验证通道配置入口（四个键：`xkey_verify_cmd` / `xkey_verify_cwd` / `xkey_verify_timeout_s` / `xkey_repair`）。CLI 是项目文件的写者（锁内 read-modify-write）。

<!-- mw-autopilot-verify:help -->
```text
usage: mw.py autopilot verify [-h] {set,show,clear} ...

positional arguments:
  {set,show,clear}
    set             Set the verification argv (dry-run validated under the
                    config lock)
    show            Print effective values, origins and the expanded argv/cwd
    clear           Remove the four xkey keys (never deletes the file)

options:
  -h, --help        show this help message and exit
```

```bash
python mw.py autopilot verify set --project <dir> [--timeout SEC] -- <argv...>
python mw.py autopilot verify show --project <dir> [--json]
python mw.py autopilot verify clear --project <dir>
```

- `--project` **必填且必须在 `--` 之前**：`--` 之后的 token 逐字进入 `xkey_verify_cmd`，`--project` 出现在其后会被吞进 argv，所以 argparse 直接报错（缺必填参数）。
- `clear` 只移除四个 xkey 键、其它字段值不变，**永不删除文件**；文件缺失 = autopilot 从未启用，打印 `nothing configured` 并退出 0（不建目录、不写文件）。
- `show` 打印有效值 + 逐字段 `[origin]`；`--json` 给机器可读形态。

### 两层配置

| 层 | 路径 | 用途 |
|----|------|------|
| 机器级 | `~/.agents/autopilot-defaults.json` | 本机默认，**只允许**覆盖 `xkey_verify_cmd` + `xkey_verify_cwd` 两个键，fail-soft |
| 项目级 | `<control>/.agenticdoc/_autopilot/config.json` | 项目配置（四个 xkey 键），fail-closed |

机器级路径解析顺序与 RAG 一致：`MW_AUTOPILOT_FILE` → `MW_AUTOPILOT_HOME` → `HOME` → `USERPROFILE`，各自拼 `/.agents/autopilot-defaults.json`。`MW_AUTOPILOT_FILE` 是整文件硬覆盖：`MW_AUTOPILOT_FILE` 指向的文件不存在时不回落到其它位置（该层为空）；两层文件缺失都不建目录。机器层是 **fail-soft**：未知键、类型/范围非法的已知键只丢该字段并记诊断，不整份作废。

优先级 `project > machine > default`，规则是**空值即未决定**：两个写者都会把 13 键材料化写进项目文件，所以项目层的 `xkey_verify_cmd: []` / `xkey_verify_cwd: ""` 视为未决定，让给机器层；项目层非空则项目胜出；两层均空/缺失回落到内置默认。机器层只允许覆盖 `xkey_verify_cmd` + `xkey_verify_cwd`，其余键越域（如机器层写 `xkey_repair` / `xkey_verify_timeout_s`）⇒ **告警并忽略**。

**两侧同版本上线**：先 `mw build --install`，再重启各 pi 窗口的 `serve`——旧 bundle 的 `validateConfigData` 读含新键（`xkey_verify_cwd`）的文件会 fail-closed，两侧必须同版本。

## claims 派发契约（conductor 侧预算）

派发卡可以用 `<!-- mw-claims: v1 -->` 块声明本次要证伪的断言，七列：
`claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算`。conductor 只做两件事：解析这张卡，
把**这张卡自己的** claims 折算成 worker 的读取预算。改动前 caps 在读卡之前就算，所以只能拿到上一张卡的预算。

- 解析（`autopilot/dispatch.py::parse_claims_block`）与 TS `shared/dispatch-card.ts::parseClaimsBlock` 同语法：
  结束标记缺失时容错到下一个 H2 或文件尾，fence 内的示例表不参与解析，表头别名与列序任意、
  全角 `：｜` 与全角数字归一，`C-01.3` 子行只能挂在 `struct` 父行下；不可解析的行进 `errors`，永不抛异常。
- caps 推导（`claim_budget_caps`，两字段各自独立）：
  - `l2_read_file_cap = min(30, Σ(类型 == manual ? 2 : 1))` —— manual 记双倍，它买的是 PM 注意力而不是 worker 取数；
  - `l2_read_byte_cap = min(393216, 65536 × n)`，`n` = claims 条数；
  - 预算两常数只在 `CLAIM_BUDGET` 里定义一次（与 TS 同名同值）；`CLAIM_TYPES` / `UNVERIFIED_REASONS` /
    `CLAIM_GATE_DEFAULT` / `CLAIM_BUDGET`（五键）全部由 `test_claim_parity.py` 逐字逐序锁住。
- 优先级：项目层 `.agenticdoc/_autopilot/config.json` **显式写的** `l2_read_file_cap` / `l2_read_byte_cap`
  逐字段胜出，只有缺的字段才用卡推导值。
- 无 claims 的卡、以及 conductor 合成卡（没有卡文件）的路径：不写 `read_scope`、不写 cap 行，
  字节与改动前一致；claims 块随卡注入 task.md 由 TS 派发层负责（D-002），conductor 侧只解析与预算。
- 生效条件：`/mw restart`（conductor 是 serve 子进程，模块只在启动时 import）。

**门禁灰度**：`advisory` 是默认，卡里有问题只告警、派发照走（回执一行 `[claims] ...`）；
`enforce` 必须显式开启（`MW_CLAIM_GATE=enforce`），才会把 claims 问题变成拒绝（零副作用）。
非法/空值回落 `advisory` 并往 stderr 打一行 `[CLAIMS] claim_gate=<值> fallback=advisory`——
门禁是 opt-in，拼错既不能静默升级成强制、也不能把回路卡死。两侧同名同义：
TS `pm/ui-bridge.ts::claimGateMode` 与 Python `autopilot/dispatch.py::claim_gate`。

## 关键环境变量

| 变量 | 说明 |
|------|------|
| `PI_WORKER_TASK` | Worker 的 task.md 路径；设置即进入 Worker 模式 |
| `PI_WORKER_TIMEOUT_MS` | Worker 墙钟兜底（默认 60m；task.md `timeout:` 分钟头优先） |
| `PI_WORKER_IDLE_MS` | 无活动判挂死阈值（默认 10 分钟） |
| `PI_WORKER_MODEL_ERR_MAX` | 同模型进程重试预算（launcher 读自身 env，默认 2；`0`=直接切备用链） |
| `PI_WORKER_FALLBACK_MODELS` | 备用模型链（csv `前缀/模型`，launcher 注入 worker） |
| `PI_WORKER_FALLBACK_INDEX` | 已消费的备用模型数（launcher 注入 worker，0 起） |
| `PI_WORKER_TRIED_MODELS` | 已耗尽模型链（csv，含主模型；launcher 注入 worker，worker 追加当前模型） |
| `MW_CLAIM_GATE` | claims 门禁灰度：默认 `advisory`（只告警），`enforce` = 显式开启拒绝，非法值回落默认 |
| `MW_TARGET_GAME` / `MW_TARGET_ENGINE` | 双工作区临时覆盖 |
| `MW_PY` | 扩展找不到 `mw.py` 时手动指定路径 |
| `MW_IMPL_GATE_ROOT` | 门禁项目根覆盖（测试钩子，默认 cwd） |
| `MW_RAG_SERVERS_FILE` | 机器级 RAG 配置的硬覆盖路径（设定但缺失 = 机器层为空，**不回落到 HOME**，用于测试隔离） |
| `MW_AUTOPILOT_FILE` | 机器级 autopilot 默认配置的硬覆盖路径（设定但缺失 = 机器层为空，**不回落到其它位置**，用于测试隔离） |
| `MW_AUTOPILOT_HOME` | 机器级 autopilot 默认配置的 HOME 覆盖（其后依次尝试 `HOME`、`USERPROFILE`） |
| `MW_RAG_SERVERS_HOME` | 机器级 RAG 配置的 HOME 覆盖（其后依次尝试 `HOME`、`USERPROFILE`） |
| `MW_RAG_PYTHON` | `skill` 形态 RAG 的解释器覆盖（缺省 Windows `python` / 其它 `python3`） |

## RAG 接入（可配置）

RAG 是**可选**能力：只有项目显式启用时才注册工具、才往 task.md 注入块；未启用项目零影响
（工具不注册、不写任何文件、不发探活请求）。完整的逐字段配置手册（四类可直接复制粘贴的示例、命令参考、
退出码、失败 signature 与排查）：[`docs/rag-config-guide.md`](docs/rag-config-guide.md)。

### 两层配置与逐字段合并

| 层 | 路径 | 用途 |
|----|------|------|
| 机器级 | `~/.agents/rag-servers.yml` | 本机所有 RAG 服务的连接信息 |
| 项目级 | `<control>/.mw/rag-servers.yml` | 项目覆盖（同名 server 逐字段覆盖机器级） |

两层文件形态都是 `{servers: {<name>: {...}}}`（只有 `servers` 是合法顶层键）。合并是**逐字段**的：
同名 server 的项目级字段覆盖机器级，`null` 删除该字段，数组（`sources`）整体替换；每个字段的来源
记在 `origin` 里（`rag list --json` 可查）。`target.yml` 的 `rag:` 段决定启用集与角色/阶段要求：

```yaml
rag:
  enabled: [overcode]              # 启用集（空或缺省 = 全关）
  default_server: overcode
  roles:
    coding: { server: overcode, require: false, rewrite: true }
    review: { server: overcode, source: docs, require: true }
  phases:
    design: { server: overcode, require: true }   # required = role.require OR phase.require
  budgets:
    time_budget_s: 900
```

`required = role.require OR phase.require`（并集，无例外）。`phase` 取**派发时** key 的阶段，由派发器
写进 task.md 的 `phase:` 头（阶段未知或 `_scratch` 不写该行；`target.yml` 的 `phases:` 键必须与
`pm-state.md` 的阶段值同大小写）。"必需"的判定标准是**产物里有可核对的引用**（`citation` + 本地路径
存在），不是"调用过工具"。

服务形态 `transport`：`mcp`（streamable-http，默认）/ `skill`（本地 CLI）/ `both`（mcp 为主，**连接层**
失败且只读工具时才回落 CLI；`rag_feedback`、`rag_chat`、超时永不自动回落）。凭证只以 `token_env` 名
出现在配置里，值由 `mw serve` 进程环境注入（task.md / trace / evidence 里不会出现值）。

### 命令

`--project <dir>` 是四个子命令的共同必填参数（argparse `required=True`）。

```bash
python mw.py rag list  --project <dir> [--json]                             # 合并后的 server 表与逐字段来源
python mw.py rag probe --project <dir> [--json]                             # 探活（诊断；不可达仍退 0）
python mw.py rag audit --project <dir> [--key <KEY>] [--json] [--out FILE]  # 只读审计：rag_call / 引用 / required-but-unused（无 --out 只写 stdout）
python mw.py rag sync  --project <dir>                                      # 把 skill 形态的说明文件同步到 .pi/skills
```

退出码（以 `mw.py` 实现为准）：

| 命令 | 退出码 |
|---|---|
| `list` / `probe` | 0 = 成功；1 = 配置错误（`probe` 不因服务不可达而失败） |
| `sync` | 0 = 成功；1 = 配置错误或框架 skill 源文件缺失 |
| `audit` | 0 = 无 `missing` / `unverified` / `required_missing`；1 = 有任一；2 = 用法或配置错误 |

### 工具面

启用后 worker 多出 6 个工具：`rag_search`、`rag_symbol`、`rag_graph`、`rag_impact`、`rag_sources`、
`rag_feedback`；`rag_chat` 只在 `rag-research` 类型下可见。引用格式为
`server:source:file_path:line` —— 左侧两段是 server/source，最右侧数字段是行号，中间全部内容
（允许含 `::`）都是 file_path。

逻辑名与参考服务（overcode）真实工具名的映射（AC-018）：

| 逻辑工具 | 线上工具名 | 说明 |
|---|---|---|
| `rag_search` | `rag_search` | 重写开关为真时改走 `rag_search_multi_rounds`（服务端多轮改写） |
| `rag_symbol` | `rag_symbol` | |
| `rag_graph` | `graph_query` | |
| `rag_impact` | `rag_impact` | |
| `rag_sources` | `list_sources` + `list_collections` | 两次调用合并为一个信封 |
| `rag_feedback` | `rag_feedback` | |

映射在适配器（`overcode-v1`）里以数据表维护：换服务族 = 加一个适配器，不改配置 schema。表中 6 行是
**六个基工具**的映射；`RAG_TOOL_MAP` 里还有第 7 条 `rag_chat`（`mcp: ["rag_chat"]`），它只在 `rag-research`
任务注册，故不列在此表。

`rag-rewrite-degraded` 与上面「开了多轮」是相反的语义：只有服务端响应信封的
`meta.rewrite_degraded === true`（服务端**改写失败**、降级为普通检索）时才追加该 trace 行
（`rag/adapter.ts` 的 meta 白名单 + `rag/tools.ts` 的判定）；它**不是**「启用了多轮改写」的标记。

### 降级与证据

五层降级：未启用 = 工具不可见；探活失败 = 注册但标注 `[unreachable at session start]`；运行时失败 =
熔断（连续 3 次连接/超时/协议错误，能力错误不计）；必需但服务不可用 = 告警；必需但没用 = 告警。
worker trace 里会出现 `rag_call`（含 `mcp_tool` 真实线上名）、`rag_fallback`、`rag-required-missing`、
`rag-rewrite-degraded` 等行；`mw rag audit` 只读地对这些行做独立判定。

## 决策服务（mw decide）

决策服务是**可选**的旁路能力（goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」）：在框架需要
判断的时刻（首个决策点 **DP-1 派发前分诊**）调用一次结构化决策（`state` + 类型化 `questions` → 类型化
`answers` + 置信度），产出**建议**，不改写派发的类型/角色/模型，也不改 watchdog/checkpoint 策略。
未配置 `.mw/decide.json` 的项目零影响：不发网络调用、不产生新进程、doctor 不出现 `triage:` 行。

### 配置（默认关闭）

项目级配置 `<control>/.mw/decide.json`。文件缺失 = 决策整体 disabled；文件损坏 = disabled + 错误串给
doctor 展示（fail-soft，不影响任何既有流程）。

```json
{
  "enabled": true,
  "transport": "timi-decisions",
  "model": "jev-latest",
  "timeout_s": 20
}
```

| 键 | 默认 | 说明 |
|----|------|------|
| `enabled` | `false` | 总开关；未写该键或文件不存在 = 关闭（`mw decide ask` 例外，见下） |
| `transport` | `timi-decisions` | **唯一传输**：`POST {base_url}/v1/decisions`。旧的 `llm-transitional` / `llmproxy-anthropic` / `direct-systemone` 已删除，显式写旧名会得到 `reason=entry-unavailable`（没有备选通道、没有回退） |
| `model` | `jev-latest` | Decisions 类模型（平台模型库为准）；非 decisions 类模型由服务端报错并原样回显，客户端不改写、不换模型 |
| `timeout_s` / `max_retries` / `max_questions` / `max_state_bytes` / `max_tokens` / `backoff_base_s` | `20` / `2` / `8` / `16384` / `1024` / `2.0` | 预算与退避，全部可配；超预算立即 fail-soft 返回 |
| `points.dp1.enabled` | 未写 = 跟随总开关 | 单个决策点开关 |
| `points.dp1.alert_on_disagreement` | `true` | 建议类型与派发类型不一致时是否唤醒 PM 一次（争议升级） |
| `triage_notify_on_unavailable` | `false` | 决策不可用时是否投一条 notice（默认静默，结构上不可能被误读为「已生效」） |

传输旋钮经配置透传：`base_url`（默认 `http://api.timiai.woa.com/ai_api_manage/llmproxy`）、`api_key`
（**通常不写**：解析顺序 = 本文件 `api_key` → 环境变量 `TIMI_API_KEY` → **pi 自己的 `~/.pi/agent/auth.json`
的 `timi.key`**，即 pi 登录过就直接复用，无需另配；`mw decide show --json` 回显为 `<redacted>`，
任何日志/证据都不落明文 key）。

### 命令

`--project <dir>` 是 `run`/`probe`/`show`/`set` 的共同必填参数（`ask`/`report`/`dp` 默认 `.`）；配置写入走
P-003 原子写（temp + `os.replace`，`O_CREAT|O_EXCL` 锁）。`decide run` 的 `state` 只走 stdin /
`--request-file`，不接受命令行参数；人要现场提问用 `decide ask`。

```bash
python mw.py decide ask   (--state <text|@path> | --state-file <path>) [--noul QID=TEXT ...] [--choice QID=K[:说明][,K2[:说明2]] ...] [--score QID=档1,档2 ...] [--model MODEL] [--json] [--project DIR]
python mw.py decide book  new <dp-id> [--out FILE] [--json]                           # 按注册表生成决策本骨架（只读配置，不联网）
python mw.py decide book  check <file> [--json] [--project DIR]                        # 七类失败码验收（只报告不修，失败 exit 2）
python mw.py decide ask   --book <file> [...]                                          # 先验后发：check 不过就零 HTTP
python mw.py decide run   --project <dir> --book <file> [--json]                     # 同上；dp 由 book.decision_point 指定
python mw.py decide run   --project <dir> --dp dp1 [--request-file FILE] [--json]  # 请求 JSON（state + questions）走 stdin 或文件
python mw.py decide probe --project <dir> [--json]                                 # 传输诊断（FIX-L 后只剩单行 /v1/decisions）
python mw.py decide show  --project <dir> [--json]                                 # 生效配置 + 最近一条证据行
python mw.py decide set   --project <dir> [--json] KEY=VALUE ...                   # 原子写配置（未知键/非法值拒绝，exit 2）
```

#### `mw decide ask`（人直接问 timi/jev-latest）

`--state` 是待评估内容（文本，或以 `@` 开头表示从该 UTF-8 文件读）；`--noul` / `--choice` / `--score`
可重复，至少给一个，否则 exit 2 并打印用法摘要。`--choice` 的说明可省略（`billing` →
`criteria == {"billing": null}`），键为 `[A-Za-z0-9_-]+`，重复键 → exit 2；`--score` 按低→高档位写
2..10 个，越界 → exit 2。`--noul` 可用 `--noul-criteria 'QID=true:说明;false:说明'` 补判据（可选，缺省不发
`criteria` 键）。模型默认 `jev-latest`，`--model` 只覆盖模型名，未知值不拦截（交给服务端报错并原样回显）。

```bash
python mw.py decide ask --project . \
  --state '求助！我的提现已经失败3天了。' \
  --noul urgent=这段话是否传达了紧急性？ \
  --noul-criteria 'urgent=true:明确有时效性;false:未表达紧急性' \
  --choice dept=billing:支付/退款相关,technical:缺陷/故障相关 \
  --score effort=平静,不满,非常愤怒
```

```text
jev-latest · 3 questions · 1186 ms
dept      [choice] billing      confidence 0.98   probs: billing 0.99, technical 0.01
urgent    [noul]   0.87         (probability of "yes")
effort    [score]  1.05         confidence 0.92   legend: 0=平静, 1=不满, 2=非常愤怒
```

- `--json`：一条机器可读对象 `{model, usage, latency_ms, answers}`，不夹杂人类文案。`answers` 是客户端
  契约形态（`choice`/`score` 额外带 `probabilities`，`score` 带 `legend`）；`usage` 目前恒为 `null`，
  因为冻结的客户端响应不携带 token 用量。
- **失败原样上抛**：`available=false`（未配置 / 无凭据 / 超时 / 429 / 5xx / 响应不可解析 / 超预算）时
  stderr 打 `[mw decide ask] <reason>: <detail>`、exit 2，stdout 不输出任何答案；**不编造答案、不重试其它
  模型**。成功时照常落证据行，`dp=dp-human-ask`。
- 项目没有 `.mw/decide.json` 时，`ask` 视为开启（人主动敲命令就是 opt-in）；显式 `enabled=false` 或配置
  文件损坏仍然关闭。其余路径（`run`/`dp`）依旧由配置表授权，不受此例外影响。

请求形状（`type` 覆盖 `choice` / `score` / `noul` / `box`；`choice` 必须声明 `choices` 或
`dynamic_choices`，`score` 必须给整数 `min`/`max`，`noul` 无必需字段；`box` 在发请求前按已知类型被拒
（`box-requires-image`））：

```json
{"state": "<一句派发场景描述>",
 "questions": {"triage_type": {"type": "choice", "choices": ["coding", "research", "review"]},
               "triage_risk": {"type": "choice", "choices": ["low", "mid", "high"]}}}
```

`answers` 每项含 `value` + `confidence`；响应另附 `available/transport/model/confidence_source/attempts/latency_ms/reason`。

#### `mw decide book`（写决策本 + 先验后发）

`ask_decision` 判 `input-incomplete`、该 dp 尚未接线，或 PM 需要一次可复核的离线决策时，写一份**决策本**
而不是在对话里描述。决策本是 `decide` 接口的**输入文件**：`{schema_version: 2, decision_point, state,
context?, notes}`；键集合与顺序**由配置决定**（`decide_registry.json` 的 `required_state_fields` + 该 dp 的
`contextSlots`），不是由人猜。位置：`.agenticdoc/<key>/evidence/books/<dp-id>-<slug>.json`
（PM 用 `.agenticdoc/_autopilot/books/`）。

```bash
python mw.py decide book new dp3-worker-clarify --out .agenticdoc/<key>/evidence/books/dp3.json
python mw.py decide book check .agenticdoc/<key>/evidence/books/dp3.json --json
python mw.py decide run --project . --book .agenticdoc/<key>/evidence/books/dp3.json
python mw.py decide ask --book .agenticdoc/<key>/evidence/books/dp3.json --noul urgent=是否紧急
```

四步：

1. `book new <dp-id>` 生成骨架（默认**只打印**，加 `--out FILE` 才写文件）：`state` 的键与顺序 ==
   `required_state_fields`，值一律是类型占位符（`"<string: …>"` / `-1` / `-1.0` / `false` / `[]` / `{}`）；
   `schema_version` / `decision_point` / `questions_version` 预填注册表真值；`notes.evidence` 为每个必填
   字段生成同名待填项；`context` 只留该 dp 允许的槽位。
2. 按每个字段的 `description` 填值（`book new` 已把描述写进占位符）。数值/枚举必须来自真实证据。
3. `notes.evidence` 每条给 `path:line`（文件必须在仓库内、行号 ≤ 行数）或命令原文
   （`cmd: rg -n …`、裸 `rg …`、`git …`）。三个身份字段的证据可以写 `cmd: mw decide book new <dp-id>`。
   `context` 的槽位值就是内容（文本槽位是字符串，数组槽位是数组，形状同 `decision_context`），
   已用槽位的来源写成 `notes.evidence["context.<slot>"] = "path:line"`。
4. `book check <file>` 通过后再用 `--book` 发送；`ask/run --book` 会先跑同一套检查，**任一失败即拒绝
   发送（零 HTTP）**，失败表打 stderr、exit 2。

**封闭键集合**（缺与多都失败）：`state` 里除该 dp 的 `required_state_fields` 与三个通用身份字段
（`schema_version` / `decision_point` / `questions_version`）外不得有其它键。七个失败码：

| 失败码 | 判据 |
| --- | --- |
| `book-schema` | JSON 不可解析、顶层键越界（只允许 `schema_version`/`decision_point`/`state`/`context`/`notes`）、`schema_version != 2`、dp 不在注册表 |
| `book-state` | 缺必填、类型不符（`string|integer|number|boolean|array|object`）、**多出注册表没有的键**、`questions_version` 与注册表漂移 |
| `book-placeholder` | 占位符未替换、空串、负数、空数组/对象、`TBD`/`TODO`/`xxx` |
| `book-context` | 未知槽位（不属于该 dp）、已用槽位缺 `source`（`notes.evidence["context.<slot>"]`）、单槽超长、`context` 总字节 > 4000 |
| `book-evidence` | 必填字段缺证据、`path:line` 文件不存在/行号越界/路径在仓库外 |
| `book-budget` | `state + 最长题面` > 32k tokens 或整请求 > 64k（复用 `_estimate_tokens` 与 `.mw/decide.json` 的闸） |
| `book-secret` | 命中 `decision._redact` 的凭据检测面 |

`book check` 只报告不修（退出码 0 = 全过 / 2 = 有失败），`--json` 输出
`{path, sha256, ok, books[], issues[]}`（一个文件可装多本示例：`{"books": {dp-id: book}}`）。
决策本**只写输入、不写预期答案**：没有 `answers`/`expected_*` 这类键的位置，`questions` 也不允许覆盖（题面归注册表）。

`--book` 成功发送后，档案侧落两处：决策行照旧进 `.agenticdoc/_autopilot/decisions.jsonl`（字段矩阵封闭），
book 的输入元数据（`book_path` + `file_sha256` + `notes.evidence` + `state_digest`）落
`.agenticdoc/_autopilot/book-receipts.jsonl`，`decide run --json` 的回执顶层多一个 `book` 对象。

### fail-soft 与退出码

决策服务**不可用绝不阻断**派发、执行、收尾：

- 成功与 `available=false`（未配置 / 入口未暴露 / 超时 / 429 / 5xx / 连接不可达 / 响应不可解析 / 超预算）
  **都 exit 0**，失败以机器可读 `reason` 表达（`disabled` / `entry-unavailable` / `timeout` / `rate-limited` /
  `upstream-error` / `bad-response` / `budget-exhausted` / `unsupported-question-type`）。
- 只有**参数非法**（缺字段、未知问题类型、超上限）exit 2；配置写入失败也是 2。
- 客户端不向编排抛异常；每次调用向 `<project>/.agenticdoc/_autopilot/triage-decisions.jsonl` best-effort
  追加一行 JSON 证据（write 失败不破坏调用方主流程）。

### 置信度硬规则

`confidence_source` 区分来源：`api`（上游直出；`timi-decisions` 恒为它）与 `model-self-report`（旧过渡路线
由模型自报，**未经校准**）。**`confidence_source != "api"` 时 `confidence` 不得用于任何门控/阈值自动决策**，只能作为
弱排序信号；呈现文案必须带来源标识（实测过渡后端对平凡事实自报 1.0，典型过自信）。

### 覆盖面与数据流

- **覆盖面（本波 2/15）**：DP-1 当前只挂在 **PM 发起派发** 的路径上（`planDispatchFrontmatter`，`dispatch_worker` 与
  `/worker` 两个入口共用）；conductor 的 **13 个自动派发点尚未接入**，那些路径的行为与未启用决策服务完全一致
  （后续波次再挂 Python 侧 `dispatch()`）。
- **数据流**：开启后，每次派发会把派发场景描述（`state`，派发描述全文加类型/阶段等上下文，上游已按
  `max_state_bytes` 截断）经内网 decisions 接口（`POST {base_url}/v1/decisions`）发往配置的 `jev-latest`；
  与既有 pi worker 自身的模型流量走同一通道。`mw decide ask` 使用的是同一条通道（人自己写 `state`）。
  **不要在派发描述里放凭据或敏感原文**；敏感场景请保持 `enabled=false`。
- 结构化证据行落在 `<project>/.agenticdoc/_autopilot/triage-decisions.jsonl`（唯一写者是 Python 决策客户端，
  TS 侧只读）。

### 建议被谁消费（执行 → 结果）

建议产出后**只作旁路提示**，四条消费路径：

| 路径 | 何时 | 形态 |
| --- | --- | --- |
| 派发回执 | `available=true` | 回执末尾追加一行 `[triage] 旁路建议，未据此更改派发：triage_type=…（conf=…）, triage_risk=…`（零额外 turn） |
| ledger 行 | 任意结果 | `kind=triage-suggestion`（可用）/ `triage-unavailable`（不可用且 `triage_notify_on_unavailable=true`） |
| PM 唤醒 | 仅「建议类型 ≠ 派发类型」且 `alert_on_disagreement != false` | 一条告警消息，文案明写 `the dispatch type/role/model were NOT changed` |
| 证据文件 | 每次调用 | `.agenticdoc/_autopilot/triage-decisions.jsonl` 一行 11 字段 JSON |

四个象限的最终状态：一致 → 静默记录；**争议 → 回执 + 一条 PM 告警，派发不变（是否改判由 PM/人决定）**；
不可用 → 默认全静默（可配 ledger 行）；未启用 → 零输出（回执逐字节不变，TS 侧有真断言）。

完整链路（输入→输出→执行→结果、四象限、测试矩阵、凭据链）：
`.agenticdoc/mw-jev-provider-integration/docs/jev-integration-flow-and-usage.md`。

### doctor 行

`mw doctor` 增加决策服务行（**信息行**，不进 `_doctor_issues`、不翻转 healthy；未配置项目输出逐字不变）：

```text
triage: enabled timi-decisions last_suggestion=<seq|none> last_unavailable=<reason|none>
triage: disabled
triage: ERROR — <配置错误串>
```

`mw doctor --json` 同步给出 `decide` section（`exists/enabled/transport/model/last_seq/last_suggestion/last_unavailable`）。

### 决策替换（dp 配置表）

决策服务之上是**决策替换**：框架里 24 个「会等人」的决策点（dp）各在注册表登记一次，由一个项目级
授权表 `.mw/decide-points.json` 决定哪些点由决策服务直接给答案/执行、哪些照旧上抛人。**配置表是唯一
授权权威**（P2 默认开、P1/P0 默认关），人用指令或直接改文件开/关单个 dp，**下一次决策即生效**——
无需重启；关掉即回原路径（零 spawn、关闭态字节同构）。失效安全：未开启 / 不可用 / 低置信 / 输入缺失
一律上抛人，**没有默认动作**。

| 面 | 形态 |
| --- | --- |
| 配置表 | `.mw/decide-points.json`（只管授权；与管传输的 `.mw/decide.json` 分工，互不写入；文件缺失 = 注册表默认） |
| 指令 | `mw decide dp list/show/on/off/set/refresh/check/apply/export/verify`（`export [--json|--write]` 把注册表导出成 `decide_registry.json`，每个 point 自带 `wired`/`trigger`/`adopted_at`/`wiring_note` 且 `required_state_fields` 带 `{name,type,description}`，重生成保留手写 wiring；`verify [--json|--live|--dp ID]` 离线把每个 dp 的最小合法 state 跑过 `decide` + 线上 body 形状检查，`--live` 打真 jev-latest，任一 dp 不可用 exit 1）（`on <P0>` 必须带 `--i-understand-p0`，否则 exit 2 且不写文件） |
| 档案 | `.agenticdoc/_autopilot/decisions.jsonl`：`decide`/`override`/`settle`/`authority-change` 四类行 + `prev_sha` 哈希链，单写者 append-only，`decision_id` 幂等 |
| 报告 | `mw decide report --key <key> --write`：phase 末由 `advance_phase` 自动生成 `evidence/review/decision-review-<phase>-*.md`；`N<5` 强制「数据不足，不结论」，机器只给 `suggest:` 不给动作 |
| 收尾签收 | `mw decide sign --project .agenticdoc/<key>` 触发签收：结论由决策模型（`dp25-signoff-conclusion`）给出，命令生成 `<key>/evidence/review/sign-final.md`（机器行 `counted_rows`/`rows_sha256` 由命令算）+ 一条 `authority-change` 档案行。done 门禁无条件校验签收内容；`.mw/decide.json` 的 `signoff: disable` 或该 key 档案无 `kind=decide` 行 → 无需签收（见下） |

#### per-dp 策略旋钮（`min_confidence` / `max_questions` / `timeout_s`）

`.mw/decide-points.json` 的每行除 `tier/enabled/mode/note` 外，还可覆盖三个策略项（spec §14 AC-016）：

| 键 | 类型 | 合法域 | 缺省（内置常量即当前值） |
| --- | --- | --- | --- |
| `min_confidence` | number | `0 <= x <= 1` | dp1/dp2/dp3 = 0.7 |
| `max_questions` | integer | `1 <= n <= 8` | `.mw/decide.json` 的 `max_questions`（8） |
| `timeout_s` | integer | `1 <= n <= 300` | `.mw/decide.json` 的 `timeout_s`（20） |

- **生效值** = per-dp 行 > `.mw/decide.json` 的同名键 > 内置常量。行里只写一个键时，另外两个各自落到下一层。
- **非法值 fail-soft**：该值被丢弃（不 disable、不抛异常），回落到下一层，并在 `dp check` 记一条 `L8` warning。
- **看生效值**：`mw decide dp show <dp>` / `mw decide dp check` 打印每行的**生效值**与决定它的层
  （`row` / `decide.json` / `builtin`），原始值非法时同屏有 `L8` 回落原因；`dp show --json`、
  `dp check --json`、`mw decide show --json` 的 `policy` 字段带同一份数据（`mw decide dp check` 的
  非 `--json` 输出每个注册 dp 一行 `policy <dp>: min_confidence=0.7(builtin) ...`）。
- **档案回显**：`kind=decide` 档案行新增 `policy` 字段（三个生效值），事后可复原「为什么它被 escalate」。
- **TS 侧**：`agent-team-loop/shared/decide-policy.ts::resolveDecidePolicy(dpId, projectDir)`，与
  `decision_points.resolve_policy` 同一解析顺序（同一份配置 → 同一生效值，由 parity 测试锁死）。
  dp3 的三个阈值随 `min_confidence` 平移（`min_match=+0.05`、`answerable=-0.2`，缺省仍是 0.75/0.7/0.5）；
  dp2 用 `min_confidence` 做 `acted` 置信门、`timeout_s` 做子进程预算。
- 这三键目前是**只读表内容**：`mw decide dp set` 仍只接受 `tier/enabled/mode/note`（未知键照旧 exit 2），
  需要时直接编辑 `.mw/decide-points.json`（下一次决策即生效）。

#### `mw decide sign`（签收 = 决策摘要 + 机器行，结论由决策模型给）

签收不再由人给结论：命令先算出本 key 的决策事实，再由 `dp25-signoff-conclusion` 决定
`continue|narrow|revoke`。命令没有结论参数。

```bash
python mw.py decide sign --project .agenticdoc/<key>                        # 决策模型签收（或无需签收）
python mw.py decide sign --project .agenticdoc/<key> --dry-run --json       # 只读预判：三个 verdict，零写入
python mw.py decide sign --project .agenticdoc/<key> --reason 'closing EXECUTE'
python mw.py decide sign --project .agenticdoc/<key> --disable            # 显式关掉签收（写 .mw/decide.json）
```

- 摘要含：`counted_rows`（本 key 的 `kind=decide` 行数）、`n_available` / `n_acted` / `n_escalated`、
  `engines`（`transport/model/confidence_source` 三元组计数）、按 dp 的计数、`escalated_reason` 分布、
  已开 P0、`rows_sha256`（被计数行的规范 JSON 哈希，档案一改就变），以及三个结论各自的 `{ok, problems}`。
- 结论只来自 `dp25-signoff-conclusion`（jev）：`continue` 要求 `N>=1`、档案哈希链完整、且**每一行**都是
  真 jev（`timi-decisions` / `jev-latest` / `api`）；`narrow` / `revoke` 是减权，只要求链完整（`N=0` 也允许）。
  `N=0` 还要 `continue` 时必须显式 `--allow-empty`，文件里落 `allow_empty: true` 与 `counted_rows: 0`。
- **决策模型不可用就不写文件**（传输关 / dp 关 / 低置信 / 超时 / 不可达）：exit 0，打印
  `decision model unavailable (<reason>); sign-off not required`。done 门禁此后仍报 MISSING（签收文件不存在），
  重跑一次即可，不需要人。
- 校验不过 → stderr 逐条原因、exit 2、**不写文件**。写入成功后追加一条 `kind=authority-change`
  档案行（`by=signoff:<conclusion>`、`change=signoff`、`conclusion=<x>`；`by` 沿用档案层冻结词表），
  文件落 `signed_via: auto-decide`（写面词表只有这一个值）。
- 固定落 `<key>/evidence/review/sign-final.md`（父目录自动创建，`conclusion:` 列 0 单行），并写出
  `promote:` / `demote:` / `p0-open:` 三行，所以同一份文件仍可直接给 `mw decide dp apply` 消费。
- **零 `kind=decide` 行 → 无需签收**：done 门禁跳过（不要求 `sign-final.md`）。此情形下 `continue` 被
  `N=0` 拒（必须显式 `--allow-empty`），只有 `narrow` / `revoke` 能过（减权只需链完整）；
  `--dry-run --json` 可直接看到 `counted_rows: 0` 与三个 verdict。
- `--dry-run --json` 永不写入、也不调决策模型，输出
  `{"conclusion": null, "ok": null, "problems": [], "facts": {...}, "path": null, "verdicts": {"continue": {"ok": true, "problems": []}, "narrow": {...}, "revoke": {...}}}`；
  窗口与脚本用 `verdicts` 预判。其它 `--json` 输出 `{conclusion, ok, problems, facts, path, verdicts}`
  （失败时 `path=null`）。
- `mw decide sign` 不再按 agent 会话拒绝：结论由决策模型给，任何调用方都给不出（`mw decide dp apply`
  的会话守卫照旧，它是独立的授权变更动作）。

**pi 窗口入口：窗口只触发签收，不产生结论。** `/mw decide show` 与
`/mw decide sign [--allow-empty] [--key <k>]`。

```text
/mw decide show                                  # 只跑 preview（mw decide sign --dry-run --json），不写任何文件
/mw decide sign --key my-key                     # 写面：mw decide sign --key <k> --json
```

- `show` 渲染 `counted_rows/available/acted/escalated`、`engines:` 直方图、三个 verdict、
  `rows_sha256` 前 12 位与 `p0-open`；`--dry-run` preview 零写入、零决策模型调用。
- `sign` 只有一个写面：`mw decide sign --key <k> --json`。没有结论参数（调用方没有结论可给）、不弹确认框、
  不要求 `ctx.hasUI`（headless / `-p` / rpc 走同一条路径）；回显解析真实 `signed_via: auto-decide` 与
  `conclusion:`，不猜结论。`--reason` 是 CLI 面，窗口不转发；项目 `signoff: disable` 仍生效（只打印预览）。
- key 取 `--key` > 当前窗口 watch 的 key > usage 报错（不猜）。

**done 门禁的 `decision_signoff` 检查（无条件执行）**：适用性由检查函数判断——`.mw/decide.json` 的
`signoff: disable` 或该 key 档案没有一条 `kind=decide` 行 → 跳过（无需签收；档案读不出则 fail-loud）。
否则校验 ①`sign-final.md` 存在 ②`conclusion:` 可解析 ③`counted_rows:` / `rows_sha256:` 存在
④用 `decide_signoff.collect` 重算并比对 sha（签名后档案被追加/篡改即失败）⑤`continue` 再跑
`verdict()`（N>=1 + 全部真 jev + 链完整）。「文件存在 + `conclusion:` 行」已并入这一条规则：原先
`decision-scope.md` 开关与另外两条无条件签收规则已删除，`decision-scope.md` 不再被读取。

当前只有 **dp1（派发前分诊，`mode=auto` 时写 `decision:` 头行）/ dp2（checkpoint 只允许收窄）/ dp3
（worker 澄清自答）** 有真实调用点，其余 21 项仅注册（开启不改变任何行为）。完整说明（24 项一览与
档位、配置表 8 层降级与热生效、`mode` 语义、档案字段与读法、报告与签收流程、失败与回退阶梯）：
[`docs/decision-substitution.md`](../../docs/decision-substitution.md)。

### 派 decide_prepare worker 写决策本（`type: decide_prepare`）

**何时派**：某个 dp 的决策刚好能由「读配置 + 收证据 + 按注册表填本」得出时（今天 dp1/dp2/dp3 定义了
`required_state_fields`），把这件事整体交给一个 `decide_prepare` worker，PM 不自己推理字段内容。
（W10 起类型值叫 `decide_prepare`；旧的 `decision` 不再被识别，不留别名。）

**卡片怎么写**：`<key>/tasks/<stem>.md` 的派发段必须四条齐全（缺任一条派发即拒，零副作用）：

```markdown
## 派发参数

- dp: dp3-worker-clarify
- 证据来源: .mw/decide.json:3 + `mw decide book new dp3-worker-clarify`
- 分支后果: 误判会把需要澄清的任务直接执行
- allow-send: no
```

- `dp` 必须是定义了 `required_state_fields` 的 dp（否则拒绝并提示「先给该 dp 定义必填字段」）。
- `allow-send: no`（缺省即 no）：worker 只能跑 `mw decide book check`；`decide run|ask --book` 由 PM 发送。
- 想给这个角色单独指定模型：`.mw/dispatch.yml` 的 `models.decide_prepare`（或 `mw model set decide_prepare
  <prefix/model>`）；**不配则沿用 `models.coding`**（同一角色配置，`fallback_models` 也一样）。`dispatch_worker`
  的 `model` 覆盖仍优先（记 `model-reason`）。本仓库当前配的是 `decide_prepare: timi/gpt-6.1-sol`（只读、要准确）。
- 写入面：卡片不写 `## 写入允许面` 时，类型默认收窄为 `<key>/workers/<task_key>/evidence/books/**`；
  卡片自己声明更宽的面时**以卡片为准**，并在 task.md 记一行 `narrowed_by:` 说明（不静默放宽）。

**验收看什么**：

1. `python -m autopilot.dispatch check --card <card>` → exit 0（同一套标准；exit 2 会逐条列出
   `missing-item:*` / `dp-required-state-fields-missing:*` / `book-send-refused`）。
2. worker 的 `evidence/books/<dp>-<slug>.json` 过 `mw decide book check`（exit 0）。
3. task.md 的「决策本参数」段已把 dp / 证据来源 / 分支后果 / allow-send / book 路径 / `narrowed_by` 写全。
4. `allow-send: no` 的 run：trace.log 不应出现 `decide run/ask`；只有 `book check`。

## 待实现（Backlog）

- **直连路由泛化**：`launcher._build_env` 的 timi 直连特判泛化为「providers.json 中无 `port` 的路由 = 直连」，新 provider 照 timi 模式注册原生 provider + 无 port 路由条目即可用，无需 proxy。 已落地最小版（mw-provider-routing，zai-coding-cn 走第 5 个直连分支 + zai/ 前缀）；本项保留为完整泛化：pi_providers 数据驱动段取代全部硬编码分支（deepseek 键在 providers 段带 port 7004，朴素「无 port=直连」启发式对其不可行，见 .agenticdoc/mw-provider-routing/design.md D-001）。
- **proxy 定位收敛**：仅服务「外部 CLI + 协议翻译」场景（claude/deepseek CLI）。需要时将 `timi_proxy_cli` 的最小闭包（proxy.py / logging_utils.py / config.py / models.py / constants.py，约 40KB 纯标准库、零 pip 依赖）vendor 进 packages/multi-workers，消除对私有 editable 包的机器级依赖。

## 测试

```bash
cd packages/multi-workers
python -m pytest -q          # 430+ 通过；e2e 默认 deselect
```
