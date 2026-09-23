# Task T-13-MCP-TOOLMAP: 逻辑工具名 → 服务端工具名映射 + `rag_sources` 合并

## 基本信息
- Stage: 3
- 依赖: T-02（adapter）、T-03（fixture + mcp-client）、T-04（tools.ts 调用链）
- 完成状态: 未开始
- 验证状态: 未验证
- 完成 Agent: worker（`coding` 类型）
- ac_refs: [AC-004, AC-006, AC-018]
- vc_refs: [VC-028, VC-026]
- pattern_refs: []

- **`[VERIFY]` 行的发射通道（血泪教训，T-02/T-12 各踩一次）**：本仓库 vitest 配置为 `silent: "passed-only"`，
  **绿灯用例里的 `console.log` 会被吞掉**，证据行在必跑命令的输出里根本看不见（T-11 采集不到）。
  必须用 `process.stdout.write("[VERIFY] ...\n")`（末尾自带换行）。Python 侧 `print` 正常，但需 `pytest -q -s` 才显示。

## 背景
T-04 的实现把**逻辑工具名直接当作服务端工具名**发给 `McpSession.callTool`。参考服务（OverCode rag-mcp，`adapter: overcode-v1`）
的真实工具名并不完全一致：

| 我们的逻辑名 | 参考服务真实工具名 | 说明 |
|---|---|---|
| `rag_search` | `rag_search` | 同名；**重写开关为 true 时**参考服务另有 `rag_search_multi_rounds` |
| `rag_symbol` | `rag_symbol` | 同名 |
| `rag_graph` | `graph_query` | **名不同** |
| `rag_impact` | `rag_impact` | 同名 |
| `rag_sources` | `list_sources` + `list_collections` | **两个工具，需要合并** |
| `rag_feedback` | `rag_feedback` | 同名 |
| `rag_chat` | `rag_chat` | 同名 |

依据：`evidence/research/spec-rag-mcp-integration-2026-09-22.md:31`（读 `...\rag-mcp\references\tools-reference.md` 的结论）、
`...\rag-mcp\SKILL.md` 的工具清单。不修的话 `rag_graph` / `rag_sources` 打到真实服务上是"工具不存在"，而且 `rag_sources` 拿不到 collection 层信息。

## 源码
1. `packages/coding-agent/src/extensions/agent-team-loop/rag/adapter.ts`（适配器族职责，**数据表形式，不逐工具硬编码**）：
   - 新增 `RAG_TOOL_MAP`（逻辑名 → `{mcp: string[], merge?: "sources"}`）与类型 `LogicalRagTool = keyof typeof RAG_TOOL_MAP`。
   - 新增 `ragToolCalls(logical, args)`：返回**实际要发出的调用列表** `{name, args}[]`。
     - `rag_sources` → `[{name:"list_sources", args}, {name:"list_collections", args}]`
     - `rag_search` 且 `multi_rounds === true`（或 `auto_rewrite === true`）→ `[{name:"rag_search_multi_rounds", args: <保留业务参数，剔除 multi_rounds/auto_rewrite 开关>}]`
     - 其余 → `[{name: RAG_TOOL_MAP[logical].mcp[0], args}]`
     - 未知逻辑名 / 映射缺项 → 抛 `RagConfigError`（`kind = "config"`），**零请求**
   - 新增 `mergeToolResponses(logical, responses)`：`rag_sources` 把 `list_sources` 与 `list_collections` 的原始 payload 合并成一份（两者条目都在，且各自保留 source/collection 归属信息），再交给既有 `normalizeResults`。
2. `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts`（**最小改动**，只改调用链那一段）：
   - 工具执行链改为：`ragToolCalls(...)` → 逐个 `session.callTool(...)` → `mergeToolResponses(...)` → 既有 `normalizeResults(...)`。
   - 一次**逻辑**工具调用 = 一次预算预留/熔断计数/心跳（`rag_sources` 虽发两次 HTTP，但只记一次工具调用；若 T-05 的 hooks 尚未落地，保持现状并在 output.md 说明）。
   - 证据行与返回体：`tool` 记**逻辑名**，另加 `mcp_tool`（多调用时用 `+` 连接，如 `list_sources+list_collections`）记实际发出名，便于核对。

## 测试
新增 `packages/coding-agent/test/suite/rag-toolmap.test.ts`（**不要改 T-04 的 `rag-tools.test.ts`**，也别改 T-02/T-03 的测试文件）：
- fixture 断言**实际发出工具名**（读 `fixture.calls[].name`）：
  - `rag_graph` → 恰一次 `graph_query`（且不是 `rag_graph`）
  - `rag_sources` → 恰两次：`list_sources` 与 `list_collections`（顺序不限）
  - 研究角色（`multi_rounds=true`）的 `rag_search` → `rag_search_multi_rounds`，且 args 里**没有** `multi_rounds`/`auto_rewrite`
  - coding 角色（`multi_rounds=false`）→ `rag_search`，args 保留业务参数
  - `rag_symbol` / `rag_impact` / `rag_feedback` → 同名
- 合并信封：`rag_sources` 返回项里 `list_sources` 与 `list_collections` 的内容都在（按 fixture 返回构造两份不同 payload，断言两者条目都出现）。
- 未知逻辑名（直接调 `ragToolCalls("rag_nope", {})`）→ 抛 `RagConfigError` 且 fixture `calls.length` 增量为 0。
- 引用语法不受影响：合并后的条目仍走 D-004 语法（复用 T-02 的往返断言即可，不重复造 5 类 fixture）。

## 完成判定
- [ ] 新增测试全绿：`node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-toolmap.test.ts`（包根 `packages/coding-agent`）
- [ ] 零回归：复跑 `test/suite/rag-tools.test.ts`、`test/suite/rag-adapter.test.ts`、`test/suite/rag-transport.test.ts`、`test/suite/rag-parity.test.ts`
- [ ] `npm run check` 输出 0 error / 0 warning / 0 info（含 `tsgo --noEmit`）
- [ ] 证据行（`process.stdout.write`）：`[VERIFY] VC-028: mapped_names=6/6 sources_merged=true multi_rounds_tool=rag_search_multi_rounds`
- [ ] 既有测试零修改；不新增依赖；不 commit
- [ ] output.md 写清：实际命令与输出、改动文件清单、未覆盖点、与 AC-006 的口径说明（适配器解析出的开关 vs 实际发出工具名）

## 注意
- **不要改 `rag/config.ts`**（T-12 已把它与 Python/golden 锁死；映射表属适配器，不进配置 schema。第二个服务族走新 adapter，v1 不做逐 server 覆盖）。
- **不要改 Python 侧**任何文件。AC-006 已 [REVISED @ 2026-09-22]：适配器解析出的开关是适配器层事实，实际线上请求按本任务的映射表转换。
- `rag_sources` 两次调用的**失败语义**：任一次失败即整体失败（错误按 T-03 的 `RagErrorKind` 上抛），不做部分成功合并；测试里覆盖其中一次失败的情形至少一例。
- 不要动 `index.ts`（其它会话持有其未提交改动）。
