# W11 — 让签收决策点默认开（dp25 P1 → P2）

- key: mw-decision-substitution
- type: coding
- 阶段: R2-1 收尾（与 W9/W10 无并行冲突）
- 上下文: 用户裁定 D 要求"让 decide 模型去签收，默认 auto"。W9 已实现自动签收，但 `dp25-signoff-conclusion` 按注册表铁律登记为 P1，而 `decision_points.py:378` 强制"只有 P2 默认开启"，因此**默认路径实际落到 LLM 推断**（实测 `sign-final.md` 里 `signed_via: auto-llm` + `decide_fallback: dp25-signoff-conclusion disabled`）。本卡把 dp25 改成 P2（默认开、默认 auto），让默认路径真的走 jev。依据 `spec.md` §15 AC-024/AC-027 与 `design.md` §9 D-068/D-071。
- 目标锚点: `H:/git/Multi-Workers/.agenticdoc/goal.md`（人只在事后 review，签收由决策模型完成）

## 上下文

现状（按行号读，禁整文件读）：

- `packages/multi-workers/decision_points.py:378` `__post_init__`：`default_enabled is not (self.tier == "P2")` 抛错 —— P1 一律默认关，这是不可绕的注册表铁律。
- `packages/multi-workers/decision_points.py:398`：`P2 dp requires an executor`（`P2` 必须能自动执行）。
- dp25 当前定义在 `DP_REGISTRY` 末尾（`_point(... tier="P1", questions=(q-conclusion,), executor=None ...)`），`REQUIRED_STATE_FIELDS` 与 `STATE_FIELD_DESCRIPTIONS` 已在 W9 补齐。
- `packages/multi-workers/decide_signoff.py` 的 `auto_conclusion(...)` 已经：判定 `signoff=auto` + `cfg.is_configured` + `dp25` 生效 enabled → 调 `decide_for(..., intent="answer")`。所以只要 dp25 默认开，链路就自动走 jev，无需改这边。
- 现状统计：`Counter({'P0': 10, 'P2': 9, 'P1': 6})`，dp25 在 P1 里。

## 要求

1. **把 `dp25-signoff-conclusion` 改为 `tier="P2"`**，并给它一个**无副作用 executor**：返回字符串 `signoff:<state 里的 conclusion>`（或等价物），**不得写文件、不得联网、不得改配置**；`decide_for(intent="answer")` 不会调用它，只有 `intent="act"` 才会，因此签收的写文件仍由 `mw decide sign` 负责。executor 需要满足 `_validate_registry` 对 P2 的要求（`_executor_kind` 不能是 `none`），并在 docstring 里写清"这不是写入动作，只是把结论回显给调用方"。
2. **注册表产物重生成**：`python mw.py decide dp export --write --project .` 重生成 `packages/multi-workers/decide_registry.json`；跑 `packages/multi-workers/scripts/gen_decide_registry_ts.py` 重生成 `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`。两者都必须零漂移（`--check` rc=0）。
3. **文档**：`docs/decision-points.md` 的 §3 表格由配置渲染，重渲染后 dp25 的 tier 列应为 P2、`已接入` 列按 wired 现状；§9（决策本）里若提到"P1 默认关"的地方补一句"dp25 例外：P2 默认开，签收默认走 jev"。
4. **测试**：更新受影响的 tier 断言（`test_decision_points.py`、`test_decide_registry_contract.py`、`test_decide_registry_export.py`、`test_decide_sign_auto.py`、`test_decide_dp_cli.py` 里凡写死 P1/P2 计数或 dp25 tier 的地方，改成从注册表派生或改期望值）；新增用例：dp25 默认 `enabled=true`、`executor` 存在且 `intent="answer"` 下不被调用（用 `FakeBackend` + 计数或 `unwired` 探针）、`intent="act"` 时 executor 返回 `signoff:<conclusion>` 且无写文件。
5. **不改** `mw.py` 的自动签收流程（W9 已完成），不改 `decision.py`，不改 `advance_phase.py`，不改任何 `CHANGELOG.md`。

## 写入允许面

packages/multi-workers/decision_points.py
packages/multi-workers/decide_registry.json
packages/multi-workers/test_decision_points.py
packages/multi-workers/test_decide_registry_contract.py
packages/multi-workers/test_decide_registry_export.py
packages/multi-workers/test_decide_sign_auto.py
packages/multi-workers/test_decide_dp_cli.py
packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts
docs/decision-points.md
.agenticdoc/mw-decision-substitution/tasks/W11-signoff-dp-p2.md

## 写入禁止面

- 不改 `packages/multi-workers/{mw.py,decision.py,decide_signoff.py,decision_book.py,decision_context.py}`。
- 不改 `packages/coding-agent/src/extensions/agent-team-loop/**` 下其它文件（只允许那个 `.generated.ts`）。
- 不改 `.mw/decide-points.json`（授权表机器零写）、不改 `.mw/decide.json`、不改 CHANGELOG/相位文档。
- 不把 dp25 的判据（continue 需 N>=1 + 链闭合 + 真 jev）改松。

## 验收命令

```
cd packages/multi-workers && python -m pytest -q test_decision_points.py test_decide_registry_contract.py test_decide_registry_export.py test_decide_sign_auto.py test_decide_dp_cli.py test_decide_signoff.py
cd packages/multi-workers && python mw.py decide dp check --project . ; echo rc=$?
cd packages/multi-workers && python mw.py decide dp show --project . dp25-signoff-conclusion
cd packages/multi-workers && python scripts/gen_decide_registry_ts.py --check ; echo rc=$?
```

不跑 `tsgo --noEmit`、不跑 `npm run check`、不跑 `npm run build`、不联网、不 commit。

## 交付格式

`report.md`（≤50 行）：改动清单（文件:行）、五条验收命令的 returncode、dp25 的 tier/enabled/executor 实测输出、残留与理由。

## 改动历史

- 2026-10-21 建卡（PM，依据实测：默认路径落到 auto-llm）。
