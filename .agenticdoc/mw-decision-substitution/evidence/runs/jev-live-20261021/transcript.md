# 真 jev 用例：输入是什么、jev 回了什么、我们怎么接收并应用

- 运行时间：2026-10-21 11:5x（本机，PM 直执，非 worker）
- 传输：`POST http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions`
- 头：`Authorization: <个人 timi key>`（裸 key，无 `Bearer`）／`Content-Type: application/json`
- body：只有 `{model, state, questions}`，`model` 固定 `jev-latest`
- 复现：`python .agenticdoc/mw-decision-substitution/evidence/runs/jev-live-20261021/run.py`
- 本目录文件：`run.py`（可复跑）、`request-a.json` / `response-a.json`（人问答）、
  `request-b.json` / `response-b.json` / `outcome-b.json`（dp3 结构化）、`cli-ask.txt`（`mw decide ask` 渲染）、
  `project/`（案例用的临时项目 + `.mw/decide.json`）

---

## 用例 A：人直接问 jev（`mw decide ask` 语义，无 dp 授权）

### 输入（`request-a.json` 原文）

```json
{
  "model": "jev-latest",
  "state": {
    "message": "求助！我的提现已经失败3天了。",
    "context": "用户从帮助中心提交工单，未提供订单号。"
  },
  "questions": {
    "urgent": {
      "type": "noul",
      "instructions": "这段话是否传达了紧急性？",
      "criteria": {"true": "用户明确表示业务受阻或要求立即处理", "false": "只是普通咨询或抱怨"}
    },
    "dept": {
      "type": "choice",
      "instructions": "这条工单应该由哪个团队接手？",
      "criteria": {"billing": "支付、开票、退款相关", "technical": "缺陷、故障、集成相关",
                   "sales": "定价、升级、新账号相关"}
    },
    "frustration": {
      "type": "score",
      "instructions": "用户此刻的情绪强度是第几档？",
      "criteria": ["平静", "不满", "非常愤怒"]
    }
  }
}
```

### jev 的反馈（`response-a.json`：HTTP 200，1010 ms）

```json
{"model": "jev-latest",
 "answers": {
   "dept":        {"type":"choice","choice":"billing","confidence":0.98,
                   "probabilities":{"billing":0.99,"sales":0.0,"technical":0.01}},
   "frustration": {"type":"score","score":0.99,"confidence":0.97,
                   "legend":{"0":"平静","1":"不满","2":"非常愤怒"},
                   "probabilities":{"0":0.01,"1":0.98,"2":0.01}},
   "urgent":      {"type":"noul","noul":0.79}},
 "usage": {"input_tokens":513,"output_tokens":70,"cached_tokens":0,"cache_write_tokens":0},
 "id": "gen-dec-1792553272-7XlykMXE041LF9GzLdiA"}
```

注意三点：`noul` 是**概率**（0.79，不是布尔）；`score` 是**浮点档位索引**（0.99）+ 服务端回传 `legend`；
`choice` 带完整 `probabilities`。响应里没有文本生成——jev 不写句子。

### 我们的解码（`TimiDecisionsBackend._decode_answers`）

| 题 | 服务端字段 | 归一后（`answers[qid]`） |
| --- | --- | --- |
| `urgent` (noul) | `noul=0.79` | `{"value": 0.79, "confidence": null}` |
| `dept` (choice) | `choice="billing"`, `confidence=0.98` | `{"value": "billing", "confidence": 0.98}` |
| `frustration` (score) | `score=0.99`, `confidence=0.97` | `{"value": 0.99, "confidence": 0.97}` |

规则：`choice` 的 `choice` 必须命中发送的 `criteria` 键集合，否则 `bad-response`；响应 `model` 与请求不符
→ `bad-response`（网关偷换模型抓得住）；`noul` 超 0..1 视为不可用。

### 给人的渲染（`cli-ask.txt`，另一次真实调用，1067 ms）

```
jev-latest · 3 questions · 1067 ms
urgent      [noul]    0.87          (probability of "yes")
dept        [choice]  billing       confidence 0.95   probs: billing 0.97, technical 0.03, sales 0.00
frustration [score]   1.02          confidence 0.95   legend: 0=平静, 1=不满, 2=非常愤怒
```

---

## 用例 B：结构化决策点（`mw decide run --dp dp3-worker-clarify`）

