# D-RQ2：真实传输记录与决策生命周期（只读设计研究）

> 卡片 `tasks/D-RQ2-records.md`；spec AC-003/005/012/013/014/016；goal `.agenticdoc/goal.md`。
> 只读：未改代码/配置/档案，未发网络请求，未调用真实模型。行号取自 2026-10-22 工作树，按符号定位优先。

## 0 结论

1. **唯一真实发送边界**是 `decision_backends._http_post`（`decision_backends.py:246`）：请求体在 `:248` 由 `json.dumps(payload)` 生成，响应统一为 `HttpResponse(status, content_type, body, retry-after)`（`:217`），HTTPError 也读 body（`:258-273`）。全仓只有两处调用：真决策 `_post`（`:738`）与健康探测 `probe_matrix`（`:852`）。因此采集点必须落在这里，**不能**在上层重新 `build_payload` 冒充原文字节。
2. 请求原文目前**没有任何持久化**：payload 在 `:802` 生成后只作为内存实参传给 `:803 _post`；档案只存 `state_digest`（`decide_archive.py:260`，`sha256(_encode_state(state))[:16]`），证据行只存归一化答案（`decision.py:234 _EVIDENCE_FIELDS`）。返回原文同样丢弃：`_decode_answers`（`:627`）只保留 value/confidence/probabilities/legend，`usage` 与其后 `_normalize_answers`（`decision.py:1158`）都会丢字段；HTTP 状态/头/重试细节只进 `detail` 字符串（`decision_backends.py:348`），落盘面为 0。
3. **`attempts` 不是 HTTP 次数**：后端 `_post`（`:720`）在 `retry-after` 时自行重试（`:749-758`），客户端 `DecisionClient.decide`（`decision.py:829`）的 `attempts += 1`（`:935`）只数客户端循环。故同一次调用可能有 `attempts=1` 而真实 POST 2 次；`call_id` + `attempt_index` 必须在 `_http_post` 内生成，才能与 `attempts` 分离且不丢失。
4. 结论：**采用案 A（新调用旁账，单写者 Python）**。案 B（扩 `decisions.jsonl`）被三条硬事实否掉：字段矩阵封闭（`decide_archive.py:91 _ROW_FIELDS` + `:948 append_decide` 固定签名）、按 `decision_id` 幂等（`:674` 去重扫描）导致 dp1 的 N 次调用只能挤进 1 行、档案写入 fail-loud（`:637` 起锁+链）而采集必须 best-effort。且 `decide_signoff.collect` 的快照键集就是 `_ROW_FIELDS`（`:287-330`），扩键集会让**所有历史 `rows_sha256` 变化**，直接违反 AC-008。
5. 旁账文件：`.agenticdoc/_autopilot/decisions-wire.jsonl`（跨 key、同目录），单写者 `packages/multi-workers/decision_wire.py`；`mw_common.acquire_lock`（`mw_common.py:2388`）行级锁 + `O_APPEND` 单行写 + `fsync`，失败只告警不改变决策结果。
6. 粒度：`call_id` = 一次 `DecisionClient.decide`（一次逻辑调用）；`attempt_index` = 一次真实 HTTP POST（含后端 retry-after 重试）；`decision_id` = `<dp>:<trigger_id>`（`decision_points.py:222`，幂等、可跨多次调用）；采纳/消费/签收是消费侧事实，另立载体，不换算成 `acted`。
7. 建议/吸收/执行必须三列分离：档案 `acted=true` 在生产中**不可达**（唯一两个调用点都 `intent="answer"`：`mw.py:983`、`decide_signoff.py:421`；`DecisionOutcome.mode` 默认 `"auto"` 只是数据结构默认，`decision_points.py:1967`）。TS 侧 `[DECISION] ... acted=1` 是**消费侧采纳**（dp2 `pm-orchestrator.ts:2480`、dp3 `worker-mode.ts:4222`），不是执行。
8. **settle 矛盾复核：RQ-3 的“无生产 writer”错误**。生产调用链确实存在：`pm-orchestrator.ts:2778`（poll 循环终端转移）→ `:1059 recordDecisionSettle` → `:1004 archiveSettleAppender` → `python -c` 调 `decide_archive.append_settle`（`:986 APPEND_SETTLE_PROGRAM`）；档案 5 条 `pm-auto` settle 行即产物。**override 仍无生产 writer**（`decide_archive.py:1024` 仅测试调用）。
9. 来源语义：`human` / `model` / `system` / `unknown` 一律按**载体字段**判定，不按 mode/available/task 头推断；缺字段显示“未记录”，推断关联显示 `inferred(依据)`，仅调用无决策行显示 `call-only`，仅决策行无调用显示 `archive-only`。
10. 签收边界不动：`rows_sha256` 的键集、`_chain_ok` 的链定义（`decide_signoff.py:243,248`）保持冻结；旁账不参与签收计数，dp25 行本来就被排除（`collect` 过滤 `dp != SIGNOFF_DP_ID`，`:301-315`）。生产门禁零改动。

