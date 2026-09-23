# Task T-04-TOOLS: 七工具面 / 门控注册 / worker 幂等注入 / task.md 块 / 前置校验

## 基本信息
- Stage: 2
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-001, AC-003, AC-004]
- vc_refs: [VC-001, VC-003, VC-004, VC-005]
- pattern_refs: []

## 描述

### 源码

1. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/guidelines.ts`：导出 `RAG_PROMPT_GUIDELINES: string[]`（**只 3 行**调用纪律：优先 `rag_symbol`/`rag_graph` 精确定位；引用必须用工具返回的 `citation` 原文，不得自行拼接；检索结果需落盘到 `rag/*.md` 才算"用了 RAG"）。方法论正文在 skill（T-08），此处不重复。

2. 新增 `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts`：

```ts
export interface RagRuntime {   // 由 tools.ts 持有，跨工具调用复用
	config: RagConfig; controlRoot: string; workerTaskDir: string | null;
	reachable: Map<string, boolean>;                     // activate 探活结果（5s/服务，仅启用集）
	sessions: Map<string, McpSession>; breaker: Breaker; budget: Budget;
}
export function registerRagTools(pi: ExtensionAPI, controlRoot: string): RagRuntime | null;   // 未启用 → null（零注册）
export function ragToolNamesForType(rt: RagRuntime, type: string): string[];                  // 该类型的 RAG 子集
export function applyRagTools(pi: ExtensionAPI, rt: RagRuntime | null, type: string): void;   // 幂等 setActiveTools
```

- 七个工具用 typebox 参数定义（`rag_search`/`rag_symbol`/`rag_graph`/`rag_impact`/`rag_sources`/`rag_feedback`/`rag_chat`，参数签名与 design §4.1 表格逐字段一致）；`server` 参数为**闭环 enum**：`Type.Union(config.enabled.map(...))`（启用集为空时**不注册任何工具**）。
- `rag_chat` **只在** `rag-research` 类型下可注册/可激活（其余类型不出现，也不出现在其 enum 列表里）。
- 工具描述尾部按探活结果追加 ` [unreachable at session start]`（VC-009）；探活只对启用集、每个 5s 超时、失败不抛错。
- 调用链：`capabilityError`（T-02）→ 预算/墙钟（T-05）→ 传输（T-03，`both` 时先 mcp）→ `normalizeResults`（T-02）→ 证据行（T-05）。
- `applyRagTools`：每次调用**重算**完整期望集合再 `pi.setActiveTools([...toolsForType(type), ...ragToolNamesForType(rt, type)])`（`before_agent_start` 每次 agent run 都会执行，必须幂等，不得只跑一次）。

3. 修改 `worker/worker-mode.ts`：`before_agent_start` handler（现 516-518，其中 517 为 `setActiveTools(toolsForType(meta.type))`）改为先取 RAG runtime（`workerModeActivate` 内注册时保存在闭包里），再调 `applyRagTools(...)`；RAG 未启用时行为与现状**逐字节等价**。同时在 `parseTaskMd`（:167）追加读取 `rag_chat_budget:` / `rag_time_budget_s:` 两个可选整数头（缺省走配置默认）。

4. 修改 `pm/task-dispatcher.ts`：`injectWorkspaceProfile`（208-249）在同一处追加 `<!-- mw-rag: v1 -->` 块（仅 `config.enabled` 非空时）：可用服务列表、必需角色/阶段、默认 server/source、rewrite 默认、chat 预算、累计时间预算、引用语法一行、`fingerprint=<sha256>`；重派发时 marker 块**整体替换**（与 workspace profile 同一套幂等语义），未启用时不写任何 rag 内容。
   块文本必须由 **单一来源** `rag/block.ts::renderRagBlock(config, meta)` 产出（若 T-01 已在 `config.ts` 实现同名函数则复用/搬迁到 `block.ts`，不得两份），并**逐字节等于** `packages/multi-workers/test/fixtures/rag-block.golden.md`（347 B，无尾换行；读取用 `new URL("../../../multi-workers/test/fixtures/rag-block.golden.md", import.meta.url)`，先例 `test/extensions/agent-team-loop-profile-injection.test.ts:550`）；注入时用 `content.rstrip() + "\n\n" + block + "\n"`。

5. 修改 `pm/ui-bridge.ts`：`dispatch_worker` 工具与 `/worker` 命令在创建 task.md 之前调用 `validateRagEnabled(projectDir)`；捕获 `RagConfigError`（如 `unknown-server`）→ 直接返回错误文本（含 server 名与可见 server 列表），**不创建 task.md、不入队**（VC-003）。

### 测试

新增 `packages/coding-agent/test/suite/rag-tools.test.ts`（用 `test/suite/harness.ts` + faux provider；fixture 来自 T-03）：

- **零影响（VC-001）**：controlRoot 无 `rag` 段的会话——断言 `rag_*` 工具数 === 0、新派发 task.md 中 `mw-rag` marker 次数 === 0、fixture 请求计数增量 === 0、`.pi/skills/mw-rag.md` 与 `workers/<task>/rag-budget.json` 存在性前后不变。
- **恰六个 + enum（VC-004）**：启用 A/B 时注册名集合 === 六名且 `rag_chat` 不可见；六个带 `server` 的工具其 enum === `["A","B"]`。
- **能力错误（VC-005）**：A 声明 `capabilities.graph=false` → `rag_graph` 返回 `kind==="capability"`、message 含 `no knowledge graph`、fixture 请求计数 === 0。
- **拒派发（VC-003）**：`rag.enabled` 引用未定义 server → `dispatch_worker` 返回错误含 `unknown rag server`，`workers/<task>/` 不存在，`_workers.parallel` 行数不变。
- **注入幂等**：连续触发两次 `before_agent_start`（或两次 run）后活动工具集不变且无重复项；未启用项目下 `setActiveTools` 的入参与改造前一致（golden 快照断言）。

### 注意

- 注册点在**两个**已知 controlRoot 处：`worker/worker-mode.ts::workerModeActivate`（controlRoot = `path.dirname(agenticdocRoot)`，`agenticdocRoot = dirname(dirname(taskPath))`）与 `pm/pm-orchestrator.ts::pmActivate`（controlRoot = `process.cwd()`）。**不要**在 `index.ts` 里猜路径。
- **T-03 交接**：`RagErrorKind` / `RagToolError` 声明在 `rag/adapter.ts`，`rag/mcp-client.ts` 只是 re-export；`RagToolError.server` 在传输层填的是 `baseUrl`（构造器拿不到配置里的 server 名），所以**在写证据行/进熔断键之前必须用配置 server 名重新标注**。fixture 的 `calls[]` 每次请求都记录（含失败尝试），可直接用 `calls.length` 增量做“零请求”断言。四类错误的构造方式见 `workers/mw-rag-t03-transport/output.md`。
- **文件所有权（与 T-12 并行）**：本任务拥有 `rag/block.ts`（新建，`renderRagBlock(config, meta): string | null`，单一来源）、`rag/tools.ts`、`rag/guidelines.ts`、`worker/worker-mode.ts`、`pm/task-dispatcher.ts`、`pm/ui-bridge.ts`；**不要改 `rag/config.ts`**（T-12 正在那里修 snake_case 键名与 path_roots 解析锚点，你只消费其导出）。若你发现 config.ts 有阻塞性缺陷，**停手并在 output.md 写清**（附最小复现），由 PM 安排。
- **rag 块字节契约**：`renderRagBlock` 必须逐字节等于 `packages/multi-workers/test/fixtures/rag-block.golden.md`（347 B，无尾换行；读取用 `new URL("../../../multi-workers/test/fixtures/rag-block.golden.md", import.meta.url)`，先例 `test/extensions/agent-team-loop-profile-injection.test.ts:550`）；注入侧用 `content.rstrip() + "\n\n" + block + "\n"`。这条断言由本任务的 `rag-tools.test.ts` 承担（T-12 不重复）。
- **T-08 已交付**：`packages/multi-workers/skills/mw-rag/SKILL.md` 里 `## 调研文档格式` 的六小节标准为 `## 查询` / `## 结论` / `## 引用` / `## 未解决` / `## 快照` / `## 影响面`（spec AC-014 已按此 [REVISED @ 2026-09-22] 对齐）。
- 零影响是结构性的：未启用时工具根本不注册（不是"注册后隐藏"），也不写任何文件（D-014）。
- 零影响是结构性的：未启用时工具根本不注册（不是"注册后隐藏"），也不写任何文件（D-014）。
- 同仓库里 T-06 已产出 rag 块 golden 与 `mw_common` 侧渲染器；TS 侧只要一次渲染偏差就会让 T-12 parity 失败——优先复用已有 `renderRagBlock` 而不是重写拼装逻辑。
- 测试运行：`node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-tools.test.ts`（coding-agent 包根）。

## 完成判定

- `rag-tools.test.ts` 全绿，输出含 `[VERIFY] VC-001` / `VC-003` / `VC-004` / `VC-005`。
- 既有 `autopilot-*` / worker 相关套件零修改通过（未启用路径等价性）。
