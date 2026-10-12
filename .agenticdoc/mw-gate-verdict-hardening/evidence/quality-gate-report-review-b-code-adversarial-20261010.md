# QG-B 代码级对抗核查报告 — mw-gate-verdict-hardening

> 独立证伪审查（B 部分）。Worker: mwg-qg2b-code-adversarial。骨架先行，逐项填充中。

## 0. 口径与边界

- 只读审查：工具面 = read/find/grep/ls + worker_file。**无 bash** ⇒ 不能运行 pytest/vitest/npm/python/git。
- 因此：凡"只能由运行证实"的项（如 G4 面板真实冻结/跟随、E2E 实测数值、`[VERIFY]` 行是否真跑过）结论只能为**无法判定**，并注明 PM 侧运行记录引用。
- 代码可读证（顺序、条件、镜像相等、断言是否连接被测路径）按可读证据下结论。
- 已读全：contract_guard.py（全文）、ui-bridge.ts 写/读面 handler、相关测试；conductor.py（7140 行）按核查项通读目标区段（done 事务、freeze、reminder、dispatch 短路等），非逐行全文。

## 1. 逐项结论

（填充中）

## 2. 对照承重性

（填充中）

## 3. 空洞测试抽查

（填充中）

## 4. 两侧镜像比对表

（填充中）

## 5. 发现的问题清单

（填充中）
# QG-B 代码级对抗核查报告 — key `mw-gate-verdict-hardening`

## 0. 口径与边界

- 本 worker 只有 read/find/grep/ls + worker_file，**无 bash** ⇒ 不能运行 pytest / vitest / npm / python / git。
- 因此凡"只能由运行证实"的命题（对照脚本是否真跑过并转红、面板运行时真实行为、`[VERIFY]` 数值是否真来自实测、文件是否真被改过（无 git diff））一律**无法判定**，并注明 PM 侧运行记录坐标；代码可读证（顺序、条件、镜像相等、断言是否连着被测路径、变异点是否打在判据路径上）按可读证据下结论。
- 已读：`contract_guard.py`（全文）、`gates.py`（关键区段）、`config.py`（全文）、`effective_config.py`（头部契约）、`dispatch.py`（全文）、`ui-bridge.ts`（写/读面与命令面）、`worker-store.ts`（全文）、`run-store.ts`（全文）、`pm-orchestrator.ts`（dispatchNewTasks + 接线）、`monitor.ts`（帧/降级/生命周期）、`launcher.py`（reconcile/poll/spawn）、`mw_common.py`（队列读写者 + run.json + doctor 判据）、`mw.py`（contract-freeze CLI）、`conductor.py` 7140 行中本清单涉及的全部区段（done 事务、freeze、reminder、stall codes、auto-decision ledger）+ 相关测试与 evidence 脚本。未逐行读 conductor.py 全文（超 50KB 截断，按核查项定向读全相关函数）。

## 1. 逐项结论

