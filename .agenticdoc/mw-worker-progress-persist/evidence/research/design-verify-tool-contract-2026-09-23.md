# Research: 窄工具契约可落地性（design）

## 决策问题

RQ-D1：design 的「窄工具」契约（D-101/D-102/D-105/D-107/D-109、§4.1、VC-005/VC-006）在 pi 扩展 API 层面是否可落地、可测？逐条核实并指出不成立/需修正之处：

1. `pi.registerTool` 的 `ToolDefinition` 完整类型与 `execute` 返回值；工具执行失败如何表达；`tool_execution_end` 的 `event.isError` 由什么决定；「非法 file 值」应如何返回才能满足 VC-006（返回错误且不写盘）。
2. TypeBox `Type.Object` 参数是否在进入 `execute` 前被 pi 校验（非法类型/额外字段）；字符串 `pattern` 是否被 API 层强制；正则校验放 schema 还是 execute。
3. `fs.appendFileSync`/`writeFileSync` 在 Windows 上同目录并发/句柄行为是否有先例或已知问题；64 KiB 上限应在哪一层做。
4. 工具名 `worker_file` 与既有命名规范是否冲突；`label`/`description`/`promptGuidelines` 是否有前缀要求（如 `RAG_PROMPT_GUIDELINES`）。
5. 把结果落成「最终实现契约」，与 design D-101/102/105/107/109 的差异逐条列出。

## 调研方法与出处

- 源码整段 `read`：
  - `packages/agent/src/types.ts`（`AgentToolResult` `:355-368`、`AgentTool` `:378-406`）
  - `packages/agent/src/agent-loop.ts`（`prepareToolCall` `:600-661`、`executePreparedToolCall` `:666-706`、`finalizeExecutedToolCall` `:716-756`、`emitToolExecutionEnd` `:763-771`）
  - `packages/ai/src/utils/validation.ts`（`validateToolArguments` `:285-322`）
  - `packages/coding-agent/src/core/extensions/types.ts`（`ToolDefinition` `:449-489`、`registerTool` `:1246-1248`、`setActiveTools` `:1337`）
  - `packages/coding-agent/src/core/tools/tool-definition-wrapper.ts`、`core/extensions/wrapper.ts`（注册工具到 AgentTool 的适配）
  - `packages/coding-agent/src/core/agent-session.ts`（`afterToolCall`/`tool_result` `:501-534`、`_normalizePrompt*` `:999-1019`、系统提示聚合 `:1021-1045`）
  - `packages/coding-agent/src/core/extensions/runner.ts`（`emitToolResult` `:876-931`）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（全文；`toolTarget` `:333-345`、`tool_execution_start/end` `:770-790`）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（当前工作区版本；`formatMachineCheckpoint` `:220-229`、`appendProgressLine` `:231-235`）
  - `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts`（注册范式 `:246-385`、`failResult` `:167-169`、`applyRagTools` `:400-407`）
  - `packages/coding-agent/src/extensions/agent-team-loop/rag/guidelines.ts`
  - `packages/coding-agent/src/core/extensions/loader.ts`（`registerTool` `:249-256`）
  - `.agenticdoc/mw-worker-progress-persist/tasks/T-2-WORKER-FILE-TOOL.md`
- `rg -n` 定界：`registerTool`、`name:`、`label:`、`promptSnippet`、`promptGuidelines`、`isError`、`appendFileSync`/`writeFileSync`、`progress.md`、`--tools`。
- 只读 `node --input-type=module` 探针（TypeBox 实跑，不落盘）：`Type.Object` 的 IR、`Compile(...).Check` 对 `pattern`/`required`/`Literal`/`maxLength`/`additionalProperties` 的强制行为、`Value.Convert` 是否套用 `default`。
- 未改动任何仓库文件；唯一写入为本文件。

## 发现

### F1 工具定义与错误语义（RQ-1）

