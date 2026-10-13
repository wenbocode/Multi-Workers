# 收口运行期动作清单 — mw-autopilot-gate-alarm-liveness（2026-10-13）

- Key：`mw-autopilot-gate-alarm-liveness`｜收口卡：T-19
- 目的：给出**本 key 各改动面生效所需的确切动作**，并记录 T-19 实际验证过存在的入口与实测输出片段。
- 验证环境：`H:\git\Multi-Workers`（Windows / PowerShell），Python 3.14.3，Node 24，serve PID 168160（`started_at_ms=2026-10-13T02:57:56Z`）。
- 纪律：本清单只列**实际执行过**的命令；未执行的一律标"未实测"。命令均为只读或帮助面，未触发任何写盘副作用（`mw doctor`/`mw status`/`--help`）。

## 一、必须由人类执行的动作（本 key 生效前置）

### 1. `/mw restart` —— Python 面

**哪些改动面需要它**（`packages/multi-workers/**.py`，conductor 是 serve 的第三子进程，Python 只在启动时 import）：

| 文件 | 本 key 改动 |
|---|---|
| `autopilot/conductor.py` | per-key 抑制 + `remind-suppressed` 留痕 + 双通道 `_emit_alarm` + cap 降级；stage-close 自动放行五判据 + `answer_gate_auto` + `phase:"decide"` 台账；`blocker_class_of` 判定层折叠；re-attest 消费者；合成 claim 生命周期 + 外机不抢；tick 的 `GateQueueUnreadable` 留痕 |
| `autopilot/gates.py` | `_SCALAR_EXTENSION_FIELDS`/`BLOCKER_CLASSES`（`blocker_class` 序外标量）；`queue_entries` + `GateQueueUnreadable` |
| `autopilot/index_parallel.py` | 合成 claim 的 `set_claim`/`clear_claim`（`.mw/index.lock` 同锁） |
| `mw.py` | `serve.meta` 身份字段 + 采集前置 + `serve_code_verdict`/`_report_serve_code_drift` + `mw status`/`mw doctor` 漂移入口 |
| `mw_common.py` | `_blocked_on_human` per-key；`_doctor_gates` 消费 `queue_entries` |

**实测入口存在**：`/mw restart` 由 agent-team-loop 扩展注册（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3490`，`sub === "restart"` ⇒ `restartMw(projectDir)`）。

**运行期实证（为什么必须重启）**：本机 serve PID 168160 的 `serve.meta` 是**旧 3 字段 schema**（无 `schema`/`commit`/`code_digest`），`mw status` 当场判：

```
[mw status] running (PID 168160)
[mw status] serve code: STALE CODE (content changed): tree=H:\git\Multi-Workers\packages\multi-workers
  schema=0/1 serve_pid=168160 started=2026-10-13T02:57:56Z code newest mtime=2026-10-13T13:47:36Z
  (base=2026-10-13T02:57:56Z) ... drift_age=10m ... digest=a660c4be5a83 fix: /mw restart
