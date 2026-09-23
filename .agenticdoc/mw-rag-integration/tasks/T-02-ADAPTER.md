# Task T-02-ADAPTER: 归一化信封 / 引用语法 / path_roots 契约

## 基本信息
- Stage: 1
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-005, AC-006]
- vc_refs: [VC-006, VC-007, VC-008, VC-026]
- pattern_refs: []

## 描述

### 源码

新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/adapter.ts`（纯函数层，无网络无写盘；`fs` 只读）。

导出：

```ts
export interface RagCitation { server: string; source: string; filePath: string; line: number }
export interface RagItem {
	symbol_name: string; qualified_name: string | null; symbol_type: string | null;
	file_path: string; line_start: number | null; line_end: number | null;
	snippet: string | null; score: number | null;
	citation: string | null;
	local_path: string | null; exists: boolean; line_hint: number | null;
	snapshot_warning: true;
}
export interface RagEnvelope { server: string; tool: string; source: string | null; snapshot: true; items: RagItem[]; meta: Record<string, unknown> }

export function formatCitation(c: RagCitation): string;
export function parseCitation(text: string): RagCitation | null;
export function loadPathRoots(pathRootsFile: string | null): Record<string, string> | null;   // null = 未配置
export function resolveLocalPath(filePath: string, roots: Record<string, string> | null):
	{ localPath: string | null; exists: boolean; lineHint: number | null; reason: string | null };
export function rewriteDefaults(role: string, phase: string, capabilityRewrite: boolean, explicit?: boolean): boolean;
export function normalizeResults(server: string, tool: string, source: string | null, raw: unknown,
	roots: Record<string, string> | null): RagEnvelope;
export function capabilityError(server: string, tool: string, caps: { graph: boolean; chat: boolean }): RagToolError | null;
```

实现要点：
- **引用语法（D-004，必须精确）**：`citation = server ":" source ":" filePath ":" line`。
  - `formatCitation`：直接拼接，`server`/`source` 先校验不含 `:`（含则抛错），`filePath` 原形保留（可为 `engine::Runtime/Renderer/X.cpp`、可含空格/反斜杠/Unicode）。
  - `parseCitation`：从左取 2 段得 server/source（每段非空且不含 `:`）；从右取最后一段 `line`（必须 `^\d+$`）；**中间剩余全部（含其中的 `:` 与 `::`）为 `filePath`**；长度不足或 line 非数字 → null。**不要**用 `split(":")` 按下标取值。
- **path_roots 契约（D-007，与 rag-mcp `resolve_path.py` 对齐）**：JSON `{ "<role>": "<绝对根>", ... }`，忽略 `_` 前缀键；解码容忍 BOM（`utf-8-sig` 语义：读入后剥 `\uFEFF`）；文件不存在 → 返回 null；内容非法 JSON → 抛 `RagConfigError`（复用 `config.ts` 错误类型）。
  - `filePath` 形态 `role::rel` 或裸 `rel`（裸形态 role 默认 `"engine"`）；`rel` 去空白、`\` → `/`、去开头 `/`。
  - 结果 = `path.resolve(root, rel)`（`localPath` 必须是规范化绝对路径）。
  - 未知 role → `localPath=null` + `reason` 含可用 role 列表；`..` 逃逸出 root → `localPath=null` + `reason` 含 traversal。
  - `roots === null`（未配置）→ `localPath=null`、`exists=false`、`reason="path_roots not configured"`；**映射存在但文件缺失** → `exists=false` 而 `localPath` 仍为解析值、`reason="file missing"`（两者必须可区分）。
  - `snapshot_warning` 恒为 `true`；`line_hint` = `line_start` 原值，不做本地校正。
- **rewrite 默认（AC-006）**：`spec`/`design`/`research`/`rag-research` 角色或 `spec`/`design` 阶段 → 默认 true，需 `capabilityRewrite` 为真；`coding`/`review` → false；`explicit` 传入时以显式值为准。
- **能力错误（AC-004）**：`capabilityError` 在能力关闭时返回 `{ kind: "capability", server, tool, message }`，message 含人类可读原因（如 `no knowledge graph for server X`）；graph 类工具（`rag_graph`/`rag_impact`）查 `graph`，`rag_chat` 查 `chat`。
- **归一化**：把 rag-mcp 返回结构（`documents[]`/`results[]`/`symbols[]`/`callers…`，见 `references/tools-reference.md`）映射为 `RagItem[]`，逐项生成 `citation` + 调 `resolveLocalPath`；`meta` 保留 `total_*`/`affected_files`/`static_analysis`/`rewrite_degraded` 等；非法结构（缺必需字段）抛 `RagConfigError` kind `invalid-shape`，不静默产出空信封。

### 测试

新增 `packages/coding-agent/test/suite/rag-adapter.test.ts`：

- **引用语法往返（VC-026）**：五类输入各做 `format → parse` 往返并逐字段断言——`engine::Runtime/Renderer/X.cpp`（`::` 形态）、`Runtime/Renderer/X.cpp`（无 role 前缀）、`Source Files/My Header.h`（含空格）、`Engine\Source\X.cpp`（反斜杠）、`源码/角色.cpp`（Unicode）；再断言 `filePath` 含 `:` 时不被切成 server/source。
- **归一化与本地核对（VC-006）**：给定 scripted raw（`file_path="engine::Runtime/Renderer/X.cpp"`、`line_start=123`）+ roots `{engine: <tmp>}`（tmp 内真建该文件）→ `local_path` 等于规范化绝对路径、`exists===true`、`line_hint===123`、`snapshot_warning===true`、`citation === "<server>:<source>:engine::Runtime/Renderer/X.cpp:123"`。
- **未配置 vs 缺失（VC-007）**：`loadPathRoots(null)` → `localPath=null`、`exists=false`、`reason` 含 `path_roots`；roots 存在但文件不在 → `exists=false` 且 `reason` 含 `file missing`（与前者不同）。
- **越界与未知 role**：`engine::../outside.cpp` → `localPath=null` 且 reason 含 traversal；`engine::` → null + reason 列出可用 role。
- **rewrite 默认（VC-008）**：`rewriteDefaults("research", …)` true、`("coding", …)` false、`("coding", … , explicit=true)` true、capability 关闭时 false。
- **能力错误（VC-005 的一半）**：`capabilityError(server, "rag_graph", {graph:false, chat:true})` 非空且 `kind==="capability"`。

### 注意

- 只用 `node:path` / `node:fs`；路径规范化用 `path.resolve` + `path.relative` 做逃逸判定（Windows 大小写不敏感：比较用 `toLowerCase()`）。
- 不要把 `local_path` 写进 `citation`；两者字段分离（design D-004）。
- 测试运行：`node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-adapter.test.ts`（coding-agent 包根）。

## 完成判定

- `rag-adapter.test.ts` 全绿，输出含 `[VERIFY] VC-006` / `VC-007` / `VC-008` / `VC-026`。
- `rag_graph` 能力关闭路径在不发起任何请求时即返回结构化错误（本任务只做纯函数判定）。
