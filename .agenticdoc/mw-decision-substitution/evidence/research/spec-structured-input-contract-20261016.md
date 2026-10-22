# SPEC RQ-4 — 决策输入的结构化契约与脱敏分层

- key: `mw-decision-substitution` · 相位 SPEC · 卡片 `tasks/RQ4-structured-input-contract.md`（card_sha256 cf6cf360…）
- 调研方式：只读检索（源码 + 仓内运行时产物），未改任何源码/配置/测试
- 代码基线：`packages/coding-agent/src/extensions/agent-team-loop/pm/{triage-client.ts,ui-bridge.ts}`、`packages/coding-agent/src/extensions/agent-team-loop/{shared,worker}/**`、`packages/multi-workers/{decision.py,mw_common.py,mw.py,decision_backends.py,autopilot/index_parallel.py}`
- 行号基准：2026-10-19 工作区实读。注意：`jev-integration-flow-and-usage.md` §2.1 引用的 `ui-bridge.ts:241-247` 与 `planDispatchFrontmatter:1257` 已漂移——现文件中 `computeDispatchTriage` 定义在 `pm/ui-bridge.ts:235-256`，DP-1 的 state 组装/传递点在 `pm/ui-bridge.ts:1429-1436`（`planDispatchFrontmatter` 定义 `pm/ui-bridge.ts:1335`）。本文一律用实读行号。

---

## Q1 输入源盘点

### Q1.0 现状基线：DP-1 的 state 是什么

`buildTriageState`（`pm/triage-client.ts:201-208`）产出的 state 是**纯文本**：`requested_type: <type>`、`cli: <cli>`、`owner_phase: <phase>`、空行、`task:`、然后是**派发描述全文**。发送前按 `MAX_TRIAGE_STATE_BYTES = 16_000` 从尾部截断（`pm/triage-client.ts:44`、截断函数 `pm/triage-client.ts:216-222`），序列化点 `pm/triage-client.ts:273`（`JSON.stringify({state, questions})`）。挂点：`planDispatchFrontmatter` 内 `pm/ui-bridge.ts:1429-1436`，state 只由 4 个输入组成（description/taskType/cli/phase，`pm/ui-bridge.ts:1430-1434`）。Python 侧预算上限 `max_state_bytes = 16384`（`packages/multi-workers/decision.py:244`）。

### Q1.1 可作输入源的仓内结构化产物（总表）

