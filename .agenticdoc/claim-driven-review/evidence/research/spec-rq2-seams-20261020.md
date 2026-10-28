# RQ-2 接缝盘点：claims 断言集 → 派发校验 → 结算覆盖 → 预算 → 度量

- Key: claim-driven-review
- Card: `tasks/RQ-2-seams-inventory.md`（sha256 `7769c7fd387c70ebd04014c38ac85bb50d9dec9aeb07f07ce3aa9326903f8b11`）
- Type: research（只读仓库；唯一证据文件）
- 盘点基线：当前工作区（`git status` 含未提交改动），行号均指**工作区文件**，不指 HEAD。
- 证据命令：`Select-String` / `Get-Content` / `git ls-files`（PowerShell），Python 3.14。

## 结论

### 0. 结论先行

1. **卡校验**：最小插入点 = `readDispatchCard` 的 `missing` 聚合处 `pm/ui-bridge.ts:2585`（**工具层**）。`dispatch_worker`（调用点 2896）与 `/worker`（3411）共用此函数，一次改动覆盖两入口；`fs` 已在模块内、`projectDir` 在手（2559/2570/2575），**可以**在该点 `fs.statSync` 断言定位目标文件尺寸。拒绝直接复用 `[dispatch-card]` 形态（2607-2613），零副作用断言见 `test/suite/dispatch-card-injection.test.ts:344-352 / 354-362 / 396-405 / 407-416 / 451-457 / 460-468 / 474-483`。服务层只继续跑 envelope 镜像（`launcher.py:2676-2677`），**不要**在服务层判 claims：那里队列行已落盘，拒绝必然产生副作用。
2. **结算**：最小插入点 = `worker/output-writer.ts:357-425` 的 `readTerminalGaps`（`missingSections` 388、`ok` 423）与 `currentRecoveryMissing`（209-219），即 `worker-mode.ts:3872` 的 `exitCode` 折叠**之前**、`finishSuccess` 的 dp3 hook（3903）之前；self-check 侧复用**一次性** `selfCheckSent`（`worker-mode.ts:3332` 声明，3994-3995 置位，`settleOrSelfCheck` 3962-4008），不新增状态即可避免无限补写。
3. **预算**：`allowedCalls` 计的是**允许的调用次数**（每次 `read`/`ls`/`find`/`grep` 各 +1，`worker-mode.ts:2950-2953`），不是去重文件数；**只有 `read`** 计字节（`worker/read-scope.ts:205-207`）。激活条件是 task.md 出现 `read_scope:`（`read-scope.ts:265`）；只有 `deny_globs` 时 `scope=null`，containment 与 caps 都不生效（184/194）。
4. **PM 手工派发加 `read_scope`**：只动 `pm/ui-bridge.ts`（工具参数 2740-2746、`writeDispatchTaskMd` 2624-2700、两处调用点 2930/3448）与测试；不动 `worker-mode.ts::TOOL_ALLOWLISTS`、不动 Python `REGISTRY`，**不会破 T-17**（T-17 只锁 `TOOL_ALLOWLISTS`↔`REGISTRY`，`test_autopilot_l0.py:233-263`）。"由 claim 数推导 caps"要动的是 TS `readDispatchCard`→`writeDispatchTaskMd`，Python `dispatch.py:1492`（须移到 1495 `dispatch_card()` 之后）+ `_read_scope_caps`（224-270）。
5. **不需要 `claim-review` 新类型**：复用 `review`（`TOOL_ALLOWLISTS.review = read/find/grep/ls`，`worker-mode.ts:111`；Python `REGISTRY["reviewer"]` 同集，`dispatch.py:85-127`）。claims 是**卡级机器块**，不是类型语义。新类型要改 6+ 文件并必红 4 条测试（T-17、`test_mwpp_collection_parity.py:112-131`、`dispatch-recovery-terminal.test.ts:314-317`、`test_mwoc_s2_sections.py:130-185`）。唯一代价：`review` 无 `bash`，AC-002 的"命令+结果"证据只能外部执行或另派 `research`/`verifier`。
6. **度量**：claims 计数应落 `run.json`（`shared/run-store.ts:36-56`，新增可选字段）+ 独立 `[CLAIMS]`（或 `[FLOW] claims`）trace 行；**不要**改 `[END]`——两侧都有锚定到行尾的正则（`shared/heartbeat.ts:93`、`mw_common.py:2768`），加字段会静默打断 exit/wall 解析。usage 侧链路：`launcher.py:320-334` end record（调用点 2586）→ `usage.py:831-855` run dict → `build_report` 1103-1164 / `_new_group_entry` 886 / `_finalize_group` 897 / `_format_row` 1215。`/autopilot status` 的 `AutopilotStatus` 是版本化 schema（`STATUS_SCHEMA` 1534；`autopilot-console.test.ts:352-404` exact `toEqual`），指标应放 `StatusModel` 的可选扩展字段（`gateBlockerClasses` 1641 是先例）或 worker 面板 `monitor.ts:124/268/440/519-534/1224`。

## 1. 卡校验链

### 1.1 `dispatch_worker` 参数 → 落盘 task.md 的完整调用链

| # | 函数 / 动作 | 文件:行号 | 要点 |
|---|---|---|---|
| 1 | `registerWorkerTools` 注册工具 | `pm/ui-bridge.ts:2690`；`name: "dispatch_worker"` 2703 | 工具层入口 |
| 2 | 参数 schema（`task_key/card_path/description/cli/model/model_reason/type/images/allow_foreign_write/key`） | `ui-bridge.ts:2710-2762` | `type` 描述在 2740-2746（类型词汇表的 UI 锁） |
| 3 | `execute` + 参数解构 | `ui-bridge.ts:2763`、`2764-2783` | |
| 4 | `validateRagEnabled`（VC-003） | `2790` | 任何写之前 |
| 5 | `resolveOwnerKeyWithSync` | `2794` | 解析/降级 owner key |
| 6 | `foreignLiveClaimRefusal`（跨 key 写守卫） | `2800` | 零副作用 |
| 7 | `resolveDispatchType` | `2814`（定义 `1586-1604`） | 类型白名单 `DISPATCHABLE_TYPES` `shared/dispatch-models.ts:75` |
| 8 | `dispatchPhase` + `dispatchDocGaps`（阶段文档门禁） | `2824-2830` | |
| 9 | 已存在 taskDir 拒绝 | `2842-2851` | |
| 10 | `judgeWriteIntent`（writeless 角色外部写拦截） | `2864-2885`（定义 `2060`） | |
| 11 | **`readDispatchCard`（G-1 卡 gate）** | `2896`（定义 `2556-2601`） | 详见 1.2 |
| 12 | `planDispatchFrontmatter`（模型/阶段/图像计划，含 DP-1 triage） | `2908`（定义 `1628-1800+`） | 任何 fs 写之前 |
| 13 | `writeDispatchTaskMd`（**唯一 task.md 写点**） | `2930`（定义 `2624-2699`） | 见 1.3 |
| 14 | `dispatchTask` → `acquireLock` → `writeFaceVerdict` → `upsertWithinLock`（队列行） | 调用 `2951`；定义 `pm/task-dispatcher.ts:291`、锁 `304`、写面判定 `320`、行写 `326` | 队列行在 `.mw/workers.lock` 临界区内落盘 |

