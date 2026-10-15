# PM State: mw-worker-output-contract

## 1. Snapshot
- Key: mw-worker-output-contract
- Claim-Id: WENBOZHOU-PC4:49268
- Phase: DONE
- Next Action: —
- Started: 2026-10-14 10:34
- Updated: 2026-10-15 15:10
- Completed: 2026-10-15 15:10

## 2. Task Status

| ID | 任务 | 批次 | 状态 | worker 任务键 | AC |
|---|---|---|---|---|---|
| T-01 | 写面单一真源（W1） | A | **done（PM 复核通过；壳层适配层缺口转 T-10）** | `woc-t01-write-surface` | AC-006/007(a)/016 |
| T-02 | 账本抽取器加固（W3） | B | **done（PM 复核通过；NC 为框架误红，已转 T-11）** | `woc-t02-ledger` | AC-008/017 |
| T-03 | 回读推送域（W5） | A | **done（PM 复核通过）** | `woc-t03-readback` | AC-011/012/013 |
| T-04 | 检查点 `landed`（W4） | B | **done（PM 复核：基线全符；但发现 1 例非确定性缺陷 ⇒ 转 T-12）** | `woc-t04-checkpoint` | AC-009 |
| T-05 | 契约判定 + 候选集 + 补齐（W2） | B | **done（PM 复核通过；两处收窄偏差待裁决 D-015）** | `woc-t05-contract` | AC-001…005/010/014/015 |
| T-06 | S2 清单注入（Python） | A | **done（PM 复核通过；AC-003 真实任务侧待 T-08 复跑）** | `woc-t06-s2-sections` | AC-002/003 |
| T-07 | 跨任务矩阵 + 基线区分 | C | **done（PM 复核通过）** | `woc-t07-matrix` | AC-005/010/017 |
| T-13 | 自检回合改「已交付」+ TS 侧 S2 全角色注入（D-015 选项 C） | B‴ | **done（PM 直执完成，复核通过）** | `woc-t13-selfcheck-r2` | AC-003/004 |
| T-08 | 部署与生效 + AC-010(b) | C | **done（PM 直执，全部通过）** | — | AC-010(b) |
| T-09 | 结案（PM 直执） | C | **done（PASS）** | — | 全 AC 勾销 |
| T-10 | 壳层守卫 + `write_scope` 解析收敛（补 T-01 缺口） | B′ | **done（PM 复核通过）** | `woc-t10-shell-guard` | AC-016 |
| T-11 | 账本声明区标题识别误取正文（误红） | B′ | **done（PM 复核通过；NC 同为框架误红）** | `woc-t11-ledger-heading` | AC-010(b) 前置 |
| T-12 | `landed` 未来 mtime 上界：跳过→钳制（修 T-04 非确定性） | B″ | **done（PM 复核：21/21 + 自跑 8 次全绿）** | `woc-t12-landed-clamp` | AC-009 前置 |

卡文件：`tasks/T-01-write-surface-single-source.md` … `tasks/T-09-closure.md`（9 张，逐张过 `inspect_envelope` + `type_extras_missing` + seed 最小项，全部 `missing=[]`）。

## 3. Evidence Ledger

- 2026-10-14 **T-05（`woc-t05-contract`，coding，done，exit=0，19 分钟，152 次工具调用）**：契约判定 H2 档 + 受判候选集 + 机械段补齐 —— `worker/output-sections.ts`（`h2Headings` 归一化判定 + 围栏/引用块排除 + `MECHANICAL_SECTIONS` 白名单 + AC-014 注释更正）、`worker/output-writer.ts`（`judgedProductFile` 候选集 `report.md → report-<slug>.md(mtime 降序) → output.md` + `hasReportProduct` 第二入口 + `appendMechanicalContextSources`）、`worker/worker-mode.ts`（**仅 settle 段**：`judgeRecoveryHere`/`judgedType`、`finishSuccess` 先补齐后判定、`settleOrSelfCheck`）、`pm/ui-bridge.ts`（S2 清单渲染 + `CardSections.type`）+ 新套件 `mwoc-w2-contract-judgment.test.ts`（40 例）。
  **PM 独立复核（重跑）**：新套件 **40/40**；`output-recovery-contract` **14/14**、`dispatch-recovery-terminal` **16/16**、`dispatch-card-injection` **18/18**、`mwds-t03` **63/63**、`mwds-t02` **38/39**、`agent-team-loop` **196/197**、`worker-file-tool` **7/9**、`npx tsgo --noEmit` = **0** ⇒ 全部为 DR6 登记的 HEAD 既存红，**零新增红**。
  **PM 重跑复现的关键证据**：AC-001 8 例矩阵逐例与声明一致（含「仅正文含别名而无标题 ⇒ 5 段全缺」= FW-001 自证漏洞关闭）；AC-005 三例**盘上真实历史产物**重放 `exit=2 → exit=0`（`mdc-rq1-dispatch-chain`、`mwgf-drq3-role-key-design`、`mvr-rq5-awareness-surface`）；AC-015 第二入口让 slug-only coding 从「根本不判」变为 `missing=改动清单`。
  **R8 预告的 3 处 settle 层改动未发生** ⇒ 见 D-015（两处实现收窄）。
  **残留**：AC-010(a) 语料 n=463（`tierA 178/463=38.4%`、`tierB 63/463=13.6%`，before 基线 145/433、35/433）已落 `evidence/woc-t05-corpus-after-20261014.txt`；`class=mechanical-only` 在 H2 档下从 8 例收敛为 5 例（另 3 例转为实质缺段，S3 救不回），已在重放选择里如实声明。

- 2026-10-14 **T-12（`woc-t12-landed-clamp`，coding，done，exit=0，3 分钟）**：`landed` 上界由「跳过未来 mtime」改为「钳到 `nowMs`（age=0）」—— `worker/worker-mode.ts` **仅两处**（`newestEvidenceMtimeMs` 证据遍历、`collectLandingSignals` 目标统计；保留 `size===0` 与 `startedAtMs` 下界）+ 新套件用例 19 → **21**。
  **PM 独立复核（重跑）**：新套件 **21/21**，且 PM **自跑 8 次连续重跑全绿**（修复前 PM 实测 1/6 非确定红）；`change-ledger` **12/12**、`checkpoint-wiring` **10/10**、`agent-team-loop` **196/197**（`T-17/B-1` HEAD 既存）、`mwds-t03` **63/63**、`mwds-t04` **19** + `t05` **11** + `t06` **9** + `t12-regression` **11** = **50/50**、`npx tsgo --noEmit` = **0**。
  **确定性复现证据（采信）**：worker 先用显式 `nowMs = mtime - 1` 把偶发变成 **100% 可复现**的反例（修复前 `expected undefined to be +0`，修后 `age=0 artifact=true`），再把原失败用例改为显式时钟（`startedAtMs = mtime - 60_000`、`nowMs = mtime + 100`）消除 NTFS 粒度竞态。PM 读源码确认两处钳制写法与本条一致。
  **刻意接受的语义变化（登记为已知限制，交 T-09）**：`wjg-w12` 重放的 `last_land` 由 `83s` 变为 `0s`（`progress.md` 的 mtime 晚于被 pin 的历史检查点时刻 18s，钳制后计为「刚落地」）；`risk` 结论不变（仍 `low`），测试未改任何期望值来掩盖。取舍：钳制修掉了真实现场的时钟粒度非确定性，代价是**重放**场景把「检查点之后才发生的追加」计到检查点时刻上（重放本就非严格时间点重建）。
  **遗留格式债（登记，交收口 scoped 处理）**：PM 自行跑 `npx biome check`（scoped，非被禁的仓级 `npm run check`）确认我们这两个文件仍有 **3 个 format 错误**（import 排序 + 若干长行），T-10/T-04/T-12 各自引入一部分；worker 自述「不在本卡新增行上」**不完全准确**（其中至少一处是它重写过的长行）。收口时用 **scoped `npx biome check --write <仅本 key 改动文件>`** 清理，绝不跑仓级命令。

