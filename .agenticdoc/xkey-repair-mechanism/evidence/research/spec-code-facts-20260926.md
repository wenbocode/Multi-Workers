# Research RQ-1：框架现有能力的机器事实

> key: xkey-repair-mechanism ｜ 类型：只读调研 ｜ 证据文件（唯一可写产物）
> 生成时间：2026-09-26 ｜ 调研对象：`packages/multi-workers/`（重点 `autopilot/conductor.py`、`autopilot/config.py`、`autopilot/dispatch.py`、`autopilot/closure.py`、`mw_common.py`、`launcher.py`、`mw.py`），并下钻到 enforcement 实际发生处 `packages/coding-agent/src/extensions/agent-team-loop/`。

## 决策问题

逐条回答 spec §4 R-1 与 §2.4 依赖表所依赖的“框架现有能力”的机器事实，为 design 决定“交接登记机器可读化 / gate 新增 / 受限写面 / 全量红分类 / 开关落点”提供依据：

- Q1 跨 key 交接登记（`cross_key_test=… owner=… handoff=registered not_fixed_by_this_key=True`）是机器字段还是 L3 散文？
- Q2 stalled-gate / 人工 gate 如何抬起、作答、被谁读、超时语义？新增 gate 类型要改哪些点？
- Q3 任务 write-face / 工具白名单 / 文件范围如何声明与强制？是否已有按路径收窄写面的强制？
- Q4 L3 管线哪一步跑全量套件？如何把红分类为“跨 key”（vs 自身回归）？
- Q5 conductor 的 per-project 配置如何加载与热重载？新开关应落在哪个文件/字段？

## 调研方法与出处

- **全文精读**（不靠搜索片段）：`packages/multi-workers/autopilot/conductor.py`、`config.py`、`dispatch.py`、`closure.py`、`gates.py`、`state.py`、`advance.py`、`audit_evidence.py`；`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`、`read-scope.ts`、`worker-file-tool.ts`、`output-writer.ts`；`shared/protected-config.ts`、`shared/implementation-gate.ts`、`autopilot/gate-writer.ts`、`autopilot/console.ts`、`autopilot/status-model.ts`（相关段）、`autopilot/monitor.ts`（gate 段）。
- **穷举扫描**（用于“未发现”这一否定结论；`mw_common.py` 2799 行、`launcher.py` 922 行、`mw.py` 4418 行为体量原因采用目标模式全量扫描而非逐行读）：搜索模式
  - Q1 词面：`cross_key`、`cross_key_test`、`handoff`、`registered`、`not_fixed_by_this_key`、`owner=`、`xkey`（全仓 `*.ts/*.py/*.md/*.json`，排除 `node_modules/dist/__pycache__/.git`）。
  - Q4 词面：`regression`、`全量`、`full suite`、`pytest`、`npm test`、`npm run`、`test.sh`、`test_suite`（`packages/multi-workers/**`、`autopilot/**`、`packages/coding-agent/src/extensions/agent-team-loop/**`）。
  - Q2 词面：`gate_timeout`、`gate.*expire`、`expired`、`gate.*age`、`remind`（extension 源码）。
  - Q3 词面：`TOOL_ALLOWLISTS`、`read_scope`、`deny_globs`、`setActiveTools`、`block: true`、`toolName === "write"`、`PI_WORKER_TASK`、implementation-gate / protected-config。
- **只读纪律**：本次未修改 `pm-state.md` / `_index.parallel` / spec 或任何其它 key 文件；未运行会改仓库状态的命令（仅 `read` / `Select-String` / `Get-ChildItem` 等只读枚举）。
- **否定结论的取证方式**：文件不存在某模式时无 `file:line` 可引；本文以“扫描范围 + 模式 + 命中清单”作为证据，并单独列出命中处证明其不构成机器字段。

## 发现

### Q1 跨 key 交接登记：是 **（b）L3 散文**，没有任何机器解析点

**判定：(b) 散文。** `[VERIFY] REPAIR-R1-F1: cross_key_test=… owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True` 只被当作 L3/repair worker 写在 `output.md`/report 里的自由文本；框架对它没有任何字段级解析。

事实与锚点：

