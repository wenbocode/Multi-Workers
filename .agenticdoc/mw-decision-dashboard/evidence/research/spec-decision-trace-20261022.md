# RQ-2：决策证据链与吸收链（只读调研）

> 卡片：`tasks/RQ-2-trace.md`；目标：`.agenticdoc/goal.md`；需求：`.agenticdoc/mw-decision-dashboard/spec.md`
> 结论口径：只读代码 + 本仓既有样例（`.agenticdoc/_autopilot/*.jsonl`、`*/evidence/review/sign-final.md`、`*/workers/*/task.md`、`*/workers/*/trace.log`）。未发任何网络请求，未调用真实模型（唯一执行的是 `decision.FakeBackend` 的内存单测式验证，零 HTTP），未改代码/配置/档案。
> 证据不复制任何 secret：本文件只引用字段名、枚举值与代码位置。

## 0. 摘要（先看这 8 条）

1. **原始请求/原始返回全程不落盘。** 档案只存 `state` 的 16 位摘要（`decide_archive.py:260-266`：`sha256(decision._encode_state(state))[:16]`，"The raw state is never written to the archive"），返回体在 backend 解码后即被归一化成 `{value, confidence}`（`decision.py:1158` `_normalize_answers`），`usage`/`probabilities`/`legend`/HTTP 头/状态码/重试细节都不持久化。任何"实际请求/实际返回详情"页面只能用 **digest + 归一化答案 + 版本号 + 传输元数据** 诚实拼装，不得自称原文。
2. **`decision_id` 是权威关联键，但只覆盖三面**：`decisions.jsonl`（decide/settle/authority-change）、`settle` 行、`task.md` 的 `decision:` 头、`trace.log` 的 `[DECISION]` 行。**`triage-decisions.jsonl` 没有 `decision_id`、也没有 `state_digest`**（字段表 `decision.py:234`），所以"模型调用证据 ↔ 档案行"只能按 `(ts, dp, latency_ms, attempts, answers)` 推断；本库 9 条 decide 行全部能推断命中（ts 秒级完全相等、latency_ms 完全相同），但这是**推断**，不是权威。
3. **schema 里预留的 join 字段是空转的**：`evidence_line`（指向 triage 证据行号）与 `cost_tokens`（token 用量）在 `_ROW_FIELDS` 里存在（`decide_archive.py:119,127`），但生产写入者从不传——本库 9/9 decide 行两者皆 `null`，`_archive_decision`（`decision_points.py:2023`）也不传。
4. **dp1 的 trigger 是 key，不是派发**：`Trigger.resolved_id()` 的兜底链是 `trigger_id → task_key → key → ts`（`decision_points.py:222-227`）。dp1 在派发前没有 task_key，于是同一 key 下所有派发共享同一个 `decision_id`，档案按 `duplicate="existing"` **重放首次行**（`decision_points.py:_archive_decision` 固定 `duplicate="existing"`；`decide_archive.py:684` 命中则原行返回、零写入）。本库实测：**30 条 dp1 调用证据 ↔ 1 条 dp1 decide 行**（ts=2026-10-21T07:04:42Z），后 29 次调用的 digest/答案在档案里不存在。
5. **生产代码里没有 `intent="act"` 调用点**（`mw.py:983-985`、`decide_signoff.py:421-427` 都是 `intent="answer"`）→ 档案 `acted=true` 结构上不可达（本库 9/9 `acted=false`）。真正的"吸收"发生在 TS 侧：`task.md` 的 `decision:` 头、`steer-dp2.md`、`trace.log` 的 `[DECISION]` 行，档案不记录。
6. **人工覆盖没有写入者**：`append_override` / `append_settle` 只有库函数（`decide_archive.py:1024,1069`），全仓非测试代码零调用；`settle` 的唯一生产写入者是 TS 侧 PM 轮询（`pm-orchestrator.ts:986-1024` 用 `python -c` 调 `append_settle`，`settled_by="pm-auto"`）。本库 override=0、settle=5（全 pm-auto），`settled_by="human"` 无路径。
7. **"人工决策"只能从 authority 面推断**：`authority-change` 的 `by ∈ {human, human:p0-confirm, signoff:continue|narrow|revoke, refresh}`（`decide_archive.py:_CHANGE_BY`，`mw.py:3971`）。本库 29 条 authority-change 中 **25 条是 `by=refresh`（机器刷新 dp 表）**，3 条 `signoff:narrow`、1 条 `signoff:continue`，`by=human*` 0 条。看板必须把 refresh 标成机器动作。
8. **决策本引用历史为空**：`book-receipts.jsonl`（`decision_book.py:139`）在本库不存在，`.agenticdoc/**/evidence/books/` 也无任何 book 文件；档案本身无 book 字段（封闭字段矩阵 `decide_archive.py:91`）。→ 历史 book 关联 0 条，不可回填，只能向前记录。

