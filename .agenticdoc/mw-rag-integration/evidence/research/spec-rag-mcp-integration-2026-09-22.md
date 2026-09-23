# Research: RAG(MCP) 接入 AgenticTask 工作流（spec 阶段）

## 决策问题

回答 spec 的以下关键决策：

- §1 范围：RAG 以什么形态接入（MCP client / Python 代理 / 纯脚本桥），暴露哪些工具，谁可用
- §2 约束：平台与性能约束（长调用 vs worker watchdog、超时预算、无新依赖）
- §2 安全：凭证明文与机器级配置落点（受保护配置集合避让）
- §4 风险：快照漂移、rewrite 不可重放、服务不可用降级
- §3 AC：K1/K2 的可机械判定断言

## 调研方法与出处

全部为本机实测/读码所得，无外部网络调研。

- `H:\git\Multi-Workers\packages\coding-agent\README.md:496` — "**No MCP.** Build CLI tools with READMEs ... or build an extension that adds MCP support."
- `H:\git\Multi-Workers\packages\coding-agent\docs\usage.md:301` — "It intentionally does not include built-in MCP, sub-agents, permission popups, plan mode, to-dos, or background bash."
- `H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\worker\worker-mode.ts:36` — `TOOL_ALLOWLISTS`：coding `read/write/edit/bash/find/grep/ls`；review `read/find/grep/ls`；research `read/find/grep/ls/bash`；verifier/reviewer 同 review（**无 bash**）
- `...\worker-mode.ts:556` — 活动追踪：`message_update` / turns / `tool_execution_start` / `tool_execution_update` / `tool_execution_end` 均 `touch()` 刷新 `lastActivityAt`；idle 看门狗仅在完全无活动时杀
- `...\worker-mode.ts:576` — `pi.on("tool_execution_update", touch)`：长工具调用只要发 update 即不触发 idle 判死
- `H:\git\Multi-Workers\packages\coding-agent\src\core\extensions\types.ts:449` — `ToolDefinition`：`name/description/promptSnippet/promptGuidelines/parameters/execute(toolCallId, params, signal, onUpdate, ctx)`
- `...\types.ts:1246` `registerTool`、`:1337` `setActiveTools(toolNames: string[])`
- `H:\git\Multi-Workers\packages\agent\src\agent-loop.ts:683-689` — 在工具 `onUpdate(partialResult)` 回调中 `emit({type:"tool_execution_update", ...})`（扩展侧可主动心跳）
- `E:\CLI_workspace\OverCode\depot\rag-mcp\SKILL.md` §二 — 接入三情形 + 延迟预算：检索类秒级~十秒级；`rag_chat` **分钟级（41s~9min）**；MCP 客户端超时建议检索 ≥120s、生成 ≥600s
- `...\rag-mcp\SKILL.md` §四 — 快照漂移四要点：RAG 为索引快照、本地文件为事实源、行号可能漂移、改码/评审前须本地核对
- `...\rag-mcp\SKILL.md` §七 — 反模式：2（`rag_chat` 当调研主力）、3（图查询当运行时真相）、5（单轮检索定覆盖）、7（能读码却让 LLM 总结）、8（`set_verbose` 当常规开关）
- `...\rag-mcp\SKILL.md` §八 — 错误恢复：`initializing` 等 30-60s 重试；无图源需显式 `source`；"symbol not found" 先 `rag_search` 拿限定名
- `...\rag-mcp\SKILL.md` §九 — 反馈闭环：工具报错/结构漂移须经 `submit_feedback` 传回，不得静默绕过
- `...\rag-mcp\setup\mcp-config.json` — `transport: streamable-http`，`url: http://localhost:8100/mcp/`，JSON-RPC 2.0 over HTTP POST，`initialize` 返回 `Mcp-Session-Id`（缺失 → HTTP 400），protocolVersion `2025-03-26`，不使用 SSE，可选 `X-MCP-Token`
- `...\rag-mcp\references\tools-reference.md` — 9+1 工具的参数/返回结构/局限（`rag_search` 单源、`graph_query` 需显式 source、`rag_symbol` 4000 字符截断无标记、`rag_impact` 只追上游 callers、`list_sources` 远程接入时 source_root 不可用）
- `H:\git\Multi-Workers\packages\multi-workers\README.md` — target.yml（dual/partition 配置面）、`mw doctor`、`dispatch.yml` 角色默认、`_build_env` 凭证隔离、worker 白名单/watchdog 是 pi worker-mode 特性
- `H:\git\Multi-Workers\packages\multi-workers\mw_common.py:441` — `PROTECTED_AGENT_CONFIG_FILES = (auth.json, models.json, settings.json, oauth.json)`；`is_protected_agent_config` 同时保护 agent dir 本身；Python 侧 `assert_not_protected_agent_config`
- `H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\shared\protected-config.ts:43` — TS 侧同一集合；`:36` 明确 extensions 目录不受保护
- `H:\git\Multi-Workers\.agenticdoc\_arch_snapshot.md` §2 — 可复用资产清单（白名单 parity 锁、`_stripped_env`、hermetic 测试、doctor 分段、target fail-closed）
- `H:\git\Multi-Workers\.agenticdoc\_pitfalls.md` P-001~P-004 — 编码损坏 / 跨窗口共享配置 / 先截断后求值 / 命令词法漏拦