- 2026-10-14 **T-04（`woc-t04-checkpoint`，coding，done，exit=0）**：检查点 `landed` 信号 —— 走「改判据」路线（不动 `writes` 计数入参，避免与 T-02 账本语义/parity 锁分叉）—— `shared/heartbeat.ts`（+26/−2：`CheckpointInfo` 追加可选 `land`/`lastLandingS`/`artifactPresent`/`progressDone`，`CHECKPOINT_LINE_RE` 加**单个可选非捕获组**）+ `worker/worker-mode.ts`（**仅检查点段**：`collectLandingSignals` 与 `parseWriteFileEvents` 同源、`computeRisk` 新增 writeless 分支且 `landed === undefined` 时原三支逐字节不变、`writeCheckpoint` 仅 writeless 追尾字段行、不新增 trace 行）+ 新套件 `test/suite/mwoc-w4-checkpoint-invariants.test.ts`。
  **PM 独立复核（重跑）**：`change-ledger` **12/12**、`agent-team-loop-checkpoint-wiring` **10/10**、`mwds-t03` **63/63**、`mwds-t04` **19** + `mwds-t05` **11** + `mwds-t06` **9** + `mwds-t12-regression` **11** = **50/50**、`agent-team-loop` **196/197**（红 = `T-17/B-1 anchor integrity`，HEAD 既存）、`npx tsgo --noEmit` = **0**。⇒ 基线逐项符合，零新增红。
  **AC-009 实测（PM 重跑原样复现）**：真实 `wjg-w12` 重放 `risk=mid → low land=2 last_land=83s artifact=yes done=yes`；零落盘负例 → `risk=high land=0 artifact=no done=no`；I3 三例（活跃无 `[TIMEOUT]`、真挂死 `exit=1 idle: no activity for 60s`、尾段 `checkpoint < deadline` 后 `wall: budget 180s exceeded`）均不吃 `risk`。
  **PM 发现的非确定性缺陷（转 T-12）**：新套件连续 6 次单文件重跑，第 2 次 `1 failed | 18 passed`（其余 19 passed）——失败用例 `collectLandingSignals … dedups repeated targets…`（`test/suite/mwoc-w4-checkpoint-invariants.test.ts:238`）报 `expected undefined to be defined`。PM 定位：`worker/worker-mode.ts:402` 与 `collectLandingSignals` 对**未来 mtime** 采取「跳过」（`mtimeMs > nowMs ⇒ continue`），而测试在写盘后立刻取 `nowMs: Date.now()`（`:233`）——Windows NTFS 粒度可落在 `Date.now()` 之后几毫秒，刚落地文件被丢弃 ⇒ `lastLandingAgeMs` 未定义。判为 T-04 交付内缺陷（信号更悲观且重放判据不可复现），正确处置为**钳制**。⇒ 新建 **T-12**，先于 T-05 串行执行。
  **残留（已转 T-05/收口）**：DR4 §5 的 writeless steer 文案更新不在 T-04 卡内要求且写面限检查点段（`checkpointSteerText` 为独立渲染函数），留待 T-05/收口；真实语料仅 `wjg-w12` 一例可重放（其余 5 例运行时长 < 30m 锚点）。

- 2026-10-14 **T-10（`woc-t10-shell-guard`，coding，done，exit=0）**：壳层守卫允许面 + `write_scope` 解析收敛到写面单一真源（**T-01 缺口 3/3 补齐**，`design.md` §3.1 三适配层全收敛）—— `shared/write-surface.ts`（新增 `EvidenceBasis`/`evidenceDirOf`/`resolveOwnWriteTarget`，导出唯一 `matchesWriteScopeEntry`）+ `worker/worker-mode.ts`（**仅**壳层守卫段 + `parseTaskMeta` 的 `write_scope` 行 + 导入；删除本地 `matchesWriteScopeEntry`、`GLOB_MAGIC_RE`、`minimatch` 导入）+ 新套件 `test/suite/mwoc-w10-shell-guard-parity.test.ts`（8 用例）。
  **PM 独立复核（重跑）**：新套件 **8/8**（`parity cases=14 mismatches=0`、`DR1 shell_blocked=true`、`out_of_surface 3/3 blocked`、`deny shared_rules=5 matched=5 packages_writeless=deny packages_writable=allow`、`write_scope one_impl=true`）；基线逐项一致 `mwds-t03` **63/63**、`write-face-runtime` **18/18**、`mwds-t02-write-intent` **38/39**（红 = AC-005a 语料回放，HEAD 既存）、`agent-team-loop-worker-file-tool` **7/9**（红 = VC-005 / slug 边界，HEAD 既存）、`change-ledger` **12/12**、`mwoc-w1-write-surface` **13/13**；`npx tsgo --noEmit` = **0**。⇒ 零新增红。
  **单一实现复现（PM 重跑 rg）**：`startsWith("write_scope:")` 全 `src` 命中 **1 处**（`shared/write-surface.ts:264`）；`matchesWriteScopeEntry` 定义 **1 处**（`write-surface.ts:292`），消费者 = `worker-mode.ts:2141`（壳层）、`write-surface.ts:314`（自用）、`worker-file-tool.ts`（经 `parseWriteScopeHeader`）；`worker-mode.ts` 内三者 **均无残留**（rg exit=1）。
  **DR1 例外保持未被抹平**：壳层 `evidence/x.md`（keyDir 相对、cwd 解析）继续 fail-closed（`rule=scope`），派发期谓词与 `worker_file` 双基准接受；裸 basename（`report.md`/`progress.md`/`report-abc.md`）同因在壳层被挡。刻意保留的 `bashWriteDenyReason` 仅剩 `packages/**` 的角色分类差异（writeless 拒 / writable 放行），5 条共用规则逐条比对 `detail === denied:<pmWriteDenyReason>`。
  **残留（已登记，不阻断）**：`agent-team-loop.test.ts:6381`（`mw-guard-form-hardening` 锚表）仍为 HEAD 既存红（1/197 不变），本卡行位移会改变其中已陈旧行的失配集合但不新增失败用例。
  **PM 直执小修（同 phase，trivial 文档纠正）**：`shared/write-face.ts:14` 注释仍引用已删除的 `worker/worker-mode.ts:matchesWriteScopeEntry` —— PM 直接改为 `shared/write-surface.ts:matchesWriteScopeEntry`（注释行，无代码/行为变更；该文件在本卡写面之外，故由 PM 处理）。

