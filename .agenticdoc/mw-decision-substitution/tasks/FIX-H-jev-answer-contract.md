# FIX-H：按 Jev 官方契约纠正答案类型（撤销 `box` 自由文本、对齐 answer 结构）

- type: coding
- owner key: mw-decision-substitution
- 前置事实：PM 直接拉了官方 OpenAPI（`https://api.typesafe.ai/api/system-one.md`，2026-10-20），
  与 FIX-G 的假设冲突。FIX-G 把 `box` 当成「自由文本」实现，**是与上游契约相反的发明**，必须纠正。

## 官方契约（原文要点，作为本卡的唯一依据）

`POST https://api.typesafe.ai/v1/systemone`，body = `{model, state, questions}`。

Question 判别式 `type ∈ {noul, choice, score, box}`，**没有自由文本类型**：

| type | 请求字段 | 响应形状 |
|---|---|---|
| `noul` | `instructions` + 可选 `criteria`（true/false 两键） | `{type:"noul", noul: 0.98}`（概率，非布尔） |
| `choice` | `instructions` + `criteria`（`{选项: 说明}`） | `{type:"choice", choice:"calm", confidence:0.7, probabilities:{...}}` |
| `score` | `instructions` + `criteria`（有序列表） | `{type:"score", score:1.7, confidence:0.55, legend:{...}, probabilities:{...}}`（**score 是浮点**） |
| `box` | `instructions`（描述"在图片里定位什么"） | `{type:"box", box:{top,bottom,left,right}, confidence:null}`，且**必须**带 header `TypeSafe-Danger-Zone-Images: true`，`state` 需配 `assets` 图像 |

响应外层：`{model, answers: {<qid>: <上面某一种>}, usage: {input_tokens, output_tokens}}`。

## 现状与契约的差异（本卡要修的）

1. `ANSWERABLE_TYPES` 现在是 `("choice","score","noul","box")`，且 `_validate_answers` 把 `box` 当自由字符串
   （非字符串报错、空串报错、超长截断 600）——这与 `box = 图像框` 相反。
2. `_b2_input_schema` 把 `box` 生成为 `{"type":"string",minLength:1,maxLength:600}`——同样相反。
3. `_describe_questions` 把 `box` 描述成 "free text answer as a plain string"——会诱导模型给出文本。
4. `_validate_answers` 的 `score` 只接受 **int**，官方是**浮点**（示例 `1.7`）。
5. B3 `_decode_answers` 里 `box` 取 `entry["box"]` 的形状假设未经官方核对（真实应为 `{top,bottom,left,right}` 归一化坐标对象）。
6. 官方 `answers` 里每种类型都带 `type` 与（choice/score/box）`confidence`；`noul` 只有概率值。当前 TS 侧
   `parseAnswerEntry` 期望 `{value, confidence}`，需要在 Python 侧映射成既有 `answers: {qid: {value, confidence}}`
   **而不是**直接透传官方形状（TS 契约不变）。

## 修复要求

1. **撤销 FIX-G 的自由文本 `box`**：`ANSWERABLE_TYPES` 回到 `("choice","score","noul")`，
   并新增独立的拒绝原因（不要复用 `unsupported-question-type`）：
   `box-requires-image` —— 当问题集里含 `box` 且本次请求没有图像资产时，直接返回
   `available=false, reason="box-requires-image"`，detail 写明「box 是图像定位题，需 TypeSafe-Danger-Zone-Images 与 assets」。
   `_validate_answers` / `_b2_input_schema` / `_describe_questions` 删除 box 的自由文本分支。
2. **score 接受浮点**：`_validate_answers` 的 score 分支改为 `int` 或 `float`（排除 bool），范围按
   `min/max` 校验（允许在范围内为非整数）；错误文本改为 `score for <qid> is not a number`。
3. **B3 `_decode_answers` 按官方形状解析**，并统一映射成内部 `{value, confidence}`：
   - `choice`：`value = entry["choice"]`，`confidence = entry.get("confidence")`，并要求该值属于 `criteria` 的键；
   - `score`：`value = entry["score"]`（浮点），`confidence = entry.get("confidence")`；
   - `noul`：`value = entry["noul"]`（概率 0..1），`confidence = None`；
   - `box`：不解析（请求侧已被 1 拒绝），保留 `unsupported` 分支以免静默。
   - 缺失 `type` 字段或 `type` 与问题类型不一致 → 明确错误文本（`answer type mismatch for <qid>`）。
4. **在 `_decode_answers` / `_validate_answers` 上方写清契约出处**（URL + 抓取日期），避免下次再凭猜。

## 必做用例（`packages/multi-workers/test_decide_backends.py`）

用**官方示例原样**作为 fixture（choice/noul/score 各一份，来自 `api/system-one.md` 的 examples）：

1. choice 示例 → 解析出 `{"tone": {"value": "calm", "confidence": 0.7}}`；
2. score 示例（`score: 1.7`）→ 解析出浮点 1.7，且 `_validate_answers` 对 `1.7` 不再报错；
3. noul 示例（`noul: 0.98`）→ `{"billing": {"value": 0.98, "confidence": None}}`；
4. 含 `box` 的问题集 → `available=false, reason="box-requires-image"`，且**零 HTTP 调用**（用假 transport 计数）；
5. `type` 与问题类型不一致 → 明确错误，不产生答案；
6. 回归：FIX-G 之前的行为不被回退的地方（choice/score/noul 的正常路径）保持绿。

## 写入允许面

- `packages/multi-workers/decision_backends.py`
- `packages/multi-workers/test_decide_backends.py`
- `docs/decision-substitution.md`（把「`box` 自由文本」那段改成「box 是图像定位题，文本决策不使用」）
- `packages/multi-workers/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/decision_points.py`（dp3/dp8 仍用 `box` 的设计问题由另卡决定，本卡不动注册表）
- `packages/multi-workers/mw.py`、`decision.py`、`decide_archive.py`
- `packages/coding-agent/**` 一切文件
- `spec.md`、`design.md`、`plan.md`、`pm-state.md`、`achieved.md`、`tasks/**`
- 禁止 `git` 写操作、`npm run check`、全量 pytest、真实网络调用（不要跑 `mw decide run`）、`Set-Content`

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_backends.py
python -m pytest -q test_decide_cli.py test_decide_dp_cli.py
```

另跑一条只读自检并把输出贴进报告：

```bash
python -c "from decision_backends import ANSWERABLE_TYPES; print(ANSWERABLE_TYPES)"
```

期望 `('choice', 'score', 'noul')`。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待改：`packages/multi-workers/decision_backends.py:101`（`ANSWERABLE_TYPES`）、`:334`（`_describe_questions`）、`:352`（`_b2_input_schema`）、`:390`（`_validate_answers`）、`:812` 起（B3 `_decode_answers`）、`:375`（`_unsupported_types`）
- 契约出处：`https://api.typesafe.ai/api/system-one.md`（PM 2026-10-20 抓取，`H:\tmp\ts-api.md` 为本地副本）
- 历史：`tasks/FIX-G-box-question-type.md`（本卡撤销其 `box` 语义，保留其对 `_describe_questions`/`_b2_input_schema` 结构的整理）
- 实体化调研：`.agenticdoc/mw-jev-provider-integration/evidence/research/spec-typesafe-api-20261016.md`

## 改动历史

- 2026-10-20 建卡：PM 核对官方 OpenAPI 后发现 `box` 是图像定位题、Jev 无自由文本类型，FIX-G 的 box 自由文本实现与契约相反；本卡纠正并把答案解析对齐官方示例。
