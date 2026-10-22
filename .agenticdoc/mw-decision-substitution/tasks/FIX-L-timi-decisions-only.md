# FIX-L：决策传输收敛为 `timi-decisions`（jev-latest），删除 glm 与 typesafe 两条路

- type: coding
- owner key: mw-decision-substitution
- 依据：用户 2026-10-20 裁定「是要接 `timi/jev-latest`，不是 typesafe；把 `timi/glm-5.3-flashx`
  从决策流程中移除，不要备选，也没有备选」。接入文档：`.agenticdoc/mw-decision-substitution/jev接入.md`
  （已实测通：`POST /v1/decisions` + timi key → 200，`noul 0.87`、`choice billing 0.98`）。

## 已实测的官方契约（唯一依据）

```
POST http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions
Authorization: <平台个人 API Key>          # 就是 timi key，不加 Bearer 前缀也可（实测直接放 key 即 200）
Content-Type: application/json
{"model": "jev-latest", "state": <str|obj|array>, "questions": {<qid>: <Question>}}
```

`Question`：`{type, instructions, criteria?}`，`type ∈ {noul, choice, score}`（**没有 box，也没有自由文本**）：

- `noul`：`instructions` 必填；`criteria` **可选**，形如 `{"true": "...", "false": "..."}`（分别说明「偏是/偏否」含义）。
- `choice`：`instructions` + `criteria` **必填**，`{选项: 说明}`，说明可为 `null`，最多 255 项。
- `score`：`instructions` + `criteria` **必填**，有序数组（低→高），2..10 档。

响应：`{model, answers: {<qid>: <Answer>}, usage: {input_tokens, output_tokens}}`

- `noul` → `{type:"noul", noul: 0.95}`（「是」的概率）
- `choice` → `{type:"choice", choice:"billing", probabilities:{...}, confidence:0.81}`
- `score` → `{type:"score", score:1.05, legend:{...}, probabilities:{...}, confidence:0.92}`

不支持流式；Decisions 模型不能用于 chat/responses 接口。

## 本卡要做的（Python：`decision.py` + `decision_backends.py` + 测试）

### 1. 新后端 `timi-decisions`（唯一传输）

- 常量：`DECISIONS_TRANSPORT = "timi-decisions"`、`DECISIONS_PATH = "/v1/decisions"`、
  `DEFAULT_MODEL = "jev-latest"`、`TIMI_BASE_URL`（沿用现值）。
- 类 `TimiDecisionsBackend`：`name = "timi-decisions"`、`confidence_source = CONFIDENCE_SOURCE_API`
  （jev 返回 `confidence`，属官方 API 字段，不是模型自报）。
- 凭据：`cfg.api_key` → `resolve_timi_api_key()`（env `TIMI_API_KEY` → `~/.pi/agent/auth.json` 的 `timi.key`）；
  缺失 → `available=false, reason="entry-unavailable"`，零 HTTP。
- 请求体：只 `{model, state, questions}`；`model = cfg.model or "jev-latest"`。
- 问题映射（**关键**，网关对 `criteria` 是硬校验）：
  - `instructions`：`spec.get("instructions")` 优先；否则用注册表兜底文本
    `f"{qid}: answer this question about the supplied state"`（并在模块注释里写明：注册表补 instructions 是后续改进项）。
  - `noul`：`{"type":"noul","instructions":...}`；若 spec 自带 `criteria`（`true`/`false` 文本）则原样带上。
  - `choice`：`{"type":"choice","instructions":...,"criteria":{id: label_or_null}}`；
    label 来源：动态候选渲染（`decision_points.dynamic_choice_labels`）优先，其次 `spec["labels"]`，否则 `None`。
  - `score`：`{"type":"score","instructions":...,"criteria":[...]}`；优先 `spec["criteria"]`（有序说明），
    否则由 `min..max` 生成 `["0","1",...]`（超过 10 档截断到 10）。
  - `box`：不进入请求（沿用 FIX-H 的 `box-requires-image` 拒绝，零 HTTP）。
- 响应解析：复用现有 systemone 形状的解码（`choice/score/noul` → 内部 `{value, confidence}`；
  `choice` 成员必须在渲染/静态集合内；`score` 保留浮点；`noul` 概率 0..1 且 `confidence=None`）。
- 失败处理：429/5xx 按 `cfg.max_retries` 在同一端点重试（指数退避，尊重 `retry-after`）；
  重试耗尽后 `reason="rate-limited"` / `"upstream-error"`；超时 `"timeout"`。
  **禁止**任何更改 model 或换 transport 的降级/备选（没有 fallback 代码路径）。

### 2. 删除 B1/B2/B3（不留备选）