```

即：**运行中的 serve 仍是旧代码/旧 schema，`/mw restart` 前 Python 侧改动一律不生效**（这正是 spec E7 事故形态）。

### 2. `mw build --install`（或 `/mw build`）+ `/mw restart` + `/reload` —— TS 面

**哪些改动面需要它**（`packages/coding-agent/src/extensions/agent-team-loop/**`）：

| 文件 | 本 key 改动 |
|---|---|
| `autopilot/monitor.ts` | 常驻 pending 行 + stage 主闸行 + `~D`/`R:*`/紧凑 age/`+N`/`J`/`P` + 110 列 fit ladder + partial+0 渲染 `gate-queue-unreadable` |
| `autopilot/status-model.ts` | `GATE_REASONS`/`GATE_SUPPRESSION_PRIORITY`/`GATE_SCOPE_UNRESOLVED` + `deriveGateReason`；`blockerClassOf`；`listGates` 错误暴露；per-key `blockedOnHuman` |
| `pm/pm-orchestrator.ts` | 接通 `readGateReminders`；无 watch 丢弃留痕 `GATE_REMINDER_DROPPED_ENTRY_TYPE`；`tookOverFromConductor` |
| `pm/ui-bridge.ts` | `ClaimState` 的 `held-conductor`（本机合成 claim） |
| `shared/change-ledger.ts` | 角色分流 + taskDir 外交付物磁盘通道 + `malformed` + infra 收窄 + `unresolvable` |
| `worker/output-writer.ts` | `## Ledger Unresolvable` / `## Ledger Malformed` 段 + `unresolvableFiles`/`malformedFiles` |

**实测入口存在**：

```
python packages/multi-workers/mw.py build --help
usage: mw.py build [-h] [--install] [--no-dist] [--allow-dirty]
  --install      Also install the freshly built bundle into the global extensions dir
  --no-dist      Skip rebuilding packages/coding-agent/dist (the npm-link pi runtime);
                 by default --install also rebuilds it
  --allow-dirty  Install despite uncommitted changes under packages/coding-agent/src
```

`--install` 同时重建 `packages/coding-agent/dist`（npm-link 的 pi 运行时）；`/reload` 是 pi 窗口的扩展重载命令（README 的"生效路径"与 UPDATE.md 均以它作为窗口侧动作）。

**运行期实证（为什么必须重建 bundle）**：T-16 终态在**旧 bundle** 下仍报 4 条"已修"误判——`shared/change-ledger.ts` 的修复只有 `build --install` + `/reload` 后才生效。**源码改了、bundle 没重建 = 行为没变。**

### 3. 批量自动化入口（可选，替代手工）

```
python packages/multi-workers/mw.py update-env --help
usage: mw.py update-env [-h] --project PROJECT [--apply] [--json] [--fetch]
  --apply  Execute the auto-fixable actions (build+install, cache pull, framework
           reinstall, serve restart) then re-check
```

`mw update-env --apply` 会执行 bundle/dist 重建 + 全局安装 + 框架重装 + **serve 重启**；但 **`push`、pi 窗口重启与 `/reload` 仍是手动步骤**（脚本自述）。

## 二、T-19 实际验证过存在的入口（命令 + 实测输出片段）

| # | 命令 | 实测输出片段 | Exit |
|---|---|---|---|
| 1 | `python packages/multi-workers/mw.py --help` | 子命令表含 `serve,start,stop,status,doctor,build,update-env,autopilot,...` | 0 |
| 2 | `python packages/multi-workers/mw.py status --project .` | `[mw status] running (PID 168160)` / `serve code: STALE CODE (content changed): ... fix: /mw restart` | 0 |
| 3 | `python packages/multi-workers/mw.py doctor --project .` | `summary: ISSUES: STALE CODE (content changed): ...` / `serve code: STALE CODE (content changed): ...` | **1** |
| 4 | `python packages/multi-workers/mw.py autopilot gates --project .` | `no pending gates (0 total, 0 answered)` | 0 |
| 5 | `python packages/multi-workers/mw.py autopilot answer --help` | `--confirm-destructive  Second confirmation required to actually write a reject (AC-009)` | 0 |
| 6 | `python packages/multi-workers/mw.py build --help` | `--install  Also install the freshly built bundle into the global extensions dir` | 0 |
| 7 | `python packages/multi-workers/mw.py update-env --help` | `--apply  Execute the auto-fixable actions (build+install, cache pull, framework reinstall, serve restart) then re-check` | 0 |

补充（源码级确认，非命令）：`/mw restart` 注册在 `pm/ui-bridge.ts:3490`；`/mw build` 与 `/mw update [--apply]` 在 README "pi 窗口命令"表中列出；`/reload` 是 pi 内置扩展重载命令。

## 三、动作 → 生效面 映射（速查）

| 动作 | 使哪些改动面生效 | 不生效的情况 |
|---|---|---|
| `/mw restart` | 全部 `packages/multi-workers/**.py`（conductor/gates/mw.py/mw_common/index_parallel） | 未执行 ⇒ 运行中的 serve/conductor 继续用启动时 import 的旧模块（本机活体 STALE 样本即为证） |
| `mw build --install` | 全部 `packages/coding-agent/src/extensions/agent-team-loop/**`（bundle + 全局扩展 + pi dist） | 未执行 ⇒ 旧 bundle 行为（T-16 误判复现） |
| `/reload` | pi 窗口重新加载扩展（窗口侧 TS 面） | 未执行 ⇒ 当前窗口仍跑已加载的旧扩展实例 |
| `mw update-env --apply` | 上述三者中的自动化部分 + serve 重启 | push / 窗口重启 / `/reload` 仍需人工 |

## 四、未实测 / 需人工确认

- 上述**没有一条** `/mw restart`、`mw build --install`、`/reload` 在 T-19 会话内实际执行——收口卡零行为改动、不得改运行环境；本清单只验证入口存在 + 漂移活体。实际重启用例须由操作者执行。
- `mw doctor` 的 `bundle: global mtime ... source newest ... stale=True` 与 `suggest: extension bundle older than source - run '/mw build' or 'mw.py build --install'` 说明**本机 bundle 也确实落后于源码**：TS 面同样处于"未生效"状态，直到 `build --install` + `/reload`。
- 多项目（JCodingAss / FeatureMigrator）的 serve 重启不在本卡范围（P-06 只读边界）。