**`ToolDefinition` / `execute` 返回值**。`ToolDefinition<TParams,TDetails,TState>` 定义在 `core/extensions/types.ts:449-489`：必填 `name`/`label`/`description`/`parameters`，可选 `promptSnippet`（`:457`）/`promptGuidelines`（`:459`）/`constrainedSampling`/`renderShell`/`prepareArguments`/`executionMode`（`:477`）/`renderCall`/`renderResult`；`execute` 返回 `Promise<AgentToolResult<TDetails>>`（`:481-486`），签名 `(toolCallId, params, signal, onUpdate, ctx)`。`pi.registerTool` 见 `:1246-1248`。

**`AgentToolResult` 没有 `isError` 字段**。定义在 `packages/agent/src/types.ts:355-368`，字段只有 `content`、`details`、`usage?`、`addedToolNames?`、`terminate?`。`AgentTool.execute` 的注释直接规定（`:388`）：**"Throw on failure instead of encoding errors in `content`."** 适配层 `wrapToolDefinition`（`core/tools/tool-definition-wrapper.ts:9-20`）与 `wrapRegisteredTool`（`core/extensions/wrapper.ts:17-40`）原样透传 `execute` 的返回值，不做任何 `isError` 解释。

**`event.isError` 的唯一判定链**（`packages/agent/src/agent-loop.ts`）：
- `executePreparedToolCall`（`:666-706`）：正常 `return` → `{ result, isError: false }`（`:677-678`）；**`execute` 抛异常 → `catch` → `createErrorToolResult(msg)` + `{ isError: true }`（`:696-704`）**。
- `prepareToolCall`（`:600-661`）：schema 校验失败、工具不存在、`tool_call` 处理器返回 `{block:true}` —— 均在 `execute` 之前进入 `immediate` 分支，`isError: true`（`:654-660`）。校验调用点在 `:617-618`。
- `finalizeExecutedToolCall`（`:716-756`）：`afterToolCall`（即扩展的 `tool_result`）可以覆写 `isError`（`:719-747`）。
- 最终 `emitToolExecutionEnd` 把 `isError` 放进 `tool_execution_end` 事件（`:763-771`）。
- 编码 agent 侧：`agent-session.ts:501-534` 把 `tool_result` 挂到 `afterToolCall`；`runner.ts:876-931` 允许处理器写 `isError`。但 `tool_result` 在 `execute` 之后触发，**对「拒绝写入」无意义**。
- worker 侧消费者：`worker-mode.ts:770-784` 对每个 `tool_execution_start` 写 `[TOOL]`；`:786-790` 只在 `event.isError` 时写 `[TOOL_ERR]`。

**反例（不要模仿）**：RAG 工具把错误编码进正常结果（`rag/tools.ts:167-169` `failResult` → `{content, details}`），因此 `isError` 恒为 false，永不产生 `[TOOL_ERR]`。若 `worker_file` 照此返回 `{ok:false,reason}`，VC-006 的「返回错误」与 D-109 的拒绝留痕都不成立。

**VC-006 确定结论**：`execute` 内部必须**抛 `Error(reason)`**（由 agent loop 捕获，不是未捕获异常）。抛出的 message 成为工具结果 content 且 `isError=true` → `tool_execution_end` → `[TOOL_ERR] worker_file <首行>`；`execute` 在抛之前不得调用任何写盘。schema 的 `pattern` 会在真实运行里先一步拒绝，也产生 `isError=true`（`prepareToolCall` 分支）→ 两条路径都满足 VC-006，且都**不写盘**。

### F2 参数校验时机（RQ-2）

**pi 确实在进入 `execute` 前校验参数**。`agent-loop.ts:617-618` 调用 `prepareToolCallArguments` + `validateToolArguments`；后者在 `packages/ai/src/utils/validation.ts:285-322`：`Value.Convert(tool.parameters, args)`（`:287`）后 `Compile(tool.parameters).Check(args)`（`:304`），失败 `throw new Error("Validation failed for tool …")`（`:316`）。该 throw 被 `prepareToolCall` 的 catch 转成 `isError` 结果（`agent-loop.ts:654-660`），`execute` 不被调用。