| # | 结论 | 代码锚点 | 最强反例或不可证伪依据 |
|---|---|---|---|
| 1 | **成立**（顺序） | `conductor.py:2244-2246`（`contract_guard.evaluate`）；写盘序列：`2278` `evidence_dir.mkdir`、`2287-2294` QG 报告、`2297` `_persist_l3_verdict`、`2316-2320` achieved 草稿（tmp+replace）、`2331` `_append_pass_line`（pm-state PASS）、`2334` `advance.advance`、`2379-2380` set-phase 重跑 | 反例候选：拒绝路径经 `mark_stalled`（`conductor.py:2261`）确实**写 achieved.md**（`conductor.py:5205` 追加“## 遗留问题（stalled 草稿）”，文件不存在还会创建）并写 roadmap key-status（`5171`）、stall 门、`stall-lesson.md`（`5214`）——但这是 stall 记账，不是 done 三件套；AC-011 字面（拒绝推进 + timeline 留痕）与 D-014（“不进入 QG/achieved 写入，直接事件 + mark_stalled”）均成立，done 产物（QG 2287 / l3-verdict 2297 / L3 achieved 草稿 2317 / pm-state PASS 2331）一个都没写。旁路：`2243` `phase==DONE ⇒ return "advanced"` 在 evaluate **之前**，但纯只读、零写盘，非“先写后查”。`contract_guard.evaluate` 自身纯只读（只 read freeze/spec/design + `gates.enumerate`）。测试 `test_autopilot_done_contract_guard.py:164-220`（VC-014）断言零 QG/pm-state/l3-verdict 写入 |
| 2 | **不成立**（写面覆盖不全） | 已守入口：`dispatch_worker` 显式 key 拒绝 `ui-bridge.ts:1332-1335`（其后才 `1409` mkdir、`1411` 写 task.md、`1413` 派发行）；`advance_phase` 拒绝 `:1698`（其后 `:1700` 才 `runAgenticScript`）；放行分支 `:233-236`（`_scratch`/`_`/`.` 前缀、无 claim、自有 claim ⇒ null）；读面无守卫：`list_tasks` all/key `:1487-1503`、`mw_status` `:1018-1036`、`/mw doctor` `:2308-2317`、monitor.ts 全文无 claim 检查 | **最强反例：`/worker` slash 命令（`registerWorkerCommands` `ui-bridge.ts:1710`，注册于 `pm-orchestrator.ts:1059`）支持 `--key <任意 key>`，`resolveOwnerKeyWithSync` 对显式 key 直接放行（`ui-bridge.ts:70-71` `if (explicitKey) return explicitKey;`），且该 handler 全程**没有** `foreignLiveClaimRefusal` 调用（全仓仅 2 处调用：`:1333`、`:1698`）⇒ `/worker --key <他人 live key>` 会走 `:1814` mkdir + `:1816` 写 task.md + `:1819` 写队列行，写进他人 live 命名空间。而拒绝文案（`:241`）自己声称 "Refused: dispatch_worker, **/worker**, advance_phase, acking its rows."——文案与实现不符；设计 D-028 也只声明两个入口。测试 `worker-crosskey-readonly.test.ts` 只覆盖工具面，未覆盖 /worker。指定两个 handler 的"拒绝先于副作用"本身成立，但按 AC-024"写面必须拒绝跨 key"的完整口径不成立 |
| 3 | **成立** | TS `worker-store.ts::upsert` `:186-214`：原行槽位替换（`:203` map 只换 idx），不可解析行/注释字节不动，已有文件不补头；Python `mw_common.py::upsert_worker_row` `:1920-1942`（槽位替换/追加，其余行原文）；`update_status` `:1943-1977`（只改匹配行；无匹配⇒已存在文件**不重写**，`:1973-1976`）；`archive_stale_entries` `:1981-2014`（不可解析行原样保留 `:2002-2003`，被移除行进 `_workers.stale.parallel` 归档不截断）；`autopilot/dispatch.py:628`（锁下走 `upsert_worker_row`） | 反例候选：`archive_stale_entries` 仍是"整文件重写"（`_write_workers_file(wpath, kept)` `:2015`），但它删除的只是"非终态 + task.md 缺失"的**可解析**行且逐行归档留痕（`:2007-2010`），不可解析行原样保留——与 AC-023"不得静默删除不可解析行"不冲突；按"只重写自己那一行"的最严字面它重写多行，属其文档化职能（归档）。未发现任何"parse→整表回写丢行"的残留路径；launcher 写队列全部经 `update_status`（`launcher.py:45` import 别名） |
| 4 | **成立** | `_FIRST_SIGHT_BLOCKS` `conductor.py:2622-2625` 仅 `design`(ac/spec) 与 `plan`(vc/design)，tasks/execute/verify/done/空不进映射（`2677` `block is None ⇒ continue`，无补锚）；非空块不重写 `:2703`；每 key 每 tick 至多一次合并原子写 `:2730`（`contract_guard.write_freeze` `contract_guard.py:209-220`，tmp+replace，merge 保另一族原值 `:2719-2727`）；CLI `mw.py::_contract_freeze_plan` `:3905`：已存在且文本变化 ⇒ `refused`（`:3956-3958`，非 `--force`），`--force` 才重冻；exit 1 on refused `:4031/:4051` | 未找到反例：`_freeze_block_first_sight` 的 merge 明确"first-sight write never rewrites an existing block"（`:2716-2718` 注释 + `:2703` 早退）；目标源文件缺失 ⇒ 不锚不报错（`:2706-2708`）。测试 `test_autopilot_contract_freeze.py` + 真活脚本 `evidence/scripts/pm-g3-live-check.py`（freeze→tamper→refuse 链，含"重跑字节稳定"断言） |
| 5 | **成立** | `pm-orchestrator.ts:542-548`：`queue.unparsable.length > 0 ⇒ alarm + return`，位于 `dispatched` 集构造（`:552`）、scope/quota（`:566-568`）、owners 扫描（`:596+`）**之前**；空队列+产物证据守卫 `:664-670`（`hasProductEvidence` `:487-492`）；无证据（新项目）⇒ 走正常派发。双向例均有：`worker-dispatch-guard.test.ts:466-487`（空队列+output.md ⇒ `queue-unreadable` + 零行；fresh ⇒ pending 行） | **边界（已由 T-15 报告 §5.1 如实登记）**：空队列守卫在 owners 循环**内部**逐 owner 判定——排在证据 owner 之前的真新任务 owner 可先派发（≤配额）后守卫才 return，故混合场景下"新增行数 = 0"不保证（AC-020 字面是"新增行数 = 0"）。scope="pm" 时扫描面 = watch key + _scratch，混合可达。测试只覆盖单 owner 场景 |
| 6 | **成立** | Python 默认：`config.py:68-69` `launcher_max_workers=8`、`dispatch_max_per_scan=3`；域 `config.py:127-128`（1..64）。TS 默认：`status-model.ts:146-147`；域 `status-model.ts:185-186`（[1,64]）——名称/值/域逐项相等；TS 运行面 `DEFAULT_DISPATCH_MAX_PER_SCAN=3` `pm-orchestrator.ts:466`，`readDispatchMaxPerScan` `:469-483`（坏配置回落 3）。launcher：`launcher.py:824`（`_poll_once` 内 None ⇒ `mw_common.launcher_max_workers`）+ `:927`（run() 同样解析），`mw_common.py:1803-1820`（越界/坏配置 ⇒ 回落 8，永不为无界）；`_workers.acked` 参与：`launcher.py:867`（read_acked）+ `:874-886`（acked 但行非终态 ⇒ 收敛为 run.json 终态否则 done，不 spawn）+ `:893`（`if key in acked: continue`，永不 spawn） | 反例候选：`mw_common.launcher_max_workers` 只检查 `limit < 1` 未显式 clamp ≤64，但项目层值经 `config.validate_config`（1..64，越界 ⇒ ConfigError ⇒ `except` 回落 8）+ 机器层仅 2 个 xkey 键可覆盖（`effective_config.py:56-59`）⇒ 不可达越界值。配置 20 键两侧逐键相等（`config.py:56-75` vs `status-model.ts:131-152`，含 `autopilot-config-sync.test.ts:158-159` 运行级 parity） |
| 7 | **成立** | run.json 由 **worker 自写**：`worker-mode.ts:719-734` 启动写 `running`（run_id/owner_key/kind/pid/supersedes），`finishRun` `:800-806` 在每条退出路径写终态；launcher 只补 `lost`：`mw_common.mark_run_lost` `mw_common.py:1735-1757`（只置 `status=lost`+`ended_at`、丢陈旧 exit、其余字段原样），唯一调用点 `launcher.py:612`。`lost` 触发的层级顺序（`_reconcile_orphans` `launcher.py:555-650`）：own 行跳过（`:580`）→ `[END]` exit 优先（`:583-585`）→ run.json 终态收敛（`:586-590`）→ run.json running/pending 且进程不在：有 output.md 即判，否则静默窗口 + 无其它活 launcher 才 `mark_run_lost`（`:591-615`）→ output.md ⇒ failed（`:616-618`）→ 静默 ⇒ failed | `supersedes` 拒派（按 AC-022 修订口径"目标**未**终态 ⇒ 拒"）：`run-store.ts:189-199`（`supersede-unknown`/`supersede-not-terminal`），接线 `pm-orchestrator.ts:1124-1133`；注意字面反向读法："指向已终态旧目录 ⇒ 拒"**不成立**——已终态目标是被设计放行的合法替换（`run-store.ts:200-201`，测试 `worker-dispatch-guard.test.ts:372-405`），拒的是未知/未终态目标 |
| 8 | **成立** | 默认阈值 `gate_reminder_after_min=30`（1..1440）`config.py:74`；上限 `gate_reminder_max=2`（1..2，配置只能调低）`config.py:75`；判定 `conductor.py:2522-2553`（三条件：age≥n×阈值、无非终态行、n≤max）+ `:2574`（max 下限保护）；已答门零残留：`gates.pending_gates` `gates.py:770-772` 只取 `status=="pending"`，无独立状态文件，测试 `test_autopilot_gate_reminder.py:273-283`；`seq` 水位去重读取端：`pm-orchestrator.ts:771-805`（readGateReminders）+ `:838-867`（reminderWatermark=最高已投递 seq，session entry `GATE_REMINDER_ENTRY_TYPE` `:768` 持久化） | 反例候选：`_reminder_count` 从 ledger 计数（`conductor.py:2496-2505`）——answered 门不再出现在 `pending` ⇒ 不再发（成立）；ledger 里的历史 remind 行不会误伤（只按 gate_id 计数）。未见"已终态 stage 的门不提醒"的过滤（见问题清单 #2，属 AC-007 缺口而非本项四要素） |
| 9 | **成立**（代码可读部分） | `PANEL_STALE_MISSED_CYCLES=3` `monitor.ts:74`；`STALE PANEL` 渲染 `monitor.ts:741`（`s.stale===true` 时首行优先位）；触发条件：降级路径 `degradedSnapshot` `:964-992`——anchor（最近一次成功采集时刻）不随失败前进（`:968-973`），`ageMs > intervalMs*3` ⇒ stale（`:972`，严格大于，与 AC-015"超过 3 个周期"一致）；降级帧"沿用上一帧"：`:986` `if (lastGoodSnapshot !== null) return {...lastGoodSnapshot, ...diagnostics}`——payload 复用、collectedAtMs/tickCount 保持 last-good，不抛错不丢帧（每 tick 都 emit，`:1040-1047`）；`startMonitor` 读失败不再吞：`:1044-1046` catch ⇒ `degradedSnapshot`（测试 `autopilot-monitor.test.ts:656+` VC-022，`:574+` VC-020 含"恰好 N 周期不算 stale"边界） | 残余（非本项判据）：`readMonitorState` 内 per-section catch（gates 目录 `:432`、conductor pid `:376`、serve meta `:362`）静默给空段、不打 DEGRADED 标记——只有整体抛错才降级；widget 写失败 `:1050-1054` 仍静默重试（achieved.md §1 已如实声明"只有 widget 写入失败仍是静默失败"）。运行时真实冻结/跟随表现 = 无法判定（需运行；PM 侧记录 `evidence/runs/t-13-g4-freshness-report.md`） |
| 10 | **成立**（静态承重；运行红=无法判定） | 六脚本逐一核查见 §2；T-20"控制 B 曾因不承重被替换"**无法证实**（见 §2 末尾） | 变异点全部打在判据所在执行行（needle 均能在当前源码中找到原句：`worker-store.ts:60`、`mw_common.py:3178/3189`、`launcher.py:824`、`ui-bridge.ts:1332/1698/236/1487`、`run-store.ts:171/189`、`pm-orchestrator.ts:600/629/542/664`），且指名用例都断言该判据的输出（非 mock 自身）。是否真跑过并转红 = 只能由运行证实（PM 侧回执表格声称全红 + `restored: True`） |
| 11 | **成立**（3/4 家族逐项相等；STALL_REASON_CODES 为单侧） | 事件 27：Python `timeline.py:67-104` vs TS `status-model.ts:1042-1083`——逐名比对全等（含 `l3-aborted`/`gate-reminder`/`contract-refused`/`contract-frozen` 四新名）；配置 20：`config.py:56-75` vs `status-model.ts:131-152`（名称、值、INT_RANGES `config.py:121-139` vs `status-model.ts:180-191` 全等）；`authorizes` 闭集 2：`gates.py:180` `{retry, contract-change}` vs `status-model.ts:651` `["contract-change","retry"]`（成员相等；运行级 parity `autopilot-gate-presentation.test.ts:284-300`）；`STALL_REASON_CODES` 14：`conductor.py:5322-5338` | **TS 侧不存在 STALL_REASON_CODES 镜像**：全 coding-agent src grep `exec-exhausted|l3-repair-exhausted|stalled-reason-drift` = 0 命中；TS 把 `reason_code` 当不透明串（`status-model.ts:973` `reasonCode: optional("reason_code")`、`monitor.ts:274` 逐字显示）。Python 侧 14 码计数由 `test_autopilot_auto_decision.py:301` 锁死。"两侧镜像"对该家族**不适用**（单侧存在）；achieved.md §7 也只写"STALL_REASON_CODES 12→14"未声称 TS 镜像——未发现单侧多/少/拼写差异 |
| 12 | **成立**（未发现空洞测试） | 抽查 ≥12 个（见 §3）：断言均连着被测路径（真实文件/真实函数/真实接线），无"断言常量即全部"、无"断言 mock 自身"、无裸 `toBeTruthy()` 主断言 | 最弱两类（非空洞但弱）：(a) schema 锁测试（`test_autopilot_gate_schema_v2.py:138-162` 断言冻结常量集合）——靠跨语言 parity 测试承重；(b) `[VERIFY]` 打印行部分回显字面量（`test_autopilot_done_contract_guard.py:259-262` `refused="true"`）而非测量值——断言本身是真的，VC-018"数值来自实测"在这些行上是弱证据 |
| 13 | **成立** | 23 张卡全部带 AC/VC 绑定（`tasks/T-*.md` 头部 "AC: … · VC: …"），无空绑定；抽查与 design §8 覆盖矩阵比对：T-07（AC-005/006/007→VC-007..010）、T-08（AC-008→VC-011）、T-09（AC-005/018→VC-007/VC-023）、T-10（AC-010/011/012→VC-013..015）、T-13（AC-015/016/017→VC-020..022）、T-15/17/18/19/20/22/23（AC-023/020/021/019/022/024/025→VC-024..047）均与 design 矩阵一致 | 轻微观察（非错配）：T-03 引 AC-011 但只配 VC-001/VC-007（AC-011 的 VC-014 在 T-10）——T-03 只拥有事件**词汇**（`contract-refused` 名字），判据归 T-10，属分工而非编号错配；VC-007/VC-011/VC-023 各被 2-3 张卡引用，与 design 矩阵的多卡覆盖一致 |
| 14 | **不成立**（2 处字面与实现不符 + 1 处登记存疑） | §5/§6/§7 各机制均有实现（队列 v2 头 `worker-store.ts:80-83`；doctor 三判据 `mw_common.py:3178/3189/3198`；`l3-aborted` `conductor.py:1983/2016`；配置 14→20 ✓（20 键实测）；事件 23→27 ✓；语料 64→73 ✓（`test_autopilot_config_parity.py:61` `FROZEN_CORPUS_COUNT=73`）） | ① §2 声称"**已终态 stage** ⇒ 零事件"——`pending_gate_reminders`（`conductor.py:2522-2553`）三条件无任何 stage 终态判定，`gates.pending_gates`（`gates.py:770-772`）只按 status 过滤；人工关闭 stage 而门未答 ⇒ 仍提醒（AC-007 明列"已终态 stage 的 gate"不得触发）。② §6 写"同 task_key 声明 `supersedes` 指向**已终态**旧目录即**拒**派"——与实现**相反**（`run-store.ts:189-199`：目标未终态/未知才拒；已终态**放行**，测试 `worker-dispatch-guard.test.ts:372-405` 断言放行）。③ 影响面登记 `autopilot/advance.py`——文件内 grep 无任何本 key 机制痕迹（无 contract/authorizes/reminder/freeze），且 design D-014 明确**否决**修改 advance.py（无 git 无法判定是否无关触碰）。"文件改了但未登记"类：无 git diff，无法判定 |

