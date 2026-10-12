# achieved — mw-gate-verdict-hardening

- key: `mw-gate-verdict-hardening` · deps: `mw-autopilot-slot-capacity`（已提交）
- 代码基线：`776b82d7f`（`dev/AgentTeam`）+ 本 key 未提交工作区改动
- 规模：**25 AC / 47 VC**；实现卡 T-01…T-23（T-08b 为假 `failed` 引发的重复派发，人工终止）
- 验收结论（**两次独立复审更正后**）：AC = **22 PASS + 3 ⚠️ PARTIAL**（AC-007 已终态 stage 未实现 / AC-008 `mw doctor` 半边未交付 / AC-024 `/worker` 未受守卫）+ AC-014/AC-022 带边界；VC 47 项按其字面成立；全量回归**新增红 = 0**。判定层级 = **源码 + 证据级**（除运行时切换外）；复审报告见 `workers/mwg-qg2a-evidence-chain/report.md`、`workers/mwg-qg2b-code-adversarial/report.md`
- 质量门报告：`evidence/quality-gate-report-20261010.md`
- **未生效声明（重要）**：本轮全部 TS/扩展改动**尚未在运行中生效**（运行时仍是旧安装副本，见「遗留 R21」）。

## 系统行为变化

### 1. 观测面不再撒谎（G4 + G2）

- `/autopilot monitor` 的**每一帧**携带绝对采集时刻与 tick 计数；连续 3 个刷新周期未前进即首行显式 `STALE PANEL (no refresh since <ISO>, <dur>)`。
- tick 内读取失败**不再静默丢帧**：改用带 `lastErrorAtMs` + 错误摘要的**降级帧**（沿用上一帧数据），只有 widget 写入失败仍是静默失败。
- 面板顶置 `BLOCKED_ON_HUMAN` 行（非终态 worker 计数 + 最旧 pending gate 年龄），gate 行附粗粒度 `age=`；数据面变化 ≤2 个刷新周期（8 s）内跟随。**但 AC-008 的 `mw doctor` 半边未交付**（design D-009 第三面要求在 `mw_common.py` 加 `blocked_on_human` + 条件文本；实测 0 命中，且无卡承接）—— 独立复审发现、PM 已复现，见「遗留」。
- `/new`·`/resume` 后 `autoStartMonitor` 在 monitor 上下文变化时先停表再重启 ⇒ 面板不再永久消失。

### 2. 闸门不再静默（G2）

- conductor 每 tick 检查 `status=pending` 的门，超阈（默认 30 min）每门最多提醒 2 次：写 `phase:"remind"` ledger 行 + `gate-reminder` timeline 事件；PM 侧按 `seq` 水位去重后推给人。
- 已答门 / 无门 ⇒ 零事件（零残留）。**“已终态 stage 的 gate ⇒ 零事件”未实现**（`gates.pending_gates` `gates.py:770-772` 无 stage 范围过滤，`pending_gate_reminders` `conductor.py:2541-2551` 无 stage 终态判据）—— 独立复审发现、PM 已复现，见「遗留」。

### 3. L3 流中止与“无裁决”不再混判（G1）

- `worker.log` 出现中止标记且无合格裁决源 ⇒ 判 `aborted` 并发 `l3-aborted` timeline 事件（而非 `no-verdict`），以 `loop="l3abort:<key>"` 的**独立预算**（`l3_abort_retry_limit`，默认 1）有界重掷；预算耗尽 ⇒ `mark_stalled(reason_code="l3-aborted")`。

### 4. AC/VC 生效文本的改写需要机械授权（G3 + AC-025）

- gate frontmatter 新增可选 `authorizes` 字段（闭集 `{retry, contract-change}`），由人经 `/autopilot gate <id> approve|reject --authorizes <a,b>` 写入；越界值 fail-closed。
- `advance *->done` 前**第一个 check-before-write** 即做 AC/VC 文本身份检查（`<key>/evidence/contract-freeze.json` 内容寻址锚）：未授权改写 ⇒ `contract-refused` 事件 + `contract-unauthorized` stall + `gated`，不写 QG/achieved/pm-state。
- **锚点由框架自己建立**：conductor 在 key 首次进入 `design`（冻 AC 块）/ `plan`（冻 VC 块）时**幂等一次写**并留 `contract-frozen` 事件；历史 key **不回溯**；显式入口 `mw autopilot contract-freeze [--block] [--force]`（已变更块默认拒绝，`--force` 才重冻并打印被替换 id）；`mw autopilot contract-guard` 与 `mw doctor` 暴露只读判定。无锚/锚损坏 ⇒ 放行（否则与 P-018 零扰动冲突）。
- repair / phase-writer / fix-writer 三处提示词逐字含同一 AC/VC 硬约束常量。

