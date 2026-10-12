# QG Review Report A（证据链 + 覆盖闭合）— key `mw-gate-verdict-hardening`

- 审查者：`mwg-qg2a-evidence-chain`（独立 QG 审查 A：证据链 + 覆盖闭合；对抗性）
- 审查对象：`evidence/quality-gate-report-20261010.md`（**PM 自写，属审查对象**——凡采信必回源码/证据文件复核；差异见 §7）
- 输入：spec.md（25 AC）· design.md（47 VC + Coverage F1–F47 + §11.7/§11.8/§11.10/§11.11）· plan.md · achieved.md · pm-state.md · key-decision.md · tasks/T-01…T-23 · evidence/runs/*（26 份）
- 锚点约定：Python 路径相对 `packages/multi-workers/`；TS 路径相对 `packages/coding-agent/src/extensions/agent-team-loop/`（测试在 `packages/coding-agent/test/`）；`runs/` = `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/`

## 0. 审查口径与边界

- **本卡为何是 supersedes 重派**：首派 `mwg-qg-review-20261010` 的任务书要求只读 review 角色写到自身目录之外（`evidence/quality-gate-report-review-20261010.md`），而 review 角色唯一合法写面是 worker 自身 `report.md`（`worker-file-tool` basename 白名单 fail-closed）⇒ 该卡空转 54s 无交付（pm-state D-063）。本卡写面已修正：唯一写入 = 本 `report.md`，由 PM 收录进 key 的 `evidence/`。
- **工具边界**：白名单 read/find/grep/ls + worker_file；**无 bash** ⇒ 不能跑 pytest / vitest / npm / python / git，不能复算 sha256 / mtime。因此凡"只能由运行证实"的项（测试通过性、控制脚本转红、活体 4s tick / 推送到达 / run.json 实际落盘 / doctor 实际输出）本报告上限 **⚠️**，附"需运行证实；PM 侧记录：<引用>"。
- **三态口径（写死供审计）**：
  - ✅ 充分：判据本体**静态可核**且我已在源码/测试断言/证据记录三处亲眼核到同一坐标（结构、顺序、常量、闭集、守卫位置、格式、断言内容、[VERIFY] 记录原文），且无 open 错误记录。测试套件的"绿"引用 PM/worker 记录但**不构成**判 ✅ 的依据本体。
  - ⚠️ 不足：三层缺层；或判据本体是运行数值/活体行为（无静态断言可锁）；或有实质覆盖缺口；或 PM 报告自身坐标失准（需我重锚）。
  - ❌ 无证据：源码与 evidence/runs 均找不到锚点/记录。
- **全局前提（不逐条降级、单独列债）**：R21——运行时未切换（全局 bundle `~/.pi/agent/extensions/agent-team-loop.js` 2026-10-10 11:40:42 / sha `52187720…`，不含本 key 标记），PM 报告已诚实把 PASS 限定为"**源码+测试级**"（§5.1）。本报告同口径判 ✅ = "源码+测试+记录级充分"；**活体生效** 维度的欠债统一归 R21（用户已知、runbook 待批），不逐条重复降级，但在备注标注。
- **抽查深度声明**：25 条 AC 全覆盖；47 条 VC 全覆盖（每条至少回到 1 个代码锚点 + 1 个命名用例 + 1 条 [VERIFY]/映射表记录）；47 条 Coverage 路径全覆盖；自推交叉问题 12 条（Q-X-001…012）。

## 1. 问题清单与核查结果

### 1.1 Q-AC（25 条，机械生成自 spec §3）

| Q-ID | 描述 | 状态 | 证据/代码锚点 | 备注 |
|---|---|---|---|---|
| Q-AC-001 | G1 中止指纹：事件+持久字段，不得只记"无裁决" | ✅ | `autopilot/conductor.py:1560`（`_L3_ABORT_MARKER`）、`:1565`（尾 64KiB 读）、`:1580`（`_l3_stream_aborted`：marker ∧ 无合格源）、`:1662-1664`（指纹分支在状态门 `:1665` **之前**——本审查重锚实测）、`:1983-1999`（`l3-aborted` 事件，data 8 键）、`:2016`（stall `reason_code="l3-aborted"`）；`test_autopilot_l3_aborted.py:194/214`（P1/P2）；`runs/t-06-l3-tests-report.md` L62-63、`runs/t-01-l3-aborted-report.md` §3 | PM 报告锚点 `:1649/:1651` 已漂移 13 行（X-2）；语义经我重锚后成立 |
| Q-AC-002 | 三类无有效裁决各命中且仅命中一类 | ✅ | `conductor.py:1662`（aborted 先于 no-verdict 分流）+ `:1636`（`_l3_resolve_source` FAIL 判据）；`test_autopilot_l3_aborted.py:487`（`test_vc003_three_way_exclusivity`：a=meets b=aborted c=below）；`runs/t-06-…` L76 | 三分互斥由谓词顺序构造 |
| Q-AC-003 | aborted 有界自动重掷 + 独立计数 + 可配置 | ✅ | `conductor.py:1936`（`l3abort:{key}` 独立 loop）、`:2006-2013`（`abort_used < abort_limit` ⇒ 派 `l3-a{round_no+1}`，共享 stem `used+abort_used`）、`:2016`（耗尽 ⇒ stall）；`config.py:95/119`（`l3_abort_retry_limit` 0..10 默认 1）；`test_autopilot_l3_aborted.py:244/267/292/613`（P3/P4/P5/P8）；`runs/t-06-…` L64-66 | 预算耗尽仍重掷（P4）覆盖 |
| Q-AC-004 | 反向：无 marker / 两节齐备 ⇒ 假阳性=0 | ✅ | `test_autopilot_l3_aborted.py:356-453`（N1-N6）+ `:453`（vc006 六例 sweep）；`runs/t-06-…` L67-75（false_positives=0 ×8 行） | 尾窗切断边界 = in-test X2（`:539`） |
| Q-AC-005 | pending 超阈主动提醒，同门 ≤2 次 | ✅ | `conductor.py:2508`（`_reminder_count`，只数 `phase=="remind"`）、`:2522`（`pending_gate_reminders` 纯判定）、`:2555`（`_remind_pending_gates`）、tick 调用 `:2764`（enabled/paused 后、goal 检测前）；`config.py:96-97`（`gate_reminder_after_min` 1..1440=30 / `gate_reminder_max` **1..2**=2）；`pm/pm-orchestrator.ts:770-799`（消费者读 ledger）+ `:986-989`（`deliverPmAlert`→triggerTurn）；`test_autopilot_gate_reminder.py` 12 例（`test_third_reminder_blocked:225`）；`test/extensions/agent-team-loop.test.ts:2488`（"delivers a new remind row once…VC-007"，断言唤醒空闲 PM）；`runs/t-07-gate-reminder-report.md` L41 | 活体推送到达未观测（R21）；需运行证实；PM 侧记录：t-07 L41 `[VERIFY] VC-007 ledger=1 event=1` |
| Q-AC-006 | answered 后零残留 | ✅ | `conductor.py:2571`（每 tick 从 `pending_gates` 重算，零私有状态）；`test_autopilot_gate_reminder.py:273`（`test_answered_gate_leaves_zero_residual`）；`runs/t-07-…`（VC-009 residual=0） | — |
| Q-AC-007 | 只对 pending gate 生效（非 gate 静默不触发） | ✅ | 两轴 `status-model.ts:1353`（`blockedOnHuman(pendingGates>0 ∧ nonTerminal==0)`，两侧同口径）；`test_autopilot_gate_reminder.py:287/301`（running/pending 行均抑制）+ `:327`（goal-change 门仍提醒）；`runs/t-07-…`（VC-010 in_flight_silent=true） | EXECUTE 稀疏 = 非终态行>0 ⇒ 抑制 |
| Q-AC-008 | 监视面（**面板与 mw doctor**）显示 pending 时长 + BLOCKED_ON_HUMAN | ⚠️ | 面板 ✅：`monitor.ts:442-453`（blockedOnHuman 采集）、`:745-753`（置顶行，`!tickStale` 门控）、`:829`（渲染）；status ✅：`status-model.ts:1338`（`GateView.ageMs`）+ `:1470`；`test/suite/autopilot-monitor.test.ts:489/531`；`runs/t-08-g2-surfaces-report.md` L72 | **实质缺口**：`mw doctor` 面未落地——design D-009 第三面（`mw_common._doctor_gates` 增 `blocked_on_human` + `_gates_text_alerted` 触发 + 文本 `BLOCKED_ON_HUMAN` 后缀）在 `mw_common.py` **grep 0 命中**（本审查实测）；doctor 现状 = `--json` 既有 `waited_s`（`mw_common.py:2750`）+ 24h/72h 文本阈值（`:3149`）。PM 报告 AC-008 行只引 monitor 锚点；t-08 回执全文无 "doctor"；achieved.md 遗留亦未登记。行动项 §4-1 |
| Q-AC-009 | authorizes 显式授权字段（闭集） | ✅ | `gates.py:171`（`_JSON_LIST_FIELDS`）、`:180`（`AUTHORIZES_ACTIONS={retry,contract-change}`，install 排除）、`:659-676`（越界 ⇒ 解析期 GateFormatError）；TS `status-model.ts:756-763/916-920`、`gate-writer.ts:177-196`（闭集校验）；`runs/t-04-contract-guard-report.md` L71（closed_set=2 listed_only=true） | 40 名单外扩展 = D-011 [REVISED] 已裁决（t-04 §R1） |
| Q-AC-010 | worker 提示词硬约束（三处同一常量） | ✅ | `conductor.py:1459`（`_CONTRACT_CONSTRAINT`）逐字拼入 `:1478-1479`（repair）/`:2459-2460`（phase-writer）/`:2490-2491`（fix-writer）；`test_autopilot_done_contract_guard.py`（VC-013 锁）；`runs/t-10-g3-done-guard-report.md` L98（prompts=3 verbatim=true） | — |
| Q-AC-011 | done 前机械授权检查（fail-closed + 留痕） | ✅ | `conductor.py:2221-2268`：`_done_transaction` **第一个 check-before-write** `:2244` 调 `contract_guard.evaluate`（其前仅有 DONE-resume 无写分支）；不过 ⇒ `:2253` `contract-refused`（data={changed_ids,freeze_rel,carrier}）+ `:2265` `mark_stalled(contract-unauthorized)` + return "gated"；`contract_guard.py:384`（evaluate）；`test_autopilot_done_contract_guard.py`；`runs/t-10-…` L99-100 | 生产可达性由 AC-025 锚点补齐（PM 端到端：pm-g3-live-check ④） |
| Q-AC-012 | 仅凭 note 自由文本 ⇒ 未授权 | ✅ | `contract_guard.py:334-348`（`authorizing_gates` 只读 `status`/`authorizes`/`key`；**不读 note/answered_by**——源码亲核）；`runs/t-10-…` L101-106（6 个 carrier 形态 authorized=false） | 构造性成立（D-016） |
| Q-AC-013 | 历史文件 parse + 渲染逐字节不变 | ✅ | `gates.py:146-152`（`_REQUIRED_FIELDS == 6` import 期断言）；`authorizes` 缺省 None（`:659-676` 可选路径）；`mw_common.py:3017-3021`（`_contract_guard_scan` 无 freeze ⇒ None）+ `:3080-3082`（`gates["contract_guard"]` 键不出现）；`runs/t-11-g3-cli-doctor-report.md` L98（freeze_keys=0）、`runs/t-04-…` L73（required_fields=6 create_keys=13） | "历史门全量 parse 成功 / flood 归档"需运行证实；PM 侧记录：t-04/t-11 [VERIFY] + `test_doctor_gates.py` 82 passed（PM 复跑） |
| Q-AC-014 | 每条机器判据附非空洞对照 + [VERIFY] 实测 | ⚠️ | 结构层 ✅：in-test 反事实（`test_autopilot_l3_aborted.py:516/539/566` X1-X3，[VERIFY] 行含 with/without 对照值）；6 个控制脚本存在（`evidence/scripts/{t15,t17,t18,t20,t21,t22}-controls.ps1`）；映射表 `runs/verify-g5g6-tests.md` §3（30 组变异矩阵）；各卡回执对照表（t-01/t-07/t-10/t-11/t-12/t-13/t-14/t-15-t17-t19/t-18/t-20/t-21/t-22/t-23） | "全部实测转红"只能由运行证实；PM 侧记录：各卡回执对照段 + verify-g5g6-tests §3（全红 + `restored: True`）。另：PM QG 报告自身锚点漂移（X-2）削弱 "anchors_present"（见 Q-VC-018） |
| Q-AC-015 | 帧携带绝对采集时刻 + 过期告警 | ✅ | `monitor.ts:74`（`PANEL_STALE_MISSED_CYCLES=3`）、`:204-221`（`collectedAtMs/tickCount/degraded/lastErrorAtMs/lastError`）、`:741-743`（首行 `STALE PANEL (…)`）、`:964-977`（降级帧 stale 计算）；`test/suite/autopilot-monitor.test.ts:574`（VC-020）；`runs/t-13-g4-freshness-report.md` L49 | 活体帧节奏未观测（R21） |
| Q-AC-016 | 数据面变化 ≤2 周期（8s）跟随 | ✅ | `monitor.ts:65`（`MONITOR_INTERVAL_MS=4000` 未改）；`autopilot-monitor.test.ts:621`（VC-021，fake timers 断言 2 周期内跟随）；`runs/t-13-…` L50 | 活体未观测（R21） |
| Q-AC-017 | tick 失败不静默丢帧（降级帧） | ✅ | `monitor.ts:1013-1045`（帧级 try ⇒ `degradedSnapshot`：上一帧+lastErrorAtMs+摘要；首 tick 失败边界有注释+用例）；`autopilot-monitor.test.ts:656`（VC-022 含 FIRST tick fails）；`runs/t-13-…` L51 | D-018 的两处 per-site 保护（worker-store/mw-runner）改为帧级 try 覆盖——t-13 回执披露，语义等价（读都发生在 readMonitorState 内） |
| Q-AC-018 | 会话替换后重挂 | ✅ | `console.ts:734-755`（`monitorCtx !== ctx` ⇒ `stopMonitor()` 后重挂）；`pm/pm-orchestrator.ts:1101`（`session_shutdown` 停表）；`test/extensions/agent-team-loop.test.ts:5846-5881`（VC-023：不同 ctx 必须 stop+re-arm，[VERIFY] 行）+ `:4644`（session_shutdown 无残留 timer）；`runs/t-12-g3-writer-g4-rearm-report.md` L104 | 活体 `/new`/`/resume` 未观测（R21） |
| Q-AC-019 | 派发隔离：PM 作用域收窄 + 越界可见 + 全局写面保留 | ✅ | `pm/pm-orchestrator.ts:601`（scope="pm" 只扫 watch key + `_scratch`，其余入 `outOfScope`）、`:566/581`（`flushScanAlarms` 每 early-return 前发 `out-of-scope`/`run-ledger-conflict`）、`:1116-1119`（`agent_settled` 传 scope/watchedKey）；`scope="cli"` 默认全局（`:551`）；`test/suite/worker-dispatch-guard.test.ts:85/108/123/136`；`runs/t-15-t17-t19-report.md` §3（作用域双向 + 控制 A） | 单次副作用面 O(1)（`outOfScope.push` 之外零写） |
| Q-AC-020 | 行缺失/不可读 ⇒ fail-closed 零派发 + 告警 | ✅ | `pm-orchestrator.ts:543-552`（`unparsable>0` ⇒ `queue-rows-unparsable` 告警 + return）、`:651-657`（空队列 ∧ 产物证据 ⇒ `queue-unreadable` 拒绝；无证据=真新项目放行）；`worker-dispatch-guard.test.ts:223/240`；`runs/t-15-t17-t19-…` §3 控制 C/D | 反向用例（清空队列 ⇒ 0 新增 + 1 告警）in-test |
| Q-AC-021 | 单轮配额 + launcher 永不无界 + acked 参与 | ✅ | `pm-orchestrator.ts:679-685`（`queued>=maxPerScan` ⇒ `dispatch-quota` 告警+return）+ `:473`（`readDispatchMaxPerScan`：opts > config > 默认 3）；`launcher.py:828/929`（`max_workers is None ⇒ mw_common.launcher_max_workers`）+ `:867-875`（acked ∧ 行非终态 ⇒ 收敛 run.json 终态或 done，不 spawn；ack 垃圾 ⇒ 无信息）；`config.py:92-94/116-118`；`test_launcher.py:1147/1217`（4+2 例）；`runs/t-18-queue-integrity-report.md` §3 | spec 标题"新增>N ⇒ 拒绝该轮**全部**派发"与其反向用例①"新增=配额"自相矛盾（X-4）；实现=反向用例/VC-029 口径（配额截断） |
| Q-AC-022 | run.json 产物自带状态 + 身份不可复用 | ⚠️ | TS 路径 ✅：`shared/run-store.ts:34`（`RUN_TERMINAL_STATUSES` 与 Python 恒等）、`:194-227`（`evaluateRunIdentity`：run-terminal/run-active/supersede-unknown/supersede-not-terminal 全拒）；`worker/worker-mode.ts:722-734`（启动自写 running+心跳）、`:796-801/1083`（settle/exit 写终态）、`:857`（process exit 兜底）；`worker/output-writer.ts:94`（marker 不夺 `VERDICT=` 首行）；`launcher.py:587-612`（`[END]` > run.json 终态 > 活动⇒lost，只补 `lost`）；`test/suite/{run-store,worker-run-identity}.test.ts`、`test_launcher.py:TestReconcileRunState`、`test_run_identity.py` | 欠债：**`autopilot/dispatch.py`（Python conductor 派发）未接 run.json 判据**（D-038，PM 已登记为残留）⇒ AC-022 的"派发/重派判据**首先**读该产物终态"仅在 TS 派发路径 + launcher 收敛成立。另 R18（spawn 竞态假 failed）为 open 记录，活体维度不满足"无 open 错误" |
| Q-AC-023 | 行格局可识别 + 读侧不丢行 + 全写者槽位保留 + doctor 三判据 | ✅ | `shared/worker-store.ts:32-33`（`WORKER_COLS_MIN/MAX=7/9`）、`:69-74`（`# mw-queue:vN` 头）、`:168-183`（`readQueue`→{rows,unparsable,version}）、`:190-215`（upsert 槽位回插，不可解析行原文保留，新队列才写头）；`mw_common.py:1636`（`parse_workers_queue`）、`:1920`（`upsert_worker_row`）、`autopilot/dispatch.py:628`（改用 upsert_worker_row）；doctor 三判据 `mw_common.py:3181/3191/3198`；`test_in3_queue_replay.py`（8 例）、`test_worker_queue_python_integrity.py`（13 例）、`worker-store.test.ts:197-379`；`runs/t-21-integrity-report.md` §3（四组数字 250/250全丢/0→1/10→3） | IN-3 夹具 sha `6c4f4dfc…`（记录值，我无法复算） |
| Q-AC-024 | PM 跨 key 只读（读全局/写限定/零副作用） | ✅ | `pm/ui-bridge.ts:221-247`（`CROSS_KEY_READ_ONLY` + `foreignLiveClaimRefusal`：`_`/`.` 前缀、无 claim、`claimId==self` 放行；`held-live` 拒绝+`switch_key` 指引）、`:1331-1336`（dispatch_worker **显式 key** 守卫，在 task.md/队列行写之前）、`:1698-1700`（advance_phase 守卫在 `runAgenticScript` 之前 ⇒ gate 脚本不执行）；读面零改动（list_tasks/mw_status/doctor 不动）；`test/suite/worker-crosskey-readonly.test.ts:106/132/165/194`（4 例）；`runs/t-22-crosskey-readonly-report.md` §3/§4 | 与 `takeOverKey` 共用 `claimState` 活性判据（t-22 §2） |
| Q-AC-025 | G3 锚点框架自建（自动/幂等/不回溯/CLI/无锚放行） | ✅ | `conductor.py:2622-2746`（`_FIRST_SIGHT_BLOCKS`={design:ac, plan:vc}；`_freeze_contract_first_sight` 既有非空块跳过、同 tick 合并一次 `write_freeze`、异常吞掉留痕）、`:2768`（tick step 2c 调用，enabled/paused 后、goal 检测前）；`mw.py:3887-4039/5691`（`contract-freeze` CLI：`--block/--force/--json`，已变更块默认 refused）；`timeline.py:110`（`contract-frozen`）；`test_autopilot_contract_freeze.py`（12 例：幂等 sha 断言/不回溯/`--force`）；`evidence/scripts/pm-g3-live-check.py`（端到端）；`runs/t-23-g3-anchor-report.md` | 无锚⇒放行 = D-015 [REVISED] 有意语义；spec §2.3 的"缺字段⇒视为未授权"字面与其冲突（X-5，design 已论证为 P-018 取舍） |

### 1.2 Q-VC（47 条，机械生成自 design §7 / §11.7 / §11.11）

| Q-ID | 描述（判据摘要） | 状态 | 证据/代码锚点 | 备注 |
|---|---|---|---|---|
| Q-VC-001 | marker ∧ 无合格源 ⇒ aborted + 事件 | ✅ | 同 Q-AC-001；`test_autopilot_l3_aborted.py:194`；`runs/t-06-…` L62（aborted=1 no_verdict=0） | — |
| Q-VC-002 | data 键集逐字=固定八元组 | ✅ | `conductor.py:1990-1999`（round/task_key/worker_status/output_bytes/done_exit_zero/retry_used/retry_limit/recorded_at——源码亲核=8 键）；`test…:214`；`runs/t-06-…` L63（keys=8） | — |
| Q-VC-003 | A/B/C 三类两两不同且各只命中一类 | ✅ | `test…:487`；`runs/t-06-…` L76（exclusive=true classes=3） | — |
| Q-VC-004 | aborted 且专用计数未耗尽 ⇒ l3abort 轮 + 独立计数 | ✅ | `conductor.py:2006-2013`；`test…:244`；`runs/t-06-…` L64（reroll=true abort_used=1） | — |
| Q-VC-005 | 共享预算耗尽仍重掷 | ✅ | `conductor.py:1948-1950`（abort 判据只看 abort_limit）；`test…:267`（P4）；`runs/t-06-…` L65 | — |
| Q-VC-006 | 无 marker / 两节齐备 ⇒ 假阳性=0 | ✅ | `test…:356-485`（N1-N6+vc006）；`runs/t-06-…` L67-75 | — |
| Q-VC-007 | 超阈 ⇒ 1 ledger 行 + 1 事件 + PM 推送 | ✅ | `conductor.py:2555-2600`（append ledger + timeline）+ `pm-orchestrator.ts:986-989`（推送）；`test_autopilot_gate_reminder.py:177` + `agent-team-loop.test.ts:2488`；`runs/t-07-…` L41 | 推送到达为活体（R21）；需运行证实；PM 侧记录：t-07 L41 |
| Q-VC-008 | 已提醒 2 次后第 3 次零产出 | ✅ | `config.py:97`（max 域 1..2）+ `conductor.py:2537`（n>max ⇒ skip）；`test…gate_reminder.py:225/241`（含 timeline 尾窗驱逐变体）；`runs/t-07-…`（rows=2 blocked_third=true） | 尾窗复活防护 in-test |
| Q-VC-009 | 门 status≠pending 后零残留 | ✅ | `test…:273`；`runs/t-07-…`（residual=0） | — |
| Q-VC-010 | 在飞行 ⇒ 不触发；仅 pending+0 在飞才触发 | ✅ | `test…:287/301/318`；`runs/t-07-…`（VC-010 两行） | — |
| Q-VC-011 | 监视面 pending 时长 + BLOCKED_ON_HUMAN 置顶 | ⚠️ | status/monitor ✅：`status-model.ts:1338/1470/1533`、`monitor.ts:442/745-753/829`；`autopilot-monitor.test.ts:489/531`；`runs/t-08-…` L72（age_shown=true blocked_marker=true） | 同 Q-AC-008：design D-009 的 **mw doctor 第三面**（`blocked_on_human` 机器字段+条件文本）未实现（`mw_common.py` grep-0）；VC 判据文本"监视面"按 D-009 应含 doctor ⇒ 降级 |
| Q-VC-012 | authorizes 闭集数组，未列出动作不得引用 | ✅ | `gates.py:180/659-676`；`status-model.ts:916-920`；`runs/t-04-…` L71、`runs/t-12-…` L103（closed_set=2 listed_only=true 两侧） | — |
| Q-VC-013 | 三条提示词逐字含同一常量 | ✅ | `conductor.py:1459+1478/2460/2491`；`runs/t-10-…` L98 | — |
| Q-VC-014 | 文本变+无批准 ⇒ done 拒 + 机器分类留痕 | ✅ | `conductor.py:2244-2268`；`runs/t-10-…` L99-100（refused=true changed_ids=1 classified=true + carrier=gate-0001） | — |
| Q-VC-015 | 仅 note 授权 ⇒ 未授权 | ✅ | `contract_guard.py:334-348`；`runs/t-10-…` L101-106（6 形态全 false） | — |
| Q-VC-016 | 历史 v1 门 + 无 freeze 工程 ⇒ parse 全成 + 渲染逐字节不变 | ✅ | `gates.py:146-152`；`mw_common.py:3017-3021/3080-3082`；`runs/t-04-…` L73、`runs/t-11-…` L98-107（zero_write / no_freeze / freeze_keys=0） | parse-all/逐字节需运行证实；PM 侧记录：t-04/t-11 [VERIFY] + `test_doctor_gates.py` 82 passed |
| Q-VC-017 | 摘掉/反转判据 ⇒ 用例转红（非空洞） | ⚠️ | in-test 反事实 ✅（`test_autopilot_l3_aborted.py:516/539/566`，[VERIFY] L77-79 含 with/without 值）；控制脚本 6 份存在；`runs/verify-g5g6-tests.md` §3（30 组） | 判据对象本身="转红"（运行结果）⇒ 需运行证实；PM 侧记录：各卡对照表（全红+还原） |
| Q-VC-018 | [VERIFY] 数值实测 + 坐标齐全 | ⚠️ | 抽验 ✅：t-06 L62-81 / t-10 L98-108 / t-14 L160-178 / t-21 §3 的 [VERIFY] 行均带具体数值且与源码/用例可对上 | 降级原因：①"来自实测"我无法复算；②PM QG 报告层存在**陈旧锚点**（AC-001 `:1649`→实际 `:1662`；AC-005 `:2475/:2577`→`:2522/:2764`；X-2） |
| Q-VC-019 | 3 配置键两侧注册 + 语料同步 | ✅ | `config.py:77-121`（20 键，亲数）；`status-model.ts:109-190/343-380`（镜像 6 处）；语料 `test/fixtures/autopilot-config-corpus.json` **73 例亲数**（含 6 新键 partial-key ×6 + range-low/high ×12）；`runs/t-14-count-locks-report.md` L163-178（corpus_sha=1e27… cases=73；P6 effective_view_20=true） | — |
| Q-VC-020 | 帧时刻逐 tick 前进 + >3 周期告警 | ✅ | `monitor.ts:74/204-208/741-743`；`autopilot-monitor.test.ts:574`；`runs/t-13-…` L49 | — |
| Q-VC-021 | 数据面变化 ≤2 周期跟随 | ✅ | `autopilot-monitor.test.ts:621`；`runs/t-13-…` L50（followed_within_cycles=2） | — |
| Q-VC-022 | 失败 ⇒ 降级帧（不丢帧不静默） | ✅ | `monitor.ts:964-977/1013-1045`；`autopilot-monitor.test.ts:656`；`runs/t-13-…` L51（degraded_frame=true silent_frames=0） | — |
| Q-VC-023 | 会话替换 ⇒ 面板重挂不消失 | ✅ | `console.ts:734-755`；`agent-team-loop.test.ts:5846`（rearmed=true panel_present=true）+ `:4644`（session_shutdown） | — |
| Q-VC-024 | 9 列样本全读入（unparsable=0）；7/8 列同 | ✅ | `worker-store.ts:109/168-183`；`worker-store.test.ts:197/92`；`test_in3_queue_replay.py:90/114`；`runs/verify-g5g6-tests.md` §1 | — |
| Q-VC-025 | 10 列行 ⇒ unparsable=1 + 回写保留 + fail-closed | ✅ | `worker-store.test.ts:369`；`test_in3_queue_replay.py:131`（三写者后原文仍在）；`worker-dispatch-guard.test.ts:223` | — |
| Q-VC-026 | 无头历史文件 upsert 后逐字节不变；新建才有 v2 头 | ✅ | `worker-store.ts:190-215`（不补头路径亲核）；`worker-store.test.ts:251/234`；`test_worker_queue_python_integrity.py`（headerless=version_one） | — |
| Q-VC-027 | unparsable>0 ⇒ 零派发 + dispatch-alarm 行 | ✅ | `pm-orchestrator.ts:543-552/452`；`worker-dispatch-guard.test.ts:223/335`；`runs/t-15-t17-t19-…` §3 控制 C | — |
| Q-VC-028 | 空+终态证据 ⇒ 零派发+告警；新项目放行 | ✅ | `pm-orchestrator.ts:651-657` + `:484`（hasProductEvidence）；`worker-dispatch-guard.test.ts:240`（双向例） | — |
| Q-VC-029 | 10 合法候选 ⇒ 新增=配额+告警 | ✅ | `pm-orchestrator.ts:679-685`；`worker-dispatch-guard.test.ts:264/278/358`；`runs/t-21-…` §3（10→3、config=1⇒1、5⇒3） | — |
| Q-VC-030 | 未传 --max-workers ⇒ 上限=launcher_max_workers | ✅ | `launcher.py:828/929`；`test_launcher.py:1172-1215`（4 例）；`runs/t-18-…` §3 | — |
| Q-VC-031 | 252 行/全非终态 ⇒ doctor 含 burst-shape；健康不含 | ✅ | `mw_common.py:3191`（判据）+ `:3538`（文本零扰动）；`test_worker_queue_python_integrity.py`（burst 用例）+ `test_in3_queue_replay.py:171`；`runs/verify-g5g6-tests.md` §1 | — |
| Q-VC-032 | done 无 supersedes ⇒ 重派被拒 | ✅ | `run-store.ts:194-227`；`worker-dispatch-guard.test.ts:297/449`；`run-store.test.ts:172` | — |
| Q-VC-033 | supersedes ⇒ 派发成功 + 旧目录不变 | ✅ | `run-store.ts:203-216`；`worker-dispatch-guard.test.ts:496`；`run-store.test.ts:203/212` | mtime 不变断言 in-test |
| Q-VC-034 | PM 派 1 任务 ⇒ 其它 key 252 行逐字节不变 | ✅ | `pm-orchestrator.ts:601`（只扫 watch+scratch）；`worker-dispatch-guard.test.ts:85`（never rewrites another key's history） | — |
| Q-VC-035 | scope:"cli" + 未认领新 key ⇒ 成功 | ✅ | `pm-orchestrator.ts:551`；`worker-dispatch-guard.test.ts:108/123`；`worker-crosskey-readonly.test.ts:132` | — |
| Q-VC-036 | foreign-live key：读可见 / 写拒 `[cross-key-read-only]` | ✅ | `ui-bridge.ts:221-247/1331-1336`；`worker-crosskey-readonly.test.ts:194/106` | — |
| Q-VC-037 | 跨 key 拒绝零副作用；gate 脚本未执行 | ✅ | `ui-bridge.ts:1698-1700`（守卫先于 runAgenticScript）；`worker-crosskey-readonly.test.ts:106/165`（writes nothing / before the gate script runs） | — |
| Q-VC-038 | 自有 claim / 未认领 key ⇒ 派发成功 | ✅ | `ui-bridge.ts:231-239`（放行集）；`worker-crosskey-readonly.test.ts:132` | — |
| Q-VC-039 | 三个 Python 写者保留 unparsable 行；无匹配不写 | ✅ | `mw_common.py:1920`（upsert_worker_row）+ `:1636`；`test_worker_queue_python_integrity.py`（4 例）+ `test_in3_queue_replay.py:131` | — |
| Q-VC-040 | 12 候选 + None ⇒ 8 spawn；config/显式各例 | ✅ | `launcher.py:828/929`；`test_launcher.py:TestLauncherMaxWorkersBound`（4 例）；`runs/t-18-…` §3 | "恰好 8 spawn"为运行断言，in-test 用 Popen 打桩 |
| Q-VC-041 | acked 收敛 0 spawn；垃圾 ack 仍 spawn | ✅ | `launcher.py:867-875`；`test_launcher.py:1217-1254`（2 例）；`runs/t-18-…` §3 | — |
| Q-VC-042 | run.json 启动字段全集 + tmp 不残留 | ✅ | `worker-mode.ts:722-734`；`run-store.ts:153-166`（tmp+rename）+ `:107`；`worker-run-identity.test.ts:77`、`run-store.test.ts:107/78/89` | — |
| Q-VC-043 | settle ⇒ done/exit=0/artifacts + marker 不夺首行 | ✅ | `worker-mode.ts:1083`；`output-writer.ts:94`；`worker-run-identity.test.ts:98/116`（D-117 首行断言亲核）；`run-store.test.ts:127/143` | — |
| Q-VC-044 | 终态拒派 + run-ledger-conflict 告警；running 拒；supersede 双向 | ✅ | `run-store.ts:194-227`；`worker-dispatch-guard.test.ts:449/475/496/530`；`run-store.test.ts:172/180/212` | — |
| Q-VC-045 | 滞后行收敛终态；活动⇒lost；[END] 不降级 | ✅ | `launcher.py:555-612`（_reconcile_orphans 判据序）；`mw_common.py:1768`（mark_run_lost 保留现场）；`test_launcher.py:TestReconcileRunState`（7 例）；`test_run_identity.py:60/83/91` | — |
| Q-VC-046 | scope=pm 跳过 key ⇒ out-of-scope 告警；cli 不产 | ✅ | `pm-orchestrator.ts:566/581`；`worker-dispatch-guard.test.ts:136/158`；`runs/t-20-run-identity-report.md`（D-036 补完记录） | — |
| Q-VC-047 | 首见 design/plan 冻结 + 幂等 + 不回溯 + 无锚放行 | ✅ | `conductor.py:2622-2746/2768`；`test_autopilot_contract_freeze.py:171/225/375`；`evidence/scripts/pm-g3-live-check.py`；`runs/t-23-g3-anchor-report.md`（§2 坐标 + §对照 A-E） | 真实仓库 0 sidecar（live-check ⑥，PM 记录） |

### 1.3 Q-COV（47 条，机械生成自 design §6 Coverage Matrix F1–F24 + §11.6 F25–F46 + §11.11 F47）

> 口径：每行问"该路径是否被实际覆盖并有证据"。机制锚点 + 命名用例（我逐一读到）+ 记录 ⇒ ✅；反向（非空洞）半边若仅靠 PM 跑控制脚本，统一归入 Q-AC-014/Q-VC-017 的 ⚠️，不逐行降级——但 F9 的**正向覆盖**本身缺一块，单列 ⚠️。

| Q-ID | 路径（design 行） | 状态 | 锚点 | 备注 |
|---|---|---|---|---|
| Q-COV-001 | F1 G1 指纹正常/尾窗切断/窗外 | ✅ | `conductor.py:1565-1606`；`test_autopilot_l3_aborted.py:194/383`（N2 窗外） | — |
| Q-COV-002 | F2 三/四类互斥 + 散文第四类 | ✅ | `test…:439/487`（prose N5 / VC-003） | 第四类按 spec §1.4 归 below |
| Q-COV-003 | F3 专用重掷 + 预算耗尽 stall | ✅ | `conductor.py:2006-2016`；`test…:244/267/613` | — |
| Q-COV-004 | F4 零漂移（无 abort ⇒ round_no==used） | ✅ | `conductor.py:1949-1950`（`round_no = used + abort_used`，静态判）+ `:5811/5859`；57 轮语料回归为 PM 记录（t-01/t-06） | — |
| Q-COV-005 | F5 提醒判定正常/第 2 次/在飞抑制 | ✅ | `conductor.py:2522-2600`；`test_autopilot_gate_reminder.py:177/210/287` | — |
| Q-COV-006 | F6 计数（ledger）/轮转不复活/不可读保守 | ✅ | `conductor.py:2508`；`test…:241`（尾窗驱逐变体） | — |
| Q-COV-007 | F7 answered 即停 | ✅ | `test…:273` | — |
| Q-COV-008 | F8 goal-change 门 halted 也提醒 | ✅ | `conductor.py:2764`（挂 tick 不挂 orchestrate，静态判）+ `:2768` 顺序；`test…:327` | — |
| Q-COV-009 | F9 G2 可见面 status/monitor/**doctor** 三面 | ⚠️ | status ✅ `status-model.ts:1338/1470`；monitor ✅ `monitor.ts:745-753/829`；**doctor ✗**——D-009 要求的 `blocked_on_human` 字段+条件文本在 `mw_common.py` 0 命中；doctor 仅有既有 `waited_s`（`:2750`）与 24h 文本阈值（`:3149`） | 与 Q-AC-008/Q-VC-011 同根；"doctor 零扰动"倒是成立（因为根本没改） |
| Q-COV-010 | F10 authorizes 闭集/空=未授权/越界拒 | ✅ | `gates.py:659-676/180`；`status-model.ts:916-920` | — |
| Q-COV-011 | F11 写侧 conductor 物化 + 人填 + worker 伪造拦 | ✅ | `conductor.py:2993`（`_gate_default_fields` authorizes "[]"）；`gate-writer.ts:152-158`（缺行拒绝）；守卫 = 既有 `xkey-gate-guard.ts`（本 key 不改，design §3） | — |
| Q-COV-012 | F12 三 prompt 逐字同一常量 | ✅ | `conductor.py:1459/1478/2460/2491` | — |
| Q-COV-013 | F13 freeze canonical sha / 时机两处 | ✅ | `contract_guard.py:121-131/86/102`；`conductor.py:2622` | — |
| Q-COV-014 | F14 done 检查/carrier 边界 | ✅ | `contract_guard.py:334-348/384`；`runs/t-10-…` L100（carrier=gate-0001 authorized=true） | — |
| Q-COV-015 | F15 零扰动（无 freeze/历史 v1） | ✅ | `gates.py:146-152`；`mw_common.py:3017-3021` | — |
| Q-COV-016 | F16 配置键双侧 + 单键/越界例 | ✅ | `config.py:77-121`；`status-model.ts:109-190`；语料 73 例（亲数） | — |
| Q-COV-017 | F17 事件词汇双侧集合相等 | ✅ | `timeline.py:67-110`（27 名，亲数）↔ `status-model.ts:1048-1082`（27 名，亲数）；parity 测试在 13 suite 集内（`runs/verify-closure.md` §3） | — |
| Q-COV-018 | F18 reason_code 12→14 + 复算一致 | ✅ | `conductor.py:5322-5337`（14 项亲数，l3-aborted `:5334` / contract-unauthorized `:5336`）、`_stall_family:5721-5725`、`_recompute:5789/5825`；`runs/t-14-…` L161-162（stall_codes=14 call_sites=14） | — |
| Q-COV-019 | F19 非空洞对照（≥2 组） | ✅（in-test 半边）/ 控制半边见 Q-VC-017 | `test_autopilot_l3_aborted.py:516/539/566` | — |
| Q-COV-020 | F20 多窗口按 gate.key 作用域 | ✅ | `pm-orchestrator.ts:964-989`；`agent-team-loop.test.ts:2552`（keyed/keyless） | — |
| Q-COV-021 | F21 帧自证/超 3 周期告警 | ✅ | `monitor.ts:74/741-743`；`autopilot-monitor.test.ts:574` | — |
| Q-COV-022 | F22 跟随 ≤2 周期 | ✅ | `autopilot-monitor.test.ts:621` | — |
| Q-COV-023 | F23 失败降级帧（含首帧失败） | ✅ | `monitor.ts:964-977/1013-1045`；`autopilot-monitor.test.ts:656` | per-site 保护改为帧级 try（t-13 披露，等价） |
| Q-COV-024 | F24 重臂（ctx 变化/session_shutdown） | ✅ | `console.ts:734-755`；`agent-team-loop.test.ts:5846/4644` | — |
| Q-COV-025 | F25 不可解析行计数 | ✅ | `worker-store.ts:168-183`；`worker-store.test.ts:211` | — |
| Q-COV-026 | F26 版本头读写 v1 兼容 | ✅ | `worker-store.ts:69-74/206`；`worker-store.test.ts:251` | — |
| Q-COV-027 | F27 upsert 槽位回插 | ✅ | `worker-store.ts:190-215`（亲核） | — |
| Q-COV-028 | F28 unparsable>0 ⇒ 零派发 | ✅ | `pm-orchestrator.ts:543-552`；`worker-dispatch-guard.test.ts:223` | — |
| Q-COV-029 | F29 空队列+终态证据 ⇒ 拒 + 新项目放行 | ✅ | `pm-orchestrator.ts:651-657`；`worker-dispatch-guard.test.ts:240` | — |
| Q-COV-030 | F30 单轮配额 | ✅ | `pm-orchestrator.ts:679-685/473`；`worker-dispatch-guard.test.ts:264/278/358` | — |
| Q-COV-031 | F31 run.json 终态优先台账 | ✅ | `launcher.py:587-612`；`test_launcher.py:TestReconcileRunState` | TS 侧 `run-store.ts:194-227` |
| Q-COV-032 | F32 supersedes 放行/旧目录拒覆写 | ✅ | `run-store.ts:203-216`；`worker-dispatch-guard.test.ts:496/530` | — |
| Q-COV-033 | F33 PM 作用域 | ✅ | `pm-orchestrator.ts:601`；`worker-dispatch-guard.test.ts:85` | — |
| Q-COV-034 | F34 cli 全局写面仍可用 | ✅ | `pm-orchestrator.ts:551`；`worker-dispatch-guard.test.ts:108/123` | — |
| Q-COV-035 | F35 launcher 默认有界 | ✅ | `launcher.py:828/929`；`test_launcher.py:1172` | — |
| Q-COV-036 | F36 doctor 形状判据 | ✅ | `mw_common.py:3191`；`test_worker_queue_python_integrity.py` | — |
| Q-COV-037 | F37 Python 三写者槽位保留 | ✅ | `mw_common.py:1920`、`autopilot/dispatch.py:628`；`test_in3_queue_replay.py:131` | — |
| Q-COV-038 | F38 行宽 7..9 区间（含 8 列） | ✅ | `worker-store.ts:32-33`；`mw_common.py`（WORKER_COLS_MIN/MAX）；`worker-store.test.ts:92/358`、`test_in3_queue_replay.py:114` | — |
| Q-COV-039 | F39 None ⇒ 配置上限 | ✅ | `launcher.py:828/929`；`test_launcher.py:1172-1215` | — |
| Q-COV-040 | F40 acked 参与 + fail-safe | ✅ | `launcher.py:867-875`；`test_launcher.py:1217-1254` | — |
| Q-COV-041 | F41 doctor 判据 + 阈值可配 | ✅ | `mw_common.py:3181/3191/3198` + `_queue_alarm_delta`；`config.py:94` | — |
| Q-COV-042 | F42 run.json 终态阻断重派 | ✅ | `run-store.ts:194-227`；`worker-dispatch-guard.test.ts:449` | — |
| Q-COV-043 | F43 supersedes 只放行已终态目标 | ✅ | `run-store.ts:203-216`；`worker-dispatch-guard.test.ts:496/530` | — |
| Q-COV-044 | F44 run.json best-effort + 不夺首行 | ✅ | `run-store.ts:115`（不抛+trace.log）；`worker-run-identity.test.ts:116/161` | — |
| Q-COV-045 | F45 被跳过 key 可见 | ✅ | `pm-orchestrator.ts:566/581`；`worker-dispatch-guard.test.ts:136` | — |
| Q-COV-046 | F46 IN-3 行格局回放（9 可读/旧 codec 全丢/10 列不丢） | ✅ | `test/fixtures/in3-queue-9col-burst.txt`（存在）+ `test_in3_queue_replay.py:67-189` + `worker-store.test.ts:326-379`；`runs/t-21-integrity-report.md` §3 | — |
| Q-COV-047 | F47 G3 锚点自动建立 | ✅ | `conductor.py:2622-2746/2768`；`test_autopilot_contract_freeze.py:171/225`；`runs/t-23-…` §对照 A-E | — |

### 1.4 Q-X（自推交叉问题，12 条）

| Q-ID | 交叉问题 | 状态 | 结论/反证锚点 |
|---|---|---|---|
| Q-X-001 | AC-008/VC-011/F9：design D-009 三面（status/monitor/doctor）中 **doctor 面是否落地**？ | ⚠️ 发现实质缺口 | `mw_common.py` 全文 grep `blocked_on_human\|BLOCKED_ON_HUMAN` = **0 命中**（本审查实测）；design.md:146/386 明确要求该面；plan §1.1 写面表把 `mw_common.py` 只分给 T-11（G3）与 T-18（G5）——**D-009 的 G2 doctor 面从未进任何卡**；t-08 回执无 "doctor"；PM QG 报告 AC-008 行只引 monitor；achieved 遗留未登记。属 design→plan 掉单，非实现失败 |
| Q-X-002 | PM QG 报告的代码坐标是否可解析？ | ⚠️ 报告缺陷（语义无损） | AC-001 行 `conductor.py:1649/状态门 :1651` → 实际 `:1662/:1665`（漂 13 行）；AC-005 行 `:2475/:2508/:2577` → 实际 `:2522/:2555/:2764`。语义（先后顺序）经我重锚后均成立。T-23 之后写入的锚点（`:2244/:2644/:2768/:2622`）均准确 |
| Q-X-003 | QG 报告 §1 基线引用是否与 `verify-baseline.md` 一致？ | ⚠️ 引用失准 | QG 报告写"基线 verify-baseline.md = 2 failed / 1431 passed"；`runs/verify-baseline.md` §2 实际记录 **2 failed / 655 passed**（34 文件子集）。1431 是 pm-state 19:30 的全量跑数。红集合同名同断言（`verify-closure.md` §4 已如实记录口径差），"新增红=0"结论仍成立，但引用对象错误 |
| Q-X-004 | AC-021 配额 × AC-020 fail-closed：spec AC-021 标题"新增>N ⇒ 拒绝该轮**全部**派发"与其反向用例①"新增=配额+告警"矛盾？ | ⚠️ spec 自相矛盾（实现取反向用例口径） | spec.md AC-021 行内两句互斥；实现 `pm-orchestrator.ts:679-685` = 配额截断（派满 N 后告警中止）；VC-029/反向用例①与 t-21 四组数字（10→3）均按截断口径验收。需 spec 措辞勘误，不需改码 |
| Q-X-005 | AC-022 配额判据 × spec §2.3"缺字段 ⇒ 视为未授权" × AC-025⑤"无锚 ⇒ 放行"：字面冲突？ | ⚠️ 已论证的有意偏离（需 spec 勘误） | spec §2.3 笼统句 vs AC-025⑤；design D-015 [REVISED @ 18:55] 论证"无锚 ≠ 缺批准记录"（否则全仓历史 key done 永久被拒，与 AC-013/P-018 冲突）。实现与 AC-025⑤ 一致（`contract_guard.py:384-391`）。spec §2.3 未同步加 carve-out |
| Q-X-006 | AC-022 "判据首先读产物终态" × Python 侧派发：`autopilot/dispatch.py` 是否读 run.json？ | ⚠️ D-038 残留 | `autopilot/dispatch.py:621-633` 只改写行格式（`upsert_worker_row`），派发判据不查 run.json；TS 路径已接（`pm-orchestrator.ts:1127`）。PM 登记 D-038，但 AC-022 PASS 行未披露此边界（在 QG §6 遗留表） |
| Q-X-007 | `dispatch_max_per_scan` 值域：plan §2.5 写 1..50，spec §2.5/config 写 1..64？ | ✅ 已闭合（文档漂移） | 实现两侧均 (1,64)（`config.py:117`、`status-model.ts:186`）；spec §2.5 与实现一致；plan §2.5 为陈旧文本。另：spec/plan 多处"默?3/默?50"存在编码残字（原"默认"） |
| Q-X-008 | QG 工作流 Step 1 前置门禁：`evidence-requirement.md` 与 `evidence/baseline/` 是否存在？ | ⚠️ 流程偏离（有替代物） | key 目录 `evidence/` 下仅 runs/research/scripts/两份事故 md + QG 报告——**无 evidence-requirement.md、无 baseline/**（本审查 ls 实测）。替代：design §7 VC 判据 + plan §2.4 + `runs/verify-baseline.md`。判据充分性标准实质存在，但与工作流字面不符，应登记偏离 |
| Q-X-009 | R18（spawn 竞态假 failed，无机器判据）对"无 open 错误"前提的影响？ | ⚠️ open 记录（已披露） | pm-state D-052 + achieved 遗留 R18 + `runs/t23-runtime-writeback-observation.md` §5。活体维度（运行时未切换 + 终态回读不可信）不满足"无 open 错误"；源码+测试级不受影响 |
| Q-X-010 | PM QG 报告 VC-024~047 行的证据通道是否逐条可锚定？ | ⚠️ 报告为模板化引用（底层有真锚） | QG 报告 §3 G5/G6 24 行全部引用同一组 6 文件 + 映射表指针，无逐 VC 锚点；且报告由 `evidence/scripts/t23-quality-gate-report.py` / `t23-patch-qg.py` 组装（scripts 目录亲见）。真实逐条锚定在 `runs/verify-g5g6-tests.md` §1（我逐行核过 47 行映射，用例名与仓库测试逐字一致）⇒ 底层链闭合，报告层引用弱 |
| Q-X-011 | achieved.md 影响面列表 × 实际改动：`advance.py` 是否被本 key 改动？ | ⚠️ 登记存疑（需 git diff 定论） | achieved.md 影响面列出 `autopilot/{…,advance}.py`；`advance.py` 全文 grep 本 key 标记（authorizes/contract/l3abort/remind/gate-reminder/六个配置键）= **0 命中**，文件仍是 spawn 包装器原形。我不能跑 git diff ⇒ 无法终判；至少属"登记面与可查证据不符" |
| Q-X-012 | 卡片绑定完整性：T-05 列 AC-015 但无 G4 VC；T-18/T-19/T-20 卡头 VC 少于 plan §3？ | ✅ 已闭合（登记噪音） | T-05 卡/plan 表列 AC-015 而无 VC-020（归 T-13）——松绑；T-18 卡头仅 VC-030/031（plan 列 VC-039-041）、T-19 卡头仅 VC-034/035（plan 列 VC-046）、T-20 卡头仅 VC-032/033（plan 列 VC-042-045）——卡头少报、由 T-21（"VC-024~046 汇总核销"）+映射表兜住。无空绑定卡 |

## 2. 汇总

| 分组 | 总数 | ✅ 充分 | ⚠️ 不足 | ❌ 无证据 | ✅ 占比 |
|---|---|---|---|---|---|
| Q-AC（spec 25 AC） | 25 | 22 | 3（AC-008 / AC-014 / AC-022） | 0 | 88% |
| Q-VC（design 47 VC） | 47 | 44 | 3（VC-011 / VC-017 / VC-018） | 0 | 94% |
| Q-COV（Coverage F1–F47） | 47 | 46 | 1（F9：doctor 面） | 0 | 98% |
| Q-X（自推交叉问题） | 12 | 2 | 10 | 0 | 17% |
| **合计** | **131** | **114** | **17** | **0** | **87.0%** |

- ❌ = 0：**没有任何问题找不到证据**——本 key 的证据链在"源码 + 测试 + evidence/runs 记录"三层上密度很高（26 份 run 报告、6 份控制脚本、47 行 VC→用例映射表、12+13 例新测试文件全部实存，我逐一抽验）。
- 17 条 ⚠️ 的构成（去重后的根因，共 7 类）：
  1. **AC-008 / VC-011 / F9（3 条，同一根因）**：design D-009 的 `mw doctor` G2 可见面（`blocked_on_human` + 条件文本）**未实现、未派卡、未登记**——实质覆盖缺口，全报告唯一功能性缺口。
  2. **AC-014 / VC-017（2 条）**：非空洞对照的"控制脚本转红"只能由运行证实（我无 bash）；in-test 反事实（X1-X3）已静态核到。
  3. **VC-018（1 条）**："[VERIFY] 数值来自实测"不可复算 + PM QG 报告自身锚点漂移（X-2）。
  4. **AC-022（1 条）**：D-038——Python 侧 `autopilot/dispatch.py` 派发判据不读 run.json（AC 字面未限定路径）。
  5. **报告/文档质量（X-2/X-3/X-10，3 条）**：QG 报告 conductor 锚点陈旧、基线数字误引（655 vs 1431）、G5/G6 VC 行模板化引用。
  6. **spec/plan 一致性（X-4/X-5/X-7/X-8，4 条）**：AC-021 配额措辞自相矛盾、§2.3 与 AC-025⑤ 字面冲突、plan §2.5 值域漂移、QG 工作流前置物（evidence-requirement.md / baseline/）缺失。
  7. **运行时/open 项（X-9 + 各 ✅ 行备注，3 条计 X-9/X-11 一类）**：R21 未切换（全局欠债，PM 已声明"源码+测试级"）、R18 open、advance.py 登记存疑。

## 3. 质检结论

**⚠️ 有条件通过（欠债 17 项，其中 1 项为实质功能覆盖缺口）**

- 对照 QG 门禁标准：无 ❌ 满足；⚠️ = 17 > 3（Stage 口径）且非零（合入口径）⇒ 不能判"✅ 通过"。
- 但 17 项中仅 **AC-008/VC-011/F9（doctor 面）是功能缺口**，其余为：我方无 bash 的运行复证欠债（2）、报告与文档质量（6）、已登记残留的边界披露不足（D-038、R18、R21）、spec 措辞勘误（3）。
- 与 PM 自评（"AC 25/25、VC 47/47 PASS（源码+测试级）；新增红 0；唯一交付缺口 R21"）相比：**"源码+测试级"的判定我基本认同**——我独立重锚后未发现任何"声称实现而源码不存在"的项；**差异集中在**：①AC-008 的 doctor 半边未交付也未披露（PM 判 PASS 过宽）；②若干 PASS 行的边界（D-038/R18/控制脚本层）未在行内标注；③报告自身的坐标与引用质量。
- 结论：**准予维持 done 状态的"源码+测试级"结论，但合入/上线前须清偿 §4 行动项 1（或正式 descope）与 2~4（报告/文档修正）；R21 运行时切换维持既有用户审批流。**

## 4. 未通过 / 证据不足问题行动计划

| # | 问题 | 根因 | 所需动作 | 建议负责 |
|---|---|---|---|---|
| 1 | Q-AC-008 / Q-VC-011 / Q-COV-009：`mw doctor` 无 `blocked_on_human` 机器字段 + 条件 `BLOCKED_ON_HUMAN` 文本 | design D-009 第三面在 plan 写面分配时掉单（`mw_common.py` 被分给 T-11/T-18，无卡承接 G2 doctor 面） | 二选一：① 新开小卡按 D-009 落地（`_doctor_gates` 加三轴字段 + `_gates_text_alerted` 触发 + `format_doctor_text` 条件后缀 + I7 零扰动用例）；② 或走 AC 修订把 AC-008 的监视面收窄为"面板 + /autopilot status"并记录 D-009 doctor 面为显式 descope | PM（新卡或 AC 勘误） |
| 2 | Q-X-002 / Q-VC-018：PM QG 报告 conductor.py 锚点陈旧（`:1649/:2475/:2577` 均不可解析） | 报告由 t23 脚本组装时复用了 pm-state 早期条目的行号，未对最终工作区重锚 | 对 `quality-gate-report-20261010.md` 附一节"重锚勘误表"（本报告 §1.1 已给出正确坐标），或直接改正文 | PM |
| 3 | Q-X-003：QG 报告 §1 基线引用（"1431 passed"）与 `verify-baseline.md`（655 passed）不符 | 把 T-21 期全量跑数误标为基线 | 修正 §1 行为"基线=2 failed/655 passed（34 文件）；全量终跑=2 failed/1523 passed；红集合同名（verify-closure §4）" | PM |
| 4 | Q-X-004 / X-5 / X-7：spec AC-021 标题与反向用例矛盾；spec §2.3 笼统句 vs AC-025⑤；plan §2.5 值域 1..50 | 措辞未随 [REVISED] 同步 | 三处文档勘误（不改码）：AC-021 标题改"超过配额即截断并告警"；§2.3 加"（契约身份锚缺失除外，见 AC-025⑤）"；plan §2.5 改 1..64 | PM |
| 5 | Q-AC-022 / Q-X-006：`autopilot/dispatch.py` 派发不读 run.json（D-038） | 范围裁剪（TS 侧为 IN-3 真实来源），AC 字面未限定 | 新小卡给 Python 派发判据接 `read_run_status`（同 D-029 优先级）；或 AC-022 行内披露边界 | 新卡 / PM |
| 6 | Q-X-008：`evidence-requirement.md` / `evidence/baseline/` 缺失 | key 用 design §7 + verify-baseline.md 替代 | 在 key 目录补一页 `evidence-requirement.md`（逐 AC/VC 指到 design §7 行 + plan §2.4）或在 pm-state 登记"工作流前置物替代"偏离 | PM |
| 7 | Q-X-011：achieved.md 影响面列 `advance.py` 但内容无本 key 改动痕迹 | 登记面与实际改动不符 | `git diff 776b82d7f.. -- autopilot/advance.py` 定论后修正 achieved.md（我无 bash 无法终判） | PM |
| 8 | Q-AC-014 / Q-VC-017 / Q-VC-018：控制脚本转红与 [VERIFY] 实测数值需独立复跑 | 本审查工具边界（无 bash）；非 key 缺陷 | 下次有 bash 的会话复跑 6 份 `*-controls.ps1` + 全量 pytest/vitest（命令见 QG 报告 §7）核对"全红 + restored" | 任意 worker / PM |
| 9 | R21 / R18（既有登记，非新增） | 运行时未切换 / spawn 竞态无判据 | 维持既有去向：runbook 待用户批准；R18 待用户决定是否单开卡 | 用户 / PM |
| 10 | Q-X-010：QG 报告 G5/G6 VC 行模板化引用 | 报告由脚本组装 | 报告修订时逐行替换为 `verify-g5g6-tests.md` §1 的具体用例名（映射已存在，仅引用层工作） | PM |

## 5. 二次印证结论（QG Step 4 四项检查）

**检查 ①：spec 每条约束是否被问题覆盖？——覆盖，1 处约束实例未落地**
- 性能（提醒在既有 4s tick 内、不新增轮询进程、帧内零新增 IO）：由 Q-AC-005/007/015/017 承载；代码静态核到（`_remind_pending_gates` 挂 `tick:2764`；`monitor.ts` 帧字段全内存、无新写路径，`autopilot-monitor.test.ts:417` "three ticks … byte-identical" 用例仍在）。
- 安全（fail-closed：授权/anchor/队列）：Q-AC-011/012/020/024 承载 ✓。
- 平台（Windows、常驻 serve 需重启生效）：R21 显式承载 ✓。
- 零回填（P-018）：Q-AC-013/022/025 承载 ✓（`run-store.ts:166` "zero backfill" 用例、`contract_freeze` 不回溯用例均实存）。
- 只读面不建文件：Q-AC-023（doctor 无状态判据）承载 ✓（`mw_common.py:3017-3021` 结构保证）。
- **例外**：spec §1.3 场景 2"早上 `mw doctor` / 面板第一眼能看到哪个门挂了多久"中 doctor 的 30min 级可见性——约束实例未落地（Q-X-001）；其余两个面（面板/status）已覆盖。

**检查 ②：design Function Flow 每个节点是否有对应问题？——是，1 个节点无实现**
- G1 流（`_verify_loop` → `_l3_round_verdict` → aborted 分支 → 重掷/stall）：Q-AC-001~004 ✓。
- G2 流（`tick` → `_remind_pending_gates` → ledger/timeline → extension 消费者 → `deliverPmAlert`）：Q-AC-005~007 ✓；**"mw doctor 可见面"节点**（D-009）无对应实现（Q-X-001）。
- G3 流（`evaluate` → `_done_transaction` → CLI 钩子 → 锚点建立）：Q-AC-011/025 ✓（`mw.py:3564-3567` 两子命令都在）。
- §11.5 派发数据流（readQueue → unparsable abort → 候选 → run 终态 → 配额 → upsert）：Q-AC-019~022 ✓，与 `pm-orchestrator.ts:543-704` 实际顺序逐一比对一致（含 `runVerdict` 在 docs-gate 之前）。
- 异常出口段（gate 解析失败跳过、越界 authorizes 拒、freeze 缺失放行、ledger 不可读保守、timeline 轮转不影响计数）：Q-AC-009/013/025 + `conductor.py:2508`（ledger 读失败=0 计数，代码注释明示保守方向）✓。

**检查 ③：Coverage Matrix 每条异常路径是否有 Q-COV？——是，F1–F47 共 47 行全部生成（§1.3），无遗漏行。**

**检查 ④：是否有卡的 vc_refs 为空但有对应 VC？——无空绑定卡；3 张卡卡头少报（T-18 少 VC-039~041、T-19 少 VC-046、T-20 少 VC-042~045，均由 plan §3 任务表 + T-21 汇总卡 + 映射表兜住）；T-05 反向情形（列了 AC-015 却无对应 VC-020）属松绑噪音。** 另发现 design §0 `ac_count: 24` 与 §8 映射表止于 AC-018 未随 AC-019~025 追加更新（G5/G6 映射在 §11.8、AC-025 在 §11.11，覆盖完整但 §0/§8 头部计数陈旧）。

## 6. 附加一致性核查

### 6.1 逐卡 ac_refs / vc_refs

23 张卡全部有非空 AC/VC 绑定（tasks/T-*.md 头部逐张 grep 核对）。不符/松绑清单：
- T-05：列 AC-015 无对应 VC（VC-020 属 T-13）。
- T-18 卡头 VC-030/031 < plan §3 的 VC-030/031/039/040/041；T-19 卡头 VC-034/035 < plan 的 +VC-046；T-20 卡头 VC-032/033 < plan 的 +VC-042~045。卡体实施记录与回执实际覆盖了少报部分（t-18 报告 §1 变更清单含三写者/acked/doctor；t-20 报告含 out-of-scope 补完）。
- T-16（docs 收口）"AC: 全部 / VC: 全部"——宽绑定，属收口卡惯例，可接受。
- 其余 18 张卡绑定与交付物一致（如 T-06 的 X1-X3 对照、T-22 的 4 用例）。

### 6.2 achieved.md「系统行为变化」7 节 + 影响面 vs 实际文件集合

- 7 节逐节对源码核过：①观测面（G4+G2 面板）✓；②闸门提醒 ✓；③L3 中止 ✓；④AC/VC 授权（G3+AC-025）✓；⑤队列完整性（G5）✓；⑥隔离+身份（G6）✓；⑦配置/事件（14→20 键、23→27 事件、12→14 reason code——三项我亲数，全部属实）。
- **"声称改了但找不到对应代码"：1 项**——`advance.py`（X-011：grep 本 key 全部标记 0 命中，文件仍是原 spawn 包装器；需 `git diff` 终判）。
- **"改了但未登记"：0 项**（所有在卡/回执声称的模块我都找到了对应符号与行为；两份 CHANGELOG 的 22 条英文条目 + README 6 键表/两子命令段均实存且内容与实现一致——`packages/multi-workers/CHANGELOG.md:68-78/133-136`、`packages/coding-agent/CHANGELOG.md:58-63/75/236-238`、`README.md:229-246`）。
- 反向：**design 登记了但没改**：`mw_common.py` 的 G2 `blocked_on_human`（design §3 模块表）——即 X-001，属"计划面登记、实现面缺失"，achieved 未把它列为遗留。

### 6.3 `evidence/runs/*.md` 与 `tasks/T-*.md` 的 [VERIFY] 对账

对得上的（抽样全过）：
- T-18 卡 [VERIFY]（13/7/386/1407/68 passed）≡ `t-18-queue-integrity-report.md` §3 同数值。
- T-06 卡（20 例 + 2 计数锁红）≡ `t-06-l3-tests-report.md` §3（20 passed；红=计数锁）≡ t-01 报告（X1-X3 绿 + 2 锁红）。
- T-10 卡（2 failed/115 passed、16 新测试）≡ `t-10-g3-done-guard-report.md` 头部与 §2；QG 报告 AC-001 行"PM 复跑 5 文件 2 failed/115+"与 t-10 一致。
- T-12（40/190/43）≡ t-12 报告 §2；T-13（26/38 passed + 两组对照）≡ t-13 报告；T-14（Python 47 + TS 47、语料 73）≡ t-14 报告 §4；T-22（4 passed/368）≡ t-22 报告 §3；T-23（12 + 121 + live-check 6 项）≡ t-23 报告与 pm-state D-057。
- QG 报告 §1 收口数字（2 failed/1523 passed/10 deselected；13 files/340 tests；check exit 0）≡ `verify-closure.md` §2/§3 逐字一致。

对不上的（3 处，均已在 §1/§4 计入）：
1. QG 报告 §1"基线 verify-baseline.md = 2 failed / **1431** passed" ↔ `verify-baseline.md` 实录"2 failed / **655** passed"（X-3）。
2. pm-state D-028 与过程日志（17:30）"T-18 后全量 **1406** passed" ↔ T-18 卡 + t-18 回执"**1407** passed"（±1，疑转写）。
3. t-05 报告"event-parity equal=true count=**26**"（T-05 时点，3 新事件）↔ 终态 27（`contract-frozen` 由 T-23/T-14 补）——时序性差异非错误，但 QG 报告未给出终态 parity 数值的直接 [VERIFY] 行（t-14 L206 有 `VC-012: equal=true count=27`，可引）。

## 7. 与 PM 报告质量门报告的差异

> 措辞级差异不列；以下均为判定或事实差异，附我的反证锚点。

| # | PM 报告判定 | 本报告判定 | 反证锚点 |
|---|---|---|---|
| 1 | AC-008 **PASS**（行内仅引 monitor.ts 锚点） | **⚠️**：`mw doctor` 半边未交付且未披露 | `mw_common.py` grep `blocked_on_human\|BLOCKED_ON_HUMAN` = 0 命中；design.md:146（D-009 第三面）、:386（模块表）；t-08 回执全文无 "doctor"；spec AC-008 明文"monitor 面板**与 mw doctor**" |
| 2 | AC-014 **PASS**（"全部实测转红并逐字节还原"） | **⚠️**：控制脚本转红层需运行证实（我不可复跑）；in-test 反事实层 ✅ | 本审查无 bash；PM 侧记录=各卡回执对照段 + verify-g5g6-tests §3。另 X-2 锚点漂移直接削弱 AC-014 的"坐标齐全"半边 |
| 3 | AC-022 **PASS** | **⚠️**：`autopilot/dispatch.py` 派发判据不读 run.json（D-038 在 §6 遗留表但 AC 行未披露边界）；AC 文面"派发/重派判据首先读该产物终态"未限定 TS | `autopilot/dispatch.py:621-633`（仅写行，无 run.json 查询）；pm-state D-038 自认 |
| 4 | VC-011 / VC-017 / VC-018 **PASS** | 各 **⚠️**（VC-011 同 #1；VC-017/VC-018 同 #2 + 锚点漂移） | 见 §1.2 对应行 |
| 5 | §1"基线 verify-baseline.md = 2 failed / 1431 passed" | **引用失准**：基线文件实录 655 passed（34 文件子集）；1431 是 T-21 期全量数 | `runs/verify-baseline.md` §2 原文；`runs/verify-closure.md` §4 口径差记录 |
| 6 | AC-001 行锚点 `conductor.py:1649`（状态门 `:1651`） | 锚点**漂移**：实际 `:1662`（状态门 `:1665`）；语义成立 | 本审查 grep+read 实测（T-06/T-07 之后 conductor 后续插入所致） |
| 7 | AC-005 行锚点 `:2475/:2508/:2577` | 锚点**漂移**：实际 `:2522/:2508→_reminder_count/:2764` | 同上；`:2508` 现为 `_reminder_count` 定义行，与报告标注的 `_remind_pending_gates` 不符 |
| 8 | §3 VC-024~047 逐 PASS（证据通道列） | 底层链闭合（映射表+用例实存），但报告行为**模板化引用**（24 行同一组 6 文件），非逐条锚定；且报告由脚本组装 | QG 报告 §3 原文形态；`evidence/scripts/t23-quality-gate-report.py`、`t23-patch-qg.py` 实存 |
| 9 | 结论"AC 25/25、VC 47/47 PASS" | **22/25 ✅、44/47 ✅、17 ⚠️、0 ❌ ⇒ 有条件通过** | 全报告 §1/§2 |

**认同部分（避免只列差异造成误读）**：PM 报告的"源码+测试级"自限口径、R21 诚实声明、§5 未验证清单、D-038/R18/R19/R20 遗留登记、收口数字与 verify-closure 的一致性、以及全部 25 AC 的**实现存在性**——我逐一重锚后无一证伪。核心分歧只有一处功能性（AC-008 doctor 半边），其余为证据质量与披露粒度。

---

[VERIFY] QG-A: questions=131 sufficient=114 insufficient=17 missing=0 conclusion=conditional


## 收尾摘要（供 PM 收录时快速读取）

- 结论：**⚠️ 有条件通过**（欠债 17 项；131 问 = 114 ✅ / 17 ⚠️ / 0 ❌）
- 最严重 3 个问题：
  1. **AC-008/VC-011/Q-COV-009：`mw doctor` G2 可见面未实现**——design D-009 第三面（`mw_common._doctor_gates` 加 `blocked_on_human` + 条件 `BLOCKED_ON_HUMAN` 文本）在 `packages/multi-workers/mw_common.py` grep 0 命中；plan 写面分配时掉单（mw_common.py 只分给 T-11/T-18）；PM QG 报告 AC-008 行仅引 monitor 锚点即判 PASS。
  2. **PM QG 报告证据质量**：conductor.py 锚点陈旧（AC-001 行 `:1649/:1651` → 实际 `:1662/:1665`；AC-005 行 `:2475/:2577` → `:2522/:2764`）；§1 基线误引（`verify-baseline.md` 实录 2 failed/**655** passed，报告写 **1431**）。
  3. **AC-022 边界披露不足**：`autopilot/dispatch.py:621-633`（Python 派发）未接 run.json 终态判据（D-038 残留，QG §6 有登记但 AC 行未披露）⇒"派发判据首先读产物终态"仅在 TS 路径 + launcher 收敛成立。
- 报告路径：`.agenticdoc/mw-gate-verdict-hardening/workers/mwg-qg2a-evidence-chain/report.md`