## 2. 对照承重性（六脚本 + 两个 py 证据脚本）

静态口径：变异行（needle）是否位于判据执行路径 + 指名用例是否断言该判据。运行红/绿本身 = 无法判定（无 bash），PM 侧回执声称全红。

| 脚本 | 控制 | 变异点（needle 在当前源码中的位置） | 对应判据/断言 | 承重 |
|---|---|---|---|---|
| `t15-controls.ps1` | A | `worker-store.ts:60` `WORKER_COLS_MAX = 9;`→8 | 9 列行变不可解析 ⇒ `worker-store.test.ts:197/337`（9 列可读）红 | **承重** |
| | B | `worker-store.ts:203` 原行槽位替换 → 按 parsed 行整表重写（丢弃不可解析行，即 IN-3 删除形态） | `worker-store.test.ts:211/234`（不可解析行保留 + 其余字节不变）红 | **承重** |
| | C | `worker-store.ts:80` `QUEUE_HEADER_RE` → 永不匹配 | `worker-store.test.ts:251`（声明头读出 v2、不补头）红 | **承重** |
| `t17-controls.ps1` | A | `pm-orchestrator.ts:600` PM scope 过滤 → `if (false)` | `worker-dispatch-guard.test.ts:96-122`（scope pm 隔离 + 其它行零变化）红 | **承重** |
| | B | `pm-orchestrator.ts:686` `if (queued >= maxPerScan)` → false | `:390-402/404-420`（配额 ≤N + `dispatch-quota` 告警）红 | **承重** |
| | C | `pm-orchestrator.ts:542` `unparsable > 0` 中止 → false | `:449-464`（坏行中止 + 原文保留）红 | **承重** |
| | D | `pm-orchestrator.ts:664` 空队列+证据守卫 → false | `:466-477`（IN-3 形状拒派 + 告警）红 | **承重** |
| | E | `pm-orchestrator.ts:1108` `recordDispatchAlarm(...)` → `void alarm` | `:160-215`（真跑 `pmActivate`+`agent_settled`，断言 ledger 行**精确相等** + 一次/session）红 | **承重** |
| `t18-controls.ps1` | A | `launcher.py:824` `limit = max_workers if ... else launcher_max_workers(...)` → `10**9` | `test_launcher.py::TestLauncherMaxWorkersBound::test_default_max_workers_is_eight_not_unbounded`（断言 8 非无界）红 | **承重** |
| | B | `mw_common.py:3189` burst 判据 → `if False:` | `test_worker_queue_python_integrity.py::test_doctor_burst_shape_flags_the_in3_fingerprint`（252 行/全非终态 ⇒ issue）红 | **承重** |
| | C | `mw_common.py:1698`（read_acked 坏行 continue）→ 坏行也记为 acked | `test_launcher.py::TestLauncherAckConvergence::test_acked_parse_failure_does_not_skip`（垃圾 ack ⇒ 仍 spawn）红 | **承重** |
| | D | `mw_common.py:1958-1966` update_status 槽位保留 → 丢不可解析行 | `test_worker_queue_python_integrity.py::test_update_status_preserves_unparsable_rows`（"unreadable \| row" 保留）红 | **承重** |
| | E | `mw_common.py:1597` 宽度区间判定 → 只认 7/9 两值 | `::test_parse_workers_queue_counts_rows_and_unparsable_slots`（8 列必须可读）红 | **承重** |
| | F | `mw_common.py:3178` `if unparsable_count:` → `if False:` | `::test_doctor_flags_unparsable_rows` 红 | **承重** |
| `t20-controls.ps1` | A | `run-store.ts:171` `if (kind === "terminal")` → `false &&` | `worker-dispatch-guard.test.ts:341`（终态 run 永不再入列）红 | **承重** |
| | B | `run-store.ts:189` `targetKind = runStateKind(read(targetDir))` → 恒 `"unknown"` | `:372-405`（合法 supersedes 替换被放行 + 旧目录字节/mtime 不变）红 | **承重** |
| | C | `run-store.ts:193` `targetKind !== "terminal"` → `false &&` | `:407-430`（拒绝替换未终态运行，ledger detail 含 `supersede-not-terminal`）红 | **承重** |
| | D | `run-store.ts:124-127` writeRunState 失败 → `throw` | `worker-run-identity.test.ts:115`（run.json 不可写时 output.md 仍落盘）红 | **承重** |
| | E | `pm-orchestrator.ts:598` `outOfScope.push(...)` → 删除 | `worker-dispatch-guard.test.ts:137-155`（`out-of-scope` 聚合告警）红 | **承重** |
| | F | `launcher.py:586` `elif run_status in RUN_TERMINAL_STATUSES:` → `False and` | `test_launcher.py::TestReconcileRunState::test_run_json_terminal_converges_stuck_row` 红 | **承重** |
| | G | `mw_common.py:1750` `data["status"]="lost"` → `"done"` | `::test_run_json_running_with_output_md_becomes_lost` 红 | **承重** |
| `t21-controls.ps1` | A | `worker-store.ts:60`（TS 读侧回 8 列上限） | `worker-store.test.ts:337`（incident 行全可读）红 | **承重** |
| | B | `mw_common.py:1585`（Python 读侧同上） | `test_in3_queue_replay.py::test_current_codec_reads_every_incident_row` 红 | **承重** |
| | C | `worker-store.ts:185` `readRawLines()` 加 filter 丢不可解析行 | `worker-store.test.ts:369`（10 列行跨 upsert 保槽）红 | **承重** |
| | D/E | `worker-store.ts:59` / `mw_common.py:1584` `COLS_MIN=7→9`（拒 8 列 legacy） | `worker-store.test.ts:358` / `test_in3_queue_replay.py::test_current_codec_also_reads_the_legacy_column_shape` 红 | **承重** |
| `t22-controls.ps1` | A | `ui-bridge.ts:1332` `if ((key ?? "").trim())` → `if (false)`（guard 永不触发） | `worker-crosskey-readonly.test.ts:69-94`（拒绝 + 零副作用三断言）红 | **承重** |
| | B | `ui-bridge.ts:1698` `crossKeyRefusal = foreignLiveClaimRefusal(...)` → `null` | `:147-172`（advance_phase 拒绝 + stub 脚本 RAN 标记不存在）红 | **承重** |
| | C | `ui-bridge.ts:236` held-live 判定 → 恒放行 | 两个拒绝用例红 | **承重** |
| | D | `ui-bridge.ts:1487` `if (scope === "all")` → false（读面断掉） | `:178-205`（反向用例：scope all/key **能读** foreign key）红 | **承重**（读面反向用例有独立守卫） |

