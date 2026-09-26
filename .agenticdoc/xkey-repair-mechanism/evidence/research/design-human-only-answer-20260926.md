# Design RQ-D4：仅人可答的判别 + gate kind 扩展（D-008 / D-009）

> key: xkey-repair-mechanism ｜ 类型：只读调研（design RQ-D4）｜ 唯一写入产物：本文件
> 生成时间：2026-09-26 ｜ 口径：当前工作区 HEAD（dirty 树）实测行号
> 上游证据：`spec-code-facts-20260926.md`（RQ-1）、`spec-reusable-parts-20260926.md`（RQ-3）
> 对应 spec：§2.3（解冻权只给人）/ AC-004 / §2.4 依赖表 / §4 R-3；KDR Q3 / Q8

## 决策问题

- **D-008「仅人可答」的可实现判别与强制点**：AC-004（spec §2.3）要求 `xkey-authorize` gate 仅接受人工作答，PM/agent 代答必须被**可观测地拒绝**（状态不前进）。需要确定：作答通道共有几条、哪条能被 agent 走通、能拿到什么身份信号、用哪种判别/强制手段达成"可观观测拒绝"。
- **D-009 gate kind 扩展的兼容性**：新增 `xkey-authorize` 必须两侧闭集镜像（`gates.py:52` ↔ `status-model.ts:467` ＋ TS 解析 `:595`）；需列出全部改动点，并判定旧版本面板/窗口读到未知 kind 的实际行为（抛 `GateFormatError`？跳过？崩溃？），从而决定"机制上线是否要求所有窗口同步更新"。
- **Q1** 作答通道全清单（每条 file:line + 可行性）：TS `answerGate`（`gate-writer.ts:139`）的上游触发是谁？slash command 是否只能由人在 TUI 输入？是否存在任何 tool/agent 可调用的作答入口？是否存在 bash/文件直写伪造有效答案？`gate-writer.ts` 是否校验锁持有者/回答者身份？
- **Q2** 现有身份信号盘点：`answered_by` 取值来源；`PI_WORKER_TASK` 是否存在且能判定 worker 模式；窗口 claim 的 host:pid；worker 模式下 `/autopilot` 是否禁用；还有哪些可用信号（如 `ctx.hasUI`）。
- **Q3** 判别方案对比（≥3，Pros/Cons + 推荐）：(a) 入口收窄；(b) 挑战-响应 nonce；(c) 双通道二次确认；(d) 审计而非阻止。判据绑定 spec §2.3 / AC-004 与现实约束（人在 pi TUI 操作，且 PM 窗口本身是 agent 驱动）。
- **Q4** kind 扩展完整改动清单（file:line + 改什么）＋向后兼容实测。
- **Q5** 超时/预算：gate 无 TTL；`mark_stalled`（`conductor.py:2294`）与 streak 判据；xkey 工单"超时未答"应复用哪条路径；与现有 stalled 语义是否冲突。

## 调研方法与出处

