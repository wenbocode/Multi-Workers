# Research: 集合计算与 parity 影响面（design）

## 决策问题

RQ-D2：改 `applyRagTools` 的集合计算、新增 `activeToolsForType`、并在检查点按角色分流（design D-104/D-106，VC-003/004/007/008），会波及哪些既有调用方与测试？逐条核实：

1. `toolsForType` 的全部调用方；`rag/tools.ts` 的 import/使用是否需随 D-106 调整。
2. `applyRagTools` 的全部调用方；`rt === null`（`:402`）与 `:406` 的差异；PM 模式是否受影响（AC-003/AC-007 边界）。
3. `setActiveTools` 的其它调用点：是否存在覆盖 worker active set 的路径（VC-004/VC-007 确定性）。
4. `writeCheckpoint()` 当前 steer 文本的逐字基线；两条分支的 `deliverAs` 建议。
5. parity/回归面：`test_autopilot_l0.py:215-239`、`test_autopilot_dispatch.py`、`test_rag_research.py:71` 的断言集合；「表不动」前提下 VC-008 的快照做法与反例。
6. 若 D-106 挂载点或 D-104 判据在证据上不成立，给出替代挂载点（含 file:line）。

## 调研方法与出处

- `read`（整段）：
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（全文，1094 行）
  - `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts`（注册/激活段 + `applyRagTools`）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（全文，250 行）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（`:595-675`）
  - `packages/coding-agent/src/core/extensions/loader.ts`（`:180-280`）、`packages/coding-agent/src/core/agent-session.ts`（`:2455-2560`）
  - `packages/multi-workers/test_autopilot_l0.py`、`test_autopilot_dispatch.py`、`test_rag_research.py`
  - `packages/coding-agent/test/suite/autopilot-protocol.test.ts`、`rag-research-doc.test.ts`、`rag-tools.test.ts`、`rag-budget.test.ts`、`autopilot-read-scope.test.ts`、`dual-root-worker.test.ts`、`cross-drive-worker.test.ts`、`test/extensions/agent-team-loop.test.ts`
- `rg -n` 定界：`toolsForType`、`applyRagTools`、`setActiveTools`、`TOOL_ALLOWLISTS`、`ragToolNamesForType`、`sendUserMessage`、`registerTool`、`workerModeActivate`、`progress.md`。
- 只读 `python -c`：实跑 `test_autopilot_l0._parse_ts_allowlists()` 取改造前快照（未写盘）。
- 未改动任何仓库文件；唯一写入为本文件。

## 发现

### F1 `toolsForType` 的全部调用方（RQ-1）

`rg -n "toolsForType" packages/ -g '!dist' -g '!node_modules'` 共 6 处（不含注释）：

| 位置 | 用途 |
|------|------|
| `worker/worker-mode.ts:89-91` | 定义：`return TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? [];`（表 `:49-80`；`isRegisteredType` `:85-87` 独立使用表） |
| `rag/tools.ts:22` | import |
| `rag/tools.ts:402` | `rt === null` 分支 `pi.setActiveTools(toolsForType(type))` |
| `rag/tools.ts:406` | 非 null 分支 `pi.setActiveTools([...new Set([...toolsForType(type), ...ragToolNamesForType(rt,type)])])` |
| `test/suite/rag-research-doc.test.ts:37` | import |
| `test/suite/rag-research-doc.test.ts:107` | `expect(toolsForType("rag-research")).toEqual(RAG_RESEARCH_TOOLS)`（11 项、顺序精确） |

结论 A：**生产侧唯一消费者就是 `rag/tools.ts` 的两处**，无 PM 侧消费者。

结论 B（import 调整）：D-106 把 `:402/:406` 改为 `activeToolsForType` 后，`rag/tools.ts:22` 的 `toolsForType` import 变成未使用 → `npm run check` 会报未使用导入。该 import 应改为 `activeToolsForType`。但 `toolsForType` 本身**不能删除/改名**：
- `rag-research-doc.test.ts:37,107` 直接 import 使用；
- `test_autopilot_l0.py:292` 用源码子串断言 `"TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback"` 仍在 `worker-mode.ts` 中 → `toolsForType` 函数体必须逐字保留。

### F2 `applyRagTools` 的全部调用方与 PM 边界（RQ-2）

定义：`rag/tools.ts:400-407`。

生产调用方只有 1 处：`worker/worker-mode.ts:697-699`（`pi.on("before_agent_start", () => applyRagTools(pi, ragRuntime, meta.type))`），import 在 `:10`。

