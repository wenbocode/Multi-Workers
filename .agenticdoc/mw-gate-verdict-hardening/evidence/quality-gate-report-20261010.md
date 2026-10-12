# quality-gate-report — mw-gate-verdict-hardening（2026-10-10）

- key: `mw-gate-verdict-hardening` · phase: **verify** · 代码基线 `776b82d7f`（+ 本 key 未提交工作区改动）
- 范围：G1 L3 流中止 / G2 闸门静默 / G3 授权范围与契约闸门 / G4 面板冻结 / G5 队列完整性 / G6 派发隔离与运行身份 + **AC-025 G3 锚点建立**
- 规模：**25 AC / 47 VC**；实现卡 T-01…T-23（T-08b 为假 `failed` 引发的重复派发，人工终止）
- 本报告由 PM 在 verify 阶段独立撰写；所有数字来自 **PM 本人复跑**或各卡回执中带 `文件:行号` 的实测，PM 未复用 worker 的总结作为证据。

## 1. 收口验证（PM 独立复跑）

| 命令 | 结果 | 与基线对照 |
|---|---|---|
| `cd packages/multi-workers && python -X utf8 -m pytest -q -p no:randomly` | **2 failed / 1523 passed / 10 deselected** | 基线 `verify-baseline.md` **实录 2 failed / 655 passed / 8 deselected**（该文件是早期子集跑，早于本 key 新增/扩展测试落地；全量终跑 = 2 failed / 1523 passed，与 `verify-closure.md` §2 同数）；两条红**同名同集合**：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` ⇒ **新增红 = 0** |
| `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run <13 suites>` | **13 files / 340 tests passed** | 无基线红 |
| `npm run check`（仓根） | **exit 0**，biome `Checked 1110 files … No fixes applied` | tsgo/pinned-deps/ts-imports/shrinkwrap/install-lock/browser-smoke 全过 |
| `evidence/scripts/pm-g3-live-check.py`（PM 自写端到端） | 6 项全绿（见 AC-025 行） | — |
| `./test.sh` | **本机不可运行**（`bash.exe` → WSL 且无已安装发行版，`wsl -l -v` rc=0xFFFFFFFF） | 以 Python 全量 + 13 TS suite 为等价非 e2e 口径（AGENTS.md） |

## 2. AC 矩阵（**post-复审**：22 PASS + 3 ⚠️ PARTIAL（AC-007/AC-008/AC-024）；另 AC-014/AC-022 标 PASS 但附边界 —— 更正见 §8、§9）

| AC | 组 | 结论 | 实现落点（`文件:行号`／符号）| 判据与证据 |
|---|---|---|---|---|
| **AC-001** | G1 | **PASS** | T-01 `conductor.py:1662`（`_l3_stream_aborted` 指纹分支）在状态门 `:1664` **之前**（复审重锚；原文 `:1649/:1651` 系 T-10/T-23 插入后漂移）；T-06 20 例（含逐字 marker 夹具） | PM 复跑 5 文件 2 failed/115+（红=T-14 计数锁，已消） |
| **AC-002** | G1 | **PASS** | T-01 `_l3_round_verdict` 三分支 + T-06 三类无有效裁决夹具 | `test_autopilot_l3_aborted.py` 断言走生产函数/`tick` |
| **AC-003** | G1 | **PASS** | T-01 `loop="l3abort:<key>"` 独立预算 + `l3_abort_retry_limit`（`config.py`，0..10，默认 1） | T-02 范围校验 + T-14 语料 73 例 |
| **AC-004** | G1 | **PASS** | 反向：无 `stream closed` 行 / `output.md` 合格 ⇒ 不判 aborted（T-06 N 组对照 X1 转红） | T-06 `[VERIFY]`② 红集合与基线一致 |
| **AC-005** | G2 | **PASS** | T-07 `conductor.py:2522` `pending_gate_reminders` 纯判定 + `:2555` `_remind_pending_gates`，`tick` 第 2b 步调用 `:2764`（复审重锚；原文 `:2475/:2508/:2577` 漂移） | 新 suite `test_autopilot_gate_reminder.py` 12 passed |
| **AC-006** | G2 | **PASS** | T-07 提醒计数入 ledger（`phase:"remind"`），已答 gate 不再提醒；T-09 读取端 `seq` 水位去重 | T-21 回放 + T-09 接缝核验（行键集一致） |
| **AC-007** | G2 | **⚠️ PARTIAL** | T-07 只对 `status==pending` 生效（**已答 gate 与“无 gate”**不产事件）；**“已终态 stage 的 gate”未实现**：`gates.pending_gates`（`gates.py:770-772`）只按 `status=="pending"` 过滤整个 gates 目录、`_remind_pending_gates`（`conductor.py:2564`）不做 stage 范围过滤、`pending_gate_reminders` 三条件（`conductor.py:2541-2551`）无 stage 终态判据 | 复审反证 QG-B #14①（PM 已独立复现）；`test_autopilot_gate_reminder.py` 3 组对照只覆盖已答/无门/在飞行 |
| **AC-008** | G2 | **⚠️ PARTIAL** | **面板半边已交付**：T-08 `monitor.ts` snapshot 级 `blockedOnHuman`（`:184`，采集 `:364-369`）+ 置顶 `BLOCKED_ON_HUMAN` 行（`:745-753`，受 `!tickStale` 门控）；**`mw doctor` 半边未交付**：design D-009 第三面（`design.md:147`/`:386`/`:432`）要求在 `mw_common.py` 的 `_doctor_gates` 加 `blocked_on_human` 字段 + `_gates_text_alerted` 触发 + `format_doctor_text` 条件后缀，实测 `mw_common.py` grep `blocked_on_human|BLOCKED_ON_HUMAN` = **0 命中**，且无卡承接 | PM 复跑 73 passed（面板侧）；doctor 侧反证 QG-A #1（PM 已 grep 复现） |
| **AC-009** | G3 | **PASS** | T-04 `authorizes` 进 `_JSON_LIST_FIELDS`（`gates.py:171`）+ 闭集 `AUTHORIZES_ACTIONS`（`:180`）；T-12 `gate-writer.ts` 唯一闭集声明 + `--authorizes` 参数面 | 跨语言闭集 parity 用例（`VC-012: closed_set=2 listed_only=true`） |
| **AC-010** | G3 | **PASS** | T-10 `_CONTRACT_CONSTRAINT`（`conductor.py:1459`）逐字拼进三处 prompt（`:1478-1479`/`:2459-2460`/`:2490-2491`） | T-10 控制组（删一处 prompt 常量 ⇒ VC-013 红） |
| **AC-011** | G3 | **PASS** | T-10 `_done_transaction` 的 `:2244` **第一个 check-before-write** 调 `contract_guard.evaluate`；不过 ⇒ `contract-refused` + `mark_stalled(contract-unauthorized)` + `return "gated"` | T-10 控制组 + T-23 PM 端到端（`evaluate().ok=False`, `changed_ids=('AC-001',)`） |
| **AC-012** | G3 | **PASS** | 反向：自由文本 `note` 不作授权——判定只认 `authorizes` 字段 + freeze；T-10 不读 `gate.note`/`answered_by` | T-10 VC-015 对照（pending/rejected/散文）转红 |
| **AC-013** | G3 | **PASS** | T-04 不改 `_REQUIRED_FIELDS`（仍 6）、不新增 v3；T-11 doctor 段只在有 sidecar 的 key 出现；历史 gate 全量 parse 成功 | PM 实测：真实仓库 `gates` 无 `contract_guard` 键、全仓 0 sidecar、`test_doctor_gates.py` 82 passed |
| **AC-014** | 全部 | **PASS（边界）** | 每条机器判据附非空洞对照（见 §4 索引：7 个 `*-controls.ps1` 脚本 + 各卡 CF 组）。**边界**：① 对照“实际跑红并逐字节还原”这一层只有各卡回执记录，本次两个独立复审均无 bash 不能复跑（运行层欠债）；② 独立复审静态核查 27 组变异点**全部落在判据行**（无空洞对照）；③ 本报告 §4 曾据不实转述标注 T-20“控制 B 不承重”——已撤回（§8） | 本报告 §4/§8；`verify-g5g6-tests.md` §3；各卡 `*-controls.ps1` |
| **AC-015** | G4 | **PASS** | T-13 `MonitorSnapshot.collectedAtMs`/`tickCount` + 首行 `STALE PANEL (...)`（`PANEL_STALE_MISSED_CYCLES=3`） | PM 复跑 `VC-020: stamp_advances=true stale_warned=true` |
| **AC-016** | G4 | **PASS** | T-13 跟随 ≤2 周期（`MONITOR_INTERVAL_MS=4000` 未改） | `VC-021: followed_within_cycles=2` |
| **AC-017** | G4 | **PASS** | T-13 裸 catch 改为**产出降级帧**（上一帧 + `lastErrorAtMs` + 摘要），首 tick 即失败边界已注释+用例 | `VC-022: degraded_frame=true silent_frames=0` |
| **AC-018** | G4 | **PASS** | T-12 `autoStartMonitor` ctx 变化 ⇒ 先 `stopMonitor` 再 start；`stopMonitor` 语义未动 | PM 复跑 `VC-023: rearmed=true panel_present=true` |
| **AC-019** | G6 | **PASS** | T-19 `dispatchNewTasks(..., { scope:"pm", watchedKey })` 收窄 + `out-of-scope` 聚合告警（D-031） | T-21 VC-034/035 + T-20 VC-046；PM 复跑 340 passed |
| **AC-020** | G5 | **PASS** | T-17 严格有序判据：`unparsable>0` ⇒ 零派发 + 告警；空队列 + 终态证据 ⇒ 零派发；无证据 ⇒ 放行 | T-21 VC-027/028（含双向用例） |
| **AC-021** | G5 | **PASS** | T-17 `dispatch_max_per_scan`（默认 3）+ T-18 `launcher_max_workers`（默认 8）+ `_workers.acked` 参与 | T-21 VC-029/030、T-18 VC-040/041；PM 实测 live `rows_total/non_terminal` 计数一致 |
| **AC-022** | G6 | **PASS（边界）** | T-20 `run-store.ts` + `worker-mode.ts` 自写 `run.json`（running/终态/心跳）+ launcher 只补 `lost`；派发判据：自己终态/active ⇒ 拒、`supersedes` 指向未知/未终态 ⇒ 拒、指向已终态 ⇒ 放行（`run-store.ts:176-205`）。**边界（D-038）**：Python 侧 `autopilot/dispatch.py:621-633` 派发判据**不读** `run.json`（AC 字面“派发/重派判据首先读产物终态”未限定路径） | T-20 report（15+6+9+7 例）；PM 复跑 340 passed；反证 QG-A #3（PM 已 grep 复现 0 命中） |
| **AC-023** | G5 | **PASS** | T-15 读侧 `{rows, unparsable[], version}` + 回写槽位保留 + `# mw-queue:v2`；T-18 Python 三个写者槽位保留 + doctor 三判据 | T-21 回放（250 行 9 列夹具，sha `6c4f4dfc…`）+ T-18/−controls A–F |
| **AC-024** | G6 | **⚠️ PARTIAL** | T-22 `ui-bridge.ts` `foreignLiveClaimRefusal` + `dispatch_worker`（显式 key）/`advance_phase` 先拒后动，返回 `[cross-key-read-only]`；读面零改动 —— **AC 字面点名的两个工具成立**；但 `/worker` handler（`ui-bridge.ts:1710`，注册于 `pm-orchestrator.ts:1059`）经 `resolveOwnerKeyWithSync`（`:66-67`）直通后未调用守卫（全仓仅 `:1333`/`:1698` 两处调用），仍可对他人 live key 写 `task.md` + 队列行（`:1813-1819`），而拒绝文案 `:241-242` 自称 `/worker` 已拒 ⇒ 文案与实现不符 | `t22-controls.ps1` 4 组全红 + 还原；`worker-crosskey-readonly.test.ts` 4 例；复审反证 QG-B #2（PM 已独立复现） |
| **AC-025** | G3 | **PASS** | T-23 `conductor.py::_freeze_contract_first_sight`（`:2644`，调用点 tick step 2c `:2768`）+ `mw autopilot contract-freeze`（`mw.py:3977`）+ `timeline.py:110` 事件 | PM 独立端到端 `evidence/scripts/pm-g3-live-check.py`：自动锚/幂等字节不变/`evaluate.ok=False`/CLI `refused` + 真实仓库 0 sidecar |

