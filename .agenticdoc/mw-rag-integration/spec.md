# Spec: mw-rag-integration

> Key: mw-rag-integration
> 创建时间: 2026-09-22 11:58
> 状态: draft
> 交付分期: K1（配置层 + 工具面 + 证据）+ K2（rag-research 类型 + 调研文档 + audit）；K3（require 硬门禁）不在本 key

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建 Agent Team 协作框架」中"项目级目标对齐（goal.md），Worker 执行过程中追踪 goal 一致性"这一条——把项目专属的外部知识库（如 UE 引擎源码 RAG）变成各阶段的**可配置、可取证**输入面，使 spec/design/coding/review/evidence 引用的是库中事实而非模型记忆，同时保证非适用项目（本框架仓自身等）零影响。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-2: 不修改 pi 核心——全部功能通过 Extension API 与 mw CLI 实现；TS 改动限 `packages/coding-agent/src/extensions/agent-team-loop/`，Python 限 `packages/multi-workers/`
  - GC-5: 工具白名单按任务类型——RAG 工具面与新增类型的白名单变更必须与 Python 侧 REGISTRY 保持奇偶一致（已有 parity 锁测试）
  - GC-6: Worker 超时看门狗——分钟级 RAG 调用必须与 activity watchdog 共存（`onUpdate` 心跳），并有单任务调用预算与墙钟上限
  - GC-7: goal.md 作为项目级锚点——RAG 的启用与"必需用"声明是项目级配置（target.yml），**不写入 goal.md**
  - GC-1: 不引入中心化调度器——服务表与选用声明都是文件，不新增常驻协调组件；RAG 服务本身是外部依赖，不进入框架常驻进程
- 冲突：无。唯一需要注意的是 RAG 服务是**外部可选依赖**，其不可用不得降级为框架自身故障（见 §2.2 与五层降级语义）。
- 预期收益（done 时在 achieved.md 对照判定）：
  - UE/OverCode 类项目的 spec/design 调研从"agent 猜符号"变为"自然语言检索 → 符号下钻"，改码前有影响面证据。判定：受控 fixture 服务下，工具发出的请求参数与返回归一化字段断言全过（AC-005/AC-006）。
  - review/evidence 的声明核对有可机械解析的引用，且引用的本地可达性可机械判定。判定：`mw rag audit` 对含缺失引用的产出物返回非 0（AC-015）。
  - 非 RAG 项目零影响，是结构性保证而非运行时判断。判定：未启用配置下 `rag_*` 注册数为 0（AC-001）。

## §1 功能概述

### 1.1 目标

把外部 RAG（MCP 服务）接入 AgenticTask 工作流：

1. **两层服务表**：机器级 `~/.agents/rag-servers.yml` 声明 N 个服务（`transport: mcp | skill | both`），项目级 `<control>/.mw/rag-servers.yml` 可覆盖/新增同名服务。
2. **项目级选用**：`target.yml` 的 `rag:` 段声明本项目启用哪几个服务、哪些角色/阶段必需用、默认 server/source 与 rewrite 默认、`rag_chat` 预算。
3. **统一工具面**：扩展内实现 streamable-http MCP client，暴露精选工具（`rag_search` / `rag_symbol` / `rag_graph` / `rag_impact` / `rag_sources` / `rag_feedback`，加仅 `rag-research` 类型可见的 `rag_chat`）；`transport: skill` 的服务由同一工具面背后的脚本桥实现，agent 不感知差异。
4. **引用归一化**：返回即带 `local_path`（本机绝对路径）/`exists`/`line_hint`/`snapshot_warning`，引用字符串 `server:source:file_path:line` 由工具给出，不由模型拼。
5. **可取证降级**：五层降级语义 + 五类证据行（`rag_call` / `rag_fallback` / `rag-unavailable` / `rag-rewrite-degraded` / `rag-required-missing`）。
6. **K2 调研闭环**：`rag-research` 任务类型（唯一可用 `rag_chat`）产出 `.agenticdoc/<key>/rag/<server>-<slug>.md`，`mw rag audit` 机械核对产出物引用。

### 1.2 技术栈 / 语言

