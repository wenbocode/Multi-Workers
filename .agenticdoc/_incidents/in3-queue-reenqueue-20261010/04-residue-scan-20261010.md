# IN-3 残留排查（2026-10-10 11:45 本地）

- 排查人：`mw-gate-verdict-hardening` 窗口（PM 直执，**只读**：未 kill、未改文件）
- 目的：用户要求"再次排查事故 worker 还有没残留"
- 结论：**有残留，且仍在活动**：3 棵重跑 worker 进程树存活 ~55 分钟，**正在写仓库**（含共享产物 `packages/multi-workers/dist/extensions/agent-team-loop.js`，11:41:15）

---

## 1. 结论速览

| 检查项 | 结果 |
|---|---|
| 队列里还有 `running` 行？ | **否**（0 行 running；但仍存活 3 个 worker 进程 ⇒ **台账与进程不一致**） |
| 还有 IN-3 重跑 worker 进程存活？ | **是，3 棵**（PID 102332 / 160728 / 35528，启动于 10:50:08 / 10:50:10 / 10:54:21） |
| 这些 worker 的台账状态？ | **全是 `done`**（`updated_at = 2026-10-10T03:20:40Z` = 本地 11:20:40，由重启后 launcher 的收尾/收敛写入） |
| 它们还在写东西？ | **是**：`trace.log` 心跳 11:44:42/48/53；`msc-t14` 正在跑 `bash Copy-Item` / `git status`（11:44:59 / 11:45:04）、vitest+pytest 全套（11:43:29） |
| 影响到共享产物？ | **是**：`packages/multi-workers/dist/extensions/agent-team-loop.js` mtime **11:41:15**（该 worker 的任务就是 docs/dist regression）；`git status` 计数 101 → **110** |
| 其它 CLI（claude/codex）残留 worker？ | 否（仅 1 个 `codex-windows-sandbox-service.exe`，系统级，非任务） |
| `.mw` 残留？ | 陈旧的 `launcher-beat.<pid>` × 18（含被我 kill 的 96968）——**属正常设计**（pid 命名，不清理） |

---

## 2. 存活残留详表

| 进程 | 父进程 | 启动 | 归属 key / 任务 | 证据 |
|---|---|---|---|---|
| cmd 109572 → **node 102332**（+ conhost 123840 + powershell 128528） | 109572 ← **96968（已被 kill 的 launcher）** | 10:50:07 / 10:50:08 | `mw-autopilot-slot-capacity` / `msc-d4-evidence-provenance` | `trace.log` 心跳 11:44:42；`progress.md` 11:40:09 |
| cmd 65280 → **node 160728**（+ conhost 133924） | 同上 | 10:50:10 / 10:50:10 | `mw-autopilot-slot-capacity` / **`msc-t14-docs-dist-regression`** | `trace.log` `[TOOL] bash Copy-Item …` 11:44:59、`bash git status` 11:45:04；`vitest-suite.log`/`pytest-full2.log` 11:43:29；`output.md` 11:37:50 |
| cmd 24632 → **node 35528**（+ conhost 130144 + powershell 161928） | 同上 | 10:54:05 / 10:54:21 | `mw-target-partition` / `mwtp-s4-verify` | `trace.log` 心跳 11:44:53；`output.md` 11:43:31 |

命令行（三者同型，`H:\git\Multi-Workers` 真实路径）：

```
"node" "...\@earendil-works\pi-coding-agent\dist\cli.js" --provider timi --model deepseek-v4.1-flash \
  -p "Read your task file at H:\git\Multi-Workers\.agenticdoc\<key>\workers\<task>\task.md and execute it end-to-end …"
```

**关键点**：它们的父 launcher（96968）已被 kill，但 Windows 不会连带杀子进程 ⇒ **进程树被"孤儿化"后继续跑**。这也解释了 11:07 轻刹时为何要手工 kill 6 个；当时漏掉了这 3 个（它们不在我给出的 6 个 PID 名单里）。

---

## 3. 为什么这是危害（不是"无害僵尸"）

1. **它们在写共享产物**：`msc-t14-docs-dist-regression` 的任务范围就是 docs + dist，`dist/extensions/agent-team-loop.js` 11:41:15 被重写（这是**所有 pi 窗口加载的扩展 bundle**）。
2. **台账说 `done`、进程还在跑**：owner PM 见此行只会认为"已完成"，其后续写入**无人复核**（正是用户提的"产物自带状态"要解决的问题）。
3. **所属 key 已收口**：`mw-autopilot-slot-capacity` 早已 DONE/committed（`10446aefb`）⇒ 这次重跑是**纯浪费 + 净风险**，不可能带来价值。
4. **它还在跑全套测试**（vitest + pytest）：占 CPU/IO，且会在 `.agenticdoc/**` 生成大量新文件（`git status` 101 → 110）。
5. **可能再次触发派发扫描**：worker 收尾时该窗口的 `agent_settled` 若被观察到（其 bundle 为 10:53 后版本），仍会走一次 `dispatchNewTasks`。
6. **IN-1/IN-2 的教训**：上一个"无人看管的孤儿重跑 worker"（`mvr-t16`）执行了 `git worktree remove --force`，删掉 3,448 个 tracked 文件。