| # | 字段 | 载体 | 文件:行号 | 可得性 |
| --- | --- | --- | --- | --- |
| 1 | 任务类型 `type` | worker task.md 头 | `workers/ds-rq1-decision-inventory/task.md:1`（本文所有 worker 的 task.md 同构）；写面 `pm/ui-bridge.ts:1789` 附近（信封模板）、枚举 `pm/triage-client.ts:55-57` | **可得**（`type: X` 行首匹配，`shared/task-frontmatter.ts` 已有读取器） |
| 2 | 写面 `write_scope` / `write_face` | worker task.md 头 | `workers/ds-rq1-decision-inventory/task.md:2`、`:6`；解析器 `shared/write-surface.ts:259`（逗号形式） | **可得** |
| 3 | 卡片溯源 `card_path` + `card_sha256` | worker task.md 头 | `workers/ds-rq1-decision-inventory/task.md:3-4`；契约 `shared/dispatch-card.ts:1-33`（T-01 envelope） | **可得**（sha256 可验证卡片未被中途改写） |
| 4 | 卡片正文（上下文/要求/交付格式三节） | `tasks/RQ-*.md` | 本 key 实例 `tasks/RQ4-structured-input-contract.md:1-4`（`- key/type/timeout` bullet）、三节判定词汇 `shared/dispatch-card.ts:45-58` | **需解析**（Markdown 正文；`timeout: 40` 在卡片 bullet `tasks/RQ4-structured-input-contract.md:4`） |
| 5 | 队列行 9 列 `task_key\|status\|cli\|provider\|task_path\|dispatched_at\|updated_at\|model\|origin` | `.agenticdoc/_workers.parallel` | 列契约 `shared/worker-store.ts:16-40`（`WORKER_COLS_MIN=7/MAX=9`）、解析 `shared/worker-store.ts:106-117`、序列化 `shared/worker-store.ts:119-131`；Python 镜像 `mw_common.py:2084` `parse_workers_file` / `:2100` `serialize_entry`；本仓实例行 `_workers.parallel:1-3` | **可得**（split " \| "；status 枚举 `shared/worker-store.ts:15`） |
| 6 | key 索引行 `key\|state\|phase\|claim\|deps\|goal\|updated` | `.agenticdoc/_index.parallel` | 解析 `packages/multi-workers/autopilot/index_parallel.py:74-89`（≥5 列）、claim 列位 `:91-93`（7 列 schema 下 index 3） | **可得**（需 split；本 key 行：`mw-decision-substitution \| claim \| SPEC`） |
| 7 | owner 阶段 `Phase` / 任务状态表 / Evidence Ledger | `<key>/pm-state.md` | 本 key `pm-state.md:6`（`- Phase: SPEC`）、任务状态表 `pm-state.md:15-22`、Evidence Ledger `pm-state.md:32-40` | **需解析**（Markdown；Phase 行是规整 `- Phase: X`） |
| 8 | run 身份与终态 `schema/task_key/run_id/owner_key/kind/status/started_at/ended_at/exit/supersedes/artifacts/pid/last_heartbeat_at` | `workers/<task>/run.json` | 字段契约 `shared/run-store.ts:31-53`；本 worker 实例 `workers/ds-rq4-structured-input-contract/run.json:1-17`；读取器（fail-soft）`shared/run-store.ts:76-99` | **可得**（JSON；终态枚举 `shared/run-store.ts:29-34`，跨语言镜像 `mw_common.py:2131`） |
| 9 | trace 行 `[START]/[MODEL]/[FLOW]/[TOOL]/[MODEL_ERR]/[CHECKPOINT]` | `workers/<task>/trace.log` | 本 worker 实例 `trace.log:1-6`（START/MODEL/FLOW/TOOL 各一行）；写入器 `worker/output-writer.ts:572` `appendTrace`；`[MODEL_ERR]` 写点 `worker/worker-mode.ts:3841-3848`（单行 cap 200 字符 `worker/worker-mode.ts:4053-4059`）；`[CHECKPOINT]` 字段 `elapsed/reads/writes/phases/uniq_targets/repeat_top/risk/land/last_land/artifact/done`（`worker/worker-mode.ts:3348-3352`） | **需解析**（文本行；字段是 `k=v` 对，正则可提） |
| 10 | 退出码 `exit` 与状态机 | `run.json` + worker 判定点 | `shared/run-store.ts:45-47`（`exit` 字段，running/lost 时缺席）；`exit 2 = needs-clarification` 判定 `worker/worker-mode.ts:2677-2681`；`lost` 仅允许 Python 侧添加 `mw_common.py:2180` `mark_run_lost` | **可得** |
| 11 | 失败模式 `runner.error_kind` | ——（拟议字段名） | 全仓 grep `error_kind` 0 命中（TS 与 Python 均无） | **不存在**；等价物 = `run.json.status/exit`（可得）+ `trace.log [MODEL_ERR]` 行（需解析，且文本已 cap 200 字符并脱敏） |
| 12 | 历史同类结果（成功/失败/澄清/丢失） | `_workers.parallel` 历史 status 列 + 各 `run.json` | `shared/worker-store.ts:15`（status 枚举 pending/running/done/failed/needs-clarification/lost）+ `shared/run-store.ts:48-49`（`supersedes` = **返工的机器信号**） | **可得**（成功/失败/澄清）；**不存在**：回滚没有机器字段（`_project_log.md:1-12` 的 Supersedes 列是 key 级取代叙事，需人工解析） |
| 13 | 历史 alarm/处置流水 `seq/phase/kind/count/detail` | `.agenticdoc/_autopilot/auto-decisions.jsonl` | 本仓实例 `auto-decisions.jsonl:1-2`（`kind=out-of-scope/no-product`）；写者 `pm/pm-orchestrator.ts:645` `recordDispatchAlarm`、路径拼接 `autopilot/status-model.ts:1223` | **可得**（JSONL；kind 是受限集合 `pm/pm-orchestrator.ts:553-568`） |
| 14 | 运行时风险信号（分拆/收窄判据） | `[CHECKPOINT]` risk 字段 | 机器启发 `computeRisk`（`worker/worker-mode.ts:351-368`：landed/artifactPresent/phasesDone/repeatTop）；写进 trace `worker/worker-mode.ts:3348-3352` | **需解析**（值本身是机器枚举 low/mid/high） |
| 15 | 受影响文件白名单 | task.md `write_scope` + 卡片正文 | `workers/ds-rq1-decision-inventory/task.md:2`（目录级白名单）；**文件级**白名单不存在——`write_scope` 只到目录，具体受影响文件只在卡片正文/描述里 | **部分可得**（目录级可得；文件级需解析正文，或不存在） |
| 16 | 当前阶段 | pm-state.md / `_index.parallel` / task.md `phase:` 头 | `pm-state.md:6`、`_index.parallel` 第 3 列（`autopilot/index_parallel.py:91-93`）、派发写入 `pm/ui-bridge.ts:1371-1373`（headLines push `phase: <P>`） | **可得** |
| 17 | 预算（墙钟）与已耗 | task.md `timeout:` 头 + `[CHECKPOINT] elapsed` + `run.json.last_heartbeat_at` | 预算解析 `worker/worker-mode.ts:592-595`（`timeout:` 头）→ `resolveBudgetMs(meta.timeoutMin, PI_WORKER_TIMEOUT_MS)`（`worker/worker-mode.ts:3250`、`:2844`；环境回退 `worker/worker-mode.ts:247`）；anchor=30min `worker/worker-mode.ts:243`；本 worker 心跳实例 `run.json:17` | **需计算**（剩余 = budget − elapsed，两个因子分别需解析 task.md 与 trace.log） |
| 18 | 问题类型与预算常量 | `decision.py` | `QUESTION_TYPES = {choice, score, noul, box}` `decision.py:105`；B2 不支持 box → `unsupported-question-type` `decision_backends.py:633`；预算默认 `timeout_s=20/max_retries=2/max_questions=8/max_state_bytes=16384/max_tokens=1024` `decision.py:241-245`，范围检查 `decision.py:289-298` | **可得**（常量即契约） |
| 19 | worker 自报交付段（结论/证据/残留与未验证/上下文来源） | `workers/<task>/output.md` | 段落词汇 `worker/output-sections.ts:48`（`RECOVERY_SECTIONS`）+ 类型扩展 `:50-63` | **需解析**（Markdown；本波 RQ worker 尚无 output.md，仅 progress.md/run.json/trace.log/worker.log） |
| 20 | 决策服务配置（fail-soft 读模板） | `.mw/decide.json` | 读面 `decision.py:326-352` `from_project`（缺文件=unconfigured）、`decision.py:261-324` `from_dict`；同类 fail-soft 模板 `mw_common.py:224-252` `load_dispatch_config` | **可得** |

