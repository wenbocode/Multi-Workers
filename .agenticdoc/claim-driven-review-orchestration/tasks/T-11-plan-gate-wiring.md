# T-11 `plan` 档接进派发工具（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1 出口（plan 档真实可跑）
- type: coding
- 依赖：T-10（`pm/review-split-plan.ts`）done

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（协调只走文件；`plan` 档必须"看得见、可回退、零副作用"）。
- 事实（PM 已核）：`mw dispatch` 工具的两个入口都在 `pm/ui-bridge.ts`：
  - `pm/ui-bridge.ts:3341` 附近（`writeDispatchTaskMd` → `dispatchTask`）
  - `pm/ui-bridge.ts:3865` 附近（同上）
  两处都是**先 `writeDispatchTaskMd` 写 task 目录与 task.md，再 `dispatchTask` 写队列行**。
  所以 `plan` 档的短路必须插在**这两步之前**——否则"零副作用"不成立（`GC-3`）。
- `readDispatchCard`（`pm/ui-bridge.ts:2864`）已给出 `sections.type`、`claims`、`resolvedPath`、`sha256`。

## 要求

1. 新增 `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-gate.ts`：
   ```ts
   export function planReviewSplitGate(input: {
     cardPath: string; taskKey: string; ownerKey: string;
     agenticdocRoot: string; projectDir: string;
   }): { text: string; manifestPath: string } | null
   ```
   - `resolveReviewSplit(projectDir)`；`mode !== "plan"` → 返回 `null`（`off`/`on` 全部原路直走，**逐字节不变**）。
   - 卡 `type:` 不是 `review` → 返回 `null`（**不要**在 stdout 打东西）。
   - 否则读卡文 → `planReviewSplit({taskKey, projectDir, cardText, mode:"plan"})` →
     写 `<agenticdocRoot>/<ownerKey>/evidence/split/review-<taskKey>-manifest.json`
     （`mkdirSync(recursive)` + 先写 `.tmp` 再 `rename`），返回
     `{ text: plan.receipt + "\n[review-split] manifest=<相对 projectDir 的路径>", manifestPath }`。
   - 任何异常一律**不抛**：返回 `{ text: "[review-split] mode=plan error=<code>" }`（P-048）。
   - **禁止**创建 `workers/<taskKey>/` 目录、**禁止**写 `task.md`、**禁止**写任何队列文件。
2. 在 `pm/ui-bridge.ts` 的**两个** dispatch 入口，紧跟 `readDispatchCard` 成功之后、`writeDispatchTaskMd` 之前插入：
   ```ts
   const splitGate = planReviewSplitGate({ cardPath, taskKey: <该入口的 task_key>, ownerKey, agenticdocRoot, projectDir });
   if (splitGate !== null) return { content: [{ type: "text", text: splitGate.text }], details: undefined };
   ```
   变量名按各自作用域的实际名字（`task_key` / `taskKey`）。**每个入口新增行数 ≤ 6**；
   `off` 档路径（`null`）必须保持原有全部行为。

## 交付格式

- 新增 `pm/review-split-gate.ts`；改 `pm/ui-bridge.ts`（仅这两处插入）。
- 新增测试 `packages/coding-agent/test/suite/review-split-gate.test.ts`，在临时项目目录里造卡，至少 6 条：
  ① `mode=plan` + review 卡（带 claims 块）→ 返回非 null、manifest 文件存在且可 `JSON.parse`、
     `selfSha256` 非空；② 同一场景断言 `workers/<taskKey>/` **不存在**、`.mw/workers.parallel` 不存在（零副作用）；
  ③ `mode=off` → 返回 `null` 且**什么都没写**；④ 非 review 类型 → `null` 且什么都不写；
  ⑤ 卡文无清单来源 → 仍返回文本（含 `units=0`），manifest 里 `ids=[]`，不抛；
  ⑥ 重复调用两次写出的 manifest 内容一致（幂等）。
- 报告 `report.md` 四段；`## 证据` 贴 `vitest` 实际 passed 数与 `git diff --stat pm/ui-bridge.ts`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/review-split-gate.ts`（新）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（只允许上述两处插入）
- `packages/coding-agent/test/suite/review-split-gate.test.ts`（新）

## 写入禁止面

- `pm/review-split-plan.ts`、`shared/**`、`.mw/**`、`.agenticdoc/**`、`dist/**`、其他任何文件

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/review-split-gate.test.ts`（≥6 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡（M1 出口接线） | `ui-bridge.ts:3341`/`:3865` 先写卡后入队、GC-3 零副作用 |