- 2026-10-14 **T-11（`woc-t11-ledger-heading`，coding，done；终态 `needs-clarification` 同为框架误红，已由本卡修复）**：账本声明区标题识别修复 —— `shared/change-ledger.ts` 仅标题识别 3 个 hunk（`HEADING_RE` 捕获级别、新增 `HEADING_PREFIX_RE`/`TITLE_CLAUSE_RE`/`asciiLower`、重写 `isLedgerHeading`）+ 新套件 `test/suite/mwoc-w11-ledger-heading-scope.test.ts`（6 用例）。
  **PM 独立复核（重跑）**：`mwoc-w11` **6/6**；卡列 5 套零回归 `change-ledger` **12/12**、`mwgal-t17b` **16/16**、`mwgal-t17c` **15/15**、`mwds-t21` **13/13**、`mwoc-w3` **21/21**；相邻锁定 `mwgal-t17-role-aware` **15/15**、`mwgal-t21-qg-fixes` **19/19**。
  **PM 独立复现（直调 `diffLedger`，非采信自报）**：对真实 `workers/woc-t02-ledger/{output.md,trace.log}` 现得 `extra=[]`（`declared` = 其真实 3 个已记录文件）；仅保留头部（H1 + `card:` 行 + `目标锚点：.agenticdoc/goal.md`）的夹具 `declared` **不再含**卡路径与 `goal.md`。⇒ 真实事件误红已消除。
  **diff 边界复核**：`git diff -U0` 显示该文件 6 个 hunk 中仅 3 个属于本卡（`@@ -339,2 +413,20`、`@@ -341,0 +434,10`、`@@ -345,2 +447,8`，均在 `HEADING_RE`/`isLedgerHeading` 区），另 2 个是 T-02 的导出与 `unjudgeable` 派生；`extractLedgerBody`/`collectDeclared`/`diffLedger` 语义未动。
  **显式偏差（PM 核实并采信）**：卡要求 2 的字面「标题必须以别名开头」与卡自己的不回归清单矛盾 —— 4 个受保护套件（`mwgal-t17b:422`、`mwgal-t17c:365`、`mwgal-t17-role-aware:98`、`mwgal-t21-qg-fixes:238`）内嵌的 T-08 语料标题 `### 结论 6｜可度量：改动前后的期望变化与运行期验收数字`，别名 `改动` 在 `：` 之后的**子句**开头；字面实现会把四套全判红。故实际规则 = 「标题本身或其 `：`/`｜`/`|` 子句开头」。PM 核实：`change-ledger.ts:278` 的 T-21 注释早已记录同一语料，子句语意是既有意图。**残留风险（供 T-09 登记）**：`…：变更xx` 形的子句仍会命中，属刻意保留的偏松面。
  **重要落地条件（写入 AC-010(b) 验证前提）**：settle 判官在 **worker 进程内**模块加载时绑定，**修复对开工早于本改动的进程不生效** —— T-11 自己的终态回读仍报同一误红（`unrecorded write(s): T-11 卡, .agenticdoc/goal.md`），即是旧判官在内存中的实证。⇒ AC-010(b) 的「≥6 新 worker 全 exit=0」必须在 **T-08 部署（`mw stop`/`mw start`）之后**重跑，否则依旧会看到该误红。

- 2026-10-14 **T-02（`woc-t02-ledger`，coding，done；终态 `needs-clarification` 系统框架误红，非交付问题）**：账本抽取器加固 —— `shared/change-ledger.ts`（+82）+ `worker/worker-mode.ts`（抽取器段 + 记账段）+ 新套件 `test/suite/mwoc-w3-ledger-extractor.test.ts`（21 用例）。
  **PM 独立复核（重跑）**：新套件 **21/21 绿**；既有套件零新增红：`change-ledger` **12/12**、`agent-team-loop-checkpoint-wiring` **10/10**、`mwds-t03-bash-write-scope` **63/63**、`mwgal-t17b-ledger-infra-writes` **16/16**、`mwgal-t17c-ledger-unresolvable` **15/15**。
  **三条数据流约束落地（读 diff + 采信实测）**：`stripDataRegions`（here-string + heredoc 体）在词法前调用；目标只取自写动词目标位（`net-file-api` 新增分支 + 字面量值环境解析）；未解析落 `[WRITE_UNRESOLVED]`（新导出 `parseUnresolvedWriteEvents`），`unjudgeable` 改由「可用事件数为零」派生（`usableEvents.length === 0 && delivered.length === 0`）。`BashWriteCandidate` 形状与 `readTerminalGaps.ok` 公式不变；41 label 全保留 + 1 新增。
  **偏差（已采信）**：DR3 §4.2 拟加的 `ChangeLedger.unresolved` 字段未加 —— `change-ledger.test.ts` 对 `diffLedger` 返回值做整对象 `toEqual` 而该测试文件不在本卡写面，加字段即回归；改用同源兄弟 API。
  **NC 根因（PM 已复现定位，可复跑）**：`shared/change-ledger.ts:416 isLedgerHeading` 用 `includes` + `#{1,6}` ⇒ worker 的 `output.md` **H1** `# T-02 · 变更账本…` 命中别名 `变更`，`:426 extractLedgerBody` 便把 H1 之后的头部区（`card:` 行、`目标锚点：.agenticdoc/goal.md`）当成「改动清单」正文 ⇒ `declared=[卡, goal.md]`、`extra` 非空。PM 用 `diffLedger` 直调验证：仅把 H1 换成中性标题 ⇒ `declared=[] extra=[]`。两文件实际均**未被写过**（`goal.md` mtime 停在 2026-09-09）。⇒ 新建 **T-11** 修此误红（否则卡住 **AC-010(b)** 的「≥6 新 worker 全 exit=0」）。
  **写面边界复核**：T-02 未触碰检查点段/settle 段；`worker-mode.ts` 工作树 diff 叠加了 `mw-write-face-guard` 已 DONE 的未提交改动（开工前 mtime 18:21，非 live 写者），全量符号锚定。

- 2026-10-14 **T-01（`woc-t01-write-surface`，coding，done）**：新建 `shared/write-surface.ts`（416 行）+ 三个薄适配（`pm/ui-bridge.ts` -148/+、`worker/worker-file-tool.ts`、`shared/deliverable-evidence.ts`）+ 新测试 `test/suite/mwoc-w1-write-surface.test.ts`（330 行 / 13 用例）。
  **PM 独立复核（重跑）**：新测试 **13/13 绿**；既有套件与 HEAD 基线**逐项一致、零新增红**：`mwds-t03-bash-write-scope` **63/63**、`write-face-runtime` **18/18**、`mwds-t02-write-intent` **1 failed / 38 passed**（既存红 `wjg-qg-evidence-closure`）、`agent-team-loop-worker-file-tool` **2 failed / 7 passed**（HEAD 2 红）。
  **PM 读源码确认**：`WORKER_FILE_NAME_RE` 全仓**仅一处定义**（`shared/write-surface.ts:54`）；`pm/ui-bridge.ts` 与 `worker/worker-file-tool.ts` 均从该模块导入同一谓词 `judgeWriteTarget`（`shared/write-surface.ts:349`）；`deliverable-evidence.ts` 改从新模块导入（去掉反向依赖）。
  **未闭合缺口（转 T-10，D-010）**：`design.md` §3.1 的**三个**适配层只完成 2/3 —— 壳层守卫 `worker/worker-mode.ts:1669 bashWriteDenyReason` / `:1802 checkBashWriteScopeTarget` 仍自带第二套路径域判定，且 `write_scope:` 存在两份解析（`parseTaskMeta` vs `shared/write-surface.ts:259 parseWriteScopeHeader`）。worker 依卡面「写入禁止面」（`worker-mode.ts` 只读）停手并登记残留，**未越面**——行为正确。

- 2026-10-14 **T-06（`woc-t06-s2-sections`，coding，done）**：生产者侧 S2 清单注入（`autopilot/dispatch.py` +91/-4）+ 新套件 `test_mwoc_s2_sections.py`（373 行 / 17 用例）。
  **PM 独立复核（重跑）**：新套件 **17 passed**；`test_autopilot_dispatch.py + test_task_type_parity.py` = **1 failed / 25 passed**，唯一红 `test_bom_historical_books`（报错为 `mw-dispatch-reliability/workers/mw-dr-glm53/task.md` 缺文件，与本卡改动无关，不读 `dispatch.py`）；`test_mwds_t13_producer_paralysis.py` **18 passed**。
  **PM 读 diff 确认**：`RECOVERY_SECTIONS` / `RECOVERY_TYPE_SECTIONS` / `RECOVERY_CONTRACT_TYPES` / `RECOVERY_CONTRACT_HEADING` + `recovery_sections_for` / `recovery_contract_section`；`_envelope_card_body` 注入前**先算 T-13 extras**（`declared_text` 为未注入前文本）——否则 review 的 `未覆盖面声明` 二者同名会吞掉 fallback 行；幂等守卫用 `RECOVERY_CONTRACT_HEADING not in declared_text`；仅 `coding/research/review` 注入（`vision`/`rag-research`/内部 registry 角色字节不变）。**只改本卡写面**（`dispatch.py` + 新 pytest）。
  **PM 复核单一真源机制**：parity 测试 `_ts_tables()` 解析真实 TS 源（`worker/output-sections.ts`），缺失时 `pytest.fail`（fail-closed），不是硬编码副本对照。
  残留（采信）：AC-003 的「**真实**任务」半边用的是 `dispatch_card`→`render_task_md` 真实调用路径生成到 `tmp_path`（本卡先于 T-08），真实 worker 产物命中 2/2 留 T-07/T-08 复跑。

