# T-16: 文档收口 + 全量回归 + 运行时切换 runbook（收口卡；dist 重建已按 PM 决定拆出）

- 波次: **4** · 依赖: T-01…T-15、T-17…T-23（全部 done）
- 写面（独占）:
  - `packages/multi-workers/CHANGELOG.md`（**只在 `## [Unreleased]` 内追加**）
  - `packages/coding-agent/CHANGELOG.md`（同上）
  - `packages/multi-workers/README.md`（**仅**在确有必要时；见「文档同步」第 3 条）
  - 新文件 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/runtime-cutover-runbook.md`
  - 新文件 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/verify-closure.md`
- AC: 全部 · VC: 全部
- 基线: `10446aefb`（对照基线文件 `evidence/runs/verify-baseline.md`）

## 目标

把本 key 的实现收口成**可交付 + 可复核**的状态：CHANGELOG、基线对照、全量回归证据、运行时切换 runbook。

## ⚠️ PM 决定（2026-10-10 19:10）：本卡**不重建 dist / 不跑 `npm run build` / 不做安装与重启**

原卡要求「dist 重建」，PM 决定**拆出**，理由两条（都写进回执）：

1. **AGENTS.md 硬规则**：`npm run build` 只在用户明确要求时才可执行；而运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）**仍在等用户拍板**（pm-state「待用户决定 ①」）。未获批准就重建/安装 = 单方面改变全项目运行时行为。
2. **风险**：`packages/coding-agent/dist/**` 是版本控制产物，多会话同 cwd 下重建会夹带其它会话改动；且切换会让 9 个旧窗口的 in-memory 解析器（pre-`b8bc115ff`，会把 9 列行当不可解析 ⇒ IN-3 复现条件）与新产物共存。

⇒ 本卡改为产出 **`runtime-cutover-runbook.md`**（见下）。dist/bundle 重建与切换留给用户在批准后执行（PM 直执）。

## 交付物

### 1. CHANGELOG（两包，**只在 `## [Unreleased]` 既有小节内追加**，不新建重复小节）
先读全文（两文件都已有很长的 `Added` 段），把下列条目追加到对应小节（格式对齐同文件既有条目：`- Added ...（mw-gate-verdict-hardening）: 说明。`）：

**`packages/multi-workers/CHANGELOG.md` → `### Added`**
- `l3-aborted` 中止指纹：L3 回合的 worker 流中止（`worker.log` 出现中止标记且无合格裁决源）不再与"无裁决"混判，发 `l3-aborted` timeline 事件、以 `loop="l3abort:<key>"` 的独立重掷预算有界重试，预算耗尽落 `mark_stalled(reason_code="l3-aborted")`。
- pending gate 主动提醒：conductor 每 tick 检查待应答门，每门最多提醒 2 次（`gate_reminder_after_min` / `gate_reminder_max`），写 `phase:"remind"` ledger 行 + `gate-reminder` timeline 事件；PM 侧用 `seq` 水位去重后推给人。
- G3 闸门授权范围：gate frontmatter 新增可选 `authorizes` 字段（闭集 `{retry, contract-change}`）；`advance *->done` 前做 AC/VC 文本身份机械检查（`contract_guard.py`，`<key>/evidence/contract-freeze.json` 内容寻址锚），未授权改写 ⇒ `contract-refused` 事件 + `contract-unauthorized` stall；锚点由 conductor 在 `design`/`plan` 接受边界**幂等自动建立**，并可用 `mw autopilot contract-freeze` 显式补/重冻，`mw autopilot contract-guard` + `mw doctor` 暴露只读判定。
- 队列完整性（G5）：`_workers.parallel` 新增可选版本头 `# mw-queue:v2`；未知行宽不再静默丢弃（7..9 列全可读），读侧统计并回写时**逐行原文保留**不可解析行；所有 Python/TS 队列写者改为**只重写自己那一行**；无法解析行 > 0 时抑制派发；`mw doctor` 新增 `queue-rows-unparsable` / `queue-burst-shape` / `run-ledger-conflict` 三条**无状态**判据。
- launcher 有界 spawn（G5）：`launcher_max_workers`（默认 8，1..64）限制单轮并发；重建队列时跳过已 acked 的终态任务。
- 派发隔离与运行身份（G6）：PM 侧自动派发作用域收窄为本窗口 watch key + `_scratch`（`mw` CLI 保持全局），被跳过的 key 聚合为 `out-of-scope` 告警；worker 自写 `<task_dir>/run.json` 运行身份（`run_id`/`owner_key`/`pid`/心跳/终态），launcher 只补 `lost` 不代写终态；同一 `task_key` 不再重跑，需补充用新 key + `supersedes`；`dispatch_max_per_scan`（默认 3）单轮配额。
- 新增配置键（`DEFAULT_CONFIG` 14 → 20）：`launcher_max_workers`、`dispatch_max_per_scan`、`queue_alarm_delta`、`l3_abort_retry_limit`、`gate_reminder_after_min`、`gate_reminder_max`。

