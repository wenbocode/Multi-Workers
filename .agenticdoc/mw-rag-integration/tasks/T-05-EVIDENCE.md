# Task T-05-EVIDENCE: 证据行 / 熔断 / 预算（并发预留）/ 全类心跳

## 基本信息
- Stage: 3
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-007, AC-008, AC-009, AC-012, AC-013, AC-016]
- vc_refs: [VC-010, VC-011, VC-012, VC-013, VC-016, VC-017, VC-021, VC-025]
- pattern_refs: []

## 描述

- **`[VERIFY]` 行的发射通道（血泪教训，T-02/T-12 各踩一次）**：本仓库 vitest 配置为 `silent: "passed-only"`，**绿灯用例里的 `console.log` 会被吞掉**，证据行在必跑命令的输出里根本看不见（T-11 采集不到）。必须用 `process.stdout.write("[VERIFY] ...\n")`（末尾自带换行）。Python 侧 `print` 正常，但需 `pytest -q -s` 才显示。

- **T-04/T-13 交接（已就位，直接消费）**：
  - `rag/tools.ts` 的 `registerRagTools(pi, projectDir, hooks?)` 第三个参数 `RagRuntimeHooks` 就是你的接线口；`RagBudgetOps` / `RagBreakerOps` 是 T-04 预留的结构化接口，当前 `runtime.budget`/`breaker` 为 `null`，调用链里 `reserveChat`/`checkWall`/`accumulate`/`settleChat`/`isOpen`/`noteFailure`/`noteSuccess` 的调用点都已存在，缺的只是真实实例。
  - **一次逻辑工具调用 = 一次预算/熔断/心跳**：T-13 后 `rag_sources` 会发两次 HTTP（`list_sources`+`list_collections`）但只算一次逻辑调用；证据行与预算计数都以**逻辑名**为准。
  - 证据行必须同时记两个名字：`tool=<逻辑名>` 与 `mcp_tool=<实际发出名>`（T-13 已把实际名放进 `RagEnvelope.mcp_tool`，多腿用 `+` 连接），否则审计时无法核对映射是否生效。
### 源码

1. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/evidence.ts`：

```ts
export function ragCallLine(e: { server: string; tool: string; via: "mcp" | "cli"; ms: number; results: number }): string;
export function appendEvidence(taskDir: string, line: string): void;      // 包装既有 output-writer.ts::appendTrace（带时间戳），不新造 trace 写手
export const RAG_FALLBACK = "rag_fallback"; export const RAG_UNAVAILABLE = "rag-unavailable";
export const RAG_REWRITE_DEGRADED = "rag-rewrite-degraded"; export const RAG_REQUIRED_MISSING = "rag-required-missing";
export function redactSecrets(text: string, tokenEnvNames: string[]): string;   // 把所有 token env 的**当前值**替换为 "<redacted>"
```

行格式（机器判据，正则必须精确匹配）：
`rag_call server=<S> tool=<T> via=(mcp|cli) ms=<N> results=<N> mcp_tool=<M>`；兜底为 `rag_fallback server=<S> tool=<T> via=cli reason=connect`。
`results` 语义：列表类 = `items.length`；`rag_impact` = `meta.affected_files.length`；`rag_sources` = `items.length`；`rag_feedback` = 0（无列表）。

2. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/budget.ts`：

```ts
export interface BudgetState { chatUsed: number; chatBudget: number; timeUsedMs: number; timeBudgetMs: number }
export class Budget {
	constructor(workerTaskDir: string | null, chatBudget: number, timeBudgetMs: number, opts?: { taskWallMs?: number | null; now?: () => number });
	readonly startedAt: number;
	reserveChat(): { ok: true } | { ok: false; kind: "budget"; message: string };   // **await 之前同步递增**（并发安全）
	settleChat(ok: boolean, kind: RagErrorKind | null): void;                       // connect 失败返还；timeout 不返还
	accumulate(ms: number): void;
	checkWall(nowMs: number): { ok: true } | { ok: false; kind: "budget"; message: string };   // 已用 > 70% 墙钟
	canCallCheap(): boolean;
	persist(): void;   // 仅当 workerTaskDir 非 null；读-改-写整个 JSON（先算后写）
}
export class Breaker {                       // 只计 connect/timeout/protocol
	noteFailure(server: string, kind: RagErrorKind): void;
	isOpen(server: string): boolean;         // 连续 3 次 → true，之后同 (worker, server) 不再发请求
	noteSuccess(server: string): void;
}
export function withHeartbeat<T>(intervalMs: number, onUpdate: ((m: string) => void) | undefined, fn: () => Promise<T>): Promise<T>;
```

