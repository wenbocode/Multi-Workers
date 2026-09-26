# Design: 自动决策的审计、开关与回滚（D5 / key `mw-autopilot-slot-capacity`）

> 角色：DESIGN 期设计卡（**只读**调研 + 单文件写入）。本文件是本次唯一写入的仓库文件；未改代码/config，未答任何 gate，未碰 FM/E2/JC，未 commit。
> 代码基线：`H:/git/Multi-Workers` HEAD `191a069a4`（本次逐行复核了本文件引用的全部 `file:line`；与 RQ-10/RQ-11 引用行号的差异已就地更正）。
> 数据基线：引用 `spec-auto-gate-boundary-20260926.md`（RQ-10）、`spec-auto-gate-guardrails-20260926.md`（RQ-11）、`spec-unattended-stage-closure-20260926.md`（RQ-8）、`spec-gate-defer-safety-20260926.md`（RQ-13）的冻结实测，不重算。
> 上游决策（已锁）：U-6=C（机器自动过**部分** gate）、U-8=混合制（证据定白名单 + PM 提案黑名单）、U-9=**B**（熔断 = 停自动 + 升级给人 + 报告）、U-1=A（主交付 = 命题重设计 + 三分处置 + 护栏）。

## TL;DR

1. **留痕用一条新事件 + 独立 append-only 账本，而不是靠 `answered_by`**：新事件 `gate-auto-decision`（timeline 行新增可选 `data` 结构化载荷：`decision_id / gate_id / rule_id / rule_version / decided_by / decided_at / mode / decision / executed / switch{...}/ evidence[{path,sha256,mtime_ns}] / budget{...}`）。**权威字段一律由 conductor 派生**（`decided_at` 取 conductor 时钟 + timeline `seq`，不取 gate `answered_at`；证据用决策时刻的 sha256 快照，不取 gate `note`/`context_refs` 散文）。gate 文件的 `answered_by`/`answered_at` 明确降级为**展示字段、非权威**。
2. **防伪有三个硬缺口必须先补**：(i) `gate-\d{4}` 正则（`conductor.py:310`）在 `gate-10000+` 静默失效（RQ-11 F6-D1）；(ii) **`.agenticdoc/_autopilot/timeline.jsonl` 与 `_autopilot/config.json` 目前不在任何工具层守卫内**（`xkey-gate-guard.ts:60` 只封 `_autopilot/gates`；`protected-config.ts:42` 只封 `~/.pi/agent/*.json`）——被审方可以直接 append 伪造事件或翻转开关；(iii) 消费记录不可撤销（`_consumed_gate_ids` 由 append-only `gate-answered` 反推，`conductor.py:297-313`）⇒ 撤销必须改成**按 `decision_id` 记账 + 负记录**。
3. **开关选型推荐 `auto_gate_mode`（str，闭集 `off|shadow|live`，默认 `off`，不加入 `EFFECTIVE_KEYS`）**：一个键同时覆盖 AC-018（只停自动决策）与 AC-024（影子模式），且无非法组合；代价 = 两侧镜像 + parity 语料 53→约 55 + `FROZEN_CORPUS_SHA256/COUNT` 重冻。
4. **配额/熔断全部复用既有原语、不自造状态机**：P5（同 gate 只消费一次）+ P4（尝试上限 + 持久 exhausted 标记，`conductor.py:2872/2959-2979`）+ P3（`advance_stall_ticks` 1..50 作为"连续重复"上界）+ `gate.created_at`（天然冷却时钟）+ P6（文件驱动硬停杆）+ P9（kill switch）。阈值参照量：洪泛实测 **6684 门 / 11.41h / 单夜 5364 / 峰值 17·min⁻¹ / 585.8·h⁻¹ / 2 key**，而"100% 一致"回放上界只有 **28 门 / 单夜 ≤3**。
5. **熔断状态必须落盘（不能只扫 timeline 窗口）**：timeline 只留 **2 代**（`timeline.py:93-94`），窗口扫描会像 JC `gate-0008` 重放那样被轮转吃掉（RQ-11 F6 / RQ-14）。⇒ 触发时 create-once 写持久刹车标记 + 一条 `decision=escalate` 事件；重启后从标记重推，仍然熔断。
6. **回滚三件套**：按来源过滤（查 `gate-auto-decision` 事件）· 批量回看（`mw doctor` autopilot 段 + `/autopilot` 视图，当前两处对 gate 零内容/只列 pending：`mw_common.py:2022-2065`、`console.ts:182-200`、`monitor.ts:644-655`）· 单条撤销（`gate-auto-revoke` 事件，消费集合 = `answered − revoked` 按 `decision_id` key；stage 状态处理**依赖 D3/D4 的单调性矩阵**）。
7. **影子模式 = `mode=shadow`，只写账本不动状态**；最小样本 = **≥5 夜 ∧ ≥20 条影子决策 ∧ 每个拟上线 rule 至少 1 条"命题为假"的反例**（否则该 rule 恒真、零信息量，AC-025 判据）。收益量化直接可用 RQ-8 的**过夜占比 88.0%/85.6%** 与 RQ-13 的**门→收口视界 p50 24.48h / max 145.99h**。

## 决策问题

本卡只回答 AC-018 / AC-019 / AC-024 / AC-030 的**设计**（RQ-10 已定"哪些门可自动"的边界，RQ-11 已定"护栏候选"，D1–D4 负责命题/延后/消费记录/证据源）。5 个问题：

1. **审计留痕**：自动决策要写什么事件、字段契约是什么，才能让审计**独立**回答"谁做的决定 / 依据哪份证据快照 / 命中哪条规则 / 当时开关状态"？现有 17 个事件类型（`timeline.py:67-85`）与 TS `EVENT_TYPES`（`status-model.ts:779-796`）要同步什么？两侧一致性判据是什么？新字段如何做到**不可由被审方伪造**（AC-030：`answered_by`/`answered_at` 应答者可写）？
2. **"只停自动决策"开关**（AC-018）：现状 `enabled=false` 终止整个 conductor（`mw.py:140-196`）、`paused=true` 软停整个 orchestrate（`conductor.py:2060`），无 auto-only 粒度。给 ≥2 方案 + pros/cons；新键方案给键名/类型/默认值/两侧镜像面/parity 语料影响与重冻流程。
3. **每夜配额与熔断**（AC-017/AC-019）：上界复用哪些 P1–P9 原语（`file:line`）？熔断判据（哪些信号）、阈值来源（洪泛实测）、动作 = B、以及**熔断状态是否持久化**。
4. **回滚与批量回看**（AC-018）：`_consumed_gate_ids` 不可逆 ⇒ 替代设计：按来源过滤 / 批量回看 / 撤销单条（含撤销后 stage 状态，与 D3/D4 单调性交叉）。
5. **影子模式**（AC-024）：模式定义、记录载体与字段、最小样本判据（含 0 样本门类）、影子期收益量化（引用 RQ-8/RQ-13 等待实测）。

## 调研方法与出处

### 代码锚点（本次逐条复核，行号 = HEAD `191a069a4`）