- **全文精读**：`autopilot/gate-writer.ts`、`autopilot/console.ts`（全 427 行）、`autopilot/status-model.ts`（gates 段 `:466-676` 及 `deriveStatusModel`）、`autopilot/monitor.ts`（`scanPendingGate`/`readMonitorState` 段）、`pm/ui-bridge.ts`（claim 身份段 `:171-208`）、`shared/protected-config.ts`（全）、`shared/file-lock.ts`（全）、`worker/worker-mode.ts`（工具表 `:50-108`、`tool_call` 拦截 `:755-800`）、`extensions/agent-team-loop/index.ts`（全）、`pm/pm-orchestrator.ts`（激活/注册段 `:660-720`、gate 自动注册点 `:704`）；Python 侧 `autopilot/gates.py`（全 508 行）、`autopilot/conductor.py`（`:140-330`、`:735-935`、`:1955-2090`、`:2160-2370`）、`autopilot/config.py`（默认值/校验段）。
- **穷举扫描（用于"未发现"否定结论）**：
  - `answerGate` → agent-team-loop 内命中 3 处（`console.ts:40/217`、`gate-writer.ts:139`），**唯一调用者 = `console.ts:217`**。
  - `pi.registerTool` → agent-team-loop 内 14 处：`pm/ui-bridge.ts`（`mw_status` `:956`、`dispatch_worker` `:1113`、`ack_worker_result` `:1284`、`list_tasks` `:1316`、`switch_key` `:1386`、`advance_phase` `:1462`）、`rag/tools.ts`（7）、`worker/worker-file-tool.ts:83`。**无一作答 gate**。
  - `pi.registerCommand` → agent-team-loop 内 `autopilot` 仅注册于 `console.ts:85`，由 `pm-orchestrator.ts:704` 调用；`worker/worker-mode.ts` 内 **0**（`grep registerCommand` 无命中）。
  - `session.prompt(` 调用者 → `modes/print-mode.ts:132/136`、`modes/interactive/interactive-mode.ts:1055/1065/1077/2997/3009/3925/3937/4242/4258/4269/4274/4282`、`modes/rpc/rpc-mode.ts:399`、`core/agent-session.ts:1505`（`sendUserMessage` 内部）；**没有任何 tool 调用 `prompt()`**。
  - 内置工具面 → `core/tools/index.ts:1`：`ToolName = "read" | "bash" | "edit" | "write" | "grep" | "find" | "ls"`，无命令执行工具。
  - `hasUI` → 赋值点 `main.ts:714`、`package-manager-cli.ts:597`、`interactive-mode.ts:1973/2317`；getter `core/extensions/runner.ts:442-443`。
  - gate kind 闭集 → 全仓 `stage-confirm` 生产代码命中：`gates.py:52-57`、`status-model.ts:467`（`dist/.../status-model.d.ts:121` 为构建产物）。
- **只读纪律**：未改动 `pm-state.md` / `_index.parallel` / `spec.md` 或任何其它文件；未运行会改仓库状态的命令；仅 `read` / `Select-String` / `Get-ChildItem` / `Get-Content`。本文件由 worker 报告文件原样复制到目标路径（byte 保真），未用 PowerShell 文本管道写正文（P-001）。

## 发现

### Q1 作答通道全清单：3 条能产生"有效答案"的路径

先定义"有效答案"：conductor 的唯一真值是 gate 文件（`gates.py:13-15`）；只要文件 frontmatter 的 `status` 变成 `approved|rejected`，`_consume_answered_gates`（`conductor.py:274-322`）／`_apply_stalled_*`（`:2190/:2258`）／`_budget_*`（`:2111/:2123`）下一次 tick 即从文件重派生并推进。因此**任何能重写 `status` 的路径都是有效作答通道**。

**C1 — `/autopilot gate <id> approve|reject [--note <text>]`（TUI slash command）**
- 注册：`console.ts:84-85` `pi.registerCommand("autopilot", …)`；唯一注册调用点 `pm-orchestrator.ts:704`。
- 分发：`console.ts:102-103`（`case "gate"` → `cmdGate`）；实现 `cmdGate` `console.ts:197-231`；校验 id `/^gate-\d+$/`（`:203-206`）；调 `answerGate`（`:217-223`），`answeredBy: windowClaimId()`（`:222`）。
- 写侧：`answerGate` `gate-writer.ts:139-176`，在 `.mw/gates.lock` 下 read-modify-write，只重写 `status/answered_at/answered_by/note` 四行（`ANSWER_FIELDS` `gate-writer.ts:50`；`rewriteAnswerFields` `:113-135`）。
- **是否只能由人在 TUI 输入：在单进程内，是。** 命令执行只发生在 `AgentSession.prompt(text)` 且 `text` 以 `/` 开头时：`agent-session.ts:1122-1130`（`if (expandPromptTemplates && text.startsWith("/")) _tryExecuteExtensionCommand(text)`），实现 `:1278-1303`。而 `prompt()` 的调用者只有交互式编辑器（用户键盘）、print 模式 CLI 初始消息、RPC 客户端（见上）；LLM 侧工具面（`core/tools/index.ts:1`）没有命令执行工具，扩展 `sendUserMessage` 走 `prompt(text, { expandPromptTemplates: false })`（`agent-session.ts:1503-1509`）**显式跳过命令处理**。→ agent 在本会话内**无法**触发 C1。**可行性：人可用；agent 不可用（in-session）。**