要点：
- `withHeartbeat` 默认 30s；`onUpdate` 触发 host 的 `tool_execution_update` → worker `touch()`（`worker-mode.ts:556/576`）——**所有可能长耗时的调用都必须包它**（不只 `rag_chat`），否则 idle 看门狗误杀。
- 预算持久化：`<worker task dir>/rag-budget.json`（仅在**首次 RAG 调用**时创建，D-014）；`reserveChat` 是同步函数（先递增再 `await` 网络），保证并发两次调用不会都拿到最后一个额度。
- 累计时间：每次调用 `accumulate(elapsedMs)`；`timeUsedMs > timeBudgetMs` → 后续调用 `kind="budget"`（VC-025）。

3. 接线（`rag/tools.ts` 调用序）：
   `breaker.isOpen` → `capabilityError` → `budget.reserveChat`（chat） / `budget.checkWall`（chat） → `withHeartbeat` → 传输 → `budget.settleChat` + `budget.accumulate` + `appendEvidence(ragCallLine)`。
   兜底策略（D-005）在传输失败后判定：**仅当** `kind === "connect"`（可证未送达）**且**工具只读（非 `rag_feedback`、非 `rag_chat`）才走 cli 兜底并写 `rag_fallback`；`timeout` / 写操作 / 昂贵调用一律直接上抛 + 写 `rag-unavailable`。

### 测试

- `packages/coding-agent/test/suite/rag-evidence.test.ts`
  - **六类各一行（VC-011）**：对六工具各成功调用一次 → trace 增量中每类各一行匹配 `^rag_call server=\S+ tool=<t> via=(mcp|cli) ms=\d+ results=\d+ mcp_tool=\S+$`；`rag_impact` 的 `results` === `affected_files.length`。
  - **熔断（VC-010）**：fixture `failNext(1..3, "reset")` → 第 4 次调用返回 `kind==="circuit"` 且 fixture 计数增量 === 0；再做两次 `capability` 拒绝后 mcp 调用仍成功（不计入熔断）。
  - **兜底限制（VC-012）**：`transport: skill` 成功 → 仅 `rag_call via=cli`、无 `rag_fallback`；`both` + fixture `failNext(1,"reset")` → `rag_fallback` + `via=cli`；`both` + `rag_feedback` 连接失败 → 无兜底、fixture 请求尝试数 === 1；`dropAfterDelivery`（timeout）→ 无兜底。
  - **token 脱敏（VC-013）**：`process.env.OVERCODE_MCP_TOKEN = "SECRET123"`、配置仅含 `tokenEnv` → 生成的 trace 行、错误消息、`detail` 中 `SECRET123` 命中 0（`redactSecrets` 生效）。
  - **降级增量（VC-021）**：fixture `rewriteDegraded: true` → 结果 `meta.rewrite_degraded === true` 且本次调用前后 trace 增量含 `rag-rewrite-degraded`；正常 fixture → 增量不含该行（**不做全文件断言**）。
- `packages/coding-agent/test/suite/rag-budget.test.ts`
  - **顺序预算（VC-016）**：`chatBudget=2` → 第 3 次拒绝且消息含 `used=2`，fixture chat 计数 === 2。
  - **并发预留（VC-016）**：剩 1 额度时 `Promise.all([call(), call()])`（fixture `delayMs=200`）→ 恰一次被拒，fixture chat 计数 === 1。
  - **心跳（VC-017 L1）**：注入 `now`/interval（如 20ms）断言 `onUpdate` 调用 ≥ 4 次且相邻间隔 < 60s 语义（用假时钟计数，不实跑 180s）。
  - **累计预算与墙钟（VC-025）**：`timeBudgetMs` 先耗尽 → 新调用 `kind==="budget"` 且消息含累计值；`taskWallMs` 已知时超过 70% → `rag_chat` 被拒而 `rag_search`（cheap）仍可用。
  - **结算语义**：`connect` 失败返还额度，`timeout` 不返还。

### 注意

- 证据行必须**只追加**（P-001：复用 `output-writer.ts::appendTrace`，绝不 `writeFileSync` 覆盖）；`rag-budget.json` 是"先算后写"（读-改-写整体）。
- **T-03 交接（直接复用，不要重新发明）**：四类错误的构造方式（`connect` = 关端口/`failNext("reset")`；`timeout` = `delayMs` 或 `dropAfterDelivery`；`protocol` = `failNext("500")`/缺 session/401；`tool` = handler 抛错或 `isError`）见 `workers/mw-rag-t03-transport/output.md` 表格；fixture 的 `calls[]` 记录每次请求（含失败尝试），"零请求"断言用 `calls.length` 增量；`RagErrorKind` 从 `adapter.ts` 取（`mcp-client.ts` re-export）。
- `ms` 用 `Date.now()` 差（整数），`results` 必须是非负整数——gate/audit 会按正则解析。
- 测试运行：coding-agent 包根 `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-evidence.test.ts test/suite/rag-budget.test.ts`。

## 完成判定

- 两个测试文件全绿，输出含 `[VERIFY] VC-010`~`VC-013`、`VC-016`、`VC-017`、`VC-021`、`VC-025`。
- 熔断/兜底/预算三条语义各有一组"反例断言"（不该发生的计数必须为 0）。