| 面 | 锚点 |
|---|---|
| timeline 事件词表 | Python `timeline.py:67-85`（17 类）；`_read_events` 保留整条 dict `:183-208`；`Timeline.append(ev,key,stage,detail)` `:274-320`；`query_events(...,ev_filter)` `:393-435`；轮转 `ROTATE_GENERATIONS=2` `:94` |
| 事件行 schema | `{ts,seq,ev,key,stage,detail}`（`timeline.py:10-17` 协议注释 + `:301-316` 写入）；TS `TimelineEvent` `status-model.ts:807-814`，TS 解析器**白名单** `:882-889` |
| TS 事件词表 | `status-model.ts:779-796`（16 类，**缺 `target-config-rejected`**）；`nonBeatFilter` `:798-804` |
| 门 schema | Python `gates.py:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:68-81`（`FRONTMATTER_FIELDS` 12 字段）、`create()` `:262`；TS `GATE_KINDS` `status-model.ts:561-568`、`GATE_FRONTMATTER_FIELDS` `:585-598`、`GateRecord` `:587-598`（**不含 answered_at/by/note**）、`GateView` `:1035-1039`（只 id/kind/status）、`STATUS_SCHEMA="autopilot-status/1"` `:1009` |
| 应答路径 | `answerGate` `gate-writer.ts:139-186`：只重写 `status/answered_at/answered_by/note`，`answeredAt` 由调用方传入（`:147`）、`answeredBy` 自由文本（`:146`）；`/autopilot gate` `console.ts:204-245`（`answeredBy: windowClaimId()`） |
| 消费与幂等 | `_consumed_gate_ids:297-313`（正则 `:310` = `r"(gate-\d{4})\b"`）；`_consume_answered_gates:316-378`；`_apply_stalled_approvals:2295-2360`（消费守卫 `:2314-2331`，含 6684 洪泛事故注释）；`_apply_stalled_rejections:2363-2394`（**无消费守卫**） |
| 终态/依赖/收口 | `_DEP_SATISFIED = {"done","closed-legacy"}` `:56`；`_stage_closure:616-656`（终态集 `:629-631`）；`_set_stage_status:380-407`（**无单调性检查**）；`_ensure_next_stage_gate:409-431`；`_deps_satisfied:2153-2154` |
| 预算/上界原语 | `_resume_credits:2273-2293`（**无上界**）；`round_budget` `config.py:53/71`；`advance_stall_ticks` `config.py:57/75` + `_advance_stall_ticks:794-799` + `_advance_failure_streak:803-866`；`_XKEY_PROPOSAL_MAX_ATTEMPTS=2` `:2872` + `_xkey_proposal_exhaust:2959-2979` + 判定 `:3021-3027`/`:3051-3057`；xkey 锁 `xkey.py:102`（`xkey-ledger.lock`）、`ledger_append:544`、`ticket_write:790` |
| 停杆/门去重 | `enabled`/`paused` `config.py:49-50`；`tick` 门 `:2060`；goal 分支 `:2064-2113`（halt `:2093`、恢复 `:2100-2111` **不区分 approved/rejected**）；`_gate_open:2188-2214`；`open_goal_change_gate:174-181` |
| 进度信号 | `advance` 事件 detail `"{edge} exit=0"` / `"{edge} exit={code} class={cls}"` `_record_advance_result:868-902`；`dispatch` 事件 detail `"{task_key} type=… loop=… attempt=…"` `dispatch.py:596-600`；`stalled` 事件 detail = reason `conductor.py:4016` |
| 配置读写 | Python `config.py:48-61`/`:63-76`/`validate_config:89-132`/`save_config:150-165`；TS `AutopilotConfig:75-101`、`DEFAULT_CONFIG:102-115`、`BOOL_FIELDS:125`、`LIST_FIELDS:128`、`STR_FIELDS:131`、`INT_RANGES:134-143`、`readConfig:229`、`saveConfig:289-322`（显式 14 键 ordered literal）；两层合并 `effective_config.py:66-70`（`EFFECTIVE_KEYS` 仅 2 个 xkey 键）/`:76`（`EMPTY_VALUE`） |
| parity 语料 | `test/fixtures/autopilot-config-corpus.json`（53 例）；`test_autopilot_config_parity.py:60-61`（`FROZEN_CORPUS_SHA256="951987eaf2ab…594d"`、`FROZEN_CORPUS_COUNT=53`）、P4 `:310-321`、P6 `:389-432`（断言 13 键 + `covered == KNOWN_FIELDS`，`KNOWN_FIELDS` 定义 `:63`）；TS 侧 `autopilot-config-parity.test.ts:343-373`（13 键断言 `:356/:359`）、`autopilot-config-sync.test.ts:157-181`（注册表分区 = 键数） |
| 观测面 | 面板 `monitor.ts:89-95`（`MonitorGate` 只 id/kind/stage/key）、`scanPendingGate:148-180`（**只收 pending**）、slots 行 `:596-599`、gates 行 `:644-655`；`/autopilot gates` `console.ts:182-200`（只列 pending）；`mw doctor` `mw_common.py:2022-2065`（**只有 xkey**） |
| 工具层守卫 | `xkey-gate-guard.ts:60` `GATE_DIR_FRAGMENT = ".agenticdoc/_autopilot/gates"`（**仅门目录**）；`protected-config.ts:42` `PROTECTED_CONFIG_FILES = auth/models/settings/oauth.json`（**仅 ~/.pi/agent**）；注册点 `index.ts:42/49/59` |
| 文档面 | `README.md:225`（config 键表）、`:271`（机器层仅 2 键）、`:276`（"所有写入者都材料化 13 键"）；`UPDATE.md:69`（CLI 指令矩阵） |

> 与 RQ-10/RQ-11 的行号差：RQ-11 写 `timeline.py:67-84`，实测 17 类跨 `:67-85`；写 `status-model.ts:779-796`，实测跨 `:779-796`（一致）；写 `conductor.py:310`（一致）。下文一律用本表行号。

### 数据引用（不重算）

- **RQ-10**：3 项目 34 条唯一人工应答 **34/34 approve、reject 0**；有样本的 4 类 = `stalled 22 / stage-confirm 7 / stage-close 4 / goal-change 1`；0 样本门 = `budget-exhausted`/`xkey-authorize`；0 样本事件 = `goal-halt`/`type-rejected`/`target-config-rejected`；洪泛陷阱：FM `gate-answered` 6694 条只来自 10 个门（`gate-0002` 重放 5588 + `gate-0003` 1098）+ 6684 个归档 pending；`answered_at` 3 处不自洽（E2 `gate-0007` 早 4.1h、FM `gate-0002/0003` 晚 104s）；5 类机器可抽原因（`context_refs[1]`）。[VERIFY]：`reject_path_samples=0`、`uniform_answer_gates=4`。
- **RQ-11**：9 类原语 P1–P9；`_consumed_gate_ids` 正则溢出 `gate-10000`；reject 路径无消费守卫；18/34 门证据 mtime 晚于应答（RQ-14 修订为 24/34）；洪泛 6684 / 11.41h / 单夜 5364 / 峰值 17·min⁻¹ / 585.8·h⁻¹ / 2 key；回放"100% 一致"最多 28 门、单夜 ≤3；`_resume_credits` 无上界；TS `EVENT_TYPES` 漂移缺 `target-config-rejected`。
- **RQ-8**：stalled 占墙钟 FM 54.6% / E2 46.5%；**stalled 等待过夜占比（22:00–08:00）FM 88.0% / E2 85.6%**；stalled 等待 p50 3.62h/4.04h、max 17.40h；stalled 阻塞 stage（`conductor.py:629-631`）与依赖（`:56`/`:2153`）；无人值守策略 **不存在**。
- **RQ-13**：stage 墙钟 n=4 / p50 36.56h / max 150.53h；门→stage 收口视界 n=11 / p50 24.48h / max 145.99h；JC `gate-0007` pending 203.93h；延后窗口内有真实写动作（E2 `gate-0014` 17.40h 内 239 次 write-edit / 80 次落在 `.agenticdoc` 之外）。

### 边界（不做）

不回答"哪些门可自动"（RQ-10）与"命题怎么写"（D1）；不设计消费记录载体（D3）与证据源优先级（D4）——遇到交叉处只**引用或标依赖**；不给实现代码。

---

## 发现

### F1 — 自动决策留痕事件（AC-018 / AC-030）

#### F1a 事件名与字段契约

**新事件 `gate-auto-decision`**（一次自动决策 = 一行；影子与实动共用一种事件，靠 `mode`/`executed` 区分）。timeline 行仍保留 `{ts,seq,ev,key,stage,detail}`，**新增可选 `data`（JSON object）**；`detail` 只写人类摘要（如 `gate-0042 approved by rule=l3-false-negative`），且**明确规定 `detail` 不是判据来源**（对齐 RQ-14 的"`note` 不得作派生输入"）。

`data` 字段契约（审计必须能只靠这一条回答四个问题）：

| 字段 | 类型 | 谁派生 | 审计问的问题 |
|---|---|---|---|
| `decision_id` | str，唯一 | conductor（`"{gate_id}@{decided_at}"`，live 下 gate 只消费一次故唯一） | "撤销/追责对哪一次决策" |
| `gate_id` / `gate_kind` / `gate_stage` / `gate_key` | str/int/null | conductor（从 gate 对象读） | "决定的是哪个门" |
| `mode` | `"shadow"｜"live"` | conductor（读 `auto_gate_mode`） | "这是判断还是动作" |
| `executed` | bool | conductor | "有没有产生副作用" |
| `decision` | `"approve"｜"reject"｜"escalate"` | conductor（rule 求值结果） | "决定了什么" |
| `rule_id` / `rule_version` | str / str | conductor 代码常量 | "命中哪条规则（可复算）" |
| `reason_code` | str，闭集 | conductor（与 D1 的 `reason_code` 提案同源） | "依据哪一类原因" |
| `decided_by` | `"conductor"`（常量） | conductor | "谁做的决定" |
| `decided_at` | ISO8601 | conductor 时钟（**不是 gate `answered_at`**） | "什么时候决定的" |
| `evidence[]` | `[{path, sha256, mtime_ns}]` | conductor 在决策时刻抓取 | "依据哪份证据快照" |
| `switch` | `{enabled, paused, auto_gate_mode, config_sha256, effective_origins}` | conductor（`load_effective` 解析结果） | "当时开关状态是什么" |
| `budget` | `{night_used, night_cap, key_used, key_cap, cooldown_s_left, breaker}` | conductor（每 tick 由文件重推） | "当时还剩多少额度" |
| `gate_file_sha256_before` / `_after` | str/null | conductor（live） | "被改的是不是这一份门" |
| `counterfactual_human` | `"approve"｜"reject"｜null` | shadow 收口时补记（第二次事件，`data.phase="resolve"`） | "人后来怎么答的（影子收益/偏差）" |