**C2 — 通过 CLI 初始消息 / print 模式 / RPC 触发同一条命令**
- print 模式：`print-mode.ts:132` `session.prompt(initialMessage, …)` → 命令被处理 → 即 `pi -p "/autopilot gate-0007 approve"` 会真正作答。
- RPC：`rpc-mode.ts:399` `session.prompt(command.message, { source: "rpc", … })` → 同样执行命令。
- **agent 可行性：真实存在。** agent 有 `bash` 工具；`agent-team-loop` 是内置扩展（`extensions/index.ts:5-8`，经 `main.ts:530` 注入所有模式），`pmActivate` 无 `hasUI` 前置（`pm-orchestrator.ts:660`），故新进程 `pi -p "/autopilot gate …"` 会在本仓注册并执行该命令。**可行性：人（命令行）与 agent（bash 派生新进程）皆可用。**

**C3 — 直接改 gate 文件（write/edit tool、bash 重定向、外部编辑器）**
- 协议明文允许：`gates.py:13-15` "Manual file edits are equally legal answers: the file is the source of truth"；`gate-writer.ts:15-17` 同义（"Manual file edits remain equally legal answers … this writer is just the audited path"）。
- conductor 只读文件，不校验来源：`gates.enumerate` `gates.py:480-504` + `_consume_answered_gates` `conductor.py:274-322`；无任何"作答者身份/通道"校验。
- **现有工具层无拦截**：`implementation-gate.ts` 只覆盖 `<root>/packages/**`（`isCodePath` `implementation-gate.ts:146-161`、`PACKAGE_PREFIX` 判定 `:139-142`），`.agenticdoc/**` 不在内；`protected-config.ts` 只覆盖 `~/.pi/agent/{auth,models,settings,oauth}.json`（`:247-269`）；worker 的 `tool_call` 拦截器只拦 `read/ls/find/grep`（`worker-mode.ts:763-772`），`write/edit/bash` 直接 `return undefined`。**可行性：任何人（含 agent 的 write/edit/bash）皆可用，且当前完全无观测。**

**是否存在 tool/agent 可调用的作答入口？未发现。** `answerGate` 唯一调用者是 `console.ts:217`；agent-team-loop 的 14 个 `registerTool` 中无一作答 gate（见"调研方法"清单）。

**`gate-writer.ts` 是否校验锁持有者/回答者身份？没有。**
- 锁：`acquireLock(opts.lockFile, …)`（`gate-writer.ts:153`）+ `file-lock.ts` 的 O_CREAT|O_EXCL（`:12-42`）——只做**互斥**，锁文件内无 holder/身份，`release` 仅 unlink（`:26-33`）；且 C3 直写根本不经过锁。
- 回答者：`answered_by` 由调用方传入（`gate-writer.ts:147` `["answered_by", opts.answeredBy === "" ? "" : renderScalar(opts.answeredBy)]`），**不校验、不签名、不派生**；`answerGate` 对 gate 文件只要求 frontmatter 有 `status:` 行（`rewriteAnswerFields` `:113-135`），不解析 `kind`。

### Q2 现有"身份"信号盘点

| 信号 | 来源 / file:line | 能区分什么 | 局限 |
|---|---|---|---|
| `answered_by` | `console.ts:222` 传 `windowClaimId()`；`pm/ui-bridge.ts:171-172` `return \`${os.hostname()}:${process.pid}\`` | 作答窗口的 host:pid（审计用） | **自报、无校验、非"人类"证明**；人在 TUI 打字与 PM agent 在本窗口伪造文件得到**同一个 pid**，协议上不可区分（RQ-1/RQ-3 已证） |
| 窗口 claim（host:pid） | `windowClaimId` `ui-bridge.ts:171-172`；`parseClaim` `:181-189`；`isPidAlive` `:191-199`；`ClaimState` `:203` | 判活：claim 是否被活进程持有（可抢占 stale claim） | 只判进程存活，不是人类身份 |
| `PI_WORKER_TASK` | `index.ts:53` `if (process.env.PI_WORKER_TASK) workerModeActivate(pi) else pmActivate(pi)` | **判定当前窗口是 worker 模式**（扩展可读 env） | 只区分 worker/PM 窗口；PM 窗口仍是 agent 驱动 |
| worker 模式下 `/autopilot` 是否禁用 | **是（更准确：不注册）**。`registerAutopilotCommands` 仅在 `pm-orchestrator.ts:704`（PM 激活）调用；`worker/worker-mode.ts` 内 `registerCommand` **0 命中** | worker 窗口连命令都不存在 → worker agent 无 C1 通道 | worker agent 仍可走 C3（直接写盘） |
| `ctx.hasUI` | 类型 `core/extensions/types.ts:313`；getter `runner.ts:442-443`（`uiContext !== noOpUIContext`）；interactive 置 true `interactive-mode.ts:1973/2317`；tick 默认 `main.ts:714` | 区分"有真人界面的交互进程"与 print/RPC/worker 进程 | 不是"有人按键"的证明；PM 窗口 `hasUI=true` 但 PM agent 同进程 |
| prompt `source` | `agent-session.ts:243-244`；`sendUserMessage` 传 `"extension"`（`:1506`）、RPC 传 `"rpc"`（`rpc-mode.ts:404`） | 输入来源（可被 `input` 事件看到） | **命令处理发生在 `input` 事件之前**（`agent-session.ts:1125` vs `:1141`），且 `ExtensionCommandContext` **无 source 字段**（`types.ts` ExtensionCommandContext 定义）→ 命令 handler 拿不到 |

