# Research: RAG 接入的落地接口与既有面（design 阶段）

## 决策问题

支撑 design.md 的以下选型（每条决策的 Pros/Cons 与推荐理由出处）：

- D-001 MCP client 放 TS 还是 Python
- D-002 工具面与 worker 白名单注入方式
- D-003 两层配置载体与合并规则
- D-004 归一化信封与能力表
- D-005 传输选择与降级/熔断
- D-006 长调用心跳与预算落点
- D-007 路径解析实现位置
- D-008 证据行与 audit 判定
- D-009 task.md 注入块与撕裂检查
- D-010 Python CLI/doctor/env 注入点
- D-011 `rag-research` 类型接入白名单 parity 的边界

## 调研方法与出处

- `packages/coding-agent/src/core/extensions/types.ts:449`、`:1246`、`:1337` — `ToolDefinition`（`execute(toolCallId, params, signal, onUpdate, ctx)`）、`registerTool`、`setActiveTools(toolNames)`：本 key 全部工具面的机制，无新机制需求（`execute` 签名实际在 480-486）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:36` — `TOOL_ALLOWLISTS`；`:516-518` — `before_agent_start` handler，`:517` 在其中调用 `pi.setActiveTools(toolsForType(meta.type))`（**每次 agent run 都会执行，不是只跑一次**：工具面注入必须幂等）
- `worker-mode.ts:167` — `parseTaskMd(taskPath)`：逐行扫描 task.md，已解析 `type:` / `timeout:` / `origin:` / `deny_globs`；新字段（`rag_chat_budget:`）沿用同一扫描器
- `worker-mode.ts:556` — 活动追踪 `touch()`；`:576` — `pi.on("tool_execution_update", touch)`：长调用心跳的接收端
- `packages/agent/src/agent-loop.ts:683-689` — 在工具 `onUpdate(partialResult)` 回调中 `emit({type:"tool_execution_update"})`
- `packages/multi-workers/test_autopilot_l0.py:215` — `_parse_ts_allowlists()`（helper 起点）；`:233` — `test_vc023_registry_parity`；`:246-250` — 断言原文 `expected_ts_keys = set(py_reg) | {"coding","review","research","fallback"}` 且 `assert set(ts_reg) == expected_ts_keys`：**TS 侧多一个 key 即失败**
- `packages/multi-workers/autopilot/dispatch.py:64-87` — `REGISTRY`（conductor 派发类型：roadmap-writer/phase-writer/verifier/reviewer/repair；`:47` 只是章节标题）、`:94` `tool_set()`、`:98` `registry_snapshot()`、`:265` 派发校验；`:9` 注释明确"per-type tool sets must stay EXACTLY equal to the Python-side REGISTRY (entry order included)"
- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts:58` — `DISPATCH_ROLE_BY_TYPE`（type→role）；`:71` — `DISPATCHABLE_TYPES = ["coding","review","research"]`（`dispatch_worker`/`/worker` 的类型白名单，`ui-bridge.ts:841` 校验）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts` — `injectWorkspaceProfile(taskPath)`：读 task.md → `resolveWorkspaceConfig(controlRoot)` → marker 幂等追加/整体替换 → 写回；`dispatchTask()` 在 `store.upsert`（`:256`）前调用它——这是 task.md **内容注入/替换**的唯一锚点，**不是唯一的 task.md 写点**（初始创建在 `ui-bridge.ts:1073/1398`）
- `packages/multi-workers/launcher.py:577` `_task_profile_mode()` / `:647` `_check_config_tear()` — 派发时记录的 profile mode 与 spawn 时 active mode 不一致则**拒 spawn** + `[LAUNCHER]` trace 证据（fail-closed 先例，本 key 的指纹检查照此形状）
- `packages/multi-workers/launcher.py:96-103` `_stripped_env()`（生产代码唯一的 `env.pop` 点，ref-verify 已证）；`launcher.py:215` `_build_env()` — **5 个早返回分支**（timi 235 / zai 253 / openai-codex 262 / anthropic|deepseek 285 / 纯 codex 293）+ 末尾通用代理返回（314），共 6 个返回路径 → RAG env 注入须为**调用后的 post-step**，否则要改 6 处
- `launcher.py:135` `_read_task_md_fields()` — 从 task.md 读 `type:`/`model:`；`:107` `_resolve_entry_model()` → `mw_common.resolve_dispatch_model`
- `packages/multi-workers/mw_common.py:136` — `DISPATCH_ROLES = ("main","coding","review","research")`；`:441` — `PROTECTED_AGENT_CONFIG_FILES = (auth.json, models.json, settings.json, oauth.json)`，`is_protected_agent_config`（`mw_common.py:475-478`）同时保护 agent dir 本身；`mw_common.py:53` 已有 `import yaml`（PyYAML 隐式依赖，`mw.py:2787` bootstrap 有检查——故 RAG 配置解析不新增依赖）；`:201` `dispatch_config_path()` — 项目级 `.mw/dispatch.yml` 先例（机器本地、gitignored）
- `packages/multi-workers/mw.py:3407+` — argparse 子命令注册模式（serve/doctor/target/partition/model/toolchain/build/update-env 等），`mw rag` 照此形状
- `packages/multi-workers/README.md` — `mw doctor` 段式输出、target.yml 三段手工维护、dispatch.yml 角色默认链
- `E:\CLI_workspace\OverCode\depot\rag-mcp\setup\mcp-config.json` — streamable-http / JSON-RPC 2.0 / `Mcp-Session-Id` / protocolVersion `2025-03-26` / 无 SSE / 可选 `X-MCP-Token`
- `...\rag-mcp\SKILL.md` §二/§四/§七/§八/§九 — 延迟预算（检索 120s+、chat 600s+）、快照漂移四要点、反模式、错误恢复、反馈闭环
- `...\rag-mcp\references\tools-reference.md` — 10 个工具的返回结构与"局限性"（单源检索、graph 需显式 source、4000 字符截断、impact 只追上游、list_sources 远程无本机路径）
- `.agenticdoc/_arch_snapshot.md` §2 — 可复用资产（parity 锁 / `_stripped_env` / hermetic 测试 / doctor 分段 / fail-closed 校验）

## 发现

1. **工具面注入点已存在**：worker 侧 `setActiveTools` 挂在 `before_agent_start` handler 内（每次 agent run 执行，故必须幂等）；PM 侧工具在 `registerWorkerTools` 注册——RAG 工具只需在 activate 时按项目配置决定是否注册，worker 侧幂等重算工具集即可，不需改 pi 核心（GC-2 满足）。
2. **parity 测试的边界是硬约束**：TS `TOOL_ALLOWLISTS` 多出一个 key 就会让 `test_vc023_registry_parity` 失败（`extra=[...]`）。初版结论（"新增 PM-only 类型必须走 TS 桶 + 改允许列表"）在评审后被否：改测试等于动门禁。正确做法是入 Python `REGISTRY` 并加 `conductor_dispatchable=False`（D-011），parity 测试零修改。
3. **task.md 注入锚点与写点不是一回事**：内容注入/替换的唯一锚点是 `injectWorkspaceProfile`（TS）+ `dispatch.py render_task_md`（Python conductor）；初始创建另有 `ui-bridge.ts:1073/1398` 两处（都经 `dispatchTask`）。RAG 块应在同一锚点追加独立 marker，且必须双侧都实现。
4. **撕裂检查先例完整**：`_check_config_tear` 证明"任务记录态 vs spawn 时活动配置"的比对是该仓既有纪律（fail-closed + `[LAUNCHER]` trace）。RAG 的"派发时选用的服务/端点"同样需要指纹，否则配置切换后 worker 静默换了知识库。
5. **env 注入必须绕开 6 分支**：`_build_env` 每个 provider 分支各自 return，RAG 注入若逐支添加会复制 6 次；`_stripped_env` 是唯一的剥离点，RAG token 应在此剥离、在 post-step 按项目启用集注入（凭证隔离语义一致）。
6. **路径解析的两种实现代价差异大**：调用 `resolve_path.py` 需 python 进程 + 参数往返；TS 内联只需读一个 JSON 映射 + `fs.existsSync`——而"引用可核对"是 AC 的核心判据，每次调用都要做，故选内联。
7. **`rag_chat` 的预算需要落盘**：worker 一次任务内可能多次调用（跨 turn），进程内计数在重启/续跑后失效；落 worker 目录的 JSON 计数更稳（与 `[CHECKPOINT]`/trace 同目录，PM 可见）。
8. **doctor 与 audit 都是只读聚合**：`mw doctor` 已有"段 + issues + --json"结构，`rag` 段直接复用；audit 是产出物扫描器（新件），只读、退出码 0/1/2 三级（与 `mcp_call.py` 的 0/2/3 语义区分开）。

## 结论 → 决策映射

| 发现 | 决策 |
|------|------|
| 1, 5, 6 | D-001 客户端在 TS、D-010 env post-step 注入、D-007 路径解析内联 |
| 2 | D-011 `rag-research` 走 TS-only 桶 + 测试允许列表，不动 REGISTRY |
| 3, 4 | D-009 双侧同锚注入 + 指纹撕裂检查（照 `_check_config_tear` 形状） |
| 1, 7 | D-002 工具注册按配置门控；D-006 预算落盘 + `onUpdate` 心跳 |
| 5 | D-003 `.mw/` 项目层 + `~/.agents/` 机器层；D-010 剥离后注入 |
| 8 | D-008 trace 证据行 + `mw rag audit` 只读判定 |
| rag-mcp 协议/反模式/局限 | D-004 归一化信封 + 能力表；D-005 传输顺序与熔断 |