## 3. VC 矩阵（复审后：VC 按其字面 47/47 成立；VC-011/017/018 因下述欠债标 ⚠️ —— 见 §9）

> VC 的完整判据文本在 `design.md` §6 / §11.7 / §11.11；本表的**证据通道**列是分组引用（非逐条锚点），逐条 VC→用例锚点在 `evidence/runs/verify-g5g6-tests.md` §1（47 行映射，含用例名）。**复审指出：本表 24 行同组引用属模板化，使用时请以映射表为准**（QG-A §7 #8）。

| VC | 判据摘要 | 组 | 证据通道 |
|---|---|---|---|
| VC-001 | 当一轮 L3 含 marker 且无合格源时，判 aborted 并发 l3-aborted 事件（非 no-verdict） | G1 (L3 流中止) | T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例） |
| VC-002 | 当 aborted 轮发事件时，data 键集逐字等于固定八元组 | G1 (L3 流中止) | T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例） |
| VC-003 | 当同一输入分别造 A/B/C 三类时，三者两两不同且各只命中一类 | G1 (L3 流中止) | T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例） |
| VC-004 | 当 aborted 且专用计数未耗尽时，派 l3abort 轮且 used_rounds 派生独立计数 | G1 (L3 流中止) | T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例） |
| VC-005 | 当 round_budget 已耗尽但发生 abort 时，仍重掷（abort 不消耗共享预算） | G1 (L3 流中止) | T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例） |
| VC-006 | 当 worker.log 无 marker 或 output.md 两节齐备时，aborted 假阳性 = 0 | G1 (L3 流中止) | T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例） |
| VC-007 | 当 pending 门超阈且无在飞行时，产生 1 条 ledger 行 + 1 条 gate-reminder，且 PM 侧收到推送 | G2 (闸门静默/提醒) | T-07 / T-08 / T-09 → `t-07-gate-reminder-report.md`、`t-08-g2-surfaces`（73 passed，我复跑）、`t-09-pm-consumer-report.md` |
| VC-008 | 当同一门已提醒 2 次时，第 3 次不产生任何行/事件/推送 | G2 (闸门静默/提醒) | T-07 / T-08 / T-09 → `t-07-gate-reminder-report.md`、`t-08-g2-surfaces`（73 passed，我复跑）、`t-09-pm-consumer-report.md` |
| VC-009 | 当门 status ≠ pending 后，该门不再产生提醒（零残留） | G2 (闸门静默/提醒) | T-07 / T-08 / T-09 → `t-07-gate-reminder-report.md`、`t-08-g2-surfaces`（73 passed，我复跑）、`t-09-pm-consumer-report.md` |
| VC-010 | 当 EXECUTE 期有在飞行（事件稀疏）时，不触发提醒；仅 pending 门 + 0 在飞才触发 | G2 (闸门静默/提醒) | T-07 / T-08 / T-09 → `t-07-gate-reminder-report.md`、`t-08-g2-surfaces`（73 passed，我复跑）、`t-09-pm-consumer-report.md` |
| VC-011 | 当渲染监视面时，pending 门含 pending 时长且真等人时有 BLOCKED_ON_HUMAN 置顶 | G2 (闸门静默/提醒) | T-07 / T-08 / T-09 → `t-07-gate-reminder-report.md`、`t-08-g2-surfaces`（73 passed，我复跑）、`t-09-pm-consumer-report.md` |
| VC-012 | 当提交 gate 字段时，authorizes 为闭集数组且未被列出的动作类型不得被引用为授权源 | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-013 | 当检查三条 worker 提示词时，逐字包含同一硬约束常量 | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-014 | 当 AC/VC 文本相对 freeze 变化且无批准记录时，done 被拒且 timeline 留机器分类 | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-015 | 当只有 gate 自由文本 note 被引用为授权源时，机械判为未授权（fail-closed） | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-016 | 当读历史 v1 gate 与无 freeze 工程时，parse 全成功且渲染逐字节同改造前 | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-017 | 当摘掉/反转任一判据时，对应用例转红（非空洞对照） | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-018 | 当复算验收时，所有 [VERIFY] 数值来自实测且"已机器校验"类声称带文件:行号或测试名 | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-019 | 当注册 3 个配置键时，两侧注册表与冻结语料同步（含单键 accept 例与越界 reject 例） | G3 (授权范围/契约闸门) | T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md` |
| VC-020 | 当面板逐 tick 渲染时，帧内绝对采集时刻随 tick 前进；连续 >3 个周期未前进时帧内显式告警"快照过期" | G4 (面板冻结/自证) | T-13 / T-12 → `t-13-g4-freshness-report.md`、`t-12-g3-writer-g4-rearm-report.md`（`autopilot-monitor.test.ts` VC-020/021/022 + VC-023） |
| VC-021 | 当数据面变化（_workers.parallel 落 N 行 running）时，面板在 ≤2 个刷新周期（8 s）内显示 workers: N running | G4 (面板冻结/自证) | T-13 / T-12 → `t-13-g4-freshness-report.md`、`t-12-g3-writer-g4-rearm-report.md`（`autopilot-monitor.test.ts` VC-020/021/022 + VC-023） |
| VC-022 | 当 tick 内任一读/渲染失败时，仍产出带失败时刻与摘要的降级帧（不丢帧、不静默） | G4 (面板冻结/自证) | T-13 / T-12 → `t-13-g4-freshness-report.md`、`t-12-g3-writer-g4-rearm-report.md`（`autopilot-monitor.test.ts` VC-020/021/022 + VC-023） |
| VC-023 | 当会话被替换/重激活（ctx 变化或 session_shutdown）时，面板被重挂且不永久消失 | G4 (面板冻结/自证) | T-13 / T-12 → `t-13-g4-freshness-report.md`、`t-12-g3-writer-g4-rearm-report.md`（`autopilot-monitor.test.ts` VC-020/021/022 + VC-023） |
| VC-024 | 9 列（含 origin）行样本读入后 rows 含全部行、unparsable == 0；7/8 列样本同样全部读入。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-025 | 人为插入 1 行 10 列行 ⇒ unparsable == 1、回写后该行原文仍在（行数不变）、且驱动 fail-closed。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-026 | 无版本头的历史队列文件经一次 upsert 后逐字节（除目标行）不变；新建队列才有 mw-queue:v2 头。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-027 | unparsable > 0 时触发一次派发 ⇒ 新增行 = 0，且 auto-decisions.jsonl 出现 phase:"dispatch-alarm"。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-028 | 队列文件缺失/空 + 候选集含终态证据 ⇒ 新增行 = 0 + 告警；无终态证据（真·新项目）⇒ 正常派发（双向例）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-029 | 候选 10 个且全部合法 ⇒ 单轮新增 = dispatch_max_per_scan（默?3）+ 配额告警。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-030 | launcher.py 未传 --max-workers 时并发上限 = launcher_max_workers（默?8）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-031 | 252 行 / 100% 非终态样本 ⇒ mw doctor --json 含 queue-burst-shape；健康队列 ⇒ 不含（零扰动）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-032 | 任务 A 已 done 且无 supersedes ⇒ 再次派发被拒（无新增行、无新 run.json）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-033 | 任务 A 已 done、新任务声明 supersedes: A ⇒ 派发成功且 A 目录 mtime/内容不变。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-034 | PM 侧自动派发 1 个任务后，其它 key 的 252 行逐字节不变（AC-019①）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-035 | 程序化 dispatchNewTasks(..., { scope: "cli" }) 与未认领新 key 的显式派发在同一状态下成功（AC-019②③）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-036 | list_tasks（scope:"all" 与 scope:"key", key=<foreign>）在 foreign-live key 上返回其行与状态（读面全局）；同一窗口对同一 ke | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-037 | 跨 key 写拒绝时零副作用：无 workers/<task> 目录、无队列行、无 _workers.parallel 文件；advance_phase 拒绝时 gate 脚本未被执行（stu | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-038 | 可写面反向例：自有 claim key（claimId == self）与未认领的新 key 显式派发成功（新建 key 流程不受 AC-024 影响）。 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-039 | unparsable 行在 update_status / archive_stale_entries / upsert_worker_row 三次写入后原文仍在且 unparsable_co | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-040 | 12 个 pending 候选 + max_workers=None ⇒ 恰好 launcher_max_workers（默认 8）个 spawn；项目 config launcher_max | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-041 | acked 且行非终态 ⇒ 收敛为终态 + 0 spawn；ack 文件为垃圾内容 ⇒ 仍正常 spawn（fail-safe）；read_acked 对无分隔符/空 key/空时间戳行一律跳 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-042 | 启动后 run.json 含 schema=1/task_key/run_id=<task>@<iso>/owner_key/kind/status=running/started_at/pi | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-043 | settle 后 status=done+exit=0+ended_at+artifacts∋output.md，且 output.md 首行是 <!-- mw-run: <run_id> s | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-044 | 自己目录 run.json 终态 ⇒ 派发被拒且零新增行，并产 kind="run-ledger-conflict" 告警（detail 含 run-terminal）；running ⇒ 拒 | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-045 | 滞后台账行 + run.json 终态 ⇒ 收敛为该终态（含 needs-clarification）；running + output.md ⇒ lost（并写回 run.json：run_ | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-046 | scope="pm" 下另一 key 的候选不被扫描（零新增行），但 auto-decisions.jsonl 出现一次 kind="out-of-scope"（count = 被跳过的 ke | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |
| VC-047 | 把临时 key 的 pm-state 推进到 design 后跑一次 conductor tick ⇒ <key>/evidence/contract-freeze.json 出现且 spec | G5/G6 (队列完整性/派发隔离/运行身份) + AC-025 | T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md` |

