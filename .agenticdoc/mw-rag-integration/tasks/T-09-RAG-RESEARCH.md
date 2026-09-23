# Task T-09-RAG-RESEARCH: `rag-research` 类型双侧接入（parity 零修改）

## 基本信息
- Stage: 5
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-011, AC-014]
- vc_refs: [VC-015, VC-018]
- pattern_refs: []

## 描述

### 源码

1. `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`：在 `TOOL_ALLOWLISTS`（36-50）追加一项，**顺序与 Python REGISTRY 条目逐项一致**：

```ts
// RAG research bucket (mw-rag-integration D-011): renders rag_chat, the only
// type allowed to call it. conductor_dispatchable=False on the Python side.
"rag-research": ["read", "find", "grep", "ls", "rag_search", "rag_symbol", "rag_graph", "rag_impact", "rag_sources", "rag_feedback", "rag_chat"],
```

2. `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`：`DISPATCH_ROLE_BY_TYPE` 追加 `"rag-research": "research"`；`DISPATCHABLE_TYPES` 追加 `"rag-research"`（PM 侧 `dispatch_worker` / `/worker` 可派发；conductor 不派发由 Python 侧门控）。

3. `packages/multi-workers/autopilot/dispatch.py`：
   - `DispatchType`（dataclass，字段 `name/tools/cli/provider/requires_read_scope`）追加字段 `conductor_dispatchable: bool = True`（**带默认值**，既有 5 个条目的位置参数不受影响）。
   - `REGISTRY` 追加条目（工具元组与 TS 侧逐项等序）：
     `"rag-research": DispatchType("rag-research", ("read","find","grep","ls","rag_search","rag_symbol","rag_graph","rag_impact","rag_sources","rag_feedback","rag_chat"), "pi", "timi", False, False)`。
   - 派发校验（:265 附近，未注册类型的拒绝处）追加：`conductor_dispatchable` 为 `False` 的类型 → 拒绝并给出原因（`"rag-research is a PM-dispatched type, the conductor must not dispatch it"`）。
4. `packages/multi-workers/mw_common.py`：`TASK_TYPE_TO_ROLE`（:137）追加 `"rag-research": "research"`。

5. 调研文档流程（AC-014）：`packages/multi-workers/skills/mw-rag/SKILL.md` 的"§调研文档格式"（T-08 已写）是唯一标准；本任务新增一个**校验辅助**（TS 侧 `rag/research-doc.ts` 或复用 worker 侧已有函数均可）：给定 key 目录，断言 `rag/<server>-<slug>.md` 存在、六个标题齐全（**以 `packages/multi-workers/skills/mw-rag/SKILL.md` 为准：`## 查询` / `## 结论` / `## 引用` / `## 未解决` / `## 快照` / `## 影响面`**；spec AC-014 已按此 `[REVISED @ 2026-09-22]` 对齐）、每条引用可按 D-004 语法解析；在 worker 的 `rag-research` 结束路径上，若未产出该文档 → 追加 `rag-required-missing` 证据行（与 T-10 的 required 判定同一机制，避免两套）。

### 补充要求：`rag_chat` 的 per-call 上限（T-05 遗留、必须由本任务闭合）
- T-05 只接了 `mcp.timeout_ms`（默认 180s），但参考服务 `rag_chat` 实测 **41s–9min**（`evidence/research/spec-rag-mcp-integration-2026-09-22.md`）——180s 会把长 chat 直接掐死，而 chat 正是 rag-research 的主武器。
- 实现：在 TS 侧新增常量 `RAG_CHAT_TIMEOUT_MS = 600_000`，实际 per-call 上限取 `max(config.mcp.timeoutMs, RAG_CHAT_TIMEOUT_MS)` **仅对 `rag_chat`**；检索类工具保持 `mcp.timeout_ms`（默认 180s）。**不得改 `rag/config.ts` 的配置 schema**（T-12 锁死的跨语言契约），因此这是一个常量而非新字段。
- 为可测性，把选择逻辑抽成可导出的小函数（如 `ragCallTimeoutMs(logicalTool, config): number`，放 `rag/tools.ts`），并断言：
  - `ragCallTimeoutMs("rag_chat", {timeoutMs: 180_000}) === 600_000`
  - `ragCallTimeoutMs("rag_search", {timeoutMs: 180_000}) === 180_000`
  - 若 `mcp.timeout_ms` 显式大于 600s，则 chat 用配置值（`max` 语义）
- 如果传输层（T-03 的 `McpSession`）无法按调用传 timeout，**停下并在 output.md 写清**，由 PM 决定是扩 transport 签名还是退回常量（不要静默忽略）。

### 测试

- `packages/coding-agent/test/suite/rag-research.test.ts`：`rag-research` 任务的活动工具集 === 11 项（`toolsForType("rag-research")` 断言逐项等序）；`roleForTaskType("rag-research") === "research"`；会话门控下 `rag_chat` 仅在该类型可见（其余类型不可见）。
- `packages/multi-workers/test_autopilot_l0.py`：**必须零修改通过**——先跑 `python -m pytest test_autopilot_l0.py -q` 记录基线，改完再跑并断言 `git diff --stat test_autopilot_l0.py` 为空。这是本任务第一验收条件（改测试 = 任务失败）。
- 新增 `packages/multi-workers/test_rag_research_dispatch.py`：`dispatch.dispatch(...)` 传 `rag-research` → 被拒且消息含 "must not dispatch"；`TASK_TYPE_TO_ROLE["rag-research"] == "research"`；`registry_snapshot()["rag-research"]` 与 TS 解析结果逐项相等（沿用 L0 测试的 `_parse_ts_allowlists` helper，不要复制一份）。
- `packages/coding-agent/test/suite/rag-research-doc.test.ts`：fixture key 目录含一份合规调研文档 → 校验通过、`[VERIFY] VC-018`；缺一小节 → 失败并指出缺失标题；引用不可解析 → 失败。

### 注意

- **不要**修改 `test_autopilot_l0.py`（C-1 已裁决）；也不要为了绕过 parity 而在 TS 侧减少条目。
- `fallback` 桶语义不变（仍是 coding 全集）；`rag-research` 不是 fallback。
- 测试运行：coding-agent 包根 `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-research.test.ts test/suite/rag-research-doc.test.ts`；multi-workers 下 `python -m pytest test_autopilot_l0.py test_rag_research_dispatch.py -q`。

## 完成判定

- `test_autopilot_l0.py` 零修改通过（含 `VC-023` 行 `registry_parity=per-type-exact`）。
- 新测试全绿，输出含 `[VERIFY] VC-015`（`parity_unchanged=pass tools=11 conductor_dispatchable=false`）与 `[VERIFY] VC-018`。