**TypeBox 实跑结论**（本机 `typebox@1.3.7`，与仓库依赖一致）：
- `pattern` **被强制**：`Type.String({pattern:"^(a|b)$"})` 对 `"z"` Check=false。
- `required`、`Literal` 联合 **被强制**。
- `maxLength` **被强制**（65536 通过、65537 失败），按 **UTF-16 code unit** 计数。
- `Type.Object({...})` **默认不拒绝额外字段**（`additionalProperties` 未写入 IR）；显式 `Type.Object({...}, {additionalProperties:false})` 才拒绝（实测 extra prop Check=false）。
- `Value.Convert` **不套用 schema `default`**（实测缺 `mode` 时 `converted` 无 `mode`），所以「默认 append」必须在 `execute` 里 `params.mode ?? "append"`。
- 12 项非法 `file` 用 D-102 正则（见 F5）在 validator 层全部 `Check=false`；合法 `progress.md`/`report.md`/`report-f1.md` 通过，`report.r1.md` **不通过**（见 F5 差异）。

**测试层面的关键事实**：既有单元测试 `tool.execute(...)` **直接调用**，绕过 schema 校验 —— 见 `packages/coding-agent/test/extensions/agent-team-loop.test.ts:202-217`（fake `pi.registerTool` 只把 tool 塞进 Map）与 `:797`/`:4792` 等直接调用点。因此 **execute 内的 `isAllowedWorkerFile` 守卫是 VC-006 单测可测性的必要条件**。

**确定结论**：正则**两处都要**——① schema `pattern`（真实运行时在 execute 前拒绝，且可被 provider 看到；满足 VC-006「不写盘」）；② `execute` 内 `isAllowedWorkerFile` 守卫（权威判据、单测可直调、可给出结构化 `reason`、防 `prepareArguments` 等前门）。单一来源：用 `WORKER_FILE_NAME_RE.source` 生成 schema pattern，避免两处正则漂移（P-005 同族）。

### F3 写入实现与 64 KiB 层（RQ-3）

**Windows 写入先例**：
- 同目录追加：`output-writer.ts:91-109`（trace.log）、`:231-235`（progress.md）、`worker-mode.ts:377-384`/`:421-433` 都用 `fs.appendFileSync`。这是 worker 进程内唯一写者，Node 单线程 + 同步调用 → 定时器机器行与工具调用**不可能交错**。
- 整文件重写：`output-writer.ts:44-88`（`writeFileSync` + D-117 合并）、`rag/budget.ts:222-226`（worker 目录内 `writeFileSync` 整文件）→ `mode:"write"` 用 `writeFileSync` 与现状同源，无新增 Windows 风险。
- 跨进程：launcher 以 `"wb"` 打开并持有 **worker.log** 句柄（`launcher.py:952-966`），并把子进程 stdout/stderr 重定向进去；`worker_file` 的目标是**同目录的另一个文件**（progress.md/report*.md），不构成共享冲突。launcher 的其它写（`:66-67`/`:82-83`/`:691-692`）也是 append，位于别的目录。
- 未发现 `EBUSY`/`EPERM`/共享冲突类既有缺陷记录；`_pitfalls.md` 与写入相关的只有 P-003（`open(p,"w")` 先截断后求值，`:24-30`），其规避是「先算后写」或 tmp+rename。`worker_file` 的拒绝路径在任何 `fs.*` 调用之前返回/抛错，P-003 不适用。设计已声明「PM 代记发生在 worker 结束后」，跨进程并发不在契约内（如要更硬，可对 `mode:"write"` 用 tmp+rename，`budget.ts` 外的 `ack-store.ts:63`/`index-store.ts:160` 有先例）。