- 2026-10-14 **T-03（`woc-t03-readback`，coding，done）**：回读推送域重构（`pm/pm-orchestrator.ts` +92/-12）+ 新测试 `test/suite/mwoc-t01-readback-delivery.test.ts`（3 条）+ 探针断言改写。
  **PM 独立复核（重跑）**：新用例 **3/3 绿**（`vitest --run test/suite/mwoc-t01-readback-delivery.test.ts`）；既有 C3 锁用例 `startWorkerPollLoop summary scoping > stays silent without a watched key and for tasks under other keys` **通过**（`-t` 过滤后 2 passed / 195 skipped）；探针 `readback-push-scope-repro-20261014.mts` 实跑 **P1..P6 全 PASS**，其中 `P3 (C1): takeover of keyB replays the un-notified terminal row exactly once (count b1=1, deliveries=1)` 与 `P2 deliveries=0` 成对证明「补推恰好一次且不是取消跨 key 门禁」。
  **PM 读 diff 确认**：模块级注释写清 `notified`（投递水位）/`readbackDelivered`（仅未读数依据）/`AckStore`（处理水位，不参与投递抑制）；终态分支拆为 C3（`!watch.key`：`notified.add` + 静默）与 C1（owner ≠ watch.key：不记账），`notified.add` 落在 owner 门禁之后、`recordWriteScopeResidualRisks` 之前（保住 R5 的每任务一次界）；widget 侧 watched key 追加 `N unread` 尾行、无 watch key 渲染单行计数且 `messages` 不增长。**`pm/ui-bridge.ts` 未被触碰**（保持 T-01 写面独占）。
  残留（worker 自报，采信）：`readbackDelivered` 因写面禁令落在 `startWorkerPollLoop` 局部而非 `PmWatchState`；多窗口去重与 `taskKey+runId` 粒度保留（design R6 已知）。

- 2026-10-14 **design 阶段 6 份研究证据（DR1…DR6，全部 done，PM 逐份复核字节一致）**：见 D-008 的 sha256 与结论索引；DR6 另落 4 份可复跑产物。
  关键实测：DR6 实跑 24 个 vitest 文件 / 558 用例，既存红 **5**（含 `agent-team-loop.test.ts:6381`、`mwds-t23:295`），语料快照 n=437（整篇 34.8% / H2 8.5% / flip 111 = mechanical-only 8 + substantive 103）；DR3 实测 `allow=0 deny=3` 与 `Write-Output a <term> --glob x` 无写 API；DR2 实测 6 例历史实例在新判定下**全部仍 exit=2**、settle 层至少 3 处既有用例需改；DR1 实测 `WORKER_FILE_NAME_RE` 共用点 2 处 + 2 测试；DR4 实测只有 `wjg-w12` 有可重放检查点；DR5 实测既有锁在 `agent-team-loop.test.ts:2079`（行号漂移，须用用例名锚定）。
  四个独立 worker（RQ-2 / RQ-3 / DR2 / DR3）在**各自运行期**都踩到同一个 P4 误拦/误记 bug（heredoc、`node -e`、脚本里的 `>`/`->`、`--glob`）⇒ P4 危害面已从「账本失真」升级为「误拦合法只读命令」。
- 2026-10-14 **RQ-2（`woc-rq2-write-face`，research，done）**：写面三层 + **34 项可直接转 tasks 的改动点**（A1-A16 `worker_file` 通道 / B1-B6 派发期 PM 侧 / C1-C11 测试 / D1 派生产物）。证据 `evidence/research/spec-rq2-write-face-20261014.md`（39,163 B，md5 `24532b4418aa972d8a91705fed48328b`；同 sha256 `ee48eb2745029051…`）+ 任务目录 `report.md`（**字节一致**，PM 复核）。
  **PM 独立复核（读源码）**：`TOOL_ALLOWLISTS` 11 键、5 键无 `write`/`edit`（review/research/verifier/reviewer/rag-research）确认；`activeToolsForType` 为这些角色追加 `worker_file` 确认；**`pm/ui-bridge.ts:1707-1722 judgeWriteTarget` 的允许面确认只有「taskDir」+「无目录成分的白名单 basename」，没有 `evidence/**` 面**，而运行期 `worker-mode.ts:1625-1646` 允许 `taskDir + <key>/evidence` ⇒ **同一路径派发期与运行期判定相反**（RQ-2 语料重放实测：review 卡声明写 `evidence/*.md` 在派发期被判不可满足）。
  **spec 改动**：P2 重写为三层 + 两处判定相矛盾；P4 加「误拦合法写入」实例；AC-006 补 design 待定项（`<key>` 基准、`write_scope` 是否约束 `worker_file`）；AC-007 钉死「文案层级」（pi 核心 `packages/agent/src/agent-loop.ts:611` 的文本**扩展改不了**，`tool_result` 钩子不覆盖 `kind:“immediate”`）；**新增 AC-016**（派发期与运行期写面同源）；§2.4 补 `read-scope.ts`/`agent-loop.ts`/`dispatch.py`；新增 **R7**（工具集 parity 锁 ⇒ 只能加通道不能改表）、**R8**（HEAD 既存红基线：worker-file-tool 7/9、mwds-t02 38/39；change-ledger+checkpoint 22/22、mwds-t03 63/63 全绿）。
- 2026-10-14 **RQ-3（`woc-rq3-ledger`，research，done）**：抽取器全标签枚举 + 伪行最小复现 + 消费者清点 + 形状校验对照。证据 `evidence/research/spec-rq3-ledger-20261014.md`（42,480 B，md5 `30b6708f21dceb59bcc47f948b5e27c2`）+ 任务目录 `report.md`（**字节一致**，PM 复核）。
  **关键结论（PM 采信其可复核部分）**：抽取器唯一实现 `worker-mode.ts:1554 extractBashWriteCandidates`（41 个 pattern 标签）；伪行最小复现 **13 字符**；机制 = here-string 打乱引号配对 + `->` 误当重定向 + 非 `verbatim` 目标被 `:2383-2385` 无条件记账；**遗漏分支** `[System.IO.File]::WriteAllText/AppendAllText`（RQ-1 的 122 条 bash 里 24 条）；RQ-1 的 0 行是「遗漏分支 + 3 条真写被 here-string 正文的 `--glob` 伪目标**误拦**（`allow=0 deny=3`）」双重原因；消费者 6 处**全在 TS**，Python/`mw doctor` **不消费**；`unjudgeable` 只是「零事件」派生布尔（乱码事件即可绕开）；形状校验**只能作辅助**——全仓文件名无异常字符，但正文里有 382/1,720 行反斜杠盘符路径会被现 whitelist 判 `malformed`。
  **spec 改动**：P4 补机制/遗漏分支/误拦/`unjudgeable` 现状；**新增 AC-017**（四段可验证判据：最小复现产 0 行、.NET API 各 1 行、`allow=3 deny=0`、`unjudgeable` 由有效事件数派生且 12 个既有用例不回归）；§2.4 补消费者面与「不涉及 Python 账本逻辑」；新增 **R9**（不能只靠形状加固）。spec 29,221 → **34,907 B**，AC 15 → **17** 条。
  只读边界复核：以 mtime 扫 605 个源文件，两窗口内**唯一**被动过的文件是 `packages/multi-workers/test/fixtures/write-face-corpus.json`（10:52:41，内容自称 `"key": "mw-write-face-guard"`）⇒ 属**另一并行 key** 的产物，非本批 worker 所为（两 worker 均声明 0 改动）。
