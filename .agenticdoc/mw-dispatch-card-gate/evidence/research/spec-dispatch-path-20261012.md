# RQ-1 证据：派发路径现状实测（「卡片存在」在哪些点被假定）

- key：`mw-dispatch-card-gate`｜阶段：SPEC｜日期：2026-10-12｜基线 commit：`6c5189831`
- 唯一写入：本文件（`.agenticdoc/mw-dispatch-card-gate/evidence/research/spec-dispatch-path-20261012.md`）；其余一切只读
- 本机：Windows / PowerShell 5.1（无 Git bash）；行内 python 一律写脚本文件再跑
- 未跑：全量 vitest / 全量 pytest / `npm run check` / `build` / `mw build`；无 git 写操作
- 用法：坐标一律 `文件:行号`，跨包路径以仓库根 `H:/git/Multi-Workers` 为锚

---

## §0 术语对齐（先决结论：代码里有两个不同的「卡」，派发路径只知道第一个）

| 名称 | 路径 | 生产者 | 消费者 | 机器可读头 |
|---|---|---|---|---|
| **task book**（worker 任务书） | `.agenticdoc/<key>/workers/<task_key>/task.md` | `dispatch_worker` / `/worker`（TS 侧自写）；conductor（Python 侧自写） | worker 进程（`PI_WORKER_TASK`）、launcher（type/model/RAG/profile） | **有**：`type:`/`phase:`/`model:`/`write_scope:`/`read_scope:`/`deny_globs:` |
| **card**（任务卡/协作卡，本 key 说的「卡片」） | `.agenticdoc/<key>/tasks/<T-NN-slug>.md` | PM 手工（write 工具 / bash），**没有任何工具写点** | autopilot conductor 的 EXECUTE 循环（任务身份 = `tasks/` 文件 stem，D-111）；人工审计 | **无** |

**实测（关键）**：现有卡片**没有 `type:` 头**，`read_task_type` 读不到类型：

```
$ python -X utf8 probe-rq1c.py
.agenticdoc/mw-guard-form-hardening/tasks/T-19-residual-fixes.md
   py type=None source=missing -> role=coding
```

（卡片首行是 `# T-19 — ...`，属 markdown 标题，既不是 `---` 也不是 `key:` 形状。）
⇒ 任何「以卡为唯一权威」的门禁**不能假定** `readTaskType` 能在卡上工作；"卡 → type/角色" 的映射在现有语料上**不存在**。

判别依据（源码）：`packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts:141` `readTaskType`（头区首值），
Python 镜像 `packages/multi-workers/mw_common.py:440` `read_task_type`；两者对 342 个现存 `task.md` 逐文件一致（见 §3）。

---

## §1 ① 完整派发调用链

### 1(a) 交互式入口：PM 窗口 → `dispatch_worker` 工具

| # | 坐标 | 作用 |
|---|---|---|
| a1 | `packages/coding-agent/src/extensions/agent-team-loop/index.ts:58` | `if (process.env.PI_WORKER_TASK)` 分流：无该 env ⇒ PM 模式（`pmActivate`），有 ⇒ worker 模式 |
| a2 | `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1119` | `registerWorkerTools(...)` 注册 PM 侧工具 |
| a3 | `.../pm/ui-bridge.ts:1823-2059` | `dispatch_worker` 工具本体（`name:` 在 `1825`，`parameters:` 在 `1830`，`execute:` 在 `1881`） |
| a4 | `.../pm/ui-bridge.ts:1830-1893` | **参数面**：`task_key` / `description` / `cli` / `model` / `model_reason` / `type` / `images` / `allow_foreign_write` / `key` —— **没有卡片路径参数** |
| a5 | `.../pm/ui-bridge.ts:1906` | `validateRagEnabled(projectDir)`（RAG 配置不可用 ⇒ 拒绝，先于任何写） |
| a6 | `.../pm/ui-bridge.ts:1910` | `resolveOwnerKeyWithSync(...)` → ownerKey |
| a7 | `.../pm/ui-bridge.ts:1916` | `foreignLiveClaimRefusal(...)` 跨 key 写守卫 |
| a8 | `.../pm/ui-bridge.ts:1919-1926` | cli 白名单 `pi|claude|codex` |
| a9 | `.../pm/ui-bridge.ts:1930` → `.../ui-bridge.ts:1148` `resolveDispatchType` | `type` 参数 → `DISPATCHABLE_TYPES`（5 值）校验；缺省按 cli 派生（pi→coding、claude→review、codex→codex） |
| a10 | `.../pm/ui-bridge.ts:1940-1941` → `.../shared/phase-docs.ts` `dispatchDocGaps` | 相位文档门禁（`spec.md`/`design.md`/`evidence/research/*`）；**不读 `tasks/`** |
| a11 | `.../pm/ui-bridge.ts:1958-1966` | `workerTaskDir(...)` + `fs.existsSync(taskDir)` ⇒ 同名任务冲突拒绝 |
| a12 | `.../pm/ui-bridge.ts:1979-2000` → `.../ui-bridge.ts:1679` `judgeWriteIntent` | 仅当 role 无 write/edit 时判「写面是否可满足」（AC-005a）；`allow_foreign_write` 是逃生舱 |
| a13 | `.../pm/ui-bridge.ts:2010` → `.../ui-bridge.ts:1190` `planDispatchFrontmatter` | 组装 frontmatter（`type:`/`phase:`/`images:`/`model:`/`model-reason:`）并校验模型 |
| a14 | `.../pm/ui-bridge.ts:2026-2038` → `.../ui-bridge.ts:1780` `writeDispatchTaskMd` | **唯一写点**：`mergeAllowForeignWrite`(1756) → `mergeWriteScope`(1765) → `workerTaskDir` → `fs.mkdirSync` → `fs.writeFileSync(taskMdPath, content)`（**`1806`**） |
| a15 | `.../pm/ui-bridge.ts:2041` → `.../pm/task-dispatcher.ts:288` `dispatchTask` | 入队：`task-dispatcher.ts:292` `injectWorkspaceProfile(entry.taskPath)`（读回并可能重写 task.md） |
| a16 | `.../pm/task-dispatcher.ts:299` → `.../shared/worker-store.ts:190` `WorkerStore.upsert` | 写 `.agenticdoc/_workers.parallel`（`worker-store.ts:215` `fs.renameSync`；锁 `shared/file-lock.ts`） |
| a17 | `.../pm/ui-bridge.ts:2056` | 回执文本 `Dispatched worker '...' ... Task file: <path>` |