测试调用方：
- `rag-tools.test.ts:293,300,301`（type=coding）、`:305`（rag-research）、`:400`（`applyRagTools(pi, null, "coding")`，断言 active set 逐项等于 coding 白名单）；
- `rag-budget.test.ts:165`（rag-research）；
- `rag-research-doc.test.ts:120`（rag-research）、`:126`（coding/review/research/verifier/roadmap-writer，只断言「不含 rag_chat」）。

`:402` 与 `:406` 差异：
- `:402`（RAG disabled）：active = `toolsForType(type)`，纯白名单；
- `:406`（RAG enabled）：active = 白名单 ∪ 6 个 `RAG_BASE_TOOL_NAMES`（`rags_search…rag_feedback`，`rag/tools.ts:64-71`），仅 `rag-research` 额外含 `rag_chat`（`:387-390`，且 `:404` 先 `ensureRagChatTool` 注册，定义 `:361-385`）。

→ 两条分支**都必须**改用 `activeToolsForType`。只看 `:406` 会让 `rt === null` 的路径（无 RAG 配置的项目；以及所有 fixture——临时目录无 rag 配置，`registerRagTools` 在 `:191-193` 因 `enabled` 为空返回 null）拿不到窄工具，AC-007/VC-001 直接不成立。

PM 边界（AC-003/AC-007）：PM 模式只调用 `registerRagTools(pi, projectDir)`（`pm-orchestrator.ts:660-664`），`pm/*.ts` 内 `applyRagTools`/`setActiveTools`/`toolsForType` 全部零命中。`registerRagTools`（`rag/tools.ts:191-220` → `probeAndRegister` `:222-245` → `registerBaseTools`）只注册与探测，**不设置 active 集合**；`rag_chat` 的注册 `ensureRagChatTool` 只从 `applyRagTools:404` 可达。→ D-106 不改变 PM 的工具集合，AC-003/AC-007 的 PM 边界成立。

补充（既有行为，与本改动无关）：PM 注册的 RAG 基础工具会经 `registerTool → refreshTools` 自动进入 active 集合（见 F3）。

### F3 `setActiveTools` 其它调用点与确定性（RQ-3）

本 bundle（`agent-team-loop`）内 `pi.setActiveTools` 只有 `rag/tools.ts:402,406` 两处（`rg -n setActiveTools packages/coding-agent/src/extensions/agent-team-loop` 零其它命中）。

但 pi 核心有一条**自动增补**路径：
- `registerTool` → `runtime.refreshTools()`：`core/extensions/loader.ts:249-256`；
- post-bind 后 `refreshTools` = `_refreshToolRegistry()`：`core/agent-session.ts:2401`、`runner.ts:332-333`；
- `_refreshToolRegistry` 在无显式 `activeToolNames` 时，把**新注册的工具名追加进 active 集合**：`agent-session.ts:2527-2546`（`previousActiveToolNames` + `!previousRegistryNames.has(toolName)` 分支）。

影响判定：
1. 结构性 gating 仍然成立：只读角色注册 `worker_file` → 自动激活；有写角色不注册 → 不可能泄漏。
2. 但 `applyRagTools` 在每次 `before_agent_start` 重算并**覆盖**完整集合（`worker-mode.ts:692-699`），所以最终集合是确定性的。**VC-007 必须在 `before_agent_start` 之后断言**（现有范式：`autopilot-protocol.test.ts:252-253` 先 `worker.emit("before_agent_start")` 再读 `activeTools()`），否则会看到注册自动增补后的中间态。
3. `setActiveTools` 对未注册名字是忽略（`docs/extensions.md:2344`：「Names passed to `pi.setActiveTools()` must already be registered; unknown names are ignored.」）→ 即使注册被跳过（测试 fake 无 `registerTool`），`setActiveTools` 不会抛错；但**捕获式断言**会看到多出的 `worker_file`。
4. 真正会抛错的是**注册调用本身**：现有 4 个测试 fake 的 `pi` 没有 `registerTool`（见 F5），对只读类型激活 `workerModeActivate` 会 `TypeError`。

### F4 检查点分流的逐字基线（RQ-4）

`writeCheckpoint()` 位于 `worker-mode.ts:886-924`；机器证据写 trace.log 在 `:899-907`；steer 在 `:915-923`。

当前 steer（`:916-923`，占位符化还原；`${formatHeartbeatAge(x)}` 记作 `<AGE(x)>`，`${Math.round(elapsedMs/60_000)}` 记作 `<MIN(elapsedMs)>`）：