**未发现"删掉也不改变判据"的不承重对照**（静态判定；27 组变异点全部命中判据行，指名用例全部断言该判据的行为/输出/副作用）。

**T-20"控制 B 曾因不承重被替换为承重变异"核实**：该说法**只**出现在 PM 自写的 `evidence/quality-gate-report-20261010.md:122`（"其中控制 B 曾因**不承重**被替换为承重变异"，证据列指向 `t-20-run-identity-report.md`）。被引来源 `t-20-run-identity-report.md` 全文（含 §5 对照表）**没有**这句话；`tasks/T-20-run-identity-state.md:64` 的对照表也只有当前 B。没有任何工件记录"原控制 B"是什么。⇒ 该声称**不可复现/无法证实**（若按本任务卡的转述"t-20-run-identity-report.md 自称"，则转述本身与事实不符——声称不在该文件里）。当前控制 B 本身是承重的（见上表）。

补充：`evidence/scripts/pm-g3-live-check.py`（freeze→重跑字节稳定→tamper→CLI refused 的真活链）与 `t23-normalize-whole-queue.py`（运维脚本：锁下一次性整表 8 列归一化，v1 逐行无锁写曾引发 WinError 5 混合态）与各自报告的声明相符；后者是一次性 ops 写路径，不在"五个写者"之列。