**最小充分性论证（对应 4 个审计问题）**：
- "谁做的决定"：`decided_by=="conductor"` + 事件由 conductor 单写（见 F1d）+ 与人工路径的判别是"存在 `gate-auto-decision` 且 `executed=true`"而不是读 `answered_by`。
- "依据哪份证据快照"：`evidence[].sha256 + mtime_ns`，在决策时刻由 conductor 算（AC-030 要求"证据快照绑定"，与 D4 的快照绑定设计**接口相同**：`{path,sha256,mtime_ns}` 三元组——两侧镜像面必须共用同一字段名，见 F1c）。
- "命中了哪条规则"：`rule_id + rule_version`；规则本体是 conductor 代码常量，审计可重放（`rule_version` 变更必须进 CHANGELOG，否则审计无法复算）。
- "当时开关状态是什么"：`switch` 直接快照有效配置 + `config_sha256`；**不靠** `config` 事件（实测 conductor 从不因配置变更写事件：全部 `config` 事件都是错误路径，`:153/212/336/405/644/715/1002/…`）。

**与现有 17 类事件的同步内容**（哪些要动、哪些不动）：

| 现有事件 | 是否要动 | 内容 |
|---|---|---|
| `gate-answered` | **不动格式** | 它同时是 `_consumed_gate_ids` 的解析源（`conductor.py:310`）。自动决策额外写一条 `gate-auto-decision`，审计按 `gate_id` join；**不要**把来源塞进 `gate-answered.detail`（会污染 `re.match` 解析面） |
| `stalled` | 可选加字段 | `mark_stalled` 已写 reason（`:4016`）；若 D1 给门加 `reason_code`，事件同源携带可省一次 join |
| `goal-halt` | 需补 | 现在只有 `mtime_ns X -> Y`（`:2093`）；`goal-change` 进影子模式前需 D1 的 `goal_diff`/`goal_sha256`（RQ-10 F5） |
| `advance` / `dispatch` | 不动 | 直接作为"两次 auto 之间是否有进展"的进度信号（C3 熔断判据） |
| `config` | 不动 | 全是错误路径；开关状态改由 `data.switch` 快照 |
| 其余 12 类 | 不动 | 无 gate 决策语义 |

**新增事件就够了吗**：不够。`gate-auto-decision` 落在 timeline 上会被 2 代轮转剪掉（`timeline.py:93-94`）⇒ 权威账本另置**只增 JSONL**`<root>/.agenticdoc/_autopilot/auto-decisions.jsonl`（同 timeline 协议：append + seq + 轮转，conductor 单写），影子样本与撤销溯源以它为准，timeline 事件作为可 join 的实时投影。这是本设计对"撤销可追溯"的关键落点（否则重演 JC `gate-0008` 的"记录被轮转吃掉"）。

#### F1b 两侧镜像面（必须逐项同步）

| 面 | Python | TS |
|---|---|---|
| 事件词表 | `timeline.py:67-85` 加 `gate-auto-decision` | `status-model.ts:779-796` 加同名 **且补 `target-config-rejected`**（现存漂移） |
| 行载荷 | `Timeline.append` 增可选 `data`（`:274-320`）；`_read_events` 已透传整 dict（`:183-208`）无需改（**但需加断言**） | `TimelineEvent` 增可选 `data`（`:807-814`）；**解析器白名单 `:882-889` 必须加 `data`**，否则静默丢弃 |
| 读取路径 | `timeline.query_events(ev_filter={"gate-auto-decision"})` | `queryTimeline(path, mark, new Set(["gate-auto-decision","gate-auto-revoke"]))` |
| 账本读取 | 新增只读 helper（`.agenticdoc/_autopilot/auto-decisions.jsonl`） | `status-model.ts` 增同路径读取（或经 `mw doctor --json` 暴露，避免两条实现） |
| 门字段（若 D1 采纳） | `gates.py:68-81` 12 字段（`reason_code`/`machine_evidence` 等按 D1 结论） | `GATE_FRONTMATTER_FIELDS:585-598` + `GateRecord:587-598`（**当前不读 answered_*，需扩**） |
| 面板/视图 | `mw_common._doctor_autopilot:2022-2065` 增 auto 段 | `monitor.ts` gates 行（`:644-655`）+ `console.ts cmdGates:182-200` 增 auto 视图 |

#### F1c 两侧一致性判据

1. **词表同构（硬判据）**：`sorted(timeline.EVENT_TYPES) == sorted(status-model.EVENT_TYPES)`。做法：新建共享冻结表（先例 `test/fixtures/autopilot-config-corpus.json`、`active-mode-table.json`），TS 侧 vitest 起 Python 子进程 dump `sorted(EVENT_TYPES)` 逐项比对；**fail-closed，不用 `skipIf`**（P-016 / D-013）。当前两表 17 vs 16，**这条判据今天就是红的**——即 D3（TS 缺 `target-config-rejected`）的回归护栏。
2. **载荷透传（硬判据）**：给定一行含 `data` 的 `gate-auto-decision` 夹具，Python `query_events` 与 TS `queryTimeline` 返回的 `data` 深相等（字段名/类型/嵌套）。Python 现成通过（整 dict 透传），TS 需改 `:882-889`，判据可当场证伪。
3. **字段集合冻结**：上表 F1a 的字段名集合写进共享夹具，两侧各断言"缺失即失败"；新增字段必须同时改夹具 + 两侧测试（P-021：verify 期两侧都跑）。
4. **不新增第二事实源**：判据断言 `_consumed_gate_ids`（`:297-313`）与 `gate-auto-decision` 的 join 结果一致——即"事件说的决定"与"消费记录实际生效的决定"逐条对齐；不一致即为可检测的信号（AC-017 要求"可检测信号"）。

#### F1d 防伪（AC-030 核心）：谁写 / 写在哪 / 如何校验

**实测前提（为什么不能信 `answered_by`）**：`answerGate` 只重写 4 个字段、`answeredAt` 由调用方传入（`gate-writer.ts:139-152`）；`gates.py` 把"手改文件"当合法应答（RQ-10 引用 `gates.py:1-20`）；实测 3 处时间戳不自洽（E2 `gate-0007` 早 4.1h；FM `gate-0002/0003` 晚 104s）。⇒ **任何护栏/审计不得依赖 `answered_by`/`answered_at`**。

**四层防伪设计**：

1. **写者唯一**：只有 conductor 进程写 `gate-auto-decision` 与账本（timeline 模块 docstring 已声明 "the conductor is the sole writer"）。人工撤销走"改门文件 + conductor 消费后写 `gate-auto-revoke`"，保持单写者不变量。
2. **路径守卫（当前缺口，硬前置）**：`.agenticdoc/_autopilot/timeline.jsonl`、`auto-decisions.jsonl`、`_autopilot/config.json` 目前**不在任何守卫内** ⇒ 被审 worker 可以用 `write`/`bash` 直接 append 伪造事件或翻转开关。**必须先扩守卫**：把 `_autopilot/**`（至少这三个文件）纳入 `xkey-gate-guard.ts` 的封堵面（该守卫的自述已明确其保证是"拒绝可观测"，不是沙箱——同 uid 的进程仍可写，这点必须写进残余风险）。
3. **字段级不可伪造**：判定所需的一切量都由 conductor 在决策时刻派生，且**不含应答者可写字段**：
   - 时间：`decided_at`（conductor 时钟）+ 事件 `seq`（单调、单写、可从末行恢复 `recover_seq`）——而不是门文件 `answered_at`；
   - 证据：决策时刻的 `sha256 + mtime_ns`（不是 `note`/`context_refs` 散文，不是事后读到的当前文件）；
   - 规则：代码常量 `rule_id/rule_version`（不是管理员手写）；
   - 开关：`load_effective` 的解析结果 + `config_sha256`（不是"我以为的值"）。