## 发现

1. **pi 无 MCP 是一等设计决定**，不是缺失。RAG 接入必须由扩展提供工具面（`registerTool`），或退化为 agent bash + CLI 脚本；后者在 review/verifier 档直接不可达（白名单无 bash）。
2. **长调用与 watchdog 可以共存**：`tool_execution_update` 是活动信号，扩展侧 `execute(...)` 的第 4 个参数 `onUpdate` 即心跳入口——分钟级 `rag_chat` 不需要改看门狗阈值。
3. **MCP 协议面窄且明确**：streamable-http + 单次 `initialize` 拿 session id + 后续每请求带 id；服务端不使用 SSE，实现成本可控。
4. **服务端 rewrite 改变了工具定位**：`rag_search`/`rag_search_multi_rounds` 的 `auto_rewrite` 让自然语言直接按库改写 query，agent 不必先猜 qualified name；但改写发生在服务端，参数面不可见 → 结果不可重放，且依赖服务端 LLM。
5. **`rag_chat` 有真实落地位**（库调研产出文档），但延迟 41s~9min、且是 LLM 二次综合，只能当线索、必须配本地核对与调用预算。
6. **"可核对引用"是唯一有意义的"用过了"判据**：RAG 返回的是索引快照路径（`engine::` 前缀），必须先经 path-roots 解析成本机路径并做存在性检查，否则"引用"无法核对。
7. **机器级配置落点必须避让受保护集合**：`~/.pi/agent/` 下 4 个文件名与 agent dir 本身受硬拦截；`~/.agents/`（rag-mcp 自身 skill 安装约定）无此约束。

## 结论 → 决策映射

| 结论 | 决策 | spec 位置 |
|------|------|-----------|
| 1, 3 | 方案 A：扩展内实现 MCP client（streamable-http），保留 skill 包做方法论与脚本桥 | §1.1, §2.4 |
| 1 | 未启用即不注册工具（非 RAG 项目结构性零影响） | AC-001 |
| 2 | 长调用用 `onUpdate` 心跳；`rag_chat` 另设墙钟上限与调用预算 | §2.2, AC-012, AC-013 |
| 4 | rewrite 按角色/阶段默认；review 强验证禁用 rewrite 检索；降级标记留证 | AC-006, AC-016, §4 |
| 5 | 新增 `rag-research` 任务类型 + 独立调研文档（六小节）+ `rag_chat` 预算 | AC-011, AC-012, AC-014 |
| 6 | 工具返回即归一化 `{local_path, exists, line_hint, snapshot_warning}`，引用字符串由工具给出 | AC-005 |
| 7 | 机器级服务表落 `~/.agents/rag-servers.yml`；token 仅以 `token_env` 名出现 | §2.3, AC-009 |
| 3, 8（错误恢复） | 五层降级语义（未启用不可见 / 探活失败仍注册并标注 / 运行失败熔断 / require 只告警 / 未调用告警） | AC-007, AC-010 |
| 9（反馈闭环） | 保留 `submit_feedback` 工具映射（`rag_feedback`） | AC-004 |
| 10（工具局限） | 适配器归一化 + 类型化错误 + 能力标注 | AC-004, AC-005 |