**结论**：没有任何现成信号能证明"人手按键"。可用的判别材料只有：**（i）是否走"命令"而非"工具/文件"；（ii）命令是否运行在 `ctx.hasUI===true` 的进程；（iii）是否 `PI_WORKER_TASK` 窗口**。三者都不是密码学证明——PM 窗口 agent 与人在同一进程、同一 pid、同一文件系统权限。

### Q3 判别方案对比

判据锚点：spec §2.3「`xkey-authorize` gate 仅接受人工作答；PM/agent 代答必须被可观测地拒绝（状态不前进）」；AC-004「由 PM/agent 提交的作答被拒绝，且工单状态保持 pending（拒绝记录可见）」；现实约束：人在 pi TUI 操作，**PM 窗口本身是 agent 驱动窗口**（RQ-D4 前提）。

**方案 (a) 入口收窄（命令仅 TUI、worker 模式禁答、`hasUI` 门）**
- 内容：作答仅存于 `/autopilot gate` 命令路径（已是事实）；worker 模式不注册该命令（已是事实，`worker-mode.ts` 0 个 `registerCommand`）；再对 `cmdGate` 加 `ctx.hasUI` 门（挡住 print/RPC/派生 `pi -p`）。
- Pros：零 schema 改动、零新增文件格式；可挡掉 worker 窗口（无命令）、print/RPC/`pi -p`（无 UI）、以及 in-session LLM（无命令工具）。成本最低。
- Cons：**挡不住 C3**——PM/worker agent 的 `write|edit|bash` 直写 gate 文件（Q1 证据：现有工具层无任何 gate 路径拦截，`implementation-gate` 只管 `packages/**`，`protected-config` 只管 `~/.pi/agent`，worker `tool_call` 只拦 read 系）。因此单靠 (a) 无法满足 AC-004 的"可观测拒绝"，因为 C3 是**静默成功**。
- 判定：**必要但不充分**。

**方案 (b) 挑战-响应：gate 内生成随机 nonce，答案须由人工输入该 nonce**
- 内容：gate 创建时写随机 nonce，作答须回填同一 nonce。
- Pros：实现简单（一面新字段/note 约定）。
- Cons（**无效**，如实指出）：nonce 若落 gate 文件或任何盘上文件，agent 的 `read`/`grep`/`bash` 可直接读取并回填（gate 文件对人/agent 同权限）；nonce 若不落盘而只存进程内存，则（i）违反框架"文件即真值、零私有状态"（D-005/`conductor.py:164-170` 注释），（ii）重启即失效，（iii）验证必须在生成它的同一进程内完成，跨窗口无法验证。**它不增加任何判别力**——攻击者与验证者共享文件系统与进程可见性。且 `answerGate` 会把 nonce 原样写进 frontmatter，仍属自报。
- 判定：**弱/无效，不推荐**（不因"凑方案"而入选）。