4. **可校验（审计侧三条独立检查）**：
   - (V1) **结构性**：每条 `gate-auto-decision`(executed=true) 必须能 join 到一条 `gate-answered`（`gate_id` 相同）；反之，任何"人工路径"的 `gate-answered`（无对应 auto 事件、且门文件 `answered_by` 也不是 auto 值域）即人答。
   - (V2) **快照重算**：用 `data.evidence[]` 的 sha256 重算规则谓词；与 `data.decision` 不一致 ⇒ 证据被事后改写或规则被偷换（RQ-14：24/34 门证据在应答后被改写，这条检查非空转）。同时比对 `mtime_ns > decided_at` 的文件 ⇒ 明确标记"应答后被改写"。
   - (V3) **门文件回改检测**：`sha256(当前门文件)` vs `data.gate_file_sha256_after`；不等 ⇒ 决策后有人改过门（可能是合法人工撤销，那么必须存在 `gate-auto-revoke`；否则告警）。
   - 三条都可写成机器可判 VC（见 F6）。
5. **残余风险（必须显式声明）**：同 uid 的带外进程写入无法在应用层阻止；守卫只能让"经 agent 工具通道"的伪造留下拒绝记录（`recordXkeyGateBlockTrace:241-259`）。若 PM 要求更强保证，需另立 key 做进程隔离/签名（超出本 key，且与 GC-1/GC-2 无关）。

**次生结论**：`answered_by` 的值域应收紧为闭集并在门文件里写入 `conductor-auto:<rule_id>`（人读友好），但设计上把它标为**展示字段**；权威仍以事件/账本为准。`answered_at` 的噪声（RQ-10/RQ-14）不需要修——审计路径不再消费它。

---

### F2 — "只停自动决策"开关（AC-018）

#### F2a 现状（已复核）

| 杆 | 语义 | 生效路径 | 锚点 |
|---|---|---|---|
| `enabled=false` | serve **terminate** conductor（全停） | `_conductor_decision` → `proc.terminate()` | `mw.py:140-196` |
| `paused=true` | conductor 存活、仍写 `beat`，但不 `orchestrate`（软停全部） | `tick` 第 2 步 `if not cfg["enabled"] or cfg["paused"]: return "idle"` | `conductor.py:2060` |

⇒ **无 auto-only 粒度**（RQ-11 F4 同结论）。二者都停"整个 autopilot"，不是"只停自动决策"。

#### F2b 方案对比

| # | 方案 | 机制 | pros | cons |
|---|---|---|---|---|
| **A1（推荐）** | 新键 `auto_gate_mode`（str，闭集 `off｜shadow｜live`，默认 `off`） | `tick` 在 orchestrate 前读有效配置；`off` ⇒ 完全不跑 auto 子系统（行为 = 今天） | ① 一个键同时覆盖 AC-018（`off`）与 AC-024（`shadow`），无非法组合；② opt-in 默认关，对齐 `xkey_repair` 范式（AC-020）；③ 可被 console/CLI 两条写路径材料化；④ 运行时可切 `shadow↔live` 不必碰其它杆 | ① 新增字符串字段 + allowlist 校验（比 bool 多一条交叉语言规则）；② 触发两侧镜像 + parity 语料重冻（F2d）；③ 不在 `EFFECTIVE_KEYS` ⇒ 机器层不可覆盖（**有意**，见下） |
| A1′ | 新键 `auto_gate_enabled`（bool，默认 false）+ 另设 `auto_gate_shadow`（bool） | 两个布尔 | 类型面最简单（沿用 `_BOOL_FIELDS`） | 两个键存在非法组合（enabled∧shadow），需要额外交互校验；语义不如单键清晰 |
| A2 | 复用/扩展 `paused` 语义（例如 `paused` 增第三态 `"auto"`） | 改 `paused` 类型 | 零新键 | **破坏既有语义与消费者**：`paused` 今天在 `conductor.py:2060`、面板 `conductorIntent`（`monitor.ts:521-526` 区）、console `cmdSetPaused`（`console.ts:371-385`）都是二值；改成三态会让"软停整个 orchestrate"与"只停 auto"混淆（正是 AC-018 要分开的两件事）⇒ **否决** |
| A3 | 门级开关（文件驱动硬停杆，复用 P6）：挂一个 pending `auto-halt` 门 / 或 `.agenticdoc/_autopilot/auto-off` 标记文件 | `_gate_open("auto-halt")` 即停 auto | ① 零 config/parity 成本；② 纯文件驱动、重启安全（GC-1）；③ 与 P6（goal-change halt）同范式 | ① 新门 kind ⇒ `GATE_KINDS` 两语言 + 语料 + 门 schema；② **污染人审队列**：面板 `gates: N pending`（`monitor.ts:644-655`）会把刹车当成一个待答门，人被误导；③ 门目录洪泛面再开一个入口（风险 22 家族）⇒ 作为**熔断刹车载体**（F3d）合适，作为**开关**不合适 |
| A4 | 纯 env（`PI_AUTOPILOT_AUTO=0`） | 仅进程 env | 零配置镜像 | ① 撞 P-015：serve 重启路径不同则 env 丢失，"看起来停了其实没停"；② 不可运行时切换；③ 不可发现/不可审计 ⇒ **否决** |

**推荐 A1**。理由：它是唯一同时满足"opt-in 默认关（AC-020）+ 运行时可只停 auto（AC-018）+ 覆盖影子模式（AC-024）+ 不撞既有消费者"的形态。

#### F2c 新键规格（A1）

| 项 | 值 |
|---|---|
| 键名 | `auto_gate_mode` |
| 类型 | string，闭集 `{"off","shadow","live"}`（allowlist，不是自由字符串） |
| 默认值 | `"off"`（fail-closed：未显式开启时行为 = 今天） |
| 语义 | `off` = auto 子系统不运行；`shadow` = 只写影子记录、无副作用；`live` = 可执行动作（仍受 F3 配额/熔断约束） |
| 非法值 | 校验失败（fail-closed）⇒ 与 `config.py:89-132` 现有 fail-closed 语义一致；错误字段名须两侧一致（D5 只断言字段名集合，D-013） |
| 机器层 | **不加入** `effective_config.EFFECTIVE_KEYS`（`:66-70`，保持 2 个 xkey 键）。若机器层写了它，diag 应报 "not machine-overridable (ignored)"。理由：① 新键是策略开关，不该被机器层静默改写；② 加入机器层需要给 `EMPTY_VALUE`（`:76`）一个"未决定"哨兵，而 str 的 `""` 与合法值无歧义但会引入"空值即未决定"的额外规则面（风险 5 / RQ-4 M2 同族）⇒ 明确记为"不改" |
| Python 镜像面 | `config.py` docstring 字段表（`:17-45`）、`DEFAULT_CONFIG`（`:48-61`）、`_STRING_FIELDS`（`:67`）、`validate_config` 新增 allowlist 分支（`:89-132`） |
| TS 镜像面 | `AutopilotConfig`（`:75-101`）、`DEFAULT_CONFIG`（`:102-115`）、`STR_FIELDS`（`:131`）、`readConfig` 合并（`:229-287`）、`saveConfig` 的 `ordered` 字面量（`:289-322`）、`validateConfigData` 的 allowlist 分支 |
| 写入路径 | console `saveConfigLocked`（`console.ts:293-317`）+ `cmdSetEnabled/cmdSetPaused` 同范式（`:319-385`）新增 `cmdSetAutoGateMode`；CLI 可复用 `mw autopilot` 组（`mw.py:3514+`） |
| 观测面 | 面板 `conductorIntent`（`monitor.ts` conductor 行）追加 `auto=off/shadow/live`；`mw doctor` auto 段（`mw_common.py:2022-2065` 扩展） |
| 文档面 | `README.md:225`（键表）、`:276`（"13 键"措辞 ⇒ 14）；`UPDATE.md:69`（CLI 矩阵） |

#### F2d parity 语料影响与重冻流程（参考上一 key 的 D-012/D-013）