**64 KiB 应在哪一层**：
- 表达不了字节语义：TypeBox `maxLength` 计 code unit，`64*1024` 个中文字符 ≈ 192 KiB 字节 → 单纯 `maxLength` 会漏拦。
- **确定结论**：权威检查放 `execute`/`writeWorkerFile`，用 `Buffer.byteLength(content, "utf8") > WORKER_FILE_MAX_BYTES` → 返回 `{ok:false, reason}` 并由 execute 抛错，**拒绝而非截断**（静默截断会毁掉 worker 结论）。schema 可选加一个 `maxLength` 作为便宜的前置门（注意单位差异），不作为唯一判据。T-2 已指定 `Buffer.byteLength`，与结论一致。

### F4 命名与可见性（RQ-4）

**工具名清单**（`rg -n 'name:'`）：
- 内置：`read` `read.ts:210`、`write` `write.ts:187`、`edit` `edit.ts:293`、`bash` `bash.ts:348`、`ls` `ls.ts:101`、`grep` `grep.ts:129`、`find` `find.ts:124`。
- RAG：`rag_search`/`rag_symbol`/`rag_graph`/`rag_impact`/`rag_sources`/`rag_feedback`/`rag_chat`（`rag/tools.ts:247-367`）。
- PM（`ui-bridge.ts`）：`mw_status:810`、`dispatch_worker:967`、`ack_worker_result:1129`、`list_tasks:1157`、`switch_key:1189`、`advance_phase:1262`。
- **无 `worker_file` 或 `worker_*` 冲突**；命名风格统一为 lowercase snake_case（多词用 `_`）。PM 与 worker 模式互斥注册（`index.ts:52-56`：有 `PI_WORKER_TASK` 只走 `workerModeActivate`，否则 `pmActivate`），因此 `worker_file` 不会与 PM 工具同会话出现。`registerTool` 不做名字格式校验（`loader.ts:249-256`）。

**label / description / promptGuidelines 无强制前缀**：
- 内置 `label` == 工具名（`read.ts:211` 等）；RAG `label: "RAG search"`（`rag/tools.ts:248` 等）；PM `label` == 工具名（`ui-bridge.ts:811` 等）。三种风格并存 → `label: "worker_file"` 或 `"Worker file"` 均可。
- `RAG_PROMPT_GUIDELINES`（`rag/guidelines.ts:11-15`）只是 RAG 七个工具**共享**的三行文案；框架不做前缀包装。`promptGuidelines` 在 `agent-session.ts:1008-1019` 去重后，`:1033-1036` 把所有 active 工具的 guideline **拼接进一个全局 Guidelines 段**（无 per-tool 前缀）→ 文案必须自洽（写明 `worker_file`）。
- `promptSnippet`（`types.ts:457`）在 `agent-session.ts:1040-1043` 进入 Available tools 段；内置工具都有，RAG 工具**都没有**。因此「窄工具不写 snippet」与 RAG 先例一致、不影响 provider 侧工具可见性（工具本体仍在请求里）；若要提升自发现性，建议补一条 snippet（非必需）。

### F5 最终实现契约（RQ-5）

> 注：与 design 不同，`formatMachineCheckpoint` / `appendProgressLine` **已在本工作区落地**（`output-writer.ts:220-235`），签名与 D-105/D-107 一致；下面只覆盖窄工具面。

```ts
// packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts
export const WORKER_FILE_TOOL = "worker_file";
export const WORKER_FILE_MAX_BYTES = 64 * 1024;
export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report-[a-z0-9][a-z0-9._-]{0,40}\.md)$/; // 单一来源
export type WorkerFileMode = "append" | "write";

export function isAllowedWorkerFile(name: string): boolean; // WORKER_FILE_NAME_RE.test(name)

export function writeWorkerFile(
  taskDir: string,
  file: string,
  content: string,
  mode: WorkerFileMode,
): { ok: true; path: string; bytes: number } | { ok: false; reason: string };
// 顺序：isAllowedWorkerFile → Buffer.byteLength 上限 → mkdirSync(dir,{recursive:true}) → 写盘
// 拒绝路径：任何 fs 调用之前 return {ok:false}（不建目录、不建文件、不截断，P-003）

export function registerWorkerFileTool(pi: ExtensionAPI, taskDir: string): void;
```