**落盘点答案（1(a) 的直接问题）**：`workers/<task_key>/task.md` 的落盘在
`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1806`（`fs.writeFileSync(taskMdPath, content, "utf8")`），
唯一入口函数 `writeDispatchTaskMd`（同文件 `1780`）。**内容是 `frontmatter + description + "\n"`，即 PM 的派发描述正文就是任务书正文。**

第二个交互入口 `/worker` 命令（同文件 `2355` `registerWorkerCommands`；`handler` 在 `2368`）走**同一组函数**：
`resolveDispatchType`(2419) → `judgeWriteIntent`(2454-2471) → `dispatchDocGaps`(2477) →
`planDispatchFrontmatter`(2486) → `writeDispatchTaskMd`(2502) → `dispatchTask`(2518)。
差异只有两点：task_key 自动生成 `manual-<Date.now()>`（`2436`），拒绝走 `ctx.ui.notify(..., "warning")` 而非工具返回文本。
⇒ 交互式的**两个**入口是同一判据（工具层）。

### 1(b) 服务侧入口：`_workers.parallel` 队列行 → worker 进程

| # | 坐标 | 作用 |
|---|---|---|
| b1 | `packages/multi-workers/launcher.py:872` `_poll_once` | 每 5s（`DEFAULT_POLL_INTERVAL=5`，`launcher.py:51`）一个 poll 周期 |
| b2 | `launcher.py:891` → `packages/multi-workers/mw_common.py:2138` `archive_stale_entries` | 非终态且 `task_path` 不存在的行归档到 `_workers.stale.parallel`（reason `task.md not found`，`mw_common.py:161`） |
| b3 | `launcher.py:897-917` | reap 已结束进程（`_reap_status`） |
| b4 | `launcher.py:921` `_reconcile_orphans` | `status==running` 但无进程的行收敛（orphan） |
| b5 | `launcher.py:924` → `mw_common.py:1829` `parse_workers_file` | 读队列行（7..9 列均可，**无卡片校验**） |
| b6 | `launcher.py:952-957` | 只挑 `status == "pending"` |
| b7 | `launcher.py:961` → `launcher.py:449` `_validate_task_path` | 只校验**位置形状**：`len(parts)==4 and parts[1]=="workers" and parts[3]=="task.md"`；**不校验存在性** |
| b8 | `launcher.py:973` → `launcher.py:1055` `_spawn` | 生成进程 |
| b9 | `launcher.py:1072-1074` | `_worker_target_config` / `_check_config_tear` / `check_rag_tear` |
| b10 | `launcher.py:1075` → `launcher.py:143` `_read_task_md_fields` | 读 task.md 的 `type:`（`mw_common.read_task_type`）与 `model:`；**文件不可读 ⇒ `("","")` 静默** |
| b11 | `launcher.py:1083-1085` | `_build_env`（凭证隔离）+ `inject_rag_env` |
| b12 | `launcher.py:1086` → `launcher.py:523` `_build_command` → `launcher.py:534` `_starter_prompt` → `launcher.py:495` `_require_task_file`（`launcher.py:445` raise `task.md not found`） | **唯一的「任务书存在性」检查，且在 spawn 阶段** |
| b13 | `launcher.py:1111` `subprocess.Popen(cmd, env=..., cwd=...)`；`launcher.py:1120` `_update_status(..., "running")` | 起进程 |
| b14 | worker 侧 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:1836` `workerModeActivate` | 读 `PI_WORKER_TASK`（`1842`），不存在 ⇒ `process.exit(1)`（`1845`）；`1848` `parseTaskMd`；`1891` `dispatchRefusal` |
| b15 | 失败方向：`launcher.py:1124-1129` | `_record_spawn_failure`（`launcher.py:57`，写 `<task_dir>/worker.log`）+ `_update_status(..., "failed")` |

### 1(c) 第三条生产写入点：autopilot conductor（同属「服务侧」，但不是 mw 队列消费方而是生产者）

- `packages/multi-workers/autopilot/dispatch.py:467` `dispatch()`：写 `task.md`（`625`）+ 队列行（`667` `mw_common.upsert_worker_row`）+ 回读校验。
- 其**任务身份来自 `tasks/` 卡片 stem**：`autopilot/conductor.py:1322` `execute_loop` 扫 `key_dir/"tasks"`（`1342`），`conductor.py:1302` `_plan_task_order` 按 plan.md 出场序排。
- ⇒ 只有 conductor 这条路径**真的以卡为输入**；`dispatch_worker` 与服务队列消费**都不读卡**。

---

## §2 ② 假设点清单（逐条：坐标 + 判断依据）

| # | 假设 | 坐标 | 判断依据 |
|---|---|---|---|
| **A1** | 「派发描述 = 任务唯一权威」，无卡片参数 | `pm/ui-bridge.ts:1830-1893`（参数表） | 参数面无 card/路径字段；`ui-bridge.ts` 全文无 `tasks/` 读取（grep 0 命中） |
| **A2** | 卡存在是因为**刚写了一张**（`workers/.../task.md`） | `pm/ui-bridge.ts:2026-2038` + `1806` | 写点从 `description` 直接生成正文；PM 侧的 `tasks/*.md` 卡**从不被读**，存在性无检查 |
| **A3** | 「文档门禁 = spec/design/evidence」，`tasks/` 不在门禁内 | `pm/ui-bridge.ts:1941` → `shared/phase-docs.ts` `dispatchDocGaps`/`phaseDocGaps` | 该模块只 stat `spec.md`/`design.md`、数 `evidence/research/*` 与 `spec.md` 的 AC/§0；**无 `tasks/` 分支** |
| **A4** | 卡的写面可满足性只需在「无 write/edit 角色」上判 | `pm/ui-bridge.ts:1979-2000` → `1679 judgeWriteIntent` | 只有 `isWritelessRole(type) && !isShellRole(type)` 才判；`coding/vision` 等写角色**无写入面准入检查** |
| **A5** | task.md 一定可读；不可读也照样入队 | `pm/task-dispatcher.ts:292` `injectWorkspaceProfile` | 读失败只 `console.error` 后 `return`（`task-dispatcher.ts:241-263` 内 try/catch），`299` 的 `store.upsert` 仍执行 |
| **A6** | 队列行一定指向一张合规任务书 | `shared/worker-store.ts:190` `upsert`；`mw_common.py:1829` `parse_workers_file` | 行解析只要求 7..9 列 + task_key 非空；无 task 类型/卡路径/卡集合任何交叉校验 |
| **A7** | 「位置合法」=「卡可用」 | `launcher.py:449` `_validate_task_path` | 实测（P3）：**不存在**的 `.../somekey/workers/t1/task.md` 通过校验（`validate: ACCEPTED (file does not exist: False)`） |
| **A8** | 卡不可读 ⇒ 类型空 ⇒ 角色回退 coding | `launcher.py:143-164` `_read_task_md_fields` | `OSError → ("", "")`；实测（P2）`_read_task_md_fields(missing) -> ('', '')`；`mw_common.py:296 resolve_dispatch_model` 用 `TASK_TYPE_TO_ROLE.get(task_type, "coding")` |
| **A9** | 任务书的唯一必需属性是「文件存在」 | `launcher.py:437-448` `_require_task_file` + `495` | 仅 `if not p.exists(): raise`；**无内容/分段/合规检查** |
| **A10** | 无 `type:` 头的任务书按 full 工具集运行（fail-open） | `worker/worker-mode.ts:340`（`?? "default"`）→ `worker-mode.ts:113-114` `toolsForType` | 实测（probe-rq1.mjs）：`no-type-no-sections` ⇒ `parseTaskMd.type=default`，`toolsForType=["read","write","edit","bash","find","grep","ls"]`，`isWritelessRole=false` |
| **A11** | 只有 `origin: conductor` 才 fail-closed；手工/无 origin 的任务书**无类型也照跑** | `worker/worker-mode.ts:617` `dispatchRefusal`（`if (meta.origin !== "conductor") return undefined;`） | 实测同上；`appendHeaderAudit`（`worker-mode.ts:581`）只写 trace 审计行（`[HEADER] unregistered-type-fallback`），不改结局 |
| **A12** | 卡集合与派发集合一致 —— **conductor 路径**：不一致是「synthetic blocking gap」；派发了一条不在 plan 里的卡只是 `config` 事件 | `conductor.py:2433` `_missing_plan_tasks`、`conductor.py:1366-1371`（orphan 事件） | plan 引用的 `T-NN-slug` 无 `tasks/` 文件 ⇒ blocking gap；反向（`tasks/` 有卡但 plan 未提）只留 timeline `config` 行，不拦 |
| **A13** | EXECUTE 阶段 `tasks/` 只需**非空**（数量），不校验是哪张 | `shared/pm-state-guard.ts:186-191` | 只数 `*.md` 个数 `< 1` 才 warning；且该 warning 仅在 `switch_key`/takeover 时呈现（`pm/ui-bridge.ts:346`） |
| **A14** | `allow_foreign_write: true` 是「留审计」的逃生舱 | 写入 `pm/ui-bridge.ts:1756-1758`；参数 `1868-1874` | **只写不读**：TS 侧除写点外仅作为 `judgeWriteIntent` 的入参（`1698`），Python 侧 0 命中（`grep allow_foreign_write packages/**/*.py` 无结果）⇒ 事后无任何校验器回读该行 |
| **A15** | 派发可追溯「依据哪张卡/哪一版」 | 无坐标（功能不存在） | 全仓 `sha256` 命中均为 goal/proposal/freeze（`autopilot/console.ts:405-406`、`shared/target-config.ts` 等），**无 task.md/卡的 hash 记录**；唯一持久记录是 `_workers.parallel` 行 + task.md 正文 |

---

## §3 ③ 两种入口是否同一判据（实测）

| 轴 | 是否共用同一实现 | 实测/证据 |
|---|---|---|
| **`type:` 解析语义** | **是**（跨语言镜像，逐文件相等） | `python -X utf8 -m pytest test_task_type_parity.py -q -s` → `corpus_py_md5_eq_ts_md5=342/342`、`py_ts_field_diff=24/24 equal=true`、`bom_books_readable=7/7`；TS `shared/task-frontmatter.ts:141` vs Python `mw_common.py:440` |
| **type → 角色映射** | **是** | 实测（probe-rq1c）：`TASK_TYPE_TO_ROLE`(py) == `DISPATCH_ROLE_BY_TYPE`(ts)，10 键 `maps equal: True` |
| **工具白名单** | **是**（运行时单一实现） | 白名单只在 `worker/worker-mode.ts:122 activeToolsForType` 决定，经 `rag/tools.ts:400 applyRagTools` → `pi.setActiveTools`；无论哪条入口写的 task.md，worker 都按同一 `type:` 头取同一张表 |
| **type 词汇表（入口可产生的类型面）** | **否** | 实测（probe-rq1i）：交互工具只接受 5 值 `coding/review/research/rag-research/vision`（`shared/dispatch-models.ts` `DISPATCHABLE_TYPES`）；worker 运行时认 10 值 + `fallback`（`worker-mode.ts:70 TOOL_ALLOWLISTS`）。`verifier/repair/phase-writer/reviewer/roadmap-writer` 经 `dispatch_worker` **不可派**（`tool_accepts=false`），但手工/conductor 写进 task.md 后 worker **照用**对应白名单 |
| **写面判据** | **部分否**（两套实现，仅 deny 表语义对齐） | PM 侧 `pm/ui-bridge.ts:1645 judgeWriteTarget` + `1567 pmWriteDenyReason`（注释自称「same six rules and priority as worker-mode.ts::bashWriteDenyReason」）；运行时 `worker/worker-mode.ts:1533 bashWriteDenyReason` + `1571 checkBashWriteScopeTarget` |
| **卡片集合一致性** | **两侧都没有** | 交互侧不读 `tasks/`（A1/A3）；服务队列消费侧不读 `tasks/`（A6/A7/A9） |
| **卡存在性** | 交互侧：由构造保证（自写 task.md）；服务侧：spawn 前 `_require_task_file` | 但**两者都不是**「卡（`tasks/*.md`）存在」的检查 |

**结论（P-04 口径）**：若门禁只落在「工具层」，服务侧（含 conductor / 手工队列行）**必然放行**——两侧没有共同判据，只能共用「解析 task.md 头」这一层语义；
反之只落服务层，交互式派发**已经写了 task.md 才入队**，仍然会造出一张没有 `tasks/` 卡的派发。
⇒ 要满足 AC-001③「两种入口行为一致」，门禁必须同时挂 **工具层写入前** + **服务层 spawn 前**（或把判据下沉到一个两侧都调的校验器里，见 §4）。

---

## §4 ④ 现成可复用校验机件清单

| 机件 | 坐标 | 已有能力 | 与「卡门禁」的距离 |
|---|---|---|---|
| 任务头唯一解析源（TS） | `shared/task-frontmatter.ts:109/117/141/159/169`（`extractTaskHeader`/`readTaskHeaderScalar`/`readTaskType`/`scanBodyTypeLines`/`findTypeEscalation`） | 头区边界 + 首值 + provenance + BOM | **头区**，不做分段；对卡无效（卡无头，见 §0） |
| 任务头唯一解析源（Python） | `mw_common.py:413/419/440/455` | 同上镜像，跨语言 342/342 | 同上 |
| worker 任务书解析 | `worker/worker-mode.ts:336 parseTaskMd`（含 `405-425` 的 `write_scope:` 读取）、`327 writeSurfaceMarkerState` | 全字段（type/phase/timeout/read_scope/deny_globs/write_scope/预算/C2 marker 结构） | 只读**已知 key**；无「必需分段」概念 |
| 工具白名单/角色 | `worker/worker-mode.ts:113 toolsForType`、`122 activeToolsForType`、`128 isShellRole`、`135 isWritelessRole` | type→工具集单一源；Python parity 由 `packages/multi-workers/test_autopilot_l0.py` 锁（`registry_parity=per-type-exact types=7`） | 可直接复用作「卡 → 角色」判定（但卡缺 `type:` ⇒ 回退 full，见 A10） |
| 文档门禁 | `shared/phase-docs.ts` `readPhaseDocs`/`phaseDocGaps`/`dispatchDocGaps` | spec/design/evidence 机械门禁（按相位分层） | 形状可照搬为「卡三段门禁」；**不含 `tasks/`** |
| `tasks/` 计数审计 | `shared/pm-state-guard.ts:186-191` | EXECUTE 阶段 `tasks/*.md >= 1` | 只计数、只在 takeover 呈现 |
| 写面判定（PM 准入） | `pm/ui-bridge.ts:1645/1664/1679/1704` | 写意图 + 目标形状 + deny 表 + 拒绝文本 | 只在写角色之外运行；与运行时守卫两套实现 |
| 写面判定（运行时） | `worker/worker-mode.ts:1533/1571` | bash 写目标提取 + deny/scope 判定 + trace 审计 | 已在 task.md 的 `write_scope:` 上工作（生产/消费闭环） |
| 交付物判定（**结果侧**） | `shared/deliverable-evidence.ts`（`hasDeliverableEvidence`、`findNonEmptyReport`、`hasNonPlaceholderProduct`） | 「这次运行交付了东西吗」三通道判据 + 占位符词表 | 问的是 **worker 产出**，不是**卡的「交付物」段**；语义不可混用 |
| 输出分段读取器 | `shared/output-sections.ts`（`SECTION_SPLIT_RE`、`readTerminalDetail`） | `## <title>` 分段 + 占位符过滤 | 分段机制可复用为卡片三段提取器（需换标题词表与来源文件） |
| 卡身份/集合机件（Python，conductor 侧） | `conductor.py:2407 _phase_artifact_present`、`2417 _plan_task_file_stems`、`2433 _missing_plan_tasks`、`1302 _plan_task_order`；`autopilot/state.py:327 artifact_mtimes`（`tasks` stem → mtime） | 「plan ↔ tasks/ 卡」差集 + stem 快照 | **最接近 AC-003①**；但只在 autopilot EXECUTE 回路里，且不读 PM/manual 队列 |
| 类型注册表 + 派发回读校验（Python） | `autopilot/dispatch.py:71 REGISTRY`、`146 tool_set`、`467 dispatch`（回读校验 `row_verified`） | conductor 的 type→工具集→路由 + 行回读 | 供 `test_autopilot_l0.py` parity 使用 |
| 审计逃生舱落盘位 | `pm/ui-bridge.ts:1756-1758` `mergeAllowForeignWrite`（写 `allow_foreign_write: true` 到 task.md frontmatter） | 形态可照搬（AC-004 的「显式例外 + 留审计」） | 注意：**当前无任何回读方**（A14），照搬时必须补「可被 rg 检索」的验收 |
| 内容 hash 机件 | `mw_common.py` `sha256_eol_normalized`（供 `mw freeze`/`mw rag sync` 用，调用见 `mw.py:1010/1030`、`1085`） | EOL 归一化 sha256（避免 CRLF 误报 drift） | 直接可用于 AC-003②「卡路径 + sha256」，判别力已被 freeze/drift 流程验证 |

---

## §5 ⑤ 失败可观测性（若在派发点拒绝，错误走到哪里）

### 5.1 工具层拒绝（交互式）
- 通道：`dispatch_worker` 返回 `{content:[{type:"text",text}]}`（`pm/ui-bridge.ts` 各处 return）；`/worker` 走 `ctx.ui.notify(..., "warning")`。
- 可见范围：**PM 模型本轮上下文可见**（tool result / notification），**不落任何文件**（无 trace、无审计行）。
- 实测证据（`test/suite/mwds-t02-write-intent.test.ts`，35 passed）：
```
[VERIFY] VC-015 refusal_text="[worker-write-surface] task 'manual-1791793835142' has type 'review', which has no write/edit/bash tool, but its task book requires writing to '.agenticdoc/other/evidence/x.md' — unsatisfiable for this role.
Fix (pick one):
1. Put the deliverable in the task's own dir: worker_file file="report.md" ...
2. Re-dispatch with allow_foreign_write: true — recorded in task.md frontmatter ...
3. Use a role with write tools: type: coding | repair | vision."
```
  同文件断言 `expect(workerTaskDirs(root, "_scratch")).toEqual([])`、`expect(store.readAll()).toEqual([])` ⇒ **零侧效应**（无 task 目录、无队列行）。

### 5.2 服务层拒绝（三条通道，实测）
| 场景 | 通道 | 结果 | 实测 |
|---|---|---|---|
| pending 行但 `task.md` 不存在 | `launcher.py:891` `archive_stale_entries`（**先于 spawn**） | 行从 `_workers.parallel` **静默移除**，落 `_workers.stale.parallel`（`task.md not found`） | 见 §7 P6 |
| 位置不合法（如 `.agenticdoc` 根下的 task.md） | `launcher.py:961-967` | `_record_spawn_failure` + 行 → `failed` | 源码；`launcher.py:449` 注释记 OverCode 事故 |
| spawn 阶段文件消失/CLI 缺失/凭证缺失 | `launcher.py:1124-1129` | `worker.log` 追加 `[launcher] spawn failed (...)` + 行 → `failed` | 见 §7 P7（`task.md not found: ...`，行 `t-missing \| failed`） |

- **PM 可见性**：终态 worker 回读文本会带续跑指令（`pm/pm-orchestrator.ts:781` `PM_CONTINUE_HINT`：「failed→读 worker.log 与 trace.log 排查」）；队列行状态经 `list_tasks`（`pm/ui-bridge.ts` 工具）与底部 widget（`renderWatchLines`）可见。
- **归档通道是否被 PM 看见：未见任何消费方**（`_workers.stale.parallel` 无 TS/Python 读取点）⇒ 5.2 第一行是「静默消失」而非「失败」。
- **卡（`tasks/*.md`）缺失：零错误面**。没有任何入口/服务侧读它，因此 T-20 事件除了 worker 自己如实上报外，**框架侧完全不可观测**（与 incident README §2.2「不可追溯」一致）。

### 5.3 成功路径的可追溯性缺口
- 唯一持久记录：`_workers.parallel` 行 + `<task_dir>/task.md` 正文。
- **无卡路径/无卡 hash**（A15）；`allow_foreign_write` 写了但无回读者（A14）。

---

## §6 ⑥ 未验证的怀疑清单（本 RQ 未证）

1. `mw doctor` / `mw status` 是否呈现 `_workers.stale.parallel` 与 `failed` 行的 reason（只查了 launcher/PM 侧；`mw.py:3843` 有 `failed = any(refused(entry) ...)` 但未展开）。
2. 卡片（`tasks/*.md`）与派发 `task_key` 的**命名映射**是否有既定契约：实测 key `mw-guard-form-hardening` 有 19 张卡 / 36 行队列，卡 stem `T-NN-slug` 与 task_key `mwgf-tNN-slug` 靠人工约定对齐（我的 token 匹配是近似：18 行可机械匹配，18 行为 QC/RQ/DRQ/smoke 等按设计无卡的派发）。AC-003① 的「集合 ⊇」需要一个显式映射规则，否则不可机器判定。
3. `dispatch_worker` 是否在某些历史版本接受过卡片路径参数（未查 git history）。
4. `write_scope:` 头缺失时运行时默认面（own taskDir + `<key>/evidence`）与 PM 侧 `renderDefaultWriteScope` 的一致性（本 RQ 只读代码，未做穷举对拍）。
5. `origin` 缺失（manual）任务带上 `type: verifier` 等 conductor 类型时，是否应被视为异常（当前 `dispatchRefusal` 直接放行；影响面未知）。
6. `injectWorkspaceProfile` 读失败时 `console.error` 输出是否进入任何持久日志（`mw.log` 捕获 worker/launcher stderr，但 TS 扩展侧的 stderr 归属未验）。

---

## §7 原始输出（逐条，未经修饰）

### P1/P2/P3/P4/P5（Python 侧，probe-rq1.py / probe-rq1b.py）
```
== P1: cardless text -> type ==
read_task_type: TaskTypeReading(type=None, source='missing', bom_stripped=False)
role fallback: coding
== P2: launcher._read_task_md_fields on a MISSING task.md ==
_read_task_md_fields -> ('', '')
== P3: _validate_task_path on a NONEXISTENT but well-formed path ==
validate: ACCEPTED (file does not exist: False )
== P4: _require_task_file on the same nonexistent path ==
require raised RuntimeError: task.md not found: C:\Users\WENBOZ~1\AppData\Local\Temp\tmpl2pxht3t\.agenticdoc\somekey\workers\t1\task.md

== P5: parse_workers_file accepts a hand-written row (no card check) ==
rows: [{'task_key': 'hand-made', 'status': 'pending', 'cli': 'pi', 'provider': 'timi', 'task_path': 'C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\tmpaoqepu_5\\.agenticdoc\\somekey\\workers\\t1\\task.md', 'dispatched_at': '2026-10-12T00:00:00+00:00', 'updated_at': '2026-10-12T00:00:00+00:00', 'model': '', 'origin': 'manual'}]
task.md exists on disk: False
worker_path_key(row): somekey
```

### P6（归档通道，probe-rq1h.py）
```
archived: ['t-missing']
queue rows now: []
stale file: C:\Users\WENBOZ~1\AppData\Local\Temp\tmpn3w93ur4\.agenticdoc\_workers.stale.parallel
t-missing | pending | pi | timi | C:\Users\WENBOZ~1\AppData\Local\Temp\tmpn3w93ur4\.agenticdoc\somekey\workers\t-missing\task.md | 2026-10-12T08:30:53+00:00 | 2026-10-12T08:30:53+00:00 |  | manual | 2026-10-12T08:30:53+00:00 | task.md not found
```

### P7（spawn 失败通道，probe-rq1g.py；stderr 行由 PowerShell 回显）
```
== before: queue row ==
t-missing pending C:\Users\WENBOZ~1\AppData\Local\Temp\tmpt1d6pboj\.agenticdoc\somekey\workers\t-missing\task.md
== after: queue row ==
t-missing | failed
== worker.log ==
exists: True
[launcher] spawn failed (2026-10-12T08:30:48+00:00): task.md not found: C:\Users\WENBOZ~1\AppData\Local\Temp\tmpt1d6pboj\.agenticdoc\somekey\workers\t-missing\task.md
```

### P8（TS 侧：无 type / 无分段 / 写面 marker，probe-rq1.mjs）
```
-- no-type-no-sections
   readTaskType: {"source":"missing","bomStripped":false}
   parseTaskMd.type: default | origin: undefined
   toolsForType: ["read","write","edit","bash","find","grep","ls"]
   activeToolsForType: ["read","write","edit","bash","find","grep","ls"]
   isShellRole: true | isWritelessRole: false
   writeSurfaceMarker: absent
-- type-only
   readTaskType: {"type":"research","source":"header","bomStripped":false}
   parseTaskMd.type: research | origin: undefined
   toolsForType: ["read","find","grep","ls","bash"]
   activeToolsForType: ["read","find","grep","ls","bash","worker_file"]
   isShellRole: true | isWritelessRole: true
   writeSurfaceMarker: absent
-- type-coding-no-sections
   readTaskType: {"type":"coding","source":"header","bomStripped":false}
   parseTaskMd.type: coding | origin: undefined
   toolsForType: ["read","write","edit","bash","find","grep","ls"]
   activeToolsForType: ["read","write","edit","bash","find","grep","ls"]
   isShellRole: true | isWritelessRole: false
   writeSurfaceMarker: absent
-- full-card-manual
   readTaskType: {"type":"research","source":"header","bomStripped":false}
   parseTaskMd.type: research | origin: undefined
   toolsForType: ["read","find","grep","ls","bash"]
   activeToolsForType: ["read","find","grep","ls","bash","worker_file"]
   isShellRole: true | isWritelessRole: true
   writeSurfaceMarker: absent
== writeSurfaceMarkerState ==
none: absent
ok: ok
half: malformed
```
（对照：`test/extensions/agent-team-loop-checkpoint-wiring.test.ts:318-320` 也断言未知类型经 fallback（含 write）；
上方脚本对 `type-coding-no-sections` 与 `full-card-manual` 的**输出完全相同** ⇒ 「三段齐备」在当前实现里**零判别力**。）

### P9（type 词汇表分歧，probe-rq1i.mjs）
```
DISPATCHABLE_TYPES (tool param vocabulary): ["coding","review","research","rag-research","vision"]
TOOL_ALLOWLISTS vocabulary (worker runtime): ["coding","review","research","roadmap-writer","phase-writer","verifier","reviewer","repair","rag-research","vision","fallback"]
type=coding         tool_accepts=true  worker_tools=["read","write","edit","bash","find","grep","ls"]
type=review         tool_accepts=true  worker_tools=["read","find","grep","ls"]
type=research       tool_accepts=true  worker_tools=["read","find","grep","ls","bash"]
type=rag-research   tool_accepts=true  worker_tools=["read","find","grep","ls","rag_search","rag_symbol","rag_graph","rag_impact","rag_sources","rag_feedback","rag_chat"]
type=vision         tool_accepts=true  worker_tools=["read","write","edit","bash","find","grep","ls"]
type=verifier       tool_accepts=false worker_tools=["read","find","grep","ls"]
type=repair         tool_accepts=false worker_tools=["read","write","edit","bash","find","grep","ls"]
type=phase-writer   tool_accepts=false worker_tools=["read","write","edit","bash","find","grep","ls"]
type=reviewer       tool_accepts=false worker_tools=["read","find","grep","ls"]
type=roadmap-writer tool_accepts=false worker_tools=["read","write","edit","find","grep","ls"]
```

### P10（跨语言 type 解析 parity，`python -X utf8 -m pytest test_task_type_parity.py -q -s`）
```
[VERIFY] fixture: cases=18 base64_inlined=true
[VERIFY] py_vs_fixture=18/24
[VERIFY] ts_vs_fixture=18/24
[VERIFY] py_ts_field_diff=24/24 equal=true
[VERIFY] eol_cross_language=6/6 py_eq_ts_eq_expected=true
[VERIFY] corpus_py_md5_eq_ts_md5=342/342
[VERIFY] bom_books_readable=7/7
8 passed in 0.26s
```

### P11（工具白名单 Python/TS parity，`python -X utf8 -m pytest test_autopilot_l0.py -q -s`）
```
[VERIFY] VC-023: registry_parity=per-type-exact types=7 verifier_entry=explicit ts_buckets=['coding', 'fallback', 'research', 'review']
[VERIFY] VC-023: unknown_rows=0 rejection=type-rejected fallback=none
[VERIFY] VC-023: worker_fail_closed=1 ts_suite=autopilot-protocol.test.ts ts_run=passed manual_fallback=full-set
6 passed in 1.39s
```

### P12（角色映射 + 卡无 type，probe-rq1c.py）
```
py keys: ['coding', 'phase-writer', 'rag-research', 'repair', 'research', 'review', 'reviewer', 'roadmap-writer', 'verifier', 'vision']
ts keys: ['coding', 'phase-writer', 'rag-research', 'repair', 'research', 'review', 'reviewer', 'roadmap-writer', 'verifier', 'vision']
maps equal: True
diff: {}
== same task.md -> same role on both sides ==
.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq1-dispatch-path/task.md
   py type='research' source=header -> role=research
.agenticdoc/mw-guard-form-hardening/workers/mwgf-t20-final-fixes/task.md
   py type='coding' source=header -> role=coding
.agenticdoc/mw-guard-form-hardening/tasks/T-19-residual-fixes.md
   py type=None source=missing -> role=coding
```

### P13（卡集合 vs 派发集合的现场快照，probe-rq1f.py；token 匹配为近似，见 §6.2）
```
cards: 19 rows: 36
cards with NO queue row: ['T-05-fixture-and-corpus']
rows with NO card: ['mwgf-cutover-smoke', 'mwgf-cutover-smoke2', 'mwgf-cutover-smoke3', 'mwgf-drq1-write-guard-design', 'mwgf-drq2-target-axis-design', 'mwgf-drq3-role-key-design', 'mwgf-qga-code-adversarial', 'mwgf-qga2-code-adversarial', 'mwgf-qga3-final-adversarial', 'mwgf-qgb-evidence-chain', 'mwgf-qgb2-evidence-recheck', 'mwgf-qgb3-final-recheck', 'mwgf-rq1-form-inventory', 'mwgf-rq2-direction-contract', 'mwgf-rq3-path-resolution', 'mwgf-rq4-taskmd-corpus', 'mwgf-rq5-key-identity', 'mwgf-t20-final-fixes']
rows matched to a card: 18
```
配合 incident：`.agenticdoc/mw-guard-form-hardening/tasks/T-20-final-ci-and-heredoc-fixes.md` 不存在、`T-20` 不在 `plan.md`（`probe-rq1d.py`：`T-20 in plan.md: False`、`T-20 card exists: False`）。

---

## §8 复现与残留

- 本 RQ 的临时脚本（写入本 worker 自身目录，因写面守卫禁止 `.tmp/` 外写）：
  `probe-rq1.py`、`probe-rq1b.py`、`probe-rq1c.py`、`probe-rq1d.py`、`probe-rq1e.py`、`probe-rq1f.py`、`probe-rq1g.py`、`probe-rq1h.py`、`probe-rq1.mjs`、`probe-rq1i.mjs`
  （按纪律用完即删；正文已内联在 §7，可原样重建）。
- 所有临时工程目录均在系统 temp 下（`tempfile.mkdtemp()`），未触碰仓库工作树。
- 只读复核命令：
  - `python -X utf8 -m pytest test_task_type_parity.py test_autopilot_l0.py -q -s`（`packages/multi-workers`）
  - `node ../../node_modules/vitest/dist/cli.js --run --silent=false test/suite/mwds-t02-write-intent.test.ts`（`packages/coding-agent`）
- 未跑（纪律）：全量 vitest / 全量 pytest / `npm run check` / `build` / `mw build`；无 git 写操作。