## 1 事实：所有真实决策发送入口与传输函数

| # | 入口（生产） | 传输函数 | 关联标识 | 落盘证据 | 位置 |
| --- | --- | --- | --- | --- | --- |
| E1 | `mw decide run --dp <id>`（结构化，注册表 dp） | `_http_post` ← `TimiDecisionsBackend.decide` ← `DecisionClient.decide` ← `decide_for` | `decision_id` 服务端算 | 档案 decide 行 + 三态证据行（best-effort） | `mw.py:911,983`；`decision_points.py:2278,2443` |
| E2 | `mw decide run`（legacy：请求自带 `questions`） | 同上传传输但**绕过 `decide_for`** | 无 `decision_id`（dp 标签默认） | 仅证据行 | `mw.py:969` |
| E3 | `mw decide ask`（人面） | `_AskDecisionClient.decide` → `_http_post` | 无 `decision_id`，dp=`dp-human-ask`（`mw.py:1195`） | 仅证据行（+`--book` 回执） | `mw.py:1631,1670` |
| E4 | `mw decide dp verify --live` | `DecisionClient.decide` | 无 `decision_id` | 仅证据行 | `mw.py:2721,2758` |
| E5 | TS dp1（派发前 triage） | 子进程 `mw decide run --dp dp1…` → E1/E2 | `decision_id` | 档案 + 证据 + `task.md` `decision:` 头 + ledger 行 | `triage-client.ts:258,862,874,882`；`ui-bridge.ts:593,621` |
| E6 | TS dp2（检查点） | 子进程 `mw decide run --dp dp2…` → E1 | `decision_id`=`<dp>:<task_key>#ckpt<N>` | 档案 + `steer-dp2.md` + trace | `pm-orchestrator.ts:2336,2435,2697` |
| E7 | TS dp3（澄清） | 子进程 `mw decide run --dp dp3…` → E1；另有 3c 本地匹配零调用 | `decision_id`（服务端或本地构造） | 档案（仅调用路径）+ trace + steer | `worker-mode.ts:4143,5638,5697,5706` |
| E8 | dp25（签收结论） | `decide_signoff.auto_conclusion` → E1（`intent="answer"`） | `decision_id`=`dp25:<key>@<ts>` | 档案 + `sign-final.md` + authority-change | `decide_signoff.py:382,421`；`mw.py:3858,3971` |
| E9 | `ask_decision` 工具（25 dp 任意） | 子进程 `mw decide run --dp … --request-file` → E1 | 服务端 `decision_id` | 档案 + 证据 + trace | `decision-tool.ts:453,582,843` |
| E10 | `mw decide probe` | `_http_post` 直调 | 无 | 无（只打印） | `decision_backends.py:852` |

传输函数只有 `_http_post` 一个（`:246`）；`headers()` 在 `:573` 生成 `Authorization: <key>`（**只能记名字，不可记值**）。E10 不是决策调用，旁账不采集（或标 `kind=probe`，默认不采）。

## 2 传输边界 seam（不重建 payload）

