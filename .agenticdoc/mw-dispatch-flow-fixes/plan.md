# Plan: mw-dispatch-flow-fixes

> 依据: spec.md（13 AC，locked 2026-09-07T20:43:55+08:00 + AC-012/013 追加）+ design.md（D-001~D-008，19 VC）

## Stage 总览

| Stage | 目标（单一） | Tasks | 覆盖 VC | 依赖 | 出口判据 |
|-------|------------|-------|---------|------|---------|
| S1 | owner 解析链正确（读侧 latest-active + 兜底 + 告警；写侧单 active） | T-01, T-02, T-03 | VC-001, VC-002, VC-003, VC-017 | 无 | 4 VC 单测/脚本验证 PASS |
| S2 | 心跳产出与消费（worker 写入 + widget/摘要 展示） | T-04, T-05 | VC-004, VC-005, VC-018, VC-019 | 无（与 S1 可并行，本窗口串行） | 4 VC 单测 PASS |
| S3 | 路由默认 pi + gate 收敛/播报作用域 | T-06, T-07 | VC-009, VC-010, VC-013, VC-014, VC-015, VC-016 | 无（与 S1/S2 可并行） | 6 VC 单测 PASS |
| S4 | doctor 活性判定 | T-08, T-09 | VC-006, VC-007 | S2（心跳行格式） | pytest + 单测 PASS |
| S5 | 全量回归 + L2 同规格实跑 | T-10, T-11 | VC-008, VC-011, VC-012 | S1-S4 全部 | ./test.sh + pytest 全绿；L2 三项全符 |
| S6 | 评审修复轮 + 终态自动回读（code-review-1 发现处置 + 用户决策 AC-014） | T-12, T-13, T-14 | VC-003/006/013/015/016/017（回归）, VC-020 | S5 完成 + code-review-1 产出 | 66/66 + 116 pytest + 本 key check 零错误；框架协议对齐推送 |

## 执行顺序

串行 S1 → S2 → S3 → S4 → S5（单窗口执行；S1/S2/S3 无相互依赖，多窗口时可并行）。

## 关键约束（跨 task 有效）

- 全部 TS 改动过 `npm run check`（full output，零 error/warning/info）
- 测试规则：vitest 走根仓 `./test.sh` 或定向 `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts`；pytest 在 packages/multi-workers 直跑
- T-03 为框架源改动（.agents/skills/agentic-task git clone）：改后需 commit + push 上游
- 每个 task 完成即跑其 VC 用例（先写测试后实现或同步进行），不留验证欠债
- 不修改 pi 核心（GC-1）；trace/队列写入遵循既有锁协议（GC-2）；无跨 worker 通信（GC-3）；看门狗语义不动（GC-4）

## Stage 明细

### S1 owner 解析链
- T-01 `index-store.ts`：`activeKey()` 改 latest-updated；新增 `readIndexMdActive()`；单测覆盖双 active（旧前新后 → 新胜）与 `_index.md` 兜底
- T-02 `ui-bridge.ts`：`resolveOwnerKeyWithSync`（显式 > latest-active > _index.md > _scratch）+ watch≠owner 每 session 一次告警；`registerWorkerTools/registerWorkerCommands` 增 watch 参数（pmActivate 传入）
- T-03 `update_index.py`：`cmd_claim` 降级其他 active 行（对齐 TS takeOverKey）；临时根脚本级验证

### S2 心跳与消费面
- T-04 `shared/heartbeat.ts`（常量 + `readHeartbeatInfo`）+ `output-writer.appendHeartbeat` + `worker-mode` 30s interval（unref，全部 exit 路径清理）
- T-05 `renderWatchLines` running 行 `ph i/n hb <age>`（>90s STALE；无 hb no-hb）+ 终态摘要 `(时长, ph i/n)` 统计

### S3 路由与 gate
- T-06 `pickWorkerRoute` 删 `review|research→claude`（codex 保留）+ 正向断言（扫描 type: review → pi/timi）
- T-07 `dispatchNewTasks` 未入队过滤前置 + `makeScopedDocGateNotifier`（watch 作用域）+ 终态摘要作用域固化单测

### S4 doctor 活性
- T-08 `mw_common.py` `worker_liveness` 节（alive/stale/no-heartbeat，`--stale-after` 默认 90）+ pytest
- T-09 `/mw doctor` TS 摘要活性行（stale 任务名列出）

### S5 回归与实跑
- T-10 全量回归：`./test.sh` + packages/multi-workers pytest 全量 + `npm run check`；mw-dispatch-reliability 既有隔离用例（VC-011）必须仍绿
- T-11 `/mw build` 重建 bundle + L2 同规格重跑（ga-spec-review-1 规格，goal-autopilot 名下）+ 证据留底 `evidence/runs/`

## 风险与回退

- T-03 框架 push 失败（远端不可达）→ 本地 clone 保留改动 + plan 记录 pending push，不阻塞 S2-S5
- T-11 L2 依赖真实凭证/服务：timi 可用即跑；不可用则记录阻塞并降级 L1 清单（验证欠债 +1，标注 L2 pending）
- VC-012 三项任一失败 → 回到对应 Stage 修复后重跑（不允许带病 done）
