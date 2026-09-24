# T-1 跨 key 分化升级投递（D-101/D-102/D-103）

- 波次: W1（唯一实现任务）
- 执行者: worker `mwcre-t1-crosskey-escalation`（type: coding）
- 依赖: 无
- 上游: `spec.md` AC-001~004、`design.md` D-101~D-104 / VC-001~004、`evidence/research/*-2026-09-23.md`

## 1. 目标

`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` 的分化升级循环（`startWorkerPollLoop`，约 `:564-578`）当前只升级 watched key 自身的 running worker：

```ts
if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
```

改为"watched key **或** 本窗口派发过"（D-101），并仅在异地时给 alert 附加 owner key（D-102）。

## 2. 必须满足的契约

1. **D-101 过滤放宽**：
   ```ts
   const ownerKey = ownerKeyOf(entry, agenticdocRoot);
   const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;
   if (!watch.key || (ownerKey !== watch.key && !owned)) continue;
   ```
   - `!watch.key` 短路保留（未 watch 的窗口不投递）。
   - `owned` 必须显式布尔化（`?? false`）。
   - 不得删除 `ownerKeyOf` 调用（它是"或"的一支，见 design F2）。
   - 不新增导出、不新增集合（复用既有 `escalated`，D-103）。
2. **D-102 文案**：`ownerKey !== watch.key` 时，在 worker 名之后插入 `（owner key=${ownerKey}）`；watched key 自身路径下文本**逐字不变**：
   - 现状首句：`` `[mw] 发散风险：worker '${entry.taskKey}' 检查点 risk=${ck.risk}` ``
   - 异地首句：`` `[mw] 发散风险：worker '${entry.taskKey}'（owner key=${ownerKey}）检查点 risk=${ck.risk}` ``
3. **D-103 不变项**：`escalated.has` / `escalated.add`、`if (!ck || ck.risk === "low") continue`、`deliverPmAlert` 调用与 `triggerTurn` 一律不动。
4. **既有用例零改动**：`test/extensions/agent-team-loop.test.ts` 中两个 `AC-004` 用例（watched key 升级 / 别键静默）**只能保持原样**（含 `agent-team-loop-watch-aggregate.test.ts` 也零改动）。

## 3. 新增用例（TDD：先红后绿）

在 `test/extensions/agent-team-loop.test.ts` 的同一 describe（monitor/AC-004 所在区）**追加** 3 个用例，复用既有 `fakePi()` / `queueRunning()` / `mkdtemp()`：

| 用例 | 构造 | 断言 |
|------|------|------|
| VC-001（AC-001） | `queueRunning(root, "key-b", "t-cross")`；`key-b/workers/t-cross/trace.log` 含 `[CHECKPOINT] … risk=high`；`const watch: PmWatchState = { key: "key-a", dispatchedTaskKeys: new Set(["t-cross"]) }`；fake timers → tick | `messages` 恰 1 条；含 `t-cross`、`key-b`、`risk=high`、`trace.log`、`progress.md`；`options[0]?.triggerTurn === true`；第二 tick 仍 1 条 |
| VC-002（AC-002） | 同夹具，但 `watch = { key: "key-a" }`（`dispatchedTaskKeys` 未定义）**与** `dispatchedTaskKeys: new Set()` 两种形态 | 两种形态均 `messages.length === 0` |
| VC-003（AC-003） | 两个跨 key 已派发 task：`t-low`（`risk=low`）、`t-high`（`risk=high`）；`dispatchedTaskKeys` 含两者 | 恰 1 条（`t-high`）；第二 tick 仍 1 条（`t-low` 从不投递） |

证据行（stdout 实测插值，必须出现在 output.md）：

```
[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0
[VERIFY] VC-002: undefined_alerts=0 empty_set_alerts=0
[VERIFY] VC-003: low_alerts=0 high_alerts=1 dup=0
[VERIFY] VC-004: watched_key_alerts=1 existing_cases_untouched=true
```

（VC-004 的取值来自既有 2 个 AC-004 用例通过 + `git diff` 显示它们零改动。）

## 4. 验收命令

1. `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts` → 期望 **0 failed**（并报告 passed 计数）。
2. `cd H:/git/Multi-Workers && npm run check` → **EXIT=0**。
3. `git diff --stat` + `git diff packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`：确认改动仅上述两处（条件 + 文案），无范围外文件。

## 5. 范围（禁止事项）

- 不改：`pm/ui-bridge.ts`、`shared/**`、`test/extensions/agent-team-loop-watch-aggregate.test.ts`、既有 2 个 AC-004 用例本体、`dist/**`、任何 Python、`CHANGELOG.md`（PM 直执 T-2）。
- 不改 risk 判据（`readTaskProgress` / 阈值 / 30 分钟锚点），不做全局广播（D-104 已否决）。
- 不 commit、不跑 `mw build`。

## 6. 交付

- 代码 + 3 个新用例；
- `output.md` 含：改动 hunk 摘要、3 个新用例的原始 `[VERIFY]` 行、验收命令输出与 pass/fail 计数、`git status --short` 结果、偏离说明（如有）。