`/worker` 命令是同一语义的第二入口：`USAGE` `3282-3283`，参数解析 `3300-3330`，`readDispatchCard` `3411`，`planDispatchFrontmatter` `3422`，`writeDispatchTaskMd` `3448`，`dispatchTask` `3470`。

### 1.2 卡 gate 在哪一层触发

**两层，但职责不同：**

- **工具层（G-1，可零副作用）**：`readDispatchCard`（`ui-bridge.ts:2556`）→ `readEnvelope`（`shared/dispatch-card.ts:435`）。
  - envelope：`readEnvelope` 2573；
  - 按类 extras：`typeExtrasMissing(envelope.type, text)` 2585（TS 定义 `dispatch-card.ts:457-497`）；
  - seed 最小项：`seedItemsMissing(text)` 2585（定义 `dispatch-card.ts:508-516`，常量 `GOAL_ANCHOR`/`SEED_GOAL_ITEM`/`SEED_PATH_ITEM` 499-501）；
  - 任何 gap → `{...empty, missing}` 返回，调用点 `2902-2904`（工具）/`3417-3419`（命令）在 **mkdir/写盘/入队之前** 返回文本。
- **服务层（G-3，兜底）**：`launcher.py:2676-2677` `if _envelope_enforced(entry): verdict = classify_envelope_refusal(entry)`；Python 镜像常量 `launcher.py:1339-1576`（`DISPATCH_TYPE_VOCABULARY` 1408-1411、`TYPE_EXTRA_PATTERNS` 1414-1429、`type_extras_missing` 1565-1592），跨语言平价由 `test_mwds_t27_service_envelope.py:485-496` 用真实 TS judge 逐例比对。
  - 服务层拒绝会**先产生队列行**（`failed` 状态 + `worker.log`），所以 AC-001 的"零副作用"只能由工具层保证。

### 1.3 最小插入点（新增 claims 块校验）

**唯一推荐插入点：`ui-bridge.ts:2585` 的 `missing` 聚合之后、`if (missing.length > 0)` 之前。**

```ts
// ui-bridge.ts:2585（原文）
const missing = [...(envelope.type === "" ? [] : typeExtrasMissing(envelope.type, text)), ...seedItemsMissing(text)];
if (missing.length > 0) return { ...empty, missing };
```

改动形态（仅形态，不在本卡实现）：

```ts
const claims = parseClaimsBlock(text);                       // 新叶子，放 shared/dispatch-card.ts
const claimGaps = claimsGaps(claims, { projectDir: input.projectDir, roleCap }); // 纯 + stat
const missing = [...typeExtras, ...seedItemsMissing(text), ...claimGaps];
```

- 位置优点：① 同时覆盖 `dispatch_worker` 与 `/worker`；② 复用现成拒绝文本与零副作用测试形态；③ 早于 `planDispatchFrontmatter` 的 DP-1 spawn（`computeDispatchTriage` 在 `planDispatchFrontmatter` 内）——claims 不合规不会先花一次 `mw decide run`。
- **可以在该点 stat 目标文件尺寸**：`fs` 在 `ui-bridge.ts` 顶部已导入，`input.projectDir` 是现有参数（2557-2562），`statSync` 是只读调用，不触碰写面。AC-001 ③ 的 `>32768` 判据在此可判。
  - 但需先定义三种未覆盖形态（见"残留与未验证"）：`symbol` 定位无文件可 stat；定位文件不存在（stat 抛错）；定位在 `projectDir` 之外。
- 建议给 claims 单独拒绝码（如 `dispatch-claims`）而不是混用 `dispatch-card`，以便 card_audit/PM 区分"卡结构不全"与"断言集不全"；文案模板照抄 `dispatchCardRefusal`（2603-2616）：`[<code>] dispatch refused: card '<path>' ... (missing=[claim:C2:locator, claims:budget-sum:48>40]) ... nothing was written.`。AC-001 要求"拒绝原因含 claim id 与缺失要素名"——`missing` 条目用 `claim:<id>:<要素名>` 形态即可同时满足机读与文案。
- **灰度（AC-006）**：`claim_gate: advisory|enforce` 不能放在这个聚合里无条件拒绝；最小形态是 `readDispatchCard` 返回 `claimGaps`，两个调用点在 `enforce` 时拒绝、`advisory` 时把一行 `[claims] 弱告警 ...` 追加到成功回执（工具回执在 `2966-2975`，命令通知在 `3481-3485`）。
  - **注意**：`triage-dispatch.test.ts:355-357` 对无 triage 的回执做了 `toBe` 全文比较，advisory 行只能在"卡里确实有 claims 块"时追加，否则 AC-007 的逐字节不变会红。

### 1.4 拒绝形态的既有实现（拒绝码 + 文案 + 零副作用断言）

- 拒绝码：`DISPATCH_CARD_CODE = "dispatch-card"`（`ui-bridge.ts:2188`）。
- 文案构造：`dispatchCardRefusal` `ui-bridge.ts:2603-2616`（首行 `[dispatch-card] dispatch refused: card '<abs>' is not a complete dispatch envelope (missing=[...]).`，末句 `nothing was written.`）。
- 零副作用断言（全部在同一文件，断言 `fs.existsSync(taskDir) === false` + 队列行数不变）：
  - `dispatch-card-injection.test.ts:344-352`（缺 `card_path`，`missing=[card_path]`）
  - `:354-362`（卡不可读，`missing=[file]`）
  - `:396-405`（缺 `deliverables`）
  - `:407-416`（缺 `type`）
  - `:451-457`（缺 coding extra `验收命令`）
  - `:460-468`（缺 seed 两项 `missing=[seed:goal.md, seed:path:line]`）
  - `:474-483`（`/worker` 入口，`missing=[card_path]`，连 `_scratch/workers` 目录都不存在）
- 解析层单测（判据本身，不涉及落盘）：`dispatch-card-envelope.test.ts:136-197`。

## 2. 结算链

### 2.1 `finishSuccess()` 判定顺序（`worker/worker-mode.ts`）