---

## 1. 问题

spec §2/§3 要求看板做到：按项目列出决策并区分自动/人工来源（AC-002）；自动决策详情展示"决策本、实际请求、实际返回、吸收与应答，且同一次决策标识"（AC-003）；调用详情不含凭证值（AC-005）；缺失字段明确标示（§2 "历史记录缺失字段须明确标示，不猜测或伪造"）。本卡只回答**是否记录得下来**，以及**记录不下来的部分如何诚实显示/可否回填**。

## 2. 方法与取证路径

只读手段：全文阅读 6 个 Python 模块 + 4 个 TS 模块；用 `python -c` 对既有 jsonl/md 做聚合统计（不含 secret，不打印答案原文里的人物/路径文本）；用 `decision.FakeBackend` 在临时目录验证"返回体是否原样留档"（内存，零 HTTP）。

| 事实 | 位置 |
| --- | --- |
| 档案字段矩阵（38 列，含 `evidence_line`/`cost_tokens`/`policy`） | `packages/multi-workers/decide_archive.py:91-133` |
| 行校验（`policy` 白名单、`answer` 形状、`authority`/`escalated_reason` 互斥） | `decide_archive.py:321,349,375` |
| `state` 只落 16 位摘要 | `decide_archive.py:260-266`；`decision._encode_state` `decision.py:572` |
| 追加/去重/重放 | `decide_archive.py:637-707`（`684` 是 `duplicate="existing"` 分支） |
| 读侧 fold（outcome=最后一条 settle；override 计数；`base_missing`） | `decide_archive.py:765,840-940` |
| 四个 append 入口 | `decide_archive.py:948,1024,1069,1110` |
| triage 证据字段表（11 列，无 id/digest/detail） | `decision.py:234-246`；写入 `decision.py:1227-1262` |
| 凭证脱敏（env key/`Bearer`/`sk-`） | `decision.py:531`（`_redact`）、`decision.py:1227` |
| 响应归一化（丢 `probabilities`/`legend`） | `decision.py:1158-1184` |
| 请求体构造（`{model,state,questions}`，state 原样） | `decision_backends.py:612-625` |
| 响应解码（保留 probabilities/legend，丢弃 `usage`） | `decision_backends.py:627-718` |
| HTTP 失败细节（`HTTP <status> content-type=… body=<body>`） | `decision_backends.py:348`：只进 stdout/stderr，不入库 |
| 决策点授权链（11 步、intent、archive 行） | `decision_points.py:2278-2720`；`_archive_decision` `2023-2100` |
| trigger → decision_id | `decision_points.py:179-227` |
| 注册表导出（`wired`=TS 调用点；`executor`=Python 执行器） | `decision_points.py:938-1010` |
| 决策本验收/回执 | `decision_book.py:139,549,1067,1088,1107` |
| CLI 面（run/ask/show/report/sign/dp） | `mw.py:911,1631,1088,3438,3784,4018` |
| `--book` 回执（best-effort，`state_digest` 无 state） | `mw.py:1499,1531` |
| settle 生产写入者（JSON on stdin → `append_settle`） | `pm-orchestrator.ts:806-830,855-888,942-984,986-1044,1059-1150` |
| `decision:` 头写入（acted 门槛在调用方） | `ui-bridge.ts:290-304,2289-2314,3034` |
| triage 调用 + ledger 行 | `triage-client.ts:161-220,258-284,863-950`；`ui-bridge.ts:593-660`；`formatTriageLedgerDetail` `triage-client.ts:969` |
| dp2 steer + trace 吸收 | `pm-orchestrator.ts:1969,2336-2474,2476`；`worker-mode.ts:3256-3300` |
| dp3 采纳 + trace 吸收 | `worker-mode.ts:4143-4245`（`4222` 是 `[DECISION] dp3 acted=1 decision_id=…`） |
| `ask_decision` 工具 trace 行（含 decision_id/mode/acted） | `decision-tool.ts:841-849` |
| 签收（`signed_via`、`rows_sha256`、verdict） | `decide_signoff.py:110-121,287-340,450-500,514-640,665-700`；`mw.py:3784-3995` |