- TypeScript：`packages/coding-agent/src/extensions/agent-team-loop/rag/`（pi Extension API，无新依赖）
- Python stdlib：`packages/multi-workers/`（target.yml schema 与校验、launcher env 注入、task.md 注入、`mw rag list|probe|audit`、doctor 段）
- MCP 传输：streamable-http + JSON-RPC 2.0 over HTTP POST，protocolVersion `2025-03-26`，`initialize` 响应头取 `Mcp-Session-Id` 且后续请求必带，不使用 SSE，可选 `X-MCP-Token`
- 文档：项目内薄 skill `mw-rag`（何时用哪个服务/阶段、引用格式、反模式），方法论指向 rag-mcp 的 SKILL.md（不 fork、不改分发包）

### 1.3 核心用户场景

1. **PM spec/design 调研**：在 UE 项目窗口用自然语言问引擎机制 → `rag_search`（rewrite + 多轮）→ 取 `qualified_name` → `rag_symbol`/`rag_graph` 下钻 → 每条结论带本机可核对的引用 → 写进 spec/design。
2. **coding 影响评估**：改码前 `rag_impact` 拿 blast radius（callers / affected_files），结合本地读码判断，不靠模型记忆。
3. **review/evidence 强验证**：`rag_graph` / `rag_impact` 反查声明涉及的调用关系与影响面；`rag_*` 返回的每条引用本地存在性可判定（`exists` + audit）。
4. **库调研（K2）**：PM 派发 `rag-research` 任务，用 `rag_chat`（预算 2 次）做全召回调研，产出独立文档，PM 读文件而不是等模型。
5. **非适用项目**：会话中根本没有 `rag_*` 工具，派发产物无任何 rag 注入行。

### 1.4 范围说明（不做什么）

- 不做 `require: true` 的硬阻断（v1 只告警 + 证据行；K3 另立 key）
- 不做跨服务语义自动路由：agent 未指定 `server` 时只用角色/阶段声明的默认值，不做自动挑选
- 不 fork、不重新分发 rag-mcp skill 包；不改其 SKILL.md / scripts
- 不做 `rag_chat` 以外的生成类工具；不向 agent 暴露 `set_verbose`
- 不做通用 MCP 客户端框架：只实现本项目所需的工具映射 + 一种传输 + 一个适配器族
- 不改 worker watchdog 的阈值逻辑（心跳是工具侧责任）

## §2 业务约束

### 2.1 平台 / 环境

- Windows + PowerShell 5.1 为主环境（验收输出走文件/read 工具）
- Python 3.x stdlib only，无新 pip 依赖；TS 沿用现仓依赖，不新增 npm 依赖
- 参考实现：`E:\CLI_workspace\OverCode\depot\rag-mcp`（streamable-http，默认 `http://localhost:8100/mcp/`）
- 服务可用性是外部条件：服务可以后启动、可以中途挂掉；框架必须能分别表达"未启用/已启用但没起/调用失败"

### 2.2 性能指标

- 检索类工具超时 180s（rag-mcp 建议检索 ≥120s）
- `rag_chat` 单次上限 600s；`rag-research` 类型默认 `rag_chat` 预算 2 次/任务（并发调用不超发，按预留计数），超预算调用被工具拒绝
- 任务级累计 RAG 时间预算：task.md `rag_time_budget_s`（缺省 900s），累计超限后拒绝新的 RAG 调用（防止多次昂贵调用叠加撞墙钟）
- 剩余墙钟守卫：任务已用时间超过墙钟预算 70% 时拒绝 `rag_chat` 等昂贵调用（便宜检索仍允许）
- 所有可能长耗时的调用（不只 `rag_chat`）统一每 ≤30s 触发一次 `tool_execution_update`，保证 10 分钟 idle 看门狗不误杀
- activate 阶段的探活在 5s 内返回（只探已启用服务），不阻塞窗口启动
- 熔断阈值：同一 server 在同一 worker 内连续 3 次调用失败后熔断

### 2.3 安全约束

- token 只以 `token_env`（环境变量名）出现在配置中；由 launcher 注入 worker env；task.md / trace.log / output.md / evidence 不得出现明文 token
- 机器级服务表落 `~/.agents/rag-servers.yml`，**不写** `~/.pi/agent/` 下受保护集合（`auth.json` / `models.json` / `settings.json` / `oauth.json` 及 agent dir 本身）
- 配置由人维护；agent 不代为修改机器级服务表（P-002 同规则）
- `mw rag audit` 只读，不修改产出物

