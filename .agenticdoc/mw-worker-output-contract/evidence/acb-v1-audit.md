# ACB-V1 · settleOrSelfCheck 审计（AC-004 三条件 / T-13 选项 C 落地核验）

- 审计对象：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` 中唯一的 `function settleOrSelfCheck`（定义于 :3645）。卡面行号 `worker/worker-mode.ts:2584` 为卡切出时的历史行号——文件其后增长约 1061 行；当前 :2573 附近是 run-state 落盘段（`const taskDir = path.dirname(taskPath);`）。全文件仅此一处 `settleOrSelfCheck` 定义，审计目标无歧义。
- 部署核验：`mw` serve 从 `packages/multi-workers` 运行（`.mw/serve.meta` `code_dir`），其 bundle `packages/multi-workers/dist/extensions/agent-team-loop.js` 与源逐字一致（下附行号）；`packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` 亦一致。三副本均含 T-13 选项 C 行为。
- 审计方式：只读代码审计。未修改任何代码、未运行测试（符合卡面「不要修改代码」与写面禁令）。
- 审计判定总表：(a) PASS / (b) PASS / (c) PASS。

## (a) 自检回合条件 = hasDeliverableEvidence(...).delivered（writeless）或 true（write 角色） — PASS

原始断言（`worker/worker-mode.ts`）：

- :3646 外层门禁（与 `judgeRecoveryHere()` :3512-3513 同式）：`if (judgedType !== undefined && (isWritelessRole(meta.type) || hasReportProduct(taskDir))) {`
- :3655-3661 观测行（判定与否都写）：`appendTrace(..., \`recovery-gap missing=${...} selfcheck=${selfCheckSent ? "sent" : "pending"}\`)`
- :3662 实质缺口过滤：`const substantive = missing.filter((name) => !isMechanicalSection(name));` —— 机械段（`MECHANICAL_SECTIONS = ["上下文来源"]`，output-sections.ts）缺口不烧回合，走 `finishSuccess` 内的 I2 backfill（:3550-3567）
- :3674-3676 交付判定（选项 C 核心）：

```ts
const isDelivered = isWritelessRole(meta.type)
    ? hasDeliverableEvidence(taskDir, lastAssistantText).delivered
    : true;
```

- :3677 回合条件：`if (!selfCheckSent && substantive.length > 0 && isDelivered) {`
- :3679-3686 回合载体：`pi.sendUserMessage("[mw recovery self-check] …本进程只自检一次…", { deliverAs: "followUp" })`

结论：writeless 角色的回合门槛恰为 `hasDeliverableEvidence(taskDir, lastAssistantText).delivered`；write 角色经外层 `hasReportProduct(taskDir)` 守卫（report.md / report-\<slug\>.md 非空，output-writer.ts:199-202）后 delivered 恒 true（`: true` 分支）。该谓词与 `finishSuccess` 的交付判定（:3534-3536）逐字相同、共用同一 `taskDir`（:2573 闭包声明；:3288 处为 `writeCheckpoint` 内局部遮蔽，值同源 `path.dirname(taskPath)`）与同一 `lastAssistantText`（:3124 声明，:3134 于 `agent_end` 刷新）。

## (b) selfCheckSent 每进程一次 — PASS

原始断言：

- :3189 进程级单次声明（worker setup 闭包内，随进程存活）：`let selfCheckSent = false;`
- :3677 回合守卫含 `!selfCheckSent`
- :3678 置位先于发回合：`selfCheckSent = true;` 在 `pi.sendUserMessage` 之前执行——即使回合发送异常也不会重发
- 全文件 `selfCheckSent` 仅 4 处出现：声明 :3189 / trace 读 :3659 / 守卫 :3677 / 置位 :3678。无任何重置路径
- 第二次 settle 落终态的幂等保障：`finishSuccess` 首行 `if (taskDone) return;`（:3525）+ `taskDone = true;`（:3526，AC-010② 单次写出口径）——自检回合后的再 settle 不会再写第二个 harness 块/第二条 `[END]`/第二条告警
- 回合消息文本自述契约：「本进程只自检一次，之后按实际产物判定」（:3684）

结论：标志为进程级闭包变量、置位先于回合发送、无重置路径、终态写出口径幂等——自检回合在单进程内至多一次。

## (c) 未交付走 finishSuccess（no-product 裁决） — PASS

原始断言：

- :3677 `isDelivered === false`（writeless 未交付）⇒ 回合块整体跳过；控制流落到 :3690 尾调用 `finishSuccess();`（`settleOrSelfCheck` 的唯一其他出口）
- :3534-3536 `finishSuccess` 以同一谓词取证据：writeless ⇒ `hasDeliverableEvidence(taskDir, lastAssistantText)`；write ⇒ `{ delivered: true, channel: "none", detail: "write role" }`（write 角色不存在未交付形态，裁决面收窄自洽）
- :3575 exit 折叠：`const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;` —— 未交付即 exit=2
- :3598 exitReason 未交付分支：`` `Agent settled after ${toolCallCount} tool call(s) without a deliverable: ${evidence.detail} ${effort}` ``
- :3606 `## Questions` 载荷：`` : `no-product: ${evidence.detail}`, ``
- :3609-3618 告警（记入真 .agenticdoc 根的调度账本，非 workers 子目录）：

```ts
if (!evidence.delivered) {
    recordDispatchAlarm(meta.trueAgenticdocRoot, {
        kind: "no-product",
        count: 1,
        detail: `${meta.taskKey}:${evidence.channel}`,
    });
}
```

- 未交付形态下 `settleOrSelfCheck` 不执行任何 `sendUserMessage`：no-product 裁决立即生效，AC-006/C5 告警不被回合延后（选项 C 与选项 B 的分界线保住）

结论：未交付 settle 不发回合、直接走 `finishSuccess` 的 no-product 裁决（exit=2 + `no-product:` Questions 首行 + 恰 1 条 no-product 告警）。

## 附 1：两条 settle 入口均经 settleOrSelfCheck

- :3712（无 phases 的首次 settle 路径）与 :3743（全部 phase 完成后）均以 `settleOrSelfCheck();` 收口——审计对象覆盖该进程全部 settle 终态路径；`taskDone === true` 后的再 settle 在 handler 首行被挡（:3700 `if (taskDone) return;`）。

## 附 2：三副本一致性（行号）

| 副本 | selfCheckSent 声明 | settleOrSelfCheck 定义 | isDelivered 三元 + 守卫 + 置位 | exitCode 折叠 | no-product Questions | kind: "no-product" |
|---|---|---|---|---|---|---|
| 源 `src/.../worker/worker-mode.ts` | :3189 | :3645 | :3674-3678 | :3575 | :3606 | :3614 |
| `packages/coding-agent/dist/.../worker-mode.js` | :2725 | :3138 | :3161-3165 | —（同构） | —（同构） | —（同构） |
| `packages/multi-workers/dist/extensions/agent-team-loop.js`（serve 实际运行副本，`.mw/serve.meta` code_dir） | :20672 | :20965 | :20979-20981 | :20922 | :20942 | :20947 |

三副本逻辑一致；T-08 部署的 bundle 已含 T-13 选项 C 行为。

[VERIFY] ACB-V1 探针交付：exit=0。