**影响面（实测锚点）**：
1. **键数**：`test_autopilot_config_parity.py::test_p6_partial_single_key` 断言 `len(effective_keys)==13` 与 `ts keys==13`（`:423-431`），且 `covered == set(KNOWN_FIELDS)`（`KNOWN_FIELDS = list(config.DEFAULT_CONFIG)` `:63`）⇒ **语料必须为每个键提供一条"仅含该键"的 accept 用例**，否则 P6 直接红。TS 侧同断言（`autopilot-config-parity.test.ts:356/:359` 的 `toBe(13)`）。
2. **语料哈希/条数**：`FROZEN_CORPUS_SHA256="951987eaf2abebfa256365ed6642ce1ae0b077a2a6a6c18b4f974729c7dc594d"`、`FROZEN_CORPUS_COUNT=53`（`:60-61`）会被 P4（`:310-321`）硬断言 ⇒ 加用例即改 sha/条数。
3. **P4 类别覆盖**：断言 `{"D1".."D6"} ⊆ categories`（子集，加新用例可用既有类别或新类别）。
4. **P5/D5 镜像**：`autopilot-config-sync.test.ts:157-181` 断言注册表并集 = 键数（自动适配），但 `BOOL/LIST/STR/INT` 分区必须显式加新键；`validateConfigData` 的 allowlist 分支需与 Python 逐字一致（D5 只比字段名集合，值渲染差异不进判据）。

**重冻流程（5 步，可复算）**：
1. 两侧同步 `DEFAULT_CONFIG` / 类型登记 / allowlist 校验（F2c 镜像面）；
2. 语料加 ≥1 条 accept（`{"auto_gate_mode":"shadow"}`）+ 可选 1 条 reject（非法值，验错误字段名两侧一致）；
3. 更新两侧的 `13 → 14` 计数断言与文档注释（`test_autopilot_config_parity.py:423-431`、`autopilot-config-parity.test.ts:356/359`）；
4. 重算语料 `sha256` 与条数，更新 `FROZEN_CORPUS_SHA256`/`FROZEN_CORPUS_COUNT`（`:60-61`）；
5. 两侧都跑（P-021）：Python `test_autopilot_config_parity.py` + TS `autopilot-config-parity.test.ts` / `autopilot-config-sync.test.ts`。

**对齐 AC-018 的判据**：`auto_gate_mode="off"` 时，判据 = "窗口内 0 条 `executed=true` 的 `gate-auto-decision`，且 `beat` 持续、人工 gate 应答照常生效、`_resume_credits` 不受影响" ⇒ 与今天行为逐项一致。

---

### F3 — 每夜配额与熔断（AC-017 / AC-019）

#### F3a 上界：复用哪些原语（全部给 `file:line`）

| 上界 | 复用原语 | 锚点 | 形态（GC-1 合规：每 tick 由文件重推） |
|---|---|---|---|
| 同 gate 只自动决策一次 | **P5** `_consumed_gate_ids` + `_gate_open` | `conductor.py:297-313`、`:2188-2214` | 消费集合改为按 `decision_id` 记账（见 F4d），每次调用重推 |
| 单 key 在窗口内的自动决策次数 | **P4** 范式（尝试上限 + 持久 exhausted 标记，不自旋） | `_XKEY_PROPOSAL_MAX_ATTEMPTS=2` `:2872`；`_xkey_proposal_exhaust:2959-2979`；判定 `:3021-3027`/`:3051-3057` | 计数从 `auto-decisions.jsonl` 窗口扫描重推；超限写持久 `auto_exhausted_at` 标记（对齐 xkey 的 `proposal_exhausted_at`） |
| 连续重复（同 key 同原因） | **P3** `advance_stall_ticks`（**1..50 唯一有界旋钮**） | `config.py:57/75`；`_advance_stall_ticks:794-799`；streak 重推 `_advance_failure_streak:803-866` | 复用同一键语义（"连续 N 次"）作为 auto 重复上界，不新增键 |
| 冷却窗（同 key 两次 auto 间隔） | **`gate.created_at`**（盘上已有，天然时钟） | `gates.py:68-81`（`created_at` 字段）、`_gate_file_content:159-175` | 零新状态：末次 auto 的 `decided_at`（账本）与门 `created_at` 比 |
| 进度门（两次 auto 间必须有新进展） | **timeline 事件**（`advance`/`dispatch`） | `_record_advance_result:868-902`（detail `exit=0`/`class=`）；`dispatch.py:596-600` | 扫窗口内同 key 事件，`exit=0` 或新 `dispatch` 计为进展 |
| 全局熔断刹车 | **P6** 文件驱动硬停杆 + **P9** kill switch | `open_goal_change_gate:174-181`、`tick` halt 分支 `:2064-2113`；`config.py:49-50`/`conductor.py:2060` | 见 F3d：create-once 标记文件/事件，重启从文件重推 |
| 预算不被无声抬高 | **P1/P2**（`_resume_credits` / `round_budget`） | `_resume_credits:2273-2293`；`config.py:53/71` | **规则**：auto 决策不计入 `_resume_credits`（谓词加在权威来源上，不加在 `answered_by` 上）⇒ 自动批准不取消预算上限（RQ-11 反作用 (a)） |

**明确不做（违反 GC）**：任何把"今晚已自动几次"放在 `ConductorState`/模块全局/内存队列的方案（`conductor.py` 的 `st = ConductorState(...)` 是进程内状态，重启即丢 ⇒ 夜跑无界，RQ-11 F5 反面示例）；任何新增可写侧车但不声明锁的方案（GC-3）。

#### F3b 熔断判据（信号）与阈值来源

| 信号 | 判据（机器可判） | 阈值与来源 |
|---|---|---|
| (S1) 门量 burst | 滚动 60s 窗口内 `gate-auto-decision`(executed) ≥ 17，或滚动 1h ≥ 100 | **17·min⁻¹ = FM 洪泛峰值实测**、**585.8·h⁻¹ = 洪泛速率实测**（RQ-10/RQ-11）⇒ 100·h⁻¹ 是"远低于已知失败速率"的次级兜底（防上限实现 bug，不是正常量级参照） |
| (S2) 单夜量超配额 | 单夜（UTC+8 22:00–08:00，RQ-11 F3 口径）auto 决策数: 单 key ≥ `key_cap`，或全项目 ≥ `night_cap` | 参照：**正常上界 28 门/149h、单夜 ≤3**（"100% 一致"回放）；**失败参照 单夜 5364 / 2 key**（洪泛实测）。提案：`night_cap = 6`（观测最大值 2 倍），`key_cap = 2`；两者都是**策略余量**（[推断]，需影子期校准），但**任何情况下必须 ≪ 5364** |
| (S3) 重复应用 | 同 `(key, reason_code)` 在窗口内 auto 决策 ≥ 2；或同 `(key, loop)` 的 auto 次数 ≥ `advance_stall_ticks` | 依据：RQ-10 F1f **7/22 是重复 stall**、5 个 key 停过 ≥2 次；FM 洪泛 = 同 key 一夜重放 5588 次。上界复用 P3（有界 1..50） |
| (S4) 证据不一致 | (V2) 重算规则谓词与 `data.decision` 不符，或 `data.evidence[].mtime_ns > decided_at` | 依据：RQ-14 **24/34 门证据 mtime 晚于应答**（E2 `gate-0010` 晚 13min）⇒ 这条检查有非空样本面；不一致 ⇒ **fail-closed 熔断** |
| (S5) 无进展 | 同 key 两次 auto 之间窗口内 `advance exit=0` 数 = 0 且无新 `dispatch` | 依据：RQ-10 I3（E2 同 key 3 连 stall、FM 一夜零推进）；原始材料齐备（事件 detail 结构化） |
| (S6) reject 率 | **不适用**：设计 B 禁止 auto-reject（白名单 W3），无 auto reject 率可看。**替代信号**：影子期"建议 reject"占比突增（如 > 历史 `reject=0/34` 的合理上界）⇒ 提示规则集错位，应停 live | 依据：RQ-10 `reject_path_samples=0` |
| (S7) 开关/配置被改 | `config_sha256` 在两次 tick 间变化且变化来自非授权写者（与 F1d 守卫拒绝记录 join） | 本设计新增；缺位时首个失败模式 = "有人关了自动决策/改了阈值，审计看不出来" |

**阈值取法原则（硬要求）**：阈值**不得**由"历史答案一致性"推出（RQ-10 已证该口径有陷阱：34/34 一致是"人在场"的产物）；应参照**可量化的失败速率**（洪泛）定上界，再用影子期实测校准。凡本卡给的数字都标注了来源/推导，未标注处一律写"需影子期数据"。

#### F3c 熔断后动作 = B（已确认）

触发任一硬信号（S1/S2/S3/S4）后：
1. **停 auto**：本 tick 起不再执行 `mode=live` 决策（等价于把 `auto_gate_mode` 的**运行时有效值**降为 `off`，但不改写配置——由刹车标记覆盖）；
2. **升级给人**：把当前待决门**保持/回到人审态**（不自动答），并在 timeline/账本写一条 `decision="escalate"`（`data.breaker_reason=S..`）；
3. **报告**：`mw doctor` autopilot 段 + `/autopilot` 视图给出"昨夜 auto 决策清单 + 熔断原因 + 未决门"（F4c）；
4. **不静默继续**（U-9 明确否决"静默继续"）。