## 4. 非空洞对照索引（AC-014）

| 卡 | 对照 / 变异 | 证据 |
|---|---|---|
| T-01 | 3 组反事实（摘指纹分支 / 摘专用 label / 摘 mark_stalled 复算） | `evidence/runs/t-01-l3-aborted-report.md` |
| T-02 | 语料反证（T-02 三键 0 命中 / T-18 三键各 6 命中）+ golden sha 重冻 `27b222b9…` | `t-02-config-keys-report.md` |
| T-03 | 摘 `contract-refused` ⇒ 事件集合计数转红 | `t-03-event-names-report.md` |
| T-04 | 闭集/解析面/值校验反例 + R1 偏离裁决（`authorizes` 在 40 名单之外） | `t-04-contract-guard-report.md` |
| T-05 | TS 镜像两侧集合相等 + 配置 20 键 | `t-05-ts-mirror-report.md` |
| T-06 | X1 反例（无 marker ⇒ 不判 aborted）转红 | `t-06-l3-tests-report.md` |
| T-07 | 3 组反事实（摘阈值分支 / 摘 ledger 写 / 摘已答过滤） | `t-07-gate-reminder-report.md` |
| T-08 | G2 呈现用例 + `!tickStale` 门控反向用例 | `autopilot-monitor.test.ts`（PM 复跑 73） |
| T-09 | 接缝核验（ledger 行键 ≡ 读取端键；`seq` 由共享写入器补） | `t-09-pm-consumer-report.md` |
| T-10 | 3 组 CF：摘 done 检查 / 放宽批准判据 / 删 prompt 常量（逐字节还原） | `t-10-g3-done-guard-report.md` |
| T-11 | 摘 doctor 段 ⇒ 3 例红；摘 CLI dispatch ⇒ 5 例红（还原） | `t-11-g3-cli-doctor-report.md` |
| T-12 | CF A（摘闭集校验）/ B（摘 JSON-list 项）/ C（摘 ctx 分支）/ D（摘缺失行拒绝）全红 + 还原 | `t-12-g3-writer-g4-rearm-report.md` |
| T-13 | 摘降级分支 / 摘 stale 计算 各转红 + 还原 | `t-13-g4-freshness-report.md` |
| T-14 | A（`STALL_REASON_CODES`→12）/ B（摘语料 accept 例）/ C（摘 Python 事件名）/ D（摘 TS 事件名）全红 | `t-14-count-locks-report.md` |
| T-15/T-17/T-19 | `evidence/scripts/t15-controls.ps1`（A 5 红 / B 1 红 / C 1 红）、`t17-controls.ps1`（5 组）、`t22-controls.ps1`（4 组） | `t-15-t17-t19-report.md`、`t-22-crosskey-readonly-report.md` |
| T-18 | `t18-controls.ps1` A–F 全红 + 还原（含 14→17 配置键与 doctor 三判据） | `t-18-queue-integrity-report.md` |
| T-20 | `t20-controls.ps1` A–G 全红 + 还原 | `t-20-run-identity-report.md`（**原括号“控制 B 曾因不承重被替换”已撤回：无工件支持，见 §8**） |
| T-21 | `t21-controls.ps1` A–E 全红 + 还原（8/9/10 列与旧 codec 丢行） | `t-21-integrity-report.md` |
| T-23 | A（摘 tick 调用）/ B（改非空块重写 ⇒ sha 断言红）/ C（删事件）/ D（改默认覆盖）/ E（真活端到端） | `t-23-g3-anchor-report.md` |