场景：worker 卡在「这条澄清该用哪个证据文件回答」上，dp3 是 P2 自动点，允许 jev 直接定。

### 输入（`request-b.json` 的 state 摘要）

```json
{"v":1,"dp":"dp3-worker-clarify","key":"jev-live-case","phase":"EXECUTE","task_type":"research",
 "risk":"low","risk_source":"machine","authority_tier":"P2",
 "task_summary":"jev 决策入口的契约调研证据应该写到哪个文件？",
 "questions_version":"q-fcbd3847",
 "ambiguity":{"kind":"scope","question":"jev 决策入口 /v1/decisions 的传输契约调研证据应该写到 evidence/research/ 下的哪个文件？"},
 "local_candidates":[{"id":"c1","label":"evidence/research/spec-worker-heartbeat-20261021.md"},
                     {"id":"c2","label":"evidence/research/spec-timi-decisions-api-20261021.md"},
                     {"id":"c3","label":"evidence/research/spec-budget-guard-20261021.md"}]}
```

`questions` 由注册表（`decision_points.py`）渲染，三题都是 jev 原生题型：

| qid | type | instructions | criteria |
| --- | --- | --- | --- |
| `answer_kind` | choice | 这条澄清属于哪一类：能凭已给材料查到答案、需要人的意图判断、还是已有表态可复用？ | fact / intent / reuse（各带说明） |
| `answerable` | noul | 仅凭 state 里给出的内容与候选条目，能否确定地回答上面这条澄清？ | `{"true":"材料里直接有答案","false":"材料不足或需要人表态"}` |
| `candidate` | choice | state.local_candidates 里哪一条最可能承载答案？ | **由 state 渲染**：`{"c1":"…heartbeat…","c2":"…timi-decisions-api…","c3":"…budget-guard…"}` |

### jev 的反馈（`response-b.json`：HTTP 200，1184 ms）

```json
{"model":"jev-latest",
 "answers":{
   "answer_kind":{"type":"choice","choice":"fact","confidence":0.55,
                  "probabilities":{"fact":0.70,"intent":0.29,"reuse":0.01}},
   "answerable":{"type":"noul","noul":0.29},
   "candidate":{"type":"choice","choice":"c2","confidence":0.98,
                "probabilities":{"c1":0.0,"c2":0.99,"c3":0.01}}},
 "usage":{"input_tokens":913,"output_tokens":96,"cached_tokens":0,"cache_write_tokens":0},
 "id":"gen-dec-1792553273-75IHdrYvYLHfnBuFhqBz"}
```

即：**答案在材料里（fact 0.70）**、**候选 c2（0.99 概率）**——正是那个讲 `/v1/decisions` 的文件；
但 **自评「凭现有材料能否确定回答」只有 0.29**，因为它只看到文件名、没看到文件内容。

### 接收 → 判定（`outcome-b.json`）

```json
{"status":"escalated","escalated_reason":"low-confidence",
 "answer":{"answer_kind":{"value":"fact","confidence":0.61},
           "answerable":{"value":0.28,"confidence":null},
           "candidate":{"value":"c2","confidence":0.98}},
 "response":{"available":true,"transport":"timi-decisions","model":"jev-latest",
             "confidence_source":"api","attempts":1,"latency_ms":990,"reason":null}}
```

两道闸串联，且都不许「猜」：

1. **Python 侧**（`decision_points.decide_for` 步 8）：聚合置信 = 各题 `confidence` 取 min（`answerable` 无
   `confidence` 不计），`0.61 < min_confidence 0.7` → `escalated / low-confidence`，`acted=false`，档案落一行
   （hash 链 `seq/prev_sha`），`mw decide run` 回 `{available:false, answers:null, escalated_reason:"low-confidence"}`。
2. **TS 侧**（`worker-mode.ts` `dp3AskDecision` 3a）：若上一步通过，还要
   `answerable ≥ DP3_ANSWERABLE_MIN(0.5)`；本例 0.28 → `escalate("unavailable", "3a", "model reports unanswerable (0.28)")`，
   即**不上抛人、也不拿它当答案**，worker 继续按人工/其它路径走。

### 如果它通过了，答案怎么被"应用"（本地取文本，模型不造句）

`resolveDp3CandidateAnswer`（`worker-mode.ts:4953`）：