#### F3d 熔断状态是否持久化（崩溃后是否仍熔断）——**必须持久化**

- **为什么不能只扫 timeline**：timeline 只留 **2 代**（`timeline.py:93-94`），窗口扫描会被轮转吃掉——这正是 JC `gate-0008` 重放事故的根因族（RQ-14：`gate-answered` 事件被剪 ⇒ 消费集合丢失 ⇒ 已 closed 的 stage 回退 `running`）。若熔断只靠"扫窗口计数"，崩溃/轮转后计数归零 ⇒ **洪泛可复现**。
- **设计**：触发时 **create-once** 写持久刹车（复用 P6 范式）：
  - 载体（二选一，推荐前者，理由见 F2b A3）：`<root>/.agenticdoc/_autopilot/auto-brake.md`（含 `breaker_reason/triggered_at/counts/sha256`）或一个 pending `auto-halt` 门；
  - 语义：存在即 `live` 被覆盖为 `off`；**每 tick 从文件重推**（GC-1），因此重启/崩溃后**仍然熔断**；
  - 解除：只能显式人工操作（删标记或答门）+ conductor 写一条 `gate-auto-revoke`/`config` 事件留痕；
  - 判据：注入 K 条 auto 决策触发刹车 → 杀进程 → 重启 → 断言"下 N tick 内 0 条 `executed=true`"。
- **同时**：`auto-decisions.jsonl` 与 timeline 双写（timeline 供实时 join，账本供长期溯源），避免轮转后审计断链。

#### F3e 无人值守默认动作的显式声明（AC-019 对齐）

每类门必须有一条**声明式默认动作**，缺省不得是"隐式永久滞留"：`auto | halt-and-report | escalate | reject`。落点建议：一张只读的声明表（conductor 代码常量 + `mw doctor` 渲染），不是散在散文里；判据 = "对每个 `GATE_KINDS`（`gates.py:54-61`）成员，声明表必须有条目，否则 doctor 报 issue"（机器可判、逐字锚定；P-014 家族）。与 RQ-10 三态一致：`stage-close`(approve) → `auto`（条件满足后）；`budget-exhausted`/`stalled` → `escalate`（影子期）；`stage-confirm`/`goal-change`/`xkey-authorize`/所有 reject → `halt-and-report`。

---

### F4 — 回滚与批量回看（AC-018）

#### F4a 现状（已复核）

| 能力 | 现状 | 锚点 |
|---|---|---|
| 列出"已自动过"的门 | **不存在** | `/autopilot gates` 只列 pending `console.ts:182-200`；面板 `scanPendingGate` 只收 pending `monitor.ts:148-180`；doctor autopilot 段零 gate 内容 `mw_common.py:2022-2065`；`gate-answered.detail` 不含 `answered_by`（`conductor.py:2349`/`:2388`） |
| 按来源过滤 | **不存在** | 同上；TS `listGates` 的 `GateRecord` 不含 `answered_*`（`status-model.ts:587-598`） |
| `_consumed_gate_ids` 可逆？ | **不可逆** | 由 append-only `gate-answered` 反推（`:297-313`）；门改回 pending 不会重新生效（`:2314-2331` 只看 id 是否在集合内） |
| reject 路径消费记录 | **缺失**（不对称） | `_apply_stalled_rejections:2363-2394` 无 `consumed` 检查；`_apply_stalled_approvals:2314-2331` 有 |
| 真正撤销 | 只能手改 `_roadmap.md` 的 `key-status:`，**不留事件** | RQ-11 F4 解除路径 3 |

#### F4b 按来源过滤

判据来源 = `gate-auto-decision` 事件（F1a）与 `auto-decisions.jsonl`（F1 新账本）。过滤表达式（两侧一致）：`ev == "gate-auto-decision" ∧ data.mode=="live" ∧ data.executed==true ∧ (无同 decision_id 的 gate-auto-revoke)`。**不得**用门文件 `answered_by` 过滤（应答者可写，AC-030）。

#### F4c 批量回看（"昨夜自动答了哪些门"）

- **夜窗定义**：本地 UTC+8，`22:00–08:00` 归到当日 22:00 的夜（RQ-11 F3 已用该口径做回放；标注为**约定**而非实测）。
- **视图落点（三处，避免只做一处）**：
  1. `mw doctor` 的 autopilot 段（`mw_common.py:2022-2065`，目前零 gate 内容）——报告路径同时覆盖 `mw doctor` 与 `mw bootstrap`（D-011 先例）；
  2. `/autopilot` 新子命令（`console.ts` 现有 `cmdGates/cmdGate/cmdTimeline` 范式 `:182-265`）——列 `decision_id / gate_id / kind / key / rule_id / evidence sha / decision / 解锁了什么（key resume? stage close?）`；
  3. 面板一行摘要（`monitor.ts` gates 行 `:644-655` 附近）——`auto: N last night (M escalated)`，**不新增误报**（无 auto 时显示 0 而非报错）。
- **"解锁了什么"的判据**：`stage-close` approve → 下一 stage 的 `stage-confirm` 门被创建（`_ensure_next_stage_gate:409-431`）；`stalled` approve → 同 key `resume` 事件（`:2349`）；`budget-exhausted` approve → `_budget_bonus` 生效（`:2216-2227`）。这些都是现成事件，批量回看只做 join。
- **告警**：存在未复核的 auto 决策（例如昨夜 exec 数 > 0 且无人工 revoke）⇒ doctor issue（对齐 D-011 的 issue/suggestion 分级）。

#### F4d 撤销单个自动决策（含 stage 状态处理）

**关键设计：消费记录按 `decision_id` 记账 + 负记录（append-only 兼容）**

- 现状空档：`_consumed_gate_ids` 是 `gate_id` 集合，从 `gate-answered` 反推；一旦写入无法移除。因此"改回 pending"或"再次批准"都不会重新生效（`:2314-2331`）——这也是 AC-028 的 `gate-\d{4}` 溢出之外的第二个不可逆来源。
- 替代设计：
  1. 消费集合语义升级为**按决策**：`consumed_decisions = {decision_id from gate-answered join gate-auto-decision}`，撤销只对 `decision_id` 生效；
  2. 撤销 = conductor 消费一个人工动作后写 `gate-auto-revoke`（`data.decision_id` 指向被撤销的决策、`data.revoked_by/revoked_at`）；**有效消费集合 = `answered_decisions − revoked_decisions`**（集合差，仍是 append-only）；
  3. 撤销后门文件回到 `pending`（人可在 window 内重答）；重新作答产生**新的** `gate-answered` 事件，因按 `decision_id` 记账不会被旧的 revoke 抵消——这正是现状 gate-id 语义做不到的。
  4. `_resume_credits` 自动跟随：它每 tick 从门目录重推（`:2273-2293`），而"被撤销的 approve 不再是有效 approve" ⇒ 谓词必须改成基于有效决策集合（不是简单 `status=="approved"` 的数数），否则撤销后 credit 仍被计入。
- **撤销原语的可执行判据**：给定 `decision_id`，撤销后下一 tick：① 同 gate 不再被消费（无新 `gate-answered`）；② 该 key 的 `key-status` 回到决策前值（若期间无其它事件）；③ `_resume_credits` 不含该决策。
- **stage 状态如何处理（与 D3/D4 单调性交叉，标依赖）**：
  - `stalled` approve（改的是 `key-status`，`_apply_stalled_approvals:2295-2360`）：撤销 = `running → stalled` 回退；这在 D3 的"stage 单调性"里属 **key-status 层**回退，D3 应给"哪些转换需要显式事件"的矩阵。本卡**依赖 D3**（`design-consumption-record-20260926.md` 第 5 项）的结论；在 D3 落地前，本设计只声明**必须走显式事件、不得静默回退**。
  - `stage-close` approve（改的是 stage `closed`，`_set_stage_status:380-407`）：撤销更危险——`_ensure_next_stage_gate` 可能已开下一 stage 的 confirm 门。规则：**只在 grace window 内（决策未生效前）允许**撤销；生效后只能走 **D2 的"待复核"状态**（`design-deferred-review-state-20260926.md`），即 `closed → pending-review` 的**显式、留痕、单调**路径，**禁止** `closed → running` 隐式回退（后者正是 JC `gate-0008` 事故形态，RQ-14/D4）。
  - `closed-legacy`：本设计下**不存在 auto-reject**，故不涉及；一旦未来放开，必须在 D3 的单调性矩阵里单列（红线，AC-018/风险 24）。