- `attempt-start`：在 `_http_post` 内、`urlopen` 之前写；字段含 `request_bytes = data`（就是实际发出的 UTF-8 字节，`:248`）、`request_sha256`、`request_len`、`url_path`、`model`（取自 payload）、`timeout_s`、`header_names`。这样即使子进程被杀死（TS 侧 20s 硬墙 `decision-tool.ts:86`）也留下“已发出”的事实。
- `attempt-end`：`urlopen` 返回/抛错处写；字段含 `http_status`、`content_type`、`response_bytes`（`HttpResponse.body` 原文）、`response_sha256`、`latency_ms`（本函数内 monotonic 计时）、`error_class`（`TransportTimeout`/`TransportConnectionError`/其他）、`retry_after_s`、`usage`（仅当响应正文自带且可解析，`usage_source=response-body`；否则 `null` + `usage_source=not-recorded`）。
- `call-end`：`DecisionClient.decide` 每个返回点（统一走 `_emit`，`:1182`）写一次；字段含客户端 `attempts`、`wire_attempts`（旁账内该 `call_id` 的 attempt-start 计数）、`latency_ms`（含 backoff 的总时延，`:1195`）、`available`、`reason`、`confidence`、`confidence_source`、`transport`、`model`。`_emit` 已有全部值，无需重算。
- `decision-end`：`decision_points._outcome`（`:2221`）单点写；字段含 `status`、`escalated_reason`、`archive=created|replayed|skipped|failed`、`state_digest`、`questions_version`、`truncated`、`mode`、`intent`。`_maybe_archive` 的 `(archived, replayed)` 正是 `:2137` 返回并传入 `_outcome`，因此重放可被**如实**记录（否则只能推断）。
- 上下文（`decision_id`/`dp`/`key`/`task_key`/`origin`/`book_ref`）由调用方在 `client.decide` 之前放进 contextvar：`decide_for` 已知 `decision_id`（`:2328` 计算、`:2443` 调用）；`mw.py` E2/E3/E4 分别放 `origin=cli-legacy|cli-ask|dp-verify-live` 且 `decision_id=None`；`--book` 时放 `book_path/file_sha256/evidence`（`_book_gate` 返回值，`mw.py:1499`）。E5..E9 的 `origin` 由 `mw decide run --origin` 透传（P1，见 §9）。
- 落盘规则：每次写都在锁内 append 一行 JSON（`ensure_ascii=False`，无内嵌换行），单行上限取自 `.mw/decide.json` extras（`wire_max_bytes`，默认 64 KiB，读侧 `_cfg_get` 已支持 extras：`decision_backends.py:146-162`）；超限截断并写 `truncated=true`、`original_len`。

## 3 schema 两案与推荐

| 维度 | 案 A：新调用旁账（推荐） | 案 B：扩旧 archive schema |
| --- | --- | --- |
| 影响面 | 新文件 + 4 个注入点 | `_ROW_FIELDS`/`append_decide`/`_validate_row`/`fold`/签收快照 |
| 每次调用与每次决策 | 天然 1:N（`call_id`/`attempt_index`） | 只能 1:1（`decision_id` 幂等，`:674`） |
| 采集失败 | best-effort，决策照常 | 档案 fail-loud（`:637`），采集失败会改决策结果 |
| 原文可存 | 可（请求/响应字节 + sha + 截断标记） | 不可：行必须过 `_validate_row` 与链哈希 |
| 签收 `rows_sha256` | 0 变化 | 键集变化即全量变化（`decide_signoff.py:287-330`） |
| 并发 | 锁 + O_APPEND（GC-4） | 已有锁/链可复用，但写入单位仍是一决策一行 |
| 读侧改动 | 新增只读 fold（monitor） | 需同时改 `fold`/`report`/`collect`/导出 |
| 回滚 | 删文件即可 | 需版本迁移 |

**推荐 A**，并保持 `decisions.jsonl` 只作“决策级权威”：`decide` 行说明授权与归一化答案，旁账说明“实际发了什么、收到了什么、几次、关联谁”。`book-receipts.jsonl` 已是同类先例（`decision_book.py:1107` 注释明说档案字段矩阵封闭、故旁开账本），但它是 `open("a")` 无锁 best-effort（`:1138`），新旁账必须补锁，不能复制这个弱点。

旁账字段（按 kind）：

