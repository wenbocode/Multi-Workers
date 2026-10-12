# runtime-cutover-runbook（T-16 / G1–G6 运行时切换 runbook）

> **本 runbook 由用户批准后由 PM 执行；本卡（T-16 / mwg-t16-docs-closure）不执行。**
> 本文件只写文档，不重建 dist、不跑 `npm run build` / `mw build`、不重启、不 kill 任何进程。

- key: `mw-gate-verdict-hardening`
- 目的：把本 key 的源码改动（G1 `l3-aborted` / G2 提醒+面板 / G3 `contract_guard` / G4 面板自证+重臂 / G5 队列完整性+launcher 有界 / G6 派发隔离+run.json）真正生效到运行时。
- 依赖理由（PM 决定，2026-10-10 19:10）：`npm run build` 属 AGENTS.md 需用户明确要求的动作；切换会让 pre-10:53 旧窗口与新产物共存（IN-3 复现条件）。
- 本文件取数时刻：**2026-10-10 19:13（本机时钟）**（所有 PID / mtime / 队列形态都标了取数时刻，执行前需重取）。

---

## 0. 运行时现状快照（2026-10-10 19:13 实测）

| 项 | 实测值 |
|---|---|
| 仓根 HEAD | `776b82d7fa3af2a36a5a46717be6d5feac8ba0a0` |
| 全局 bundle | `C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`，952453 B，mtime **2026-10-10 11:40:42** |
| 仓内 dist bundle | `H:\git\Multi-Workers\packages\coding-agent\dist\extensions\agent-team-loop.js` → **当前不存在**（`Test-Path` = False） |
| `serve` 主进程 | `mw.py serve` PID **14240**（2026-10-10 15:29:38 起；`.mw/mw.pid` 与 `.mw/serve.meta` 均 = 14240） |
| launcher 进程 | `launcher.py` PID **4756**（14240 的子进程，2026-10-10 15:29:38 起；`.mw/launcher-beat.4756` mtime 19:13:12 仍在心跳） |
| 队列 `.agenticdoc/_workers.parallel` | **270 行 / 全部 8 列 / 无 `# mw-queue:v2` 头 / unparsable=0**（取数时刻 19:13:13，文件 mtime 19:05:14） |

> 说明：PM 记录里全局 bundle 为「10-10 10:53:02 旧构建」，本次现场实测 mtime 是 **2026-10-10 11:40:42**。以现场实测为准；无论哪个时刻，都早于本 key 的源码改动完成时间，故仍是旧构建。**执行前请重取 mtime。**

### 0.1 9 个 pre-10:53 常驻 pi 窗口（必须重启，否则 IN-3 复现）

这些窗口的 in-memory 解析器是 pre-`b8bc115ff`，只认 7..8 列；新产物会写 9 列（带 `origin`），旧窗口会把 9 列行当不可解析 ⇒ 触发 IN-3（整表重写 + 250 行全量重派）。

取数命令（PowerShell，取数时刻 2026-10-10 19:13）：

```powershell
Get-CimInstance Win32_Process | Where-Object {
  $_.Name -eq 'node.exe' -and $_.CommandLine -like '*@earendil-works/pi-coding-agent*' -and
  $_.CreationDate -lt [datetime]'2026-10-10T10:53:00'
} | Select-Object ProcessId, ParentProcessId, CreationDate | Sort-Object CreationDate
```

取数时刻实测 PID（9 个，均为 `node.exe ... @earendil-works/pi-coding-agent/dist/cli.js`）：

| # | PID | 启动时刻 |
|---|---|---|
| 1 | 80740 | 2026-09-10 23:02:08 |
| 2 | 25704 | 2026-09-19 16:16:34 |
| 3 | 50032 | 2026-09-23 17:06:17 |
| 4 | 95236 | 2026-09-23 17:14:49 |
| 5 | 30656 | 2026-09-24 15:31:24 |
| 6 | 10604 | 2026-09-24 15:47:32 |
| 7 | 18200 | 2026-09-24 19:21:04 |
| 8 | 117296 | 2026-10-09 15:58:48 |
| 9 | 136660 | 2026-10-09 20:40:14 |