### Q1.2 按四类决策归并（RQ-1 证据未到，按卡片指定四类）

**A. 派发前（spec.md §4 的 #1 派发 type/角色/范围、#9 模型/供应商选择，`spec.md:55,63`）**
可直接读到的字段：requested_type（`triage-client.ts:201-208` 现已送）、cli、owner_phase、卡片三节全文（需解析+裁剪）、write_scope 目录白名单（task.md:2）、images 需求（`ui-bridge.ts:1357-1373` 三态检测）、write_face 串行语义（`packages/multi-workers/autopilot/dispatch.py:28-33`）、role→model 配置（`mw_common.py:224-252` 读 dispatch.yml）。**不存在**：历史同类任务的聚合成功率（需新建聚合器从 `_workers.parallel`/run.json 计算）。

**B. 执行中（#2 分拆粒度、#3 歧义澄清、#9 降级触发，`spec.md:56-58,63`）**
可直接读到：`[CHECKPOINT]` 全字段（trace.log，`worker-mode.ts:3348-3352`）、`computeRisk` 输入信号（`worker-mode.ts:351-368`）、budget/elapsed（Q1.1#17）、task type（task.md:1）、`needs-clarification` 通道（exit 2 语义 `worker-mode.ts:2677-2681`；现在直接等于甩给人，`spec.md:57`）。**不存在**：结构化的"卡在哪一步"字段（只有 trace 文本可推）；歧义澄清没有机读问题对象（`needs-clarification` 只是一个状态值）。

**C. 收尾（#6 QG 结论处置、#7 相位门禁失败处置、#13 提交/发布时机，`spec.md:59-61,67`）**
可直接读到：worker 交付段四节（output.md，`output-sections.ts:48`）、run.json artifacts（`run-store.ts:50-51`）、验收命令输出（卡片 `- 验收命令` bullet，本卡即含）、`auto-decisions.jsonl` 流水（Q1.1#13）、phase（pm-state.md:6）。**不存在**：QG blockers 的结构化列表（verdict 目前在文本/JSONL detail 里）；提交/发布窗口的机器判据（release 流程在 AGENTS.md，非仓内数据）。

