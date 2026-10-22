# Design: mw-jev-provider-integration

## §0 架构总览

三层结构，全部原则服从"**旁路化**"：决策服务只在框架需要判断的时刻被调用，不可用时一切照旧。

```
  决策点（框架决策时刻）                     决策客户端                       传输后端
  ─────────────────────                     ──────────                       ────────
  DP-1 派发前分诊 ──┐                                                       ┌─ B1 llmproxy-anthropic (jev，D-1 阻塞)
  （类型 + 风险）    │   state + questions   ┌───────────────┐   encode     ├─ B2 llm-transitional (glm，默认可用)
  DP-2..4（后续波）──┼──────────────────────▶│ decision.py   │─────────────▶┤
                    │                       │ 契约/预算/    │   decode     └─ B3 direct-systemone (保留，未交付凭据)
   PM 可见面 ◀───────┘   answers + conf      │ fail-soft     │
   （readback/ledger/doctor，待 RQ-D4 定档）  │ 证据行 [..]    │
                                            └───────────────┘
```

- **决策客户端**（新文件）是唯一契约面：调用方只给 `state` + `questions`，只拿 `answers` + 元数据；后端差异（协议、编码、错误形态）在客户端内部吸收。
- **默认关闭**：未配置 `.mw/decision.yml` 时，框架行为与现状逐字一致（无新进程、无新网络调用）。
- **fail-soft 是结构性保证**：客户端所有对外函数不抛异常，失败以 `available=false` + `reason` 表达。

## §1 设计前提（全量实证锚点）

| 事实 | 证据 |
| --- | --- |
| 官方决策 API：`POST https://api.typesafe.ai/v1/systemone`，`state`+`questions`→`answers`，四型问题（choice/score/noul/box），`confidence` 只读，无流式无 reasoning | `evidence/research/spec-typesafe-api-20261016.md` |
| 仓内接线（目录/生成/路由/凭据）无断点；`models.generated.ts` 是聚合 hub，grep 零命中是结构性的 | `evidence/research/spec-jev-catalog-wiring-20261016.md`（`generate-models.ts:724-736`、`models.generated.ts:114`） |
| 决策面锚点：解析链/回退链/反馈链/凭据面与冲突边界 | `evidence/research/spec-jev-decision-surface-20261016.md` |
| timiai/llmproxy **未暴露**承载 `state/questions` 的入口：决策形状路径穷举 20+ 全 404；`/v1/messages` 严格校验拒收该两字段；`/responses` 报 typesafe `Unmapped LLM provider`；`/v1/messages`+jev 持续 429（≥90s 复测） | `evidence/research/spec-jev-live-probe-20261016.md` |
| 可用传输：`http://api.timiai.woa.com/ai_api_manage/llmproxy` 的 `/v1/messages` 与 `/responses`（`/v1/chat/completions`、`/v1/responses` 一律 404），鉴权 `Authorization: Bearer <TIMI_API_KEY>` | 同上（P1–P7） |

**OPEN（未决，本设计不依赖）**：D-1 = timiai 侧决策入口的形状（待上游）。设计将入口形状隔离在 B1 后端内部，D-1 解除后只改该后端。

## §2 设计决策

### D-001 决策客户端独立成文件，CLI 只加一个函数与一行注册

- 新增 `packages/multi-workers/decision.py`（契约/校验/预算/fail-soft/证据行）与 `packages/multi-workers/decision_backends.py`（B1/B2/B3 + fake）。
- `mw.py` 仅新增 `cmd_decide()` 与子命令表一行；**不触碰** `_goal_gate_install` 及其安装点（属并行 active key `mw-goal-gate-write-intent` 的写入面）。
- **实现锚点（据 RQ-D2）**：argparse subparsers `mw.py:6682-6684`；嵌套 action 模式（`target`/`model`/`rag` 同构，`mw.py:6711-6731`）；`cmd_*` 返回 int 经 `sys.exit` 派发（`mw.py:7144-7166`）；机器出口 `--json` + 文本少量行（照 `cmd_doctor` `mw.py:653-662`）。CLI 形态：`mw decide <run|probe|show>`。
- **TS→Python 桥**：`PYTHON_EXE`（win=`python`）+ `MW_PY`（`shared/mw-runner.ts:12-64`，路径可 `MW_PY` 覆写），TS 侧 spawn 带 `-X utf8`（`agentic-scripts.ts:67` 先例）；DP-1 调用点（TS）通过该桥同步调 `mw decide run`，JSON 进 JSON 出。
- 理由：新文件零争用；`mw.py` 改动面压到最小，提交时即使文件被并行改动也可用索引级重建只 stage 本 key 的 hunk。

