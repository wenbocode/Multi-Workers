# Task T-10-REQUIRE-AUDIT: required 判定（role∪phase）/ 告警证据 / `mw rag audit`

## 基本信息
- Stage: 5
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-010, AC-015, AC-016]
- vc_refs: [VC-014, VC-019, VC-020, VC-021]
- pattern_refs: []

## 描述

- **证据行解析契约（T-05 已定稿，按此实现）**：`rag_call` 行的规范形态是 `rag_call server=<S> tool=<T> via=(mcp|cli) ms=<N> results=<N> mcp_tool=<M>`（前六字段是前缀，`mcp_tool` 为实际发出名，fan-out 时用 `+` 连接，如 `list_sources+list_collections`）；另有 `rag_fallback` / `rag-unavailable` / `rag-rewrite-degraded` / `rag-budget-exceeded` / `rag-required-missing` 五类行。解析器必须**按 key=value 逐字段读**，不要用位置切割或 `$` 锚定整行——后续新增字段不得让 audit 崩。`mcp_tool` 只作核对用途，不参与 require 判定。### 源码

1. **worker 端 required 判定与告警（AC-010）**：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
   - 任务开始时从 task.md 的 `<!-- mw-rag: v1 -->` 块解析 `requiredFor(role, phase)`（T-01 的 `requiredFor`）；role 由 task.md `type:` 经 `roleForTaskType` 得到，phase 由任务声明（无声明视为 none）。
   - 全程记录"是否有**可核对引用**"（工具返回过带 `citation` 且 `exists` 可判定的结果即算"用了"；只有 `rag_call` 行而无引用**不算**）。
   - 任务结束路径（复用 `output-writer.ts::writeOutput` 与 `appendTrace`，**不要**再写第二套 trace/output writer）：required 且未用 → `appendTrace(..., "rag-required-missing role=<role> phase=<phase> server=<S>")`，并在 output.md 附加 `## RAG` 段，正文含 `RAG 未生效`（并说明是"声明必须使用但产出无可核对引用"）。
   - **只告警不阻断**：不改变退出码、不改变 `_workers.parallel` 状态（VC-014 断言 status=done）。
2. **`mw rag audit`（AC-015，只读）**：`packages/multi-workers/mw.py`（子解析器在 T-08 预留的 `rag_sub` 上加一行）+ 审计实现放 `mw_common.py` 或 `autopilot/` 下的独立函数（只读，默认只写 stdout）：
   - 扫描面：`<key>/rag/*.md`（递归一层即可）+ **终态** worker 目录（`_workers.parallel` 状态为 done/failed/needs-clarification）的 `output.md` / `trace.log`；**不扫** `spec.md`/`design.md`/plan 等阶段文档；**非终态** worker 目录跳过（避免写一半的文档）。
   - 引用提取：按 D-004 语法 `server:source:file_path:line`（左侧两段 + 右侧行号 + 中间全归 file_path），用同名解析器（Python 侧实现一份，函数命名 `parse_citation`，与 TS 测试用例共享同一批 fixture 字符串）。
   - 判定：`missing` = 引用可解析但本机文件不存在（或 role 未知、路径越界）；`unverified` = 无法核对（如该 server 未配置 `path_roots`）；每条记录带 `task_key / worker / role / phase` 归属。
   - `required_missing`：对 `requiredFor(role, phase)` 为真的终态任务，**存在可核对引用**才不算 missing；只有 `rag_call` 行不算（VC-020）。role.require 与 phase.require 各自单独为真都要触发（并集，无例外）。
   - 输出 `{calls, citations, missing[], unverified[], required_missing[]}`；退出码：0 = missing 与 unverified 均为 0；1 = 有 missing 或 unverified；2 = 参数/配置错误。`--json` 机器可读；`--out <file>` 才落盘（默认**不写任何文件**）。
3. `mw doctor` 的 rag 段（T-08）追加 `required_missing` 计数（只读展示）。

### 测试

- `packages/coding-agent/test/suite/rag-required.test.ts`（VC-014）：fixture 项目 `roles.review.require=true` + review worker 未调用 RAG → 队列 status `done`、trace 含 `rag-required-missing`、output.md 含 `RAG 未生效`；对照组（未声明 require）→ trace **不含**该行；再对照（声明 require 且确有可核对引用）→ 不含该行。
- `packages/multi-workers/test_rag_audit.py`：
  - **正负例（VC-019）**：负例（引用指向不存在文件）→ 退出码 ≠ 0 且 `missing >= 1`；正例（全可达）→ 退出码 0 且 `missing == 0 and unverified == 0`。
  - **扫描边界**：把同样的假引用写进 `spec.md`/`design.md` → 不计入；非终态 worker 目录 → 不计入。
  - **归属**：每条 missing 记录含 `task_key/worker/role/phase`。
  - **只读**：默认运行前后对项目目录做文件清单 + mtime 快照，断言无一变化；`--out` 指定时才产生该文件。
  - **require 并集（VC-020）**：仅 `roles.coding.require=true` 未用 → `required_missing` 非空；仅 `phases.design.require=true` 未用 → 同样非空；worker 只有 `rag_call` 行而无可核对引用 → 仍判 `required_missing`。
  - **降级标记（VC-021 的 Python 面）**：对含 `meta.rewrite_degraded` 的结果，audit 输出中对应调用标记为 `degraded=true`（不改变退出码）。

### 注意

- audit 必须**只读**：不得写回产出物、不得改 `_workers.parallel`、不得创建 `<key>/rag/` 目录（VC-019 的 `writes=0`）。
- 与 T-09 共用 `rag-required-missing` 机制（文档缺失走同一条路径），不要实现两份。
- 测试运行：multi-workers 下 `python -m pytest test_rag_audit.py -q`；TS 侧 `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-required.test.ts`。

## 完成判定

- 上述测试全绿，输出含 `[VERIFY] VC-014` / `VC-019` / `VC-020` / `VC-021`。
- `mw rag audit` 在正例项目上退出 0，在负例项目上退出 1，且两者都不修改项目内任何文件。