---

## 4. 建议动作（待授权，一条命令）

```powershell
# 3 棵残留 worker 树（含 cmd/conhost/powershell 子进程）
Stop-Process -Id 102332,160728,35528,109572,65280,24632,128528,161928 -Force
```

- 授权后我执行，并复查 `git status` 计数、`dist` mtime、队列是否仍 0 pending。
- **不建议保留**：它们对应的任务在台账里已是 `done`，且所属 key 已收口；不存在"删了会丢有效工作"的可能。
- 若担心 `msc-t14` 的产物（`output.md` 11:37:50）有价值：它已在磁盘上，kill 不会删除它；只是不再让这个进程继续覆写。

---

## 4.1 处置结果（2026-10-10 11:48，用户授权“立刻清掉，你来清”）

**已执行**（PM 直执）：

| PID | 对象 | 结果 |
|---|---|---|
| 102332 | node `msc-d4-evidence-provenance` | KILLED |
| 35528 | node `mwtp-s4-verify` | KILLED |
| 109572 / 24632 | cmd.exe 包裹进程 | KILLED（node 死后随之退出） |
| 128528 / 161928 | 其 powershell 子进程 | 随之退出 |
| 23868 / 62672 | 2026-08-28 的 `pi -p "Say exactly: ok"` 挂死探针（与本事故无关，一并清） | KILLED |
| 65280 | `msc-t14` 的 cmd 包裹（worker 已于 11:45:40 自行退出） | 自行退出 |

**验证证据**（11:49:13 复查，等了 50 s）：

- 三个 `trace.log` **冻结**在 11:45:40 / 11:47:42 / 11:47:53，无新写 ⇒ 确认停止写入；
- 本项目已无残留 worker 进程（唯一命中 `Read your task file` 的 node 进程是 PID 142604，属 **E2Feature/FM** 项目：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\gui-monitor-hitl-e2e\…`，**未动**）；
- `packages/multi-workers/dist/extensions/agent-team-loop.js` 停在 11:41:15；
- `git status` 计数停在 111，未继续增长；
- 队列 252 行 / **0 pending**，无需再派发。

**清理时未做的事**：未回滚 `msc-t14` 在 11:37–11:45 对 `dist/` 与其产物的覆写（属另一 key 的写面）；未改队列；未动任何 `.agenticdoc` 产品内容。

---

## 5. 其它（非本事故但有风险）

| 项 | 说明 | 建议 |
|---|---|---|
| PID 23868 / 62672（2026-08-28 启动） | `pi … -p "Say exactly: ok"` 的**一次性**探针进程，跑了 6 周未退出 ⇒ 典型 `-p` 挂死 | 可清（与本事故无关） |
| `.mw/launcher-beat.<pid>` × 18 | pid 命名，历史累积 | 无需处理（但可作为"历史 launcher 代数"线索） |
| PID 34196 / 153208（11:13 / 11:20 启动的 pi 窗口） | 长驻窗口（其他维护者） | **不要碰**；但它们若有 `dispatch_worker` 动作会各自触发扫描 |
| PID 142604（11:35:14，`E:\CLI_workspace\FeatureMigrator\...ap-gui-monitor-hitl-e2e-repair-a3-a4`） | **另一个项目**（E2Feature/FM）的 conductor 任务，属 E2 的 `mw serve` | 不属本项目，勿动 |

---

## 6. 排查方法（可复现）

```powershell
# 1) 本项目所有 worker 进程（任意 CLI）
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*Read your task file at H:\git\Multi-Workers*' } |
  ForEach-Object { "PID $($_.ProcessId) parent=$($_.ParentProcessId) start=$($_.CreationDate)" }

# 2) 队列 running 行
Get-Content .agenticdoc/_workers.parallel | Where-Object { ($_ -split '\|')[1].Trim() -eq 'running' }

# 3) 残留 worker 是否在活动（心跳/产物 mtime）
Get-Item .agenticdoc/*/workers/*/trace.log | Sort-Object LastWriteTime -Descending | Select-Object -First 10
```
