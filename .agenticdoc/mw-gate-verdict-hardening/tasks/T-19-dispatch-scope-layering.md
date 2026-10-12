# T-19: G6-A 派发作用域分层（PM 收窄 / mw 指令全局）

- 波次: **4** · 依赖: **T-17**（同写 `pm-orchestrator.ts`，必串行）
- 写面（独占）: `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`、`packages/multi-workers/mw.py`（仅断言/注释级；本卡不得改变 `mw dispatch` 语义）
- AC: **AC-019** · VC: **VC-034 / VC-035 / VC-046**
- 基线: `10446aefb`

## 问题（用户要求①：隔离）

当前 `dispatchNewTasks`（`:393-476`）**没有任何作用域概念**：一次 `agent_settled` 触发的是**全项目 28 个 key** 的候选集，并对 `.agenticdoc/_workers.parallel`（项目级共享台账）做整表回写。

⇒ **本 key 只派 1 个 worker，也可能把其它 27 个 key 的队列行翻面**（IN-3 的放大路径）。用户明确要求："当前 key 的执行会影响到所有历史 worker，必须隔离"。

**用户定调的边界（2026-10-10）**：收窄**只加给 PM 侧的自动派发**；`mw` 指令面（`mw dispatch` 等）**必须保留全局扫描能力**（显式跨 key 派发是合法用法）。

## 交付

1. `dispatchNewTasks(scope: "pm" | "cli")`：
   - `scope === "pm"` ⇒ 候选集 = **本窗口 watch 的 key**（`_index.parallel` 里本窗口 claim 的 key）∪ `{_scratch}`；
   - `scope === "cli"` ⇒ 候选集 = 现有全项目行为（供显式刷新命令与测试使用）。
2. `agent_settled` 处理器（`:737-744`）传 `scope: "pm"`。
3. 被作用域跳过的候选必须**可见**：在 `auto-decisions.jsonl` 写 `{ phase: "dispatch-alarm", kind: "out-of-scope", keys: [...] }`（数量聚合，避免刷屏）—— 这不是禁止，只是"我看到了但没动"。
4. `mw.py` 侧：加注释/断言说明 CLI 面**不受**此收窄影响（该面的全量 spawn 在 `launcher.py`，显式派发入口是 `dispatch_worker(key=…)`）。

> **实现记录（2026-10-10，PM 直执）**：本卡 1/2 已随 T-17 同批落地（`DispatchScanOptions.scope` + `agent_settled` 传 `pm`）；第 3 项（out-of-scope 候选写 `dispatch-alarm`）**改为**：告警类型扩展到 `queue-rows-unparsable` / `queue-unreadable` / `dispatch-quota`，由 `agent_settled` 的 `onAlarm` 写 `auto-decisions.jsonl` + `deliverPmAlert`（每 session 每 kind 一次）；被作用域跳过的候选**不单独告警**（健康项目下每轮都会有别的 key 的候选 ⇒ 会成噪音），其可见性由 AC-024 的**全局只读读面**承担（用户定调：看得见，不是“我看到了但没动”）。

## 契约（冻结）

- **不得**把 `scope` 收窄应用到 Python `dispatch.py` / `mw dispatch`（AC-019②）。
- **不得**改 `_index.parallel` 的写面语义（只是读自己 claim 的 key）。
- 收窄后**单次派发的副作用面 = 1 行**（自己的任务）；其它 key 的行必须逐字节不变。
- 若本窗口没有 claim 任何 key（未接管任何 key 的窗口）⇒ 候选集 = `{_scratch}`（fail-safe，不全局扫描）。

## [VERIFY]

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-scope.test.ts
```

- 用例 A（AC-019①）：构造 28 key / 250+ 行队列 + 本窗口 watch 1 个 key ⇒ 派发 1 个任务后，其它 key 的行**逐字节**不变（对文件做 sha 前后比对）。
- 用例 B（AC-019②）：同一状态下调用 `dispatchNewTasks(..., { scope: "cli" })` ⇒ **跨 key 派发成功**（新增其它 key 的行）；另加：**未认领新 key** 经 `dispatch_worker(key=新 key)` 显式派发 ⇒ 成功（AC-019③）。

> 修订（2026-10-10）：原用例 B 写的是 `mw dispatch --key <其它 key>`，但**该子命令不存在**（`mw.py` 子命令表实测无 dispatch，见 AC-019 `[REVISED]` 标注）。

## 非空洞对照

1. 移除 `scope === "pm"` 的候选集收窄 ⇒ 用例 A 必红（其它 key 行被写）。
2. 把收窄也施加到程序化 `scope: "cli"` 路径/未认领新 key ⇒ 用例 B 必红（跨 key 派发失败）。

## 回执

写入 `workers/t-19-scope-layering/report.md`，写完立即复制到 `evidence/runs/`。