- 删除 `LLMTransitionalBackend`（glm）、`LLMProxyAnthropicBackend`、`DirectSystemOneBackend` 三个类，
  以及只服务它们的常量（`TYPESAFE_BASE_URL`、`resolve_typesafe_api_key`、`TOOL_NAME`、
  `ANTHROPIC_VERSION`、`PROBE_MATRIX` 里的旧行）。
- `decision.py`：`DecisionConfig.transport` 默认 → `"timi-decisions"`、`model` 默认 → `"jev-latest"`；
  `DEFAULT_BACKEND_CLASSES` 只剩 `{"timi-decisions": "TimiDecisionsBackend"}`；
  `_imported_backend_factory` 的 `transport or "timi-decisions"` 同步。
- 配置里出现旧值（`llm-transitional`/`llmproxy-anthropic`/`direct-systemone`）时：
  **fail loud** —— `entry-unavailable` 且 detail 写明「unknown decision transport <x>」，
  绝不回退到 `timi-decisions` 假装成功。
- `credential_status` 只保留 timi 一项（`{"timi": bool}`）。

### 3. 必做用例（`test_decide_backends.py`，删旧、加新）

用**文档原文示例**做 fixture：

1. `noul` 请求体逐字符合文档形状（`type`/`instructions`；无 `criteria` 时不发该键），响应 `{noul:0.95}` → 内部 `{value:0.95, confidence:None}`。
2. `choice` 必须带 `criteria`（`{billing:"...",technical:"..."}`），响应解码出 `value="billing"`、`confidence=0.81`、`probabilities` 不丢。
3. `score` 的 `criteria` 是有序数组，响应 `score:1.05` 保留浮点、`legend` 不丢。
4. 动态候选：`candidate` 题的 `criteria` 用渲染出的 `{c1: label}`，且答案 `c3` 通过、`c9` 被拒。
5. 无 timi 凭据 → `entry-unavailable`，零 HTTP。
6. 429 一次后成功 → `attempts>=2` 且最终 `available=true`；连续 429 → `reason="rate-limited"`。
7. **无备选断言**：构造一个「响应里 model 不是 jev-latest」的场景，断言后端**不接受**该答案
   （返回 `bad-response`），而不是换模型重试；并断言模块里不存在指向其他 endpoint 的常量
   （`grep` 式断言：`TYPESAFE_BASE_URL`/`/v1/systemone`/`glm-5.3-flashx` 在该模块出现 0 次）。
8. 旧传输值 → `entry-unavailable`。

## 写入允许面

- `packages/multi-workers/decision.py`
- `packages/multi-workers/decision_backends.py`
- `packages/multi-workers/test_decide_backends.py`
- `packages/multi-workers/test_decide.py`

## 写入禁止面

- `packages/multi-workers/mw.py`（CLI 侧由 FIX-M 负责，含 `decide ask`）
- `packages/multi-workers/test_decide_cli.py`、`test_decide_dp_cli.py`、`test_decision_points.py`、`test_decide_run_authority.py`
- `packages/multi-workers/CHANGELOG.md`、`README.md`（FIX-M 统一写）
- `packages/coding-agent/**`、`packages/ai/**`、`docs/**`、`.agenticdoc/**`
- 禁止 `git` 写操作、`npm run check`、全量 pytest、**真实网络调用**（不要跑 `mw decide run/ask/probe`）、`Set-Content`

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_backends.py
python -m pytest -q test_decide.py
python -c "import decision_backends as b; print(b.ANSWERABLE_TYPES); print([n for n in dir(b) if n.endswith('Backend')])"
```

第三条期望只出现 `TimiDecisionsBackend`（外加 `BackendOutcome`/协议名，不得再有 `LLMTransitionalBackend` 等）。

## 交付格式

`report.md`：结论 / 契约落地点（文件:行）/ 三条验收输出原文 / 残留 / 未覆盖面
（**禁止**声称「已真连 jev」——本卡不联网；真连由 PM 用 `mw decide` 验）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`（jev 作为决策模型）
- 接入文档：`.agenticdoc/mw-decision-substitution/jev接入.md`（`/v1/decisions` 契约、criteria 必填规则、响应字段表）
- 现状锚点：`packages/multi-workers/decision_backends.py:100-105`（旧常量）、`:164-204`（凭据解析）、`:637`（B2）、`:838`（B1）、`:923`（B3）、`:1030-1045`（响应解码）；`packages/multi-workers/decision.py:246`（transport 默认）、`:491-494`（类映射）、`:516`（默认值）
- PM 实测证据（2026-10-20）：`POST /v1/decisions` model=jev-latest → 200，`{"is_urgent":{"type":"noul","noul":0.87},"department":{"type":"choice","choice":"billing","confidence":0.98,...}}`

## 改动历史

- 2026-10-20 建卡：用户裁定决策流程只接 `timi/jev-latest`，删除 glm 与 typesafe 两条路，且不允许任何备选。