### 2.1 本库实测计数（2026-10-22 快照）

| 面 | 数量 | 说明 |
| --- | --- | --- |
| `decisions.jsonl` | 43 行（seq 1..43，链完整） | decide 9 / authority-change 29 / settle 5 / override 0 |
| decide 分布 | dp1 1、dp3 1、dp7 1、dp25 6 | 9/9 `available=true`、9/9 `acted=false`、9/9 `confidence_source=api`、9/9 `mode=auto` |
| decide 授权 | advisory 6、human 3 | 3 条 `escalated_reason=low-confidence`（conf 0.46/0.53/0.19） |
| decide 新列 | `policy` 7/9、`evidence_line` 0/9、`cost_tokens` 0/9 | 旧行连 `policy` 键都没有（读侧必须容忍缺键） |
| authority-change | refresh 25、signoff:narrow 3、signoff:continue 1、human* 0 | 4 条带 `note`（`signed_via=auto-decide`×3、`signed_via=auto-llm; decide_fallback=…`×1） |
| settle | 5 行，全 `pm-auto`、`evidence_ref=<task_key>@<run_id>`、`task_key` 非空 | 只覆盖 dp1 |
| `triage-decisions.jsonl` | 95 行、26 个 dp 标签 | dp1 30、dp-human-ask 10、dp25 6；含 1 条 off-triple 旧行（`transport=llm-transitional`、`model=glm-5.3-flashx`、`reason=disabled`） |
| `task.md` 的 `decision:` 头 | 5 个任务卡，全部 `dp1-dispatch-type:mw-decision-substitution` | 与 5 条 settle 行一一对应 |
| `sign-final.md` | 3 个（narrow×3，`signed_via=auto-decide`；`counted_rows` 0/0/2） | 无人工 `cli/tui` 签收 |
| `book-receipts.jsonl` / book 文件 | 0 / 0 | 决策本链路历史零数据 |
| `auto-decisions.jsonl`（ledger） | 37 行，其中 `triage-suggestion` 23 | 列只有 `seq/phase/kind/count/detail`，detail 含 `triage_type/dispatched_type/disagreement`，**无 decision_id** |

## 3. 持久化面清单（谁写、写什么）

| 面 | 写入者 | 内容 | 是否权威 |
| --- | --- | --- | --- |
| `.agenticdoc/_autopilot/decisions.jsonl` | 唯一 Python 写入者 `decide_archive.py`（锁 + hash 链）；settle 由 TS 经 `python -c` 委派 | 4 种行；decide 行含 `state_digest/questions_version/available/answer/authority/escalated_reason/acted/actual_action/mode/model/transport/attempts/latency_ms/confidence/confidence_source/policy/note` | 是（正确性依赖，失败即 exit 2） |
| `.agenticdoc/_autopilot/triage-decisions.jsonl` | `decision.py:_append_evidence`（best-effort，失败静默） | `ts/dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source` | 否（审计旁证；无 id/digest/detail，无 schema 版本） |
| `<key>/evidence/review/sign-final.md` | `mw decide sign`（人工/自动两条路） | 机器行 `conclusion/counted_rows/rows_sha256/engine/allow_empty/key/claim/ts/reason/promote/demote/p0-open/signed_via/decide_fallback` + 人类表格 | 是（done 门禁按 `rows_sha256` 复算） |
| `.agenticdoc/_autopilot/book-receipts.jsonl` | `decision_book.append_book_receipt`（`mw decide run/ask --book`） | `ts/dp/decision_id/book_path/file_sha256/evidence/state_digest/available/reason/transport` | 旁证（回执写失败只提示） |
| `<key>/workers/<task>/task.md` `decision:` 头 | `ui-bridge.mergeDecisionHeader`（派发时） | `<dp>:<trigger_id>` | 关联声明，不是授权证明（见 §5.3） |
| `<key>/workers/<task>/trace.log` | worker/PM | `[DECISION] dp2 consumed=1 decision_id=…`、`[DECISION] dp2 acted=1 decision_id=…`、`[DECISION] dp3 acted=1 decision_id=…`、`[DECISION] <iso> dp=… trigger=… decision_id=… mode=… acted=… source=… latency_ms=…`、`[DECISION_UNAVAILABLE] …` | 吸收旁证（未索引） |
| `<key>/workers/<task>/steer-dp2.md` | PM（原子 rename） | 首行含 `decision_id=… dp=… risk=… elapsed/budget/remaining` | 吸收契约（dp2 narrow 的载体） |
| `.agenticdoc/_autopilot/auto-decisions.jsonl` | PM ledger（best-effort） | `triage-suggestion` 行 detail（无 decision_id） | 旁证（不得当主键） |