**D. 处置（#4 失败重派/换模型/放弃、#10 依赖升级、#8/#11/#12/#14 P0 类，`spec.md:58,60,62-68`）**
可直接读到：run.json status/exit/supersedes、`[MODEL_ERR]` 单行（≤200B，`worker-mode.ts:4053-4059`）、attempts/latency（决策证据行 `decision.py:121-133` `_EVIDENCE_FIELDS`）、fallback 模型配置（`mw_common.py:330` 起的 fallback_models 块）。**不存在**：`error_kind` 机读枚举（Q1.1#11）；P0 判定字段（P0 目前只存在于 spec 表格与 DS-1 裁定，`pm-state.md:45`，代码里无 `risk=P0` 常量——需在本 key 落地）。

---

## Q2 最小充分输入

原则：字段集 = 人做该判断时实际看的 3–7 项；**所有任务描述全文、trace 全文、代码原文一律不进 state**（这是与现状 16KB 文本的本质差异）。字段名与出处均可在 Q1.1 表中定位，不再重复行号。

| 决策类别（spec.md §4 编号） | 必需字段（进 schema，缺失→Q6 处置） | 可选字段 | 明确**不需要**的字段 |
| --- | --- | --- | --- |
| 派发 type/角色/范围（#1，DP-1 现挂点） | `requested_type`、`owner_phase`、`task_summary`（≤600B 摘要）、`scope.write_scope`（目录级）、`scope.ext`（扩展名集合）、`risk_self`（低/中/高，PM 标注） | `images_required`、`history.recent_*`（owner key 近 N 次状态计数）、`card_sha` | 任务描述全文、用户原话、绝对路径、代码片段、模型 registry 详情（路由已有专门机制 `ui-bridge.ts:1395-1412`）、cli/provider 凭据状态 |
| 分拆/收窄/直执（#2，checkpoint 升级） | `dp=dp2-checkpoint`、`risk`（机器 computeRisk 值）、`progress.elapsed_min/budget_min`、`progress.phases_done/total`、`progress.artifact_present`、`task_type` | `progress.repeat_top`、`progress.last_land_age_min`、`failure.kind`（若有） | trace.log 全文、工具调用序列、已读文件列表、`[TOOL]` 行内容 |
| worker 歧义澄清（#3） | `dp=dp3-clarify`、`task_key`、`task_summary`、`ambiguity_kind`（枚举：scope/依赖缺失/规则冲突）、`asker_question`（≤300B，PM 改写后） | 相关 write_scope 子集、已尝试方案计数 | worker 与用户的对话记录、会话历史、用户原话 |
| 失败处置：重派/换模型/直执/放弃（#4） | `dp=dp4-failure`、`failure.kind`（枚举见 Q6）、`failure.exit`、`task_type`、`budget_remaining_min`、`history.recent_failed` | `failure.summary`（≤300B，kind 的机器单行）、`fallback_configured`（布尔） | `[MODEL_ERR]` 原文（已 cap 200B 但仍含模型报错细节，只留 kind+摘要）、堆栈、stderr 全文 |
| 测试失败归类（#5，环境噪声 vs 真回归） | `dp=dp5-flaky`、`test_name`（符号级）、`failure.summary`、`baseline_known`（布尔：是否在已知环境噪声基线内） | 最近同测试通过次数 | 测试输出全文、diff 全文 |
| QG 结论处置（#6）/ 相位门禁失败（#7） | `dp=dp6-qg`、`blockers_count`、`blockers_kind`（枚举数组）、`phase`、`evidence_present`（布尔） | 各 blocker 一行摘要（≤200B/条，≤3 条） | evidence 文件全文、review 对话、git log |
| 提交/发布时机（#13） | `dp=dp13-release`、`phase`、`checklist_done`（布尔计数）、`user_mandated`（用户是否已明确要求） | 版本 diff 统计 | CHANGELOG 全文、lockfile diff |
| 失败上抛人（P0：#8/#11/#12/#14） | 不进模型——**schema 直接拒绝生成**：`authority_tier=P0` 的 dp 在构造侧短路（见 Q3/Q6） | —— | 任何内容（凭据类决策连摘要都不外发） |

---

## Q3 脱敏分层

### Q3.1 三级敏感度表