```
公共：schema=1, kind, row_id(uuid4), ts(ISO ms UTC), call_id, decision_id|null, dp, key|null,
      task_key|null, origin, source, record_error|null
attempt-start：attempt_index, method, url_path, model, timeout_s, header_names[],
      request_bytes, request_sha256, request_len, truncated, original_len, redactions
attempt-end：attempt_index, 关联 row_id, latency_ms, http_status|null, content_type,
      response_bytes, response_sha256, response_len, truncated, original_len, redactions,
      usage|null, usage_source, retry_after_s|null, error_class, error_detail
call-end：attempts, wire_attempts, latency_ms, available, reason, answers_present,
      confidence, confidence_source, transport, model, policy|null
decision-end：status, escalated_reason, archive, state_digest, questions_version,
      truncated[], mode, intent, book_ref|null
```

## 4 逐字段写者 / 读者 / 缺失行为

| 字段 | 写者（唯一） | 读者 | 缺失时显示 |
| --- | --- | --- | --- |
| `call_id` | `decision_wire.new_call`（客户端入口） | monitor 详情、attempt 关联 | 缺 = 旧记录，整段显示“未记录（采集前）” |
| `decision_id` | 上下文（`decide_for`/`mw.py`）；旁账只透传 | monitor 关联、档案 join | `null` 显示“无决策标识（E2/E3/E4 路径）” |
| `origin` | 调用方 context（`--origin` / `mw.py` 分支） | 来源页签 | 缺 = `unknown`，不回填推断 |
| `source` | 由 kind+载荷导出（见 §7） | 来源页签/筛选 | `unknown` |
| `request_bytes` | `_http_post`（`data`） | 详情“实际请求” | 缺 = “未记录（发送前终止/采集失败）” |
| `response_bytes/http_status` | `_http_post` | 详情“实际返回/失败详情” | 有 start 无 end = “已发出，未记录到响应” |
| `attempt_index/attempts` | `_http_post` / `DecisionClient._emit` | AC-012 调用计数 | 缺 = `null`，不按 1 回填 |
| `usage` | `_http_post`（解析响应正文） | 详情元数据 | `usage_source=not-recorded`（不估） |
| `archive` | `decision_points._outcome` | 决策/调用计数对照 | 缺 = “未记录归档结果”，只显示档案存在性 |
| `state_digest` | `decision_points`/`decide_archive` | 与档案行比对 | 不一致 = 明确标注“档案摘要≠本次发送摘要” |
| `mode/intent` | `_outcome` 入参（真实值） | 授权显示 | `mode=unknown`（**不**取 `DecisionOutcome` 默认） |

## 5 调用点矩阵（生产写入点，未知不猜）