### 5. 队列不再因“读不懂一行”而重建（G5）

- `_workers.parallel` 支持 `# mw-queue:v2` 版本头；行宽 7..9 列全可读；不可解析行**计数 + 告警 + 回写时逐行原文保留**（不再静默删除）。
- 所有队列写者（TS `upsert`、Python `update_status`/`archive_stale_entries`/`upsert_worker_row`/`autopilot/dispatch.py`）改为**只重写自己那一行**；无匹配行时不重写文件。
- 派发侧 fail-closed：`unparsable > 0` ⇒ 零派发 + `dispatch-alarm`；空队列 + 终态证据 ⇒ 零派发；单轮配额 `dispatch_max_per_scan`（默认 3）；launcher `launcher_max_workers`（默认 8）有界并发并跳过已 acked 终态任务。
- `mw doctor` 新增三条**无状态**判据：`queue-rows-unparsable` / `queue-burst-shape` / `run-ledger-conflict`（只读面不建文件）。

### 6. 派发隔离 + 运行身份不可复用（G6）

- PM 侧自动派发作用域收窄为本窗口 watch key + `_scratch`（`mw` CLI 保持全局）；被跳过的 key 聚合为 `kind="out-of-scope"` 告警（可见而非静默）。
- 每个 worker 在**自身目录**写 `run.json`（`run_id`/`owner_key`/`pid`/心跳/终态）；launcher 只补 `lost` 而不代写终态。派发判据（`run-store.ts:176-205`）：自己的 `run.json` 终态或 active ⇒ 拒（同一 task_key 一律不重跑）；新 task_key 声明 `supersedes: <旧>` 且旧目录**已终态** ⇒ 放行（合法替换），指向**未知/未终态** ⇒ 拒。
- 跨 key 只读（AC-024）：`dispatch_worker`（显式 `key`）/`advance_phase` 对他人 live 持有的 key 在任何副作用前拒绝并返回 `[cross-key-read-only]`；读面（`list_tasks scope:"all"`、`mw_status`、doctor、面板）保持全局。

### 7. 配置与事件词汇

- `DEFAULT_CONFIG` **14 → 20**：`launcher_max_workers`(1..64,8)、`dispatch_max_per_scan`(1..64,3)、`queue_alarm_delta`(10..10000,50)、`l3_abort_retry_limit`(0..10,1)、`gate_reminder_after_min`(1..1440,30)、`gate_reminder_max`(1..2,2)；两侧镜像 + 冻结语料 **64 → 73** 例（单键 accept + 越界 reject），sha 双侧同步。
- timeline 事件词汇两侧 **23 → 27**（`l3-aborted`/`gate-reminder`/`contract-refused`/`contract-frozen`）；`STALL_REASON_CODES` **12 → 14**。

### 影响面（后续任务参考）

- 触及包：`packages/multi-workers`（`autopilot/{conductor,config,dispatch,gates,timeline}.py` 改动 + `autopilot/contract_guard.py` **新增**，`launcher.py`、`mw.py`、`mw_common.py`；`autopilot/advance.py` **未改动** —— 原始登记误列，复审更正）与 `packages/coding-agent`（`agent-team-loop/{autopilot,pm,shared,worker}` 的 TS 侧 + 控制台/面板）。
- 语义变更点（下游卡必须认领）：gate frontmatter 新增可选字段；`advance *->done` 新增前置拒绝路径；队列行可带版本头并把 `origin` 写为第 9 列；PM 自动派发作用域收窄；worker 目录新增 `run.json`；`lost` 成为两侧终态但在 widget 属待处理。

## 遗留