| 级别 | 定义 | 覆盖字段（Q1.1 编号） | 处置 |
| --- | --- | --- | --- |
| **L0 可外发** | 枚举、计数、布尔、相对路径形态、机器生成的 id | #1 type、#5 队列列中的 status/cli/model、#7 phase、#8 run 元数据（task_key/run_id/status）、#14 risk 枚举、#16 phase、#17 计数、#18 问题常量、决策元数据（dp/key/phase） | 原样进入 state |
| **L1 需摘要/脱敏后外发** | 自由文本与路径类，脱敏后仍保留决策效力 | #4 卡片正文→`task_summary`；#9 `[MODEL_ERR]`→`failure.kind`+单行摘要；#15 路径→repo 相对路径+扩展名；#19 交付段→结论一行；用户原话→PM 改写的意图描述 | 走 §3.2 规则后再入 schema |
| **L2 绝不外发** | 凭据、个人信息、跨 key 数据、原文级代码 | 环境凭据值（`TIMI_API_KEY`/`ZAI_*`/`TYPESAFE_API_KEY` 等 `_API_KEY/_TOKEN/_KEY/_SECRET/_PASSWORD` 后缀，`decision.py:360`）、bearer/sk- 串（`decision.py:361-362`）、`~/.pi/agent/auth.json` 内容（`jev-integration-flow-and-usage.md` §3）、绝对路径盘符与用户目录（`C:\Users\<name>`、`WENBOZHOU-PC4`）、内部域名/端口（llmproxy host:port）、其他 key 的 worker 数据（跨 key 隔离，AGENTS.md 多会话规则）、代码原文 | 不进 state；schema 无承载字段（结构性排除，而非运行时过滤） |

### Q3.2 机读规则（正则/白名单建议，均在 TS 构造侧执行）

1. **凭据**：沿用并前置 `decision.py:360-362` 的三类模式（env 后缀集合 `_API_KEY|_TOKEN|_KEY|_SECRET|_PASSWORD`、`(?i)bearer\s+\S+`、`\bsk-[A-Za-z0-9._-]{6,}`）+ 值匹配（读 env 后做 longest-first 字面量替换，`decision.py:365-376` 已有实现，TS 侧对 `task_summary`/`failure.summary` 重复同一规则）。L2 字段结构性不存在，规则只是防线。
2. **路径**：`relative_to(project_root)` 成功 → 保留相对路径并截断到 ≤3 层 + 扩展名；失败 → 只留 basename+ext。正则剥离盘符/UNC：`^[A-Za-z]:[\\/]`、`^\\\\[^\\]+[\\/]`；剥离用户目录：`(?i)[A-Z]:\\Users\\[^\\]+` → `<user>`（本仓 trace 中大量出现 `H:\git\Multi-Workers\...`，如 `trace.log:5-6`）。
3. **内部域名与端口**：默认拒绝策略——仅白名单 `localhost`、`127.0.0.1`、已登记服务名；其余 `host:port` → `<internal-host>`（正则 `\b[a-z0-9.-]+\.[a-z]{2,}:\d{2,5}\b`）。`transport`/`base_url` 类配置值永不入 state（它们属 L2，见 `.mw/decide.json` extras `decision.py:246-252` 语义）。
4. **个人信息**：机器名/claim id 里的 host（`WENBOZHOU-PC4:53592`，`pm-state.md:5`）→ 剥离 host 段只留冒号后数字或整体占位；邮箱正则 `\b[\w.+-]+@[\w-]+\.[\w.]+\b` → `<email>`。
5. **用户原话**：schema 不设 free-text 原话字段；`task_summary` 与 `asker_question` 是 PM **生成**的摘要，构造规则写死：不得包含 >15 连续词的逐字引用；长度 cap（`task_summary` ≤600B、`asker_question`/`failure.summary` ≤300B）。
6. **代码片段**：schema 无 code 字段；只允许 `symbols`（标识符，正则 `[A-Za-z_$][\w$]*`）与 `anchors`（相对路径:行号）。
7. **出口控制点**：唯一出口是 TS 侧 `triage-client.ts:273` 的 `JSON.stringify`（stdin，不进 argv——`mw.py:693-699` 明确拒收 argv state）。新 `buildStructuredState` 在构造时完成全部脱敏；Python `_redact`（`decision.py:378-387`）保留为后端侧兜底（它今天只覆盖 detail/transport/model，`decision.py:1006-1010` 等，**不覆盖 state**——见 Q5 第 9 点）。
8. **脱敏后保持决策有效性**：路径只留相对路径+扩展名（决策依赖的是"改哪个子系统"而不是全路径）；代码只留符号名+定位；报错只留 kind+单行（B2 的回答是受限枚举，`decision_backends.py:405-419` 逐题校验枚举/整数/布尔，模型不需要原文也能分类）；计数/布尔/枚举原样（体积与状态数字不构成敏感面）。