- **不可逆的残余**：自动 approve 已经烧掉的 token / 已产生的源文件写不可回滚（RQ-13 风险 24）。撤销只回滚**状态机**，不回滚已发生的计算——必须在撤销视图里显式提示。

---

### F5 — 影子模式（AC-024）

#### F5a 模式定义与记录载体

- **定义**：`auto_gate_mode="shadow"` 时，conductor 每 tick 对每个 `pending` 门跑同一套规则求值，写 `gate-auto-decision` 且 `mode="shadow" / executed=false / decision∈{approve,reject,escalate}`，**不写门文件、不改 key-status、不改 stage、不给 credit**。门的 `pending` 态保持原样，人看到的东西与今天一致。
- **记录载体**：
  - 权威 = `<root>/.agenticdoc/_autopilot/auto-decisions.jsonl`（append-only、seq、conductor 单写）；影子样本要跨夜累积 ⇒ **不能只依赖 2 代 timeline**；
  - timeline 投影 = 同一条 `gate-auto-decision`（供实时视图 join）；
  - **收口补记**：当该门后来被人答时，conductor 追加一条同 `decision_id`、`data.phase="resolve"`、`data.counterfactual_human=...` 的记录 ⇒ 影子样本自带"若自动会怎么答"与"人实际怎么答"的配对。
- **判据**：影子模式下门文件 sha256 不变、`_roadmap.md` 不变、`_resume_credits` 不变（F6 VC 之一）。

#### F5b 最小样本判据

| 项 | 判据 | 依据 / 为什么 |
|---|---|---|
| 时长 | **≥ 5 个完整夜窗** | RQ-8 实测等待 **88.0%/85.6% 落在 22:00–08:00** ⇒ 夜窗是收益的主战场；且最大单夜 3 门，5 夜才有 ~15 的样本量 |
| 总量 | **≥ 20 条影子决策**（跨门类） | 回放上界 28 门/149h（RQ-11）⇒ 20 是"至少覆盖一次完整月历波动"的工程下限；不宣称统计显著性 |
| 分布 | 每个**拟上线**的 rule 至少出现 **1 条"命题为假"的反例**（即影子 `decision=escalate/reject` 或规则谓词求值为假） | AC-025 硬判据：命题必须**可以为假**；若某 rule 在影子期从未为假 ⇒ 恒真、零信息量（`stage-close` 的"全部 key 已终态"就是恒真反例，RQ-12）⇒ **不许上线** |
| 门类覆盖 | 0 样本门类（`budget-exhausted`/`xkey-authorize`/`goal-halt`(=`goal-change`)/`type-rejected`/`target-config-rejected`）与 **reject 路径**必须各积累 ≥1 条影子样本才允许讨论其规则；但这 5 类中 `goal-change`/`xkey-authorize`/所有 reject 已是**黑名单（永不 auto）**，影子只为证据不为上线 | RQ-10 F1g / `reject_path_samples=0`；`type-rejected`/`target-config-rejected` 是 dispatch fail-closed 机器路径、无人参与（RQ-10 F3 附表），影子只用于验证"规则不会误报" |
| 反例充分性 | 每条拟上线的 approve 规则还需 **≥1 条"证据快照在应答后被改写"的样本被正确检出** | RQ-14：24/34 门证据 mtime 晚于应答 ⇒ 规则必须证明自己能发现"证据漂移"，否则是假自举 |

#### F5c 影子期收益量化（"若不自动要等多久"）

- **可复算定义**：对每条影子决策 `d`（门 `g`）：`saved_wait(d) = answered_mtime(g) − max(g.created_at, first_tick(rule_true))`；其中 `g.created_at` 在门文件 frontmatter（`gates.py:68-81`），`answered_mtime` 用**文件 mtime**口径（不用 `answered_at`：实测 3 处不自洽，RQ-10 F1e）。`first_tick(rule_true)` 来自影子事件 `decided_at`。
- **实测锚点（引用，不重算）**：RQ-8 的 stalled 等待过夜占比 **FM 88.0% / E2 85.6%**（即自动省下的等待绝大多数发生在无人值守时段，正是本 key 的目标场景）；stalled 等待 p50 3.62h/4.04h、max 17.40h；RQ-13 的门→stage 收口视界 **n=11 / p50 24.48h / max 145.99h**（说明单门延迟会传导到 stage 收口），以及 JC `stage-close` pending **203.93h**、E2 一条 **136.4h**。
- **同时量化风险**：影子期统计 (i) 影子建议 vs 人工答案不一致率（RQ-10 的 16/22 "approve 前有带外修复"说明不一致会集中出现在"缺修复"场景）；(ii) 证据漂移检出率；(iii) 假设规则上线时会被 S2/S3 熔断的频次（用同一条 `budget` 计算但不执行）。⇒ 影子期不只是攒样本，也是**阈值校准**的唯一来源。

---

### F6 — VC 候选（≥4，全部机器可判）

| # | VC（触发 → 断言） | 判定层级 / 方式 |
|---|---|---|
| VC-D5-1 | 审计字段完整性：对每条 `gate-auto-decision` 且 `data.executed==true`，`data` 必含 `decision_id,gate_id,gate_kind,mode,decision,rule_id,rule_version,decided_by=="conductor",decided_at,switch.config_sha256,evidence[]`，且 `evidence` 每项含 `{path,sha256,mtime_ns}`；缺任一即 fail | 两侧解析器 + 一条夹具用例（Python `query_events` / TS `queryTimeline` 同断言）；P-021 两侧都跑 |
| VC-D5-2 | 来源不可伪造：所有自动决策的判据字段**不得**取自门文件 `answered_by`/`answered_at`；构造一个 `answered_by="conductor-auto"` 但**无** `gate-auto-decision` 的门，判定必须为"人工/来源未知"，不得被判为自动 | 审计器单测：把 `answered_by` 设成 auto 值域但删除事件 ⇒ 断言"非自动" |
| VC-D5-3 | 开关生效：`auto_gate_mode="off"` 时，任何窗口内 `executed==true` 的 `gate-auto-decision` 数 == 0，且 `beat` 持续、人工 `gate-answered` 仍被消费、`_resume_credits` 不变 | conductor 测试（faux provider harness）：置 off → 跑 N tick |
| VC-D5-4 | 熔断触发且持久：注入使 S2/S3 达到阈值的决策序列 ⇒ (a) 停止 emit `executed=true`；(b) 出现且仅出现一条 `decision=="escalate"`；(c) 刹车载体存在；杀进程并重启后 (a) 仍成立 | conductor 测试 + 重启复用（断言从文件重推，不依赖内存） |
| VC-D5-5 | 撤销可追溯：给定 `decision_id`，撤销后存在 `gate-auto-revoke`（同 `decision_id`）；下一 tick 不再消费该门；`key-status` 回到决策前值；窗口内**无** `closed→running` 隐式回退（stage 变化必须有对应事件） | conductor 测试；stage 层断言需等 D3 的单调性矩阵落地（**依赖**） |
| VC-D5-6 | 影子纯净：`auto_gate_mode="shadow"` 下跑 N tick，门文件 sha256、`_roadmap.md`、`_resume_credits` 均不变，且 `auto-decisions.jsonl` 条数 == 影子决策数（`executed==false`） | conductor 测试（前后快照比对） |
| VC-D5-7 | 跨语言词表一致：`sorted(timeline.EVENT_TYPES) == sorted(status-model.EVENT_TYPES)`，且含 `gate-auto-decision` 与 `target-config-rejected` | TS vitest 起 Python dump 比对（fail-closed，无 `skipIf`），共享冻结词表夹具（先例 `autopilot-config-corpus.json`） |
| VC-D5-8 | parity 语料重冻：新键在两侧注册表（bool/list/str/int）中同分区、同默认值；语料 `sha256`/条数与冻结常量一致；P6 的键数断言为 14 且 `covered == KNOWN_FIELDS` | Python+TS parity 测试（这两条今天就会因新键变红，正是需要的护栏） |

## 结论 → 决策映射

- **支撑 AC-018（审计 + kill switch + 可回滚）**
  - 留痕：`gate-auto-decision`（含 `data` 契约，F1a）+ `auto-decisions.jsonl` 账本；`answered_by` 降级为展示字段（F1d）。
  - 开关：推荐 `auto_gate_mode` 单键（F2c，`off|shadow|live`，默认 `off`，不入 `EFFECTIVE_KEYS`），理由与代价见 F2b/F2d；"只停自动决策"的判据在 F2d 末。
  - 回滚：`gate-auto-revoke` + 按 `decision_id` 记账的集合差（F4d），批看三处视图（F4c）；stage 状态处理**依赖 D3/D4**。
  - VC：VC-D5-2/3/5/6。