1. **L3 prompt 只规定“两节 + FAIL 标记”，不规定任何交接字段形状。** `_l3_prompt` 定义于 `packages/multi-workers/autopilot/conductor.py:1113`；正文要求：
   - 输入是 EXECUTE 期 worker 在 `output.md`/`evidence/` 记录的 `[VERIFY]` 输出，**明确“不重跑命令”**：`conductor.py:1116-1117`（`[VERIFY]` 字样在同一行，`:1117` = “（证据记录制：不重跑命令）”）。
   - `output.md` **必含两节**：`## Quality Gate Report`（VC 逐条 PASS/FAIL）与 `## Achieved`：`conductor.py:1119-1121`。
   - 长报告可放 `report.md` 作为“文档化回退源”：`conductor.py:1122-1124`。
   - prompt 未出现 `cross_key` / `owner=` / `handoff` / `registered` / `not_fixed_by_this_key` 中任何一词。

2. **机器实际解析的只有三样东西**（全部在 conductor 内）：
   - 两个 section 的存在性：`_md_section` 定义 `conductor.py:1076`；`_parse_l3_output` 在 `conductor.py:1104-1105` 取 `## Quality Gate Report` / `## Achieved`；`_l3_qualifies` 在 `conductor.py:1207-1213` 用同一判据。
   - **FAIL 标记**（决定 below）：正则 `_L3_FAIL_RE` `conductor.py:1155`、`_L3_FAIL_BULLET_RE` `:1159`、`_L3_FAIL_PROSE_RE` `:1160`、`_L3_FAIL_ZERO_RE` `:1161`，扫描入口 `_l3_fail_marker_line` `conductor.py:1164-1185`。这些正则只认 `FAIL` 词形，不认 `cross_key_test=`/`handoff=`。
   - 判定源选择：`_L3_SOURCE_ORDER = ("output.md","report.md")` `conductor.py:1152`；解析 `_l3_resolve_source` `conductor.py:1215-1231`；`report-<slug>.md` 被注释明确排除在回退源外（`conductor.py:1148-1151`）。

3. **verdict 落盘 schema 的字段里没有跨 key 登记。** provenance record 字段集合：`conductor.py:1294-1305`（`round / task_key / deciding_source / source_mtime_ns / anchor_path / anchor_mtime_ns / suspect / reasons / raw_verdict / verdict / fail_line / recorded_at`），持久化到 `l3-verdict-provenance.json`（文件名常量 `conductor.py:1187`），追加写 `_persist_l3_provenance` `conductor.py:1359`。
   派生终态记录是**封闭值域** `_VERDICT_VALUES = ("meets","below")`（`conductor.py:616`），落 `l3-verdict.txt` + 复制 `l3-report.md`（`_persist_l3_verdict` `conductor.py:619-659`；读取 `_l3_verdict` `conductor.py:603-613`；done 凭据校验 `_done_credentials_present` `conductor.py:1415-1459`）。
   done transaction 生成的 `evidence/quality-gate-report-<ts>.md` 也只带 `generated_by/generated_at/source` 三行 + `## Quality Gate Report` 正文：`conductor.py:1741-1757`。

4. **`[VERIFY]` 行在整个 Python 生产代码里只作为 prompt 文本出现，无解析器。** 全仓 `[VERIFY]`（区分大小写）命中于生产代码的只有三处，且都在 prompt 字符串内：`_exec_prompt` `conductor.py:1001`、`_l3_prompt` `conductor.py:1116`、`_repair_prompt` `conductor.py:1140`。worker 侧 `output.md` 只在 `output-writer.ts:66-88`（D-117）被**原样拼接保留**（不解析行内容），`writeOutput` 定义 `output-writer.ts:45`。

5. **词面穷举结果（全仓 `*.ts/*.py/*.md/*.json`）**：
   - `cross_key`：仅命中本 key 自身的 `.agenticdoc/xkey-repair-mechanism/{spec.md,evidence/research/spec-problem-framing-20260926.md}`、本 task 文件，以及 **一个测试的 console.log 字符串** `packages/coding-agent/test/extensions/agent-team-loop.test.ts:3004`（`console.log("[VERIFY] AC-007: cross_key_dispatch_visible=yes")`）——不是被解析的字段。
   - `not_fixed_by_this_key` / `handoff=registered`：无任何代码命中（仅在 `.agenticdoc/mw-done-closure-repair/evidence/*`、`mw-rag-integration` 等**历史 key 的文档/报告**中出现）。
   - `xkey`：无代码命中。
   - `handoff`：代码内命中全部属于 packages/ai 的 cross-provider-handoff 测试与 coding-agent 示例 `examples/extensions/handoff.ts`，与 agent-team-loop/autopilot 无关。
   - `owner=`：仅命中 `autopilot/state.py:200`（`WorkerTaskInfo(owner=owner, …)`）与 conductor 的 sprint 标签，均为队列/任务归属，不是交接登记。