| 步 | 动作 | 行号 | 说明 |
|---|---|---|---|
| 1 | `if (taskDone) return;` | 3818 | 第二次 settle 无操作（AC-010②） |
| 2 | `consumeDp2NarrowSteer("settle")` | 3824 | dp2 窄 steer 消费，消费成功则 return（run 保持 open） |
| 3 | `evidence = hasDeliverableEvidence(taskDir, lastAssistantText)`（writeless 角色）/ 写角色恒 `delivered` | 3831-3833（`shared/deliverable-evidence.ts:190`） | 无产物 → `no-product`，不进入恢复判定延迟 |
| 4 | `judgeRecovery = judgeRecoveryHere()` | 3846（定义 3680-3683） | writeless 恒判；写角色需 `hasReportProduct`（`output-writer.ts:199`） |
| 5 | 机械回填 `appendMechanicalContextSources`（仅 `上下文来源`） | 3850-3865（定义 `output-writer.ts:293`） | 回填在 `readTerminalGaps` **之前**（I1） |
| 6 | `gaps = readTerminalGaps({... judgeRecovery})` | 3866-3871 | 内部 `checkRecovery`（`output-writer.ts:388`，谓词 `worker/output-sections.ts:210-216`）+ `diffLedger`（393） |
| 7 | `const exitCode: 0 \| 2 = evidence.delivered && gaps.ok ? 0 : 2;` | 3872 | **唯一的终态折叠** |
| 8 | `gapsReason` 组装（missing section / unrecorded / unjudgeable） | 3876-3886 | |
| 9 | `questionsText` 组装（`recovery-incomplete:` / `no-product:`） | 3890-3896 | `## Questions` 首行是 PM 回读点（`output-writer.ts:445-457`） |
| 10 | dp3 澄清替换（`exitCode===2` 时） | 3903-3905（定义 3691-3810） | 自动应答 → 不写终态，run 保持 open |
| 11 | 取终态锁 `taskDone = true` + 清 timer | 3906-3908 | |
| 12 | `writeOutputGuarded({exitCode,...})` | 3910-3925（`output-writer.ts:427`） | 唯一写盘点 |
| 13 | 无产物告警 `recordDispatchAlarm` | 3926-3938 | 仅 `!evidence.delivered` |
| 14 | `recordEnd(exitCode)` | 3948（定义 3285-3305） | `[END]`、run.json 终态 |
| 15 | `markOutcome` | 2699-2701 | `2 → needs-clarification` |

### 2.2 "新增断言覆盖判据"应放在哪一步之前/之后

**放在第 6 步（`readTerminalGaps`）内部作为新增判据类，并在第 7 步（`exitCode` 3872）之前折叠；self-check 侧放在 `settleOrSelfCheck` 的 gap 计算处（`worker-mode.ts:3964`）与 `finishSuccess()` 调用（4007）之间。**

- 之前不能放：第 3 步之前（`hasDeliverableEvidence`）。T-13/D-015 的既有契约是无投递立即 `no-product`，不延迟、不额外给 turn（3960-3993 注释）。claims 判定只能对**已投递**的产物做。
- 之后不能放：第 11 步 `taskDone = true` 之后。那时 `writeOutputGuarded` 的 `exitCode`/`## Questions`/run.json 已经定稿，再判会出现"产物说 done、trace 说缺断言"的分叉，正是 `readTerminalGaps` 被抽成单一判定点的原因（`output-writer.ts:349-356` 注释）。
- 具体落点建议：
  - 终态：`TerminalGaps`（`output-writer.ts:49-110`）加 `claimGaps: string[]`（可选/默认 `[]`，测试没有手构该对象的先例，见 6.2），`ok` 条件在 423 追加 `&& claimGaps.length === 0`；`## Questions` 首行（`gapNote`，`output-writer.ts:448`）追加"未裁决断言：..."。
  - self-check：`currentRecoveryMissing`（209-219）保持"缺段落"语义不变（它的返回值被 `isMechanicalSection` 过滤，3979），另加 `currentClaimGaps(...)`；`settleOrSelfCheck` 里把两者分别渲染成两段文案，但**共用同一个触发条件**（`!selfCheckSent && (substantive.length>0 || claimGaps.length>0) && isDelivered`，3994）。
- **一次性状态变量就是 `selfCheckSent`**（3332 声明；3976 trace 里作为 `selfcheck=sent|pending`；3995 置位）。不要新增第二个布尔：既有的 I1 不变量是"每进程最多一次 self-check 轮"（`mwoc-w2-contract-judgment.test.ts:673-700`）。
- 结算期读取 claim 集合的来源：`taskContent`（`worker-mode.ts:2624`）或 `output-writer.ts` 里的 `taskHeaderScalar(dir,"task.md")` 同款读取。**前提是派发期把 claims 块写进了 task.md**（见 2.3）。

### 2.3 一个必须一起解决的前置事实

`extractCardSections`（`ui-bridge.ts:2258-2325`）只按 **heading** 切片，`<!-- mw-claims: v1 -->` 是 HTML 注释，**不会**被现有卡种子注入（`renderCardSeedSections` 2333、`applyCardSeedSections` 2372）带进 task.md。因此：

- 派发期必须显式把 claims 块原样注入 task.md（在 `mw-dispatch-card: v1` 标记区内追加，或独立 marker），否则结算期与 Python 侧都看不到断言集合；
- 或者让结算期用 task.md 的 `card_path:` 回读卡文件——但卡可能已被改动，`card_sha256:`（`mergeCardHeader` 2468-2481 写入）就是为这种漂移准备的，回读必须校验 sha，成本更高。推荐注入。

## 3. 预算承载

### 3.1 `checkReadScopeCall` 的计费口径

- 函数：`worker/read-scope.ts:167-219`。
- **`allowedCalls` = 允许的调用次数，不是去重文件数**：判定顺序 deny-glob（175）→ scope（184）→ file cap（194，`state.allowedCalls >= config.fileCap`）→ byte cap（205-214）；调用方在允许时 `readScopeState.allowedCalls++`（`worker-mode.ts:2952`）。同一个文件读两次 = 2 次配额。去重只发生在收敛检查点的 `readCounts` map（`worker-mode.ts:3189/3214`），与 read_scope 预算无关。
- **只有 `read` 计字节**：`read-scope.ts:205 if (tool === "read")` → `statSize(path.resolve(...))`（206），`ls`/`find`/`grep` 的 `chargedBytes` 恒 0（只吃 file cap）。
- 拦截面：`read`/`ls`/`find`/`grep` 四个工具（`worker-mode.ts:2940-2947`）；无 path 的调用以 `"."`（项目根）为目标参与 containment（2948-2949；`autopilot-read-scope.test.ts:529-555` 锁定"根越界即 block"）。
- 允许的调用在 `tool_execution_start` 写 `[FLOW] <ts> tool_call <name>` + `[TOOL] <ts> <name> <target>`（`worker-mode.ts:3225-3226`）；被拒绝的调用只写 `[READ_SCOPE]`（`appendReadScopeTraceLine`，2963），不进入 `[FLOW] tool_call`。**因此 `fetches` 有两个不等价口径**：`allowedCalls`（含被拦后的重试前次数）与 `[FLOW] tool_call` 计数（只含放行）。AC-005 必须二选一并写死（spec §3 已按 `[FLOW] tool_call` 定义，见 3.4 差异）。

### 3.2 `readScopeConfigFromMeta` 的激活条件

`read-scope.ts:259-272`：

```ts
if (meta.readScope === undefined && meta.denyGlobs === undefined) return undefined;
```

- 两者都缺 → 返回 `undefined` → `worker-mode.ts:2934 if (readScopeConfig)` 不注册拦截器 → **零拦截**（AC-012 红线，`autopilot-read-scope.test.ts:601-625`）。
- 只有 `deny_globs` → `scope: null`（deny-only）：deny 生效，但 containment（184）和两个 cap（194/205）全部跳过。
- 有 `read_scope`（哪怕空列表）→ `scope` 为数组（空数组 fail-closed）；caps 用 `meta.readFileCap ?? 8` / `meta.readByteCap ?? 65536`（270-271，常量 `read-scope.ts:31-32`）。
- caps 的 task.md 解析：`worker-mode.ts:650-657`（`l2_read_file_cap:` / `l2_read_byte_cap:`，非正数忽略）。`TaskMeta` 字段 `worker-mode.ts:531-534`。