## 3. 空洞测试抽查（15 项，≥8 要求）

判定口径：断言是否连着被测路径（真实文件/真实函数/真实接线），排除"断言常量即全部 / 断言 mock 自身 / 裸 `toBeTruthy()` 主断言"。

| # | 测试 | 断言样例 | 被测路径 | 连通 |
|---|---|---|---|---|
| 1 | `worker-crosskey-readonly.test.ts:69` "dispatch_worker refuses an explicit foreign live key and writes nothing" | `expect(fs.existsSync(.../t-foreign)).toBe(false)`、`readAll()==[]`、`_workers.parallel 不存在` + 文案含 `[cross-key-read-only]` | 真实 `WorkerStore/IndexStore/AckStore` + 真 `registerWorkerTools` execute | **连通**（副作用零断言打在真实文件系统上） |
| 2 | `worker-crosskey-readonly.test.ts:147` "advance_phase refuses a foreign live key before the gate script runs" | 拒绝文案 + stub `advance_phase.py` 的 `RAN` 标记**不存在** | 真 `registerAdvancePhaseTool` + 会写标记的 stub 脚本 | **连通**（"gate 脚本未被执行"有物理证据） |
| 3 | `worker-dispatch-guard.test.ts:96` scope pm 隔离 | 派发后 keys 集合 + `readFileSync(queue).toContain("o-history")`（其它 key 行保留） | 真 `dispatchNewTasks` + 真队列文件 | **连通** |
| 4 | `worker-dispatch-guard.test.ts:160` 告警接线 | ledger 行 `toEqual([{seq:1, phase:"dispatch-alarm", kind:"queue-rows-unparsable", ...}])` 精确相等 + 二次 settle 不加行 | 真 `pmActivate` + `agent_settled` handler + 真实异步落盘轮询 | **连通** |
| 5 | `worker-dispatch-guard.test.ts:466` 空队列+证据 / fresh 双向 | (a) `queue-unreadable` + `readAll()==[]`；(b) 无告警 + `t-1` pending | 真 `dispatchNewTasks`，双向对照 | **连通** |
| 6 | `worker-store.test.ts:211/234/251` | 重写后原文行数、`lines[1]` 状态位、版本头三态 | 真 `WorkerStore.upsert` + 原始文件字节 | **连通** |
| 7 | `run-store.test.ts:166-223` `evaluateRunIdentity` 全矩阵 | `run-terminal`/`run-active`/`supersede-unknown`/`supersede-not-terminal` + 懒读计数 `reads===0` | 真 run.json 文件 + 真 `readTaskContent` 计数注入 | **连通** |
| 8 | `worker-run-identity.test.ts:73-117` | run.json 内容字段 + `output.startsWith("<!-- mw-run: …")` + agent 首行不被夺占 | 真 `workerModeActivate`（FakeWorkerPi 只替 pi API，不替被测写路径） | **连通** |
| 9 | `test_autopilot_done_contract_guard.py:164` VC-014 拒绝 | `calls == []`（advance 未跑）+ QG/pm-state/l3-verdict 不存在 + 事件 `data` 字段精确 | 真 `conductor._done_transaction`（只 monkeypatch advance） | **连通** |
| 10 | `test_autopilot_done_contract_guard.py:290/306` 无锚 no-op / 冻结未变放行 | `verdict=="advanced"` + `calls==[(k,"done")]` + 无 contract-refused 事件 | 同上 | **连通** |
| 11 | `test_worker_queue_python_integrity.py:101/113/131/175` | `"unreadable \| row" in text`、`read_bytes()==before`、归档文件含被移除行 | 真 `update_status/archive_stale_entries/upsert_worker_row` | **连通** |
| 12 | `test_autopilot_gate_reminder.py:273/225/241` 零残留 / 第三次封顶 / 尾部驱逐 | `_remind_rows()==[]`、`rows==2`、timeline 尾驱逐后仍 `[1,2]` | 真 `conductor.tick` + 真 ledger/timeline | **连通** |
| 13 | `autopilot-monitor.test.ts:574/621/656` VC-020/021/022 | 帧首行 `collected <ISO> tick N`、`workers: 3 running` 于第 2 周期、DEGRADED + last-good payload + 恰好 N 周期不告警 | 真 `startMonitor`（注入 nowMs/readState seam，fake timers 驱动真 setInterval） | **连通** |
| 14 | `test_run_identity.py:39-97` | 跨语言终态集恒等（TS 集合来自解析 TS 源码常量）+ `mark_run_lost` 保留 run_id/artifacts/supersedes/pid + 丢陈旧 exit + fail-safe | 真 `mw_common.read_run_status/mark_run_lost` | **连通** |
| 15 | `test_autopilot_gate_schema_v2.py:138-162` | `FRONTMATTER_FIELDS` 顺序/长度 40、`_REQUIRED_FIELDS` 恰 6、`_LIST_FIELDS` 恰 2 | **模块常量锁**（非行为断言） | **弱连通**（承重靠 `autopilot-gate-presentation.test.ts:206-235` 跨语言 parity 与 `:284-300` authorizes parity；单独看是断言常量） |