**结论：若本 key 需要消费 `handoff=registered` / `owner=` / `cross_key_test=`，框架当前没有读者——必须新增“写侧（L3 输出形状）+ 读侧（conductor 解析）”，且需兼容既有散文形状（spec P-005/P-014）。**

### Q2 gate 机制：文件即协议；无超时字段；新增 gate 类型需改 4 类点

**落盘文件与 schema（gates.py）**：
- gate 目录：`<project>/.agenticdoc/_autopilot/gates/gate-{seq:04d}.md`（目录路径由调用方传入，policy 在 config：`gates.py:20-23`；目录构造见 `conductor.gates_dir` `conductor.py:66-67`）。
- 12 字段 frontmatter：`id / kind / stage / key / created_at / created_by / question / context_refs / status / answered_at / answered_by / note` —— `gates.py:65-81`；必需字段子集 `_REQUIRED_FIELDS` `gates.py:83-84`。
- `kind ∈ {stage-confirm, stage-close, stalled, budget-exhausted, goal-change}`：`GATE_KINDS` `gates.py:52-58`。
- `status ∈ {pending, approved, rejected}`：`GATE_STATUSES` `gates.py:60`；解析校验 `gates.py:411-414`。
- 正文（`---` 以下）是**人读散文**，`parse` 忽略之：`gates.py:460-476`。
- YAML 子集与严格报错：`_parse_frontmatter` `gates.py:308-365`，`GateFormatError` `gates.py:104`；未知字段直接 raise（`gates.py:337-340`）。

**抬起（create）**：
- 唯一创建者是 conductor（`gates.py:246-247`、`:272` 注释：“conductor is the sole gate creator, TS only answers”）。
- 序列号 = 目录 rescan `max(id)+1`：`_next_seq` `gates.py:243-256`；原子写 `_write_atomic` `gates.py:198-205`。
- conductor 侧统一入口 `_create_gate` `conductor.py:2064-2091`：在 `.mw/gates.lock` 下调用 `gates.create`，成功后写 timeline `gate-created` 事件（`conductor.py:2087-2089`）。锁协议 = `acquire_conductor_lock`（stale steal）`conductor.py:97-148`；`gates.create` 本身**不取锁**（`gates.py:268-272`）。

**作答（answer）**：
- 字段名：`status / answered_at / answered_by / note`（`ANSWER_FIELDS`）——`packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts:50`；`approve → approved`，`reject → rejected`：`gate-writer.ts:140`。
- 作答入口：`/autopilot gate <id> approve|reject [--note <text>]`，命令分发 `console.ts:102-104`、`cmdGate` `console.ts:197`、调用 `answerGate` `console.ts:217`；写侧实现 `answerGate` `gate-writer.ts:139-176`（`.mw/gates.lock` 下 read-modify-write，只重写 4 个字段，其余字节保留：`gate-writer.ts:113-135`）。
- 人工直接改文件同样是合法作答（文件是唯一真值）：`gates.py:13-15`、`gate-writer.ts:16-18`。

**谁读 / 消费语义（conductor）**：
- 全量扫描 `gates.enumerate` `gates.py:480-504`；pending 过滤 `gates.py:506-508`。
- 已答 gate 的消费：`_consume_answered_gates` `conductor.py:274-322`（当前只 transition `stage-confirm approved`→stage running、`stage-close approved/rejected`→closed/halted）；幂等消费记录是 timeline 的 `gate-answered` 事件，由 `_consumed_gate_ids` 重放 `conductor.py:255-272`。
- 其它 kind 的轮询/消费：`stalled` → `_resume_credits` `conductor.py:2168`、`_apply_stalled_approvals` `conductor.py:2190`、`_apply_stalled_rejections` `conductor.py:2258`；`budget-exhausted` → `_budget_bonus` `conductor.py:2111`、`_budget_gate_rejected` `conductor.py:2123`；`goal-change` → `open_goal_change_gate` `conductor.py:150`；通用 pending 探测 `_gate_open` `conductor.py:2093-2109`。
- 超时语义：**未发现任何 gate 超时/到期/提醒机制。** gate schema 无 timeout 字段（`gates.py:65-81`）；conductor 只轮询 `pending`；监控面板只统计/列出 pending（`monitor.ts:255-267`、`:552-553`）。搜索模式 `gate_timeout|gate.*expire|expired|gate.*age|remind` 在 extension 源码 0 命中。**stalled-gate 家族不提供超时语义**（spec §4 R-3 的“沿用超时语义”无现成实现可留）。