```
[mw checkpoint] 运行 <AGE(elapsedMs)>（总预算 <AGE(budgetMs)>）。请立即自评收敛性，把一行追加到 <path.join(taskDir,"progress.md")>：CKPT <MIN(elapsedMs)>m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。
```

deliverAs：`{ deliverAs: "followUp" }`（`:922`）。原因注释见 `:911-914`：agent mid-run 时裸 `sendUserMessage` 抛 "Agent is already processing"，`followUp` 作为独立 turn 排队（2026-09-09 smoke 验证）。

deadline steer（`:940-945`）基线：

```
[mw deadline] 预算还剩约 <AGE(budgetMs - steerAtMs(budgetMs))>。立即停止开始新工作：完成当前最小步骤后收尾，最终回复中列出已完成/未完成/后续建议（会被存为 output.md 摘要）。最终回复第一行必须是单行结论（状态 + 关键产出/卡点）。
```

deliverAs：`{ deliverAs: "steer" }`（`:944`，注释 `:938-939`：必须注入当前 turn）。

基线捕获方法与建议：
- **建议两分支都用 `followUp`**。两条检查点分支都从 `writeCheckpoint`（定时器）发出，mid-run「已在处理」约束完全相同；`steer` 只属于 deadline 分支。改 `deliverAs` 还会直接打破既有断言 `agent-team-loop.test.ts:4032`（`expect(ckpt?.options?.deliverAs).toBe("followUp")`，type=coding）。
- VC-004 的「coding 逐字相等」应在**渲染层**断言，不要在源码层 grep：用 `vi.useFakeTimers()` + 固定 `startedAt`（现有范式 `agent-team-loop.test.ts:4021-4035`），读 `sent.find(m => m.text.includes("[mw checkpoint]"))`，与**硬编码的、改造前渲染结果**逐字比较。反例：`grep` 模板字符串只能证明模板没变，不能覆盖 `formatHeartbeatAge`/`Math.round(ctx.ms/60_000)`/`path.join` 的运行时替换与空白；若实现把 `writeCheckpoint` 里的字符串拆成 helper 并改变拼接顺序，源码 grep 仍绿而输出已漂移。

### F5 parity/回归面（RQ-5）

**Python 断言集合**：
- `test_autopilot_l0.py:215-240`：`_parse_ts_allowlists()` 以正则 `const TOOL_ALLOWLISTS[^=]*=\s*\{(.*?)\n\};`（`:218`）解析 TS 源，`test_vc023_registry_parity` 只对 Python `REGISTRY` 的 **6 个 key** 做逐项保序相等（`:243-247`）；TS 侧**历史 bucket**（coding/review/research/fallback）只校验 key 存在（`:238-240`）与 `fallback == coding`（`:244-246`）。
  → **关键结论**：单改 `review`（或 research/coding）这一表项的**值**不会被任何现有 parity 用例抓住；「表不动」只有靠 VC-008 的全量快照才能锁。
- `test_autopilot_l0.py:292`：源码子串 `"TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback"` 必须仍在。
- `test_autopilot_l0.py:296-311`：当 `node_modules/vitest` 存在时**实跑** `test/suite/autopilot-protocol.test.ts` 并要求 exit 0；`:313-318` 还要求该测试文件含 `"fails closed"`、`"GC-8/AC-012"`、`"exactly equal to the Python REGISTRY"` 三个子串。→ 改该 TS 测试时必须保留这些子串。
- `test_autopilot_dispatch.py:36-68`：Python `REGISTRY`/`tool_set` 的元组断言（D-106 零改动，不受影响）。
- `test_rag_research.py:74-90`：复用 `_parse_ts_allowlists` 断言 rag-research 顺序精确；`:128-136` `test_autopilot_l0_is_byte_unchanged` 用 `git diff --stat -- test_autopilot_l0.py` 断言 L0 文件**逐字节未改**。

**会被 D-106 打破的既有 TS 测试（必须同步改）**：
1. `test/suite/autopilot-protocol.test.ts:203-207` 的 `fakeWorkerPi` **无 `registerTool`**；`:234-260` 对 verifier/reviewer 断言 `activeTools()` 与 `PY_REGISTRY` **逐项相等**；`:335-355` 对 manual review/research/verifier 断言等于 `PY_REVIEW_TOOLS`。这些类型都无 `write` → 注册 `worker_file` 触发 `pi.registerTool is not a function`（TypeError），且 active set 会多出 `worker_file`。→ 该文件必须加 `registerTool` stub，并把只读类型的期望集改为 `[...expected, "worker_file"]`（或改为先断言子集/再加新用例）。
2. `test/suite/dual-root-worker.test.ts:32-46`（fake 无 `registerTool`）+ `:74`（`type: verifier`）。
3. `test/suite/cross-drive-worker.test.ts:34-…`（fake 无 `registerTool`）+ `:153`（`type: verifier`）。
4. `test/suite/autopilot-read-scope.test.ts:407-412`（fake 无 `registerTool`）+ `:445`（`activateWorker` 固定写 `type: verifier`）。
   → 上面 3 个文件必须给 fake `pi` 补 `registerTool: () => {}`。