### D-002 传输后端抽象：B2 默认可用，B1 显式阻塞，B3 仅保留实现位

| 后端 | 承载 | 状态 | 编码方式 |
| --- | --- | --- | --- |
| B1 `llmproxy-anthropic` | jev（正式目标） | **受 D-1 阻塞**：未配置/不可用时报 `reason=entry-unavailable`，不得静默当作成功 | 待上游确认（隔离在本后端内） |
| B2 `llm-transitional` | 现有可用模型（默认 `glm-5.3-flashx`，走 `/v1/messages`） | **本波默认启用** | `state`+`questions` → 提示词 → 强制结构化 JSON → 解析回 `answers` |
| B3 `direct-systemone` | typesafe 直连 | 仅保留实现位，不交付凭据配置 | 官方 systemone 形状（RQ-1） |

- 选择来自配置；未配置 → B2；B1 被选中但入口不可用 → `available=false, reason=entry-unavailable`。
- `confidence_source` 必填：B1/B3 为 `api`，B2 为 `model-self-report`（未经校准，呈现文案必须带来源）。**硬规则：`confidence_source != api` 时，`confidence` 不得用于任何门控/阈值自动决策，只能作为弱排序信号**（实测 B2 对平凡事实自报 1.0，典型过自信）。

**B2 请求模板（实测组合，证据 `design-transport-b2-contract-20261016.md` Q1/Q2/Q6）**：

```text
POST http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/messages
Headers: Content-Type: application/json | Authorization: Bearer <TIMI_API_KEY> | anthropic-version: 2023-06-01
Body:   {model: glm-5.3-flashx, max_tokens: 1024, temperature: 0,
         system: "...Answer ONLY via the submit_decision tool...",
         tools: [{name: submit_decision, input_schema: <一题一属性，属性名 = question id>}],
         tool_choice: {type: tool, name: submit_decision},
         messages: [{role: user, content: "state: ...\nquestions: ..."}]}
```

- **解析规则（按优先级）**：非 200 → 错误类别表；200 但 body 含 `error` 字段 → litellm 透传错误；取 `content` 中 `type=="tool_use"` 的块（**忽略 thinking/text**：即使强制 tool_choice 也会附 text 块）；校验 `input`（可解析 / 必需键齐 / enum 与 min-max）；不合格 → 回喂校验错误重发 1 次；再失败 → 提示词回退（解析 text 块 JSON，实测该模型 n=1 严格遵守）→ 仍失败则 `bad-response`。
- **禁止携带的字段**：`response_format`（实测 400 `unknown_fields`）、`state`/`questions`（同为 400）、`store`（`timi-responses.ts:19` 佐证该网关拒收）。
- **不选 `/responses` 承载 B2**：实测 reasoning 独占 `max_output_tokens` 致正文为空、响应体是 litellm 混血形状（`object:"chat.completion"`、回显字段失真、`model` 被回填内部前缀 `zai/...`）。

### D-003 契约（CLI = API，单一实现）

请求（JSON）：

```json
{"state": "...", "questions": {"triage_type": {"type": "choice", "choices": ["coding", "research", "review"]},
                               "triage_risk": {"type": "choice", "choices": ["low", "mid", "high"]}}}
```

响应（JSON）：

```json
{"available": true, "transport": "llm-transitional", "model": "glm-5.3-flashx",
 "confidence_source": "model-self-report", "attempts": 1, "latency_ms": 1234,
 "answers": {"triage_type": {"value": "research", "confidence": 0.8},
             "triage_risk": {"value": "low", "confidence": 0.6}},
 "reason": null}
```

- 退出码：成功/失败（available=false）均 0；参数非法（缺字段/未知问题类型/超上限）为 2。
- `reason` 取值集合（机器可读）：`disabled` / `entry-unavailable` / `timeout` / `rate-limited` / `upstream-error` / `bad-response` / `budget-exhausted`。
- CLI 与 Python API 走同一 `DecisionClient.decide()`，校验与响应构造只有一处实现。

