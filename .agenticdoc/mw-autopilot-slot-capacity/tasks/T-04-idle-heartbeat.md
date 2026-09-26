# T-04: idle 看门狗：in-flight 分类判定 + 心跳 + `[IDLE_KILL]` 证据（c2）

- 波次: **0** · 依赖: 无
- 写面（独占）: 
  - `packages/coding-agent/src/core/tools/bash.ts`
  - `packages/coding-agent/src/extensions/agent-team-loop/worker-mode.ts`
  - `packages/coding-agent/test/suite/worker-idle-heartbeat.test.ts`（新建）
- AC: AC-005 · VC: VC-004, VC-005, VC-006
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

修 idle 误杀（实测 24 次，23/24 最后活动是 bash、22/24 "工具起→判死" 恰等于 `idle_s`）。真因 = bash 的 update 是**输出驱动**（`core/tools/bash.ts:200/371-373/392-401/411-414`），缺的是心跳，不是阈值。

## 交付物

- D：`[IDLE_KILL]` 结构化证据（写入 timeline/日志）——in-flight 工具名、工具已运行秒数、阈值、最后活动来源；**没有它就不许杀**。
- B：in-flight 工具分类判定 —— 长跑工具（bash）在飞时用 `toolIdleMs` 而非纯 `idle_s`；对齐既有 `withHeartbeat` 30s 先例（`rag/budget.ts:257-280`）。
- A/B 组合：`core/tools/bash.ts` 加心跳续命（30s 粒度），使"长 bash 无输出"不再累计 idle。
- C：**无 in-flight 工具**分支保留原判据 + 二次确认（避免真挂死被漏杀）。

## 契约（不得重定义）

- **不单独抬 `DEFAULT_IDLE_MS`**（`worker-mode.ts:148` = 600000）：阈值不是根因，抬阈值会让数据被截尾。
- `PI_WORKER_IDLE_MS` 现有语义不变（`:163-167`）。
- 不新增配置键；`worker_timeout_min` 接线归 T-12。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-idle-heartbeat.test.ts`

## 非空洞对照（必须附在回执里）

- 去掉心跳 ⇒ "长 bash 无输出 601–622s" 用例必须变红（仍被杀）。
- 把分类判定放宽成"任何工具在飞都不杀" ⇒ **真挂死用例**必须变红（必须同时断言真挂死仍被杀：无 in-flight 工具 + 无 token 增量）。
- 去掉 `[IDLE_KILL]` 证据 ⇒ 证据完整性断言必须红。

## 风险与注意

- 改动落在 core 工具层与 worker 模式，影响面含非 worker 会话 ⇒ 用 fixture 收敛，不动交互式路径行为。
- 既有 89 条 Windows 基线失败与本卡无关，不要追。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-04-idle-heartbeat/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