## 4. 记录矩阵（已记录 / 未记录）

### 4.1 看板"决策详情"需要的字段

| 展示项 | 档案 decide 行 | triage 证据 | 其它面 | 结论 |
| --- | --- | --- | --- | --- |
| `decision_id` | ✔ 9/9 | ✘（无该列） | ✔ settle/sign 锚 dp、trace 行、task.md 头 | 主键可用，但调用证据侧无主键 |
| dp / trigger | ✔（id 两段） | ✔ dp（trigger 无） | ✔ | 可用 |
| key / task_key | key ✔；task_key 仅 decide/settle | ✘ | task.md 路径含 key | 可用（authority-change 恒 `task_key=None`） |
| 时间 | ✔ ts 秒级 | ✔ ts 秒级 | trace 毫秒级 | 可用；两侧秒级同秒是推断关联的基础 |
| 决策本（path+sha256） | ✘ 无字段 | ✘ | ✔ 仅 `book-receipts`（本库 0） | **未记录** |
| 问题集 | 仅 `questions_version`（q-8hex） | ✘ | 注册表现值 | 版本可比对，历史问题文本不可还原 |
| 实际请求 state | **仅 16hex `state_digest`** | ✘ | ✘ | **原文未记录**；截断丢弃的字段名只在内存 |
| 实际响应体 | ✘（只有归一化 `answer`） | ✔ 同归一化 answer | ✘ | **原文未记录** |
| `answer.value/confidence` | ✔ | ✔ | — | 已记录 |
| `probabilities/legend` | 结构上可带（校验只要求 value/confidence，多余键不校验）；本库 0 | 本库 7 行历史数据带（旧版本），当前版本会被 `_normalize_answers` 丢弃 | — | 版本漂移，读侧须容忍 |
| transport / model | ✔ | ✔ | sign 的 `engine:` 是常量 | 已记录（含旧 off-triple 值） |
| attempts / latency_ms | ✔ | ✔ | — | 已记录 |
| reason / escalated_reason | ✔ | reason ✔ | — | 已记录 |
| confidence / confidence_source | ✔ | ✔ | — | 已记录（`unknown` 表示未标注） |
| 授权：authority/mode/acted/actual_action | ✔ | mode/acted 只在调用侧 | trace `acted=1`（TS 采纳） | 档案 `acted` 恒 false，采纳在 TS |
| 有效 policy（min_confidence/max_questions/timeout_s） | ✔ 7/9（旧行缺键） | ✘ | `decide show`/`dp show` 可现算 | 需容忍缺键 |
| token 用量 | `cost_tokens` 字段存在但恒 null | ✘（`usage` 解码即丢） | usage 台账只覆盖 pi 会话的 LLM 调用，不含 Python decision 调用 | **未记录** |
| HTTP 状态/头/重试细节 | ✘ | ✘ | detail 只出现在 stdout/stderr | **未记录** |
| 人工 override（by/reason/ref_seq） | 字段齐（`decide_archive.py:1024`） | — | 无 CLI/TS 写入者 | **无路径**（本库 0 行） |
| settle outcome/settled_by/evidence_ref | ✔ 5 行 | — | — | 仅 `pm-auto`；`human` 无路径 |
| 吸收（是否被消费） | ✘ | ✘ | task.md 头、steer-dp2.md、trace `[DECISION]` | **档案未记录** |
| 签收（结论 + 来源） | authority-change `by=signoff:*` + note `signed_via` | — | `sign-final.md`（含 `rows_sha256`） | 已记录 |
| 测试/人工提问调用（`dp-human-ask`） | ✘（无档案行） | ✔ 10 行 | — | 只有调用证据，无决策标识 |