### D-004 预算与 fail-soft 边界

- 默认：`timeout_s=20`（实测 B2 单次 2.5–5.4s 含 thinking，留余量）、`max_retries=2`、退避指数（base 2s，无 `retry-after` 时按估算）、`max_questions=8`、`max_state_bytes=16384`、`max_tokens=1024`。
- 全部可配（`.mw/decision.yml`）；超预算立即返回 `budget-exhausted`，不再重试。
- 客户端不抛异常：网络/解析/校验（参数之外的运行时）失败一律归一为 `available=false`。
- **错误类别处置（实测 8 类，证据 RQ-D3 Q3）**：400 `invalid_request_error`（中文 message 带 `unknown_fields`）/403 `permission_error`（模型不可用）/404（**可能是 HTML**，先看 content-type）→ **不可重试**（配置/请求问题）；429 `rate_limit_error`（**无 retry-after 头**，只能自定指数退避）/5xx/超时/连接错 → **可重试**；**HTTP 200 但 body 含 `error` 字段或 `litellm.*Error` 文本** → 必须解析 body 判定（不可只看状态码）；成功体非 JSON → 协议错误；强制 `tool_choice` 下无 `tool_use` 块 → 先走 text 回退，再失败则 `bad-response`。

### D-005 证据行与反馈通道——定档（合并 RQ-D1 与 RQ-D4）

**通道组合（三层，缺一不可）**：

1. **权威结构化记录（evidence 层）**：每次决策调用追加一行 JSON 到**新文件** `.agenticdoc/_autopilot/triage-decisions.jsonl`（append-only、best-effort，仿 `recordDispatchAlarm` 的"写失败不破派发"契约）；字段 = AC-008 全集（dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source）。**它不是 PM 通道**，只是可审计的机器记录。前缀 `[TRIAGE]` 已实测零撞名（12 个 trace 前缀 / 6 个 ledger phase / 11 个 alarm kind / 5 个 doctor 行前缀 / 4 个 session customType 均无 `triage` 命中）。
2. **PM 可见面（同步路径，零额外 turn）**：建议直接拼进**派发回执**（`ui-bridge.ts:2491-2494` 工具返回值 / `:2982` `/worker` 的 `ctx.ui.notify`）—— PM 正看着自己刚发起的工具调用，这是 RQ-D1 认定的最自然面；文案显式写"旁路建议，未据此改派发"与来源标识。
3. **持久面 + 争议唤醒（ledger/alarm）**：`recordDispatchAlarm`（`pm-orchestrator.ts:623-641`，五元组行形状不动，摘要进 `detail`）新增 **notice 类 kind `triage-suggestion`**（进入 `NOTICE_DISPATCH_ALARM_KINDS` `:543-551`，文案经 `describeDispatchAlarm` `:563-610`）；`deliverPmAlert`（`ui-bridge.ts:188-200`，`triggerTurn`）**仅在建议与派发类型不一致时**调用（争议升级；避免每次派发都烧一个 PM turn）。**`recordDispatchAlarm` 是 best-effort 契约**（I/O 失败只 `console.error`，绝不破派发，`:619-641` 注释），本 key 沿用。
   - **doctor 行实现锚点（据 RQ-D2）**：新 `_doctor_decide`（照 `_doctor_dispatch` `mw_common.py:1558`）→ 挂进 `doctor_report`（`:4234-4287`）→ 在 `format_doctor_text` 条件渲染（紧跟 dispatch 块 `:4473-4496`）；**zero-perturbation 铁律**（未配置时输出逐字节不变，新行只在条件成立时发射）；信息行**不进** `_doctor_issues`（不翻转 healthy）；`mw doctor --json` 同步可见。TS 面板若需逐字同步渲染，先例 `ui-bridge.ts:2990-3105`。

**为何不用其它面（实测反例）**：`write-scope-risk` / `model-error` 两类 dispatch-alarm 行**只写不投**、无任何机器读者（doctor 只解析 `write-face-refusal`，`mw.py:2529-2553`）——是本仓"写了但没人看"的现成死面，本设计不得重蹈；`_autopilot/timeline.jsonl` 是 **conductor 单写者**（`pm-orchestrator.ts:349-353`），TS 侧不得写；`_workers.parallel` / task.md 是共享热格式（队列 writer/parser 全链），改它们违背"旁路不改派发"。