**方案 (c) 双通道：答案写入 + 人工在 TUI 二次确认（如 `--confirm <phrase>` 且 phrase 只口语传达）**
- 内容：`cmdGate` 在写盘前调 `ctx.ui.confirm`（原语存在：`types.ts:534` `ui: Pick<ExtensionUIContext, "select"|"confirm"|"input"|"notify">`），或要求 `--confirm <phrase>`。
- 可实现性评估：(i) `ctx.ui.confirm` 在同一命令 handler 内阻塞等待真人点击——在一个进程里是可实现的；但它与 C1 是**同一通道**，不是"第二通道"。(ii) `--confirm <phrase>` 若 phrase 由框架生成并落盘（gate/sidecar），agent 可读（同 (b) 无效）；若 phrase **只存内存**，则必须保证 command handler 与生成者在同一进程，破坏无状态/重启安全，且 C3 直写完全绕过。(iii) "phrase 只口语传达"要求人类从 TUI 之外获取 secret，超出框架能力。
- Pros：在不新增落盘状态时能对"按键者"加一道显式确认。
- Cons：**不解决 C3**（直写文件不需要经过 confirm）；内存态与文件驱动设计冲突；若 phrase 落盘则退化为 (b)。
- 判定：**可实现但无净收益**；对 C3 无效，不作为主机制。

**方案 (d) 审计而非阻止**
- 内容：不宣称强判别；把作答来源（窗口 claimId／模式／命令通道）如实写入 `answered_by`（免费格式单行标量，`gates.py:378-455` `optional()` 不校验取值），并在闭合证据里显式披露"作答者 = human-declared, 判别手段 = 命令通道 + 模式门，非密码学证明"。
- Pros：诚实、零误报、立即可做；满足 AC-004 的"拒绝记录可见"的形式要求（当与 (a) 联合时，被拒通道确有记录/提示）。
- Cons：**本身不拒绝任何东西**，不能单独满足 §2.3 的"必须被可观测地拒绝"。
- 判定：**必须作为补充**，不能单独成答。

**推荐：以 (a) 为基线 + 新增工具层写拦截（关键新建件）+ (d) 披露；显式不采用 (b)。**
- 基线 (a)：`cmdGate` 加 `ctx.hasUI` 门；worker 模式不注册命令（已具备）。
- **关键新建件**：仿 `shared/protected-config.ts` 的 `pi.on("tool_call")` 硬拦截（`protected-config.ts:247-269`），新增"agent 工具不得写 gate 目录"的 guard：`write/edit` 路径命中 `gatesDir(projectDir)` 即 block；`bash` 命中 gate 目录 + 写构造即 block（fail-closed）。这是**唯一能对 agent 作答产生"可观测拒绝"的落点**；注册位置与 `registerProtectedConfigGuard` 同级（`index.ts:41`，EVERY mode）。
- (d)：把 `answered_by` 升级为携带通道/模式（如 `human-tui@host:pid`），并在闭合证据披露判别强度。
- 明确不采用 (b)：nonce 对同权限 agent 无效。
- 诚实边界：`protected-config` 的 bash 扫描是**文本启发式而非沙箱**（其 docstring 自述 "This is a text-level heuristic, not a sandbox"），因此 D-008 的承诺应表述为"阻断 agent 工具面的作答路径并留痕"，而非"密码学上仅人可答"。

### Q4 kind 扩展完整改动清单 + 向后兼容

**必须改（闭集镜像两侧）：**

| # | file:line | 改什么 |
|---|---|---|
| 1 | `packages/multi-workers/autopilot/gates.py:52-58`（`GATE_KINDS`） | 加入 `"xkey-authorize"`。该常量同时被 create 校验 `_validate_new_gate:217-220` 与解析校验 `_to_gate:407-410` 引用，改一处两处生效 |
| 2 | `packages/multi-workers/autopilot/gates.py:26`（模块 docstring 的 kind 列表） | 同步文档（无行为影响） |
| 3 | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:467`（`GATE_KINDS`） | 加入 `"xkey-authorize"`。解析放行判定 `parseGateFile:595-596` 直接引用该常量，改一处即放行 |
| 4 | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:468`（`GATE_STATUSES`） | **无需改**（新 kind 复用 `pending/approved/rejected`） |
| 5 | `conductor.py:274-322`（`_consume_answered_gates`）或新增轮询函数 | 新增 `xkey-authorize` 的 approved/rejected 消费分支（当前只 transition `stage-confirm`/`stage-close`）。若 per-key，复用 `key=` 字段 + `_gate_open(kind, key=…)`（`conductor.py:2093-2109`）；创建统一走 `_create_gate`（`:2064-2091`，已记录 `gate-created` 事件 `:2087-2089`） |
| 6 | 测试 | Python `packages/multi-workers/test_autopilot_gates.py`（kind 创建/解析）；TS `packages/coding-agent/test/suite/autopilot-console.test.ts`（`/autopilot gates|status`）与 gate-writer/console 测试族 |
| 7 | `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts:121` | 构建产物，**重新构建生成**，勿手改 |