### 2.4 集成依赖

- pi Extension API：`registerTool` / `setActiveTools` / `ToolDefinition.execute` 的 `onUpdate` / 事件 `tool_execution_update` / `promptGuidelines`
- mw 侧：`target.yml` 配置加载与 fail-closed 校验惯例、launcher `_build_env` env 注入、task.md 生成、`mw doctor` 分段输出、worker 工具白名单 + Python REGISTRY parity
- 外部：MCP streamable-http 服务；`transport: skill` 要求包内提供 JSON-RPC CLI 入口（契约：`<python> <cli_entry> <tool> --arg k=v ...`，stdout 单段 JSON，退出码 0/2/3）

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-22T12:10:00+08:00，编号永不回收

### K1 配置层与工具面

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 target.yml 无 `rag:` 段或 `rag.enabled: []` 的项目下，pi 会话启动后注册表中 `rag_*` 工具数量为 0，且 `dispatch_worker` 生成的 task.md 中 `rag` 注入行命中数为 0 |
| AC-002 | 机器级与项目级同时定义同名 server S（项目级覆盖 `mcp.url`）时，`mw rag list --project <dir> --json` 输出的 S.url 等于项目级值，且来源字段标注为 `project` |
| AC-003 | 在 target.yml `rag.enabled` 引用机器级/项目级都未定义的 server 名时，`dispatch_worker` 拒绝派发：worker 目录未创建、`_workers.parallel` 无新增行、错误消息含 `unknown rag server` 与该 server 名 |
| AC-004 | 启用服务 A/B 后，会话注册的工具集恰为 `rag_search` / `rag_symbol` / `rag_graph` / `rag_impact` / `rag_sources` / `rag_feedback` 六个；`server` 参数为包含 A 与 B 的密闭枚举；`rag_chat` 不在其中；`rag_graph` 打到声明无图能力的 server 时返回类型化错误且错误文本含"no knowledge graph" |
| AC-005 | 对返回 `engine::Runtime/Renderer/X.cpp` 的 fixture 结果，`rag_search` 返回项含 `local_path`（path_roots 映射后的本机绝对路径）、`exists`（bool）、`line_hint`、`snapshot_warning: true`，且 `citation` 字段形如 `server:source:file_path:line`；path_roots 缺失时 `exists=false` 且返回映射文件配置提示（不返回错误路径） |
| AC-006 | 角色为调研类（spec/design 阶段）调用 `rag_search` 未显式传 `multi_rounds`/`auto_rewrite` 时，适配器为该次调用解析出的重写开关必须为 `multi_rounds=true, auto_rewrite=true`；角色为 coding 时为 `false`。落到线上请求时按 AC-018 的映射表转换（开关为 true → 实际工具名 `rag_search_multi_rounds`，业务参数保留），fixture 服务记录的**实际工具名与参数**必须与映射结果一致 [REVISED @ 2026-09-22] |
| AC-007 | 服务未启动时：activate 仍注册工具且描述含 `[unreachable at session start]`；首次调用在 5s 内返回类型化错误并追加 `rag-unavailable` 证据行；同一 server 连续 3 次失败后第 4 次调用不发起网络请求（fixture 服务请求计数不增）且错误文本含熔断提示 |
| AC-008 | 每次成功的 `rag_*` 调用在 worker `trace.log` 追加一行 `rag_call`，含 server / tool / 实现路径（`mcp` 或 `cli`）/ 耗时 / 结果条数；走脚本桥兜底时额外追加 `rag_fallback` 行 |
| AC-009 | token env 值为 `SECRET123`（配置只持有 `token_env` 名，不含值）时，对 task.md / trace.log / output.md / evidence / worker.log / `.mw/` 派发与 launcher 日志的 `SECRET123` 扫描全部 0 命中，worker 命令行 argv 不含该值，且 worker env 中存在对应 `token_env` 变量 [REVISED @ 2026-09-22] |
| AC-010 | target.yml 声明 `roles.review.require: true`，review worker 全程未调用任何 `rag_*` 时：worker 终态仍为 done（不阻断），`trace.log` 含 `rag-required-missing` 行，output.md 的 evidence 段含"RAG 未生效"标注 |

### K2 调研类型与核对器

