# FIX-R：`DecisionClient` 的入参类型落地（TypedDict/Literal）+ 两条 fail-loud

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户在审阅 `DecisionClient.decide` 时指出：`def decide(self, state: object, questions: dict, ...)` 两个入参没有真正的类型，
题目结构（`noul/choice/score/box`、`choices` vs `dynamic_choices` 二选一、`score.min/max`、`criteria` 键集合）只活在
`_validate_input` 的运行时 if 分支里，静态零保护。用户裁定先补接口类型。

现状（本卡只改这些点，别扩散）：

- `packages/multi-workers/decision.py:116` `QUESTION_TYPES = frozenset({QUESTION_CHOICE, QUESTION_SCORE, QUESTION_NOUL, QUESTION_BOX})`
- `packages/multi-workers/decision.py:668` `def decide(self, state: object, questions: dict, *, dp: str = "unspecified") -> dict`
- `packages/multi-workers/decision.py:817` `_validate_input(self, state: object, questions: object) -> None`（唯一抛 `DecisionInputError` 的路径）
- `packages/multi-workers/decision.py:936` `_normalize_answers(self, answers: object, questions: Mapping) -> dict | None`
- `state` 之所以是 `object`：端点的 `state` 文档形状是 string / object / array（`decision_backends.py:391 _state_payload`），
  两种形态都合法，所以注解不能用 `dict`。**本卡把 `state` 改成 `Mapping[str, object] | str | list | bytes` 这一类联合**，
  不要收窄成 `Mapping`。

## 要求

1. 在 `decision.py` 加类型别名/TypedDict（放在 `QUESTION_TYPES` 附近，`from typing import Literal, Required, TypedDict, NotRequired`）：
   - `QuestionType = Literal["noul", "choice", "score", "box"]`
   - `NoulSpec`：`type: Required[Literal["noul"]]`、`instructions: NotRequired[str]`、`criteria: NotRequired[Mapping[str, str]]`
   - `ChoiceSpec`：`type: Required[Literal["choice"]]`、`instructions`、`choices: NotRequired[Sequence[str]]`、`dynamic_choices: NotRequired[str]`、`labels: NotRequired[Mapping[str, str]]`
   - `ScoreSpec`：`type: Required[Literal["score"]]`、`instructions`、`min: Required[int]`、`max: Required[int]`、`criteria: NotRequired[Sequence[str]]`
   - `BoxSpec`：`type: Required[Literal["box"]]` + 可选字段（按现有代码实际读取的键）
   - `QuestionSpec = NoulSpec | ChoiceSpec | ScoreSpec | BoxSpec`
   - `DecisionState = Mapping[str, object] | Sequence[object] | str | bytes`
2. 把签名改成注解真实形状，**运行逻辑不变**：`decide(self, state: DecisionState, questions: Mapping[str, QuestionSpec], *, dp: str = "unspecified") -> dict`；
   `_validate_input(self, state: object, questions: object)`（内部仍按 `Mapping` 判定）、`_normalize_answers(...)` 同步注解。
   `QUESTION_TYPES` 改为 `frozenset[QuestionType]` 或保持不变并注明与 `QuestionType` 一致。
3. `_validate_input` 新增两条 fail-loud（仍旧只抛 `DecisionInputError`，不联网、不写文件）：
   - `noul` 若带 `criteria`：必须是 mapping，键集合**恰好** `{"true", "false"}`，两值都是非空字符串；否则
     `DecisionInputError("question <qid> type 'noul' criteria must be exactly {true, false} ...")`。
   - `choice` 若同时带 `labels` 与 `dynamic_choices`：直接拒（现在 `labels` 静默失效），消息写清"dynamic_choices 会渲染候选，
     labels 只用于静态 choices，二者不能同时给"。
4. 测试（`packages/multi-workers/test_decide.py` 追加，不改已有断言的语义）：
   - 两条新校验各 2 例（合法通过 / 非法 `DecisionInputError`，含 `criteria={"yes": ...}` 与 `labels+dynamic_choices`）；
   - 一条：`decide` 接受 `state` 为 `str`（文本形态）与 `dict` 两种；
   - 一条：注解自测（`typing.get_type_hints(DecisionClient.decide)` 里 `state` 不是裸 `object`、`questions` 不是裸 `dict`），
     防止以后被改回去。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide.py test_decide_backends.py test_decision_points.py test_decide_cli.py test_decide_signoff.py
python -c "import typing, decision; print(typing.get_type_hints(decision.DecisionClient.decide))"
```

（第二条打印出来的注解必须出现 `QuestionSpec`/`TypedDict` 或至少是具体 Union，而不是 `object`/`dict`。）

## 写入允许面

- `packages/multi-workers/decision.py`
- `packages/multi-workers/test_decide.py`

## 写入禁止面

- `packages/multi-workers/decision_points.py`、`decision_backends.py`、`mw.py`、`decide_signoff.py`
- `packages/multi-workers/CHANGELOG.md`（PM 写）
- 其它任何 `test_decide_*.py`、`packages/ai/**`、`packages/coding-agent/**`、`.agenticdoc/**`、`.agents/**`
- 禁止 `git` 写操作、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络调用、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 两条验收输出原文 / 是否有测试因新校验需要改语义（有则逐条说明改了什么、为什么不是削弱）/ 残留。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 现有契约文档：`docs/decision-substitution.md`（D-003 响应字段）、`packages/multi-workers/README.md` 的 `mw decide` 段
- 必须保持的既有事实：`decide` 只抛 `DecisionInputError`；响应恒 8 字段（`_RESPONSE_FIELDS:122`）；
  机器面归一化只留 `{value, confidence}`（`_normalize_answers:936`），`probabilities/legend` 只在人用面放宽（`mw.py:1280 _AskDecisionClient`）
- 注册表实际数据（改完必须仍然通过）：`decision_points.py:872 REQUIRED_STATE_FIELDS` 只覆盖 dp1/dp2/dp3；
  dp3 的 `answerable` 带 `criteria{true,false}`（FIX-O），dp3 的 `candidate` 用 `dynamic_choices` 且**不带** `labels`

## 改动历史

- 2026-10-21 建卡：用户指出 `decide` 入参无类型，裁定补 TypedDict/Literal + 两条 fail-loud。
