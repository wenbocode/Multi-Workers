# RQ-3：现有看板资产与「真实 jev 测试页」的可复用链路（只读调研）

> key: mw-decision-dashboard · 日期: 2026-10-22 · 角色: research（只读）
> 约束遵守：未发起任何真实模型调用、未起/未重启服务、未改任何代码或配置、未写 key 外文件。
> 本文件的每个结论都给出 `path:line`；【观测】= 本次实际运行/读取得到的证据，【推断】= 由已读代码推出的判断。

## 结论

- 现状：**没有任何「决策看板」服务端**。`mw serve` 只起 launcher + conductor +（可选）LLM 代理；`usage.py` 的 HTML 看板是**每次调用重新生成的静态单文件**（无 JS、无 tab、无 HTTP 写入面），由 `webbrowser.open` 打开。因此「本地浏览器 + 可提交表单的 DP 测试页签」若要做，必须新增 HTTP 服务面（新代码 + 重启才生效），不是复用。
- 现状：**TUI 已有决策入口，但只有 `show`/`sign`**（`/mw decide`）。`dp`/`book`/`ask`/`run` 在窗口 parser 里被拒（`unknown sub 'dp'` 即此），Python CLI 侧全部可用（实测 `dp list` 25 个 dp、rc=0）。
- 现状：**「真实 jev 调用 + 不执行业务动作」已经存在且是生产路径**：`mw decide run --book <file>` → 决策本先验后发（失败零 HTTP）→ `decide_for(intent="answer")` → step 9 直接返回，**不进入 executor**（`decision_points.py:2558-2562`），档案行 `acted=false`。今天 25 个 dp 里只有 dp25 的 executor 是 `wired` 且为纯回声（无文件/网络副作用），其余为 `none`/`unwired`。
- 现状（关键限制）：**决策本的「填」只对 4 个 dp 有意义**。Python 注册表只有 dp1/dp2/dp3/dp25 声明 `required_state_fields`，其余 21 个为空；`check_book` 的封闭键集合会把任何域字段判为 `book-state`（实测 `dp4 + failure.kind` 被拒）。所以「选 DP + 填决策本」在 dp4..dp24 上只能填 3 个身份字段。
- 现状（关键缺口）：**档案与证据行都不保存原始 request/response**。`decisions.jsonl` 只存 `state_digest` + `answer` + `model/transport/attempts/latency`；`triage-decisions.jsonl` 只有 11 个字段；`response.usage` 在 client 里被丢弃，`probabilities/legend` 只有 `mw decide ask` 的私有子类保留。要展示「实际载荷/实际返回全文」，现有代码里**没有**可读 seam。
- 推荐（待用户确认）：**载体选 TUI**（PM 窗口里的一个「决策」页面，两个 tab：历史 / 测试），后端**只加一条增量 CLI**（一个 `decide` 子命令，内部仍是 `_book_gate` + `decide_for(intent="answer", archive=False)` + `build_payload` 回显），不新增 HTTP 监听、不新增浏览器面；浏览器侧只做**只读静态页**（复用 `usage.render_html` 的表/样式），不做提交。
- 阻塞项（需用户决策，不是我能自行决定的）：载体（浏览器 vs TUI）、测试发送是否允许写入档案、21 个无 `required_state_fields` 的 dp 是否要放宽封闭键集合、是否允许为「展示真实载荷/返回」加代码 seam。

## 1. 研究范围与执行方式

只读调查四件事，全部通过读源码 + 只读命令完成：

1. 现有 HTML/TUI 看板资产（谁渲染、怎么打开、有无交互/服务）；
2. 「服务接口」到底是什么（有没有可提交的本地 HTTP 端点）；
3. DP 测试能力（哪些路径已经能真实打 jev、各自副作用）；
4. 决策本的校验/组装/state/questions/payload/backend/结果/executor 边界，用于判断「选 DP + 填本 + 真实发」能否零新增代码完成。

本次实际执行的只读命令（均无网络调用、无写入）：

| 命令 | 结果 |
| --- | --- |
| `python -X utf8 mw.py decide dp list --project <repo> --json` | rc=0，25 个 dp，enabled=10 |
| `python -X utf8 mw.py decide dp verify --project <repo> --json` | rc=0，offline 25 ok / 0 fail（FakeBackend，零 HTTP、零写入） |
| `python -X utf8 mw.py decide book new dp1-dispatch-type --json` | rc=0，输出骨架到 stdout（未落盘） |
| `python -X utf8 mw.py decide book check decide_book_template.json --json` | rc=2，23 条 issue（占位符未填 → 零 HTTP），符合「只报告不修」 |
| `python -c "... check_book(dp4 + failure.kind) ..."` | `['book-state state.failure.kind: not in required_state_fields (closed key set)']` |
| 只读统计 `.agenticdoc/_autopilot/*.jsonl` | `decisions.jsonl` 43 行（decide 9 / settle 5 / authority-change 29）、`triage-decisions.jsonl` 95 行、`book-receipts.jsonl` **不存在** |

