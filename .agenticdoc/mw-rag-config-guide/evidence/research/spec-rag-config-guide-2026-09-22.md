# 调研证据: mw-rag-config-guide / spec 阶段（2026-09-22）

目的：在写 spec 前把「配置文件的真实字段集合」与「既有写入/文档先例」从代码里核出来，避免文档靠记忆写。

## 1. 服务表字段集合（唯一真源：`packages/multi-workers/mw_common.py`）

`_rag_finalize_server`（`mw_common.py:518` 起）接受的**全部**键：

| 键 | 校验 | 默认 | 出处 |
|---|---|---|---|
| `transport` | 必须 ∈ `("mcp","skill","both")`（`RAG_TRANSPORT_VALUES`） | `mcp` | `mw_common.py:519-526` |
| `adapter` | 必须 == `overcode-v1`（`RAG_ADAPTER_DEFAULT`） | `overcode-v1` | `:527-531` |
| `path_roots_file` | 非空字符串或 `null`；文件内容 sha256 进 `path_roots_digest` | `None` | `:532-535`, `_rag_path_roots_digest` |
| `sources` | 非空字符串列表 | `[]` | `:536-541` |
| `capabilities` | 仅 `graph`/`chat`/`rewrite`，各自必须 bool | 全 `false` | `_rag_finalize_capabilities` |
| `mcp.url` | 非空字符串；`transport ∈ {mcp, both}` 时**必需** | 无 | `_rag_finalize_mcp` |
| `mcp.token_env` | 非空字符串或 `null`（**只写变量名**） | `None` | 同上 |
| `mcp.timeout_ms` | 正整数 | `180000`（`RAG_DEFAULT_MCP_TIMEOUT_MS`） | 同上 |
| `skill.cli_entry` | 非空字符串；`transport ∈ {skill, both}` 时**必需** | 无 | `_rag_finalize_skill` |
| `skill.dir` | 非空字符串或 `null` | `None` | 同上 |
| `skill.timeout_ms` | 正整数 | `180000` | 同上 |

顶层：`{servers: {<name>: {...}}}`，**只有 `servers` 合法**（`_rag_layer_servers` 报 `unknown-key`）。

## 2. `target.yml` 的 `rag:` 段字段集（`_rag_finalize_target`）

| 键 | 语义 | 默认 | 出处 |
|---|---|---|---|
| `enabled` | 服务名列表；**空或缺省 = 全关**；引用未定义服务 → 报 `unknown rag server` | `[]` | `_rag_finalize_target`（`enabled_raw is None → []`） |
| `default_server` | 解析兜底的 server 名；必须已定义 | `None` | 同上 |
| `roles.<role>` | `{server, source, require, rewrite}`（`_RAG_ROLE_KEYS`） | `{}` | `_rag_finalize_specs` |
| `phases.<phase>` | `{server, source, require, rewrite}`（`_RAG_PHASE_KEYS`） | `{}` | 同上 |
| `budgets.chat_budget` / `time_budget_s` | 非负整数 | `2` / `900` | `_rag_finalize_budgets` |

TS 侧同名（`rag/config.ts:223` `RAG_SECTION_KEYS = {enabled, default_server, roles, phases, budgets}`；`parseEnabled` 缺省 → `[]`），
**两侧语义一致**（已交叉核对，非单侧推断）。

## 3. 既有写入先例（不要发明新写法）

- `mw.py::_cmd_rag_sync`（`mw.py:1198`）：`<project>/.pi/skills/mw-rag.md` 的**唯一写入方**，sha256 比对后决定写/删 → 模板命名的参照。
- `mw.py::_apply_bootstrap_line` + `_atomic_write_yml`：**文本级**改写 `target.yml`（保注释），仅在文件是 v1/不可解析时才走 flat 行写；
  `mw target set` 的注释明确写了「v1 flat 写与历史字节一致」的约束。→ `rag init` 追加 `rag:` 段必须沿用文本级追加，禁止 YAML round-trip。
- `mw.py::_target_template(...)`：新 `target.yml` 的模板构造先例。

## 4. 文档先例

- `packages/multi-workers/docs/dual-toolchain-practice-guide.md`（46 KB）是本仓 `docs/` 里既有手册的体例：分节 + 可复制代码块 + 字段表。
- 上位 key 记录过用户偏好与坑点：`_pitfalls.md` P-005（有实现没人用）、P-006（`[VERIFY]` 通道）、P-008（文档静默过期 → 需 parity 测试）。

## 5. 已核实的"疑似文档缺陷"结论

一度怀疑 README 写错 `enabled` 缺省语义（曾读到「缺省 = 全启」）。**复核后为误读**（控制台 mojibake）：
`packages/multi-workers/README.md:270` 实为 `enabled: [overcode]              # 启用集（空或缺省 = 全关）`，与实现一致。
故本 key **不包含** README 语义更正，只新增手册与命令。
