# Task T-03-TRANSPORT: fixture MCP server + MCP client + CLI bridge

## 基本信息
- Stage: 2
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-007, AC-012]
- vc_refs: [VC-009]
- pattern_refs: []

## 描述

### 源码

1. 新增 `packages/coding-agent/test/suite/rag-fixture.ts`（测试基础设施，`node:http` 起服务；既有先例 `test/llama-extension.test.ts` 用 `http.createServer`）：

```ts
export interface RagFixtureOptions {
	tools?: Record<string, (args: Record<string, unknown>, call: number) => unknown | Promise<unknown>>;   // 脚本化返回
	delayMs?: number;                    // 单次响应延迟（模拟慢调用）
	dropAfterDelivery?: boolean;         // 收到请求后不回响应（模拟"已送达但响应丢失"）
	token?: string;                      // 期望的 X-MCP-Token；不匹配 → 401
	rewriteDegraded?: boolean;           // rag_search 返回 meta.rewrite_degraded=true
}
export interface RagFixture {
	url: string; port: number;
	calls: Array<{ method: string; name: string | null; args: Record<string, unknown> }>;
	failNext(n: number, mode?: "reset" | "500"): void;   // 制造连接级失败（可证未送达）
	stop(): Promise<void>;
}
export async function startRagFixture(options?: RagFixtureOptions): Promise<RagFixture>;
```

协议（照 `E:\CLI_Workspace\OverCode\depot\rag-mcp\setup\mcp-config.json`）：`POST /mcp/`，JSON-RPC 2.0；`initialize` 返回 `Mcp-Session-Id` **响应头**，缺 header 的后续请求 → HTTP 400；`tools/call` 按名字分发到 scripted handler；无 SSE。fixture 必须记录每次调用的 `method`/`name`/`args` 与计数（供 VC-005/010/012 断言"零请求"）。

2. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/mcp-client.ts`：

```ts
export type RagErrorKind = "connect" | "protocol" | "tool" | "capability" | "budget" | "timeout" | "circuit";
export class RagToolError extends Error { kind: RagErrorKind; server: string; tool: string; detail?: unknown }
export class McpSession { constructor(baseUrl: string, tokenEnv: string | null) ; initialize(timeoutMs?: number): Promise<void> ; callTool(name: string, args: unknown, opts: { timeoutMs: number; signal: AbortSignal; onUpdate?: (m: string) => void }): Promise<unknown> }
```

实现要点：`initialize` 用 `protocolVersion: "2025-03-26"`，从响应头取 `Mcp-Session-Id` 并保存，后续每请求携带；`X-MCP-Token` 取自 `process.env[tokenEnv]`（**绝不从配置读明文**）。错误分类：`ECONNREFUSED`/`ENOTFOUND`/连接被 reset → `connect`（**可证未送达**）；HTTP 非 2xx 且非 401/403 → `protocol`；JSON-RPC `error` 字段 → `tool`；401/403 → `protocol`（鉴权类，不兜底）；`AbortSignal` 超时 → `timeout`。超时用 `AbortController` + `setTimeout`（检索默认 180s、`rag_chat` 600s，由调用方传）。

3. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/cli-bridge.ts`：

```ts
export async function callCli(cliEntry: { dir: string; cliEntry: string; timeoutMs: number },
	name: string, args: Record<string, unknown>, opts: { signal: AbortSignal; env: NodeJS.ProcessEnv; onUpdate?: (m: string) => void }): Promise<unknown>;
```

实现要点：`spawn(pythonExe, [cliEntry.cliEntry, name, ...kvArgs], { cwd: dir, env, shell: false })`（**参数数组，不经 shell**）；解释器按仓库既有约定解析（`shared/mw-runner.ts::PYTHON_EXE`：Windows `python` / 其它 `python3`，并支持 `MW_RAG_PYTHON` 显式覆盖）——**不要**用 `process.execPath`（那是 Node/Bun，会让 skill 传输路径直接死亡）；stdout 必须是单段 JSON → parse；退出码 0 = 成功、2 = `connect`、3 = `tool`、其他 = `protocol`；stderr 只进 `detail`（**需脱敏**：调用 `redactSecrets`，见 T-05）。契约：`<python> <cli_entry> <tool> --arg k=v ...`。

### 测试

新增 `packages/coding-agent/test/suite/rag-transport.test.ts`：

- **握手**：`initialize` 后 `callTool` 正常返回 scripted 结果；断言 fixture 收到的第二个请求带 `Mcp-Session-Id`（VC-009 的一半：会话真实建立）。
- **未起服务快失败（VC-009）**：对未监听端口调用 → `RagToolError.kind === "connect"`，且耗时 < 2000ms（断言 `Date.now()` 差）。
- **超时**：`delayMs` 大于 `timeoutMs` → `kind === "timeout"`。
- **已送达不响应**：`dropAfterDelivery: true` → `kind === "timeout"`（**不得**判为 `connect`——这是 T-05 兜底策略的判据基础）。
- **协议错误**：模式 `500` → `kind === "protocol"`；302/400（缺 session）→ `protocol`。
- **token**：fixture 期望 token 与 env 匹配时成功；不匹配 → `protocol` 且错误消息不含 token 值。
- **CLI bridge**：用一个临时 `.py` 脚本（`writeFileSync` 到 tmp）返回 JSON 并分别 `exit(0/2/3)` → 断言 kind 映射与 shell 未被使用（参数含空格时不裂开）。

### 注意

- 只用 `node:http` / `node:child_process` / 全局 `fetch`（本仓已装 undici 全局 dispatcher，见 `src/core/http-dispatcher.ts`）；**不新增依赖**。
- fixture 必须 `stop()` 干净（`server.close()` + 等待所有响应结束），避免 vitest 挂起。
- 测试运行：`node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-transport.test.ts`（coding-agent 包根）。

## 完成判定

- `rag-transport.test.ts` 全绿，输出含 `[VERIFY] VC-009`（含 `error_kind=connect` 与 `elapsed_lt_2000ms`）。
- `connect` / `timeout` / `protocol` / `tool` 四类错误可被上层区分（T-05 的熔断与兜底只依赖这四类）。
