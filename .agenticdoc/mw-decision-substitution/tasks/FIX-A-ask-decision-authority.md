# FIX-A：回收 `ask_decision` 的授权镜像与伪 `decision_id`/`acted`（QG MAJOR-1 + MAJOR-2）

- type: coding
- owner key: mw-decision-substitution
- 来源：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md` §B major 第 1、2 条

## 上下文

QG 复审判定 PASS-WITH-FINDINGS，其中两条 major 落在同一个文件 `pm/decision-tool.ts`，必须收尾前修掉。

**MAJOR-1（D-036 单一权威 / D-041 acted 是消费侧事实）**
`readDecisionAuthorization`（`pm/decision-tool.ts:236`）自己读 `.mw/decide-points.json`、并用 `ASK_DECISION_DP_TIERS` 镜像注册表 tier，推导 `enabled/mode`；`runAskDecision`（`:570`）成功 payload 的 `decision_id` 是 TS 拼的 `` `${dp}:${trigger}` ``，`acted = authorization.mode === "auto"`。两处都是 D-036/D-041 明令禁止的：
- 单一权威：只有 `.mw/decide-points.json` + Python `decide_for` 能判 `enabled/mode`；TS 不得镜像。
- `acted` 是**消费侧事实**（执行门控动作的那个点声明），不得由 `mode` 反推。
- `mw.py:872` 的 `_decide_run_payload` 已经四键齐备（`decision_id/mode/acted/escalated_reason`），工具应当原样透传。
- 后果：Python 侧 `decision_id` 由 state 的 `task_key`/`key` 解析（`decision_points.py:150-161` `resolved_id`），工具 state 只带 owner key → 档案行 id 恒为 `<dp>:<owner-key>`，与工具报给 LLM 的 `<dp>:<trigger>` 不一致；同 key 第二次 ask 触发 `duplicate-replay`。且 `acted:true` 会让模型把"已授权"当事实。

**MAJOR-2（测试绿但生产不可达）**
`buildDecisionState`（`:292` 区域）对所有 dp 只产 `{v, dp, key, task_key, task_summary}`。`decide_for` 步 5 对 dp1/dp2/dp3 校验 `REQUIRED_STATE_FIELDS`（`decision_points.py:626-677`，dp3 需 12 项），缺 7-9 项 → 生产恒 `input-incomplete`；CLI 把它映射成 legacy reason `bad-response`（`mw.py:846-866` `_DECIDE_RUN_REASON_MAP`），工具只透传 legacy reason、丢掉 `escalated_reason` → 模型看到"服务坏响应"而不是"输入契约不满足"。而 `decision-tool.test.ts:210` 的 stub runner 直接返回 `available:true`，所以测试全绿。

## 要求

1. **删镜像**：移除 `readDecisionAuthorization` 与 `ASK_DECISION_DP_TIERS` 的一切使用（无其它调用点时整段删除），工具不再读 `.mw/decide-points.json`，也不再自行推导 `enabled/mode/acted`。
2. **四键透传**：`runAskDecision` 的成功 payload 直接消费子进程 `mw decide run` 返回的 `decision_id`、`mode`、`acted`、`escalated_reason`，不做重写、不自行拼 id。
3. **`acted` 归位**：工具 payload 不再自造 `acted`。若现行工具返回结构要求该字段，则以子进程 `acted` 为准（Python 在 `intent="answer"` 路径落 `acted=false` advisory 行，见 D-035）。
4. **按 dp 构造 state**：`buildDecisionState` 按 dp 产出该 dp 的必填字段集。可复用 `pm/triage-client.ts` 的 `REQUIRED_FIELDS_BY_DP` / `prepareStructuredState` 既有机制（**只复用，不复制**）；调用点拿不到的字段，工具应返回结构化的"缺哪些字段"而不是发一个注定被拒的 state。
5. **透传 `escalated_reason`**：`unavailable` 分支把子进程的 `escalated_reason`（7 值词表，`decision_points.py:88`）原样带给调用者；legacy reason 仅作兼容展示。语义对齐 D-021 / `_DECIDE_RUN_REASON_MAP`。
6. **修注释与测试**：模块头注释 `:28-40` 那段"`mw decide run` 直调 `DecisionClient`、不读表、不返回 mode/acted/decision_id"对现行代码是过时假命题，按实际行为重写。`decision-tool.test.ts:210` 那条"derives mode/acted from the table"的用例必须改成钉住**新契约**（四键透传 + 不在工具侧读表），不得保留把 D-036 违约当绿灯的断言。
7. 不得引入 `any`；只准用可擦除 TS 语法；不得新增 inline import。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 权威实现：`packages/multi-workers/decision_points.py:626`（`REQUIRED_STATE_FIELDS` 仅 dp1/dp2/dp3 有键）、`packages/multi-workers/decision_points.py:1085`（`load_points_config` 唯一权威读表）、`packages/multi-workers/mw.py:872`（`_decide_run_payload` 四键齐备）
- 待修：`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:236`（`readDecisionAuthorization`）、`:292`（`buildDecisionState`）、`:570`（`runAskDecision`）
- 反面样本测试：`packages/coding-agent/test/suite/decision-tool.test.ts:210`

## 交付格式

- 改动摘要：每条要求对应 `path:line`（改前 → 改后一句话）。
- 契约证据：一条命令级证据证明工具不再读 `.mw/decide-points.json`（如 `grep` 结果或测试里对该文件的写入后断言 payload 不变）。
- 测试结果：`decision-tool.test.ts` 原始计数行（`Tests  N passed`），以及 `triage-client-state` / `decision-association` 两套件的计数行（它们消费同一契约，必须一起绿）。
- 若发现某条要求在现有结构下无法完成（例如工具返回结构被下游写死），写清冲突点与最小可行替代，不要硬改下游。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`
- `packages/coding-agent/test/suite/decision-tool.test.ts`

## 写入禁止面

- 其它任何 `src/**`、`test/**` 文件（尤其 `pm/triage-client.ts`、`pm/pm-orchestrator.ts`、`worker/worker-mode.ts`：并行 worker 正在改）
- `packages/multi-workers/**`（Python 侧权威，本卡只消费其输出）
- `docs/**`、`CHANGELOG`、`.agenticdoc/**`（除 `workers/fix-qg-major12/**` 自身运行目录）
- 禁止 `git` 任何写操作；禁止 `npm run check` / `biome --write`（会改写其它会话在途文件）

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-tool.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-client-state.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-association.test.ts
npx tsgo --noEmit -p tsconfig.json
npx biome check src/extensions/agent-team-loop/pm/decision-tool.ts test/suite/decision-tool.test.ts
```

全绿且 `tsgo` rc=0 才算完成；任一条红就停下报告，不要放宽断言。

## 改动历史

- 2026-10-20 建卡：来源 QG MAJOR-1（`decision-tool.ts:236/570` 镜像 + 伪 id/acted）+ MAJOR-2（`buildDecisionState` 恒 input-incomplete 且 `escalated_reason` 丢失）。