### 3.3 conductor 与 PM 两条通道的 caps 设置

**conductor（Python）**

- 渲染器：`autopilot/dispatch.py:852-1005`；caps 行 `980-983`（`l2_read_file_cap:` / `l2_read_byte_cap:`），`read_scope:` 块 `977-979`，`deny_globs:` `984-986`。
- caps 值来源：`_read_scope_caps(project_root)` `dispatch.py:224-270` —— 只读 `.agenticdoc/_autopilot/config.json` 的**项目层**键（`project_layer` 判定 263-264），缺文件/缺键返回 `(None,None)` → task.md 不写 caps 行（byte-identical，VC-007/VC-008）。
- 调用点：`dispatch.py:1492`（在 `dispatch_card()` 1495 **之前**，且早于 profile/RAG 渲染）。
- 强制 scope：`dispatch.py:1437-1442`，`entry.requires_read_scope`（`verifier`，`REGISTRY` 里 `requires_read_scope=True`，见 `test_autopilot_dispatch.py:55`）。
- conductor 的实际 scope 值由调用方硬编码：`conductor.py:1209`（`.agenticdoc`）、`1727`/`2669`/`2719`/`2754`/`2786`/`2828`/`2879`（`[".agenticdoc/<key>", ".agenticdoc/goal.md"]`）。

**PM 手工（TS）**

- **没有**任何 read_scope/caps 渲染。`pm/` 目录下 `read_scope` 仅 1 处命中，且是注释（`ui-bridge.ts:2143`："Same shape as the existing `read_scope:`/`deny_globs:` headers"）。
- `writeDispatchTaskMd` 只合并 `write_scope`（`mergeWriteScope` 2146）、卡头（`mergeCardHeader` 2468）、decision（`mergeDecisionHeader` 2177）。
- `dispatch_worker` 参数表（2710-2762）与 `/worker` flag 列表（3301-3304）都没有 `read_scope`/caps → 手工派发的 task 永远 `undefined` 配置 → **拦截整体关闭**。

### 3.4 由 claim 数推导 caps：要改的具体函数与调用点

**TS 侧**

1. `shared/dispatch-card.ts` 新增 `parseClaimsBlock(text)` + `claimBudgetCaps(claims, config)`（纯函数，caps 默认值紧邻 `read-scope.ts:31-32` 的既有常量，避免第二套常量）。
2. `pm/ui-bridge.ts:2556-2601 readDispatchCard`：解析 claims，返回 `claims` + `caps`（放进 `DispatchCardGate`，定义 2531-2545）。
3. `pm/ui-bridge.ts:2624 writeDispatchTaskMd`：输入加 `readScope?: string[]`/`readFileCap?`/`readByteCap?`，新增 `mergeReadScope`（与 `mergeWriteScope` 2146 同形态，YAML block list + 两个 scalars），在 `2666 mkdirSync` 之前完成字符串合并。
4. 调用点：`2930`（工具）与 `3448`（命令）把 `cardGate` 里的 caps 透传进去。
5. 若 caps 需要配置：见 3.5 的配置落点，以及 6.1 里"新增 autopilot config key 必红 21-key 锁"的代价。

**Python 侧**

1. `autopilot/dispatch.py:569-601 dispatch_card`：在返回 dict 里加 `"claims": parse_claims_block(text)`（该函数已读全文，是唯一的卡文本来源）。
2. `dispatch.py:1492` 的 `read_file_cap, read_byte_cap = _read_scope_caps(project_root)` **必须下移**到 `1495 card_backed = dispatch_card(...)` 之后，改为 `_read_scope_caps(project_root, card_backed)`。
3. `_read_scope_caps`（224-270）：签名加 claim 数，值 = `min(3*claims, 60)` 次 / `min(claim_bytes, 512*1024)`，且**项目配置显式值优先**（保持 263-270 的"缺键才回退"语义）。
4. `render_task_md`（852-1005）无需改：`read_file_cap`/`read_byte_cap` 已在签名（860-861）与渲染（980-983）。
5. 若 conductor 的 claim 卡是 synthesized（`synthesized_card` 777）而非 `tasks/<stem>.md`，`dispatch_card` 返回 `None`，需要在 synthesized 路径也带上 claims（或明确 conductor 只在卡 backed 时启用 claims）。

### 3.5 明确回答：给 PM 手工派发加 `read_scope` 参数要动哪几个文件、会不会破 T-17

要动 **1 个生产文件 + 测试**：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
  - 工具参数 schema（2710-2762）与 `/worker` flag 解析（3301-3311）；
  - `writeDispatchTaskMd` 输入与 `mergeReadScope`（2624-2699，紧邻 2146）；
  - 两处调用点（2930 / 3448）。
- 可选：`worker/read-scope.ts`（31-32 附近放 claim→cap 的默认常量/纯函数）；不涉及 `worker-mode.ts` 的解析（650-657 已支持 caps）。
- 测试：`test/suite/autopilot-read-scope.test.ts:323-383`（parseTaskMd 形状）与 `:455-625`（wiring）加 PM 派发渲染用例；`triage-dispatch.test.ts:355` 只有回执文本变化时才需要更新。

**不会破 T-17**：T-17 的两条锁是

- `test_autopilot_l0.py:233-263`：`REGISTRY`（7 类）↔ TS `TOOL_ALLOWLISTS`（逐类 order-exact），并断言 TS key 集合 == `py_reg ∪ {coding, review, research, fallback}`；
- `test_autopilot_dispatch.py:31-68`：`REGISTRY` 类型集合与每类工具元组。

两者都只看**类型→工具集**。新增一个 `read_scope` 参数、渲染 4 行 frontmatter，既不新增类型也不改任何工具元组，T-17 保持全绿。会破 T-17 的唯一路径是"新增 `claim-review` 类型"或"给 `review` 加 `bash`"（见第 4 节）。

## 4. 类型与词汇表

### 4.1 若新增 `claim-review`：要改的文件与"漏改红哪条测试"