- 2026-10-14 **RQ-4（`woc-rq4-checkpoint-settle`，research，done）**：检查点生成链 + writeless 落盘信号 + settle 顺序与插入点。证据 `evidence/research/spec-rq4-checkpoint-settle-20261014.md`（32,361 B，sha256 `6febd50cc55660e2…`）+ 任务目录 `report.md`（同字节）。
  **PM 独立复核（读源码）**：`finishSuccess` 内 `hasDeliverableEvidence` → `readTerminalGaps({judgeRecovery: isWritelessRole(type) || reportProduct})` → `exitCode` 在 `writeOutputGuarded` **之前**（「先判后写」确认）；`READ_TOOLS`/`WRITE_TOOLS` 只含 `{read,grep,find,ls,glob}`/`{write,edit}`（`worker-mode.ts:260-262`，`worker_file`/`bash` 不计 ⇒ writeless `writes=0` 恒真，**入参缺陷**）；`computeRisk` 三支（`:283-286`）；`checkpointAnchorMs = min(30m, max(1s, budget/2))`（`:250-252`）；`agentProductText` 只读 `report.md`/`output.md`（`output-writer.ts:140-147`）。
  **spec 改动**：P5 加根因与 `computeRisk` 三支；S3 加顺序约束（I2 = `finishSuccess:2713-2720` 必须早于判定；I1 = `agent_settled:2811-2822`）；S5 加两条修法路径与「不得触碰 idle/墙钟」硬约束；AC-005 加「自动插入须落进最终文件、判定与产物一致」；AC-009 加根因与 3 例不回归验证；**新增 AC-015**（`report-<slug>.md` 可写但不受判的候选集缺口，本仓 QG 即此形态）；§2.4 补 `deliverable-evidence.ts`/`heartbeat.ts`。spec 26,422 → **29,221 B**，AC 14 → **15** 条。
- 2026-10-14 **RQ-1（`woc-rq1-contract-corpus`，research，done）**：契约判定链 + 别名表 + 澄清模板来源 + 消费者 + 测试翻转面。证据 `evidence/research/spec-rq1-contract-corpus-20261014.md`（46,755 B，413 行；兜底副本 `workers/woc-rq1-contract-corpus/report.md`）。
  **三条改变 spec 的结论（PM 已独立复核）**：① 受判文本 = `agentProductText()`（**优先 `report.md`**，`output-writer.ts:140-145`）而非 `output.md`，判定整篇 `includes`、标题不参与（PM 读源码确认）；② **AC-010 前提被推翻**：`99.4%`/`87.2%` 属 `mw-dispatch-card-gate` 派发卡信封统计（PM `grep` 复核到 `spec-dispatch-input-format-20261012.md:142`、`spec-card-format-corpus-20261012.md:281`、`mw-dispatch-card-gate/spec.md:42-43`），本契约无历史统计；③ **PM 独立复现语料对照**：judged 433 份，整篇别名 145/433 = **33.5%**（RQ-1：142/423 = 33.6%），只认标题 35/433 = **8.1%**（RQ-1：29/423 = 6.9%），`alias_ok→heading_fail` **110** 例（RQ-1：113）。
  **spec 相应改动**：P1 机制更正（受判文本 / 调用点 `:2740` 与 `:257-259` / `exitCode` `:2746`）；S1/S3 作用对象改为「受判产物文本」；§1.7 新增第 6/7 条（语料现实 + 跨契约误引）；**AC-010 重写**为新产物全通过 + 逐条处置、**新增 AC-014**（更正误引）；R1 重写；§2.4 补 `output-writer.ts`。spec 22,590 → **26,422 B**，AC 13 → **14** 条。
  **AC-014 的记忆文档半边已执行**：`_framework-reflect.md` FW-001 的修法 5 已更正出处，并追加「第七次实例的成因链更正」（受判文本 + 误引）。
- 2026-10-14 **RQ-5（`woc-rq5-readback-push`，research，done）**：吸收终态回读推送缺口（P6）。唯一证据文件 `evidence/research/spec-rq5-readback-push-20261014.md`（29,452 B，md5 `734716be04d5d2a43cd106601e0dedb3`，与 `workers/woc-rq5-readback-push/report.md` **同 md5** ⇒ 无需 PM 提升）。
  本次实际跑出：`woc-rq5` 走的是壳层直写证据路径（`worker_file` 只能落任务目录，`write` 工具不在 research 工具面）——这正是 P2 的现场复现，同一批 RQ 的写法差异值得在 design 阶段对照。
  PM 独立复核：`pm/pm-orchestrator.ts` 与 `shared/ack-store.ts` 相对 HEAD **无改动**（只读边界守住）；`:1434-1475` 原文确认 `notified.add` 早于 owner 门禁、`recordWriteScopeResidualRisks`(`:1448`) / `readOutputBody`(`:1457`) 均在门禁之后；探针 `:143-156` 确认 `P4` 断言是绝对值 `step4 === 1`（⇒ 修复后必然翻转，属探针断言债）；既有测试 `agent-team-loop.test.ts:2053-2085`（`:2077` 断言「无 watch key 期间终态行不得复活」）确认存在。
  **据 RQ-5 修正 AC-011**（同属该 AC 范围内）：新增 (c) `P4` 断言须先改写为 `had("b2")` 或 `step4 === step3 + 1`、(d) 修法须分离 **C3/C1** 且既有断言 `:2077` 必须保持通过；§4 R5 补记 `notified` 兼任 `recordWriteScopeResidualRisks` 每任务一次的界（C3 分支必须继续记账）；§2.4 补 `ack-store.ts` / `worker-store.ts` / 既有测试锁。spec 21,256 → **22,590 B**（AC 仍 13 条）。

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions

- D-001（范围，2026-10-14）：本 key 收 `_framework-reflect.md` 的 **FW-001 / FW-002 / FW-005 / FW-007 / FW-009**（同属 worker 输出面：`output.md` 段契约、`<key>/evidence/**` 产物写面、`trace.log` 变更账本、检查点判据），并按用户指定并入 **P6 终态回读推送范围缺口**。范围外分流：FW-003/FW-004 → `mw-dispatch-reliability`；FW-006 → `mw-review-audit-method`；FW-008 → `mw-test-runner-hygiene`。
- D-002（修法）：S1 判定改按标题结构；S2 前置清单 + 收尾前自检；S3 机械段自动补齐；S4 `worker_file` 路径域放宽到 `<key>/evidence/**`（GC-5 禁止给 research/review 加 `write`）；S5 账本形状校验 + `unjudgeable` + 检查点判据改用落盘信号；S6 推送记账后置 + 补推语义。
- D-003（证据引入）：`_scratch/evidence/readback-push-scope-gap-20261014.md`（14,191 B / sha256 `A55ACD7DF8EB70D9…`）与探针 `readback-push-scope-repro-20261014.mts`（5,197 B / sha256 `1EDE11BAA4827006…`）**字节纯净**并入本 key `evidence/`；spec 17,160 → 21,256 B，AC 10 → **13** 条；研究笔记补 F6 与映射行。
- D-007（AC 判据校正，2026-10-14，设计阶段）：**AC-017(c)** 由 `allow=3 deny=0` 校正为 `allow=2 deny=0`（另加「该命令产 0 候选」）。依据 = DR3 实测 + PM 复核 `wfg-rq1` 的 `trace.log:266/352/357` 三条 deny（target 均为 `--glob`）与 `:384 [WRITE_SCOPE_SUMMARY] allow=0 deny=3 allow-unknown=0`；其中 `:352` 的 `Write-Output a <term> --glob x` **无写 API**，修后不构成候选。AC 编号不回收，原文保留并就地加校正标注。

