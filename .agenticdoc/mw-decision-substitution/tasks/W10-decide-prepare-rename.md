# W10 — `decision` worker 改名 `decide_prepare`（+ role 级模型）

- key: mw-decision-substitution
- type: coding
- 阶段: R2-1（并行波次，与 W9 无文件重叠）
- 上下文: 用户裁定（2026-10-21）：这个角色的职责只有"准备决策本"，不该叫 `decision`（读起来像它会决策）；改名 `decide_prepare`，且要能单独配模型。依据 `.agenticdoc/mw-decision-substitution/spec.md` §15 AC-028 与 `design.md` §9 D-072/D-073。
- 目标锚点: `H:/git/Multi-Workers/.agenticdoc/goal.md`（worker 类型体系按"准备/执行"分工，决策归 jev）

## 上下文

现状（按行号读，禁整文件读）：

- `packages/multi-workers/mw_common.py:143` `DISPATCH_ROLES = ("main","coding","review","research","vision","decision")`；`:144` `TASK_TYPE_TO_ROLE` 里 `"decision": "decision"`；`:260` 用 `DISPATCH_ROLES` 校验 `.mw/dispatch.yml` 的 models 键。
- `packages/multi-workers/autopilot/dispatch.py:89` `REGISTRY`（含 `decision` 条目，工具集 `read/find/grep/ls/bash`）；`:234` `decision_card_fields`；`:270` `decision_card_issues`（判据 `missing-item:*` / `dp-required-state-fields-missing:*` / `book-send-refused`，这些码名**保持不变**）。
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:146` `TOOL_ALLOWLISTS.decision`；同文件固定提示词里有 "decision book" 文案。
- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:224` `DISPATCH_TYPE_VOCABULARY`（含 `"decision"`）与 `TYPE_EXTRA_PATTERNS` 的 `decision` 四项判据。
- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts:58` `DISPATCH_ROLE_BY_TYPE`、`:75` `DISPATCHABLE_TYPES`。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3111`（`dispatch_worker` 的 `type` 描述）与 `:4213`（`/mw model set` 角色表）。两处都由测试解析，必须同步。
- `.mw/dispatch.yml` 现在只有 `coding/main/research/review` 四个 role 模型。

## 要求

1. **改名一次到位**：`decision` → `decide_prepare`，**不留别名**。覆盖：`DISPATCH_ROLES`、`TASK_TYPE_TO_ROLE`、`autopilot/dispatch.py` REGISTRY 键与相关 docstring、`worker-mode.ts` 的工具白名单键与提示词、`dispatch-card.ts` 词表 + `TYPE_EXTRA_PATTERNS` 键、`dispatch-models.ts` 角色映射 + `DISPATCHABLE_TYPES`、`ui-bridge.ts` 两处文案。
2. **判据不变**：卡片仍需 `- dp:` / `- 证据来源:` / `- 分支后果:` / `- allow-send:`；`allow-send: no`（缺省）时 `--book` 被拒；未定义 `required_state_fields` 的 dp 拒派；写面仍收窄到 `<key>/evidence/books/**` 并记 `narrowed_by`。
3. **role 级模型**：`.mw/dispatch.yml` 的 `models` 下新增 `decide_prepare: timi/gpt-6.1-sol`（只读、要准确，用 review 同级模型）。确认 `mw model set decide_prepare <prefix/model>` 可用（走既有 `DISPATCH_ROLES` 校验），且 `dispatch_worker` 的 `model` 覆盖仍然优先（记 `model-reason`）。
4. **测试改名并更新**：`test_dispatch_decision_type.py` → `test_dispatch_decide_prepare.py`（旧文件删除）、`test/suite/worker-decision-type.test.ts` → `test/suite/worker-decide-prepare.test.ts`（旧文件删除）；同步 `test_dispatch_models.py`（角色数与镜像含 `decide_prepare`）、`test_mwpp_collection_parity.py`（快照键）、`test_autopilot_dispatch.py`（期望集合 + `tool_set`）、`test/suite/dispatch-recovery-terminal.test.ts`（若它锁定词表）。
5. **文档**：`packages/multi-workers/README.md` 的 worker 类型表改名；新建 `docs/decide-prepare-worker.md`（≤60 行：定位、工具面、写面、四项判据、`allow-send` 语义、一个真实例子、与 `decision book` 的关系）。
6. **不改** `packages/multi-workers/decision.py`、`decide_signoff.py`、`decision_points.py`、`mw.py`、`advance_phase.py`（W9 的写面）。

## 写入允许面

packages/multi-workers/mw_common.py
packages/multi-workers/autopilot/dispatch.py
packages/multi-workers/test_dispatch_decide_prepare.py
packages/multi-workers/test_dispatch_models.py
packages/multi-workers/test_mwpp_collection_parity.py
packages/multi-workers/test_autopilot_dispatch.py
packages/multi-workers/README.md
packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts
packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts
packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
packages/coding-agent/test/suite/worker-decide-prepare.test.ts
packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts
.mw/dispatch.yml
docs/decide-prepare-worker.md
.agenticdoc/mw-decision-substitution/tasks/W10-decide-prepare-rename.md

## 写入禁止面

- 不改 `packages/multi-workers/{decision.py,decide_signoff.py,decision_points.py,mw.py,decide_registry.json}`（W9 写面）。
- 不改任何 `CHANGELOG.md`、`.agenticdoc/<key>/{pm-state,plan,spec,design}.md`（PM 收口写）。
- 不改 `.agents/skills/agentic-task/**`、`dist/**`。

## 验收命令

```
cd packages/multi-workers && python -m pytest -q test_dispatch_decide_prepare.py test_dispatch_models.py test_mwpp_collection_parity.py test_autopilot_dispatch.py test_autopilot_l0.py
cd packages/multi-workers && python -m autopilot.dispatch check --dp dp3-worker-clarify ; echo rc=$?
cd packages/multi-workers && python mw.py model show --project ../.. 2>&1 | head -30
cd packages/coding-agent && npx vitest --run test/suite/worker-decide-prepare.test.ts test/suite/dispatch-recovery-terminal.test.ts
```

不跑 `tsgo --noEmit`（当前被另一个 live 窗口的半成品文件挡住）、不跑 `npm run check`、不跑 `npm run build`、不联网、不 commit。

## 交付格式

`report.md`（≤60 行）：改名落点清单（文件:行）、`decide_prepare` 模型生效证据、验收命令 returncode、残留与理由。

## 改动历史

- 2026-10-21 建卡（PM，依据 spec §15 AC-028 / design §9）。