| AC 编号 | 描述 |
|--------|------|
| AC-011 | `rag-research` 类型任务下发后，worker 的活动工具集为 `read/find/grep/ls` + RAG 全集（含 `rag_chat`）；TS 侧白名单与 Python 侧 REGISTRY 的 parity 测试通过且两者条目顺序一致 |
| AC-012 | task.md 声明 `rag_chat_budget: 2` 时，第 3 次 `rag_chat` 调用被工具拒绝（错误文本含预算与已用次数），且不产生服务端请求（fixture 计数不增） |
| AC-013 | 在把 idle 阈值调低到 60s 的测试配置下，单次 180s 的 fixture 慢 `rag_chat` 调用期间 worker 未被 idle 看门狗终止（进程存活、`rag_call` 行含实际耗时），且调用期间观测到 >= 4 次工具进度更新（`tool_execution_update`）且相邻间隔 < 60s [REVISED @ 2026-09-22] |
| AC-014 | `rag-research` 任务结束后必须产出 `.agenticdoc/<key>/rag/<server>-<slug>.md`，且含六个固定小节（查询 / 结论 / 引用 / 未解决 / 快照 / 影响面）；「引用」小节必须逐条给出 `citation` 与本地核对状态（`local_path` / `exists`），无法核对项与未解决项必须列入「未解决」；每条引用匹配 `server:source:file_path:line` 形态 [REVISED @ 2026-09-22] |
| AC-015 | `python mw.py rag audit --project <dir> --json` 对产出物引用做解析与本地存在性核对，输出含 `missing` 与 `unverified` 计数；引用指向不存在文件的负例退出码非 0 且 `missing >= 1`；`require: true` 角色未调用 RAG 时输出含 `rag-required-missing` |
| AC-016 | 服务端 LLM 不可用导致 rewrite 降级时（fixture 返回降级标记），`rag_search` 返回结果带降级标记字段，并追加 `rag-rewrite-degraded` 证据行；服务端可用时不出现该行 |
| AC-017 | (K1) 在 `rag.enabled` 非空的项目执行 `mw rag sync --project <dir>` 后，`<control>/.pi/skills/mw-rag.md` 存在且与框架仓 `packages/multi-workers/skills/mw-rag/SKILL.md` 字节一致；在 `rag.enabled` 为空的项目执行同一命令后该文件不存在；pi 会话 activate 自身既不创建也不删除该文件（会话前后该路径的存在性一致） |
| AC-018 | 六个逻辑工具名必须映射到 `overcode-v1` 参考服务（OverCode rag-mcp）的真实工具名：`rag_graph` → `graph_query`；`rag_sources` → `list_sources` + `list_collections` 两次调用合并为一个信封（每项保留各自 source 归属）；`rag_search` 在重写开关为 true 时改调 `rag_search_multi_rounds`；其余逻辑名与参考服务同名。映射必须以数据表形式声明在适配器内（v1 不得散落逐工具硬编码）；fixture 服务记录的实际请求工具名必须等于映射结果 [ADDED @ 2026-09-22] |

## §4 风险与未决项