| 层 | 文件:行号 | 改动 | 漏改会红 |
|---|---|---|---|
| TS 工具白名单 | `worker/worker-mode.ts:109-140`（`TOOL_ALLOWLISTS`，`review` 在 111，`fallback` 在 139） | 新增 entry | `test_autopilot_l0.py:233-263`（TS missing types / key drift / 逐类比较） |
| TS 词表 | `shared/dispatch-card.ts:221-232`（`DISPATCH_TYPE_VOCABULARY`，11 项） | 新增 token | `dispatch-recovery-terminal.test.ts:314-317`（`REGISTERED_WORKER_TYPES ⊆ vocabulary`；若只改 allowlist 不改词表必红） |
| TS extras | `shared/dispatch-card.ts:194-198`（`TYPE_EXTRA_SECTIONS`）+ `249-266`（`TYPE_EXTRA_PATTERNS`）+ `185-191`（`REVIEW_EXTRA_SECTIONS` 等） | 新类型若要 extras | 无直接锁；但漏改则 `typeExtrasMissing` 走 `isKnownDispatchType` 早退（461-466），卡可无审计目标/未覆盖面声明而过 |
| TS 可派发类型 | `shared/dispatch-models.ts:75`（`DISPATCHABLE_TYPES`）+ `58-69`（`DISPATCH_ROLE_BY_TYPE`） | 新增 | `test_autopilot_l0.py:348-390`（`test_vc014_pm_dispatch_awareness_texts`：tool `type` 描述 token 集必须 == `DISPATCHABLE_TYPES ∪ {codex}`，**描述串 2740-2746 也要改**） |
| TS 恢复契约 | `worker/output-sections.ts:52-55`（`RECOVERY_TYPE_SECTIONS`）+ `63`（`RECOVERY_CONTRACT_TYPES`） | 若新类型需特殊段 | `test_mwoc_s2_sections.py:130-185`（TS 表 ↔ Python 镜像逐字；`extras ⊆ RECOVERY_CONTRACT_TYPES`） |
| TS 队列工具集 | `worker/worker-mode.ts:168`（`REGISTERED_WORKER_TYPES`） | 自动派生，无需改 | （派生值） |
| Python 注册表 | `autopilot/dispatch.py:85-127`（`REGISTRY`，7 类） | 新增 entry（tools/cli/provider/requires_read_scope/conductor_dispatchable） | `test_autopilot_dispatch.py:31-68`（`set(REGISTRY)` 精确集合） |
| Python 词表 | `launcher.py:1408-1411`（`DISPATCH_TYPE_VOCABULARY`，11 项） | 新增 token | `test_mwds_t27_service_envelope.py:485-496` 只在语料出现该类型时红；`test_mwds_t27...:382` 附近说明 known 角色 extras 为空 |
| Python extras | `launcher.py:1387-1394`、`1414-1429` | 新类型 extras | 同上平价 |
| Python 角色映射 | `mw_common.py:143`（`DISPATCH_ROLES`）+ `144-160`（`TASK_TYPE_TO_ROLE`） | 新增 | `test_dispatch_models.py:143-159`（`_TS_ROLE_BY_TYPE` 逐项） |
| Python 恢复契约 | `dispatch.py:615-619`（`RECOVERY_TYPE_SECTIONS`）+ `637-639`（`RECOVERY_CONTRACT_TYPES`） | 与 TS 同步 | `test_mwoc_s2_sections.py:130-185` |
| 冻结快照 | — | — | `test_mwpp_collection_parity.py:112-131`（11-key `_EXPECTED_ALLOWLISTS` 字面量，key 漂移/顺序漂移必红） |
| 任务类型平价 | `test_task_type_parity.py:79-87`（内嵌 `POWER_TOOLS`） | 新增 entry（仅影响 fixture 用例的 `escalates`） | 当前 fixture 无新类型用例，不红；但新旧类型在 fixture 里出现时会红 |

**结论：不需要新类型，复用 `review`。** 理由：

1. `review` 的工具集 `["read","find","grep","ls"]`（`worker-mode.ts:111`）与 Python `REGISTRY["reviewer"]`（`dispatch.py:85-127`）已经逐字对齐，claims 取证单元不需要新工具。
2. claims 是**卡级机器块**（`<!-- mw-claims: v1 -->`），语义是"这份 review 要裁决哪些断言"，与 `type:` 正交；把类型当开关会迫使同一种 review 在两种类型下维护两套 extras/契约/模型 role。
3. `review` 的恢复契约已经含 `未覆盖面声明`（`output-sections.ts:52-55`），AC-002 的 `## 断言裁决` 只需追加为新段（或作为 `## 证据` 的子表），不必新类型。
4. AC-006 的灰度开关放在**卡块/配置**上即可，不需要类型维度。
5. 唯一实质缺口：`review` 无 `bash`，无法执行"命令+期望结果"判据。处理面（按 GC-2 本 key 不改工具集）：
   - 断言判据只允许 `path:line` 与"已落盘证据引用"；
   - 需要命令的断言，由 PM 在合并单元或 `research`/`verifier` 单元执行；
   - 若最终决定要 shell，才考虑 `claim-review`（届时按 4.1 全表改），但那是另一个 key 的工具集决策（spec §1.4 已排除）。

## 5. 度量接缝

### 5.1 `status-model.ts` 的面板字段来源

- `deriveStatusModel(projectDir)` `autopilot/status-model.ts:1684-1768`：纯文件派生，唯一硬失败是 config.json 非法（1691-1693）。
- `AutopilotStatus`（版本化，`schema: "autopilot-status/1"`）定义 1622-1631；子结构 `StageView` 1554-1558、`StageKeyView` 1547-1552、`KeyRounds` 1541-1546、`GateView` 1560-1570 附近。
- 字段来源：`_roadmap.md`（`readRoadmap` 675、`currentStage` 1650-1661）、`_index.parallel` 的 phase（1699）、`usedRounds([<key>/workers])`（1500-1532）、gate 文件（`listGates` 1716-1731）、`timeline.jsonl` head（1735）。
- **注意：worker 面板不是 status-model**。底部面板是 `autopilot/monitor.ts`：`readMonitorState` 440-660、`MonitorSnapshot` 268-300、`MonitorWorker extends WorkerEntry` 124-127、worker 行来自 `WorkerStore.readAll()`（519-534）、渲染 `renderMonitorLines` 1224-1350。
- `/autopilot status` 的输出构造点：`autopilot/console.ts:181-191`（`const result = deriveStatusModel(projectDir)` 183）→ `renderStatusText` `status-model.ts:1777-1810` 或 `JSON.stringify(result.model.status)`（190）。`mw_status` 工具（`ui-bridge.ts:1558-1581`）只报 serve PID，**不是**指标出口。
- 锁定测试：`autopilot-console.test.ts:352-404`（`s.stage`/`s.gates`/`s.timeline`/`s.config` 全部 `toEqual`，schema 字面量 364）→ **给 `AutopilotStatus` 加字段必红**。

### 5.2 `usage.py` 的聚合入口

| 环节 | 文件:行号 |
|---|---|
| ledger 读取 + start/end 配对 | `usage.py:717-861`（run dict 构造 807-830） |
| 事件窗口过滤 | `usage.py:842-860` |
| 聚合（totals + 4 个 group 维度） | `usage.py:1103-1164`（`total_tokens`/`total_calls` 1111-1112；`buckets` 1104-1109） |
| group 初始化/收尾 | `usage.py:886-896`（`_new_group_entry`）、`897-941`（`_finalize_group`，wall p50/p90） |
| 报表结构返回 | `usage.py:1137-1170`（`totals` 1147-1153、`groups` 1155、`coverage` 1156） |
| 文本渲染 | `usage.py:1215-1233`（`_format_row`）、`1248-1287`（`format_report_text`） |
| ledger 写入 | `usage.py:240-267`（`append_event`） |
| ledger 生产（claims 必须在这里进） | `launcher.py:282-334`（start/end record）、调用点 `2586`（reap）、`_reap_entries` `1023-1035` |

`load_runs` 只透传固定字段（807-830），任何新字段（如 `claims`）必须在 320-334 的 `end` record 里写、在 807-830 里透传，否则 `build_report` 看不到。

### 5.3 新增 `claims/closed/partial/unverified/fetches/tokens_per_closed_claim` 应落在哪个结构体

