# T-04c decision_id / mode / acted 转发

- key: mw-decision-substitution · type: coding
- 依据：T-08 残留 2 + PM 裁定 D-041

## 上下文

`pm/ui-bridge.ts:actedDecisionOf`（`:293`）已经写好：它只**结构性读取** `triage.result.decision_id` 与 `triage.result.acted`，绝不从配置表或 mode 推导（D-036）。但现在**上游一个字段都不转发**：

- `pm/triage-client.ts:141` 的 `TriageResult` 没有 `decision_id` / `mode` / `acted` / `escalated_reason`；
- Python 侧 `mw decide run` 自 T-02b 起已经在 JSON 里返回 `decision_id` / `mode` / `acted` / `escalated_reason`（`mw.py:_decide_run_payload`）。

所以「决策 → 结果」关联链整条是断的：`decision:` 头行永远不写，settle 也永远没有可关联的 decision。

## 语义（D-041，必须照此实现）

Python 的 `acted=false`（`intent="answer"`）表示「Python 没有替你执行动作」，**不等于「答案没被采纳」**。采纳发生在消费侧，因此：

| 场景 | `decision_id` | `acted` |
| --- | --- | --- |
| dp1 派发，CLI 返回 `available=true`、`mode=auto`、有 `triage_type` | 透传 CLI 的 `decision_id` | **true**（派发方采纳了该类型） |
| dp1 派发，`mode=suggest` / `available=false` | 透传（若有） | false / 缺省 |
| dp3 澄清，自动应答并成功注入 `[mw dp3-answer]` steer | 透传 | **true** |
| dp3 澄清，3b / `suggest` / 降级 / 预算用尽 | 透传（若有） | false / 缺省 |
| dp2 `narrow` 已执行（写 steer + 跳过告警） | 透传 | **true**（本卡只要求把字段备好，dp2 侧接线可选） |

**硬约束**：不得在 TS 里读 `.mw/decide-points.json` 判断"该不该 acted"，也不得由 `mode` 反推 `acted`。`acted` 是**消费动作发生的事实**，由执行点显式给出。

## 要求

1. `TriageResult` 增加可选字段：`decision_id?: string`、`mode?: "auto" | "suggest"`、`acted?: boolean`、`escalated_reason?: string`；在 `triageDispatch` 解析 CLI 响应处**原样透传**（不要把 `escalated_reason` 映射回 `reason`，两者并存）。
2. `worker/worker-mode.ts` 的 dp3 自动应答成功分支（`attemptDp3Clarification` 返回 true 处，约 `:3684`）：把该次结果标记 `acted: true` 并带上 `decision_id`，供 trace 与后续 `decision:` 头行使用；降级分支不得标 true。
3. `pm/ui-bridge.ts` 的 dp1 派发路径：`computeDispatchTriage` 在 CLI 返回可用且 `mode==="auto"` 且拿到 `triage_type` 时，在 `DispatchTriage` 上补 `decision?: DispatchDecision`（复用 `actedDecisionOf` 的输入形状），使 `writeDispatchTaskMd` 能写 `decision:` 头行；`suggest`/不可用保持 undefined（字节同构）。
4. dp2 `narrow` 分支：跳过告警并写完 steer 后，把 `{decisionId, acted:true}` 附到该任务的记录结构上（若该结构不存在，则只写 trace `[DECISION] dp2 acted=1 decision_id=...`），不改变告警路径。
5. 测试：
   - `triage-client-state.test.ts`：CLI 响应含 `decision_id`/`mode`/`acted`/`escalated_reason` 时逐键透传；缺失时字段为 undefined（不伪造）。
   - `decision-association.test.ts`：dp1 `auto` + 可用 → `writeDispatchTaskMd` 真的写出 `decision:` 行；`suggest` → 不写（字节同构基线）。
   - `dp3-answer.test.ts`：自动应答分支 trace 含 `acted=1` 与 `decision_id`；降级分支不含。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/triage-client-state.test.ts`
- `packages/coding-agent/test/suite/decision-association.test.ts`
- `packages/coding-agent/test/suite/dp3-answer.test.ts`

## 写入禁止面

- 其它任何文件（含 `pm-orchestrator.ts`、`index.ts`、Python 侧、skill 脚本、其它 key 目录）
- 禁止 `git add/commit/checkout/stash/clean`；禁止 `npm run build`、`npm run check`（用 `npx tsgo --noEmit` + 对本人文件的 `npx biome check`）

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/triage-client-state.test.ts test/suite/decision-association.test.ts \
  test/suite/dp3-answer.test.ts test/suite/triage-dispatch.test.ts
```

期望：全绿（48 + 27 + 13 + 新增）。

## 种子

- goal 锚点：`.agenticdoc/goal.md`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:293`（`actedDecisionOf`，已就绪的消费端）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:141`（`TriageResult`，缺字段）
- `packages/multi-workers/mw.py:862`（`_decide_run_payload`，已返回四字段）

## 交付格式

- 四段：结论 / 证据（四套件尾行 + `decision:` 行真的写出的对照）/ 残留与未验证 / 改动清单。
- 必须证明「`suggest` 时 task.md 与基线逐字节相同」，而不是只断言不含 `decision:`。
- 契约冲突停手写残留。

## 改动历史

- 2026-10-20 创建（T-08 残留 2 → D-041）