注册 schema（`WORKER_FILE_NAME_RE.source` 复用正则，`additionalProperties:false` 可选但建议）：

```ts
parameters: Type.Object(
  {
    file: Type.String({ pattern: WORKER_FILE_NAME_RE.source, description: "Basename only: progress.md | report.md | report-<slug>.md" }),
    content: Type.String({ minLength: 1, description: "Text to write (max 64 KiB UTF-8)" }),
    mode: Type.Optional(Type.Union([Type.Literal("append"), Type.Literal("write")])),
  },
  { additionalProperties: false },
),
executionMode: "sequential", // 可选，写者语义；execute 内无 await，默认并行也无竞态
execute: async (_toolCallId, params) => {
  const mode = params.mode ?? "append";            // schema default 不被 Value.Convert 套用
  const r = writeWorkerFile(taskDir, params.file, params.content, mode);
  if (!r.ok) throw new Error(`worker_file rejected: ${r.reason}`); // 唯一正确的失败形状
  return { content: [{ type: "text", text: `wrote ${r.bytes} bytes to ${r.path} (${mode})` }], details: {} };
}
```

- **错误形状**：`execute` 抛 `Error`（agent loop 捕获 → `isError=true` → `[TOOL_ERR]`）。**不要** `return {isError:true,...}`（类型上不存在，运行时被忽略，isError 仍 false），也**不要**照 RAG 的 `failResult` 把错误编码进 content（isError=false，无 `[TOOL_ERR]`）。
- **`[TOOL]`/`[TOOL_ERR]` 行**：`tool_execution_start` 在 prepare 之前发出（`agent-loop.ts:446-452`），所以被拒调用也会先有一条 `[TOOL] ts worker_file`（无 target，见差异 9），随后 `[TOOL_ERR] ts worker_file <reason 首行>`。与 read-scope 拦截的既有双行行为一致。
- **正则最终形式**：`/^(?:progress\.md|report\.md|report-[a-z0-9][a-z0-9._-]{0,40}\.md)$/`（若要覆盖 T-2 的 `report.r1.md` 合法用例，改首段为 `report[-.]`，见差异 2）。无 `g` 标志（避免 `.test` 的 `lastIndex` 状态）；`$` 在 JS 无 `m` 标志下不匹配尾部换行，故 `"progress.md\n"` 被拒。

## 结论 → 决策映射

| 发现 | 影响决策/VC | 结论 |
|------|-------------|------|
| F1（`AgentToolResult` 无 `isError`；只有 throw/block 能置 `event.isError`；loop 捕获 throw） | D-109 / VC-005 / VC-006 / AC-006 | **修正**：失败必须 `execute` 抛 `Error(reason)`；design D-109 的「execute 返回 isError 结果」不成立 |
| F2（pi 在 execute 前用 TypeBox `Compile.Check` 校验；`pattern` 强制、额外字段默认不拒；单测直调 execute 绕过 schema） | D-102 / VC-006 / AC-006 | 正则放 **schema + execute 两处**，以 `WORKER_FILE_NAME_RE.source` 为单一来源；`additionalProperties:false` 可选 |
| F3（appendFileSync 有先例且进程内单写者；P-003 规避 = 先算后写；`maxLength` 是 code unit） | D-101 / D-107 / VC-005 | 拒绝路径在 fs 前完成；64 KiB 用 `Buffer.byteLength` 在 execute 拒绝（不截断） |
| F4（无命名冲突；无 label/guideline 前缀要求；RAG 无 promptSnippet 先例） | §4.1 | `worker_file`/snake_case 可用；snippet 可选，guideline 文案需自洽 |
| F5（最终契约） | D-101/102/105/107/109、T-2 | 见上；与 T-2 的 `writeWorkerFile` 纯函数 + execute 抛错组合一致 |