**新增一个 gate 类型（如 `xkey-authorize`）需要改的点**：
1. `GATE_KINDS` 白名单：`packages/multi-workers/autopilot/gates.py:52-58`（`create` 与 `_to_gate` 都会校验，`gates.py:216-220`、`:411-414`）。
2. TS 读侧镜像 `GATE_KINDS` 与校验：`status-model.ts:467`、`:595-596`。
3. conductor 消费分支：在 `_consume_answered_gates`（`conductor.py:274-322`）或新增轮询函数中处理该 kind 的 approved/rejected；若需 per-key 语义，复用 `_gate_open(key=…)`/`_create_gate(key=…)`（`conductor.py:2064-2091`、`:2093-2109`）。
4. workorder/payload：把结构化字段塞进 `context_refs`（block list，`gates.py:65-81`、`:308-365`）或 `note`；`question` 必须单行（`gates.py:223-224`），`context_refs` 条目必须非空单行（`gates.py:229-241`）。
5. 测试：gate 创建/解析/作答/消费的既有测试族 `packages/multi-workers/test_autopilot_gates.py`、TS `gate-writer`/`console` 测试。

### Q3 受限派发：**只有工具类型白名单，没有按路径收窄写面的强制**

**声明点（task.md frontmatter，Python 渲染侧）**：
- 派发类型 → 工具集 / cli / provider：`dispatch.REGISTRY` `packages/multi-workers/autopilot/dispatch.py:70-107`（`_CODING_TOOLS` 含 `write/edit/bash` `dispatch.py:51`，`_REVIEW_TOOLS` 只读 `dispatch.py:52`）；`verifier` 强制非空 `read_scope`（`requires_read_scope=True` `dispatch.py:88-91`，`dispatch()` 拒绝 `dispatch.py:457-464`）。
- task.md 头部字段由 `render_task_md` 写：`type / phase / model / origin / loop / attempt / read_scope / l2_read_file_cap / l2_read_byte_cap / deny_globs` —— `dispatch.py:243-314`；`read_scope` 展开 `_expand_read_scope` `dispatch.py:317-357`；`deny_globs` 默认取自 target.yml `_resolve_deny_globs` `dispatch.py:359-368`。
- 队列行不含工具/路径信息（只有 task_key/status/cli/provider/task_path/…）：`dispatch.py:486-496`。

**强制点（worker-mode，TS 侧）**：
- 工具白名单：Python `REGISTRY` 与 TS `TOOL_ALLOWLISTS` 必须逐项相等（含顺序），L0 parity 测试锁定：`worker-mode.ts:52-83`（注释 `:60-63` 说明 parity）；下发 `applyRagTools` → `pi.setActiveTools(activeToolsForType(type))`：`rag/tools.ts:400-406`、`worker-mode.ts:747-754`（`activeToolsForType` `worker-mode.ts:101`；无 `write` 的只读角色额外拿 `worker_file` 窄写通道 `worker-mode.ts:99-104`、`worker-file-tool.ts:66-111`）。
- 二次 fail-closed：`origin: conductor` 且 type 未注册 → 拒绝启动；`verifier` 缺 `read_scope` → 拒绝：`dispatchRefusal` `worker-mode.ts:442-461`、调用点 `worker-mode.ts:626-639`。
- **文件范围强制（read_scope/deny_globs）只拦截 read-ish 工具**：`tool_call` 拦截器在 `readScopeConfig` 存在时注册（`worker-mode.ts:761-797`），且仅当 `event.toolName` 属于 `read/ls/find/grep` 才判定，其余（`write`/`edit`/`bash` 等）直接 `return undefined`（放行）：`worker-mode.ts:763-772`。判定纯函数 `checkReadScopeCall` `read-scope.ts:167-227`；`deny_globs` 优先于 scope（`read-scope.ts:180-199`）；无 scope 的 deny-only 模式 `read-scope.ts:242-266`。