| 事件 | 生产写入点 | 载体 | 来源 | 备注 |
| --- | --- | --- | --- | --- |
| dp1 建议产生 | `mw decide run --dp dp1`（E1） | 档案 decide + 证据 | model | `intent=answer` → 档案 `acted=false` |
| dp1 采纳（不改写派发类型） | `ui-bridge.ts:290 dispatchDecisionOf` → `:2308 mergeDecisionHeader` → `:3034` 写 `decision:` 头 | `task.md` 头 | 消费侧采纳（system） | 仅 `mode=auto` 且 `triage_type==dispatchedType`；类型本身从不改写（AC-014） |
| dp1 建议落账 | `ui-bridge.ts:639 emitDispatchTriage` → `pm-orchestrator.ts:666 recordDispatchAlarm` | `auto-decisions.jsonl` | system | 无 `decision_id`；`seq` 靠数行数、无锁 → 只作旁证 |
| dp1 状态路径审计 | `ui-bridge.ts:3048` 追加 `[DECISION] dp1 state=structured|legacy` | `trace.log` | system | 无 `decision_id` |
| dp2 建议 + 采纳 | `pm-orchestrator.ts:2336`（调用）→ `:2697` 判活+`:2435` 写 `steer-dp2.md` → `:2480` 写 `acted=1` | 档案 + steer + trace | model→system | 采纳需 `mode=auto && narrow && confident` 且 steer 落盘成功 |
| dp2 消费 | `worker-mode.ts:3256 consumeDp2NarrowSteer` → `:3295` `[DECISION] dp2 consumed=1 … marker=ok|failed` | `trace.log` + steer 标记 | system | 建议/采纳/消费三段，缺一不可当“生效” |
| dp3 建议（3a/3b） | `worker-mode.ts:5706` 子进程 → E1 | 档案 + 证据 | model | 服务端 `mode` 是唯一授权来源（`:5767`） |
| dp3 建议（3c 本地匹配） | `worker-mode.ts:5697`（**零 spawn**，`confidenceSource="local-match"`） | 仅 trace | system | 无档案、无网络：显示“本地决策（无调用）” |
| dp3 采纳 | `worker-mode.ts:4194-4222`：`dp3 acted=1 decision_id=…` + follow-up steer | trace + transcript | 消费侧采纳 | `decision_id` 可能是本地构造（3c），与服务端 id 不可混计 |
| dp25 建议 | `decide_signoff.py:382→421`（E1） | 档案 decide | model | `intent=answer`，`note="intent=answer"` |
| dp25 采纳/签收 | `mw.py:3784 _decide_sign`：`:3888 verdict` → `:3950 _decide_sign_write`（`:3667 write_signoff`）→ `:3971 append_authority_change(by=signoff:<c>, note=signed_via…)` | `sign-final.md` + authority-change | human（cli/tui）或 system（auto-decide/auto-llm） | `signed_via` 与 `decide_fallback` 是唯一来源凭据 |
| 人工授权调整（dp on/off/set） | `mw.py:2107/2205/2245` → `:1836 _dp_append_authority_change(by=human|human:p0-confirm)` | `.mw/decide-points.json` + authority-change | human | `dp set` 同样只写表+审计行 |
| 人工 gate 答复 | `mw.py:7701 _ap_answer` → `conductor.answer_gate_confirmed`；TS `gate-writer.ts:165` 原子替换 | `gates/*.md`（status/answered_at/answered_by/note/authorizes）+ timeline | human | 不进 `decisions.jsonl` |
| 机器 gate 答复 | `conductor.py:7913 answer_gate_auto`（`answered_by=conductor-auto:<rule>`） | 同上 | system | 不得显示为人工 |
| 机器授权刷新 | `mw.py:2216 _dp_refresh` → `by="refresh"`（`:2245` 段） | authority-change | system | 历史 25/29 条即此类，不得计入人工 |
| 机器 settle | `pm-orchestrator.ts:2778→1059→1004` | archive `kind=settle` | system (`pm-auto`) | 仅当 `task.md` 有 `decision:` 头（dp1） |
| 人工 settle | **无生产写入点**（`append_settle` 只被 TS `settled_by="pm-auto"` 调；`mw decide settle` 不存在） | — | — | 显示“无路径/未记录”，不得伪造 |
| 人工 override | **无生产写入点**（`decide_archive.py:1024` 仅测试调用） | — | — | 同上；历史 0 行 |
| 人工回答（直接答复决策） | **无生产写入点**（`mw decide ask` 只产生证据行，`dp=dp-human-ask`，无 `decision_id`） | 证据行 | human 请求 / model 应答 | 不得当作 dp 采纳 |
| 业务执行 | **无生产调用点**（`intent="act"` 仅测试；dp1..dp24 executor 均 `_unwired_executor`） | — | — | “执行”列必须显示 0/未执行，不得由采纳推导 |

## 6 settle 矛盾复核

- 事实链：`pm-orchestrator.ts:2778`（终端转移分支内、`notified` 去重）→ `:1059 recordDecisionSettle` → 读 `task.md` 的 `decision:` 头（无头则 `no-decision-header` 跳过）→ `:942 planDecisionSettle`（幂等键 `(decision_id,outcome,run_id)`；rollback 需先有 ok）→ `:1004 archiveSettleAppender` → `:986 APPEND_SETTLE_PROGRAM` 通过 stdin JSON 调 `decide_archive.append_settle`（`:1069`，带锁+链）。
- 反证：`.agenticdoc/_autopilot/decisions.jsonl` 现有 seq 27-31 共 5 条 `kind=settle`、`settled_by=pm-auto`、`evidence_ref=<task>@<run_id>`；对应 5 个任务卡的 `decision:` 头。
- 结论：RQ-3 的“settle 无生产 writer”不成立；RQ-2 正确。两卡共同点仍成立：**`settled_by="human"` 与 `override` 无生产路径**，且 settle 只覆盖“任务卡带 decision 头”的 dp1，dp2/dp3/dp25 的吸收不在 settle 面。