---

## Q4 体积与成本

**现状**：上限 16_000B（TS，`triage-client.ts:44`）/16_384B（Python，`decision.py:244`），内容是描述全文（中文 UTF-8 每字 3B → 16KB ≈ 5.3k 字 ≈ 7–9k token 量级）；超限走 `boundTriageState` 的 0.9 系数反复截断（`triage-client.ts:216-222`），截断点在句子中间，判据质量无保证。

**目标**：结构化 state 序列化后 **≤ 2_000B / ≈800 token**，典型 800–1_500B。构成：枚举/计数 ≈300B；`task_summary` ≤600B；`failure.summary` ≤300B；其余为键名与结构开销。理由：(a) B2 输出预算仅 `max_tokens=1024`（`decision.py:245`）、单次硬超时 20s（`decision.py:241`），输入越短延迟越低；(b) 判据密度提高——Q2 表中每类决策只需要 3–7 个字段；(c) 与 16KB 相比体积降约 8 倍且**不再有截断语义**（超限时裁剪的是可选摘要字段，结构永不破损）。

**校验点适配**：TS 侧对 canonical JSON 计 UTF-8 字节（对齐 Python 侧 `_encode_state` 的字节口径，`decision.py:402-414`：str 直接编码，dict 走 `json.dumps(ensure_ascii=False, sort_keys=True)` `decision.py:410`）；预算判定本身不改（`decision.py:653-659`）。

**缓存 digest 口径**：`state_digest = sha256(canonical_json(state))`，canonical = 键排序 + 无空白（与 `decision.py:410` 的 `sort_keys` 一致，保证 TS/Python 双侧算出同一 digest）。**必须覆盖**（变化即失效）：`v`、`dp`、`key`、`task_key`、`phase`、`task_type`/`requested_type`、`risk`、`authority_tier`、`task_summary`、`scope.*`、`progress.*`（`elapsed_min` 按**分钟桶**量化，否则每次心跳都失效）、`failure.*`、`history.*`、`questions_version`（问题文本/criteria 变了必须失效）。**必须排除**（不影响答案的运行时字段）：`ts`、`run_id`、`pid`、heartbeat 时间、attempts、latency。digest 用途与 `spec.md` §6 已列的档案字段 `state_digest`（`spec.md` §6）对接，落库细节归 RQ-3。

---

## Q5 现有校验的适配

引入结构化 `state`（JSON 对象）需要动的校验点，全部列出（行号为实读）：