**与 design 的差异/修正建议**

1. **D-109 错误形状（必须改）**：design 写「`execute` 返回 `isError` 结果」——`AgentToolResult` 无该字段，实际会被忽略、`isError=false`、无 `[TOOL_ERR]`。改为：`execute` 在 `writeWorkerFile` 返回 `{ok:false,reason}` 时 `throw new Error(reason)`（loop 捕获，非未捕获异常）。T-2「不得抛未捕获异常」按此解读即成立。
2. **D-102 正则与示例矛盾（必须二选一）**：`report-[a-z0-9]…` 不匹配 D-102 的示例 `report.r1.md`，也不匹配 T-2 验收清单里的 `report.r1.md` 合法用例（实测 validator Check=false）。建议放宽为 `report[-.][a-z0-9][a-z0-9._-]{0,40}\.md`（仍拒绝 `report..md`），或从 D-102/T-2 删掉 `report.r1.md`。否则 T-2 的「合法路径」用例必红。
3. **D-101 未指定校验层**：补一句「正则单一来源 `WORKER_FILE_NAME_RE`，schema 用 `.source` 引用，execute 用同一正则守卫」。
4. **§4.1 schema 缺 `additionalProperties:false`**：设计未提；TypeBox 默认放行额外字段（实测），建议补上以收紧契约。
5. **§4.1 未提 `promptSnippet`**：RAG 工具也无 snippet，属可选；建议补一条，否则 Available tools 段缺该工具（不影响 provider 工具可见性）。
6. **`mode` 默认值必须在 execute 落地**：`Value.Convert` 不套用 schema `default`（实测），不能依赖 schema。
7. **D-108 语义副作用（设计决策，需确认）**：`worker_file` 不计入 `WRITE_TOOLS`，所以只读角色即便用 `mode:"write"` 落了报告，`writes` 仍为 0、`computeRisk` 会判 `high`（`worker-mode.ts:886-926` + `risk` 规则）。「零产出」信号因此会把「有报告落盘」也标成 high。若要区分，建议单独计数（如 `workerFileWrites`）而不是并入 `writes`。
8. **D-105/D-107 已实现**：`output-writer.ts:220-229`（`formatMachineCheckpoint`，字段序与 D-105 逐字一致）与 `:231-235`（`appendProgressLine(taskKey, agenticdocRoot, line)`，签名与 D-107 一致）。design §3 把它们列为「(改)」属预期；实现时不要重复造第二套格式化。
9. **`[TOOL] worker_file` 无 target（可选）**：`toolTarget`（`worker-mode.ts:333-345`）只读 `path`/`command`/`pattern`/`query`，不读 `file`，故 trace 行只有工具名。若要留证目标文件名，可把 `file` 加入取值链（对现有工具无影响）。
10. **注册点**：与并行 RQ-D2 结论一致——`registerWorkerFileTool` 应落在 `worker-mode.ts` 的 RAG `try/catch` **之后**、`before_agent_start` **之前**（即 `:677`~`:697` 区间），避免 RAG 配置抛错时把窄工具一并吞掉；结构性 gating 用 `toolsForType(meta.type).includes("write")`（`:89`）。
11. **VC-006 覆盖方式**：因单测直调 `execute`（绕过 schema），必须同时保留 execute 内守卫；12 项反例在 validator 层与 execute 层都实测为拒（F2/F5），满足「全部返回错误 + 目录文件集合不变」。
12. **跨引用**：`worker-file-tool.ts` 的写入应直接 `path.join(taskDir, file)`（basename-only，构造上无路径解析，P-004 不适用），不要复用 `appendProgressLine` 的 `outputDir(taskKey, agenticdocRoot)` 派生（两者目录推导路径不同，混用会引入第二处目录来源）。