## 7 统一事件来源语义与诚实显示

- `human`：只有带人工身份/签名的载体才算——`sign-final.md` 的 `signed_via ∈ {cli,tui}`、authority-change `by ∈ {human, human:p0-confirm}`、gate `answered_by` 非 `conductor-auto:*`、`mw decide ask` 的人工发起。字段缺失即 `unknown`。
- `model`：服务返回的答案（`available=true` 的档案行 / 旁账 `http_status=2xx` 且有 answers）。
- `system`：无模型的机器事实——`by=refresh`、`pm-auto` settle、dp3 3c 本地匹配、`conductor-auto:*` gate、任务头/steer/trace 的采纳与消费。
- `unknown`：历史行缺 `mode/transport`、TS 侧无头关联、旁账缺失。
- 三列分离：`建议`（档案 decide 行 / 本地决策）｜`采纳`（task 头、steer、trace `acted=1`、sign 结论）｜`执行`（生产恒无）。`mode=auto`、`available=true`、`task.md decision:` 头都**单独不足以**证明任意一列。
- 历史显示规则：缺原文 → “未记录（该字段在设计上从未持久化）”；旁账有调用无决策行 → `call-only`（注明 E2/E3/E4 或 duplicate-replay）；有决策行无调用 → `archive-only`（零 spawn 升级或采集前历史）；跨面关联无显式键时 → `inferred(ts 秒 + dp + latency_ms + attempts/answers)`；`confidence_source=unknown/model-self-report` 按既有措辞标注“不作门禁”。
- 计数口径：`calls = count(distinct call_id)`、`attempts = count(attempt-start)`、`decisions = count(distinct decision_id 且有档案行)`，三者分列并显示差额原因；2026-10-22 快照里 33 条 dp1 证据行 ↔ 1 条 dp1 档案行必须能这样解释（duplicate-replay 不丢调用计数）。

## 8 旧签收 / hash 链边界（不静默改门禁）

- `rows_sha256` 的快照键集 `_ROW_FIELDS`（`decide_signoff.py:287-330`）与 `_chain_ok` 的链定义（`:248`）必须冻结；旁账旁开即天然满足。
- `collect` 排除 dp25 自身行（`:301-315`），所以 dp25 新增调用不会移动签收计数/摘要；`sign-final.md` 里的 `rows_sha256` 仍可复算校验，旧文件字节不动（AC-008）。
- 只有 `continue` 校验“真引擎 + N≥1”（`verdict` `:450-500`）；`narrow/revoke` 只校验链——面板须显示“文件声明值 vs 已校验”，不得把 narrow 的 `engine:` 当已验。
- `append_settle`/`append_authority_change` 的行形状不变；如未来要给 decide 行加 `evidence_line`（`append_decide` 已接受该参数），也只能指向旁账序号，且必须另开迁移，不在本次设计内启用。

## 9 后续编码写面建议与真实路径测试

单写者分工（编码阶段，按文件）：

| 文件 | 改动 | 写面所有权 |
| --- | --- | --- |
| `packages/multi-workers/decision_wire.py`（新） | 上下文（contextvar）、行构造、限长/脱敏、锁+append、只读 fold；只 import stdlib（脱敏回调注入，避免与 `decision.py` 循环 import） | **唯一旁账写者** |
| `packages/multi-workers/decision_backends.py` | `_http_post` 两处 hook（不改正负返回类型）；`probe_matrix` 不采 | 传输观察点 |
| `packages/multi-workers/decision.py` | `DecisionClient.decide` 开 `call_id` 上下文 + `_emit` 落 `call-end`；`_append_evidence` 保持不变 | 调用级 |
| `packages/multi-workers/decision_points.py` | `_outcome` 落 `decision-end`（含 `archived/replayed`） | 决策级 |
| `packages/multi-workers/mw.py` | E2/E3/E4 上下文与 `origin`；`--book` 放 `book_ref`；`--origin` 透传 | CLI 入口 |
| `packages/multi-workers/decide_signoff.py` | 调用前放 `origin=signoff-dp25` | dp25 入口 |
| TS 四文件（P1，各 1 行 argv） | `triage-client.ts`/`decision-tool.ts`/`pm-orchestrator.ts`/`worker-mode.ts` 传 `--origin` | 只声明来源，不写账 |