**结论：当前没有任何“按路径声明并强制写面”的机制。** 能收窄的只有：(a) 去掉 `write`/`edit` 工具（改 `REGISTRY` + `TOOL_ALLOWLISTS` 两处 + parity 测试）；(b) 只读工具的路径/字节围栏（`read_scope`/`deny_globs`/cap）。`bash` 在 `_CODING_TOOLS` 内且**不受 read_scope 拦截**（`worker-mode.ts:763-772`），因此 `phase-writer`/`repair` 类型实际可写任意路径。全仓写面硬拦截仅有两处，均与任务级写面无关：
- `protected-config.ts:246-269`：只拦 `~/.pi/agent/{auth,models,settings,oauth}.json` 与 agent 目录（跨窗口凭证，2026-09-15 事故）。
- `implementation-gate.ts:761-778`：写 `packages/**` 代码路径时要求“本窗口有 active key claim”**或 `PI_WORKER_TASK` 已设置**（`implementation-gate.ts:752-760`、`:31-33`）；**dispatched worker 因 `PI_WORKER_TASK` 一律预授权**，不做按任务的路径收窄。
- `pm-state-guard.ts:49-121` 只保护 `pm-state.md` 的 Phase 字段。

**对 spec GC-2 / AC-005 的直接含义：“写面精确到冻结常量块、diff 边界机械强制”在现有框架内没有可复用的落点，必须新造 enforcement（或在施工后按 diff 做后验校验）。**

### Q4 L3 全量回归扫描：**框架管线不跑套件，也不做“跨 key vs 自身回归”分类**

事实与锚点：
1. **L3 明确不重跑命令**：`_l3_prompt` `conductor.py:1113`，正文 `conductor.py:1116-1117` 写明输入是 EXECUTE 期记录的 `[VERIFY]` 输出、“（证据记录制：不重跑命令）”；需要重跑才能确认的标 `needs-rerun` 计入遗留（`conductor.py:1118`）。
2. **框架层没有任何测试执行器**：
   - `packages/multi-workers/autopilot/**` 与 `mw.py`/`launcher.py` 对 `pytest|npm test|npm run|test.sh|unittest` 的命中仅为 `mw.py` 的构建/自检命令（`mw.py:3551`、`:3572-3573`、`:3939`、`:4050`，均为 `npm run build`/`mw doctor`，与 L3 无关）；`autopilot/audit_evidence.py` 只审计 spec/design 证据文件（`audit_evidence.py:215-263` 的 `build_dossier`/gaps），不跑测试。
   - `advance.advance()` 只包装 AgenticTask 的 `advance_phase.py`（`advance.py` 模块 docstring + `advance()` 末尾），也不跑套件。
3. **唯一的机械“红分类”是 advance 框架失败的文本分类**，与测试红无关：`_classify_advance_failure` `conductor.py:720-735`（`interface-drift|gate-blocked|timeout-env|other`，标记表 `conductor.py:699-711`），消费于 `_record_advance_result` `conductor.py:812-850` + `_advance_failure_streak` `conductor.py:747-810`。
4. **L3 的“红”只被识别为 report 里的 `FAIL` 词形**（Q1 第 2 点），不区分“自身回归”与“跨 key”；两者在机器层不可区分。
5. 词面扫描 `regression|全量|full suite|pytest|test.sh` 在 `packages/multi-workers/**` 生产代码 0 命中（仅 `mw_common.py:2654` 的 “zero-regression” 注释、TS 注释里的 “zero regression”）。

**结论：spec §2.4 依赖表所写“L3 判定链 × 全量套件回归扫描 → conductor.py”不成立。全量套件运行只发生在 EXECUTE/repair worker 按项目 task.md 自述执行时（其 stdout/`[VERIFY]` 行落进 output.md），框架既不触发也不解析“全量红数”。本 key 若要 (file,test) 粒度的红账本，需自建“红来源”，不能假设 conductor 已有。**

### Q5 配置读取：`_autopilot/config.json` + mtime+size 缓存；两侧镜像 + 未知字段 fail-closed