**可疑项（最弱三类，均非严格空洞）**：
1. `test_autopilot_gate_schema_v2.py:138-144/151-161` — 断言冻结常量集合（schema 锁），不驱动行为；其价值完全依赖 parity 测试存在（存在 ✓）。
2. `test_autopilot_done_contract_guard.py:259-262`、`autopilot-gate-presentation.test.ts:278` — `[VERIFY]` 打印行部分回显**字面量**（`refused="true"`、`listed_only=true`）而非测量值；上方 assert 是真的，但 VC-018"所有 [VERIFY] 数值来自实测"对这些行不成立（部分键是手写常量）。
3. `worker-run-identity.test.ts:91-93/109/157` — `toBeTruthy()` 仅作辅助存在性断言（主断言在同测试内为精确 `toBe`），不构成空洞主断言。

## 4. 两侧镜像比对表

| 家族 | Python 坐标 | TS 坐标 | 相等与否 |
|---|---|---|---|
| timeline 事件名（27） | `autopilot/timeline.py:67-104`（`EVENT_TYPES` frozenset） | `autopilot/status-model.ts:1042-1083`（`EVENT_TYPES` Set） | **相等**：逐名比对 27/27 全同（`beat, dispatch, worker-terminal, advance, gate-created, gate-answered, stalled, skip, stage-close, config, goal-halt, goal-snapshot, type-rejected, target-config-rejected, reconcile, resume, l3-no-verdict, gate-auto-decision, gate-auto-revoke, review-deceded→review-decided, review-escalated, evidence-reconciliation, stage-reopen-refused, l3-aborted, gate-reminder, contract-refused, contract-frozen`）；运行级锁 `autopilot-event-parity.test.ts:73` |
| 配置键（20） | `autopilot/config.py:56-75`（`DEFAULT_CONFIG`）+ 域 `:121-139`（`_INT_RANGES`） | `autopilot/status-model.ts:131-152`（`DEFAULT_CONFIG`）+ 域 `:180-191`（`INT_RANGES`） | **相等**：20 键名、默认值、区间逐项同（`launcher_max_workers` 8/[1,64]、`dispatch_max_per_scan` 3/[1,64]、`queue_alarm_delta` 50/[10,10000]、`l3_abort_retry_limit` 1/[0,10]、`gate_reminder_after_min` 30/[1,1440]、`gate_reminder_max` 2/[1,2] 及既有 14 键）；运行级锁 `autopilot-config-sync.test.ts:158-159`、计数锁 `autopilot-console.test.ts:911-918`（20 键 + 末 7 键序） |
| `STALL_REASON_CODES`（14） | `autopilot/conductor.py:5322-5338`（含 `l3-aborted`、`contract-unauthorized`）；计数锁 `test_autopilot_auto_decision.py:301` | **不存在**：TS 侧无该集合（grep `exec-exhausted|l3-repair-exhausted|stalled-reason-drift` 在 coding-agent src 0 命中）；`reason_code` 为不透明自由串（`status-model.ts:973` `reasonCode: optional("reason_code")`、`monitor.ts:274/896-897` 逐字透传） | **不适用**：单侧存在。该家族无"两侧镜像"可比对；achieved.md §7 亦未声称 TS 镜像 ⇒ 未发现单侧多/少/拼写差异（无从产生） |
| `authorizes` 闭集（2） | `autopilot/gates.py:180`（`AUTHORIZES_ACTIONS = {retry, contract-change}`；解析期成员校验 `:669-674`） | `autopilot/status-model.ts:651`（`AUTHORIZES_ACTIONS = ["contract-change","retry"]`；闭集校验 `:920`） | **相等**：成员集合一致（顺序不同，无语义）；运行级锁 `autopilot-gate-presentation.test.ts:284-300`（spawn Python dump 后 sorted 比对） |