- D-006（阶段推进 + design 调研，2026-10-14）：`advance_phase(spec → design)` 成功（IndexParallel → DESIGN）。design 阶段按并行优先协议一次性派 **6 个** research worker（只读角色、互不重叠、各自唯一证据文件）：DR1 写面通道（`worker_file` 放宽 + 派发期同源，AC-006/007/016）、DR2 契约判定与机械段补齐（AC-001..005/010/014/015）、DR3 账本抽取器加固（AC-008/017）、DR4 检查点判据与看门狗不变量（AC-009）、DR5 回读推送域（AC-011/012/013）、DR6 验证矩阵与基线红区分（全 AC + 部署序列）。任务键 `woc-dr1…dr6`，卡 `tasks/T-DR1…T-DR6-*.md`，证据 `evidence/research/design-rq{1..6}-*-20261014.md`。

- D-005（阶段锁定，2026-10-14）：**用户确认锁定 spec / AC-001..AC-017**（spec 34,907 B；5 份 spec 阶段研究证据已吸收：rq1 46,755 / rq2 39,163 / rq3 42,480 / rq4 32,361 / rq5 29,452 B，均有同字节 report.md 兜底）。锁定时 PM 提出的两个拍板点按「接受」处理：AC-010 判据改为「本 key 交付后新跑的 ≥6 个 worker 受判产物全 exit=0 + 110 例逐条处置」；AC-016 保留在**本 key 范围内**（派发期 `pm/ui-bridge.ts` 判定与运行期同源，否则 FW-002 不闭合）。

- D-004（调研，并行优先）：spec 阶段一次性派 **5 个** research worker（RQ-1 契约判定语料入口 / RQ-2 写面分层与改动点 / RQ-3 账本与消费者 / RQ-4 检查点与 settle 插入点 / RQ-5 回读推送），各自唯一证据文件、互不重叠，均为只读角色。

- D-016（模型服务挂死，2026-10-15，执行阶段）：`woc-t13-selfcheck` r1/r2 两次均因 **deepseek-v4-flash-0731 请求挂死**（r1 首请求 14m CPU 1.19s；r2 完成全部实现后验证阶段挂 18m CPU 18.7s）。上游探活 200/1.8s 正常，属间歇性。已确认 worker 侧**无请求超时**，活动看门狗把心跳算作活动故未触发。处置：终止 + ack + **PM 直执**（实现已在盘上，剩余验证 PM 独立重跑等价覆盖）。建议：T-09 前评估给 worker 模型请求加超时/重试（遗留项）。

- D-015（**已按推荐 = 选项 C 执行**，2026-10-14，执行阶段）：用户裁决「按推荐」。PM 将两处收窄按**选项 C** 处置：新建 **T-13** 卡（`tasks/T-13-selfcheck-delivered.md`，过卡门禁）——(1) 自检回合条件改「已交付」（`hasDeliverableEvidence(taskDir, lastAssistantText).delivered`，与 `finishSuccess` 同谓词；未交付保持立即 `no-product` 裁决，`mwds-t04:401` 形态不变）；（2）TS 侧注入条件改「card 有 type」（去掉 `isWritelessRole` 收窄）；（3）R8 登记的两处用例（`dispatch-recovery-terminal:162`、`output-recovery-contract:282`）改两次 settle 流；（4）`dispatch-card-injection.test.ts` 加入写面更新 expected。已派发 `woc-t13-selfcheck`。T-07 依赖更新为 A+B+T-10+T-13。
  **(1) AC-003 TS 半边收窄**：`pm/ui-bridge.ts:1908` 实际为 `sections.type !== undefined && isWritelessRole(sections.type) ? recoveryContractSection(...) : ""`；卡写的是门控「`card is not None`」。后果：**经 PM（TS 路径）派发的 coding 卡不带 S2 清单**（Python/autopilot 路径已覆盖 coding/research/review，故 autopilot 无影响）。worker 的理由是该文件被 `test/suite/dispatch-card-injection.test.ts`（字节日铉 coding fixture）钉死，而该测试不在本卡写面。
  **(2) AC-004 自检回合收窄**：`worker/worker-mode.ts::settleOrSelfCheck` 实际要求 `judgedProductFile(taskDir) !== undefined` 才发回合；卡/AC-004 文字无此条件，且 R8 明确登记「settle 层至少 3 处既有用例必须改」。后果：**reply-only 被判 run（无 report 文件，产物 = settle 回复）拿不到修复回合**，直接被判 `exit=2`。已核实机制：`judgeRecoveryHere()` 对 writeless 角色恒真（含无产物），但回合被文件条件挡住；而 `dispatch-recovery-terminal:162` 正是该形态（delivered 但 reply-判）——即 R8 预告要改的那一例。
  **PM 建议（选项 C，待确认）**：把回合条件从「有产物文件」改为「**已交付**（`evidence.delivered`）」——即「有东西可修就给一次机会」，而**未交付**仍保持立即 `no-product` 裁决（AC-006/C5 告警不被延后）。理由：这正好对应 R8 登记的 3 处改动（两个已登记文件，非全量涟漪）；能消除「已交付却被 reply-判而无法自修」的假 `exit=2`；且不推动 `mwds-t03`/`mwds-t04` 的未交付单 settle 用例。并同卡修复 (1)（一行 + 字节日铉测试的 expected 更新）。
  **备选**：选项 A = 接受两处收窄并作为 AC-003/AC-004 的正式范围声明（最快、最保守，但保留两个已知缺口）；选项 B = 字面执行（全量回合）—— PM 已核其会连带改 `mwds-t03`/`mwds-t04` 等写面外不变式套件与延后 `no-product` 告警，**不推荐**。

- D-014（T-12 采纳与两处语义取舍，2026-10-14，执行阶段）：（a）**采信** T-12 的钳制修法 —— 未来 mtime 的唯一合理解释是「刚落地」（时钟粒度/写读竞态），钳到 `nowMs` 比跳过更忠实，且把偶发变成确定性反例；（b）**接受代价**：重放场景 `last_land` 由 `83s` 变 `0s`（把检查点之后的追加归到检查点时刻），不因此再开一轮修复 —— AC-009 的验收点是 `risk`（正/负例结论不变），重放本就非严格时间点重建，且引入 epsilon 阈值会在边界处重新引入非确定性；该限制登记入 T-09；（c）**格式债**：属本 key 改动面的文件尚有 3 个 `biome format` 错误，收口时用 scoped `biome check --write` 清理，**不跑仓级 `npm run check`**（会改动并行会话文件）。

- D-013（T-04 非确定性缺陷的裁决与补卡，2026-10-14，执行阶段）：PM 复跑 T-04 新套件 6 次得 1 次红，定位为 `worker-mode.ts:402` / `collectLandingSignals` 的「未来 mtime ⇒ 跳过」上界语义与 `Date.now()` 取值的竞态（Windows NTFS mtime 粒度）。裁决：（a）判为**代码缺陷**而非测试写法问题 —— 未来 mtime 的唯一合理解释是「刚落地」，跳过使 `landed` 信号更悲观且重放判据不可复现（重放固定历史 `nowMs`）；（b）修法为**钳制**（把未来 mtime 归到 `nowMs`，age=0），保留 `startedAtMs` 下界与 `size===0` 语义；（c）同时把该用例改为**显式 `nowMs`**（消竞态）+ 新增未来 mtime 用例，并要求连续 10 次重跑证据；（d）T-12 写面与 T-05 相邻（同在 `worker-mode.ts`），**先 T-12 后 T-05** 串行。