交叉核对来源：`.agenticdoc/mw-gate-verdict-hardening/pm-state.md` D-044（同 9 个 PID）；本 runbook 的 `Get-Process node` / `Get-CimInstance Win32_Process` 现场取数与其逐字一致。

> `trace.log` 交叉核对（可选）：对每个 PID 在其归属 `workers/*/trace.log` 里核对 `[START] pid=<PID>` 与 `[MODEL]` 行，确认该 PID 仍是该 worker 的常驻窗口。

---

## 1. 前置（执行前逐条确认）

### 1.1 工作树快照（记录，不改）

```powershell
cd H:\git\Multi-Workers
git rev-parse HEAD
git status --porcelain | Out-File -Encoding utf8 .agenticdoc\mw-gate-verdict-hardening\evidence\runs\cutover-git-status-$(Get-Date -Format yyyyMMdd-HHmmss).txt
git status --porcelain
```

- 若 `M packages/coding-agent/src/**` 中有**不属于本 key**的改动在飞，先与对应会话确认或等其落盘——`mw build --install --allow-dirty` 会把这些未提交源码一起编进产物。
- 本 key 预期写面（执行时唯一应有本 key 的 `M`）：`packages/coding-agent/src/extensions/agent-team-loop/**`、`packages/multi-workers/{autopilot/*,launcher.py,mw.py,mw_common.py}`，以及三个文档（两 CHANGELOG + multi-workers README）。

### 1.2 队列归一（必须是全 8 列，unparsable=0）

```powershell
cd H:\git\Multi-Workers
python -X utf8 -c "import collections,pathlib; p=pathlib.Path('.agenticdoc/_workers.parallel'); L=p.read_text(encoding='utf-8').splitlines(); import datetime; print('sampled_at',datetime.datetime.now()); print('rows',sum(1 for l in L if l.strip()),'cols',dict(collections.Counter(len(l.split('|')) for l in L if l.strip())))"
```

若不是「全 8 列 / unparsable=0」，用 PM 提供的归一脚本（v2：持 `.mw/workers.lock`、内存构建、一次 `_write_workers_file`、5 次重试）**从仓根**执行：

```powershell
cd H:\git\Multi-Workers
python -X utf8 .agenticdoc\mw-gate-verdict-hardening\evidence\scripts\t23-normalize-whole-queue.py
```

期望末行：`after : rows=<N> cols={8: <N>}`、`parser view: rows=<N> unparsable=0 ...`。该脚本拒绝任何第 9 列不是 `manual` 的行。

### 1.3 备份全局 bundle（回滚用，见 §5）

```powershell
$stamp = Get-Date -Format yyyyMMdd-HHmmss
New-Item -ItemType Directory -Force -Path H:\git\Multi-Workers\.tmp\cutover-backup-$stamp | Out-Null
Copy-Item "$env:USERPROFILE\.pi\agent\extensions\agent-team-loop.js" "H:\git\Multi-Workers\.tmp\cutover-backup-$stamp\agent-team-loop.js" -Force
Copy-Item "$env:USERPROFILE\.pi\agent\extensions\.mw-py-path" "H:\git\Multi-Workers\.tmp\cutover-backup-$stamp\.mw-py-path" -Force
Get-Item "$env:USERPROFILE\.pi\agent\extensions\agent-team-loop.js" | Select-Object Length,LastWriteTime
```

---

## 2. 构建与安装

一条命令（**会跑仓根 `npm run build`**，即 `_deploy_bundle` 内的 `npm run build` on `packages/coding-agent`）：

```powershell
cd H:\git\Multi-Workers
python mw.py build --install --allow-dirty
```

它做的事（`mw.py::cmd_build` → `_build_bundle` → `_deploy_bundle`）：