**降级呈现（必须与"已产出建议"可机判）**：

- evidence 层：可用 ⇒ 行内有结论值 + `confidence` + `confidence_source`；不可用 ⇒ `available=false reason=<unconfigured|timeout|upstream-error|bad-response|rate-limited|budget-exhausted>`，**无结论值、无 confidence**。
- PM 展示层：**默认静默**（不可用时不投任何建议文案，结构上不可能被误读为"已生效"）；可选配置 `triage_notify_on_unavailable` 开启后投一条 `kind:"triage-unavailable"` notice，文案明示"决策服务未产出建议（reason=…），派发照常"。
- 运维面（AC-010）：doctor 新增 `triage:` 行（前缀 `triage:` 已实测零撞名）—— `triage: enabled <backend> last_probe=<结论> last_suggestion=<seq|none> last_unavailable=<reason|none>`。

### D-006 DP-1（派发前分诊）接入点——定档（据 RQ-D1）

- **本波挂点 A：`planDispatchFrontmatter` 入口**（`ui-bridge.ts:1257`；两个 PM 入口共用：`dispatch_worker :2440` 与 `/worker :2938`）。理由：单点覆盖全部 PM 发起的派发；此处数据面最全（`description` 全文 + `cardGate.sections` + `ownerPhase` + index 行）；且位于任何 fs 写之前（拒绝零副作用）。
- **后续波挂点 C：Python `dispatch()` 校验段**（`dispatch.py:1427-1470`，REGISTRY 校验后、`:1519` 起的 `workers.lock` 临界区**之前**——绝不可进临界区，同步 HTTP 会拉长锁持有）。它才能覆盖 conductor 的 13 个自动派发点（`roadmap-writer`/`phase-writer`/`verifier`/`reviewer`/`repair`），但输入较薄（无 PM 窗口上下文、合成信封正文最简 `dispatch.py:778-819`）。
- **时序**：默认 **同步 + 硬超时**（默认 8s，可配）—— 使建议能进派发回执（spec AC-007 "派发前"）；超时/失败 → 无建议、派发照常（与 `validateModelValue` 的 fail-open 风格一致，`dispatch-models.ts:180-186`）。`mode: async`（派发入队后异步产出、经 ledger 落痕）作为配置位记录，不在本波交付。
- **输入面**：`state` = 卡片正文/description + `ownerPhase`（+ index 行 Deps 事实可选）；`questions` = `triage_type`（choice: coding/research/review）+ `triage_risk`（choice: low/mid/high）。
- **风险等级口径（关键）**：派发面**不存在**显式 risk 字段（task.md 头字段全集 `dispatch.py:852-1003` / `ui-bridge.ts:2180-2233`、queue 行 `conductor.py:6489-6503`、`REGISTRY`、watchdog 均无）。因此 `triage_risk` 是**新增语义**（模型基于卡片文本 + phase 的建议），**不得**与运行期 `computeRisk`（`worker-mode.ts:351-370`，checkpoint 收敛风险，消费点 `pm-orchestrator.ts:1636-1660`）混同；证据行与文案上须可区分（前者 `src=dispatch`，后者 `src=checkpoint`）。
- **覆盖面事实（禁止宣称全量）**：PM 手动派发 ×2（`ui-bridge.ts:2235` / `:2790`）= 本波 100% 覆盖；conductor 自动派发 ×13 绕过本波挂点（需后续波挂点 C）；孤儿重派 ×2（`pm-orchestrator.ts:1050-1113`、`conductor.py:6469-6520`）无分诊时刻、不需覆盖；worker 自我分拆不存在（worker 模式不注册任何工具，`ui-bridge.ts:2501-2507`）。→ **本波覆盖 2/15 个分诊调用点（全部 PM 发起派发）；A+C 才为 15/15。**
- 接入形态：**旁路建议**，不写回派发的 `type`/角色/模型字段，不改 watchdog/checkpoint 策略（spec AC-007）。

### D-007 配置面（默认关闭）

