# FIX-C：签收写守卫补齐 `worker_file` 通道（QG MAJOR-4）

- type: coding
- owner key: mw-decision-substitution
- 来源：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md` §B major 第 4 条

## 上下文

D-015 的签收写守卫 `registerDecisionSignoffGuard`（`shared/xkey-gate-guard.ts:420`）只拦 `write` / `edit` / `bash` 三类 `tool_call`。但 writeless 角色（research / review）**唯一的写通道是 `worker_file`**，而 `worker_file` 的写面判定 `judgeWriteTarget`（`shared/write-surface.ts`）显式接受 `<key>/evidence/**`（"no extension restriction"，见 `worker/worker-file-tool.ts:101-107` 的 `inEvidence` 分支跳过 basename 白名单）。

所以 `worker_file({file: "evidence/review/sign-final.md", ...})` 是**合法落地**的。

而守卫模块自己的注释（`shared/xkey-gate-guard.ts:296-320`）声称 "sign-off is the HUMAN answer channel … an agent cannot do it through its only tool channel" —— 这个前提对 `worker_file` 不成立。

done 门禁只验文件存在 + `conclusion:` 行（`.agents/skills/agentic-task/scripts/advance_phase.py:98-110`），不验作者，所以被派发的 worker 可以自写签收、满足 done 门禁。这正是 spec §10 风险表"签收被 PM 代签"的变体（PM 不可，worker 可以）。

**已确认安全的边界**（不要扩大改动面）：
- `dp apply` 仍拒绝 agent 会话；
- `.mw/decide-points.json` 不在 evidence 写面内，不可经 `worker_file` 写 → **授权表本身安全**；
- 被伪造的是"人已 review"这个事实与 done 门禁。

## 要求

1. 在守卫里增加 `toolName === "worker_file"` 分支：命中签收路径时拒绝，错误信息与现有 write/edit/bash 拒绝路径保持同一措辞风格，并带 `evidence_line`（守卫既有的 trace 契约，一行）。
2. 签收路径判定必须与 `advance_phase.py` 的固定名一致：`sign-final.md`（D-014 固定名），且覆盖 `<key>/evidence/review/sign-final.md` 与 `<key>/evidence/sign-final.md` 两种落位；实现放**一个**判定函数，守卫与（如需要）write-surface 共用，禁止两处各写一份正则。
3. 不要因此拦掉 writeless 角色的正常产物（`evidence/review/<其它名>.md`、`evidence/research/**` 必须仍可写）。
4. 测试（`decision-signoff.test.ts`）：
   - 新增：`worker_file` 写 `evidence/review/sign-final.md` → 被拒，`[DECISION_SIGNOFF_BLOCK]`（或既有 trace 名）一行，且无文件落地。
   - 新增：`worker_file` 写 `evidence/review/review-notes.md` → 放行（防过度拦截）。
   - 既有 3 条（write/edit/bash）必须继续绿。
5. 若 `judgeWriteTarget` 才是更合适的唯一收口点（报告的第二方案），可以改那里，但必须说明为何不会误伤 `dp apply`/PM 自己的签收写入路径；两种方案任选其一，不要双保险重复实现。
6. 不得引入 `any`；只准用可擦除 TS 语法。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待修：`packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:420`（只匹配 `write|edit|bash`）
- 漏洞面：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts:101`（evidence 面跳过 basename 白名单）
- 门禁判据：`.agents/skills/agentic-task/scripts/advance_phase.py:98`（只验文件存在 + `conclusion:` 行）

## 交付格式

- 方案选择与理由（守卫分支 vs write-surface 拒绝表），一段话。
- `path:line` 改前/改后对照。
- 测试计数行 + 一条"真实拦截"证据（`worker_file` 调用被拒的 trace 行原文）。
- `tsgo --noEmit` rc。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts`
- `packages/coding-agent/test/suite/decision-signoff.test.ts`

## 写入禁止面

- 其它任何 `src/**`、`test/**`（尤其 `pm/decision-tool.ts`、`pm/pm-orchestrator.ts`、`worker/worker-mode.ts`：并行 worker 正在改；`shared/heartbeat.ts`：PM 本会话已改）
- `packages/multi-workers/**`、`.agents/**`、`.claude/**`（框架脚本副本，另有 key 在改）
- `docs/**`、`CHANGELOG`、`.agenticdoc/**`（除 `workers/fix-qg-major4/**` 自身运行目录）
- 禁止 `git` 任何写操作；禁止 `npm run check` / `biome --write`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-signoff.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/xkey-coverage.test.ts
npx tsgo --noEmit -p tsconfig.json
npx biome check src/extensions/agent-team-loop/shared/xkey-gate-guard.ts test/suite/decision-signoff.test.ts
```

`xkey-coverage.test.ts` 若文件名不同，用 `ls test/suite | grep -i xkey` 找到真实文件后跑它，并在报告中给出实际命令。
全绿且 `tsgo` rc=0 才算完成；红就停下报告，不要放宽断言。

## 改动历史

- 2026-10-20 建卡：来源 QG MAJOR-4（`xkey-gate-guard.ts:420` 只拦 write/edit/bash；`worker-file-tool.ts:101-107` evidence 面接受任意名）。
