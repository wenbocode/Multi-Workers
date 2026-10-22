# FIX-E：dp3 子进程 mode 缺失的本地回退 + 签收守卫深路径误拒（QG-2D 残留）

- type: coding
- owner key: mw-decision-substitution
- 来源：`evidence/quality-gate-report-20261020d.md`「残留与未验证」第 1、2 条（MAJOR-3 / MAJOR-4 的剩余项）
- 两条都很小：合计约 6 行实现 + 2 个用例。

## 背景

第一轮 QG 的 MAJOR-3（TS 镜像授权表）与 MAJOR-4（签收写守卫）已在 FIX-B / FIX-C 修过主体；
本轮窄卡复审（`ds-qg-review-2d`）判「NOT-CLOSED」，留下两个具体残留，PM 已独立复现，确认成立。

## 改动 1：dp3 子进程 `mode` 缺失时不得回退本地 policy（MAJOR-3 残留）

`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4933` 现在是：

```ts
const childMode = payload.mode === "auto" || payload.mode === "suggest" ? payload.mode : input.policy.mode;
```

子进程没报 `mode`（或报了非法值）时，退回本地读表得到的 `policy.mode`。问题是这条路径**会 spawn**
（3a / 3c 走服务），而 `payload.mode` 正是「服务是否认为自己已经作答」的事实来源；本地回退等于
TS 在 `payload.mode` 缺失时自己认定 `mode=auto`，进而可能注入 steer（`acted=true`），
这与 D-036（单一权威）和 D-041（`acted` 是消费侧事实）冲突。

改成 fail-loud：

- `payload.mode` 必须是 `"auto"` 或 `"suggest"`；
- 否则**不落答案**，返回 `escalate("unavailable", "3a", "decision mode missing")`（走人）；
- 不要新增 `EscalatedReason` 词表成员（`unavailable` 已在词表内）。

注意区分：`:4863` 的 3c 本地引用匹配路径（零 spawn，`mode: input.policy.mode`）**不动**，
它是本地判定、没有子进程可问，`worker-mode.ts:4745` 的注释已经写明理由；`:3715` 与 `:3788`
的 trace 行也**不动**（那是非答案行的标签，不是生效依据）。

## 改动 2：签收守卫对深层研究路径误拒（MAJOR-4 残留）

`packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:383` 用
`dir.lastIndexOf("evidence")` 定位 evidence 段，导致合法研究产物
`evidence/research/evidence/sign-final.md`（最后一段 `evidence` 之后 tail 为空）被当成签收文件拒写。

改成从**第一个** `evidence` 段起算：`dir.indexOf("evidence")`。语义要保持不变：

- `.agenticdoc/<key>/evidence/sign-final.md` → 拒；
- `.agenticdoc/<key>/evidence/review/sign-final.md` → 拒；
- 大小写变体（win32 fold）→ 拒；
- `<key>/evidence/research/sign-final.md` → 放行；
- `<key>/evidence/research/evidence/sign-final.md` → 放行（这就是本次要修的误拒）；
- `<key>/evidence/review/sub/sign-final.md` → 放行（tail 长度 2，非签收落位）。

同时补一句注释说明为什么用首个 `evidence` 段（key 目录相对路径只有一层 evidence 面，
更深的 `evidence` 是产物名的一部分，不是落位）。

## 必做用例

1. `packages/coding-agent/test/suite/dp3-answer.test.ts`：新增一例——stub 子进程返回
   `available=true` 且带合法 `answers`，但**不带 `mode`**（或 `mode: "bogus"`），断言
   结果走 `escalate`、trace 是 `sub=3a acted=false` 且 `escalated_reason=unavailable`、
   **不注入任何 steer**、**不写 `decision:` 头行**。
2. `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts`：新增一例——
   `worker_file` 写 `.agenticdoc/<key>/evidence/research/evidence/sign-final.md` 放行；
   同文件已有的两个拒绝分支保持不变、必须仍通过。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`
- `packages/coding-agent/test/suite/dp3-answer.test.ts`
- `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts`
- `docs/decision-substitution.md`
- `packages/coding-agent/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/**` 一切文件（Python 侧本次零改动）
- `pm/decision-tool.ts`、`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`pm/triage-client.ts`
- `spec.md`、`design.md`、`plan.md`、`pm-state.md`、`achieved.md`、`tasks/**`
- `.agenticdoc/**` 下除本节列出的四个测试、两个源码文件、一个文档、一个 CHANGELOG 之外的任何路径
- 禁止 `git` 任何写操作；禁止 `npm run check`（含 `biome check --write .`）；禁止全量 pytest、禁止全量 test.sh
- 禁止用 `Set-Content` 写文件（会经 cp936 往返丢字节），一律用 `edit` / `write` 工具

## 验收命令

```bash
npx tsgo --noEmit
node ../../node_modules/vitest/dist/cli.js --run test/suite/dp3-answer.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/xkey-gate-guard-coverage.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-signoff.test.ts
npx biome check src/extensions/agent-team-loop/worker/worker-mode.ts src/extensions/agent-team-loop/shared/xkey-gate-guard.ts test/suite/dp3-answer.test.ts test/suite/xkey-gate-guard-coverage.test.ts
```

上述四条 vitest 用例数只允许**增加**：`dp3-answer` 现 20、`xkey-gate-guard-coverage` 现 11、
`decision-signoff` 现 11（回归不许掉）。`npx tsgo --noEmit` 必须 rc=0。

## 文档

`docs/decision-substitution.md` 补两行（放在讲 dp3 落行与签收守卫的小节）：

1. dp3 走服务时，子进程未报 `mode` 视为不可用并上抛人，**不回退本地配置**；
2. 签收守卫只认 `evidence/sign-final.md` 与 `evidence/review/sign-final.md` 两个落位，
   `evidence/<其它>/…/sign-final.md` 属于普通产物、可写。

`packages/coding-agent/CHANGELOG.md` 的 `## [Unreleased] / ### Fixed` 追加一行（无 issue 编号，
写成「决策替身：dp3 服务未报 mode 时不再回退本地配置；签收守卫不再误拒深层 evidence 产物」）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待改点 1：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4933`
- 不改点（对照组）：同文件 `:4745`（注释）、`:4863`（3c 本地匹配）、`:3715`、`:3788`
- 待改点 2：`packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:383`
- 契约：`design.md` 的 D-036 / D-041 / D-014 / D-015
- 用例参照：`test/suite/dp3-answer.test.ts:550`（已有「child mode 胜于本地行」用例）、
  `test/suite/decision-signoff.test.ts`（两落位拒绝用例）
- 上一轮证据：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020d.md`

## 上下文纪律

单文件读取一律带 offset / limit，单次 ≤ 200 行；`worker-mode.ts` 有 5000+ 行，只读上面点名的行段。

## 改动历史

- 2026-10-20 建卡：来自 `ds-qg-review-2d` 的两条残留（MAJOR-3 的 mode 回退、MAJOR-4 的深路径误拒），PM 已独立复现。