- **支撑 AC-019（默认动作显式声明 + 熔断持久）**
  - 每类门的声明表 + "缺声明即 doctor issue"（F3e）；熔断动作 = B（F3c）；熔断持久化设计（F3d，理由 = timeline 2 代轮转）。
  - VC：VC-D5-4。
- **支撑 AC-024（影子模式）**
  - `mode=shadow` 定义与载体（F5a）、最小样本判据（F5b，含"每个规则 ≥1 条命题为假反例"）、收益量化口径与引用（F5c：RQ-8 过夜占比 88.0%/85.6%、RQ-13 门→收口 p50 24.48h/max 145.99h、JC 203.93h）。
  - VC：VC-D5-6。
- **支撑 AC-030（不可伪造审计字段）**
  - 四层防伪（F1d）：单写者 + 路径守卫（**当前缺口，硬前置**）+ conductor 派生字段 + 三条校验 (V1/V2/V3)；残余风险显式声明。
  - VC：VC-D5-1/2。
- **支撑 AC-017（副作用防护）**：逐条映射——(a) `_resume_credits` 无上界 → auto 不计 credit + `night_cap`/`key_cap`（F3a 末/F3b S2）；(b) `closed-legacy` 静默解锁 → 禁止 auto-reject（RQ-10 W3），故本设计不产生该副作用；(c) `stalled↔running` 振荡 → S3 重复上界（复用 P3）+ 冷却（`created_at`）+ 刹车（F3d）；(d) 注意力掩盖 → F1 留痕 + F4c 批看 + doctor issue。
- **与相邻卡的接口（依赖，不含答案）**
  - **D3**（`design-consumption-record-20260926.md`）：本设计的"按 `decision_id` 记账 + 集合差撤销"必须与 D3 的消费记录载体/单调性矩阵对齐；`_consumed_gate_ids` 正则溢出（`gate-\d{4}`，`conductor.py:310`）与 reject 路径无守卫是"撤销"能正确工作的硬前置。
  - **D4**（`design-evidence-provenance-20260926.md`）：`evidence[{path,sha256,mtime_ns}]` 三元组必须与其快照绑定字段同名同义；证据源优先级表决定 V2 判定优先级。
  - **D2**（`design-deferred-review-state-20260926.md`）：撤销 `stage-close` 的生效后路径 = D2 的"待复核"状态，不得自造。
  - **D1**：`reason_code`/`machine_evidence`/`goal_diff` 等门字段由 D1 定；本设计只消费。
- **顺序约束（本卡立场）**：① 修 `gate-\d{4}` 溢出 + reject 消费守卫（D3）；② 扩工具层守卫覆盖 `_autopilot/{timeline.jsonl,auto-decisions.jsonl,config.json}`（F1d）；③ 落地审计事件 + 账本 + `auto_gate_mode=off` 骨架（行为与今天一致）；④ 影子模式；⑤ 熔断/配额；⑥ 才谈 `live`。**① ② 必须先于任何 `live`**（否则重演洪泛或出现可伪造的审计面）。

## 数据缺口

1. **无 live 自动决策样本**：影子模式尚未运行 ⇒ `night_cap`/`key_cap` 的"策略余量"（本卡提案 6/2）无实测支撑，只能按"正常上界 3/夜"与"失败速率 5364/夜"之间的量级选取，需影子期校准。
2. **`budget-exhausted` / `xkey-authorize` / `goal-halt` / `type-rejected` / `target-config-rejected` 生产 0 样本**，reject 路径 0 样本（RQ-10）⇒ 这些门类的规则永远无法用历史验证；`type-rejected`/`target-config-rejected` 是无人参与的机器路径，是否有"门"语义本身需 D1 定。
3. **成本不可估**：无 token 账本/代理日志 ⇒ 自动决策省的"等待"可算，省的/多花的"token"不可算（RQ-11 数据缺口 5）。
4. **夜窗定义是约定**（UTC+8 22:00–08:00，RQ-11 数据缺口 3）⇒ 阈值口径随 PM 定义变化。
5. **工具层守卫覆盖面**：本次实测确认 `_autopilot/timeline.jsonl` 与 `_autopilot/config.json` **不在任何守卫内**（`xkey-gate-guard.ts:60` + `protected-config.ts:42`），扩守卫属安全面变更，需单独评审（是否影响 xkey evidence/ledger/tickets 的既有放行）。
6. **D3/D4/D2/D1 的设计文件在本卡写入时尚未产出**（`workers/msc-d3-…`、`msc-d4-…` 等目录无 output/report）⇒ 消费记录、单调性、证据字段名三处接口为**待对齐依赖**，落地前必须回看。
7. **`auto-decisions.jsonl` 的轮转/保留策略未定**（影子期样本必须能跨月存活，但无界增长违反 GC-3 精神）⇒ 需要 PM 定保留窗口（本卡只给下限：≥ 影子期 + 复盘窗口）。

[VERIFY] D5: audit_event=gate-auto-decision(new; timeline line gains optional `data`) fields=[decision_id,gate_id,gate_kind,gate_stage,gate_key,mode(off/shadow/live),executed,decision(approve|reject|escalate),rule_id,rule_version,reason_code,decided_by=conductor,decided_at,evidence[{path,sha256,mtime_ns}],switch{enabled,paused,auto_gate_mode,config_sha256,effective_origins},budget{night_used,night_cap,key_used,key_cap,cooldown_s_left,breaker},gate_file_sha256_before/after,counterfactual_human] authoritative_source=conductor-derived(timeline seq + evidence snapshot sha256 + code-constant rule + load_effective switch); answered_by/answered_at=display-only(non-authoritative; answerer-writable gate-writer.ts:139-152, gates.py:1-20) ts_mirror_faces=[timeline.EVENT_TYPES:67-85, TimelineEvent:807-814, parser whitelist:882-889, GateRecord:587-598] py_mirror_faces=[EVENT_TYPES:67-85, Timeline.append:274-320] crosslang_criteria=[vocab equality, data passthrough, frozen field set, consumed-vs-event join] kill_switch=none-exists; options=[A1 new str key `auto_gate_mode` (off|shadow|live, default off, NOT in EFFECTIVE_KEYS(effective_config.py:66-70)) RECOMMENDED, A1' two bools, A2 reuse paused REJECTED, A3 file-driven stop gate, A4 env REJECTED] parity_impact=[corpus 53->~55 cases, FROZEN_CORPUS_SHA256/COUNT re-freeze test_autopilot_config_parity.py:60-61, P6 13->14 test_autopilot_config_parity.py:423-431 + autopilot-config-parity.test.ts:356/359, P5 registry autopilot-config-sync.test.ts:157-181] quota_primitives=[P5 _consumed_gate_ids:297-313, P4 _XKEY_PROPOSAL_MAX_ATTEMPTS:2872/_xkey_proposal_exhaust:2959-2979, P3 advance_stall_ticks:794-799/config.py:57/75, gate.created_at gates.py:68-81, P6 open_goal_change_gate:174-181, P9 config.py:49-50/conductor.py:2060] breaker_signals=[S1 burst 17/min or 100/h, S2 night_cap=6 key_cap=2 (normal upper bound 3/night vs flood 5364/night), S3 repeat >=2 same (key,reason_code), S4 evidence inconsistency (24/34 rewritten), S5 no progress, S6 shadow reject surge, S7 switch tamper] breaker_action=B(stop auto + escalate gate + morning report; NOT silent) breaker_persisted=YES(create-once brake file; timeline keeps only 2 generations timeline.py:93-94) rollback=[filter by gate-auto-decision/gate-auto-revoke, batch view doctor:2022-2065 + console.ts:182-200 + monitor.ts:644-655, undo by decision_id with set-difference answered-minus-revoked (append-only compatible), stage handling DEPENDS on D3 monotonicity/D2 pending-review/D4 evidence fields; no implicit closed->running] shadow=[mode=shadow; ledger .agenticdoc/_autopilot/auto-decisions.jsonl; min >=5 nights AND >=20 decisions AND >=1 falsifiable counterexample per rule AND >=1 evidence-drift case; benefit=RQ-8 overnight share 88.0%/85.6%, RQ-13 gate->stageclose p50 24.48h/max 145.99h, JC pending 203.93h] guard_gap=timeline.jsonl+config.json NOT guarded today(xkey-gate-guard.ts:60 gates-only; protected-config.ts:42 pi-agent-only) => hard prerequisite VCs=[VC-D5-1..8]
