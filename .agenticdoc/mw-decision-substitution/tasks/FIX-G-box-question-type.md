# FIX-G：决策服务无法回答 `box` 类型问题 —— dp3（旗舰路径）恒不可用

- type: coding
- owner key: mw-decision-substitution
- 来源：PM 实测（不是推断）——见「实证」节

## 实证

`H:\tmp\mwds-jev` 里打开决策服务后，用真实注册表问题跑两次：

```
dp1-dispatch-type   available=true  transport=llm-transitional model=glm-5.3-flashx
                    attempts=1 latency_ms=5144 answers={"triage_type":{"value":"coding",...},
                    "triage_risk":{"value":"mid",...}}        ← 正常作答
dp3-worker-clarify  available=false reason=unsupported-question-type  answers=null
```

根因在 `packages/multi-workers/decision_backends.py`：

- `ANSWERABLE_TYPES = ("choice", "score", "noul")`（`:101`）；
- `_unsupported_types()`（`:375`）以它为闸，B2（`:628`）与 B3（`:848`）都走这条闸；
- 注册表里 `dp3-worker-clarify` 的第二个问题是 `{"id": "clarifying_answer", "type": "box"}`
  （`decision_points.py:370`），`dp8-scope-change` 的 `scope_rationale` 也是 `box`（`:423`）；
- `_b2_input_schema()`（`:352`）与 `_validate_answers()`（`:390`）同样只认三种类型。

后果：**dp3 的 3a 分支在生产里永远拿不到答案**（`decideDp3WorkerClarify` 会把它归一成
`escalate("unavailable", "3a", "unsupported-question-type")` 并上抛人），21 个 dp3 用例全绿是因为它们
stub 了 runner。同理 `ask_decision` 对 dp3 之外的 `box` 问题也永远拒答。这是「能接线但不能作答」的契约缺口。

## 修复方向（加法，不改注册表）

让 `box` 成为可作答的自由文本类型，三处后端一致：

1. `ANSWERABLE_TYPES` 增加 `"box"`；
2. `_b2_input_schema()`：`box` → `{"type": "string", "minLength": 1, "maxLength": 600}`；
3. `_describe_questions()`：`box` 分支写明「free text, plain string, no JSON」（模型才会填字符串而不是对象）；
4. `_validate_answers()`（B1/B2 共用）：`box` → 必须是非空字符串（`strip()` 后非空），超长按字符截断到 600 并保留；非字符串 → 现有 `unsupported question type` 之外的明确错误文本（例如 `box for <qid> is not a string`）；
5. B3 `_decode_answers()`（`:812` 起，自带一套校验）加同一分支，行为与 4 一致；
6. B3 `build_questions()` 的 `box` 走 else 分支透传原样即可，不要顺手改成别的类型。

**不要**改 `decision_points.py` 的注册表（`box` 是契约里的类型名，dp8 也用它），也**不要**把自由文本强塞进 `choice` 的 enum。

## 必做用例（`packages/multi-workers/test_decide_backends.py`）

1. `_unsupported_types(DP_REGISTRY["dp3-worker-clarify"].questions) == []`（用真实注册表，不是手搓 dict）——这条若在修复前跑应红，修复后绿；
2. `_b2_input_schema` 对 `box` 生成 `{"type": "string", ...}`，且 `dp1` 的 `choice` 仍是 enum；
3. `_validate_answers` 接受 `{"answer_kind": "fact", "clarifying_answer": "见 decision_backends.py:375", "confidence": 0.8}` 并返回原样字符串；
4. `_validate_answers` 拒绝 `clarifying_answer: 123` 与空串 `"   "`；
5. 回归：`dp1-dispatch-type` 的问题集不产生任何 `box`，schema 不变。

## 写入允许面

- `packages/multi-workers/decision_backends.py`
- `packages/multi-workers/test_decide_backends.py`
- `docs/decision-substitution.md`（只在讲 dp3 3a 的小节补一句「自由文本答案走 `box` 类型」）
- `packages/multi-workers/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/decision_points.py`（注册表是契约，本次不改）
- `packages/multi-workers/mw.py`、`decide_archive.py`、`decision.py`
- `packages/coding-agent/**` 一切文件
- `spec.md`、`design.md`、`plan.md`、`pm-state.md`、`achieved.md`、`tasks/**`、`.agenticdoc/**`（除 CHANGELOG 与文档之外）
- 禁止 `git` 任何写操作；禁止 `npm run check`；禁止全量 pytest（只允许点名的测试文件）；禁止 `Set-Content`（用 `edit` / `write`）
- 禁止在本次改动里发起真实网络决策调用（不要跑 `mw decide run`）——PM 负责联网验证

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_backends.py
python -m pytest -q test_decide_cli.py test_decide_dp_cli.py
```

三份都通过，且 `test_decide_backends.py` 用例数只增不减。另外跑一条只读自检：
`python -c "from decision_points import DP_REGISTRY; from decision_backends import _unsupported_types; print(_unsupported_types(DP_REGISTRY['dp3-worker-clarify'].questions))"` 必须输出 `[]`。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待改 1：`packages/multi-workers/decision_backends.py:101`（`ANSWERABLE_TYPES`）
- 待改 2：同文件 `:352`（`_b2_input_schema`）、`:334`（`_describe_questions`）、`:390`（`_validate_answers`）、`:812`（B3 `_decode_answers`）
- 契约来源：`packages/multi-workers/decision_points.py:370`（dp3 的 `box`）、`:423`（dp8 的 `box`）
- 消费侧：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4924`（`parseAnswerEntry(answers?.clarifying_answer)`，期望字符串）
- 实测证据：PM 2026-10-20 在 `H:\tmp\mwds-jev` 的两次真实调用（dp1 正常、dp3 `unsupported-question-type`）
- 文档：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020b.md`（残留第 3 条的「工具不可答」在本卡之外）

## 改动历史

- 2026-10-20 建卡：PM 实测发现 dp3 因 `box` 类型恒 `unsupported-question-type`，导致旗舰路径在生产中永远上抛人。
