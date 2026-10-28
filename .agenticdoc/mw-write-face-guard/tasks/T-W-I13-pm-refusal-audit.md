# T-W-I13 · PM 侧拒绝审计 + 计数诚实（AC-003 收口）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 派发闸门拒绝一个任务时，"拒绝"这件事必须**留下痕迹**并且**不能把没派出去的当作派出去了**。今天 PM 侧两条都不成立。
- **本卡要修的缺口（PM 复核实测）**：
  1. **PM 通道拒绝零持久审计**：`spec.md` AC-003 要求"未声明写面 ⇒ fail-closed 处置**并写审计行**"。conductor 侧有 `_write_face_audit` → `.autopilot/timeline.jsonl`（`dispatch.py:1089/1164/1183/1230`）；PM 侧（W-08 交付的 `pm/task-dispatcher.ts`）虽然把拒绝做成返回值，但**没有调用方消费它** ⇒ 拒绝不留任何记录。
  2. **计数不诚实**：`pm/pm-orchestrator.ts:1243` 的 `await dispatchTask(...)` 之后**无条件** `queued += 1`（`:1254`）。`dispatchTask` 现在是 `Promise<DispatchOutcome>`，**拒绝不抛异常**，于是被拒的任务会被计入"已派发"，进而可能触发 `dispatch-quota` 告警与前端计数失真（`onAlarm?.({ kind: "dispatch-quota", count: queued })` 就在上面几行）。
- **已有可用载体（不要新建写者）**: `pm/pm-orchestrator.ts:556` 的 `recordDispatchAlarm(agenticdocRoot, alarm)` 已经把机器可读审计行追加到 `.agenticdoc/_autopilot/auto-decisions.jsonl`（`phase: "dispatch-alarm"`，1-based `seq`，注释明示"对决策消费者不可见、对人/`mw doctor`/后续消费者可见"，且**best-effort 不破派发**）。PM 侧拒绝审计就落这里，与 D-008"PM 侧审计出口 = 派发返回值"一致：返回值仍是对外契约，调用方负责把它变成持久行。
- **定位锚点**: `pm/pm-orchestrator.ts:1243`（`dispatchNewTasks` 的派发调用）、`:1254`（无条件 `queued += 1`）、`:925`（另一处 `await dispatchTask(...)`，孤儿/内部派发路径，同样未看返回值）、`:556`（`recordDispatchAlarm`）、`:264`（`ctx.ui.notify(cfg.audit.join("\n"), "warning")` 的人可见面先例）、`pm/task-dispatcher.ts:346`（`DispatchRefusalCode`）、`:369`（`DispatchOutcome` 形状：`code` / `overlapWith` / `sample` / `serialOnly` / `inFlight` / `reason` / `detail`）。
- **裁定与 AC**: `spec.md` AC-003（拒绝须写审计行）、AC-008；`design.md` D-008（拒绝形状与审计出口）、D-014/D-115 家族。
- **测试锚点**: `packages/coding-agent/test/suite/write-face-pm-gate.test.ts`（W-08/W-09 交付，当前 19 passed，含"拒绝零副作用"的目录/队列快照 diff 断言）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/test/suite/write-face-pm-gate.test.ts`

## 写入禁止面

其余一切路径。特别地：`pm/task-dispatcher.ts`、`pm/ui-bridge.ts`、`shared/**`、`worker/**`、`packages/multi-workers/**` 全部只读（本卡只做调用方消费，不改判定与渲染）。**禁止 `npm run check`**（P-017）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **消费 `DispatchOutcome`**：`pm-orchestrator.ts:1243` 与 `:925` 两处派发调用都要看返回值——被拒时**不得** `queued += 1`（`:1254`），并记录一条 PM 侧审计行。
2. **审计行复用既有通道**：用 `recordDispatchAlarm` 家族（`auto-decisions.jsonl`）落一行，`kind` 取新的稳定串（如 `write-face-refusal`），`detail` 至少含 `code` / `overlap-with:<task_key>` / 冲突样例路径（有则含），与 conductor 侧的字段语义一致；**best-effort**：审计写失败不得中断派发（沿用该函数既有语义）。若需要扩展 `DispatchAlarm.kind` 联合类型，做**加法**扩展，不要改既有 kind 的语义。
3. **不要吞掉别的拒绝原因**：非写面类的 `DispatchOutcome`（若将来有其它 code）同样不应计入 `queued`；实现要对"`ok !== true`"统一处理，不要只 `=== "write-face-overlap"` 硬编码一个 code。
4. **人可见面**：沿用既有 `ui.notify` 风格给一条简短可见提示（拒绝即提示），但**不要**把提示当审计（审计以第 2 条的持久行为准）。
5. **测试**（写进 `test/suite/write-face-pm-gate.test.ts`，不得放宽既有 19 条）：
   - 被拒任务：`auto-decisions.jsonl` 恰好新增 1 行，`phase`/`kind`/`detail` 字段可断言；队列**无**该行（沿用既有快照 diff 手法）；扫描返回的 `queued` 计数**不含**被拒任务。
   - 成功派发：`queued` 计数**含**它，且**不**产生 `write-face-refusal` 行（避免噪声）。
   - 两条派发路径（`:1243` 与 `:925`）各覆盖一次。
6. `git diff --stat` 收尾时只应出现允许面两个文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：`auto-decisions.jsonl` 新增行的逐字节原文、被拒/成功两种情形下的 `queued` 计数、`write-face-pm-gate` 套件条数（基线 19）、以及两条派发路径各自的判定输出。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts` 的形态检查，**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-pm-gate.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t23-cutover-recheck.test.ts test/suite/dispatch-recovery-terminal.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/pm packages/coding-agent/test/suite
```

（`autopilot-read-scope` / `worker-file-tool` 等既有红与本卡无关；遇到报基线，不要修。）

## 改动历史

- 2026-10-14 W-08 交付 PM 侧派发闸（`dispatchTask` 返回 `DispatchOutcome`），其 §残留 2 自报"`pm-orchestrator.ts` 忽略返回值、被拒仍 `queued += 1`"；PM 随后裁定 AC-003 在 PM 通道未成立（`plan.md` §7.3 / `design.md` 未决项）。
- 2026-10-14 PM 复核：PM 侧已有 `recordDispatchAlarm` → `auto-decisions.jsonl`（`:556`），故本卡不需要新建 timeline 写者；方案 (a)（消费返回值）即可闭合 AC-003，且顺带修掉计数不诚实。
- **热文件告警**：`pm/pm-orchestrator.ts` 是跨 key 关注文件（另一窗口 key `mw-worker-output-contract` 的读回投递话题可能落到它）。PM 派发前实测：`git status` 干净、mtime 2026-10-13 21:01、无活跃写者。**开工后若发现该文件被第三方改动，立刻停下并在 `残留与未验证` 报告，不要覆盖别人的行。**

## 硬约束

- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 不改判定/渲染逻辑（`task-dispatcher.ts` / `ui-bridge.ts` 只读）；只做调用方消费与审计落行。
- 审计失败不得中断派发；被拒不得计入 `queued`。
- 既有 19 条断言只许加不许放。