## 5. 未验证 / 边界（诚实清单）

1. **运行时尚未切换**：本轮全部 TS/扩展改动**未生效**。实测全局 bundle `~/.pi/agent/extensions/agent-team-loop.js` = 2026-10-10 11:40:42 / 952,453 B / sha256 `52187720D22D06DEE10FEE383981CD041FAD763BFB292B9B2BD7756D3A53FE0B`，含 `WORKER_COLS_MIN/MAX`（post-`b8bc115ff`）但**不含本 key 任何标记**（8 个 marker 命中均为 0）。⇒ 本报告结论均为**源码+测试级**，非“已在运行中观测”。切换步骤见 `evidence/runs/runtime-cutover-runbook.md`（+PM 复核附录），**待用户批准**。
2. **9 个 pre-11:40 常驻窗口**：其加载的安装副本历史内容不可考 ⇒ runbook 已把“一定是 pre-fix 解析器”**降级为安全假设**，结论是“一律重启”。
3. **两条基线红保持**（非本 key 引入，环境相关）：`test_baseline_left_end_bound`、`test_true_below_without_resume_stays_below`；本 key 未修，去向见 §6。
4. **`./test.sh` 不可运行**（WSL 无发行版）⇒ 非 e2e 口径以 pytest 全量 + 13 TS suite 替代。
5. **AC-011 的“生产可达性”依赖 AC-025 的锚点**：历史 key（无 sidecar）仍不受 G3 保护，这是 D-015 `[REVISED]` 的有意选择（否则与 AC-013 冲突）。
6. **本次 QG 的判定层级 = 源码 + 证据级**；独立 review 复审（`workers/mwg-qg2b-code-adversarial/report.md`）后 **AC-007 / AC-024 降级为 ⚠️ PARTIAL**、§4 一条不实声称撤回 —— 全部更正见 **§8**。
7. **PM 直执的小改已复核**：`console.ts` 顶层 `USAGE`/文件头补 `--authorizes`（T-12 交接①）；22 条 CHANGELOG 正文由中文改写为英文体例；两者改后均复跑相关 suite + `npm run check` exit 0。