**无需改**：`gate-writer.ts`（作答不解析 kind，Q1 已证）；`monitor.ts`（kind 无关，见下）；`status-model.ts:468` 的 status 闭集。

**向后兼容实测（旧版本读到未知 kind 会发生什么）：**

- **Python（conductor）**：`_to_gate:407-410` 逐字：
  `if kind not in GATE_KINDS:` → `raise GateFormatError(f"{path}: unknown kind {kind!r} (expected one of: …)")`。
  `enumerate():480-504` 遇到第一个坏文件即抛；`_consume_answered_gates` 捕获并 **skip 整个 tick**：`conductor.py:284-288` `except gates.GateFormatError as exc: st.timeline.append("config", detail=f"gate file corrupt, tick skipped: {exc}"); return False`，`orchestrate` 在 `:172` 提前返回。tick 的 goal-change 前置检查也捕获同一异常并返回 `"ok"`（`:1970-1976`）。策略由测试钉死：`test_autopilot_conductor_stage.py:415-433`（`test_corrupt_gate_file_skips_tick`，期望 `tick()=="ok"`、出现含 "corrupt" 的 config 事件、无新队列行）。
  → **旧 conductor 遇到 `xkey-authorize` gate：每个 tick 都被跳过（autopilot 冻结），只留 config 事件，不崩溃但停摆。** 注意 conductor 是唯一创建者（`gates.py:246-247/272`、`conductor.py:2064`），正常不会产生"旧 conductor + 新 kind 文件"，只有**降级/热替换/旧 serve 进程未重启**才会遇到。
- **TS（面板/窗口）**：
  - `parseGateFile:595-596` 抛 `GateFormatError`；`listGates:638-676` 按文件 catch 进 `errors`（`:663-666`）并从列表剔除；`deriveStatusModel` 把 `gateScan.errors` 并入 `warnings` → `/autopilot status` 返回 ok + 警告；`/autopilot gates`（`console.ts:175-190`）打印 `warning: …`，该 gate 不出现在 pending 列表。
  - **monitor 面板不受影响**：`scanPendingGate:150-177` 自写行扫描，只要求 `status=="pending" && id!="" && kind!=""`（`:177`），**不做 kind 闭集校验** → 新 kind 仍显示（`:255-267`）。
  - **作答路径不受影响**：`cmdGate` 只校验 `/^gate-\d+$/`（`console.ts:203-206`）；`answerGate` 只要求 frontmatter 有 `status:` 行（`gate-writer.ts:113-135`），**不解析 kind** → 旧窗口仍可 `answerGate` 新 kind gate。
- **判定（决定是否要求所有窗口同步更新）**：**不要求所有窗口同步更新**——旧窗口能作答（按 id）、monitor 能显示；只有 `/autopilot status|gates` 会以 warning 形式隐藏未知 kind（可见性降级，非功能阻断）。**但 Python conductor 必须是含新 kind 的版本**，否则所有 tick 被跳过。建议 kind 与两侧闭集同版本发布，并在 spec/design 明写"升级 conductor 是硬前提"。

### Q5 超时/预算：xkey 工单"超时未答"应复用哪条路径

**gate 无 TTL（复核确认）**：schema 12 字段无 expiry/ttl/remind（`gates.py:65-81`）；config 默认字段 9 个无超时项（`config.py:38-48`、范围表 `:52-60`）；`advance_stall_ticks` 是唯一的时间/重试阈值（`config.py:47`，范围 1..50 `:59`）。

**streak 判据链**：`_advance_stall_ticks`（`:738-745`）读 config 阈值（默认 5）；`_advance_failure_streak`（`:747-810`）从 timeline 尾部倒走，**只对 `ev=="advance"` 且 `exit!=0` 的同一 (key,edge) 事件计数**（`:786-799`），遇到其它事件即"有进展"停止；`_record_advance_result`（`:812-848`）在 `count >= 阈值` 时调 `mark_stalled`（`:844`）。