## 2. 证据

### 2.1 现有看板资产（HTML / TUI）

**HTML（stats）——静态单文件，不可提交**

- `packages/multi-workers/usage.py:2096` `render_html()`：纯字符串渲染一个 report dict，注释明确「no I/O and no second data read」。
- `packages/multi-workers/usage.py:1832` `_HTML_STYLE`：内联样式，单文件、无外部字体/CDN（`usage.py:1831` 注释）。
- `packages/multi-workers/usage.py:2177` 起是文档拼装；全文只有 `<!doctype html>`，**没有 `<script>`、没有 onclick、没有 nav/tab**（本次 grep 验证）。
- `packages/multi-workers/mw.py:10217` `_publish_stats_html()`：写 `<usage_dir>/reports/usage-<ts>.html`，然后 `mw.py:10253` `webbrowser.open(target.as_uri())`。没有服务端，没有 POST 面。
- `packages/multi-workers/mw.py:10125` `cmd_stats()`：`--html` 只是「渲染 + 打开」，`--detail` 隐含打开。

**TUI（pi 扩展）——已有决策入口，但只有 show/sign**

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4492` `parseDecideArgs()`：`""|show` 或 `sign <continue|narrow|revoke> [--reason] [--allow-empty] [--key]`，其它一律 usage error（`:4508-4511` 就是 `unknown sub '<x>'` 的产生点）。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4643` `runMwDecideCommand()`：`ctx.hasUI !== true` 直接拒（`:4647`），preview = `mw decide sign --key <k> --json`（零写入），`sign` 走 `ctx.ui.confirm` 后才带 `--human-confirmed` 写。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4742` `registerMwCommands()`；`decide` 分派在 `:4884`，`stats` 在 `:4901`。窗口侧全部是「薄封装 + Python 单一裁决」。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4449` `runMwStatsCommand()`：把 argv 尾原样转发给 `mw.py stats`，只 notify 文本——**窗口没有把 HTML 看板变成 tab 的先例**。
- 可复用的 TUI 展示范式（固定行数卡片 + 缺失字段哨兵）：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts:350` `renderGateCards()`（13 行/卡，`MISSING_FIELD_SENTINEL` 而不是编造），`:457` `cmdGate()` 的 approve/reject 流程。

**pi API 事实（决定载体可行性）**

- `packages/coding-agent/docs/extensions.md:1493` `pi.registerCommand(name, {description, handler, getArgumentCompletions})`。
- `packages/coding-agent/docs/extensions.md:948` `ctx.hasUI`：TUI/RPC 为 true，`-p`/JSON 为 false；`ctx.mode` 为 `tui|rpc|json|print`（`:940`）。
- `packages/coding-agent/docs/extensions.md:2467` 指向 `docs/tui.md`；`docs/tui.md` 给出 `ctx.ui.custom((tui, theme, keybindings, done) => ...)`、overlay、`SelectList`/`SettingsList`/`BorderedLoader`、`ctx.ui.editor`、`ctx.ui.notify`。
- `packages/coding-agent/docs/extensions.md:1636` `pi.exec(command, args, {signal, timeout})` —— 若从扩展直接发调用，这是唯一受支持的进程通道；本项目已有更专用的 `mw-runner.ts`。
- TUI 没有现成 TabBar 组件（`packages/tui/src/index.ts` 导出清单无 TabBar），tab 需要自绘（Container + 键位）或用两次 `SelectList` 导航。

### 2.2 服务接口：没有可提交的本地 HTTP 面

- `packages/multi-workers/mw.py` 全文无 `http.server`/`BaseHTTPRequestHandler`/`serve_forever`/端口绑定（本次 grep 验证）；`mw serve` 是 launcher + conductor（`mw.py` 顶部 subcommand 说明）。
- 唯一的本地监听是 LLM 代理：`packages/multi-workers/proxy_multi.py:14` `_make_proxy()`（`bind_host=127.0.0.1`），由 `timi_proxy_cli.proxy.LocalProxyServer` 提供，负责 chat 补全转发，**不承载 `/v1/decisions`，也不是看板接口**。
- 决策的唯一传输是直连：`packages/multi-workers/decision_backends.py:110` `DECISIONS_PATH = "/v1/decisions"`，`:111` `DEFAULT_MODEL = "jev-latest"`，`TimiDecisionsBackend.endpoint()` = `base + /v1/decisions`。
- 现有「服务接口」实际是**进程内 CLI 面**：`mw decide run|ask|probe|show|set|book|report|sign|dp`（`mw.py:10731` 起 argparse），窗口通过 `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:513` `runMwCliRaw()` → `:576` `decideMw()` 同步 spawn（30s 超时，stdout+stderr 合并，ok = rc 0）。

### 2.3 真实调用链：决策本 → 校验 → 组装 → payload → backend → 结果

1. **决策本装载/校验**（`decision_book.py`）
   - 结构：`{schema_version:2, decision_point, state, context?, notes}`，顶层键封闭（`decision_book.py:36-42`）。
   - 七个失败码封闭集合：`book-schema / book-state / book-placeholder / book-context / book-evidence / book-budget / book-secret`（`decision_book.py:60`）。
   - `scaffold_book()`（`:362`）：键集合/顺序来自注册表，值是**类型占位符**，`notes.evidence` 为每个必填字段留同名待填项。
   - `check_book()`（`:549`）：`_check_state_closed`（缺必填 + 多出键双向报）、`_check_state_types`、`_check_placeholders`、`_check_context`（槽位白名单 + 每个已用槽位要 `notes.evidence["context.<slot>"]`）、`_check_evidence`（`path:line` 必须真实存在且行号在范围内，或 `cmd:` 前缀）、`_check_budget`（复用 `decision._estimate_tokens` + `.mw/decide.json` 闸）、`_check_secrets`（`decision._redact` 改动即命中凭据，`:1019`）。
   - 封闭键集合只用 `REQUIRED_STATE_FIELDS[dp] ∪ {schema_version, decision_point, questions_version}`（`decision_book.py:20-27`、`:626-660`）。
2. **发送面组装**（`mw.py`）
   - `_book_gate()`（`mw.py:1499`）：`load_book` → `check_book` → 失败即 `exit 2`、**零 HTTP**；成功返回 `book_state(book)`（顶层 `context` 合入 `state.context`，空槽丢弃，`decision_book.py:1067`）+ meta（`book_path`/`file_sha256`/`evidence`）。
   - `_decide_run()`（`mw.py:911`）：`--book` 与 `--request-file` 互斥；book 的 `decision_point` 与 `--dp` 冲突则拒绝；然后**结构化路径** `decision_points.decide_for(dp, Trigger.from_mapping(state), project_dir, client=..., intent="answer")`（`mw.py:975-983`）。
   - `_book_receipt()`（`mw.py:1531`）→ `decision_book.append_book_receipt()`（`decision_book.py:1107`）写 `.agenticdoc/_autopilot/book-receipts.jsonl`（`decision_book.py:139`），字段含 `book_path/file_sha256/evidence/state_digest/decision_id/available/reason/transport`。
3. **state 与 questions**
   - state：`decision_points._state_builder()`（`:404`）写入 `schema_version`/`decision_point` + 调用方 data + `key`/`task_key` + 注册表 `questions_version`；**不编造缺失字段**（缺失留给 step 5 判 `input-incomplete`）。
   - questions：注册表是唯一权威，`questions_map()`（`decision_points.py:884`）；请求体**不带** `questions`（只有旧格式 legacy 请求才自携）。
   - 预算：canonical state ≤ 2000 B（`decision_points.MAX_STATE_BYTES`，step 6 两段截断后仍超则 `input-oversize`）。
4. **实际 payload**（`decision_backends.py`）
   - `build_questions()`（`:578`）：`noul` → `{type, instructions, criteria?}`；`choice` → `criteria`（caller `criteria` > 动态渲染 > `labels`）；`score` → `criteria` 数组（2..10 级）；`box` 与未知类型**不进入请求**。
   - `build_payload()`（`:612`）：**恰好** `{model, state, questions}`。这是唯一的线上体构造点，`_dp_verify_payload()`（`mw.py:2613`）也用它做契约断言。
   - 拒绝前置：`box` 无图 → `box-requires-image`；非 `choice|score|noul` → `unsupported-question-type`；动态选项渲染不出来 → `input-incomplete`；这些都在读凭证之前返回（`decision_backends.py:733-760`）。
5. **结果**
   - `_decode_answers()`（`:627`）：`choice` 必须在 enum 内、`score` 保留小数、`noul` ∈[0,1] 且无 confidence；`probabilities`/`legend` 原样带上；响应 `model` 与请求不一致直接 `bad-response`（无模型回退）。
   - `DecisionClient.decide()`（`decision.py:687`）：8 类 reason 封闭集合、`max_retries`/backoff/时间预算、`_normalize_answers` 只留 `{value, confidence}`（`:1080-1100`）——**`probabilities`/`legend` 在这一层被丢掉**。
   - 证据行：`_append_evidence()`（`decision.py:1227`）写 `.agenticdoc/_autopilot/triage-decisions.jsonl`（`:109`），字段固定 11 个（`:234`）：`ts/dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source`。
6. **executor 边界**（`decision_points.decide_for`，`:2278`）
   - 11 步顺序：未知 dp → 抛 `DecisionInputError`；`enabled=false` → `escalated(disabled)`（在 build_state/encode/backend 之前）；mode；transport 可用性（`.mw/decide.json`）；build_state + 必填（`input-incomplete`）；2000B（`input-oversize`）；`client.decide`（`unavailable`）；答案可用性/置信度（`low-confidence`）；**step 9：`mode=suggest` 或 `intent="answer"` → 存档 `acted=false`，返回建议**（`:2558-2562`）；step 10/11：auto 才调 `executor`（`:2631`），抛错/无返回值 → `escalate(over-authority)`。
   - executor 现状：`_unwired_executor()`（`:427`）必抛；dp25 `_echo_conclusion_executor()`（`:445`）只返回 `signoff:<conclusion>`，不写文件；`decide_registry.json` 里 dp4/dp6/dp8/dp10..dp20/dp24 为 `none`，dp1/dp2/dp3/dp5/dp7/dp9/dp21/dp22/dp23 为 `unwired`，dp25 为 `wired`。

### 2.4 现有 DP 测试能力（4 条路径对照）

| 路径 | 真实打 jev | 读决策本 | 走授权门 | 写档案 | 执行器 | 失败可见性 | 现成 CLI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `mw decide dp verify`（默认 offline） | 否（FakeBackend） | 否（合成最小 state） | 否 | 否 | 否 | 每 dp `failures[]` | `mw.py:2778` |
| `mw decide dp verify --live` | **是** | 否（合成最小 state） | 否 | 否 | 否 | 每 dp + exit 1 | `mw.py:2744` |
| `mw decide ask --book/--state` | **是** | 是（`_book_gate`） | 否（human 即权威） | 否（只有 evidence 行 + book receipt） | 否 | stderr `reason: detail`，exit 2 | `mw.py:1631` |
| `mw decide run --book` | **是** | 是 | **是**（`decide_for`） | **是**（`acted=false`） | 否（`intent="answer"`） | JSON `reason`/`escalated_reason` | `mw.py:911` |

补充事实：

- `dp verify --live` 的状态来自 `_dp_verify_state()`（`mw.py:2569`）：只用注册表必填路径 + `_DP_VERIFY_STATE_VALUES` 常量，**不接受外部输入**；`--live` 直接 `decision.DecisionClient(cfg).decide(...)`（`mw.py:2744`），不经过 `decide_for`，**不存档、不起执行器**。这是现有代码里最干净的「只发真实 jev」样本。
- `decide ask` 是唯一保留宽答案的人面：`_AskDecisionClient`（`mw.py:1347`）重写 `_normalize_answers` 保留 `probabilities`/`legend`，并记录 `ask_detail`（失败原因原文）。`--book` 时只写 evidence 行与 book receipt，**不写 `decisions.jsonl`**。
- `decide run --book` 输出的 JSON（`_decide_run_payload()`，`mw.py:880`）= legacy 8 键 + `decision_id/mode/acted/escalated_reason/state_digest`；**不含 payload 回显**，answers 也已被 client 窄化。

### 2.5 档案/证据里到底有什么（看板数据面）

- 档案：`.agenticdoc/_autopilot/decisions.jsonl`（`decide_archive.py:39`），`kind ∈ {decide, override, settle, authority-change}`（`:46`），37 个字段的封闭矩阵（`:91`），哈希链 `prev_sha` + `seq`，`decision_id` 去重（`duplicate="existing"` 回放）。
- `append_decide()`（`:948`）写入的与决策相关的字段：`state_digest/questions_version/available/reason/answer/authority/escalated_reason/acted/actual_action/mode/model/transport/attempts/latency_ms/confidence/confidence_source/cost_tokens/policy/note`。**没有 `state`、没有原始 payload、没有原始 response**；`append_decide` 的 `state` 形参只用来算 digest（`:1026` 注释：raw state is never written）。
- `cost_tokens` 有字段但**无生产者**（本次 grep：只有 `decide_archive.py` 自身与测试）。`response.usage`（token 计数）在 client 里被丢弃。
- `settle`/`override` 有 writer（`append_settle` `:1069`、`append_override` `:1024`）但**无生产调用点**（grep 只命中测试）：`outcome` 实际长期停在 `pending`。实测档案 5 条 settle 行是历史上手工/一次性写入的。
- 决策吸收（adoption）在 TS 侧：`[DECISION] dp2 acted=1 decision_id=… trigger=…`（`pm-orchestrator.ts:2467-2480`）、`[DECISION] dp3 acted=1 decision_id=…`（`worker-mode.ts:4222`）、`dp2 consumed=1 decision_id=… via=…`（`worker-mode.ts:3298`）、`ask_decision` 的 `[DECISION]/[DECISION_UNAVAILABLE]/[DECISION_RETRY_STOP]`（`decision-tool.ts:843-868`）。这些只落在各 task 的 `trace.log`。
- 来源判定素材：`authority ∈ {advisory, binding, human}`（`decide_archive.py:47`）、`by`（authority-change 行，如 `refresh` / `signoff:narrow`）、gate 答复（`autopilot/console.ts:457` 写 `answered_by`）、`sign-final.md` 的 `signed_via`。
- 本仓库实测：43 行档案（decide 9 / settle 5 / authority-change 29）、95 行 evidence、**`book-receipts.jsonl` 不存在**（说明历史上没有任何一次决策本发送，`决策本 ↔ 决策` 的关联对全部历史行都是 **unknown**，不是空）。

## 3. 复用资产（可直接用，不需重写）

| 资产 | 位置 | 复用点 |
| --- | --- | --- |
| 注册表快照 | `decision_points.registry_snapshot()`（`:981`）+ 打包的 `packages/multi-workers/decide_registry.json` | DP 选择列表、必填字段、问题集、`wired/executor` 一屏可读 |
| 决策本骨架/校验/发送视图 | `decision_book.scaffold_book/check_book/book_state`（`:362/:549/:1067`） | 「填本」= 生成骨架 + 填 + 校验；发送视图保证空槽不上线 |
| 决策本回执 | `append_book_receipt()`（`:1107`） | 唯一能把「这次决策用了哪本书/哪个字节版本」关联到 `decision_id` 的账本 |
| 真实调用链 | `mw decide run --book` + `decide_for(intent="answer")` | 与生产 PM 路径**同一条**，零业务动作 |
| payload 构造 | `TimiDecisionsBackend.build_payload()`（`:612`） | 唯一线上体构造点，可用来「如实回显实际载荷」（而不是另写一份摘要） |
| 宽答案/失败详情 | `_AskDecisionClient`（`mw.py:1347`） | `probabilities/legend` + 失败 `detail`，人面已实现 |
| 档案 fold + 报告 | `decide_archive.fold()`（`:840`）、`mw decide report`（`mw.py:3438`） | 「逐决策」详情块（判据表/逐决策/分歧样例/无法关联）已成型 |
| 静态 HTML 表/样式 | `usage.render_html()`（`:2096`）、`_html_table()`（`:1981`）、`_HTML_STYLE`（`:1832`）、`_html_escape()`（`:1940`） | 只读页面零依赖复用；转义规则现成（AC-005 的展示侧） |
| 静态页发布 | `mw.py:10217 _publish_stats_html()` | 「写文件 + 打开浏览器」的既有节奏，无服务端 |
| TUI 卡片范式 | `autopilot/console.ts:350 renderGateCards()` | 固定行数 + 缺失哨兵，适合「历史列表」 |
| 进程调用 | `shared/mw-runner.ts:576 decideMw()` / `:590 statsMw()` | 窗口 → Python 的既有唯一通道（30s/180s 超时、合并 stderr） |
| 离线契约探针 | `mw.py:2682 _dp_verify_point()` | 加 `--book` 后可秒级验证「这本书能不能发」而不发 |

## 4. 限制与安全边界

### 4.1 「只发真实 jev、不执行业务动作」vs「真实执行」

- **只发不执行**（推荐）：`decide_for(..., intent="answer")` → step 9，**永不进入 executor**，档案 `acted=false`、`authority=advisory`；`mode=auto` 也一样（`decision_points.py:2558-2562`，`mw.py:975-983` 就是这么调的）。`dp verify --live` 更是连 `decide_for` 都不进（`mw.py:2744`）。两条路都已是生产代码，不需要新造「模拟链路」。
- **真实执行**：只有 `intent="act"` + `mode=auto` + `executor` 才走 step 10/11。今天的实际风险面**很小**（只有 dp25 的纯回声 executor；其余 `none`/`unwired` 会 `over-authority` 上抛），但语义上是**未经人审的自动生效**，而且一旦将来有 executor 落盘/写配置，测试页会直接触发。**结论：测试页必须固定 `intent="answer"`，不给 `--act` 开关**。
- 真实模型调用的固有风险（与执行无关）：真花钱/真占配额（`max_retries=2` + 20s 预算，`rate-limited` 会重试）、真实返回会被写进 evidence 行（append-only，写失败 best-effort）、`timeout`/`upstream-error` 会被当作正常结论展示（必须清楚显示「失败」而不是「无建议」）。

### 4.2 凭证（GC-3）

- 解析链：`cfg.api_key` → env `TIMI_API_KEY` → `~/.pi/agent/auth.json` 的 `timi.key`（`decision_backends.py:159-190`）；`credential_status()` 只吐布尔。
- 脱敏：`decision._redact()`（`decision.py:531`）在 `_scrub_detail` 与 evidence 行都生效；`book check` 的 `book-secret` 用同一函数（`decision_book.py:1019`）。`mw decide show --json` 把 `api_key` 打成 `<redacted>`（`mw.py:1044`）。
- **风险点**：worker 的凭证隔离是 **env 级**（`launcher.py:529 _stripped_env()`，只有 `pi+timi` 分支在 `:679-693` 把 `TIMI_API_KEY` 放回去）。但决策客户端的第三级回退读的是**同机器同用户的 `~/.pi/agent/auth.json`**，所以「非 timi worker」也能发真实决策请求。测试页若放在 worker 侧，等于绕开这层隔离；**应只开在 PM/人面**。
- 展示侧：浏览器的静态页不得内联任何 key；TUI 页面不得把 `Authorization` 回显。现有代码没有把 key 放进 response/detail 的路径（`decision.py:224-241` 的响应字段表 + `_redact`），保持即可。

### 4.3 副作用：档案污染与 sign-off 计数

- `mw decide run --book` **一定**写一条 `kind=decide` 档案行（`mw.py:975-1010`）。`decide_signoff.collect()`（`decide_signoff.py:287`）把「同 key 的所有 `kind=decide` 行」计入 `rows_total/rows_available/rows_sha256`（只排除 dp25 自身）。**实测当前档案只有 9 条 decide 行**，任何测试发送都会改变签名摘要 `rows_sha256` 与 `n_available`。
- 规避手段（择一，需确认）：(a) 测试本用独立 `state.key`（如 `dp-playground`）→ 不进入任何真实 key 的签名集；(b) 新增只读子命令走 `decide_for(..., archive=False)`（`decide_for` 已支持该形参，`decision_points.py:2286`）；(c) 接受污染但在写入前 TUI 明示。
- `allow-send` 边界：`autopilot/dispatch.py:256 decision_allows_send()` 规定「只有显式 `allow-send: yes` 才允许 worker 发送，缺省 no，发送归 PM」（`:273 decision_card_issues()`）。测试页属于人/PM 面，与 `mw decide ask`「人就是权威」一致；**不得**把它做成 worker 可用的发送通道。

### 4.4 「实际请求/实际返回」的可见性边界（直接影响 AC-003/AC-004）

- 实际 payload：**可如实重建**。`build_payload()` 是纯函数（state + questions + cfg + 动态渲染），`_dp_verify_payload()` 已在用它做断言。要在页面显示，必须调用**同一个** `build_payload`，不能在前端拼摘要；`decision.py` 目前**没有**把发出的 body 回传的 seam（`decide()` 只返回 8 个响应字段）。
- 实际返回：**只有窄化后的 answers**。`probabilities/legend` 仅在 `_AskDecisionClient` 保留；`usage`（token）任何层都不保留；原始响应体只活在后端 `_decode_answers()` 的入参里。
- 因此 AC-003 的「实际返回」今天只能做到「decoded answers + model/transport/attempts/latency/confidence_source」；要「全文」必须加代码 seam（需用户确认）。
- 历史行：`state`/payload/response 从未落盘（`decide_archive.py:1026` 注释 + 字段矩阵），**老决策的实际载荷不可能还原**，只能在详情里标「未记录」。

## 5. 最小复用方案（推荐 A，备选 B）

### A（推荐）TUI 页面 + 一条增量 CLI，零新增服务

1. **载体**：PM 窗口 `/mw decide` 增加第二个子命令（如 `/mw decide page`），`ctx.ui.custom()` 打开一个双 tab 页面：
   - tab1 历史：读 `decisions.jsonl`（fold）+ `book-receipts.jsonl` + `trace.log` 的 `[DECISION]` 行 → 列表 + 详情（决策本/请求/返回/吸收/应答，缺字段显示 `未记录`）。
   - tab2 测试：`SelectList` 选 dp（数据来自 `decide_registry.json`）→ `ctx.ui.editor` 编辑 `scaffold_book()` 生成的 JSON（可先 `book check` 预检）→ 确认后发送。
2. **后端增量（唯一代码改动）**：`mw decide run` 增加两个只增不改的开关：
   - `--echo-payload`：用 `TimiDecisionsBackend().build_payload()` 把**真正要发**的 body 回显（与发送同一函数、同一入参）；
   - `--no-archive`：`decide_for(..., intent="answer", archive=False)`，避免污染签名集；
   - 失败详情复用 `_AskDecisionClient` 的 `ask_detail` 语义（或把 `detail` 并入 JSON 的 `book`/`diagnostic` 字段）。
   仍走 `_book_gate`（先验后发、零 HTTP）与 `decide_for`（授权/step 9），不新增传输、不改协议。
3. **窗口侧**：`decideMw()` 转发 argv，返回 JSON 后渲染；`ctx.hasUI !== true` 直接拒（复用 `:4647` 的判据）。
4. **成本**：Python 1 个文件小改 + TS 1 个命令分支 + 测试；无重启依赖（Python CLI 每次新进程），扩展侧仍需 `/mw build` + 重启 pi 才加载新 bundle。

### B（备选，成本高）浏览器双页签 + 本地 HTTP

- 需要新增一个只绑 `127.0.0.1` 的 handler（POST `/api/decide/run`）、CSRF/来源校验、生命周期挂到 `mw serve`（**必须重启 serve 才生效**）、以及「浏览器里不出现 key」的额外约束。
- 现有 `usage.py` 的静态 HTML 无法提交，只能作为**只读历史页**复用（渲染 + 打开），不能承载 AC-004 的交互。

### C（纯零代码）只用现有 CLI，不做页面

- `mw decide book new --out` → 手填 → `book check` → `decide run --book`；满足 AC-004 的功能，但没有任何「页面」形态，且无 payload/返回详情，不满足 AC-003 的展示要求。

**方案取舍**：AC-002/AC-004 用 A 的 tab1/tab2 即可闭环；AC-003 的「实际请求」在 A 里靠 `--echo-payload` 达成（同函数同入参），「实际返回全文」仍需用户决定是否加 seam；AC-005 靠既有 `_redact`/`book-secret`/`_html_escape`。

## 6. spec 决策映射

| spec 项 | 现状证据 | 本调研结论 |
| --- | --- | --- |
| AC-001（`dp list` 入口不再 unknown sub） | 窗口 parser `ui-bridge.ts:4492-4533` 只认 show/sign；Python CLI 实测 25 dp、rc=0 | 属 RQ-1 修复面；**看板/测试页依赖它**（同一 parser），修复时需一起放开 `dp`（以及新的 page 子命令） |
| AC-002（按项目列出所有决策 + 可证实来源，未知标未知） | `decisions.jsonl` 4 种 kind + `authority/by` + gate 答复 + `sign-final.md`；实测 43 行/9 decide | 可做：列表 = fold；来源 = `authority` + `by`；`override/settle` 无生产 writer → 只能标「未记录/未结算」，不能推断 |
| AC-003（决策本 + 实际请求 + 实际返回 + 吸收 + 应答，同一 decision_id） | book receipt 账本存在（`decision_book.py:1107`）但本仓库 **0 条**；档案无 state/payload/response；吸收在 `trace.log` | 部分可做：决策本=未记录（历史）；实际请求=`build_payload` 重建（需 `--echo-payload`）；实际返回=窄化 answers（全文需 seam）；吸收=trace 行；应答=`answer`+`actual_action` |
| AC-004（选 DP + 合法决策本 → 内部真实调用 → 真实返回；失败明确展示） | `mw decide run --book` 已满足调用/失败语义（rc 0 + reason，档案 acted=false）；`_book_gate` 失败零 HTTP | 只需「选/填/显示」的壳；**不要**新增传输或模拟 |
| AC-005（展示/落盘不含凭证） | `decision._redact`（`:531`）、`_check_secrets`（`decision_book.py:1019`）、`_html_escape`（`usage.py:1940`） | 复用即可；新增页面不得绕过这三处 |
| §4 未决项「UI 载体」 | 无 HTTP 服务、HTML 静态无 JS、TUI 有 show/sign + custom 组件 | 推荐 TUI；浏览器仅只读页（需用户拍板） |
| §4 未决项「测试副作用」 | `decide run` 必写档案并进入 sign-off 计数；`archive=False` 已存在但 CLI 未暴露 | 推荐 `--no-archive` + 独立测试 key；需用户拍板 |
| §4 未决项「人工范围」 | `authority=human` / `override` / `authority-change.by` / gate `answered_by` / `signed_via` | 五类产物都在文件里，判定规则待用户确认 |
| §4 未决项「历史缺失字段」 | 无 state/payload/response/usage；无 book receipt | 明确标「未记录」，不重建、不伪造 |

## 7. 需用户确认事项

1. **载体**：TUI（推荐，零新增监听）还是本地浏览器？若浏览器，是否接受「新增 127.0.0.1 HTTP 端点 + 重启 serve」的成本与安全面？
2. **历史 vs 测试的数据源边界**：历史页是否允许跨 key 汇总（`decisions.jsonl` 是项目级、混合多个 key）？是否需要按 key/时间过滤？
3. **测试发送的落账方式**：`--no-archive`（不写档案）／独立测试 key／照常写档案（会改 `sign-off` 的 `rows_sha256`）——三选一。
4. **21 个无 `required_state_fields` 的 dp**：是否接受「只能测身份字段」？还是要放开决策本的封闭键集合（引入「可选字段白名单」，属于 registry/spec 变更）？
5. **「实际返回」的保真度**：接受「decoded answers + 元数据」即可（零改动），还是必须保留原始响应体/`usage`（需要 `decision.py` 加 seam，属于冻结协议模块的改动）？
6. **是否允许测试页在非 timi-provider 的 worker 里使用**（会经 `auth.json` 绕过 env 级凭证隔离）？建议只开 PM/人面。
7. **人工决策的判定清单**：override / settle / authority-change / gate 答复 / 签名，哪几类算「人工决策」？（决定 AC-002 的「来源」列）
8. **P0 dp 是否允许出现在测试页**：允许即等于用真实模型评估 P0 决策，但不得据此执行；是否需要在页面上硬性标注「P0 = 仅观察」？

## 8. 残留与未验证

- 未做任何真实 jev 调用：`_decode_answers` 对 `usage` 的处理、`probabilities` 的实际分布形态，只有代码与测试（`test_decide_backends.py:124`）证据，没有线上样本。
- `dp verify --live` 未运行（会打真实模型，本任务禁止）；其「一次 25 个 dp 串行」的耗时/限流表现未验证。
- 浏览器方案未做原型：`mw serve` 加 HTTP 端点的具体挂载点、重启影响（在飞 worker 的 orphan reconcile）未验证。
- 21 个 dp 的 questions 里，`dp8/dp3/dp25` 带 `instructions`/`labels`，其余多为仅 `choices`；`build_questions()` 对缺 `instructions` 的注册表项会用确定性占位文案（`decision_backends.py:520`），测试页展示时应标注「占位文案」。
- `book-receipts.jsonl` 在本仓库从未生成过，回执读取路径（含历史缺失）没有真实样本可校验。
- 未核对 `decide_archive.fold()` 对「只有 override 无 decide」的孤立行在 UI 上的呈现细节（`base_missing` 分支已有，但无历史样本）。

## 9. 上下文来源

**完整读取的源文件**

- `packages/multi-workers/decision_backends.py`（758 行）
- `packages/multi-workers/decision.py`（1107 行）
- `packages/multi-workers/decision_book.py`
- `packages/multi-workers/decision_context.py`
- `packages/multi-workers/mw.py` 相关段：`:700-1100`（decide run/probe/show）、`:1150-1760`（ask/book/gate/receipt）、`:1879-2060`（dp list/show）、`:2540-2860`（dp verify）、`:3176-3520`（report）、`:10125-10310`（stats/HTML 发布）、`:10731-11010`（decide/dispatch argparse）
- `packages/multi-workers/decision_points.py` 相关段：`:95-560`（常量/Trigger/注册表/executor 工厂）、`:860-1450`（questions_map/snapshot/REQUIRED_STATE_FIELDS/预算）、`:1967-2735`（DecisionOutcome/archive seam/answer 校验/decide_for 全 11 步）
- `packages/multi-workers/decide_archive.py` 相关段：`:39-546`（常量/字段矩阵/校验）、`:790-1120`（fold/append_decide/append_settle）
- `packages/multi-workers/decide_signoff.py` 相关段：`:215-340`（collect）、`:400-440`（auto_conclusion, intent=answer）
- `packages/multi-workers/autopilot/dispatch.py` 相关段：`:186-360`（decision 卡片四项 / allow-send / write face）
- `packages/multi-workers/usage.py` 相关段：`:1832-2230`（HTML 样式/表格/render_html）
- `packages/multi-workers/launcher.py` 相关段：`:527-775`（`_stripped_env` 与 timi 凭证分支）
- `packages/multi-workers/proxy_multi.py`（全文）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（全文）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`（全文）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 相关段：`:4440-5000`（`/mw decide`、`/mw stats`、`registerMwCommands`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` 相关段：`:340-520`（gates 卡片 / gate 答复）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（全文）
- `packages/coding-agent/docs/extensions.md` 相关节：ExtensionContext / `ctx.hasUI` / `ctx.mode` / `pi.registerCommand` / `pi.exec` / Custom UI
- `packages/coding-agent/docs/tui.md`（全文：组件接口、`ctx.ui.custom`、overlay、SelectList/SettingsList/BorderedLoader、主题与 invalidate）
- `.agenticdoc/mw-decision-dashboard/spec.md`、`key-decision.md`、`tasks/RQ-3-playground.md`、`.agenticdoc/goal.md`
- `packages/multi-workers/decide_registry.json`、`decide_book_template.json`、`README.md`（决策服务章节 `:631-969`）

**只读数据样本**

- `.agenticdoc/_autopilot/decisions.jsonl`（43 行）、`triage-decisions.jsonl`（95 行，含一条 `transport=llm-transitional` 的历史行）、`auto-decisions.jsonl`（37 行）
- `.mw/decide.json`（enabled=true / timi-decisions / jev-latest / signoff=auto）、`.mw/decide-points.json`（25 行表）

**未使用的通道**：未调用 `ask_decision`、未发起任何 `decide run/ask/--live`、未启动/重启 `mw serve`、未写 key 外任何文件。