### 4.2 行级语义陷阱（看板必须区分）

- `available=true` ≠ 被采用：3 条 low-confidence 行 `available=true` 但 `authority=human`、`escalated_reason=low-confidence`、`answer` 仍存在。
- `mode=auto` ≠ `acted=true`：9/9 `mode=auto`，9/9 `acted=false`；`intent="answer"` 的 auto 决策按建议归档（`decision_points.py:2558-2600`，`note="intent=answer"`）。
- `acted=true` 当前不可达：无 `intent="act"` 调用点；dp1..dp24 的执行器是 `_unwired_executor`（必抛 `NotImplementedError`，`decision_points.py:427-445`），只有 dp25 是 echo 型 `wired`（`decision_points.py:445-469`）。注册表导出的 `wired: true`（`decide_registry.json`）指 **TS 调用点存在**，不等于可执行。
- `outcome` 只有 `settle` 能改：decide 行恒 `pending`；fold 取**最后一条** settle（`decide_archive.py:840-940`）。
- 孤儿行：只有 override/settle 而缺 decide 行时 `base_missing=true`，行仍参与统计。

## 5. 关联 ID 与因果链

### 5.1 `decision_id = <dp>:<trigger_id>`（首冒号切分）

- trigger 解析：`Trigger.resolved_id()` = `trigger_id | task_key | key | ts`（`decision_points.py:222-227`）。
- 真实取值：dp1=key（派发前无 task_key）；dp3=`<task_key>#nc<N>`；dp2=`<task_key>#ckpt<N>`；dp25=`<key>@<iso>`（`decide_signoff.auto_conclusion`）；signoff 审计行=`signoff@<key>@<ts>`；refresh=ISO 时间戳。
- 幂等语义：同一 `decision_id` 只允许一条 decide 行；重复走 `duplicate="existing"`，返回原行且 `created=false`，`_outcome` 只在**内存 detail** 里追加 `note=duplicate-replay`（`decision_points.py:2128-2135`），档案字节不变。
- 后果：**dp1 的 decision_id 不是"一次派发"，而是"一个 key"**。看板若按 decision_id 计数会自动把 30 次调用折叠成 1 条。

### 5.2 跨面 join 表（可用 / 不可用）

| 想连的两面 | 可用键 | 强度 |
| --- | --- | --- |
| archive decide ↔ settle | `decision_id` | 权威 |
| archive ↔ task.md `decision:` 头 | `decision_id` | 权威，但头本身只声明关联（见 5.3） |
| archive ↔ trace `[DECISION]` 行 | `decision_id` | 权威（但 trace 无全局索引，需按 key/task 目录扫） |
| archive ↔ sign-final.md | `rows_sha256`（对 key 的 decide 快照复算） | 权威、可复算；不含 settle/override，排除 dp25 行 |
| archive ↔ authority-change(signoff) | `key` + `ts` + `note.signed_via` | 权威（同一 `ts` 写入） |
| archive decide ↔ book receipt | `decision_id` + `state_digest` | 权威（仅 `--book` 路径且回执写得下） |
| archive decide ↔ triage 证据 | **无显式键**；只能 `(ts 秒, dp, latency_ms, attempts, answers)` 推断 | 推断（本库 9/9 命中，但不能当权威，ts 秒级碰撞与重放会误配） |
| archive ↔ ledger `triage-suggestion` | **无**（detail 无 id） | 不可连（只能按时间/phase 猜） |
| archive ↔ trace `[DECISION] dp1 state=structured` | 无 id | 不可连（只有 state 形态与字节数） |

### 5.3 `decision:` 头的真实含义（重要）