真实路径测试（零外网、零付费；用 stdlib `http.server` 监听 `127.0.0.1:0`，`cfg.extras={"base_url": …, "api_key": "test-not-real"}`）：

1. `packages/multi-workers/test_decide_wire.py`（新）：
   - VC-W1 成功：`decide_for` 走真实 `_http_post`，服务端记录收到字节 == 旁账 `request_bytes`（逐字节）；`attempt-end.http_status/content_type/response_bytes` 与响应一致；`decision-end.archive=created`；用请求体 `state` 复算 `state_digest` 与档案行相等。
   - VC-W2 重试：429+`retry-after: 0`，`max_retries=1` → 同 `call_id` 2 条 attempt-start，`call-end.attempts=1`、`wire_attempts=2`（记录现有语义而非抹平）。
   - VC-W3 超时/断连：`TransportTimeout`/`ConnectionError` → 有 attempt-start + `error_class`，`http_status=null`，详情显示“未收到响应”。
   - VC-W4 duplicate：同 `decision_id` 两次调用 → 2 个 `call_id`、1 条档案行、第二次 `decision-end.archive=replayed`；read-fold 输出 `calls=2/decisions=1`。
   - VC-W5 零 spawn：`enabled=false`、`input-incomplete`、`input-oversize` → 仅 `decision-end`，服务端请求计数 == 0。
   - VC-W6 脱敏：把 `TIMI_API_KEY` 长值放进 state → 落盘文件 0 次原值、`redactions≥1`；`Authorization` 值从不落盘。
   - VC-W7 采集失败不改结果：写入器注入异常 → 决策仍 `available=true`，stderr 一条告警，无伪造行。
   - VC-W8 签收边界：旁账写入前后 `decide_signoff.collect(...).sha256` 与既有 `sign-final.md` 字节均不变。
2. 既有套件回归（真实路径、不新增 fixture 遮蔽）：`packages/multi-workers/test_decide_backends.py`、`test_decide_run_authority.py`、`test_decide_sign_auto.py`、`test_decide_archive.py`；TS `packages/coding-agent/test/suite/decision-association.test.ts`、`decision-tool.test.ts`、`triage-dispatch.test.ts`（验证 `decision:` 头、dp2/dp3 `acted=1`、settle 关联未被旁账改动）。
3. 读侧（monitor）单测：只读 fold 面对“缺 kind / 半行 tail / 未知键 / 旧行无旁账”不得抛异常，逐项输出“未记录”而非猜测。

## 10 未覆盖与残留

- 未验证：`_http_post` 被测试 monkeypatch（`test_decide_backends.py:81`）时旁账是否应静默（设计建议：测试显式关闭 `wire_log`）；本卡未跑任何真实调用。
- 未验证：Windows 上 `O_APPEND` 单行写 + `acquire_lock` 组合在高并发（多个 worker 同时决策）下的实测表现；锁重试 20 次约 100 s 上限（`mw_common.py:2388`）是否足够未测。
- 未验证：`usage` 是否真出现在 `/v1/decisions` 响应正文（本卡禁网）；缺失时按 `not-recorded` 显示，不做估算。
- 未验证：monitor 读侧对 `auto-decisions.jsonl` 无锁并发写的容忍度（该文件 `seq` 由数行数得出，`pm-orchestrator.ts:666`，可能重号）；只作旁证。
- 未覆盖：`dp verify --live`、`probe` 是否也需要独立“健康探测”账（默认不采，避免把探针混入调用统计）。
- 未覆盖：跨 workspace（dual-root）下 `.agenticdoc` 的旁账路径归属（与 RQ-2 残留一致），本卡未展开。
