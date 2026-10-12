# T-22 回执：AC-024 跨 key 只读（读全局 / 写限定）

- key: `mw-gate-verdict-hardening` · 日期: 2026-10-10 · 基线 HEAD: `776b82d7f`
- 执行方式：**PM 直执**（D-014 硬门禁批次内）
- 覆盖 AC：**AC-024**（并修订 AC-019② 的反向用例）

---

## 1. 用户命题与设计取向

用户反馈："一个更合理的设计是 pm 可以看其它 key 的 workers 和状态，但不能有改、重新派发等操作，也就是只读。"

⇒ **读面不设限，写面先拒后动**。逐一核对了扩展的写入口，只有两个入口能跨 key 写：

| 面 | 位置 | 收窄前 | 现在 |
|---|---|---|---|
| 读 | `list_tasks` `scope:"all"` / `scope:"key"` | 全局 | **不变（全局）** |
| 读 | `mw_status` / `mw doctor` / 监视面板 | 全局 | **不变（全局）** |
| 写 | `dispatch_worker`（显式 `key`）→ `resolveOwnerKeyWithSync` 的 `if (explicitKey) return explicitKey;` | **任意 key 可写** | **他人 live key ⇒ 拒绝** |
| 写 | `advance_phase` → `runAgenticScript(advance_phase.py)` | **任意 key 可写**（改其 pm-state + index 行）| **他人 live key ⇒ 拒绝** |
| 写 | `ack_worker_result` → `ackTasks(..., {watch})` | 已限本窗口 | 不变（既有先例）|
| 写 | `switch_key` / `takeOverKey` | 需显式调用、他人 live claim 需 `force` | 不变（取得写权的正门）|

## 2. 实现（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`）

- 新增 `CROSS_KEY_READ_ONLY = "cross-key-read-only"` 与
  `foreignLiveClaimRefusal(indexStore, key): string | null`；
  判据 = `claimState(indexStore.findByKey(key)?.claimId, windowClaimId()) === "held-live"`
  （**与 `takeOverKey` 的 force 判据同一函数**，避免两套活性口径漂移）。
- 放行：`_scratch`、`_`/`.` 前缀、index 无行（未认领新 key）、`claimId == self`。
- 拒绝文本：固定码 + owner claim + **允许面**（`list_tasks` all/key、`mw_status`、`mw doctor`、面板）+ **下一步**（`switch_key`）。
- `dispatch_worker`：守卫放在 `ragCheck` / `mkdir` / `dispatchTask` **之前**，且**仅当显式传 `key`** 时评估（隐式路径已退化为 `_scratch`，既有行为不变）。
- `advance_phase`：`registerAdvancePhaseTool(pi, projectDir, indexStore)` 新增第 3 参（`pm-orchestrator.ts:773` + 测试 2 处同步），守卫在 `runAgenticScript` 之前。
- 工具描述同步声明只读语义（并修正 `dispatch_worker` 里过期的 `.agenticdoc/<task_key>/task.md` 路径说明）。

## 3. `[VERIFY]` 实测

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts
→ Test Files 1 passed (1) / Tests 4 passed (4) / 831ms

# 全量相关面（所有导入 ui-bridge / worker-store / pm-orchestrator 的测试文件，18 个）
→ Test Files 18 passed (18) / Tests 368 passed | 1 skipped (369) / 15.70s

npm run check → 通过（biome / check:pinned-deps / check:ts-imports / shrinkwrap / install-lock / tsgo --noEmit / browser-smoke）
```

## 4. 非空洞对照（`evidence/scripts/t22-controls.ps1`）

| 控制 | 变异 | 结果 |
|---|---|---|
| A | 删除 `dispatch_worker` 显式 key 守卫 | 2 failed / 2 passed |
| B | 删除 `advance_phase` 守卫 | 1 failed / 3 passed |
| C | `foreignLiveClaimRefusal` 恒返回 null | 3 failed / 1 passed |
| D | 破坏 `list_tasks scope:"all"` 全局读路径 | 1 failed / 3 passed |

控制后文件还原校验通过（`restored: True`）。

## 5. 与 T-17/T-19 的同批补充（本次一并落地）

`T-17` 卡片第 3 项的告警载体此前只做到"回调"，本轮补齐**落盘 + 推送**：

- 新增 `recordDispatchAlarm(agenticdocRoot, alarm)`：向 `.agenticdoc/_autopilot/auto-decisions.jsonl` 追加
  `{seq, phase:"dispatch-alarm", kind, count, detail}`（形状对齐 Python 单写者 `conductor._append_auto_decision_row`：一行一 JSON、1-based `seq`）。
  `phase:"dispatch-alarm"` 对 **8 个 `row.get("phase") == "decide"` 消费者不可见**。
- `agent_settled` 的 `onAlarm` 现在是：**每 session 每 kind 一次** ⇒ `recordDispatchAlarm` + `deliverPmAlert`（避免队列持续损坏时每轮刷 ledger / 每轮唤醒 PM）。
- `describeDispatchAlarm(alarm)`：一行人读文本（含计数）。
- **接线用例**（`test/suite/worker-dispatch-guard.test.ts` 的 "dispatch alarm wiring"）：真的跑 `pmActivate(pi)` → 塞 1 行 10 列坏行 + 1 个待派任务 → 触发 `agent_settled` → 断言 ledger 里**恰好 1 行**且内容精确等于
  `{"seq":1,"phase":"dispatch-alarm","kind":"queue-rows-unparsable","count":1,"detail":"cols"}`，PM 侧收到一次推送；再触发一次 ⇒ 仍只有 1 行。
  **T-17/T-19 非空洞对照共 5 组**（`evidence/scripts/t17-controls.ps1`）：A 作用域 2 failed；B 配额 1 failed；C unparsable 中止 2 failed（含接线用例）；D 空队列+证据守卫 1 failed；E 摘掉 ledger 写入 1 failed。

## 6. 已知残余（诚实记录）

1. 裸 bash 直跑 `python advance_phase.py <他人 key> done` 绕开工具层（AgenticTask 是外部仓；与 G3 残余同源）。
2. 异主机 claim 保守判 live；同主机按 PID 判 live/stale ⇒ 僵死 claim 判 `held-stale` 会放行（有意：防永久锁死）。
3. `dispatch_worker` 未显式传 `key` 时退化为 `_scratch` 是**既有**行为，非本卡引入。
4. T-17 卡片里"台账历史终态行"这一支判据目前由"行存在即跳过"覆盖；`_workers.acked` 的参与属 **T-18**，`run.json` 终态优先属 **T-20** —— 两者均未落地。
