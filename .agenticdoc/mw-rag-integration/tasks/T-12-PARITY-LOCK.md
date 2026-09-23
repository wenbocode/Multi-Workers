# Task T-12-PARITY-LOCK: TS↔Python 配置/渲染/指纹 cross-language parity 锁定

## 基本信息
- Stage: 5
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-002, AC-005]
- vc_refs: [VC-027]
- pattern_refs: []

> 说明：T-01（TS 配置层）在 T-06（Python 配置层）落地**之前**就已派发，两侧的字段命名/文件形态/指纹 canonical 规则存在漂移风险。本任务把 T-06 已锁定的契约在 TS 侧钉死，并**修掉发现的漂移**。

## 描述

### 依据（T-06 已落地的事实，不得改写）

- 两层文件形态 `{servers: {<name>: {...}}}`，只有 `servers` 是合法顶层键；`target.yml` 的 `rag:` 段接受 `enabled`/`default_server`/`roles`/`phases`/`budgets`。
- 字段 snake_case（`token_env`/`timeout_ms`/`cli_entry`/`path_roots_file`/`default_server`/`chat_budget`/`time_budget_s`）；`mw_common.RAG_FIELD_CAMEL` 是权威映射表。
- `origin` 键是 snake_case 求值字段路径（`mcp.url`、`mcp.token_env`、`capabilities.graph`、`sources`、`skill` …）。
- `MW_RAG_SERVERS_FILE` 硬覆盖（设定但缺失 → 机器层为空，不回落 HOME）。
- 指纹 canonical JSON：`sort_keys`、`separators=(",",":")`、`ensure_ascii=False`、整值浮点归一为 int；`roles`/`phases` 整块参与、server 条目按启用集过滤；`path_roots_digest` 在 load 时算。
- rag 块字节契约：`packages/multi-workers/test/fixtures/rag-block.golden.md`（347 B，无尾换行）。
- 共享输入 fixture：`packages/multi-workers/test/fixtures/rag/{machine-servers.yml,project-servers.yml,target.yml,rag-roots.json}`（SHA256 见 T-06 output.md）。

### 源码

1. **不要创建/修改 `rag/block.ts`**（该文件由 T-04 拥有，块渲染器与 rag 块字节相等断言在 T-04 的 `rag-tools.test.ts` 里做）。本任务只改 `rag/config.ts`（T-01 产物）并新增 parity 测试。
2. **已识别的具体漂移（PM 预读 T-01 实现所得，必须逐条修正；方向永远是"以 Python/golden 为准"）**：
   - `pathRootsDigest(file)` 现在直接 `fs.readFileSync(file)` —— 相对 `path_roots_file` 会锚到 `process.cwd()`；Python 侧（`mw_common.load_rag_config`）按 **project root（controlRoot）** 解析并写入 `path_roots_digest`。必须改成按 project root 解析（TS 的 `loadRagConfig(controlRoot)` 已有该参数）。
   - `target.yml` 的 `rag:` 段键名：TS 用 camelCase（`RAG_SECTION_KEYS = enabled/defaultServer/roles/phases/budgets`，`ROLE_KEYS` 含 `chatBudget`/`timeBudgetS`，`BUDGET_KEYS` 含 `chat`/`timeS`）；Python 用 **snake_case**（`_RAG_TARGET_KEYS = enabled/default_server/roles/phases/budgets`，`_RAG_ROLE_KEYS` 含 `chat_budget`/`time_budget_s`，`_RAG_BUDGET_KEYS = chat_budget/time_budget_s`）。**同一份 target.yml 不可能两边都认** —— 以 Python 为准把 TS 改成 snake_case（对外暴露的 `RagConfig` 字段名可保持 camelCase，但 **YAML 输入键** 必须是 snake_case）。
   - `origin` 键大小写：TS 现在写 `origin.pathRootsFile`、`origin['mcp.url']` 这类 camelCase 路径；Python 写 snake_case 求值路径（`path_roots_file`、`mcp.token_env`、`capabilities.graph`、`sources`、`skill`）。统一为 **snake_case**（或对外转换，但 parity 测试比较的必须是归一化后的同一集合）。
   - 错误类别：只需保证 `unknown-key` / `unknown-server` 两侧**同名同义**；其余类别（`bad-yaml` / `invalid-shape` / `mcp-missing-url` / `skill-missing-cli` / `enabled-empty-entry`）可各自表述，但要在 output.md 里列出对照表。
3. 新增 `packages/coding-agent/test/suite/rag-parity.test.ts`。

### 测试（`rag-parity.test.ts`，用共享 fixture；读法照 `test/extensions/agent-team-loop-profile-injection.test.ts:550` 的 `new URL("../../../multi-workers/...", import.meta.url)`）

- **golden 字节相等（VC-027）**：若 `rag/block.ts` 已存在（T-04 已落地），断言 `renderRagBlock(...)` 与 `rag-block.golden.md` **逐字节**相等（长度与内容，含"无尾换行"）；若尚未存在，写一条明确的 pending 断言并在 output.md 标注 "covered_by(T-04 rag-tools.test.ts)"（**不要**自己新建 block.ts）。
- **指纹相等（VC-027）**：TS 算出的指纹必须等于 golden 中 `fingerprint=` 的值（同一配置、同一 canonical 规则）。这是最灵敏的漂移探针。
- **origin 表相等（VC-027）**：TS 的 origin 字段集合（经 `RAG_FIELD_CAMEL` 归一）与 Python `load_rag_config` 的 origin 键集合完全相同；逐字段抽查（`mcp.url` project / `mcp.token_env` machine / `sources` project / `skill` machine）。
- **错误类别一致**：非法顶层键 → `unknown-key`；`enabled` 引用未定义 server → `unknown-server`（两侧同名类别）。
- **fixture 完整性**：断言四个 fixture 文件的 sha256 与 T-06 output.md 记录一致（若不一致 → fixture 被改动，必须停下来核对而不是改期望值）。
- Python 侧补一条：`rag_fingerprint(load_rag_config(fixtureProject))` 等于 golden 的 `fingerprint=`（Py 自洽 + 与 TS 对照恒等）。

### 注意

- 发现漂移时的修改方向：**Python/golden 是事实来源**，改 TS；不要为了对齐而改 Python 既有产物（除非发现 Python 侧确有 bug——那要单独记录并说明）。
- 本任务与 T-04 **并行**运行：文件所有权划分——T-12 只改 `rag/config.ts` 与新增 `rag-parity.test.ts`；`rag/block.ts`、`rag/tools.ts`、`worker-mode.ts`、`task-dispatcher.ts`、`ui-bridge.ts` 归 T-04。若你发现自己需要改 T-04 的文件，**停手并在 output.md 说明**，由 PM 决定第二次派发。
- 只改 `rag/**` 与新增测试；既有测试零修改；不 commit；不新增依赖。
- 测试运行：coding-agent 包根 `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-parity.test.ts`。

## 完成判定

- `rag-parity.test.ts` 全绿，输出含 `[VERIFY] VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true`。
- 若修改了 T-01 产物，在 output.md 列出"漂移点 → 修法"清单（供 T-11 写进 `achieved.md`）。