- D-012（T-11 偏差裁决与 AC-010(b) 验证前提，2026-10-14，执行阶段）：T-11 worker 报告一处显式偏差——卡要求 2 的字面「标题必须以别名开头」与卡自己的不回归清单矛盾。PM **核实后采信偏差**：4 个受保护套件内嵌同一 T-08 语料标题（别名 `改动` 在 `：` 后子句开头），字面实现会同时判红这4 套；`change-ledger.ts:278` 的既有 T-21 注释已记录该语料，说明子句语义是既有意图。裁决：保留子句锚定（标题本身或 `：`/`｜`/`|` 子句开头），并按「不弱化真红」原则保留真红正向用例；`…：变更xx` 形残留偏松面登记为已知限制。另一项：settle 判官在 worker 进程内绑定 ⇒ 修复对开工早于本改动的进程不生效（T-11 自身终态截图即实证），故 **AC-010(b) 必须在 T-08 部署后重跑**。

- D-011（T-02 误红的定位与补卡，2026-10-14，执行阶段）：T-02 worker 实质交付通过（21/21 新用例 + 基线零新增红），但 settle 判 `exit=2 / needs-clarification`，理由 `unrecorded write(s): T-02 卡, .agenticdoc/goal.md`。PM 用 `diffLedger` 直调复现并定位到 `shared/change-ledger.ts:416` 的 `includes` + `#{1,6}` 标题识别（报告 H1 含「变更」即把头部当声明区）。判为**框架缺陷**，新建 **T-11** 修复（H1 排除 + 起始锚定 + 用真实事件做夹具 + 真红不弱化），只改声明区标题识别，不改 `unjudgeable`/抽取器/`collectDeclared`。理由：它直接卡住 AC-010(b)（≥6 新 worker 全 `exit=0`）；同属 FW-005（trace.log 变更账本）语义面。T-11 与 T-10 写面不重叠，并行派发。

- D-010（T-01 缺口补卡，2026-10-14，执行阶段）：T-01 交付了写面单源的 2/3（派发期 `ui-bridge` + `worker_file` 通道）；壳层守卫与 `write_scope` 解析仍未收敛。鉴于 `design.md` §3.1 明列**三个**适配层、AC-016 硬判据含「不得各写一份正则」，新建 **T-10**（`tasks/T-10-shell-guard-convergence.md`，过卡门禁）补齐第三处，置于 `worker-mode.ts` 串行链：T-02 → **T-10** → T-04 → T-05。卡内明写**保留** DR1 裁决的差异（shell 通道对 keyDir 相对 `evidence/x.md` 继续 fail-closed）并逐例测试锁住，不抹平。T-07 依赖改为 A+B+T-10。

- D-009（阶段推进 + 批次 A 派发，2026-10-14）：`advance_phase(plan → tasks)` → 写 9 张任务卡（T-01…T-09，全部过卡门禁：信封三段 + coding 四项额外节 + seed 最小项）→ `advance_phase(tasks → execute)`（Phase=EXECUTE）。按 plan §4 一次派 **3 个** 编码 worker（写面零重叠）：`woc-t01-write-surface`（`shared/write-surface.ts`+`worker-file-tool.ts`+`deliverable-evidence.ts`+`pm/ui-bridge.ts`）、`woc-t03-readback`（`pm/pm-orchestrator.ts`+探针）、`woc-t06-s2-sections`（`autopilot/dispatch.py`+pytest）。派发前实测：三者允许面文件 `git status` 干净、无 running worker；`worker/worker-mode.ts` 被另一 key 留有未提交改动 ⇒ 串行链（T-02/T-04/T-05）一律**符号锚定**、开工前再核。批次 B 待 A 回读后按 T-02 → T-04 → T-05 串行派。

## 6. Turn End Records

- 2026-10-14（接手上半程）：PLAN 收口 → 写 9 张任务卡并过卡门禁 → EXECUTE，派批次 A 三个 worker；pm-state Task Status 建表。
- 2026-10-14：建 key（写 `spec.md` 自动 claim，本窗口 `WENBOZHOU-PC4:162452` 归属）→ `advance_phase spec`（Phase=SPEC）→ 落 `key-decision.md` 与 `evidence/research/spec-contract-evidence-20261014.md` → 并入 P6（byte-pure）并改 spec → 派 `woc-rq1…rq5`（running）。

## 7. Process Log

