# W9 — 签收交给决策模型（`signoff: auto|disable` + `dp25-signoff-conclusion`）

- key: mw-decision-substitution
- type: coding
- 阶段: R2-1（并行波次，与 W10 无文件重叠）
- 上下文: 用户裁定 D（2026-10-21）。原设计把 `evidence/review/sign-final.md` 作为人在 agent 会话外的强制签收，`done` 门禁依赖它，导致 PM 无法自行收尾。新语义：签收由 **decide 模型**决定（jev），decide 不可用时由 agent 的 LLM 推断；人可以用 `mw decide sign --auto|--disable` 控制，缺省 `auto`，`disable` 表示永不走签收流程、`done` 不阻塞。依据 `.agenticdoc/mw-decision-substitution/spec.md` §15 AC-023..027 与 `design.md` §9 D-064..D-071。
- 目标锚点: `H:/git/Multi-Workers/.agenticdoc/goal.md`（"jev 替换中低风险人工决策"；签收是最后一个仍在人手里的高频步骤）

## 上下文

现状（必须按行号读，禁整文件读）：

- `packages/multi-workers/decision.py:332` `DecisionConfig`：配置字段与 `from_dict` 校验都在这里；新增 `signoff` 从这里进。
- `packages/multi-workers/decide_signoff.py:505` `write_signoff(...)`：现在**无条件拒绝 agent 会话**（`AGENT_SESSION_ENV_VARS`）。自动签收必须能在此写入，人签拒绝保持。
- `packages/multi-workers/decide_signoff.py:257` `collect(...)`：签收事实来源（rows/链/可用数/P0/engine），`verdict(...)` 在 `:305`。
- `packages/multi-workers/mw.py:3657` `_decide_sign(...)`：`--conclusion` 缺省时是只读预览；要改成"缺省 = 走自动流程"，并新增 `--auto` / `--disable` 两个模式持久化开关。
- `packages/multi-workers/decision_points.py:476` `DP_REGISTRY`（24 项）、`:120` `EXPECTED_DP_COUNT = 24`、`:1070` `REQUIRED_STATE_FIELDS`、`:1128` `STATE_FIELD_DESCRIPTIONS`、`:402` `_state_builder`。
- `packages/multi-workers/decision_points.py:2191` `decide_for(...)`：11 步判定，`intent="answer"` 分支只归档建议不执行（签收要用这个意图）。
- `.agents/skills/agentic-task/core/scripts/advance_phase.py:255` `_decision_signoff_problems(...)`：`done` 门禁的签收检查，要加 disable 豁免。
- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:333` `DECISION_SIGNOFF_BASENAME` 与 `:352` 附近的拒绝文案：现在写"human answer channel"，需要与新语义一致，且不能拦住 `mw decide sign` 这条 CLI（仍必须拦住裸写文件）。

## 要求

1. **配置字段**：`DecisionConfig` 增 `signoff: str = "auto"`，`from_dict` 接受 `auto` / `disable`；非法值**不进** `errors`（不得让 24 个 dp 掉线），改为设 `cfg.signoff_error`、`signoff` 保持 `auto`。`signoff` 出现在 `mw decide show --json` 的输出里。
2. **模式持久化**：`mw decide sign --auto` / `--disable` 走既有 `_decide_write_config`（原子写 + 校验）把 `signoff` 写入 `.mw/decide.json`，打印结果后 exit 0；`--dry-run` 时只打印不写。
3. **自动流程**（`mw decide sign` 无 `--conclusion` 时）：
   - `signoff=disable` → 打印"signoff disabled"，不写文件，exit 0。
   - `signoff=auto` 且 decide 可用（`DecisionConfig.is_configured`）且 `dp25-signoff-conclusion` enabled → 调 `dp25` 拿结论，写 `signed_via: auto-decide`。
   - 否则 → 若给了 `--conclusion` 视为 LLM 推断，写 `signed_via: auto-llm`；没给则只打印预览 + 指引（exit 0，不写文件）。
   - jev 不可用或置信低于该 dp 生效 `min_confidence` → 回落 LLM 路径，并在 `sign-final.md` 记一行 `decide_fallback: <reason>`。
   - `--conclusion` 显式传入且**没有** `--auto`/`--disable` 时，保持旧语义（人签 `signed_via: cli`，agent 会话仍拒绝），仅在 TUI `--human-confirmed` 时 `signed_via: tui`。
4. **新增决策点 `dp25-signoff-conclusion`**：P1、`default_mode="auto"`、executor `unwired`（写文件由 sign 命令做），`REQUIRED_STATE_FIELDS` = `("key","rows_total","rows_available","chain_ok","p0_open")`，可选 `escalated_reasons` / `engine_violations`；`STATE_FIELD_DESCRIPTIONS` 补全；question `q-conclusion`（`choice`，choices `continue|narrow|revoke`，labels 必填）；`instructions` 写明判据（continue 需 N>=1 + 链闭合 + 每行 `timi-decisions/jev-latest/api`；narrow 用于降级；revoke 用于链断或 engine 不符）。`EXPECTED_DP_COUNT` 改 25。
5. **签收事实 → state**：新增函数（放 `decide_signoff.py`）把 `collect()` 的事实组装成 dp25 的 state（不读 diff、不读代码），调用 `decide_for(..., intent="answer")`，返回 `(conclusion, detail)`；不可用/低置信返回 `(None, reason)`。
6. **`decide_signoff.write_signoff`**：新增参数允许自动签收路径（例如 `allow_agent_session: bool = False`），`signed_via in {"auto-decide","auto-llm"}` 时允许；其它值维持现有拒绝。`render(...)` 支持新增的 `signed_via` 值与 `decide_fallback` 行（机器行格式要与 `parse_signoff` 一致）。
7. **`done` 门禁豁免**：`_decision_signoff_problems` 先读项目根 `.mw/decide.json`（`key_dir.parent.parent`），`signoff == "disable"` 时返回 `[]` 并让 `check_gate` 打印一条 note（若现有结构不便输出 note，至少返回 `[]`，并写一条 `[VERIFY]`/注释说明）。
8. **guard**：`xkey-gate-guard.ts` 的拒绝文案改成与新语义一致；确认 `mw decide sign --project ...` 这条命令在 agent 会话内不被判为写构造（若被拦，放行"CLI 动词 `mw decide sign`"，仍拦 `Set-Content`/重定向/`mw decide dp apply`）。
9. **产物与文档**：`python mw.py decide dp export --write --project .` 重生成 `decide_registry.json`；跑 `packages/multi-workers/scripts/gen_decide_registry_ts.py` 重生成 `shared/decide-registry.generated.ts`；更新 `docs/decision-points.md` 的 dp 表到 25 项（表格可由配置渲染，勿手写死数字）。
10. **测试**：新增 `test_decide_sign_auto.py`（≥12 例：四模式分支、disable 门禁豁免、agent 会话允许、低置信回落、`dp25` 不在注册表/不可用、`signed_via` 回显、`signoff_error` 拒绝）；扩 `test_decide_signoff.py`；更新 `test_decision_points.py`、`test_decide_registry_contract.py`、`test_decide_registry_export.py` 的 24 → 25；`test_decide_cli.py` 补 `sign --auto/--disable`。

## 写入允许面

packages/multi-workers/decision.py
packages/multi-workers/decide_signoff.py
packages/multi-workers/decision_points.py
packages/multi-workers/decide_registry.json
packages/multi-workers/mw.py
packages/multi-workers/test_decide_sign_auto.py
packages/multi-workers/test_decide_signoff.py
packages/multi-workers/test_decision_points.py
packages/multi-workers/test_decide_registry_contract.py
packages/multi-workers/test_decide_registry_export.py
packages/multi-workers/test_decide_cli.py
packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts
packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts
docs/decision-points.md
.agents/skills/agentic-task/core/scripts/advance_phase.py
.agenticdoc/mw-decision-substitution/tasks/W9-sign-auto.md

## 写入禁止面

- 不改 `packages/multi-workers/mw_common.py`、`autopilot/dispatch.py`、`worker/worker-mode.ts`、`shared/dispatch-card.ts`、`shared/dispatch-models.ts`、`pm/ui-bridge.ts`（W10 的写面）。
- 不改任何 `CHANGELOG.md`、`pm-state.md`、`plan.md`、`spec.md`、`design.md`（PM 收口写）。
- 不删除/降级既有测试；不把 `done` 门禁整个摘掉。

## 验收命令

```
cd packages/multi-workers && python -m pytest -q test_decide_sign_auto.py test_decide_signoff.py test_decision_points.py test_decide_registry_contract.py test_decide_registry_export.py test_decide_cli.py
cd packages/multi-workers && python mw.py decide dp check --project . ; echo rc=$?
cd packages/multi-workers && python mw.py decide dp show --project . --dp dp25-signoff-conclusion
cd packages/coding-agent && npx vitest --run test/suite/xkey-gate-guard.test.ts
```

不跑 `tsgo --noEmit`（当前被另一个 live 窗口的半成品文件挡住）、不跑 `npm run check`、不跑 `npm run build`、不联网、不 commit。

## 交付格式

`report.md`（≤60 行）：改动清单（文件:行）、四个模式的实测输出片段、验收命令的 returncode、残留与理由。

## 改动历史

- 2026-10-21 建卡（PM，依据 spec §15 / design §9）。
