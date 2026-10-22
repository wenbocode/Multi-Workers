# FIX-I：dp3 3a 改为 Jev 原生题型（choice + noul + 动态候选），dp8 rationale 换掉 box

- type: coding
- owner key: mw-decision-substitution
- 背景（用户 2026-10-20 裁定）：`3a 要改成 choice/nuol`。Jev 官方契约**没有自由文本题型**
  （`noul` / `choice` / `score` / `box`，`box` 还是图像定位框），所以「让模型返回一段带 `path:line`
  的文字答案」在 Jev 上不可能。3a 改为：**模型只做选择与可答性判断，引用与文本由本地候选自带**。

## 冻结契约（本卡与 FIX-J 共用，两侧必须逐字一致）

### dp3 注册表问题集（`decision_points.py`，registry 是唯一权威）

```python
questions=(
    {"id": "answer_kind", "type": "choice", "choices": ["fact", "intent", "reuse"]},
    {"id": "answerable", "type": "noul"},
    {"id": "candidate", "type": "choice", "dynamic_choices": "local_candidates"},
)
```

### dp8 注册表问题集

```python
questions=(
    {"id": "scope_decision", "type": "choice", "choices": ["keep", "narrow", "expand"]},
    {"id": "scope_reason", "type": "choice",
     "choices": ["outside-write-face", "cross-key-conflict", "scope-creep", "unclear-boundary"]},
)
```

### `dynamic_choices` 语义（新属性，只对 `type=choice` 有效）

- 值是一个 **state 键名**（本卡只用 `local_candidates`），与静态 `choices` **互斥**。
- state 里该键的形状：`[{"id": "c1", "label": "..."}, ...]`，1..5 项，`id` 必须从 `c1` 连续编号
  （正则 `^c[1-9]$`），`label` 非空且 ≤ 80 字符，`label` 内不得含换行。
- 该 dp 的 `REQUIRED_STATE_FIELDS` 追加 `local_candidates`（缺失 → `input-incomplete` +
  `missing_fields=["local_candidates"]`，零 HTTP）。
- 渲染：B3 `criteria = {id: label}`；B2 prompt 里逐行 `c1: <label>` 且 schema 的 `enum` 是**渲染出的 id 列表**。
- 答案校验：`choice` 的成员判定用**渲染后的 id 集合**，不是注册表静态 choices；
  `questions_version` 仍然只由注册表 questions 计算（不随每次调用的候选变化）——这是刻意的：
  版本串标识「问题集形状」，候选是输入数据。

## 本卡要做的（Python 侧）

1. `decision_points.py`
   - `_validate_question` 支持 `dynamic_choices`：仅 `choice`；必须是非空字符串 state 键；
     与静态 `choices` 同时出现 → `ValueError`；两者都缺 → 仍按原规则报错。
   - dp3 / dp8 问题集按上面的冻结契约替换。
   - `REQUIRED_STATE_FIELDS["dp3-worker-clarify"]` 追加 `"local_candidates"`。
   - 新增 `resolve_dynamic_choices(questions, state) -> dict[str, tuple[str, ...]] | None`：
     返回每个动态题的合法 id 元组；任一动态题在 state 里缺失/形状非法 → 返回 `None` 由调用方按
     `input-incomplete` 处理（不要在这里抛异常）。
2. `decision_backends.py`
   - `_describe_questions` / `_b2_input_schema` 支持动态题：B2 的 enum 与提示行用**渲染结果**；
     `_b2_input_schema` 的 `required` 仍只列有 schema 的 id。
   - B3 `build` 的 `criteria`：动态题用 `{id: label}`；`_decode_answers` 的 choice 成员校验用渲染集合。
   - `_validate_answers` 的 choice 分支：成员判定改为「渲染集合（若该题是动态题）否则注册表 choices」。
   - 动态题解析失败（state 缺 `local_candidates`）→ `available=false, reason="input-incomplete"`，
     detail 里带 `missing_fields=["local_candidates"]`，**零 HTTP 调用**。
