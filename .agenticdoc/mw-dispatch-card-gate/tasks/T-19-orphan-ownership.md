# T-19 无人认领时的投递归属（AC-011 / E9）

- Key: mw-dispatch-card-gate｜Wave: 12｜依赖: T-12/T-14（终态）｜type: coding｜可与 T-18 并行（写面不相交：T-18 = `ui-bridge.ts` 的 card header 合并）

## 上下文（用户裁定：E2Feature 此刻即瘫痪，属本 key 修）
窗口的自动重派扫描（`pm-orchestrator.ts` 的 `dispatchNewTasks(scope:"pm")`，由 `agent_settled` 触发）**只覆盖本窗口 watch 的 key + `_scratch`**；而 conductor 驱动的 key **禁止被 claim**（AUTOPILOT-HANDOFF §5 #13：claim ⇒ `_index.parallel` 上 `CLAIM_LIVE` ⇒ conductor 跳过该 key ⇒ autopilot 卡死）。⇒ **conductor 一旦停摆，没有任何主体拥有重派权**，操作者唯一合规动作是"什么都不做"（静默）。同时 35 个 key 全落 `out-of-scope` 告警，且该告警的清空条件（claim 某 key）恰是被禁止的动作 ⇒ **按构造永不清空**。

实测（`evidence/incidents/autopilot-producer-paralysis-20261012.md`）：`H:\git\E2Feature` 队列 675 done / 33 failed / **0 pending / 0 running**，队列文件 2 天零写入，**无 `run.json`**（旧格式）、无本地框架副本、无 `.mw/config.json`。

**这是归属缺口，不是版本偏移**（后者已由 T-13/T-14 修）。本卡修归属。

## 要求（逐条可验收）

1. **扫描范围与写权分离**：把"扫描（判定归属）"与"写权（谁能写某 key）"分开——
   - **扫描**：对 `.agenticdoc/*/workers/*/task.md` 做**全项目只读扫描**（不再把其它 key 当作"越界"），用于归属判定；
   - **写权**：仍受 AC-019 约束——只允许写 ① 本窗口 watch 的 key ② `_scratch` ③ **无活 claim 的 ORPHANED key**（走第 3 条的 claim-free 修复派发）；**有活 claim 的 key 一律不写**。
2. **ORPHANED 判定 + 响亮告警**：
   - 四态判定并给出 `ORPHANED = 存在未派发工作 ∧ 无活 claim ∧ 无活运行`（活运行 = `run.json` status running 或该 task_key 进程存活；判定依据写进报告）；
   - `ORPHANED` ⇒ **可操作**告警（指名 key、未派发工作、建议动作），走既有 `dispatch-alarm` 通道，`kind` 用新值（如 `orphaned-keys`），**每 session 每 key 一次**；
   - **告警文案分 kind**：`[mw] dispatch 已拒绝：` 只允许用于真实拒绝类 kind（`queue-rows-unparsable`/`no-product`/`write-scope-risk` 等）；**notice 类**（`out-of-scope`/`orphaned-keys`）必须用中性措辞（现状：`pm-orchestrator.ts:1201` 把所有 kind 一律套"已拒绝"）；
   - `out-of-scope` 告警在"本窗口无任何 claim"时不得表现为**恒亮**（应降级为可解释的 notice 或按需收敛）。
3. **claim-free 修复派发（核心，防死锁）**：
   - 提供一条让人/窗口对 `ORPHANED` key 派发任务的路径，**其特征是不写 claim 字段**（不使 conductor 对该 key 变 `CLAIM_LIVE`）；
   - **必须先读代码确认 conductor 的跳过条件原文**（在 `packages/multi-workers/autopilot/conductor.py` 或 `.mw/**` 中定位 `CLAIM_LIVE`/eligible 判定），把该条件原文与行号写进报告；
   - 反例断言：修复派发之后，conductor 对该 key **仍然 eligible**（claim 未被本次修复置上）。
4. **旧形态不阻碍修复（AC-011e）**：修复派发面对**旧形态目录/旧形态卡**时不得"彻底无路可走"——必须存在一条**服务层合成信封**的可行路径（复用 T-13 的 `render_task_md`/合成语义或 T-14 的 fallback 语义），且该路径**留审计事实**（`[ENVELOPE_FALLBACK]` 或等价）。必要时允许修改 `packages/multi-workers/launcher.py`，但**不得改动 `autopilot/dispatch.py` 的 producer 语义**（T-13 已定）。
5. **测试**（新建 `packages/coding-agent/test/suite/mwds-t19-orphan-ownership.test.ts`）：ORPHANED 判定四态（有工作+无 claim+无运行 ⇒ ORPHANED；有运行 ⇒ 不判；有 claim ⇒ 不判；无工作 ⇒ 不判）；告警分 kind 文案；**修复派发后 claim 未置 且 conductor 仍 eligible**；有活 claim 的 key 仍被拒写；旧形态卡经服务层合成信封可派发（含审计事实）。
6. **文档澄清**：定位 AUTOPILOT-HANDOFF（含 §5 #13）——若在本仓，更新该条为"**禁止用 claim 接管 conductor key；无人认领时的重派必须走 claim-free 修复派发**"；若不在本仓，在 `report.md` 中给出应写入的原文（PM 落文档）。**你不得写 `.agenticdoc/**`**。

## 交付格式
- 写入允许面：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`、`shared/index-store.ts`、`shared/worker-store.ts`、`shared/run-store.ts`、新建 `packages/coding-agent/test/suite/mwds-t19-orphan-ownership.test.ts`、必要时 `packages/multi-workers/launcher.py`（仅第 4 条的合成信封路径）。
- 写入禁止面：`packages/multi-workers/autopilot/dispatch.py`（T-13 语义）、`autopilot/card_audit.py`、`pm/ui-bridge.ts`（T-18 正在写）、`packages/coding-agent/test/extensions/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）、其它 key 目录。
- 验收命令：
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t19-orphan-ownership.test.ts` 全绿；
  - 回归：`node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts test/suite/worker-store.test.ts test/suite/run-store.test.ts test/suite/dispatch-card-envelope.test.ts test/suite/mwds-t02-write-intent.test.ts` 全绿（AC-019 隔离语义与既有门禁不得被破坏）；
  - `python -X utf8 -m pytest packages/multi-workers -q` 失败数 == **2**（既有基线），不得新增。
- 报告（`report.md`）须含：结论、证据（原始命令与输出；**conductor 跳过条件原文 + 行号**；修复派发后 claim 未置的断言；ORPHANED 判定四态输出；告警文案对照）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。