1. 取模型选的 `candidate` id（`c2`）；
2. 本地打开 `evidence/research/spec-timi-decisions-api-20261021.md`；
3. 用问题里的锚词逐行匹配，命中行截 200 字符 → `answer = "<该行文本> (evidence/research/spec-timi-decisions-api-20261021.md:1)"`；
4. `source` 由 `DP3_CITATION_RE` 从这段本地文本里捕获；
5. 以 steer 形式回灌 worker（`formatDp3AnswerSteer`，明确标注"非人工输入、decision_id=…"），并写
   `[DECISION] dp3 acted=1 decision_id=…` 到 trace。

**模型的自由文本一律不进 `answer`**——它只做两件事：判定可答性、在候选里点名。

---

## 全链路（一次调用的九步）

| 步 | 位置 | 做什么 | 失败时 |
| --- | --- | --- | --- |
| 1 | `decision.DecisionConfig.from_project` | 读 `.mw/decide.json`（`enabled/transport/model`），mtime 变了就重读 | `enabled=false` → `disabled`，零 HTTP |
| 2 | `decision_points.get_decision_point` | dp 注册表查 id / tier / 题型 | 未注册 → 拒 |
| 3 | `decide_for` 步 6 | `_fit_state` 截断（≤ `max_state_bytes`） | `input-oversize` |
| 4 | 同 | `_validate_input` 必需字段 + `dynamic_choices` 可渲染 | `input-incomplete`（零 HTTP） |
| 5 | `decision_backends._http_post` | 单次 POST（`timeout_s`，429/5xx 才重试，带 `retry-after`） | `timeout` / `upstream-error` / `rate-limited` |
| 6 | `_classify` | 2xx 且 body 带 `error` → 判错（实测见附录） | `upstream-error`，**绝不**当成功 |
| 7 | `_decode_answers` | 按题型解码 + 成员校验 + `model` 校验 | `bad-response` |
| 8 | `decision.DecisionClient._normalize_answers` | 只保留请求过的 qid，`confidence` 夹到 0..1 | `bad-response` |
| 9 | `decide_for` 步 8 + 档案 | 值合法性（`_value_fits`，动态题按渲染 id）、置信门控、`acted`、hash 链落档 | `low-confidence` / 上抛 |

---

## 附录 A：真实遇到的两件事（都已在代码里修）

1. **HTTP 200 + `{"error": {...}}`**：jev 网关的校验失败也回 200，body 是
   `{"error":{"message":"Invalid Decisions request: … questions.dept.choice.criteria 至少 1 项","code":"304"}}`。
   `_classify` 认得这种形状（`parsed["error"]` 非空 → 按 body 分类），所以不会被当成"成功但没答案"。
2. **`choice` 的 `criteria` 被重建丢了**：调用方按官方形状直接给 `criteria` 时，后端曾按
   `choices`/`labels` 重建 → 空对象 → 上面那个 200-with-error。已改为**调用方 `criteria` 优先、逐字透传**
   （`decision_backends.py:_choice_criteria`），并加两条用例：`caller_supplied_choice_criteria_is_used_verbatim`、
   `dynamic_candidates_override_declared_criteria`；`test_decide_backends.py` 59 passed。

---

## 不 build 是否能生效

| 能力 | 位置 | 需要 `mw build --install`？ |
| --- | --- | --- |
| `mw decide ask` / `run` / `sign`（人跑决策） | Python CLI（`packages/multi-workers/mw.py`） | **不需要**，每次都是新进程，改完即生效 |
| done 门禁的签收校验（a+b 的 b） | Python（`advance_phase.py` + `decision_points/decide_archive`） | **不需要** |
| 决策档案 / 证据行 / hash 链 | Python | **不需要** |
| worker 自动问 jev（dp1/dp2/dp3 注入、steer 回灌、`[DECISION]` 行） | TS 扩展（`worker-mode.ts` / `triage-client.ts`） | **需要**（pi 加载的是构建产物） |
| TS 消费逻辑本身是否成立 | `npx vitest --run test/suite/dp3-answer.test.ts` 等 | **不需要**（vitest 直接跑 TS 源码） |

因此：签收门禁这一整条（`a+b`）不 build 就能用；"worker 在真实会话里自动采纳 jev 的答案"这一步才需要
`mw build --install`。