**"xkey 工单超时未答"的复用判定**：
- 直接复用点 = **`mark_stalled`（`conductor.py:2294-2366`）** 这条终止升级路径。它做的事：roadmap key-status → `stalled`（`:2306-2319`，带锁）、经 `_create_gate` 建一个 `stalled` gate（`:2320-2325`）、写 `achieved.md` 遗留草稿（`:2327-2341`）与 `patterns/<key>/stall-lesson.md`（`:2343-2363`）、追加 timeline `stalled` 事件（`:2366`）；对已 stalled key **幂等早退**：`:2308-2309` `if stage is not None and stage.key_status.get(key) == "stalled": return  # already marked`。
- **但 `_advance_failure_streak` 不会自己触发**：它只数 `advance` 事件，pending gate 不产生 advance 事件。因此"超时检测"必须**新建一条 gate 年龄 streak**，可复用的现成料是：`_create_gate` 记录的 `gate-created` 事件（`conductor.py:2087-2089`，detail 含 `gate-XXXX kind=…`）、tick 每拍追加的 `beat`（`conductor.py:1961`）、gate 自身的 `created_at`（`gates.py:65-81`）。阈值语义直接复用 `advance_stall_ticks`（`:738-745`）或新增 config 键。判定后仍调 `mark_stalled` 收尾。
- 亦可复用 `_gate_open(kind, key=…)`（`:2093-2109`）做"是否已有 stalled gate"的去重守卫。

**与现有 stalled 语义的冲突（同一 key 既有 stalled gate 又有 xkey 工单）**：
1. **双 pending gate**：`mark_stalled` 无条件建 `stalled` gate（`:2320-2325`）。若该 key 还有 pending 的 `xkey-authorize` gate，面板会出现两个待答 gate（monitor 逐个展示，`monitor.ts:255-267`），人答一个另一个仍 pending。
2. **幂等早退吞掉超时动作**：若 key 已因他因 stalled（`:2308-2309`），xkey 超时调 `mark_stalled` 是**静默 no-op**——不建 gate、不写新事件，超时事实丢失。
3. **应用/解冻不对称（最关键）**：`_apply_stalled_approvals`（`:2190-2255`）与 `_apply_stalled_rejections`（`:2258-2286`）**只匹配 `kind=="stalled"`**；`_resume_credits`（`:2168-2188`）也只数 approved 的 `stalled` gate。→ 若超时用 `mark_stalled` 把 key 冻结，之后人 **approve 的是 `xkey-authorize` gate，不会解冻该 key**（没有 xkey 消费/恢复分支，Q4 改动 #5），key 永久停在 stalled；反之若人 approve `stalled` gate，key 恢复，但 `xkey-authorize` 仍 pending，工单悬空。
4. **消费记录本身不冲突**：`_consumed_gate_ids`（`:255-272`）按 gate id 去重，两个 gate 各自独立记账；冲突只发生在 key 状态机与解冻语义上。

**建议的复用方式（写入 design）**：(i) 超时**检测**新建 gate 年龄 streak（复用 `advance_stall_ticks` 阈值语义 + `gate-created`/`beat` 事件，`:2087-2089`/`:1961`）；(ii) 终止**升级**复用 `mark_stalled`（`:2294`），但先用 `_gate_open("stalled", key=K)`（`:2093`）守卫避免重复 gate；(iii) 在 `orchestrate` 的 gate 消费顺序中新增 `xkey-authorize` 消费分支，且排在 `_apply_stalled_*`（`:211/:214`）之前，使 xkey approve 能解冻 key（镜像 `_apply_stalled_approvals` 范式），避免冲突 3；(iv) 若策略不允许冻结（spec §1.3 场景 D / P-009 只要求"有去向、有预算、不空转"），则只把工单置为 `timed-out` 并写升级记录，**不改 key-status**，从根上避开冲突 1/2/3。

## 结论 → 决策映射