1. **TS 出口构造**：`buildTriageState`（`triage-client.ts:201-208`）返回 string → 新增返回 object 的构造器；序列化点 `triage-client.ts:273` 无需改（`JSON.stringify` 直接接受对象）；`boundTriageState`（`triage-client.ts:216-222`）改为：对象 → canonical JSON → 计字节 → 超限先裁可选摘要字段，**禁止**盲截字符串（旧实现会把 JSON 截坏）。
2. **CLI 请求形状**：`_decide_read_request`（`mw.py:693-721`）只校验 payload 是 dict 且含 `state`/`questions` 键（`mw.py:716-719`），对 `state` 的**值类型零校验** → 新增：`state` 必须是 str（legacy）或 dict（structured），其余 exit 2（沿用 `DecisionInputError` → exit 2 通道，`mw.py:803-807`）。
3. **客户端参数校验**：`_validate_input`（`decision.py:778-812`）目前对 state 只查 `state is None`（`decision.py:780-781`）→ 新增 structured 分支：`isinstance(state, dict)` 时校验 `v` ∈ 支持集、`dp` 非空、按 dp 的 required 字段存在且类型正确（规则见 Q6）；未知键**剥离 + 不报错**（避免 schema 版本耦合；可在证据行记 `state_keys_dropped`）。这是唯一 raise 路径（`DecisionInputError`，`decision.py:138-141`），语义保持"调用方参数错误"。
4. **状态编码**：`_encode_state`（`decision.py:402-414`）**已支持 dict**（`decision.py:410`）→ 不改；但要求 TS 侧也用 `sort_keys` 序列化，保证 Q4 的 digest 跨语言一致。
5. **预算校验**：`decision.py:653-659`（超 `max_state_bytes` → `budget-exhausted`，`decision.py:86`）语义不变——对象按序列化后字节计。
6. **后端 prompt 组装**：`_serialize_state`（`decision_backends.py:325-331`）已支持 dict（`json.dumps` 进 prompt）；`build_payload`（`decision_backends.py:522-538`）的 prompt 模板需一句话说明"state 段是 JSON 对象，字段含义见键名"，B2 强制 `submit_decision` 工具（`decision_backends.py:98`）与逐题校验（`decision_backends.py:405-419`）不变；box 不支持不变（`decision_backends.py:633`）。
7. **证据行**：`_EVIDENCE_FIELDS`（`decision.py:121-133`）不含 state（凭据防泄漏的正确现状，`decision.py:25-27` 硬规则）→ 如需输入审计，只加 `state_digest`（Q4 口径）一个键；旧证据行无该键，读取端 fail-soft（`mw_common.py:1601-1620` 的读取器按需容忍缺键）。
8. **向后兼容（旧字符串）**：分派规则 `isinstance(state, str)` → legacy 通道（现行为逐字节不变）；dict → structured。**兼容面收敛为三处**：`decision.py:780-781`（None 检查外的新分支）、`mw.py:716-719`（值类型校验）、`triage-client.ts:216/273`（构造与截断）。请求外层 shape 不加新键（`state_schema` 之类放 state dict 内部的 `v` 字段），`_decide_read_request` 的 required-key 检查不动。DP-1 的 questions 常量（`triage-client.ts:55-57`）与 `max_questions` 校验（`decision.py:783-788`）不受影响。
9. **兜底脱敏的边界**：`_redact`/`_scrub_detail`（`decision.py:378-397`）今天只作用于 detail/transport/model（`decision.py:1006-1010` 等），**不作用于 state 本身**；`_serialize_state` 会把 dict 原样嵌进 prompt（`decision_backends.py:522-527`）。因此脱敏责任必须在 TS 构造侧（Q3.2 第 7 点），Python 侧只能做"凭据后缀/bearer/sk- 字面量"的最后防线（可在 `decide()` 入口、`_validate_input` 之后对 `task_summary`/`failure.summary` 字符串字段跑一次 `_redact`）。

---

## Q6 失败模式与字段完整性

**总原则**（对齐 spec.md DS-4 与 AC-004：不可用/低置信/超授权面/输入缺失 → 一律上抛人，禁止默认动作；`pm-state.md:47`、`spec.md` AC-004）：

- **分层处置**：(a) TS 构造侧发现 required 缺失/类型错 → **不发起调用**，返回 `unavailable("input-incomplete")`（复用 `triage-client.ts:151-153` 的 unavailable 形态），DP-1 语义退回"无建议"（派发本身不受影响，`ui-bridge.ts:241-242` 的旁路契约）；对**binding 类**决策点（本 key 后续交付）等价于"不执行任何自动动作 → 上抛人"。(b) Python 侧发现 structured state 缺 required → `DecisionInputError`（exit 2，stderr 带字段名）——这是调用方 bug，不该伪装成服务不可用。(c) 服务/模型侧失败 → 现有 8 类 reason（`decision.py:88-99`）不变。
- **判定规则**：
  - `required`：字段缺失、类型错、枚举越界、超长（summary 类 cap）→ **缺失即拒绝**（拒绝=不调用/exit 2，绝不是猜默认值）。
  - `optional`：缺失 → 字段整体省略，不影响调用；但**不许填占位默认值**（如 `risk: "low"`），避免伪造判据。
  - 条件必填：`progress.*` 仅 checkpoint 类 dp 必填；`failure.*` 仅失败处置类 dp 必填；`scope.*` 仅派发类 dp 必填（矩阵进 schema 草案的 `required_if`）。
  - 一致性校验（缺失即拒绝）：`authority_tier=P0` 的 dp 一律拒绝调用（P0 永久人工，`pm-state.md:45` DS-1）；`elapsed_min > budget_min` 时 `risk` 必须非 low（机器口径 `computeRisk`，`worker-mode.ts:351-368`）；`failure.exit` 与 `failure.kind` 必须同现。
- **机读失败信号对照**：Q1.1#11 的 `error_kind` 不存在 → schema 的 `failure.kind` 枚举由 TS 构造侧从 `run.json.status/exit`（可得）+ `[MODEL_ERR]` 行首（需解析）归一，枚举建议：`model-error | wall-timeout | exit-nonzero | needs-clarification | lost`（与 `RunStatus` 枚举 `run-store.ts:29` 对齐，model-error 对应 `worker-mode.ts:3841-3848` 的 [MODEL_ERR] 写点、exit 3 语义）。