3. 不改 `box` 的拒绝语义（FIX-H 的 `box-requires-image` 保留），注册表里不再有 dp 使用 `box`。

## 必做用例（`packages/multi-workers/test_decide_backends.py`）

1. dp3 的 `questions_map("dp3-worker-clarify")` 现在等于冻结契约的三题；dp8 等于两题；
   全仓库 `questions_map` 里 `box` 出现次数为 **0**（用 `DP_REGISTRY` 遍历断言）。
2. 合法 state（含 `c1..c3`）→ B3 请求体 `questions["candidate"]["criteria"] == {"c1": ..., "c2": ..., "c3": ...}`。
3. 缺 `local_candidates` → `input-incomplete` + `missing_fields == ["local_candidates"]` + 零 HTTP（假 transport 计数）。
4. 候选形状非法（不连续 / id 非 `cN` / label 空或 >80 / 超过 5 项）→ 同样零 HTTP 拒绝，detail 说明具体原因。
5. 答案 `candidate=c2`（在渲染集合内）通过；`candidate=c9`（不在集合内）→ 明确错误。
6. 回归：`noul` 答案按概率（`0.0..1.0`）通过、越界拒绝（FIX-H 已覆盖，确认不被打破）。

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_backends.py`
- `packages/multi-workers/test_decide_backends.py`
- `packages/multi-workers/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/mw.py`、`decision.py`、`decide_archive.py`
- `packages/coding-agent/**` 一切文件（TS 侧由 FIX-J 负责，禁止你改）
- `docs/**`、`spec.md`、`design.md`、`plan.md`、`pm-state.md`、`achieved.md`、`tasks/**`、`.agenticdoc/**`
- 禁止 `git` 写操作、`npm run check`、全量 pytest、真实网络调用（不要跑 `mw decide run` / `mw decide probe`）、`Set-Content`

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_backends.py
python -m pytest -q test_decide_cli.py test_decide_dp_cli.py
python -c "from decision_points import questions_map; print(questions_map('dp3-worker-clarify')); print(questions_map('dp8-scope-change'))"
```

最后一条的期望输出（键序可变）：

```
{'answer_kind': {'id': 'answer_kind', 'type': 'choice', 'choices': ['fact','intent','reuse']},
 'answerable': {'id': 'answerable', 'type': 'noul'},
 'candidate': {'id': 'candidate', 'type': 'choice', 'dynamic_choices': 'local_candidates'}}
{'scope_decision': {...}, 'scope_reason': {...}}
```

## 交付格式

`report.md`：结论 / 契约落地点（文件:行）/ 验收输出原文 / 残留 / 未覆盖面（禁止声称「Jev 已跑通」——本卡不联网）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`（jev 作为决策模型替换中低风险人工决策）
- 现状锚点：`packages/multi-workers/decision_points.py:368-372`（dp3 两题，含 `box`）、`:421-424`（dp8 含 `box`）、`:185-207`（`_validate_question`）、`:624-672`（`REQUIRED_STATE_FIELDS`）
- 后端锚点：`packages/multi-workers/decision_backends.py:334`（`_describe_questions`）、`:352`（`_b2_input_schema`）、`:390`（`_validate_answers`）、`:812` 起（B3 `_decode_answers`）
- 官方契约：`https://api.typesafe.ai/api/system-one.md`（本地副本 `H:\tmp\ts-api.md`），题型只有 `noul`/`choice`/`score`/`box`
- 前序：`tasks/FIX-G-box-question-type.md`（错误方向，已由 `tasks/FIX-H-jev-answer-contract.md` 撤销）

## 改动历史

- 2026-10-20 建卡：用户裁定 3a 改 `choice`/`noul`；因 Jev 无自由文本题型，改为「动态候选 + 选择 + 可答性」，引用与文本由本地候选自带。