- **每 run 的原始计数**：`RunState`（`shared/run-store.ts:36-56`，`schema/task_key/run_id/owner_key/kind/status/.../artifacts`）。新增可选字段（`claims?: number`、`claims_closed?`、`claims_partial?`、`claims_unverified?`、`fetches?`、`tokens?`）并在 `readRunState`（70-91）保持宽松（它只校验 `status`/`task_key`）。`tokens` 的真实来源仍是会话 usage（`usage.scan_pi_session` 414-516），run.json 不重复存 token，避免双写不一致。
- **trace**：新增独立行（`[FLOW] <ts> claims total=6 closed=4 partial=1 unverified=1 fetches=37`），由 `appendTrace`（`output-writer.ts:572-578`）写；**不要**扩 `[END]`（见结论 6）。
- **usage 聚合**：`run` dict（`usage.py:807-830`）+ `_new_group_entry`（886）新增 `claims/closed/partial/unverified/fetches` 累加；`_finalize_group`（897-941）计算派生比率 `tokens_per_closed_claim = total_tokens / closed`（`closed == 0 → None`，遵守 usage.py "None renders -, never 0" 契约，1175-1201）。
- **PM 面板**：`MonitorSnapshot`（monitor.ts:268-300）或 `StatusModel` 的可选字段（1640 `gateBlockerClasses` 先例）。不要进 `AutopilotStatus`（5.1 的 exact `toEqual` 锁）。
- **`pm status`**：本仓没有名为 `pm status` 的字面命令（`pm status` 命中 0，见未找到清单）。等价出口是 `/autopilot status`（console.ts:181-191）；若要 `tokens_per_closed_claim` 出现在这里，扩展 `renderStatusText`（status-model.ts:1777）读取 `StatusModel` 的可选字段即可，`--json`（190）保持 schema 不动。

### 5.4 是否要动 dist / bundle

**要，且两者都是 tracked 产物：**

- `git ls-files packages/coding-agent/dist` → **1005** 个文件（其中 `dist/extensions/agent-team-loop/**` **216** 个）；由 `packages/coding-agent/package.json:37` 的 `"build": "tsgo -p tsconfig.build.json …"` 生成。
- `git ls-files packages/multi-workers/dist` → **1** 个文件 `dist/extensions/agent-team-loop.js`；由 `packages/multi-workers/build-extension.sh`（esbuild，`format: "esm"`，注入 `__PI_CODING_AGENT_VERSION__`）生成。
- 结论：实现 key 必须同时重建这两处并提交（本卡为只读盘点，未执行 build）。

## 6. 破坏面清单

### 6.1 必红 / 需更新

| 改动 | 会红的测试（文件:行号） | 原因 |
|---|---|---|
| 派发期 claims 拒绝（新拒绝码） | `dispatch-card-injection.test.ts:344-352,354-362,396-405,407-416,451-457,460-468,474-483` 的**形态**是模板，不是必红；真正必红的是任何断言"任务卡只有 envelope/extras/seed 三类 gap"的 `missing=[...]` 全等断言（同上，若 claims gap 加进同一 `missing` 数组，含 review 卡的 fixture 需新增期望） | `missing` 数组被逐字断言 |
| advisory 行追加到成功回执 | `triage-dispatch.test.ts:355-357`（`toBe` 全文） | 回执字节锁；只在"卡含 claims"时追加即可避免 |
| claims 块注入 task.md | `dispatch-card-injection.test.ts:180-340`（卡种子/写入面/字节形态断言区，含 `CARD_SEED_MARKER` 位置） | task.md 字节形态 |
| `read_scope`/caps 渲染进 PM task.md | `triage-dispatch.test.ts:349-362`（task.md 含 `type: coding` 但不含全等）、`dispatch-card-injection.test.ts` 的卡头断言 | 只在 claims 存在时新增行，无 claims 时字节不变（AC-007） |
| caps 由 claim 数推导（conductor） | `test_autopilot_readcap_injection.py:482-492`（VC-001 注入与位置）、`:545-561`（VC-003 值随配置）、`:649-696`（VC-007/008 byte-identical）、`:762-792`（VC-010 小 cap 仍 block）、`:794-866`（VC-011 非法值不无限）、`:900-940`（baseline/签名） | caps 值与"缺配置不渲染"契约 |
| 新增 autopilot config key（`claim_gate` / claim caps） | `autopilot-console.test.ts:933`（21 键）、`:953-965`（`BOOL_FIELDS` 逐项、`DEFAULT_CONFIG` 不含 `envelope_fallback`）、`:969-984`（`INT_RANGES` 顺序）；`test_autopilot_config.py:56-57`（范围校验）；`test_autopilot_config_parity.py:423-427`（两侧 21 键硬编码） | 21-key 冻结；**用 `envelope_fallback` 式"注册表内、DEFAULT_CONFIG 外"可选键可避免**（`config.py:118-125` / `status-model.ts:173-186`），但 `BOOL_FIELDS` 逐项断言仍要改 |
| 改 `[END]` 行格式 | `shared/heartbeat.ts:93`（锚定 `$`）、`mw_common.py:2768`（锚定 `$`）、`test_common.py:428-459`、`heartbeat-progress.test.ts:42-70`、`change-ledger.test.ts:96` | 两侧解析器都会失配 → exit/wall 归零 |
| 新增 `claim-review` 类型 | `test_autopilot_dispatch.py:31-68`、`test_autopilot_l0.py:233-263`、`test_mwpp_collection_parity.py:112-131`、`test_mwoc_s2_sections.py:130-185`、`dispatch-recovery-terminal.test.ts:314-317`、`test_autopilot_l0.py:348-390`、`test_dispatch_models.py:143-159` | 类型/工具/词汇/契约四套平价 |
| `TerminalGaps` 加必填字段 | 无手构对象的测试（6.2），但 `writeOutput` 的默认路径（`output-writer.ts:443-444`）会漏字段 → 用可选/默认 `[]` | 运行期而非编译期风险 |
| 改 `readScopeConfig` 语义（deny-only 也计 caps） | `autopilot-read-scope.test.ts:216-254`（默认值与越界优先）、`:360-382`（缺失/非法 caps 不定义） | D-106/AC-012 语义锁 |

### 6.2 不应红（红了说明设计错）