- 新文件 **`.mw/decide.json`**（JSON，与 CLI 同名；kebab-case 目录下现有 JSON 先例：`serve.meta`）；缺失/损坏 → 决策功能整体 disabled（fail-soft），不影响任何既有流程。
- **实现锚点（据 RQ-D2）**：读侧照 `load_dispatch_config` 的 fail-soft 双返回（`(data, error)`，缺文件 = 未配置、坏文件 = 错误串给 doctor）`mw_common.py:224-252`；写侧照 **P-003 原子写**（temp + `os.replace`，`console_run.py:191-195`），`encoding="utf-8"` + `newline="\n"`；如需要读改写再加 `acquire_lock`（O_CREAT|O_EXCL，`mw_common.py:2279-2298`）。
- 字段（草案）：`enabled`、`transport`、`model`、`timeout_s`、`max_retries`、`max_questions`、`max_state_bytes`、`max_tokens`、`points.{dp1}.enabled`、`points.{dp1}.alert_on_disagreement`（默认 true）、`triage_notify_on_unavailable`（默认 false）。
- **传输旋钮（W1 实装确认，经 `cfg.extras` 透传）**：`base_url`（默认 timiai llmproxy）、`api_key`（**不推荐写盘**，推荐 env `TIMI_API_KEY` / `~/.pi/agent/auth.json` `timi.key`）、`entry_probe`（B1 入口探测开关）、`systemone_url`（B3）、`jev_model`（B1 模型 id）。`mw decide set` 必须接受并校验这些键。
- 读写遵循既有 fail-soft 与原子写约定（`mw_common.py:217-261` 模式 + P-003）。

### D-008 凭据与隔离

- 只依赖 `TIMI_API_KEY`（env → `~/.pi/agent/auth.json` 的 `timi.key`），复用既有凭据解析/剥离模式；不新增凭据文件与字段。
- 日志与证据不落明文 key；错误文本按既有截断规范收敛。

### D-009 并行写入边界

- `mw.py`：只增 `cmd_decide` + 一行注册；与 `mw-goal-gate-write-intent`（active）的 `_goal_gate_install` 及其安装点互不触碰。
- `packages/multi-workers/CHANGELOG.md`：只追加本 key 自己的 `[Unreleased]` 条目，不重排他人段落。
- 若提交时目标文件含他窗改动 → 索引级重建（`git show HEAD:` + 选择性 hunk + `hash-object`/`update-index`），工作树零触碰。

## §3 模块与文件划分

| 文件 | 动作 | 争用面 |
| --- | --- | --- |
| `packages/multi-workers/decision.py` | 新增（契约/预算/证据行/fail-soft） | 无 |
| `packages/multi-workers/decision_backends.py` | 新增（B1/B2/B3 + fake） | 无 |
| `packages/multi-workers/test_decide.py` | 新增（fake transport 全覆盖） | 无 |
| `packages/multi-workers/mw.py` | 增 `cmd_decide` + 一行注册 | 与 `mw-goal-gate-write-intent` 同文件（不同函数） |
| `packages/multi-workers/mw_common.py` | 增 doctor 一行调用 | 当前无 other-window 改动 |
| `packages/multi-workers/README.md` / `CHANGELOG.md` | 文档与条目追加 | CHANGELOG 与他 key 同文件（不同段落） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | DP-1 旁路建议：`planDispatchFrontmatter` 入口（`:1257`）调用 + 回执拼接（`:2491`/`:2982`） | 与 `mw-model-fallback-cli` 同文件，但其写入面为 `:3302-3391` 的 `/mw model` 段，与本 key 段落不交叠 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | 新增 notice kind `triage-suggestion`/`triage-unavailable`（`:479-549`）+ `describeDispatchAlarm` 文案（`:563-610`） | 据 RQ-D4 实测：不在任何 active key 的声明写面 |
| `.agenticdoc/_autopilot/triage-decisions.jsonl`（运行期产物） | 新增（append-only，best-effort） | 同目录已有 TS 写者（`auto-decisions.jsonl`），无格式冲突 |

## §4 接口与协议

见 D-003（CLI/API 契约）、D-005（证据行）、D-007（配置 schema）。CLI 形态：

```bash
mw decide --request-file req.json            # 或 stdin
mw decide --probe                            # 传输矩阵诊断（AC-004）
mw decide --show                             # 打印生效配置与后端可用性
```