| # | 结论（file:line 证据） | 支撑的 design / 决策 |
|---|---|---|
| 1 | 作答有效通道共 3 条：C1 TUI 命令（`console.ts:84/102/197/217`）、C2 CLI/print/RPC 触发同命令（`print-mode.ts:132`、`rpc-mode.ts:399`、命令执行 `agent-session.ts:1122-1130`）、C3 文件直写（`gates.py:13-15`、`gate-writer.ts:15-17`）。in-session LLM 无命令工具（`core/tools/index.ts:1`），但 agent 可走 C2（bash 派生 `pi -p`）与 C3（write/edit/bash） | **D-008** 判别必须覆盖 C3，否则 AC-004 的"可观测拒绝"不成立 |
| 2 | `answerGate`/锁**不校验**身份：`gate-writer.ts:147`（answeredBy 调用方传入）、`:153`（锁仅 O_CREAT\|O_EXCL 互斥，`file-lock.ts:12-42`）；C3 不经锁 | **D-008** 现有写入侧零判别，须新建强制点 |
| 3 | 身份信号仅：`answered_by`=host:pid（自报，`ui-bridge.ts:171-172`）、`PI_WORKER_TASK`（`index.ts:53`）、worker 模式无 `/autopilot`（`worker-mode.ts` 0 个 registerCommand）、`ctx.hasUI`（`types.ts:313`）。无人/agent 可分信号 | **D-008** 不能靠现有身份做判别；可利用"命令 vs 工具/文件"与 `hasUI` |
| 4 | (a) 入口收窄必要不充分（挡不住 C3）；(b) nonce **无效**（同权限 agent 可读，落盘/内存均无判别力）；(c) 双通道对 C3 无效且破坏无状态；(d) 审计必须但单独不足 | **D-008** 推荐 = (a)+工具层写拦截（仿 `protected-config.ts:247-269`，注册 `index.ts:41` 同级）+(d) 披露；不采用 (b) |
| 5 | 新增 `xkey-authorize` 改动点：`gates.py:52`（→ 覆盖 `:217/:407`）、`gates.py:26` 文档、`status-model.ts:467`（→ 覆盖 `:595`）、`conductor.py:274-322` 消费分支、测试两侧；status 闭集/`gate-writer`/`monitor` 无需改 | **D-009** 改动清单 |
| 6 | 旧 TS 窗口：`listGates` 逐文件 catch（`status-model.ts:663-666`）→ warnings + 隐藏；monitor 不校验 kind（`monitor.ts:150-177`）仍显示；`cmdGate`/`answerGate` 不解析 kind → 仍可作答。旧 Python conductor：`enumerate` 抛 `GateFormatError`（`gates.py:407-410`）→ `_consume_answered_gates` catch 后 **skip 整个 tick**（`conductor.py:284-288`，策略测试 `test_autopilot_conductor_stage.py:415-433`） | **D-009**：不要求所有 TS 窗口同步更新（作答/面板可用，仅 status/gates 降级）；但 **conductor 必须同步升级**，否则全 tick 冻结 |
| 7 | gate 无 TTL（`gates.py:65-81`、`config.py:38-48`）；升级路径 = `advance_stall_ticks`（`:738`）+ streak（`:747`）→ `mark_stalled`（`:2294`），但 streak 只数 advance 事件 | **R-3 / KDR Q8**：超时须新建 gate 年龄 streak，终止复用 `mark_stalled` |
| 8 | 与 stalled 语义冲突：双 pending gate（`:2320-2325`）、已 stalled 幂等早退吞动作（`:2308-2309`）、解冻不对称（`_apply_stalled_*` 只认 stalled `:2190/:2258`、`_resume_credits:2168`） | **D-008/design**：新增 xkey 消费分支须排在 `conductor.py:211/:214` 之前且能解冻；或以 `timed-out` 记录替代冻结以规避冲突 |

**D-008 一句话结论**：现存协议没有任何"人/agent"可分信号（`answered_by` 只是自报 host:pid），唯一能产生**可观测拒绝**的落点是新增"agent 工具不得写 gate 目录"的 `tool_call` 硬拦截（仿 `shared/protected-config.ts`），叠加"命令 + `hasUI`"入口收窄；挑战-响应 nonce 对同权限 agent **无效**，不得作为方案。

**D-009 一句话结论**：闭集镜像只需改两处常量（`gates.py:52` + `status-model.ts:467`，解析放行自动覆盖 `:217/:407/:595`）＋ `conductor.py:274-322` 消费分支；旧 TS 窗口只会降级显示（作答仍可用），但旧 conductor 会因 `GateFormatError` 跳过每一个 tick —— **conductor 与 kind 必须同版本上线**。