`ui-bridge.dispatchDecisionOf` 的准入是 `available && mode==="auto" && triage_type===dispatchedType && decision_id 非空`，随后**无条件**构造 `{decisionId, acted:true}`（`ui-bridge.ts:290-304`），完全不看 `TriageResult.acted`。因此一条 `authority=human / escalated_reason=low-confidence / acted=false` 的 dp1 决策**也会**把头写进 task.md（本库正是这种情形：唯一的 dp1 档案行是这个状态，而 5 个任务卡都带该头）。→ 看板不得把 `decision:` 头当作"自动生效"证据；它只证明"当时 mode=auto 且建议类型与派发类型一致"。

## 6. 吸收（adoption）链

| 决策点 | 吸收动作 | 落盘证据 | 与档案的关系 |
| --- | --- | --- | --- |
| dp1 派发 | 派发类型不因建议而改写（AC-014）；建议只进 ledger | `auto-decisions.jsonl` 的 `triage-suggestion` detail（含 `disagreement`） | 档案 `acted=false`；头按 5.3 写或不写 |
| dp2 检查点 | `narrow` → 写 `steer-dp2.md`（原子 rename）→ worker 注入并回写 consumed 标记 | `steer-dp2.md` 首行 `decision_id=`；`trace.log` `[DECISION] dp2 acted=1 …` / `[DECISION] dp2 consumed=1 … via=… marker=ok|failed` | 档案决定行 `acted=false`（intent=answer）；采纳事实只在 TS |
| dp3 澄清 | `auto` 答案 → 注入 follow-up steer | `trace.log` `[DECISION] dp3 acted=1 decision_id=…`、`[DECISION] dp3 detail=…`、`[DECISION_UNAVAILABLE]/[DECISION_RETRY_STOP]`（`ask_decision` 工具） | 同上；`nc_raw/nc_human` 计数只在 trace |
| dp25 签收 | 结论回显 → `mw decide sign` 写 `sign-final.md` + `authority-change` | `sign-final.md`（`conclusion`/`signed_via`/`rows_sha256`）；authority-change `by=signoff:<c>` + note | 档案有 dp25 建议行（advisory）与签收审计行，二者不互相计数 |

要点：**"决策被吸收"目前没有统一字段**，三种载体（task.md 头、steer 文件、trace 行）各写一份，且都不带"吸收时间/吸收结果"。看板要么逐载体读取并标注来源，要么显示"档案无吸收记录（见 trace）"。

## 7. 历史回填可行性（逐项）

| 目标 | 可行性 | 依据与风险 |
| --- | --- | --- |
| 回填原始请求 payload | **不可行** | 从未持久化；`state_digest` 单向 |
| 回填原始响应体（含 usage） | **不可行** | backend 解码后丢弃 `usage`，客户端再归一化 |
| 回填 `probabilities/legend` | 部分（仅历史 triage 行自带） | 7 行旧数据有；当前版本不写；不得据"缺"推断"模型没给" |
| 回填 HTTP 状态/重试链 | **不可行** | 只在 detail 字符串里，未入任何文件 |
| 回填 decide 行 ↔ triage 行关联 | 条件可行（推断） | 用 `(ts 秒相等, dp, latency_ms, attempts, answers 全等)`；本库 9/9 命中；必须标 `inferred` |
| 回填被重放吞掉的 29 次 dp1 调用 | **不可行**（作为档案行） | 无 decide 行；只能在看板显示"调用证据（无档案行）"，并解释 duplicate 语义 |
| 回填 book 引用 | **不可行** | 无回执、无 book 文件、档案无该字段 |
| 回填 override / 人工 settle | **不可行**（且禁止猜） | 无写入者；`_validate_row` 要求 human 身份，但没人写过 |
| 回填签收 ↔ 决策快照 | **可行且可验证** | 按 `decide_signoff.collect` 的字段子集复算 `rows_sha256`，与 sign 文件比对；不匹配即"档案已被追加" |
| 回填 decision_id 到 ledger | **不可行** | ledger detail 无该字段，历史行无法分辨同 key 的多次派发 |
| 修补 `evidence_line`/`cost_tokens` | 仅向前 | 需写入者改造（`_archive_decision` 传参 + 客户端保留 usage），历史不可补 |

## 8. 脱敏风险（AC-005）