## §5 测试策略

- `test_decide.py`（新增，pytest，沿用包内既有骨架）：fake transport 覆盖 AC-001/002/003/006/007/008。
  - **骨架与跑法（据 RQ-D2）**：文件头 docstring 交代契约与 T-xx 背景；`sys.path.insert(0, str(pathlib.Path(__file__).parent))` + `import mw  # noqa: E402`；`MW_PY = pathlib.Path(__file__).parent / "mw.py"`；`autouse` fixture 做 env 隔离（`monkeypatch.setenv`/`delenv`）；一切产物落 `tmp_path`；裸 `assert` + 失败上下文；CLI 级用 `subprocess.run([sys.executable, str(MW_PY), "decide", ...], encoding="utf-8")`；人工可见断言行 `[VERIFY]` 约定（不参与断言）。跑法：`cd packages/multi-workers && python -m pytest -q`（e2e 由 `pytest.ini` 默认 deselect；根 `./test.sh` 只覆盖 TS）。
  - 契约测试：四型问题、响应字段完整性、`confidence_source` 传播。
  - fail-soft 矩阵：不可达/超时/429/5xx/非 JSON/上游错误体 → `available=false` + 正确 `reason`，且不抛异常。
  - 预算测试：超时、重试上限、最大问题数、state 字节上限。
  - 等价性测试：`enabled=false` 与"决策不可用"两条路径下，DP-1 接入点的行为与未接入一致（逐分支）。
- 真实链路：`mw decide --probe` 作为**证据**（AC-004），不做 CI 断言（上游可波动）。
- 全量：`./test.sh` 相关套件（对比既有环境红列，零新增）。

## §6 风险与回退

| 风险 | 影响 | 处置 |
| --- | --- | --- |
| D-1 长期不解除 | B1 不可用 | B2 承载同一契约；B1 保持显式阻塞；上游开通后 `--probe` 复验并切换 |
| 上游契约与预期不符 | B1 编码方式需改 | 入口形状只在 `decision_backends.py` 的 B1 内，加 backend 级测试锁 |
| 过渡后端置信度不可信 | PM 误判 | `confidence_source` + 文案标注；DP-1 建议为旁路，不自动生效 |
| `mw.py` 并发改动 | 提交冲突 | 索引级重建；必要时等 `mw-goal-gate-write-intent` settle |
| 决策调用拖慢派发 | 延迟 | 同步调用有硬超时；DP-1 失败一律旁路跳过；默认关闭 |

## §7 待证据回填（设计相位）

- ~~**RQ-D1**（`design-dp1-triage-anchors-20261016.md`）→ D-006 接入点定档与覆盖面事实~~ **已回填（2026-10-16）**：挂点 A（`ui-bridge.ts:1257`）本波，挂点 C（`dispatch.py:1427-1470`）后续波；覆盖面 2/15。
- **RQ-D2**（`design-mw-python-patterns-20261016.md`）→ D-001/D-005/D-007 的骨架与 `[XXX]` 前缀避让。**已回填（2026-10-16）**：CLI argparse 锚点、`.mw/decide.json` + P-003 原子写、doctor 行锚点与 zero-perturbation、pytest 骨架与跑法、40+ 前缀避让表（`[TRIAGE]`/`triage:` 均零撞名）。
- **RQ-D3**（`design-transport-b2-contract-20261016.md`）→ D-002 B2 的请求模板、错误类别清单、置信度局限。**已回填（2026-10-16）**：模板 + 8 类错误处置 + `confidence_source` 硬规则入 D-002/D-004。**已实装验证（T-01b）**：33 个 hermetic 用例全绿；1 次真实 B2 调用 `available=true, latency_ms≈5200`，返回 `triage_type`/`triage_risk` 两项且均带 `confidence=0.8`（`confidence_source=model-self-report`）→ 该置信度不得用于门控，与 D-004 一致。
- **RQ-D4**（`design-feedback-channel-20261016.md`）→ D-005 反馈通道定档。**已回填（2026-10-16）**：合并 RQ-D1，定为三层（结构化 JSONL + 回执 echo + ledger/alert 争议唤醒），降级默认静默 + doctor `triage:` 行。