- 10:34 建 key 与 spec（17,160 B，AC-001…AC-010），Phase=SPEC，index 同步。
- 10:40 研究笔记落盘（6,675 → 7,831 B），含 F1…F5 与映射表。
- 10:52 并入 readback 推送缺口证据（双 sha 记录），spec 收编 P6/S6/AC-011…013，AC 总数 13。
- 10:55 派 5 个 research worker（`woc-rq1-contract-corpus` … `woc-rq5-readback-push`），全部 running。
- 11:0x 吸收 `woc-rq5-readback-push`（done）
- 11:1x 吸收 `woc-rq1-contract-corpus`（done）；ack。
- 11:2x 吸收 `woc-rq4-checkpoint-settle`（done）：复核 settle「先判后写」与计数入参缺陷、新增 AC-015；ack。
- 11:3x 吸收 `woc-rq2-write-face`（done）：复核写面三层与派发期/运行期判定相反、新增 AC-016 与 R7/R8；ack。
- 11:3x 吸收 `woc-rq3-ledger`（done）
- 11:4x 用户锁定 AC-001..AC-017
- 11:5x advance spec → DESIGN；派 6 个 design 阶段 research worker
- 21:4x 接手本 key（Phase=PLAN，plan.md 已就绪）→ 写 9 张任务卡 → `advance_phase(plan → tasks)` → `advance_phase(tasks → execute)` → 派批次 A（`woc-t01-write-surface` / `woc-t03-readback` / `woc-t06-s2-sections`）。
- 21:5x 吸收 `woc-t03-readback`（done）：PM 重跑新用例 3/3、C3 锁用例通过、探针 P1..P6 全 PASS（P3 `count b1=1`），读 diff 确认 C1/C3 拆分与 `notified.add` 新位置；ack；为缩短关键路径提前派 `woc-t02-ledger`（与 A 批写面零重叠）。
- 13:0x **T-09 结案（PASS）**：`achieved.md`（≥200 B，含 `## 系统行为变化` 五切面 + `## 遗留` 6 项）+ `evidence/quality-gate-report-20261015.md`（AC-001…017 勾销表 + 证据链 + 未覆盖面声明 + PASS）；`_framework-reflect.md` FW-001 标**已闭合**（T-11/T-05/T-13 修法落地 + AC-014 更正落点）、FW-009 标**已修**；`_pitfalls.md` 追加 P-037（卡面行号漂移）、P-038（抽取器误拦只读命令）、P-039（一次性守卫语义混淆）。**PASS 证据**：全 AC 勾销 PASS、新增红=0、AC-010(b) 6/6 exit=0、tsgo=0。将走 `advance_phase verify → done`。
- 12:5x **T-08 部署 + AC-010(b)（PM 直执，全部通过）**：`mw build --install --allow-dirty`（built + self-check OK version=0.83.0；bundle 安装到全局 `~/.pi/agent/extensions/agent-team-loop.js` + dist 重建）；无存活 worker 后 `mw stop`（旧 PID 65248）→ `mw start`（新 PID 48052）；`mw doctor`：`serve code: fresh` + `bundle: stale=False` + `summary: healthy` + `timi available`（conductor not running = autopilot 未启用，正常）；AC-010(b) 新建 6 个探针（acb-r1/r2 research、acb-v1/v2 review、acb-c1/c2 coding），扫描脚本 `new-worker-exit-scan.py` 判定 **runs=6 passed=6 coverage_ok=true count_ok=true 全部 exit=0**；6 份 report.md 段齐全无 Questions。用户已确认选项 A（bundle 含其他会话未提交改动，报告记录归属）。需人工 `/reload` 所有已打开 pi 窗口（T-09 achieved.md 引用）。
- 11:5x **T-07 吸收（PM 独立重跑）**：新套件 `mwoc-matrix-t07.test.ts` 25/25（PM 重跑）；24 文件基线差分（PM 重跑 558 例）：NEW FAILURES=0、STILL FAILING=恰 5 个 DR6 HEAD 既存红（worker-file-tool:177/:285、agent-team-loop:6381、mwds-t02:345、mwds-t23:295）、MISSING=7 全为 A/B/T-13 预期改名（逐一核过：dispatch-terminal/output-recovery 两次 settle 流、mwds-t03 VC-024 注册守卫、mwgal-t21 20→21）；语料 AC-010(a) n=466（活漂移 +1）tierA 181/466=38.8% tierB 66/466=14.2% flip 111；AC-010(c) 处置 3 rescued/83 still-fails/25 exempt 逐字一致；tsgo=0；写面仅 mwoc-matrix-t07.test.ts + evidence/。
- 11:5x **T-07 派发**（2026-10-15）：T-13 done 后解阻，派发 `woc-t07-matrix`（同卡），描述里含模型挂死风险提示（要求长时间无活动时立即写 progress.md 落盘）。
- 11:4x **T-13 PM 直执收口**（2026-10-15）：r2 挂死终止 + ack 后，PM 独立复核盘上实现（worker-mode.ts `isDelivered` 条件、ui-bridge.ts `sections.type !== undefined`、两处 R8 用例两次 settle 流、dispatch-card-injection expected+write_face 行全部逐行核读）；重跑 10 组套件零新增红（40/40, 18/18, 16/16, 14/14, 63/63, 19/19, 38/39, 196/197, 7/9, tsgo=0）；直接运行 probe 复现三类角色清单注入（coding 5 段/review 5 段/research 4 段）+ headingCount=1 幂等；写 `woc-t13-selfcheck-r2/output.md` 交付物。T-13 done。记 D-016（模型挂死，建议 worker 请求超时）。
- 11:0x **T-13 r1 挂死排查 + 重派 r2**（2026-10-15，执行阶段）：`woc-t13-selfcheck` 首跑在**第一个模型调用处挂死**——trace.log 自 02:51:23 起只有 `[START]`/`[MODEL] model=deepseek-v4-flash-0731`/30s 心跳，无任何工具/turn；worker.log 仅 `[worker] start`；14 分钟后 PID 36464 仍活着但 CPU 累计仅 1.19s（真挂死，非活跃等待）。PM 排查：本地代理 127.0.0.1:8000 对 `/v1/chat/completions` 返回 404（该端口是泛型代理，pi 走 timi 直连）；直接探活上游 `http://api.timiai.woa.com:80/ai_api_manage/llmproxy/chat/completions`（TIMI_API_KEY from `~/.pi/agent/auth.json`）→ **HTTP 200 / 1.8s**，模型服务健康（r1 挂死属瞬时故障窗口）。PM 用 `Stop-Process` 终止 PID 36464，ack 后以新 task 键 **`woc-t13-selfcheck-r2`**（同卡）重派，全新进程/目录；run.json 残留 `running`（进程死亡未 reconcile，PM 直接处置）。
- 22:7x 吸收 `woc-t05-contract`（done）+ 用户裁决 D-015 = 选项 C：PM 建 T-13 卡（自检回合改「已交付」+ TS 侧全角色注入 + R8 两处改两次 settle 流 + `dispatch-card-injection` 入写面），过门禁后派发 `woc-t13-selfcheck`；T-07 依赖更新为 A+B+T-10+T-13。
- 22:6x 吸收 `woc-t05-contract`（done）：PM 重跑新套件 40/40 + 6 套基线（零新增红）+ tsgo=0；复现 AC-001 八例矩阵与 AC-005 三例真实产物 `exit=2→0`；确认 R8 预告的 3 处 settle 层改动**未发生**（被两处实现收窄取代）⇒ 记 D-015（待用户裁决：建议选项 C = 回合条件改「已交付」）+ 修 (1) 同卡；ack。
- 22:5x 吸收 `woc-t12-landed-clamp`（done）：PM 重跑 21/21 且自跑 8 次全绿（修前 1/6 非确定红）+ 五套基线符 + tsgo=0；读源码确认两处钳制；记录两处取舍（重放 `last_land` 83s→0s 作为已知限制、3 个 biome format 错误交收口 scoped 清理）；记 D-014；派发 T-05（settle 链最后一环，`worker-mode.ts` 已让出）；ack。
- 22:5x 吸收 `woc-t04-checkpoint`（done）：PM 重跑基线逐项符（12/12、10/10、63/63、50/50、196/197、tsgo=0）与 AC-009/I3 结论；但复跑 6 次发现 1 次非确定红（`collectLandingSignals` 去重用例），定位为未来 mtime「跳过」语义缺陷 ⇒ 新建 T-12（钳制 + 显式 nowMs + 10 次重跑证据）并**先于 T-05** 派发；记 D-013；ack。
- 22:4x 吸收 `woc-t10-shell-guard`（done）：PM 重跑新套件 8/8 + 6 套基线（零新增红）+ `tsgo`=0；rg 复现 `write_scope`/`matchesWriteScopeEntry` 各仅 1 处实现、`worker-mode.ts` 无本地 glob/minimatch 残留；核实 DR1 两侧未被抹平；PM 直执纠正 `shared/write-face.ts:14` 陈旧注释引用；派发 T-04（`woc-t04-checkpoint`，`worker-mode.ts` 已让出）；ack。
- 22:2x 吸收 `woc-t11-ledger-heading`（needs-clarification）：PM 重跑 6/6 + 7 套基线全绿；直调 `diffLedger` 复现修复后 `extra=[]`（真实事件误红已消除）；`git diff -U0` 核实只动标题识别 3 hunk；核实并采信子句锚定偏差（字面实现会判红 4 套受保护测试）；记下 AC-010(b) 须在 T-08 部署后重跑（settle 判官进程内绑定）；ack。
- 22:1x 吸收 `woc-t02-ledger`（needs-clarification）：PM 重跑新套件 21/21 + 五组基线（零新增红）；用 `diffLedger` 直调复现并定位 NC 根因（H1 含「变更」⇒ 头部被读成声明区；换中性 H1 即 `declared=[]`）⇒ 判为框架误红、T-02 实质 done；新建 T-11 修误红（D-011），并与 T-10 并行派发（写面不重叠）；ack。
- 22:0x 吸收 `woc-t01-write-surface`（done）：PM 重跑新测试 13/13、既有六组套件与 HEAD 基线逐项一致（零新增红），读源码确认 `WORKER_FILE_NAME_RE` 单一定义与两处导入同源；确认壳层守卫仍未收敛（3/3 只完成 2/3）⇒ 新建 T-10 补卡并记 D-010；ack。
- 21:5x 吸收 `woc-t06-s2-sections`（done）：PM 重跑新套件 17 passed / t13 18 passed / dispatch+parity 25 passed（唯一红为既存 `test_bom_historical_books`），读 diff 确认注入点、幂等守卫与「先算 extras 再注入」的碰撞修正，复核 parity 测试解析真实 TS 源（fail-closed）；ack。AC-003 真实任务侧登记为 T-07/T-08 待复跑。
- 12:0x DR1…DR6 全部 done 并吸收：逐份复核 sha256/字节一致、校正 AC-005 与 AC-017(c)、扩写 R8 基线（含 5 个既存红 + 语料 n=437 + 8/103 分类）；6 个 worker 全部 ack。（`woc-dr1…dr6`，全部 running）；mw serve PID 151032 正常。；spec 锁定行改写，记 D-005；准备 advance → design。：抽取器机制与最小复现、误拦实例、新增 AC-017 与 R9；5 个 research worker 全部收口。：复核受判文本链路与语料数字（独立复现 33.5%/8.1%），重写 AC-010、新增 AC-014，更正 FW-001；ack。：证据同 md5 复核、源码未被改动、P4 断言债与既有测试锁确认；据其修正 AC-011 / §4 R5 / §2.4；ack 完成。
