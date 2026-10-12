# T-13: G4 帧自证与失败降级（monitor 串行链第二段）

- 波次: **2** · 依赖: T-08
- 写面（独占）:
  - `.../agent-team-loop/autopilot/monitor.ts`（渲染首行 `:672-673`、`startMonitor` `:820-839`、裸 catch `:828-833`）
  - `.../agent-team-loop/test/suite/autopilot-monitor.test.ts`（G4 用例段）
- AC: AC-015, AC-016, AC-017 · VC: VC-020, VC-021, VC-022
- 基线: `10446aefb`

## 目标

让面板**不能撒谎**：帧自证新鲜（冻结可见、可自动判过期），失败不静默丢帧，数据面变化有界跟随。

## 交付物

1. **帧自证**（D-017）：`MonitorSnapshot`（`:170-176`）增 `collectedAtMs`（绝对墙面时刻，`Date.now()`）+ `tickCount`（模块级单调递增）；渲染进 `renderMonitorLines` 首行（`:672-673`）。
2. **过期告警**：连续 > 3 个刷新周期未前进（复用 `staleAfterMs = max(30s, pollMs*5)`，定义 `:609`、`tickStale` `:635`）⇒ 首行显式 `STALE PANEL`（用 `formatDuration:651-658`）。
3. **失败不静默**（D-018）：裸 catch（`try` `:829` / `catch` `:831`）改为**产出降级帧**（沿用上一帧数据 + `lastErrorAtMs` + 错误摘要 + 降级标记），不丢帧。
4. **跟随**（AC-016）：数据面变化后面板在 ≤2 个刷新周期（8 s）内跟随（`MONITOR_INTERVAL_MS = 4000`，`:58` 不改）。

## 契约（不得重定义）

- **不围绕 `/mw restart` 设计**：RQ-4 已证伪（`launcher-beat` 身份耦合 TS 侧 0 命中；`/mw restart` 不触碰 pi 进程）。
- **不得新增写路径**（既有断言 `autopilot-monitor.test.ts:412` 锁"三 tick 文件字节不变"）；失败证据只落在**帧内**。
- 不动 T-08 的 `blockedOnHuman` 字段与置顶行逻辑；不动生命周期段（`stopMonitor` `:847`）。
- 边界必须写进实现注释并在用例里覆盖：**首次 tick 即失败** ⇒ 无"上一帧"可沿用，只能出 `collectedAtMs` + 错误摘要。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts`

## 非空洞对照（必须附在回执里）

- 注入一个总是抛错的 `readState` ⇒ 必须看到**降级帧**（而非停在旧帧/空帧）；摘掉降级分支 ⇒ 用例转红。
- 用 fake timers 推进 >3 周期不刷新 ⇒ `STALE PANEL` 必须出现；摘掉告警 ⇒ 转红。
- 让 `_workers.parallel` 从 0 running 变 N running ⇒ ≤2 周期内面板必须显示 `workers: N running`（VC-021 的反向用例）。

## 风险与注意

- **`monitor.ts` 串行链第二段**：开工前 `git diff` 确认 T-08 已落且无第三处并发改动。
- 若发现 `readMonitorState` 之外还有**不受该 try 保护**的读（例如 `startMonitor` 之外被独立调用的路径），**先回报 PM**，不要顺手把写面扩到 `shared/worker-store.ts` / `shared/mw-runner.ts`。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-13-g4-freshness/report.md`（含 `[VERIFY]` 命令原文与输出、三组非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