**`packages/coding-agent/CHANGELOG.md` → `### Added`**
- 面板块自证 + 降级帧（G4）：`/autopilot monitor` 每帧携带绝对采集时刻与 tick 计数，连续 3 个刷新周期未前进即显式 `STALE PANEL (...)`；读取失败不再静默丢帧，改为输出带错误摘要的降级帧；数据面变化 ≤2 个刷新周期内跟随。
- 面板不在人应答前撒谎（G2）：顶置 `BLOCKED_ON_HUMAN` 行（非终态 worker 计数 + 最旧 gate 年龄），并给 gate 行加粗粒度 `age=`。
- `/autopilot gate <id> approve|reject --authorizes <a,b>`：把授权动作类型写进门文件（闭集 `{retry, contract-change}`，越界 fail-closed；门文件无 `authorizes:` 行时拒绝并提示）。
- `/new`·`/resume` 后面板重臂：`autoStartMonitor` 在 monitor 上下文变化时先停表再重启，修掉"面板永久消失"。
- 跨 key 只读：`dispatch_worker`（显式 `key`）与 `advance_phase` 对另一窗口 live 持有的 key 在**任何副作用之前**拒绝并返回 `[cross-key-read-only]`；读面（`list_tasks scope:"all"/"key"`、`mw_status`、doctor、面板）保持全局只读。
- `worker-store` 行格局可识别（G5）：7..9 列全可读、不可解析行计数与告警、回写不删行、新队列带 `# mw-queue:v2` 头。

**`### Fixed`（两包各自合适的包）**
- 闸门可静默数十天无人知（pending gate 无提醒）。
- L3 流中止与"无裁决"混判（中止被当成可疑裁决源）。
- gate 自由文本 `note` 被当成 AC/VC 改写授权。
- `/mw restart` 后 monitor 面板冻结在旧帧却显示新 PID、不报错、不自证过期。
- `/new`·`/resume` 后 `/autopilot monitor` 面板永久消失。
- 队列行被静默丢弃导致全项目队列重建（IN-3：解析器丢 9 列行 + 整表重写 ⇒ 250 行全量重派）。

**`### Changed`**
- 配置键 14 → 20（上列 6 键，全部带范围校验与冻结语料 73 例）。

> 注：**不要**编造 issue/PR 编号。仅当确有关联 issue 时才用 `([#N](...))` 形式；本 key 来自外部 reflect 台账与用户要求，无编号。

### 2. 全量回归 + 基线对照（写进 `verify-closure.md`）
- Python：`cd packages/multi-workers && python -X utf8 -m pytest -q -p no:randomly`（全量；预期 **2 failed**，即 `verify-baseline.md` 里记录的两条既有红，逐字比对；新增红必须为 0）。
- TS：本次 key 触达的全部 suite 一次性跑（用 `node ../../node_modules/vitest/dist/cli.js --run <files>`，从 `packages/coding-agent` 运行）。至少含：
  `test/suite/worker-store.test.ts`、`run-store.test.ts`、`worker-dispatch-guard.test.ts`、`worker-run-identity.test.ts`、`worker-crosskey-readonly.test.ts`、`autopilot-monitor.test.ts`、`autopilot-console.test.ts`、`autopilot-gate-presentation.test.ts`、`autopilot-event-parity.test.ts`、`autopilot-config-sync.test.ts`、`autopilot-config-parity.test.ts`、`test/extensions/agent-team-loop.test.ts`、`test/extensions/agent-team-loop-pm-state-sync.test.ts`。