| 改动 | 不应红的测试 | 理由 |
|---|---|---|
| 无 claims 块的卡 | 全部 `dispatch-card-injection.test.ts`、`dispatch-card-envelope.test.ts`、`triage-dispatch.test.ts:349-368` | AC-007：未带 claims 的卡逐字节不变 |
| 无 claims 的 report | `output-recovery-contract.test.ts:107-150`、`mwoc-matrix-t07.test.ts:248-311`、`mwoc-w2-contract-judgment.test.ts:261-282,371-396` | `checkRecovery` 谓词本身不改，只加"新判据类" |
| 无 claims 的 settle | `mwds-t04-deliverable.test.ts:400-420`（exit=2/needs-clarification）、`dispatch-recovery-terminal.test.ts:432-460`（`readTerminalGaps` 单一判定） | `ok` 只在新字段非空时变化 |
| PM 手工通道加 read_scope 参数 | `test_autopilot_l0.py:233-263`（T-17）、`test_autopilot_dispatch.py:31-68`、`test_mwpp_collection_parity.py:112-131` | 不新增类型、不改工具集 |
| 复用 `review` 类型 | `dispatch-recovery-terminal.test.ts:314-317`、`test_mwds_t27_service_envelope.py:485-496` | 词表与 extras 未变 |
| run.json 加可选 claims 字段 | `test_run_identity.py`、`test_mwds_t10_dispatch_run_state.py`、`mwds-t04-deliverable.test.ts:229-340`（run.json 读取） | `readRunState` 只校验 status/task_key（run-store.ts:84-88） |
| usage 加可选聚合字段 | `test_stats_cli.py`、`test_usage.py`、`test_launcher_run_ledger.py` | `build_report` 返回 dict 加键；若测试断言 `set(report)` 全等则需核对（未在本卡覆盖） |
| trace 新增独立 `[CLAIMS]` 行 | `heartbeat-progress.test.ts`、`test_common.py:428-459`、`change-ledger.test.ts` | 新行不匹配既有锚定正则 |
| 不新增 config key（用卡级开关） | `autopilot-console.test.ts:933-984`、`test_autopilot_config_parity.py:423-427` | 21-key 冻结不动 |

## 接缝表

| 层 | 文件:行号 | 函数 | 改动形态 | 锁定测试 |
|---|---|---|---|---|
| 卡 gate（工具层） | `pm/ui-bridge.ts:2585` | `readDispatchCard` | `missing` 聚合追加 `claimsGaps(...)`；返回值加 `claims/caps` | `dispatch-card-injection.test.ts:344-483` |
| 卡解析（叶子） | `shared/dispatch-card.ts:221-232` 附近新增 | `parseClaimsBlock` / `claimsGaps` | 纯解析 + 正则；被 ui-bridge 与 worker-mode 共用 | 新增单测；`dispatch-card-envelope.test.ts` 保持绿 |
| 卡 gate（服务层） | `launcher.py:2676-2677` | `classify_envelope_refusal` | 不改（claims 只在工具层） | `test_mwds_t27_service_envelope.py:485-496` |
| task.md 注入 | `pm/ui-bridge.ts:2333/2372/2624-2699` | `renderCardSeedSections` / `applyCardSeedSections` / `writeDispatchTaskMd` | 在卡种子区原样带出 claims 块 + `read_scope`/caps 行 | `dispatch-card-injection.test.ts` 字节断言 |
| 结算（终态） | `worker/output-writer.ts:357-425` | `readTerminalGaps` | `TerminalGaps` 加 `claimGaps`（可选默认 `[]`），`ok`（423）纳入 | `dispatch-recovery-terminal.test.ts:432-460`、`mwoc-matrix-t07.test.ts:128-311` |
| 结算（self-check） | `worker/output-writer.ts:209-219` + `worker/worker-mode.ts:3962-4008` | `currentRecoveryMissing` / `settleOrSelfCheck` | 新增 `currentClaimGaps`；复用 `selfCheckSent`（3332/3994-3995） | `mwoc-w2-contract-judgment.test.ts:648-700`、`dispatch-recovery-terminal.test.ts:197-215` |
| 结算（exit 折叠） | `worker/worker-mode.ts:3872` | `finishSuccess` | `exitCode = delivered && gaps.ok && claimGaps.length===0 ? 0 : 2` | `mwds-t04-deliverable.test.ts:400-420` |
| 预算（读侧） | `worker/read-scope.ts:31-32/167-219/259-272` | `checkReadScopeCall` / `readScopeConfigFromMeta` | 常量与"claim→caps"纯函数；不改计费口径 | `autopilot-read-scope.test.ts:149-254/323-383/455-625` |
| 预算（Python 渲染） | `autopilot/dispatch.py:224-270/1492/852-1005` | `_read_scope_caps` / `dispatch` / `render_task_md` | `dispatch_card` 返回 claims；caps 调用下移到 1495 后 | `test_autopilot_readcap_injection.py:482-940` |
| 类型/词汇 | `worker/worker-mode.ts:109-140`、`shared/dispatch-card.ts:194-266`、`autopilot/dispatch.py:85-127`、`launcher.py:1408-1429` | — | **不改**（复用 review） | `test_autopilot_l0.py:233-263`、`test_mwpp_collection_parity.py:112-131` |
| 度量（run） | `shared/run-store.ts:36-56`；`worker/output-writer.ts:572-578` | `RunState` / `appendTrace` | 可选字段 + 独立 `[CLAIMS]` 行 | `mwds-t04-deliverable.test.ts:229-340` |
| 度量（usage） | `launcher.py:320-334/2586`、`usage.py:807-830/886-941/1103-1164/1215` | `_usage_end_record` / `load_runs` / `build_report` | end record + run dict + 聚合/派生比率 | `test_launcher_run_ledger.py`、`test_usage.py`、`test_stats_cli.py` |
| 度量（面板） | `autopilot/monitor.ts:124/268/440/519-534/1224`；`autopilot/status-model.ts:1641/1777` | `readMonitorState` / `renderStatusText` | 可选字段，不进 `AutopilotStatus` | `autopilot-console.test.ts:352-404` |

## 未找到清单

1. `pm status` 字面命令：**未找到**。
   - 命令：`(Get-ChildItem packages/coding-agent/src/extensions/agent-team-loop -Recurse -Filter *.ts | Select-String -Pattern 'pm status') | Measure-Object` → `Count = 0`。
   - 等价出口是 `/autopilot status`（`autopilot/console.ts:181-191`）与 `mw status`（`mw.py:580`，只报 serve PID）。
2. claims 机器块既有实现：**未找到**。
   - 命令：`(TS src + multi-workers *.py) | Select-String 'mw-claims'` → `Count = 0`。
   - 唯一 `*claims*` 命中是 conductor 的 `synthetic_claims`（`conductor.py:428/573/580`），语义是 key 级合成认领，**不能复用**（命名冲突，新模块避免叫 `claims` 裸名）。
3. PM 手工通道的 read_scope 渲染：**未找到**。
   - 命令：`(Get-ChildItem .../pm -Recurse -Filter *.ts | Select-String 'read_scope') | Measure-Object` → `Count = 1`，唯一命中是注释 `ui-bridge.ts:2143`（"Same shape as the existing read_scope:/deny_globs: headers"），**没有**对应渲染代码。
4. `tokens_per_closed_claim` 指标：**未找到**。
   - 命令：`(packages/coding-agent/src + packages/multi-workers *.ts/*.py) | Select-String 'tokens_per_closed'` → `Count = 0`。
5. claims 与 `[END]` 兼容的既有扩展位：**未找到**（两侧 `[END]` 正则锚定 `$`，见 6.1）。

## 未覆盖面声明