| 面 | 是否可能含凭证 | 现有防护 | 结论 |
| --- | --- | --- | --- |
| `decisions.jsonl` | 低 | 不存 state（仅 digest）；answer 值受 enum/数值校验；`note`/`actual_action`/`change` 均代码生成 | 结构上安全；**例外**：`override_reason`（人工自由文本，`_validate_row` 只要求非空） |
| `triage-decisions.jsonl` | 低 | `transport`/`model` 过 `_redact`；`detail`（含 HTTP body）**不写**；answer 受归一化 | 安全；但 answer 值本身未过 `_redact`（enum 约束下风险低） |
| `book-receipts.jsonl` | **中** | `check_book` 的 `_check_secrets` 只扫 `state` 与 `context`（`decision_book.py:1019-1060`），**不扫 `notes.evidence`**；回执把 `evidence` 原样复制（`decision_book.py:1107-1140`） | `cmd:` 形式的证据若内联凭证会入账；`book_path` 在 `resolve_repo_root` 失败时回退绝对路径（`book_meta:1088-1105`） |
| `sign-final.md` | 中 | `reason:` 是 `--reason` 人工自由文本；`decide_fallback:` 已压成单行 | 需展示前脱敏 |
| `trace.log` / `steer-dp2.md` | 低 | 只写 decision_id/计数/mode；steer 文本是固定文案 | 安全 |
| 终端输出（`decide ask` 失败 stderr、`decide run` detail） | 高（可能含 HTTP body） | `_sanitize` 只替换本次 secret 并截 200 字符 | 不落盘；看板/测试页若转发 stderr 必须先脱敏（AC-005 的关键风险点） |

## 9. 未知来源如何诚实显示（规则建议）

1. **字段缺失**：显示 `未记录`（不是 `-`、不是空），并注明"该字段在设计上不持久化"或"该行写入于字段引入之前（缺键）"。
2. **`mode` 缺失**：显示 `mode=unknown`；不得按 registry 默认补 `auto`（`DecisionOutcome.mode` 默认值只是数据结构默认，不代表记录）。
3. **`acted` 与吸收**：分别显示两列——`档案 acted`（false/true/未记录）与`吸收证据`（trace/steer/task 头/无）。不得把 mode=auto 或 task 头换算成 acted。
4. **`confidence_source`**：`api` 可作判据；`model-self-report` 标"自报、不作门控"；`unknown` 标"未标注"。三者在 `triage-client.ts:945-960` 已有措辞范式。
5. **transport/model 非当前三元组**：逐字显示（如 `llm-transitional` / `glm-5.3-flashx`）并标 `legacy/off-triple`；`decide_signoff.TRUE_ENGINE` 明示只有 `timi-decisions/jev-latest/api` 算真引擎。
6. **调用证据无档案行**：标 `call-only (duplicate-replay)`，并说明"档案按 (dp,trigger) 幂等，本行不是首次调用"。
7. **档案行无调用证据**：标 `archive-only`（可能写入于 triage 证据启用前，或证据写失败——证据是 best-effort）。
8. **推算关联**：标 `inferred(ts+latency+answers)` 并给出所用匹配字段；永不显示为权威。
9. **签收 `engine:` 行**：narrow/revoke 的 verdict 只校验链不校验引擎（`decide_signoff.py:450-500`），故显示为"文件声明值"，continue 才显示"已校验"。
10. **`refresh` 行**：显示为"机器刷新 dp 表（registry→table）"，不得计入人工决策。
11. **计数口径**：`decision_id` 去重计数（决策数）与 triage 行计数（调用数）分开显示，并显式给出 `calls_without_decision_row` 差额。

## 10. 结论 → spec 映射

