# T-16 docs-closure 回执（mwg-t16-docs-closure）

## 结论

T-16 收口完成：两包 CHANGELOG 仅在 `[Unreleased]` 追加（28 行全增不删）、README 补 6 新配置键 + G3 子命令、`verify-closure.md` 全量回归对照（Python `2 failed/1523 passed` 红集合与基线逐项一致，新增红=0；TS `13 files/340 tests` 全绿；`npm run check` exit 0 无 biome 改写）、`runtime-cutover-runbook.md` 30 条可复制命令（**未执行切换**）。

## 1. 卡范围变更（写进回执，按 task.md 要求）

PM 2026-10-10 19:10 决定：本卡**不重建 dist / 不跑 `npm run build` / 不安装、不重启**，改为产出切换 runbook。三条理由：

1. **AGENTS.md 硬规则**：`npm run build` 只在用户明确要求时才可执行；而运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）仍在等用户拍板（pm-state「待用户决定 ①」）。未获批就重建/安装 = 单方面改变全项目运行时行为。
2. **多会话 cwd 风险**：`packages/coding-agent/dist/**` 是版本控制产物，多会话同 cwd 下重建会夹带其它会话未提交的 `src` 改动。实测 `_BUILD_DIRTY_PATHS=["packages/coding-agent/src"]` 当前为脏；现场 `packages/coding-agent/dist/extensions/agent-team-loop.js` **不存在**，全局 bundle 为旧构建。
3. **IN-3 复现条件**：9 个 pre-10:53 pi 窗口的 in-memory 解析器是 pre-`b8bc115ff`（只认 7..8 列），新产物写 9 列 ⇒ 旧窗口把 9 列行当不可解析 ⇒ 整表重写 + 全量重派。

⇒ 卡改名 `docs-closure`：产出 `runtime-cutover-runbook.md`（只写不执行）。

## 2. 交付物

### 2.1 CHANGELOG（`## [Unreleased]` 内既有小节追加，全增不删）

`git diff --numstat`：`13 0 packages/coding-agent/CHANGELOG.md`、`15 0 packages/multi-workers/CHANGELOG.md`。

**对照（证明未动既有条目、未重复小节）**

| 文件 | `[Unreleased]` 追加前行数 | 追加后行数 | 增量 | 新增小节 |
|---|---|---|---|---|
| `packages/multi-workers/CHANGELOG.md` | 119 | 134 | **+15** | 0（复用既有 `### Added` / `### Changed` / `### Fixed`） |
| `packages/coding-agent/CHANGELOG.md` | 224 | 237 | **+13** | 0（复用既有 `### Added` / `### Changed` / `### Fixed`） |

- 交付前已通读两文件 `[Unreleased]` 全文；`git diff -U0` 的 `-` 行数 = **0**（无任何既有条目被改/删）。
- coding-agent 的 Unreleased 有**两个** `### Added`；新增条目落在**第一个**（本周期新增段，与 `mw-autopilot-slot-capacity` 等条目同段），第二个旧式 `### Added` 未动。
- **未编造 issue/PR 编号**：所有新条目无 `([#N](...))`（本 key 来自外部 reflect 台账与用户要求，无编号）。

新增条目首 40 字（逐一列出，`...` 为截断）：

multi-workers：
1. `- Added the `l3-aborted` abort fingerprint (` / 卡条：`l3-aborted` 中止指纹
2. `- Added the pending-gate proactive reminder `
3. `- Added the G3 gate authorization scope (mw-gate-verd`
4. `- Added queue integrity (G5) (mw-gate-verdict-hardening`
5. `- Added the launcher bounded spawn (G5) (mw-gate-verdi`
6. `- Added dispatch isolation and run identity (G6) (mw-ga`
7. `- Added six autopilot config keys (mw-gate-verdict-hard`
8. `- Changed the autopilot config key count from 14 to 20 `
9. `- Fixed 闸门可静默数十天无人知（pending gate 无提醒）...`
10. `- Fixed L3 流中止与"无裁决"混判（中止被当成可疑裁决源）...`
11. `- Fixed gate 自由文本 `note` 被当成 AC/VC 改写授权 ...`
12. `- Fixed 队列行被静默丢弃导致全项目队列重建（IN-3...`