**不被打破的相邻测试（证据）**：
- `rag-tools.test.ts:400`：`applyRagTools(pi,null,"coding")` == coding 白名单 → coding 有 `write`，不含 `worker_file`，仍绿。
- `rag-tools.test.ts:293-305`、`rag-budget.test.ts:165`、`rag-research-doc.test.ts:120-130`：只断言 rag_chat 有无/是否含 rag_*，加 `worker_file` 不影响。
- `agent-team-loop.test.ts:2765-2780`（type=coding）、`:3880-3928` 的 `fakeWorkerPi`（只有 `on`/`sendUserMessage`，但所有 `startWatchdogTask` 都是 `type: coding`，`:3927/:3955/:3988/:4021`）、`agent-team-loop-output.test.ts:139`、`agent-team-loop-worker-tree-kill*.test.ts`（均 `type: coding`，`:286` 为 refused 类型）→ 不触达只读分支。
- `rag-required.test.ts:93`、`rag-e2e-slow.test.ts:82` 有 `registerTool` stub（且 rag-research 虽无 write，也不会 TypeError）。

**VC-008 的快照做法（可行方案）**：
- 现状：`TOOL_ALLOWLISTS` 未导出（`worker-mode.ts:49` 为 `const`），Python 侧靠解析源文本。改造前（2026-09-23）实跑 `_parse_ts_allowlists()` 得到 10 个 key 的精确快照（保序）：

```json
{
  "coding": ["read","write","edit","bash","find","grep","ls"],
  "review": ["read","find","grep","ls"],
  "research": ["read","find","grep","ls","bash"],
  "roadmap-writer": ["read","write","edit","find","grep","ls"],
  "phase-writer": ["read","write","edit","bash","find","grep","ls"],
  "verifier": ["read","find","grep","ls"],
  "reviewer": ["read","find","grep","ls"],
  "repair": ["read","write","edit","bash","find","grep","ls"],
  "rag-research": ["read","find","grep","ls","rag_search","rag_symbol","rag_graph","rag_impact","rag_sources","rag_feedback","rag_chat"],
  "fallback": ["read","write","edit","bash","find","grep","ls"]
}
```

- 方案：新增一个 Python 用例文件（例如 `packages/multi-workers/test_mwpp_collection_parity.py`），`from test_autopilot_l0 import _parse_ts_allowlists`（**复用共享 helper，不复制**；先例 `test_rag_research.py:22-23`），把上面的 10-key 字面量硬编码为期望值，断言 `_parse_ts_allowlists() == EXPECTED`。这同时覆盖 AC-008 的两个子句：值无漂移 + 「仍能解析 worker-mode.ts」（解析失败时 `_parse_ts_allowlists` 在 `:220`/`:229` 直接 assert）。
- 反例：
  1. 把快照断言写进 `test_autopilot_l0.py` → 被 `test_rag_research.py:128-136` 的「L0 逐字节未改」守卫否决。
  2. 在新文件里复制 `_parse_ts_allowlists` 实现 → 违反 `test_rag_research.py:22-23` 的「shared helper, never a copy」契约，正则一旦只改一处就出现假绿。
  3. 运行时从当前源码重新生成基线再比较（自比较）→ 同义反复，抓不到任何漂移。
  4. 只断言 6 个 REGISTRY key（现有 parity 的做法）→ 漏掉 legacy bucket（见上）；全量快照才有意义。

- TS 侧 VC-007「表不动」：不必导出表；对每个已登记 type 断言 `toolsForType(type)` 等于快照 + 断言 `activeToolsForType(type)` 组合关系，即可（沿用 `rag-research-doc.test.ts:107` 的既有 `toolsForType` 断言范式）。反例：为测试而把 `TOOL_ALLOWLISTS` 改成 `export const` 会新增一个无消费者的公开符号，且不能替代快照（导出的是运行值，快照锁的是契约）。

### F6 修正建议（RQ-6）