---

## State Schema 草案（可直接进 design）

约束：序列化（canonical JSON：排序键、无空白）后 ≤2000B；所有路径相对 repo 根；L2 级内容无承载字段。`S` 敏感级 ∈ {L0, L1}（L2 结构性不存在）。

```jsonc
{
  "v": 2,                          // int, required, L0 — schema 版本，digest 覆盖
  "dp": "dp1|dp2-checkpoint|dp3-clarify|dp4-failure|dp5-flaky|dp6-qg|dp13-release",
                                   // string enum, required, L0 — 决策点 id
  "key": "<owner-key>",            // string, required, L0
  "task_key": "<task-key>",        // string, optional, L0
  "phase": "SPEC|DESIGN|EXECUTE|...", // string, required, L0
  "task_type": "coding|research|review", // string enum, required, L0
  "requested_type": "coding|research|review", // string enum, required_if dp=dp1, L0
  "risk": "low|mid|high",          // string enum, required, L0 — 机器 computeRisk 或 PM 标注
  "risk_source": "machine|pm-label", // string enum, required, L0 — 判据可溯源
  "authority_tier": "P0|P1|P2",    // string enum, required, L0 — P0 时构造侧短路不外发
  "task_summary": "<≤600B 摘要>",  // string, required_if dp∈{dp1,dp3}, L1 — PM 生成，禁逐字用户原话/凭据/绝对路径
  "scope": {                       // object, required_if dp=dp1, L0/L1
    "write_scope": ["<repo 相对路径，≤3 层>"],  // string[], ≤12 项, L1
    "ext": ["ts","py"],            // string[], ≤6 项, L0
    "images_required": false       // bool, optional, L0
  },
  "progress": {                    // object, required_if dp=dp2-checkpoint, L0
    "elapsed_min": 42,             // int（分钟粒度桶）, required
    "budget_min": 60,              // int, required
    "phases_done": 1,              // int, required
    "phases_total": 4,             // int, required
    "writes": 12,                  // int, optional
    "uniq_targets": 5,             // int, optional
    "repeat_top": 0,               // int, optional
    "artifact_present": true,      // bool, required
    "last_land_age_min": 3         // int|null, optional
  },
  "failure": {                     // object, required_if dp∈{dp4-failure,dp5-flaky}, L0/L1
    "kind": "model-error|wall-timeout|exit-nonzero|needs-clarification|lost",
                                   // string enum, required, L0
    "exit": 3,                     // int, required_if kind∈{exit-nonzero}, L0
    "attempts": 2,                 // int, optional, L0
    "summary": "<≤300B 单行>",     // string, optional, L1 — 已过 §3.2 脱敏
    "test_name": "<符号名>",       // string, required_if dp=dp5-flaky, L1（仅标识符）
    "baseline_known": false        // bool, required_if dp=dp5-flaky, L0
  },
  "ambiguity": {                   // object, required_if dp=dp3-clarify, L0/L1
    "kind": "scope|missing-dep|rule-conflict", // string enum, required, L0
    "question": "<≤300B PM 改写后的问题>"      // string, required, L1
  },
  "closure": {                     // object, required_if dp∈{dp6-qg,dp13-release}, L0
    "blockers_count": 0,           // int, required
    "blockers_kind": ["..."],      // string[] enum, optional, L0
    "evidence_present": true,      // bool, required
    "checklist_done": true,        // bool, optional
    "user_mandated": false         // bool, optional
  },
  "history": {                     // object, optional, L0 — owner key 近 N=20 次聚合
    "recent_done": 4, "recent_failed": 1, "recent_needs_clarification": 0, "recent_lost": 0,
    "recent_superseded": 2         // 返工信号（run.json supersedes，run-store.ts:48-49）
  },
  "questions_version": "dp1@1"     // string, required, L0 — 问题集版本，digest 覆盖
}
```

- 必填矩阵由 `required_if dp=…` 表达；未提及的字段一律 optional。
- 拒绝规则引用 Q6：required 缺失/类型错/P0 dp/占位默认值 → 构造侧拒发；Python 侧 `decision.py:778-812` 加同规则校验，exit 2。
- digest 口径引用 Q4：全字段进 digest，除显式排除的运行时字段（本 schema 未含此类字段，`v/dp/.../questions_version` 全覆盖）。

---

## 验收

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-decision-substitution\evidence\research\spec-structured-input-contract-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

预期：`Q-answered: 6`。