| # | 遗留 | 性质 | 去向 |
|---|---|---|---|
| **AC-007 缺口** | “已终态 stage 的 gate ⇒ 零提醒”未实现（复审发现，PM 复现：`gates.py:770-772` 无 stage 范围、`conductor.py:2541-2551` 无 stage 终态判据） | 代码缺口：待新 key 修复（或明确降级该 AC 子句） |
| **AC-024 缺口** | `/worker --key <他人 live key>` 未受跨 key 守卫（`ui-bridge.ts:1710` 无 `foreignLiveClaimRefusal`），且拒绝文案 `:241-242` 已声称 `/worker` 被拒 ⇒ 文案与实现不符 | 代码缺口：待新 key（扩守卫或改文案，口径待用户裁） |
| **AC-008 缺口** | `mw doctor` 的 G2 可见面未交付（`mw_common.py` grep `blocked_on_human|BLOCKED_ON_HUMAN` = 0 命中；design `:147`/`:386`/`:432` 要求；AC-008 字面含“与 `mw doctor`”） | 代码缺口：待新 key 落地或正式 descope |
| **D-038 确认（AC-022 边界）** | Python 侧 `autopilot/dispatch.py:621-633` 派发判据不读 `run.json` ⇒ “派发/重派判据首先读产物终态”只在 TS 路径 + launcher 收敛成立 | 代码缺口：待新 key 接 `read_run_status`（或 AC 行内明确边界） |
| **文档勘误（待新 key）** | spec AC-021 措辞冲突、spec §2.3 vs AC-025⑤、plan §2.5 值域、design §0 `ac_count`/§8 映射表陈旧；`evidence-requirement.md` 缺失；T-18/19/20 卡头 VC 少报 | 文档：随新 key 的 spec/design 阶段一并修 |
| R21 | **dist/bundle 未重建 ⇒ 本轮改动尚未生效**；运行时切换待批准 | 交付缺口（非缺陷） | 用户批准后 PM 直执 `evidence/runs/runtime-cutover-runbook.md`（含 bundle sha256、9 个窗口 PID、验证与回滚）；**本 key 的 done 不代表已上线** |
| R18 | spawn 竞态下“刚派发的行不得被静默判终态”缺机器判据（假 `failed` 实证） | 新发现 | 待用户决定是否单开小卡；证据 `evidence/runs/t23-runtime-writeback-observation.md` §5 |
| R19 | 错过 design/plan 边界的 key 无锚（不回溯） | 有意设计 | 需人显式 `mw autopilot contract-freeze`；`mw autopilot contract-guard --key K` 会打印 `no freeze sidecar` |
| R20 | `monitorCtx` 只由 `autoStartMonitor` 写（`cmdMonitor on` 不更新） | 已知小瑕疵 | 接受不处理（最坏多一次无害 stop+start） |
| D-038 | `autopilot/dispatch.py` 未接 `run.json` | 已知边界 | 后续 key 或用户决定 |
| — | 两条环境相关基线红（`test_baseline_left_end_bound`、`test_true_below_without_resume_stays_below`） | 存量 | 不作为本 key 验收对象；如需修另开 key |
| — | `./test.sh` 本机不可运行（WSL 无发行版） | 环境限制 | 以 Python 全量 + 13 TS suite 为等价非 e2e 口径 |
| — | E2Feature 侧 reflect 台账仍标记 `l3-verdict-source-mismatch` 未闭环 | 跨项目 | 本 key 已实现其根因修复；是否回写 E2 台账由用户决定 |

## 证据索引

- 质量门与收口验证：`evidence/quality-gate-report-20261010.md`、`evidence/runs/verify-closure.md`、`evidence/runs/verify-baseline.md`、`evidence/runs/verify-g5g6-tests.md`
- 逐卡报告：`evidence/runs/t-01…t-23-*-report.md`（含 `[VERIFY]` 原文与对照红/绿）
- 运行时与事故：`evidence/runs/t23-runtime-writeback-observation.md`、`evidence/incident-in3-queue-reenqueue-20261010.md`、`evidence/in3-impact-assessment-20261010.md`、`.agenticdoc/_incidents/in3-queue-reenqueue-20261010/`
- 切换与复核脚本：`evidence/runs/runtime-cutover-runbook.md`、`evidence/scripts/`（`*-controls.ps1`、`pm-g3-live-check.py`、`t23-normalize-whole-queue.py`、`t23-queue-inspect.py` 等）