## 5. 发现的问题清单（按严重度）

1. **[中] `/worker` slash 命令绕过 AC-024 跨 key 写面守卫，且拒绝文案虚假声称已守**
   - 现象：`/worker --key <他人 live key>` 可在他人 live 持有的 key 下创建 task 目录、写 task.md、写 `_workers.parallel` 行。
   - 锚点：handler `ui-bridge.ts:1710-1826`（`:1814` mkdir、`:1816` 写 task.md、`:1819` dispatchTask），显式 key 直接放行于 `ui-bridge.ts:70-71`；全仓 `foreignLiveClaimRefusal` 仅 2 个调用点（`ui-bridge.ts:1333`、`:1698`）；拒绝文案 `ui-bridge.ts:241` 却列 "Refused: dispatch_worker, **/worker**, advance_phase, acking its rows."；注册点 `pm-orchestrator.ts:1059`。
   - 影响：AC-024②"写面必须拒绝跨 key"在 `/worker` 路径不成立；agent 依据拒绝文案以为 `/worker` 已被守卫。设计 D-028 只声明两个入口（工具层），文案超出了设计承诺。
   - 建议动作：`registerWorkerCommands` 在 `resolveOwnerKeyWithSync` 后对显式 `--key` 加同一 `foreignLiveClaimRefusal` 检查（或删掉文案里的 `/worker`）；补 `/worker` 路径的反向用例。