- 未运行任何测试（只读盘点），所有"必红/不应红"是**静态判据 + 测试断言形态**推断，非执行结果。
- 未核 `packages/coding-agent/test/extensions/agent-team-loop.test.ts` 全部 6000+ 行：只按符号命中检查了 `resolveDispatchType`/`Invalid type`（5611/5630/5743-5773）与 `dispatch_worker` 调用点，没有逐条审阅该文件里可能存在的"参数集合全等"断言。
- 未核 `packages/multi-workers/test_usage.py` / `test_stats_cli.py` / `test_launcher_run_ledger.py` 的断言细节（只按文件名与 `build_report` 结构推断"加键不红"），若其中存在 `set(report) == {...}` 全等断言则会红。
- 未核 `mw.py` 的 `/mw stats` 输出构造：本卡只按 `usage.format_report_text`（1248-1287）定位渲染点，未追 `mw.py` 的 CLI 包装层。
- 未验证 `dist/` 与 `src/` 的当前差异是否已包含未提交改动（`git status` 显示 `dist/extensions/agent-team-loop/index.js` 已修改），因此"重建 dist"的具体 diff 未评估。
- 未评估 Windows 特有路径行为（`isSameOrUnder` 的 win32 小写比较）对 claim 定位 stat 的影响；只在 3.1 记录了实现位置。
- 未评估 claims 块与 `worker_file` 64 KiB 写面上限、`progress.md` 交互（P-007 相关），本卡只盘点派发/结算/预算/度量四处接缝。

## 证据

1. 卡校验链逐函数行号：`read` `pm/ui-bridge.ts:2556-2701`、`2690-2975`、`3270-3485`；`read` `shared/dispatch-card.ts:194-266/435-516`。
2. 服务层镜像：`grep` `launcher.py` → `ENVELOPE_ENFORCE_SINCE` 1339、`DISPATCH_TYPE_VOCABULARY` 1408-1411、`type_extras_missing` 1565-1592、`_envelope_refusal` 1968-1983、`_poll_once` 2531、gate 调用 2676-2677。
3. 结算链：`read` `worker/worker-mode.ts:3813-3955`、`3962-4008`、`3680-3683`、`2699-2701`；`read` `worker/output-writer.ts:49-110/209-219/357-425/427-560`。
4. 预算：`read` `worker/read-scope.ts:31-32/167-219/259-272`；`grep` `worker-mode.ts` → 2678-2682、2934-2965、650-657；`read` `autopilot/dispatch.py:224-270/1437-1442/1492-1507/852-1005`；`grep` `conductor.py` `read_scope=` → 1209/1727/2669/2719/2754/2786/2828/2879。
5. 平价锁：`read` `test_autopilot_l0.py:216-263/352-390`、`test_autopilot_dispatch.py:31-68`、`test_mwpp_collection_parity.py:34-131`、`test_mwoc_s2_sections.py:96-130`、`dispatch-recovery-terminal.test.ts:300-320`。
6. 度量：`read` `usage.py:240-267/717-861/886-941/981-1170/1215-1287`；`read` `launcher.py:282-334/419-500/1023-1035/2570-2600`；`read` `run-store.ts:36-56`；`read` `status-model.ts:1534-1810`；`read` `monitor.ts:124-135/268-300/440-534/1224-1350`；`read` `autopilot/console.ts:181-191`。
7. tracked 产物：`git ls-files packages/coding-agent/dist | Measure-Object -Line` → 1005；`git ls-files packages/multi-workers/dist | Measure-Object -Line` → 1；`git ls-files packages/coding-agent/dist/extensions/agent-team-loop | Measure-Object -Line` → 216；`read` `packages/multi-workers/build-extension.sh`。
8. 计数：`DISPATCH_TYPE_VOCABULARY` = 11 项；`TOOL_ALLOWLISTS` = 11 key；Python `REGISTRY` = 7 类（脚本正则计数）。
9. 未找到计数：`pm status` = 0、`mw-claims` = 0、`tokens_per_closed` = 0、`pm/` 下 `read_scope` = 1（注释）。

## 残留与未验证

1. **AC-001 ③ 的边界语义**未定：`symbol` 定位无文件可 stat；定位文件不存在时 `statSync` 抛错；定位在 `projectDir` 之外时是否允许 stat。三者都需要在设计相位写死（建议：symbol 豁免；不存在 → 拒绝并命名；越界 → 拒绝）。
2. **`Σ预算 ≤ 角色上限（默认 40）` 的"角色上限"住哪**未定：卡级字段、`.mw/dispatch.yml` 新 section、或 `_autopilot/config.json` 可选键。三者的破坏面不同（见 6.1），本卡只确认"不能用 21-key DEFAULT_CONFIG"（会红两处 21 键锁）。
3. **claims 块的 `## 断言裁决` 表与现有 `## 证据` 段的关系**未定：作为独立 H2（`output-sections.ts` 只认 H2 别名，需在 `RECOVERY_TYPE_SECTIONS` 或新判据里加别名）还是 `## 证据` 的子表。两种都会动 `checkRecovery` 的输入文本；本卡只确认插入点在 `readTerminalGaps`。
4. **`fetches` 口径二选一**未定：`allowedCalls`（允许次数，含拦截前的尝试不计）vs `[FLOW] tool_call` 计数（只含放行）。spec §3 AC-005 写的是 `fetches`，§5 记忆前馈写的是 `[FLOW] tool_call` 计数；两者在"被 read_scope 拦截后重试"的场景会分叉。
5. **PM 手工通道的 caps 默认值**未定：`3×claims`、上限 60 次/512 KiB 是 AC-003 的建议值，但 `read-scope.ts` 的既有默认是 8/65536，本 key 明令不改默认（spec §1.4）。新值必须是**显式写入 task.md** 的 caps 行，而不是改默认常量。
6. **conductor 的 claim 卡来源**未验证：`dispatch_card()` 只认 `<key>/tasks/<stem>.md`，L2/L3 的 synthesized card 路径（`synthesized_card` 777）没有 claims；AC-004 的"两通道语义一致"需要 conductor 也支持卡级 claims（或明确 conductor 只在 card-backed 时启用）。
7. **未执行测试**：本卡所有破坏面结论是静态判据；实现 key 必须用 `./test.sh` 的对应子集与 `packages/multi-workers` 的定向 pytest 验证（禁止全量 vitest/pytest 的规则同样适用于实现相位）。

## 上下文来源

- 派发卡：`.agenticdoc/claim-driven-review/tasks/RQ-2-seams-inventory.md`
- 需求与 AC：`.agenticdoc/claim-driven-review/spec.md`（§3 AC-001…AC-007）
- Key 决策：`.agenticdoc/claim-driven-review/key-decision.md`
- 项目目标锚点：`.agenticdoc/goal.md`（"不修改 pi 核心"、"文件驱动的去中心化协调"）
- 代码（只读）：`packages/coding-agent/src/extensions/agent-team-loop/{pm,worker,shared,autopilot}/**`、`packages/multi-workers/{autopilot,launcher.py,usage.py,mw_common.py,mw.py,build-extension.sh}`
- 测试（只读）：`packages/coding-agent/test/suite/**`、`packages/coding-agent/test/extensions/**`、`packages/multi-workers/test_*.py`
- 工具：`read`、`Select-String`/`Get-Content`（PowerShell）、`git ls-files`、Python 3.14（仅计数/未写仓库）

[VERIFY] seams=5 min_insert_points=5 files_to_edit=11 tests_named=29 new_types=0 t17_breaks=0 vocab=11 allowlists=11 py_registry=7 dist_tracked_files=1006 claims_impl_hits=0 tokens_per_closed_hits=0