- 落点：`<project>/.agenticdoc/_autopilot/config.json`，`config.config_path` `packages/multi-workers/autopilot/config.py:66-67`。
- 默认字段（9 个）：`DEFAULT_CONFIG` `config.py:38-48`（`enabled/paused/poll_interval_sec/max_parallel_keys/round_budget/worker_timeout_min/l2_read_file_cap/l2_read_byte_cap/advance_stall_ticks`）。
- 校验：`validate_config` `config.py:75-97`；**未知字段直接报错**（`unknown = sorted(set(cfg) - set(DEFAULT_CONFIG))` `config.py:80-82`）；范围表 `_INT_RANGES` `config.py:52-60`、bool 表 `_BOOL_FIELDS` `config.py:51`。
- 读取/写入/热重载：`load_config` `config.py:101-113`（缺文件 = 默认、零足迹；存在但非法 = raise `ConfigError`）；`save_config` `config.py:115-127`（原子写 + 主动清缓存）；`cached_load` `config.py:129-150`（**mtime+size 缓存**，命中回防御性拷贝；`_CACHE` `config.py:63`）；`invalidate_cache` `config.py:152-154`。
- 消费者：
  - conductor 每 tick：`config.cached_load` `conductor.py:168`（`orchestrate`）、`:1964`（`tick` 的 enabled/paused 门）、`:2501`（poll interval）、done transaction 里 `:1802`。
  - `mw serve` 的 conductor 生命周期：`mw.py:160-161`（`_ap_config.cached_load(project_dir)["enabled"]`）。
  - 读上限注入：`dispatch._read_scope_caps` 走 `autopilot_config.load_config`（`dispatch.py:227-241`）。
- TS 侧镜像（同一文件的读写者，必须同步改）：`status-model.ts:67-81`（`AutopilotConfig`）、`:82-93`（`DEFAULT_CONFIG`）、`:95`/`:98-105`（校验表）、`:112-140`（`validateConfigData`，未知字段报错 `:123-127`）、`:149-193`（`readConfig`）、`:199-214`（`saveConfig`，规范化写出全部字段）；`/autopilot enable|disable|pause|resume` 经 `readConfig`+`saveConfig` 改写（`console.ts:276-331`、`:333-352`）。

**新增开关（如 `xkey_repair.enabled`）应落在**：
- 文件：`.agenticdoc/_autopilot/config.json`（落盘；避 spec P-015 的 env 丢失坑）。
- 形状：当前两侧校验器只支持**扁平 bool/int**，且对未知字段 fail-closed；嵌套对象 `xkey_repair: {...}` 会被 `validate_config`/`validateConfigData` 视为已知字段但无嵌套校验（值可存入，读取端需自行解析）。最省改动且与现有一致的是**扁平 bool 字段**（如 `xkey_repair_enabled`）。
- 改动点：`config.py:38-48` + `:51-60`（默认值+范围/bool 校验）、`status-model.ts:67-93` + `:95-105` + `:149-193`/`:199-214`（镜像读写）；若只在 conductor 消费，读 `config.cached_load(...)[<field>]`（`conductor.py:168` 处）。

## 结论 → 决策映射

| 结论 | 支撑的 design/plan 决策 |
|---|---|
| Q1：交接登记是散文，框架 0 机器解析点（L3 prompt 只认两节 + FAIL 词形；provenance/verdict 字段封闭） | R-1 判定为真；本 key **必须先交付“交接登记机器可读化”**：新增 L3 输出机器形状（写侧 prompt）+ conductor 解析（读侧），并兼容既有散文（P-005 双侧测试、P-014 多字形）。沿用 provenance/`fail_line` 通道，不新造 verdict 文件 |
| Q2：gate 是 12 字段 markdown 文件 + `.mw/gates.lock`；conductor 唯一创建、TS/人工作答；无超时字段 | `xkey-authorize` 作为新 `GATE_KINDS` 落地（gates.py + status-model.ts 双改）；payload 进 `context_refs`；“仅人可答”需新增作答者校验（现有 `answered_by` 只记录 claimId，不校验身份）；R-3 超时需自建（无现成语义） |
| Q3：只有工具类型白名单（REGISTRY/TOOL_ALLOWLISTS 双镜像），read_scope/deny_globs 只拦 read/ls/find/grep，bash 不受拦；无按路径写面强制 | GC-2/AC-005 的“写面精确到冻结常量块 + diff 边界机械强制”**不能复用现成能力**，须新造 enforcement（新 dispatch 类型 + 后验 diff 边界校验），并新增 parity 测试 |
| Q4：框架不跑全量套件、不做跨 key 分类；红只能来自 worker 写进 output.md 的 `[VERIFY]`/stdout 散文 | (file,test) 红账本需自建来源与分类；AC-002 的“无登记红只升级”分类逻辑无处复用；依赖表“L3 全量套件回归扫描→conductor.py”应改口径 |
| Q5：config.json 扁平字段 + 双侧镜像 + 未知字段 fail-closed；conductor 经 `cached_load` 热重载 | 机制开关按 P-015 落 config.json；用扁平 bool 字段，改 `config.py` 与 `status-model.ts` 两侧；默认关闭满足 AC-008 |