2. **[中] AC-007/achieved.md §2 "已终态 stage 的 gate ⇒ 零事件"未实现**
   - 现象：pending 超阈的门只要 `_workers.parallel` 无非终态行就会提醒，即使其所属 stage 已 closed/halted。
   - 锚点：`conductor.py:2522-2553`（`pending_gate_reminders` 三条件无 stage 终态判定）；`gates.py:770-772`（`pending_gates` 只按 `status=="pending"` 过滤）；`test_autopilot_gate_reminder.py` 无 stage-terminal 用例（grep `stage|closed` 仅 2 处无关命中）。
   - 影响：人工直接编辑 roadmap 关闭 stage 而未答门 ⇒ 对已终态 stage 的门继续提醒（AC-007 明列该类不得触发；achieved.md 声称零事件）。
   - 建议动作：`pending_gate_reminders` 增加门所属 stage 状态过滤（roadmap 已在 tick 内加载），或修订 AC/achieved 口径。
3. **[中低] T-20 "控制 B 曾因不承重被替换"证据链不可复现**
   - 现象：声称只存在于 PM 自写的 `evidence/quality-gate-report-20261010.md:122`；被引来源 `evidence/runs/t-20-run-identity-report.md` 全文无此声明，`tasks/T-20-run-identity-state.md` 亦无；无任何工件记录原控制 B。
   - 影响：AC-014/VC-018 的"已机器校验类声称必须带可复现坐标"在此条上不成立（溯源断裂，无法证伪也无法证实）。
   - 建议动作：在 T-20 回执或 QG 报告补记原控制 B 的变异内容与当时判据失效原因（一行即可恢复可复现性）。
4. **[低] AC-020 "新增行数 = 0"在混合 owner 场景不保证（已登记的取舍，但 AC 字面未反映）**
   - 锚点：守卫在 owners 循环内逐 owner 判定 `pm-orchestrator.ts:664-670`，位于其前的 owner 可先派发（`:686-704`）后守卫才 `return`；T-15 报告 §5.1 已如实记录；测试 `worker-dispatch-guard.test.ts:466-487` 仅单 owner。
   - 建议：AC-020 反向用例补一条"fresh owner 在前 + 证据 owner 在后"的混合场景，或把守卫提前到候选总收集后。
5. **[低] achieved.md §6 supersede 规则表述与实现相反**
   - 锚点：achieved.md "同 task_key 声明 `supersedes` 指向已终态旧目录即拒派" vs 实现 `run-store.ts:189-199`（目标**未**终态/未知 ⇒ 拒；已终态 ⇒ **放行**，测试 `worker-dispatch-guard.test.ts:372-405`）。
   - 建议：修正为"指向未终态/未知旧目录即拒派；已终态放行（唯一合法替换通道）"。
6. **[低] 拒绝路径仍写 achieved.md（stall 记账）**
   - 锚点：`conductor.py:2261`（拒绝分支 `mark_stalled`）→ `conductor.py:5205`（追加"## 遗留问题（stalled 草稿）"，缺文件时创建）。done 三件套（QG `:2287` / l3-verdict `:2297` / L3 achieved 草稿 `:2317` / pm-state PASS `:2331`）确实零写；AC-011 成立，但"不写 achieved"的字面（D-014 措辞"不进入 QG/achieved 写入，直接 mark_stalled"内部即含此张力）不严格成立。
   - 建议：文档口径改为"不写 done 产物（QG 报告 / L3 achieved 草稿 / pm-state PASS）；stall 记账照常"。
7. **[低] achieved.md 影响面登记 `autopilot/advance.py` 存疑**
   - 锚点：`advance.py` 全文无本 key 任何机制（grep contract/authorizes/reminder/freeze = 0）；design D-014 否决项 (b) 明确不改 advance.py。无 git 无法判定是否无关触碰，但"触及"声明找不到对应实现。
   - 建议：核对登记（若仅无关触碰则从影响面移除）。
8. **[信息] monitor 读面的 per-section 静默降级**
   - 锚点：`monitor.ts:432`（gates 目录读失败 ⇒ 空队列段）、`:376`（conductor pid 读失败 ⇒ not running）、`:362`（serve meta）——不触发 DEGRADED 标记；只有 `readMonitorState` 整体抛错才走降级帧（`:1044-1046`）。这些 catch 的原意是"缺失=合法空态"，但读错误与缺失不可区分（AC-017 字面"未受保护的读一律降级"在此不闭合）。widget 写失败静默（`:1050-1054`）已在 achieved.md §1 如实声明。
   - 建议：低优先——per-section catch 区分 `ENOENT`（合法空态）与其余错误（计入 `lastError`）。
9. **[信息] `[VERIFY]` 打印部分回显字面量**（见 §3 可疑项 2）：断言真实、打印弱；VC-018 口径上算瑕疵。
10. **[信息] TS 侧无 `STALL_REASON_CODES` 镜像**（§4）：非缺陷（无消费者、无声称），记录以免下一个 key 误以为存在双侧锁。

无其它问题。核心机制（done-guard 顺序、五个写者槽位保留、freeze 不回溯/不重写、fail-closed 短路、配额/有界、run.json 身份、G4 帧自证、G2 提醒上限）在代码层面全部成立。

[VERIFY] QG-B: items=14 confirmed=12 refuted=2 undecided=0 hollow_controls=0 hollow_tests=0 mirror_mismatch=0 conclusion=conditional
