# Task T-2: 窄工具 worker_file

## 元信息
- Stage: 1
- 依赖: 无（可与 T-1 并行；本任务只新建自己的文件）
- 风险: 中（写入面唯一入口，守卫必须 fail-closed；失败形状若不抛错则拒绝留痕永不出现）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-005, AC-006]
- vc_refs: [VC-005, VC-006]

## 背景（实测，来源见 evidence/research/design-verify-tool-contract-2026-09-23.md）

- 只读角色（review/research/verifier/reviewer/rag-research）的 `TOOL_ALLOWLISTS` 条目无 `write`/`edit`（`worker/worker-mode.ts:49-80`），检查点要求「把一行追加到 progress.md」时无手段可用（事故：OverCode `chroma-review-evidence-r1`，146 次工具调用 writes=0）。
- 注册范式：`rag/tools.ts:246-265`（`pi.registerTool({ name, label, description, promptGuidelines, parameters: Type.Object({...}), execute })`）。
- **失败形状（关键）**：`AgentToolResult`（`packages/agent/src/types.ts:355-368`）**没有 `isError` 字段**；只有 `execute` **抛异常**（`agent-loop.ts:696-704` 捕获）才能让 `tool_execution_end.event.isError === true`，进而由 `worker-mode.ts:786-790` 写 `[TOOL_ERR]`。返回 `{isError:true}` 会被忽略；把错误编码进 content（RAG `failResult`，`rag/tools.ts:167-169`）则 `[TOOL_ERR]` 永不出现 → AC-006/VC-006 不成立。
- **参数校验时机**：pi 在 `execute` 前用 TypeBox `Compile(...).Check` 校验（`packages/ai/src/utils/validation.ts:287,304`）；`pattern`/`required`/`Literal`/`maxLength` 被强制，但 `Type.Object` **默认不拒额外字段**（需显式 `additionalProperties:false`），且 `Value.Convert` **不套用 schema `default`**（`mode` 默认值必须在 execute 内落地）。既有单测直接调用 `execute`（`test/extensions/agent-team-loop.test.ts:202-217`），**绕过 schema** → execute 内的 `isAllowedWorkerFile` 守卫是 VC-006 可测性的必要条件。
- `P-004`：路径词法检查在 Windows 上易漏拦 → 本工具**不做路径解析**，只接受 basename + 正则判定；写入用 `path.join(taskDir, file)`（basename-only）。
- `P-003`：拒绝路径必须在任何 `fs.*` 调用之前返回/抛错（不建目录、不建文件、不截断）。

## 交付物

1. `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts`（新文件）
   - `export const WORKER_FILE_TOOL = "worker_file";`
   - `export const WORKER_FILE_MAX_BYTES = 64 * 1024;`
   - `export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;`（**单一来源**；无 `g` 标志）
   - `export function isAllowedWorkerFile(name: string): boolean`
   - `export type WorkerFileMode = "append" | "write";`
   - `export function writeWorkerFile(taskDir: string, file: string, content: string, mode: WorkerFileMode): { ok: true; path: string; bytes: number } | { ok: false; reason: string }`
     顺序：`isAllowedWorkerFile` → `Buffer.byteLength(content, "utf8") > WORKER_FILE_MAX_BYTES` → `fs.mkdirSync(taskDir, {recursive:true})` → `fs.appendFileSync`（append）/ `fs.writeFileSync`（write）。拒绝时**不得**触碰 fs。
   - `export function registerWorkerFileTool(pi: ExtensionAPI, taskDir: string): void`
     - `pi.registerTool({ name: WORKER_FILE_TOOL, label: "worker_file", description: ..., promptGuidelines: [...], parameters: Type.Object({ file: Type.String({ pattern: WORKER_FILE_NAME_RE.source, description: "Basename only: progress.md | report.md | report-<slug>.md" }), content: Type.String({ minLength: 1, description: "Text to write (max 64 KiB UTF-8)" }), mode: Type.Optional(Type.Union([Type.Literal("append"), Type.Literal("write")])) }, { additionalProperties: false }), execute: async (...) => {...} })`
     - `execute`：`const mode = params.mode ?? "append"`（不依赖 schema default）；`writeWorkerFile(...)`；`ok:false` 时 `throw new Error(\`worker_file rejected: ${r.reason}\`)`；`ok:true` 返回 `{ content: [{ type: "text", text: \`wrote ${r.bytes} bytes to ${r.path} (${mode})\` }], details: {} }`。
2. 测试：新增 `packages/coding-agent/test/extensions/agent-team-loop-worker-file-tool.test.ts`
   - 合法：`progress.md`（append，追加到既有 sentinel 之后）、`report.md`（write）、`report-f1.md`、`report.r1.md`（write）→ 内容与 `bytes` 正确；
   - **VC-006 12 项反例**：`../x.md`、`a/b.md`、`..\x.md`、`C:\abs\x.md`、`\\unc\share\x.md`、`trace.log`、`task.md`、`output.md`、`worker.log`、``（空串）、`.md`、`report-.md` → 全部 `ok:false`；断言目录内文件集合写前后不变（`readdirSync` 排序比对）；
   - 超长内容（`Buffer.byteLength > 64 KiB`，用多字节字符构造以证明按字节而非 code unit）被拒且不写盘；slug > 40 字符的文件名被拒；
   - **schema 层证明**（便宜且必要）：对 `WORKER_FILE_NAME_RE.source` 调 `Compile(Type.String({pattern: ...})).Check` 或等价方式，断言 12 项反例在 schema 层同样 `false`、合法项 `true`；
   - `execute` 抛出的是 `Error`（`await expect(...).rejects.toThrow(/rejected/)`），且抛出后目录文件集合不变；
   - `[VERIFY]` 行用 `process.stdout.write("…\n")`，字段取实测值。
   - 临时目录用 `os.tmpdir()`。
3. 若 workspace 已有 `WorkerFileMode`/工具名冲突，开工前用 `rg` 确认（预期无冲突）。

## 约束

- 只新建上述两个文件；不改 `worker-mode.ts`（T-3 接线）、不改 `rag/tools.ts`、不改 `TOOL_ALLOWLISTS`（parity 锁）、不改 `dist/**`、不改 Python、不改 `~/.pi/agent`。
- 不要复用 `appendProgressLine`（`output-writer.ts`）：它的目录来自 `outputDir(taskKey, agenticdocRoot)`，与本工具的 `taskDir` 是两套目录推导，混用会引入第二个目录来源（RQ-D1 差异 12）。
- TS 只用可擦除语法；无 `any`；无 inline `import()`。
- 不 commit；不运行 `mw build`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts
cd H:/git/Multi-Workers && npm run check
git status --short
```

## 报告要求

最终消息给出：新增文件、用例计数、12 项反例逐项结果（execute 层 + schema 层）、`[VERIFY]` 行原文、失败形状实现方式（`throw` 原文）、以及任何偏离本任务书的实现细节。