- **风险：rewrite 在服务端不可见 → 结果不可从证据重放**。缓解：review/verifier 的强验证禁用 rewrite 检索，只认 `rag_graph` / `rag_impact` 这类确定性工具；证据行记录 agent 传入的 query 原文并标注"服务端 rewrite 不可见"。
- **风险：rewrite 依赖服务端 LLM，不可用时静默降级为关键词检索**。缓解：降级标记 + `rag-rewrite-degraded` 证据行（AC-016）。
- **风险：RAG 结果为索引快照，行号漂移**；直接照抄会改错行。缓解：工具返回 `snapshot_warning` + 引用必须经本地 `exists`/audit 核对；skill 与 promptGuidelines 明写"本地文件为事实源"。
- **风险：MCP 协议或工具集漂移**（服务端演进，如新增/改名工具、返回结构变化）。缓解：适配器归一化 + 探活 + 类型化错误；结构不符时按 rag-mcp §九 经 `rag_feedback` 反馈，不静默绕过。
- **风险：`rag_chat` 分钟级延迟拖垮任务**。缓解：独立类型 + 调用预算 + 单次 600s 上限 + 任务级累计时间预算 + 剩余墙钟守卫 + 心跳保活。
- **风险：AI/服务端返回的 `file_path` 含 `::`（如 `engine::Runtime/Renderer/X.cpp`），朴素切分会把引用解析错**。缓解：固定引用语法（左侧 server/source、右侧 line、中间全部归 file_path）并以契约 fixture 锁定（AC-005/AC-014 的 VC 覆盖 `::`、空格、Windows 反斜杠形态）。
- **风险：MCP 请求已送达但响应丢失时自动切 CLI 兜底，会对非幂等/昂贵工具重复副作用（`rag_feedback` 重复落盘、`rag_chat` 重复计费）**。缓解：仅在"可证未送达"（连接建立失败）且工具只读时允许自动兜底（D-005）。
- **风险：`transport: skill` 的包没有合规 CLI 入口**。缓解：配置校验期即拒绝（fail-closed），并在 `mw rag probe`/doctor 中给出明确原因。
- **待确认**：`~/.agents/rag-servers.yml` 在非 Windows 目标机器上的可写性与目录约定是否需 env 覆盖（design 阶段定）。
- **待确认**：`rag-research` 是否同时暴露给 conductor/autopilot 派发路径（本 key 先只做 PM `dispatch_worker` + `/worker` 路径，design 阶段定边界）。

## §5 记忆前馈

### 可复用资产

- **pi 扩展工具注册 + 心跳**：`ToolDefinition`（`core/extensions/types.ts:449`，`execute` 第 4 参数 `onUpdate`）与 `worker-mode.ts:576` 的 `tool_execution_update → touch()`；分钟级调用复用既有活动信号，不新增机制、不改看门狗阈值。
- **工具白名单 + parity 锁**：`worker-mode.ts:36` 的 `TOOL_ALLOWLISTS` 与 Python `autopilot/dispatch.py` REGISTRY 已有奇偶校验测试——新增 `rag-research` 类型直接沿用该锁，不新造校验。
- **target.yml 配置面与 fail-closed 先例**：`mw_common` 的 target 配置加载/校验 + launcher 撕裂校验（坏配置拒绝派发）——`rag:` 段校验与 AC-003 复用同一模式。
- **凭证隔离与 env 注入模板**：launcher `_stripped_env` + timi/zai 直连分支的 `resolve_credential → 注入 api_key_env` 写法——RAG token 按同模式注入，零新机制。
- **doctor 分段诊断**：`mw doctor` 的段式 + `--json` 输出惯例——新增 `rag` 段（`mw rag probe` 复用同一实现）。
- **hermetic 测试模式**：fake Popen / fixture 服务的既有写法（`test_serve_doctor.py` 的 TestServeSupervision）——AC-004~AC-016 全部走本地 fixture MCP 服务，不依赖真机 RAG 服务。
- **protected-config guard（TS + Python 双侧）**：`PROTECTED_AGENT_CONFIG_FILES` 与 `assert_not_protected_agent_config`——机器级服务表命名与落点据此避让（`~/.agents/` 而非 `~/.pi/agent/`）。
- **evidence/research 留底惯例**：`advance_phase.py` 门禁要求的 `evidence/research/*-*.md` 命名与结构，本 key 直接沿用。

### 需规避坑点

- **P-001（PS 文本管道把无 BOM UTF-8 变 mojibake）**：spec/配置/任务文档/证据全部用 write/edit 工具或 Python 显式 `encoding="utf-8"` 写入；禁用 `Get-Content`/`Set-Content`/`WriteAllText` 往返。RAG 调研文档中文化程度高，是本 key 最易踩的一处。
- **P-002（会话内改跨窗口共享配置）**：机器级服务表不放进受保护集合，且明确"配置由人维护、agent 不代改"；worker 侧若有写入需求一律拒绝。
- **P-003（`open(w)` 先截断后求值）**：服务表/审计报告写入一律"先算后写"（算出完整内容再 `write_text`）；并发读场景用临时文件 + `os.replace`；复验除退出码外必须断言文件非空 + 关键锚点（AC-002/AC-015 的 JSON 断言按此写）。
- **P-004（命令文本词法分析漏拦）**：本 key 不向 agent 下发可自由拼接的 shell 命令（脚本桥由扩展构造参数数组，不走 shell 字符串）；若 design 阶段出现任何命令构造，回归必须含正反例双向。