1. 脏树门禁：`_BUILD_DIRTY_PATHS = ["packages/coding-agent/src"]`。当前该面有未提交改动，故**必须带 `--allow-dirty`**；否则报 `工作树有未提交改动，构建会把它编进 tracked 产物` 并退出 1。
2. esbuild 打包：`packages/coding-agent/src/extensions/agent-team-loop/index.ts` → `H:\git\Multi-Workers\packages\coding-agent\dist\extensions\agent-team-loop.js`，并做 jiti 自检（必须导出 function）。
3. `_rebuild_pi_dist()`：在 `H:\git\Multi-Workers\packages\coding-agent` 跑 `npm run build`（tsgo + copy-assets），刷新 `dist/**`。此步失败 ⇒ 不改全局 bundle（fail-closed）。
4. 安装全局 bundle：`H:\git\Multi-Workers\packages\coding-agent\dist\extensions\agent-team-loop.js` → **`C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`**（当前该处仍是 §0 的旧构建）。
5. 写 `C:\Users\wenbozhou\.pi\agent\extensions\.mw-py-path`，并幂等安装 `agentictask-update.ts`。

成功输出应包含：`built + self-check OK (...)`、`dist rebuilt`、`installed globally: C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`、`Restart open pi windows to load the new bundle and dist.`

失败处理：`_build_bundle` 失败 ⇒ 全局 bundle 不动；`npm run build` 失败 ⇒ 全局 bundle 不动。任一步失败都**不要**手工复制半成品，先修构建。

---

## 3. 重启 serve / launcher（以及 9 个旧窗口）

### 3.1 重启常驻服务（launcher + serve）

```powershell
cd H:\git\Multi-Workers
python mw.py status --project H:\git\Multi-Workers
python mw.py stop   --project H:\git\Multi-Workers
python mw.py start  --project H:\git\Multi-Workers
Start-Sleep -Seconds 5
python mw.py status --project H:\git\Multi-Workers
Get-Content H:\git\Multi-Workers\.mw\mw.pid
Get-Content H:\git\Multi-Workers\.mw\serve.meta
```

- `stop` 是优雅停止（写 stop-request，最多等 30s；不 force-kill）。`start` 重新拉起 `serve`（内含 launcher）。预期 `serve.meta` 的 `pid` 变成新 PID，`code_dir=H:\git\Multi-Workers\packages\multi-workers` 不变。
- 重启后 conductor 才加载新的 `autopilot/**.py`（Python 侧：conductor / launcher 是进程内旧代码，必须重启）。

### 3.2 重启 9 个 pre-10:53 pi 窗口

用 §0.1 重新取数的 PID 列表（**执行时重取，不要照抄上表**）：

```powershell
$old = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -eq 'node.exe' -and $_.CommandLine -like '*@earendil-works/pi-coding-agent*' -and
  $_.CreationDate -lt [datetime]'2026-10-10T10:53:00'
}
$old | Select-Object ProcessId, CreationDate, ParentProcessId | Format-Table
# 逐个“由用户/操作者在其终端里”重启（不要由本 runbook 批量 kill）：
# 对每个窗口：先让其收尾落盘（/pm-save 或等当前 turn 结束），再关闭该终端窗口后重新打开 pi。
```

纪律：
- **先收尾再关**：这些窗口可能持有 live worker / key。关闭前让每个窗口完成当前 turn，或确认其无在飞任务。
- **不要 kill**：本 runbook 不提供批量 kill；由用户在该窗口自己的终端里正常退出并重开。
- 重启完成判据：所有 pi 窗口的启动时间都晚于本次 `mw build --install` 完成时刻。

---

## 4. 切换后验证

### 4.1 `mw doctor --json` 关键字段

```powershell
cd H:\git\Multi-Workers
python mw.py doctor --json --project H:\git\Multi-Workers | Out-File -Encoding utf8 .agenticdoc\mw-gate-verdict-hardening\evidence\runs\after-cutover-doctor.json
python -X utf8 -c "import json; r=json.load(open('.agenticdoc/mw-gate-verdict-hardening/evidence/runs/after-cutover-doctor.json',encoding='utf-8')); q=r['queue']; print('rows_total',q['rows_total']); print('non_terminal_count',q['non_terminal_count']); print('unparsable_count',q['unparsable_count']); print('version',q['version']); print('run_ledger_conflict',len(q['run_ledger_conflict'])); print('issues',r['summary']['issues']); print('bundle',r['bundle'].get('global_bundle_mtime'),'stale',r['bundle'].get('stale'))"
```