## 6. 遗留与去向

| 遗留 | 性质 | 去向 |
|---|---|---|
| **R21** dist/bundle 未重建 + 运行时未切换 | 交付缺口（非缺陷） | 用户批准后 PM 直执（runbook）；本 key `done` 时在 `achieved.md`「遗留」显式标注 |
| **R18** spawn 竞态下“刚派发的行不得被静默判终态”无机器判据 | 新发现（假 `failed` 现场实证） | 待用户决定是否单开小卡；证据 `evidence/runs/t23-runtime-writeback-observation.md` §5 |
| **R19** 错过 design/plan 边界的 key 无锚（不回溯） | 有意设计 | 显式 `mw autopilot contract-freeze`；doctor/CLI 可见“无 sidecar” |
| **R20** `monitorCtx` 只由 `autoStartMonitor` 写 | 已知小瑕疵（最坏多一次无害 stop+start） | 接受不处理（T-12 回执 §6） |
| **D-038** `autopilot/dispatch.py` 未接 `run.json` | 已知边界 | 记入本 key 残留；后续 key 或用户决定 |
| 两条基线红 | 环境相关存量 | 不作为本 key 验收对象；如需修另开 key |

## 7. 复现命令（最小集）

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -X utf8 -m pytest -q -p no:randomly            # 期望 2 failed(=基线) / 1523 passed
cd H:/git/Multi-Workers
npm run check                                          # 期望 exit 0
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts test/suite/run-store.test.ts test/suite/worker-dispatch-guard.test.ts test/suite/worker-run-identity.test.ts test/suite/worker-crosskey-readonly.test.ts test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-event-parity.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-config-parity.test.ts test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts
python -X utf8 .agenticdoc/mw-gate-verdict-hardening/evidence/scripts/pm-g3-live-check.py   # G3 端到端
```

**结论（两次复审更正后）：AC = 22 PASS + 3 ⚠️ PARTIAL（AC-007 已终态 stage 未实现；AC-008 `mw doctor` 半边未交付；AC-024 `/worker` 未受守卫且文案不符）、AC-014/AC-022 带边界备注；VC 47/47 按其字面成立（VC-011/017/018 因欠债标 ⚠️）；新增红 0。交付缺口 = 运行时切换（R21）+ 3 个代码缺口 + 文档勘误（待新 key），详见 §8/§9。**

## 8. 复审更正（2026-10-10 20:40）——独立 review 反证 + PM 独立复现

来源：独立代码级对抗复审 `workers/mwg-qg2b-code-adversarial/report.md`（`[VERIFY] QG-B: items=14 confirmed=12 refuted=2 undecided=0 hollow_controls=0 hollow_tests=0 mirror_mismatch=0 conclusion=conditional`）。
下表每条都由 **PM 亲自复现**（不采信 worker 结论本身）：

| # | 本报告原判定 | 复审反证 | PM 独立复现（坐标） | 处置 |
|---|---|---|---|---|
| 1 | AC-007 = PASS | **“已终态 stage 的 gate”未实现** | `gates.pending_gates`（`gates.py:770-772`）= 整个 gates 目录按 `status=="pending"` 过滤，无 stage 范围；`_remind_pending_gates`（`conductor.py:2564`）直接使用；`pending_gate_reminders` 三条件（`conductor.py:2541-2551`）无 stage 终态判据 ⇒ 人工关闭 roadmap stage 而门未答时仍会提醒 | 本条降级 **⚠️ PARTIAL**；代码缺口 → 遗留（新 key） |
| 2 | AC-024 = PASS | **`/worker` 未受守卫 + 拒绝文案自相矛盾** | `foreignLiveClaimRefusal` 全仓仅 2 个调用点（`ui-bridge.ts:1333`、`:1698`）；`/worker`（`registerWorkerCommands` `:1710`，注册 `pm-orchestrator.ts:1059`）经 `:66-67` 显式 key 直通且无守卫，`fs.mkdirSync`+`writeFileSync` task.md `:1813-1816`、`dispatchTask` `:1819`；拒绝文案 `:241-242` 明写 “Refused: dispatch_worker, **/worker**, advance_phase…” | 本条降级 **⚠️ PARTIAL**；缺口 → 遗留（新 key，含“扩守卫 vs 改文案”口径待裁） |
| 3 | §4 T-20 行括注“控制 B 曾因**不承重**被替换为承重变异” | **无工件支持**：该说法只出现在本报告；被引来源 `t-20-run-identity-report.md` 全文无此句、`tasks/T-20-run-identity-state.md` 对照表也只有当前 B，且无任何工件记录“原控制 B”是什么 ⇒ 违反 AC-014/VC-018 的锚点要求 | `rg` 两个被引文件均无该断言（0 命中） | **撤回该括注**；`t20-controls.ps1` 当前 7 组经复审静态判定全部承重（27 组变异点均落在判据行） |

**复审确认的已声明边界（非新缺陷，无需动作）**：

1. 空队列 + 产物证据守卫位于 per-owner 循环内（`pm-orchestrator.ts:653`，循环起于 `:595`）⇒ 混合场景下“新增行数 = 0”只按 owner 成立；`t-15-t17-t19-report.md:98` 已如实登记该取舍。
2. `readMonitorState` 的 per-section catch（`monitor.ts:362/376/432`）静默给空段，仅整体抛错才降级 —— 与本报告 §5.1 已声明的“widget 写失败静默”同族。
3. `STALL_REASON_CODES`(14) 无 TS 镜像 —— 两侧从未声称镜像，不计不符。

**复审未否证的项**：done-guard 首个 check-before-write（`conductor.py:2244` 严格先于 `:2278/2287/2297/2317/2331/2334` 全部写盘）、五个队列写者槽位保留、AC-025 首见冻锚（仅 design/plan、非空不重写、CLI 默认拒变更块）、AC-020 短路先于配额/候选、AC-021 有界 + `_workers.acked` 参与、`run.json` worker 自写 + launcher 只补 `lost`、G2 上限（30min/2 次/零残留/`seq` 水位）、G4 帧自证与降级帧、事件 27 / 配置 20 / `authorizes` 闭集 2 逐项相等、15 个抽查测试无空洞、23 张卡无空绑定。

## 9. 第二次复审更正（QG-A 证据链审查，2026-10-10 21:00）

来源：独立证据链审查 `workers/mwg-qg2a-evidence-chain/report.md`（131 问 = 114 ✅ / 17 ⚠️ / 0 ❌；`[VERIFY] QG-A: questions=131 sufficient=114 insufficient=17 missing=0 conclusion=conditional`）。同样由 PM 逐条复现：

| # | 本报告原判定 | 复审反证 | PM 独立复现 | 处置 |
|---|---|---|---|---|
| 1 | AC-008 = PASS（只引 `monitor.ts` 锚点） | **`mw doctor` 半边未交付**：AC-008 字面要求“monitor 面板**与 `mw doctor`**”两个监视面；design D-009 第三面（`design.md:147`/`:386`/`:432`）要求在 `mw_common.py` 加 `blocked_on_human` + `_gates_text_alerted` 触发 + `format_document_text` 条件后缀，且该面**从未进任何任务卡**（plan 把 `mw_common.py` 只分给 T-11/T-18） | `rg 'blocked_on_human|BLOCKED_ON_HUMAN' packages/multi-workers/mw_common.py` = **0 命中**（monitor.ts 侧 = 10 命中）；`t-08` 回执全文无 “doctor” | AC-008 降级 **⚠️ PARTIAL**；缺口中 `mw_common.py` G2 面 → 遗留（新 key） |
| 2 | §1 “基线 `verify-baseline.md` = 2 failed / **1431** passed” | **引用失准** | `verify-baseline.md` 原文 = “2 failed, **655** passed, 8 deselected”（早期子集跑）；1431 是 T-21 期全量数 | **已更正 §1**（并保留“新增红 = 0”结论：两条红同名同集合） |
| 3 | AC-001 / AC-005 行 conductor 锚点 | **锚点漂移**（报告由脚本组装时复用早期行号） | 实测：AC-001 → `:1662`/`:1664`（原 `:1649`/`:1651`）；AC-005 → `:2522`/`:2555`/`:2764`（原 `:2475`/`:2508`/`:2577`） | **已重锚 §2 两行** |
| 4 | AC-022 = PASS | **D-038 边界未在行内披露** | `rg 'run\.json' packages/multi-workers/autopilot/dispatch.py` = **0 命中** ⇒ Python 派发判据不读产物终态 | AC-022 标 **PASS（边界）**；缺口 → 遗留（新 key） |
| 5 | §3 VC 证据通道列 | **模板化引用**（24 行同组 6 文件），非逐条锚定 | 属实（报告由 `t23-quality-gate-report.py` 生成） | §3 加口径说明并指向 `verify-g5g6-tests.md` §1 的 47 行映射 |
| 6 | AC-014 = PASS | 对照“跑红 + 还原”只能由运行证实 | 属实（两次复审均无 bash）；静态层 27 组变异点全部承重 | AC-014 标 **PASS（边界）** |

**复审认同（非差异）**：25 条 AC 的**实现存在性**经独立重锚后**无一证伪**；收口数字（2 failed / 1523 passed、13 suite / 340 tests、`check` exit 0）与 `verify-closure.md` 逐字一致；R21 为已诚实声明的全局欠债。

**仍未处置（归入新 key，避免污染本 key 已冻口径）**：

1. 代码缺口：**AC-008 doctor 面**、**AC-007 stage 终态**、**AC-024 `/worker` 守卫/文案**、**D-038 `dispatch.py` 接 `run.json`**。
2. spec/plan/design 勘误：AC-021 标题与反向用例措辞冲突；spec §2.3 与 AC-025⑤ 字面冲突；plan §2.5 值域（1..50 应为 1..64）；design §0 `ac_count: 24` 陈旧、§8 映射表止于 AC-018。
3. 工作流前置物：`evidence-requirement.md` / `evidence/baseline/` 缺失（本 key 以 design §7 + `verify-baseline.md` 替代）——需登记偏离或补页。
4. 卡片卡头 VC 少报（T-18/T-19/T-20）——plan §3 为准，卡头补登记。
5. 运行层欠债：6 份 `*-controls.ps1` 与全量 pytest/vitest 需在有 bash 的会话独立复跑。