D-106 挂载点、D-104 判据在证据上**成立**（表可不动、生产侧仅 2 个调用点、PM 不受影响、解析正则对「表后新增函数」健壮）。需要补的修正：

1. **影响面遗漏（最重要，属 design/plan 的 VC-009 风险）**：design §3/§4 未列出会被 D-106 直接打破的 4 个测试文件与 1 个期望集用例（F5 第 1-4 条）。若不与实现同批更新，`test_autopilot_l0.py:296-311` 会因 vitest exit!=0 失败，VC-008/VC-009 均不成立。必须纳入实施任务：给 `dual-root-worker.test.ts` / `cross-drive-worker.test.ts` / `autopilot-read-scope.test.ts` / `autopilot-protocol.test.ts` 的 fake `pi` 补 `registerTool` stub，并把只读类型的 active set 期望改为含 `worker_file`（保留 `test_autopilot_l0.py:313-318` 的三个子串）。
2. **断言时机**：VC-007 必须在 `before_agent_start` 之后断言最终集合（`registerTool → refreshTools → agent-session.ts:2527-2546` 会在注册时先自动增补），与 `autopilot-protocol.test.ts:252-253` 的既有范式一致。
3. **注册点精确化（替代挂载点）**：design 写「`:667-672` 附近」。精确锚点：`workerTaskDir` 在 `worker-mode.ts:667`，`registerRagTools` 的 `try` 块在 `:668-677`。建议把 `registerWorkerFileTool` 放在 **`:677`（try/catch 之后）与 `:697`（`before_agent_start` 之前）之间**——放在 `:668-676` 的 try 内会因 RAG 配置抛错被 catch 跳过（catch 只记日志、流程继续），从而让「RAG 配置坏掉」的只读 worker 丢掉落盘通道。判据 `toolsForType(meta.type).includes("write")` 在模块作用域可直接调用（`:89`），无需新参数。
4. **import 调整**：`rag/tools.ts:22` 改为 `import { activeToolsForType } from "../worker/worker-mode.ts";`（F1 结论 B）。
5. **D-104 judge 的抽样**：`rag-research` 也是无 `write` 类型，会同样获得机器行与只读 steer。AC-001 枚举 `review/research/verifier/reviewer` 用「（…）」形式，属可接受超集；无需额外 gate，但测试的 type 矩阵应含 `rag-research` 以防漏测。

## 结论 → 决策映射

| 发现 | 影响决策/VC | 结论 |
|------|-------------|------|
| F1（仅 2 个生产调用点；`toolsForType` 必须逐字保留；import 需切换） | D-106 / VC-007 / AC-007 | 成立；`activeToolsForType` 走表外，不动 `TOOL_ALLOWLISTS`，`toolsForType` 函数体与导出保持不变 |
| F2（`applyRagTools` 单调用方；`:402`/`:406` 都要改；PM 不调用 applyRagTools） | D-106 / AC-003 / AC-007 | 成立；把 `:402` 与 `:406` 一起改用 `activeToolsForType`，PM 边界确认无影响 |
| F3（唯一显式 setActiveTools 在 rag/tools.ts；核心有 registerTool 自动增补） | VC-004 / VC-007 | 最终集合由 `before_agent_start` 重算保证确定性；断言须在该事件后取值 |
| F4（steer 基线文本 + deliverAs） | D-104 / VC-004 / AC-004 | 两分支均 `followUp`；deadline 保持 `steer`；VC-004 用渲染层硬编码基线断言 |
| F5（parity 面；4+1 测试需同步改；legacy bucket 仅快照可锁） | VC-008 / AC-008 / VC-009 / AC-009 | 快照方案 = 复用 `_parse_ts_allowlists` 的新 Python 用例 + 硬编码 10-key 字面量；不得改 L0 文件 |
| F6-1/2/3/4/5 | design §3/§4、plan/任务拆分 | **与 design 的差异**：design 遗漏了 4 个 fake-pi 测试文件与 1 个期望集用例的同步修改，且注册点应精确到 `:677`~`:697`（outside RAG try/catch） |

**与 design 的差异/修正建议汇总**：D-104/D-106 的技术选择（表外集合、结构性 gating、仅无写角色写机器行）经证据核实成立，无需替代挂载点；但 design/plan 必须补上 F5 列出的测试同步面（否则 VC-008/VC-009 不可能通过），并把窄工具注册点明确落在 `worker-mode.ts:677-697`、断言时机明确在 `before_agent_start` 之后、VC-004 的「逐字基线」明确为渲染层硬编码比较。