JSON 路径与期望：

| 字段 | JSON 路径 | 期望 |
|---|---|---|
| 队列总行数 | `.queue.rows_total` | ≥ 切换前的行数，且行数不因切换被重写暴涨（IN-3 反向） |
| 非终态 | `.queue.non_terminal_count` | 与切换前同量级，不出现「250 行全量重派」形态 |
| 不可解析 | `.queue.unparsable_count` | **0**（`queue-rows-unparsable` 判据不告警） |
| 队列版本 | `.queue.version` | 读侧能报版本；新写队列行带 `# mw-queue:v2` 头（可用 `Get-Content .agenticdoc/_workers.parallel -TotalCount 1` 核对） |
| 突发形态 | `.queue` + doctor 文本行 | 不出现 `queue-burst-shape` 告警；不出现 `run-ledger-conflict` |
| 全局 bundle | `.bundle.global_bundle_mtime` / `.bundle.stale` | mtime 晚于构建时刻；`stale` 不为 true |
| 汇总 | `.summary.issues` | 无「本 key 引入」的新 issue；`summary.healthy` 与切换前基线同口径 |

### 4.2 一次派发确认运行身份（G6）

由 PM 在**已重启**的窗口里派发一个 `_scratch` 任务，然后：

```powershell
cd H:\git\Multi-Workers
# 1) 确认新 row 已带 origin（新写者只重写自己那一行，且行格局可识别）：
Get-Content .agenticdoc\_workers.parallel | Select-String '<新 task_key>'
# 2) 确认 worker 自写运行身份：
Get-ChildItem .agenticdoc\_scratch\workers\<新 task_key>\run.json | Select-Object FullName,LastWriteTime
Get-Content .agenticdoc\_scratch\workers\<新 task_key>\run.json
```

期望：
- 新 row 的 `origin` 为 `conductor`（不是空/`manual`）；队列**不再被翻成 9 列整表重写**——切换前后 `rows_total` 不出现 250+ 行暴涨。
- `<task_dir>/run.json` 由 worker 自写，含 `run_id` / `owner_key` / `pid` / 心跳（`heartbeat_at`）/ 终态；launcher 只补 `lost`，不代写终态。
- 不需要 restart 即可确认：派发隔离范围 = 本窗口 watch key + `_scratch`；越界 key 聚合为 `out-of-scope` 告警。

---

## 5. 回滚

### 5.1 退回旧全局 bundle

```powershell
$backup = Get-ChildItem H:\git\Multi-Workers\.tmp\cutover-backup-*\ -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item "$($backup.FullName)\agent-team-loop.js" "$env:USERPROFILE\.pi\agent\extensions\agent-team-loop.js" -Force
Copy-Item "$($backup.FullName)\.mw-py-path"         "$env:USERPROFILE\.pi\agent\extensions\.mw-py-path" -Force
Get-Item "$env:USERPROFILE\.pi\agent\extensions\agent-team-loop.js" | Select-Object Length,LastWriteTime
```

- 备份路径：`H:\git\Multi-Workers\.tmp\cutover-backup-<stamp>\agent-team-loop.js`（§1.3 生成）。
- 回滚只退扩展 bundle；`packages/coding-agent/dist/**` 的 tsgo 产物仍会晚于源码——若需要完全回到旧 dist，用 `git` 检出的旧提交重建或 `mw update-env --apply` 前先记录 dist 快照。
- 回滚后同样需要重启 `serve` 与所有 pi 窗口，旧 bundle 才真正生效。

### 5.2 队列回滚

若切换后队列被写成不可用形态，用同一归一脚本（幂等，拒绝非 `manual` 的第 9 列）恢复：

