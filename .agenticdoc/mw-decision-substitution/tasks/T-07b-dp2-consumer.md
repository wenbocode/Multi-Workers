# T-07b `steer-dp2.md` 消费者 + narrow 失败回退

- key: mw-decision-substitution · type: coding
- 依据：T-07 残留 1（`steer-dp2.md` 无消费者）+ PM 复核（全仓仅 pm-orchestrator 写入，无读方）

## 上下文

T-07 的 dp2 `narrow` 只做了三件事：写 `steer-dp2.md`、`displaySummary`、跳过 `deliverPmAlert`。

复核确认 **没有任何代码读这个文件**：

```
grep -r "steer-dp2|dp2-narrow-request" packages/coding-agent/src
→ 仅 pm/pm-orchestrator.ts:1594,1937,1950（都是写侧）
```

后果：`narrow` 一旦被选中，**升级告警既不唤醒 PM、也不送到 worker** —— 任务卡在原地，人永远不知道。这是 fail-open，正是 DS-4「失败一律上抛人、禁默认动作」禁止的形态。

## 要求

1. **worker 侧消费者**（`worker/worker-mode.ts`）：挂 `before_agent_start`（`worker-mode.ts:2868` 已有同型 hook，`applyRagTools` 旁）作为主消费点，并在 settle 前（`finishSuccess` 内）再查一次以覆盖“转中到达”的情形：
   - 存在且未消费（无 `[dp2-consumed]` 标记行）→ 以 `deliverAs: "followUp"` 注入其正文，前缀 `[mw dp2-narrow]`；注入成功后向该文件**原子追加**一行 `[dp2-consumed <runId> <ISO ts>]`，并写 trace `[DECISION] dp2 consumed=1`；
   - 已消费 → 不重复注入（幂等，重启后也不重放）；
   - 读取/注入失败 → trace `[DECISION] dp2 consume-failed reason=<short>`，不抛。
2. **PM 侧失败回退**（`pm/pm-orchestrator.ts`）：`narrow` 决策后**先探测任务是否仍在运行**（读 run.json 状态 / 进程存活判定，复用该文件已有工具）：
   - 在运行 → 写 steer 文件 + `displaySummary`，跳过告警（现有行为）；
   - 已 settled / 终态 → **回退到 `deliverPmAlert`**（`triggerTurn:true`），并在告警文本末尾追加一行 `[dp2-narrow-fallback] task not running; escalated instead`；
   - 探测本身失败 → 同样回退告警（fail-closed）。
3. 测试（`test/suite/dp2-narrow.test.ts` 增补 + `test/suite/dp3-answer.test.ts` 不动）：
   - 消费者：注入一次、第二次不重复、marker 行落在文件尾部、无 marker 但文件为空时不注入；
   - 回退：run.json 为 settled 时 `deliverPmAlert` 被调用且含 `[dp2-narrow-fallback]`，steer 文件**不写**；
   - 幂等：同一 steer 文件在 worker 重启后仍只注入一次；
   - 关闭态不变：`enabled=false` 零 spawn、零写、告警字节等同基线。
4. 不新增 dp、不改决策分类阈值、不改 dp3 逻辑。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（仅 dp2 narrow 分支与紧邻辅助函数）
- `packages/coding-agent/test/suite/dp2-narrow.test.ts`

## 写入禁止面

- `pm/decision-tool.ts`、`pm/triage-client.ts`、Python 侧、其它 key 目录
- 禁止 `git add/commit/checkout/stash/clean`、禁止 `npm run build`、**禁止跑 `npm run check`**（它带 `--write`，会改别人的在途文件；用 `npx tsgo --noEmit` + 对本人文件的 `npx biome check`）

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/dp2-narrow.test.ts test/suite/dp3-answer.test.ts
```

期望：全绿（20 + 新增 + 13）。

## 种子

- goal 锚点：`.agenticdoc/goal.md`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1942`（写 steer 请求）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:2110`（dp2 插入点）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2868`（`before_agent_start` hook 挂点）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3703`（settle 时补查的 followUp 注入点）

## 交付格式

- 四段：结论 / 证据（vitest 尾行 + 「无消费者 → 有消费者」对照）/ 残留与未验证 / 改动清单。
- 必须证明「任务已终态时不写 steer 文件而走告警」这条回退路径被测试覆盖。

## 改动历史

- 2026-10-20 创建（T-07 残留 1 的 PM 裁定 D-038）