| spec 项 | 现状能否满足 | 依赖/缺口 |
| --- | --- | --- |
| AC-002 按项目列出所有已记录决策，来源可证实、未知即未知 | **可满足（读档案 + 4 类来源标签）** | 来源标签：`archive.decide`（模型建议/上抛）、`archive.authority-change`（人工/签收/机器刷新）、`archive.override`（当前无）、`sign-final.md`；须区分 `by=refresh` |
| AC-003 同一决策标识展示决策本/实际请求/实际返回/吸收/应答 | **部分满足** | 应答=answer ✔；吸收=trace/steer/头（非档案）✔但需二次读取；**实际请求/返回原文不可得**，只能 digest+归一化答案+版本；决策本历史 0 条（需向前记录 receipt） |
| AC-004 测试页走真实调用并展示真实返回 | **可满足** | 走 `mw decide run --dp … --book …` 最完整（archive 行 + book receipt + triage 证据）；若用 `decide ask` 则只有 triage 行、无 decision_id。**注意 trigger 必须每次唯一**（否则 duplicate 重放，返回的 decision_id 是旧的） |
| AC-005 详情/落盘不含凭证 | **可满足但需看板侧补齐** | 档案/证据结构上安全；风险集中在 book receipt 的 `evidence`、`sign-final.md` 的 `reason`、以及测试页转发 stderr detail |
| §2 "缺失字段明确标示，不猜测" | 需设计约束 | 见 §9 的 11 条显示规则 |

对看板/测试页的最小数据契约（建议写入 spec/design）：
1. 权威源固定为 `decisions.jsonl`（fold：`decide_archive.fold`），旁证源为 `triage-decisions.jsonl`、`sign-final.md`、`book-receipts.jsonl`、`task.md`/`trace.log`；每行标注来源与证据强度。
2. 每条详情固定 6 段：标识（decision_id/dp/trigger/key/task_key/ts）｜授权（authority/mode/acted/policy）｜调用（transport/model/attempts/latency/confidence/source/questions_version/state_digest + 关联的 triage 行）｜应答（answer）｜吸收（settle + trace/steer/头）｜缺口（未记录字段清单）。
3. 测试页每次提交必须生成唯一 `trigger_id`（例如 `<key>#test@<iso>`）；`intent="answer"` 语义在 UI 上明示"只取判断、不执行业务动作"。

## 11. 残留与未验证

- **本卡未验证运行时行为**：没有实跑 `mw decide run/sign/dp`（禁网），`duplicate-replay` 的 stdout 形状、`mw decide dp list` 的入口差异均按代码推断（后者属 RQ-1）。
- **未验证 `_validate_answer` 对多余键的容错是否稳定**（本卡只读到它不校验未知键；`probabilities/legend` 能否进入 archive 取决于是否有人绕过 `_normalize_answers`）。
- **未验证 dp2/dp3 吸收行的真实存量**：本库 trace.log 未逐文件统计（worker 目录数量大），只按代码确认写入格式。
- **双 workspace（dual-root）下的 `.agenticdoc` 解析**未展开：`decide_signoff._agenticdoc_root`/`_control_root` 假设 key 目录在 `.agenticdoc/` 下；跨 workspace 时看板取哪一侧未验证。
- **`auto-decisions.jsonl` 的写入方**（`recordDispatchAlarm`）未做全量读取，只确认列结构与 `triage-suggestion` detail 文案。
- **usage 台账**（`usage.py`）确认只扫 pi/claude 会话文件，因此不含 Python decision 调用的 token；未验证是否存在代理层日志可补 token（`.mw/proxy.log` 仅 50B，无内容）。

## 12. 上下文来源

- 卡片：`.agenticdoc/mw-decision-dashboard/tasks/RQ-2-trace.md`；需求：`.agenticdoc/mw-decision-dashboard/spec.md`；目标：`.agenticdoc/goal.md`。
- 代码（全读）：`packages/multi-workers/decide_archive.py`、`decision.py`、`decision_backends.py`、`decision_points.py`（关键段）、`decision_book.py`、`decide_signoff.py`、`mw.py`（decide 相关段）、`packages/coding-agent/src/extensions/agent-team-loop/pm/{triage-client.ts,pm-orchestrator.ts,ui-bridge.ts,decision-tool.ts}`、`worker/worker-mode.ts`（dp2/dp3 段）。
- 样例数据（只读、只聚合）：`.agenticdoc/_autopilot/{decisions.jsonl,triage-decisions.jsonl,auto-decisions.jsonl,timeline.jsonl}`、`.agenticdoc/*/evidence/review/sign-final.md`、`.agenticdoc/*/workers/*/task.md`、`.mw/decide.json`、`.mw/decide-points.json`。
- 历史结论参照：`.agenticdoc/mw-decision-substitution/{spec.md,design.md}`（D-005/D-013/D-041/D-067）、`docs/decision-substitution.md:515`（"没有 `mw decide settle/override` 子命令"）。
