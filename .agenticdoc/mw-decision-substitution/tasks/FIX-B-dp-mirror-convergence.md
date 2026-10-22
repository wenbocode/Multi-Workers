# FIX-B：两处 TS 配置表镜像收敛（QG MAJOR-3）

- type: coding
- owner key: mw-decision-substitution
- 来源：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md` §B major 第 3 条

## 上下文

D-036「唯配置论」要求 `.mw/decide-points.json` 是**唯一**授权权威，TS 只消费 Python 回传的 `mode/acted/decision_id`。QG 复审在 TS 侧数出 4 处读表判 `enabled/mode`：`decision_points.py:1085`（权威）+ `pm/decision-tool.ts:236`（FIX-A 已覆盖）+ **`pm/pm-orchestrator.ts:2044`** + **`worker/worker-mode.ts:4468`**（本卡）。

除"字面违反"之外，还有实测的**语义分歧**（这才是风险点）：

| 场景 | Python（权威） | TS 现状 |
|---|---|---|
| 非对象行（L2） | 强制该 dp **off**（`decision_points.py:884-968`） | `recordOf(row) === undefined` → 回落注册表默认（dp2/dp3 均 P2 **on**） |
| 坏 `note`（L3） | **force-off** | 完全不读 `note`，仍 enabled |

后果：当前因为 TS 放行后 Python 仍会拒（`unavailable` → 回退原告警/原问人），所以**不 fail-open**；但两处独立实现意味着 Python 侧任何降级语义调整都不会传播，且行损坏时会白付一次子进程。

另有一条：`decideDp2Checkpoint` 的 `acted` 判定用本地 `authorization.mode` 而不是子进程回传的 `payload.mode`（`pm-orchestrator.ts:2317`）——这正是 D-041 禁止的"由 mode 反推 acted"的邻居问题：acted 应来自消费点，mode 应来自 Python。

## 要求

1. **`pm-orchestrator.ts:2044-2063`**：
   - 非对象行改为回落 **disabled**（与 Python L2 对齐），不要回落注册表默认。
   - 补 `note` 的 L3 判定（坏 note → disabled），与 `decision_points.py:884-968` 的 `force_off` 语义一致；若 L3 的具体判定规则在 Python 侧是函数级的，把规则抄成**一个**小函数并注明"镜像 `decision_points.py:<行号>`，分歧以 Python 为准"。
   - `decideDp2Checkpoint` 的 `acted` 不再用本地 `authorization.mode`（`:2317`）：改为消费子进程回传的 `payload.mode`；本地读表只保留 `enabled` 作为"是否 spawn"的短路，并在函数注释里写明"非权威、仅短路"。
2. **`worker/worker-mode.ts:4468-4490`**（`readDp3Policy`）：同上三条（非对象行 → off、补 L3、注释声明"非权威、仅短路、分歧以 Python 为准"）。
3. **注释即契约**：两处镜像都要有一段明确注释：`enabled/note` 的预读**只用于避免白付子进程**，授权判定权威在 Python `decide_for`；两者不一致时以 Python 为准。这是 QG 报告给出的一条可接受收口方式（另一条是彻底删掉镜像，若你能在不新增跨进程开销的前提下做到，优先彻底删）。
4. **测试**：
   - `dp2-narrow.test.ts` 增：非对象行（如 `"dp2-dispatch-narrow": "yes"`）→ 不 spawn、`mode` 视为 off。
   - `dp3-answer.test.ts` 增：坏 `note` → 不 spawn。
   - 两套既有用例必须继续全绿（现有 30 + 13 例）。
5. 不得引入 `any`；只准用可擦除 TS 语法；模块内联单调用点小函数。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 权威实现：`packages/multi-workers/decision_points.py:884`（L2/L3 `force_off` 语义，含非对象行与坏 note）
- 待修：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:2044`（`readDp2Authorization`）、`:2317`（acted 由本地 mode 反推）
- 待修：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4468`（`readDp3Policy`）

## 交付格式

- 三处（orchestrator、dp2 acted、worker-mode）的 `path:line` 改前/改后对照。
- 与 Python 对照表：每条 L2/L3 规则 → Python 锚点行号 + TS 新实现行号。
- 测试计数行（`dp2-narrow.test.ts`、`dp3-answer.test.ts`）+ `tsgo --noEmit` rc。
- 若判定"彻底删镜像"可行，说明零 spawn 短路如何保留（或为何可丢）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/dp2-narrow.test.ts`
- `packages/coding-agent/test/suite/dp3-answer.test.ts`

## 写入禁止面

- 其它任何 `src/**`、`test/**`（尤其 `pm/decision-tool.ts`、`shared/xkey-gate-guard.ts`、`shared/heartbeat.ts`：并行 worker 与本 PM 正在改）
- `packages/multi-workers/**`（Python 权威，只读对照）
- `docs/**`、`CHANGELOG`、`.agenticdoc/**`（除 `workers/fix-qg-major3/**` 自身运行目录）
- 禁止 `git` 任何写操作；禁止 `npm run check` / `biome --write`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/dp2-narrow.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dp3-answer.test.ts
npx tsgo --noEmit -p tsconfig.json
npx biome check src/extensions/agent-team-loop/pm/pm-orchestrator.ts src/extensions/agent-team-loop/worker/worker-mode.ts test/suite/dp2-narrow.test.ts test/suite/dp3-answer.test.ts
```

全绿且 `tsgo` rc=0 才算完成；红就停下报告，不要放宽断言。

## 改动历史

- 2026-10-20 建卡：来源 QG MAJOR-3（`pm-orchestrator.ts:2044` + `worker-mode.ts:4468` 镜像与 Python L2/L3 语义分歧；`:2317` mode 反推 acted）。