- `npm run check`（全量输出；若 biome 报 "No fixes applied" 则记录；**不要**用 `--write` 之外的手段去动别人的文件）。
- `./test.sh`：**本机不可运行**（`bash.exe` = 无发行版的 WSL）。在回执里如实记录这条环境限制，并说明以「Python 全量 pytest + 上列 TS suite 集」作为等价替代（AGENTS.md 口径：非 e2e）。
- 基线对照表：`verify-baseline.md` 的红集合 vs 收口红集合，**逐项列名**，新增红必须为空。

### 3. 文档同步（只做必要项，不做大改）
- 若 `packages/multi-workers/README.md` 里有需要同步的 **autopilot / doctor / config 键** 说明（例如配置键表、`mw autopilot` 子命令表），补上本 key 的新键与新子命令（`contract-guard` / `contract-freeze`）；**找不到对应位置就不改**，并在回执里说明。
- **不要**改 `spec.md`/`design.md`/`plan.md`（PM 已同步）。

### 4. `runtime-cutover-runbook.md`（新文件；只写文档，不执行）
内容（逐条写清命令、前置、验证、回滚）：
1. 前置：`git status` 快照；确认写面无其它会话在飞；确认 `.agenticdoc/_workers.parallel` 已归一到 8 列（PM 提供的 `evidence/scripts/t23-normalize-whole-queue.py`）。
2. 构建与安装：`mw build --install --allow-dirty`（内部会跑仓根 `npm run build`）+ 说明它把 bundle 装到 `~/.pi/agent/extensions/agent-team-loop.js`（当前该文件仍是 **10-10 10:53:02** 的旧构建）。
3. 重启：`mw serve` 的 launcher/serve 进程重启；**并列出 9 个 pre-10:53 的 pi 窗口 PID**（这些窗口的 in-memory 解析器是 pre-`b8bc115ff`，必须重启才能消除 9 列行被丢弃的 IN-3 复现条件；PID 列从 `Get-Process node` + `trace.log` 现场取，写进 runbook 时标注"取数时刻"）。
4. 验证：切换后立刻跑 `mw doctor --json`（`rows_total`/`non_terminal`/`unparsable`/`version`/`issues`）+ 一次 `dispatch_worker`（确认新 row 带 `run.json` 身份 + 队列不再被翻成 9 列）。
5. 回滚：如何退回旧 bundle（备份 `agent-team-loop.js` 的路径与文件名）+ 队列归 Normalize 脚本。
6. **明确写：本 runbook 由用户批准后由 PM 执行；本卡不执行。**

## 契约（不得重定义）

- **不**运行 `npm run build` / `mw build` / `mw build --install`；**不**重启任何进程；**不** kill 进程。
- 不修改已发布版本小节（`## [0.x.y]` 一律不动）；只追加 `## [Unreleased]`。
- 不 commit；不 `git add -A`；不 `git stash/reset/checkout/clean`。
- 测试一律具体文件口径（见上）；不跑全量 vitest（含 e2e）。

## [VERIFY]

- `npm run check`（全量输出追加进回执）
- `cd packages/multi-workers && python -X utf8 -m pytest -q -p no:randomly`（全量，贴末 5 行）
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run <上列 TS suite 全集>`
- `git diff --stat -- packages/multi-workers/CHANGELOG.md packages/coding-agent/CHANGELOG.md`

## 非空洞对照（必须附在回执里）

- 基线对照表（新增红 = 0 的逐项证据）。
- CHANGELOG 对照：给出追加前后 `## [Unreleased]` 的行数增量 + 新增条目的首 40 字（证明未动既有条目、未重复小节）。
- runbook 的自检：把它交给一个"没参与本 key 的人"能照做的判据——每条命令都必须是**可复制粘贴且带路径**的；在回执里列出你实际核对过的命令条数。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t16-docs-closure/report.md`，写完**立刻**复制到 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-16-docs-closure-report.md`。