coding-agent：
1. `- Added panel frame self-proof and degraded frames (G4`
2. `- Added the panel not lying before a human answers (G2)`
3. `- Added `/autopilot gate <id> approve|reject --authori`
4. `- Added panel re-arm after `/new`·`/resume` (mw-gate-v`
5. `- Added cross-key read-only (mw-gate-verdict-hardening)`
6. `- Added `worker-store` row-shape recognition (G5) (mw-g`
7. `- Changed the extension-side config key count from 14 `
8. `- Fixed `/mw restart` 后 monitor 面板冻结在旧帧却显示新 PI...`
9. `- Fixed `/new`·`/resume` 后 `/autopilot monitor` 面板永久消...`
10. `- Fixed 队列行被静默丢弃导致全项目队列重建（IN-3...`

### 2.2 全量回归 + 基线对照

证据：`evidence/runs/verify-closure.md`。

| VERIFY | 命令 | 结果 |
|---|---|---|
| 1 | `npm run check`（全量） | **exit 0**；`Checked 1110 files in 589ms. No fixes applied.`（biome 未改写任何文件） |
| 2 | `cd packages/multi-workers; python -X utf8 -m pytest -q -p no:randomly` | **2 failed, 1523 passed, 10 deselected, 162 warnings in 192.74s** |
| 3 | `cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run <13 files>` | **Test Files 13 passed (13) / Tests 340 passed (340)** |
| 4 | `git diff --stat -- <两 CHANGELOG>` | 13 + 15 = **28 insertions(+), 0 deletions(-)** |

**基线对照表（新增红 = 0，逐项）**

| 基线红（`verify-baseline.md`） | 收口实测 | 判定 |
|---|---|---|
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（`219ed809…` vs `6be60fe5…`） | 同名同 hash 对 | 既有红，未扩散 |
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`（`3 in [2]`，真实语料 fixture） | 同名同 fixture | 既有红，未扩散 |

口径差异（非回归）：基线只跑 `34 × test_autopilot_*.py + test_doctor_gates.py`（`2 failed/655 passed/8 deselected`）；本卡按卡跑**全量**（`2 failed/1523 passed/10 deselected`）。failed 集合逐字一致，passed/warnings 因选择面扩大而增大。

`./test.sh` **本机不可运行**（`bash.exe` = WSL 且「没有已安装的分发版」，`wsl -l -v` rc=0xFFFFFFFF）。已如实记录，并以「Python 全量 pytest + §3 的 13 个 TS suite 全集」作为非 e2e 等价替代口径。

### 2.3 文档同步（README）

`packages/multi-workers/README.md` 确有 autopilot 配置键表 ⇒ 做了最小追加（`10 0`，全增）：

- 配置键表补 6 行：`launcher_max_workers=8 (1..64)` / `dispatch_max_per_scan=3 (1..64)` / `queue_alarm_delta=50 (10..10000)` / `l3_abort_retry_limit=1 (0..10)` / `gate_reminder_after_min=30 (1..1440)` / `gate_reminder_max=2 (1..2)`（默认值/范围实测自 `autopilot/config.py::DEFAULT_CONFIG` + `_INT_RANGES`，`len(DEFAULT_CONFIG)==20`）。
- 新增 `### G3 契约闸门（mw-gate-verdict-hardening）` 小节，记录 `mw autopilot contract-guard`（只读判定）与 `mw autopilot contract-freeze`（`--block ac|vc|all` / `--force` / `--json`）。
- 未改 `spec.md` / `design.md` / `plan.md`。
- README 行尾保持 CRLF（407→407，CR-only=0）。

### 2.4 `runtime-cutover-runbook.md`（新文件，只写不执行）

内容齐全：§0 运行时现状快照（含全局 bundle 实测 mtime `2026-10-10 11:40:42`、serve PID 14240、launcher PID 4756、队列 270 行全 8 列）、§0.1 9 个 pre-10:53 窗口 PID（现场取数、标注取数时刻与交叉核对来源）、§1 前置（git 快照 + 队列归一 + 备份）、§2 `mw build --install --allow-dirty`（含其内部 `npm run build` 与 `_BUILD_DIRTY_PATHS` 脏树门禁）、§3 serve/launcher + 9 窗口重启、§4 切换后验证（`mw doctor --json` 字段路径表 + 一次派发确认 `run.json`）、§5 回滚（备份 bundle 路径 + 归一脚本）、§6 明确「由用户批准后由 PM 执行；本卡不执行」。

**runbook 自检**：所有命令都带完整路径 / `cd H:\git\Multi-Workers`，可复制粘贴；实测核对条数 = **30 条**（与 runbook §6 的自检分解一致：§0.1 取数 1 + §1.1 快照 4 + §1.2 检查 1 + 归一 1 + §1.3 备份 4 + §2 构建 1 + §3.1 服务 7 + §3.2 取数 1 + §4.1 验证 2 + §4.2 派发核对 4 + §5.1 回滚 3 + §5.2 队列 1 = 30）。

## 3. 硬规则遵守

- 未跑 `npm run build` / `mw build` / `mw build --install`；未重启、未 kill 任何进程。
- 未 commit；未 `git add -A/.`、未 `checkout/stash/reset/clean`。
- 未碰 `.agenticdoc/_workers.parallel` / `_workers.acked`（只读采样，写入面为 0：队列 mtime 在采样前后由 launcher 自身推进，本卡无写）。
- 未跑全量 vitest（含 e2e）；TS 只用卡内具体文件命令。
- 写面仅：两 CHANGELOG、multi-workers README、三个 `evidence/runs/*` 新文件、本报告。
- `git status` 复核：本卡新增的 `M` 就是这三个文档，无其它文件被 biome/脚本误改。

## 4. 风险 / 备注

- **运行时是旧副本**：全局 bundle 是旧构建、常驻 launcher 是进程内旧代码；本报告结论只以本卡自跑输出为准，未依赖 worker 终态回读。
- **bundle mtime 与 PM 记录不一致**：PM 记「10-10 10:53:02」，现场实测 **11:40:42**；runbook 已标注「以现场实测为准，执行前重取」。
- **`packages/coding-agent/dist/extensions/agent-team-loop.js` 当前不存在**：执行切换时 `mw build` 会（重新）生成它；runbook 已写明。
- 未执行切换 ⇒ G1–G6 的运行时效果尚未生效（需用户批准后按 runbook 执行）。