```powershell
cd H:\git\Multi-Workers
python -X utf8 .agenticdoc\mw-gate-verdict-hardening\evidence\scripts\t23-normalize-whole-queue.py
```

---

## 6. 执行边界（重申）

- **本 runbook 由用户批准后由 PM 执行；本卡不执行**：不跑 `npm run build` / `mw build` / `mw build --install`，不重启、不 kill、不改任何协调文件。
- 命令条数自检（本 runbook 中**带完整路径、可复制粘贴**的命令）：§0.1 取数 1 条 + §1.1 快照 4 条 + §1.2 检查 1 条 + 归一 1 条 + §1.3 备份 4 条 + §2 构建 1 条 + §3.1 服务 7 条 + §3.2 取数 1 条 + §4.1 验证 2 条 + §4.2 派发核对 4 条 + §5.1 回滚 3 条 + §5.2 队列 1 条 = **30 条**。

---

## 附：PM 现场复核更正（2026-10-10 19:20，实测）

上面 §0 的现状快照由 T-16 在 19:13 取数。PM 在 19:19 独立重取并更正三处：

| 项 | 原记录 | PM 实测（19:19） | 影响 |
|---|---|---|---|
| 全局 bundle mtime | 「10-10 10:53:02 旧构建」 | **2026-10-10 11:40:42**，952,453 B，sha256 `52187720D22D06DEE10FEE383981CD041FAD763BFB292B9B2BD7756D3A53FE0B` | 切换前**必须重取 mtime 与 sha256**；备份按 sha256 命名而不是 mtime |
| bundle 与 `b8bc115ff` 的关系 | 暗示「pre-fix 时代」 | 实测 bundle **含 `WORKER_COLS_MIN` / `WORKER_COLS_MAX`** ⇒ 它是 **post-`b8bc115ff`** 的构建（有 7..9 列容忍 + 9 列序列化）；且**不含本 key 任何标记**（`mw-queue:v2` / `run.json` / `blockedOnHuman` / `STALE PANEL` / `cross-key-read-only` / `contract-frozen` / `gate-reminder` / `l3-aborted` 命中均为 0） | 结论不变（**本 key 的改动都未生效**），但“旧构建”的**点**要说准：bundle 是“含 7..9 容忍、不含本 key 功能”的构建 |
| 仓内 dist bundle | `dist/extensions/agent-team-loop.js` 不存在 | 该**单文件**确实不存在；但 `packages/coding-agent/dist/extensions/agent-team-loop/` **是目录且存在**（`dist/extensions/` 下 `agent-team-loop/` 与 `llama/` 的 mtime 均为 2026-10-10 11:29:46，`dist/*.js` 为 11:40:46） | 切换产物 = `~/.pi/agent/extensions/agent-team-loop.js`（单文件安装副本）；`dist/**` 是构建中间物，别混为一谈 |

### §0.1「9 个 pre-10:53 窗口必须重启」——降级为**安全假设**（不是实测结论）

可实测的只有“窗口进程启动时刻”（表中 9 个 PID：80740 / 25704 / 50032 / 95236 / 30656 / 10604 / 18200 / 117296 / 136660）。
每个窗口加载的是**它启动时刻的安装副本**；安装副本在当前时刻 = 11:40:42，但**历史各时刻的安装副本内容不可考**（该文件无版本历史）。
因此：

- PID 117296（2026-10-09 15:58:48，早于 `b8bc115ff` 10-09 16:27）与 PID 136660（2026-10-09 20:40:14，晚于 `b8bc115ff` 但早于 10-10 11:40 的安装）**不能断言其解析器是否容忍 9 列**；
- **可执行的结论**：切换时**一律重启这 9 个窗口**（成本低、收益确定），而不是依据“它们一定是 pre-fix”来推断风险；
- 判定某窗口是否为风险源的正向证据只能是它自己的 `workers/*/trace.log`（该进程的读写轨迹）或它启动时安装副本的哈希 —— 两者都不可得时，按“全部重启”处理。

