# 质量门报告 — mw-autopilot-gate-alarm-liveness（2026-10-13）

- Key：`mw-autopilot-gate-alarm-liveness`｜收口卡：T-19｜日期：2026-10-13（本文件落地时点）
- 基线：`cc9a46a1a` + 本 key 全部实现卡工作树改动
- 权威依据：`spec.md` AC-001…AC-016；`design.md` D1-D10 / D-009…D-015；`plan.md §5 收口判据`；对抗式质量门 `workers/mwgal-t18-adversarial-qg/report.md`（R-1…R-8 / G-1…G-4）
- 证据口径：`path:line` 为**当前工作树 1-based 行号**（定位以符号锚为准，P-07）；测试输出为**本次收口实测逐字**（T-19 复跑，非引用他人自述）。实现卡自证输出见各 `workers/*/report.md`。

## 结论

**16 条 AC：11 条成立、4 条部分成立（判据成立、运行期证据或子判据未闭环）、1 条运行期未达成（AC-015 默认 off）。** 零行为走样：本 key 未放宽任何既有判据（P-03），`GateView` 精确四字段与 20 键 config 集合锁均保持。

四条"部分成立"的准确含义：

| 部分成立项 | 判据/实现 | 未闭环的部分 |
|---|---|---|
| AC-003 六值枚举 | 三读面已派生，R-2/R-3/R-4 修复后 `gate-queue-unreadable` 三面可见 | 无（修复后收口为成立）；历史缺口已由 T-21/T-22 关闭 |
| AC-005 漂移自证 | `serve.meta` 身份 + `code_digest` + `mw status`/`mw doctor`/serve 环路判据全部成立，本机有活体 STALE 样本 | **G-1**：判据内"重启后复核 pending 门禁未被新自动裁决意外改写"（`answered_by=conductor-auto:` ∧ `answered_at > 新 started_at_ms`）的机器检查全仓无实现 |
| AC-014 派发不以 claim 为前置 | 合成 claim 全生命周期 + 人工让位 + 单锁单写者 + 外机不抢，测试全绿 | **G-2**：无真实无接管会话的运行期长跑证据，仅测试级 |
| AC-015 stage-close 自动放行 | 五判据 + 留痕 + 回落点名 + 安全阀全部成立 | **G-3**：默认 `auto_gate_mode=off` + shadow 门槛 ⇒ 生产自动批准占比仍 0%（本机 `phase:"decide"` = 0 行），"减少必须等人的门总数"运行期未达成 |

**对抗式质量门 5 个缺陷（R-1…R-5）全部已处置并内建回归**（R-1/R-2/R-3 由 T-21，R-4/R-5 由 T-22）；R-6 风险链随 R-1 关闭；R-7/R-8 为反证（确认设计成立）。残留见文末。

## 证据

### A. T-19 本次实测（逐字，仓库根 / 包根）

**Python 面（key 定向 + 跨语言锁面）**：

```
cd packages/multi-workers
python -X utf8 -m pytest test_mwgal_t11_suppression.py test_mwgal_t12_stage_close_auto.py \
  test_mwgal_t13_drift_identity.py test_mwgal_t14_blocker_class.py test_mwgal_t15_reattest_confirm.py \
  test_mwgal_t16_synthetic_claim.py test_mwgal_t22_qg_fixes.py -q
→ 100 passed, 10 warnings in 15.41s

python -X utf8 -m pytest test_autopilot_gates.py test_autopilot_gate_schema_v2.py \
  test_autopilot_contract_guard.py test_doctor_gates.py test_autopilot_state.py \
  test_autopilot_gate_reminder.py test_serve_doctor.py test_update_env.py -q
→ 192 passed, 66 warnings in 74.88s
```

**TS 面（key 定向 + 跨语言锁面）**：

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t10-state-surface.test.ts \
  test/suite/mwgal-t10b-presentation-budget.test.ts test/suite/mwgal-t13-drift.test.ts \
  test/suite/mwgal-t14-blocker-class.test.ts test/suite/mwgal-t14b-monitor-blocker-class.test.ts \
  test/suite/mwgal-t16b-takeover-yield.test.ts test/suite/mwgal-t16c-restorewatch-trace.test.ts \
  test/suite/mwgal-t17-ledger-role-aware.test.ts test/suite/mwgal-t17b-ledger-infra-writes.test.ts \
  test/suite/mwgal-t17c-ledger-unresolvable.test.ts test/suite/mwgal-t20-config-parity.test.ts \
  test/suite/mwgal-t21-qg-fixes.test.ts
→ Test Files  12 passed (12) ; Tests  131 passed (131)

node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts \
  test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-config-sync.test.ts \
  test/suite/autopilot-config-parity.test.ts test/suite/autopilot-event-parity.test.ts
→ Test Files  5 passed (5) ; Tests  61 passed (61)
   （含 P1 crosslang_verdict_match=73/73、P2 canonical_sha_match=38、P6 effective_view_20=true）
```

**仓库级检查**：见 `## 验证命令与实测输出`（T-19 独占运行 `npm run check`，逐字输出见 `report.md`）。

**运行期活体证据（本机，`packages/multi-workers`）**：

```
python mw.py status --project .
[mw status] running (PID 168160)
[mw status] conductor: not running
[mw status] serve code: STALE CODE (content changed): tree=H:\git\Multi-Workers\packages\multi-workers
  schema=0/1 serve_pid=168160 started=2026-10-13T02:57:56Z code newest mtime=2026-10-13T13:47:36Z
  (base=2026-10-13T02:57:56Z) expected commit=(unavailable)
  actual commit=cc9a46a1ad1ebb35eb1a5d96d8101c46cd3b78ad drift_age=10m dirty_at_start=n/a
  version=? digest=a660c4be5a83 fix: /mw restart
EXIT=0

python mw.py doctor --project .
...
summary: ISSUES: STALE CODE (content changed): ... fix: /mw restart
serve code: STALE CODE (content changed): ...
EXIT=1
```

即**运行中的 serve 是旧 schema（`schema=0`）、旧代码**，而新鲜进程入口（`mw status`/`mw doctor`）当场说出它并给出 `/mw restart`——这正是 AC-005 设计要修的形状在本机的活体复现。

### B. 逐条 AC 对账（判定 + 证据 + 未覆盖/残留）

| AC | 判定 | 证据（锚/逐字） | 未覆盖 / 残留 |
|---|---|---|---|
| AC-001 常驻 pending 行 | **成立** | `monitor.ts:420 readMonitorState` 全量收 gates（无 cap/衰减/去重）+ `:1164 renderMonitorLines`；`monitor.ts:1005-1104` 编码表 + `:1105 renderPendingGateLine` 的 fit ladder（`~D`/age/reason 必显）。实测 `mwgal-t10-state-surface.test.ts`（15-gate 全渲染 + drop 序）在本报告 A 组绿 | — |
| AC-002 按 key 抑制 / 不可解析不抑制 / 留痕 | **成立** | `conductor.py:2950 pending_gate_reminders`（条件 1 per-key；空 key 不抑制）+ `:3178 _remind_pending_gates`（`remind-suppressed` 台账）+ `:3043 _emit_alarm`；`blocked_on_human` 三面同批：`monitor.ts:607`、`status-model.ts:1586`、`mw_common.py:3354`。实测 `test_mwgal_t11_suppression.py` 在 A 组 100 passed 内 | — |
| AC-003 六值封闭枚举三面派生 | **成立（修复后）** | `status-model.ts:696 GATE_REASONS` / `:707 GATE_SUPPRESSION_PRIORITY` / `:712 GATE_SCOPE_UNRESOLVED` / `:738 deriveGateReason`；`monitor.ts:1061 GATE_REASON_CODE`；`conductor.py:2930-2932` 三常量 + 注释声明同枚举。`gate-queue-unreadable` 三面：monitor 渲染（T-21 R-2）、`listGates` errors（T-21 R-3）、`gates.py:373 queue_entries` / `:230 GateQueueUnreadable`（T-22 R-4）。实测 `mwgal-t21-qg-fixes.test.ts` + `test_mwgal_t22_qg_fixes.py` 全绿 | 历史缺口 R-2/R-3/R-4 已处置；无残留 |
| AC-004 双通道发射 / cap=打断次数 | **成立** | `conductor.py:3043 _emit_alarm` 单一 choke point（stderr + timeline `config`）；`:3229` cap 标注"已达打断上限，仍待处理"；`:2935 _reminder_count` 台账真值（D-006）。实测 `test_mwgal_t11_suppression.py` 的 `test_reminder_emission_is_fail_loud_dual_channel` / cap 用例在 A 组绿 | — |
| AC-005 `serve.meta` 身份 + 漂移 | **部分成立** | `mw.py:120 SERVE_META_SCHEMA=1`；`:161 _write_serve_meta`；`:5312 _runtime_digest`；`:5416 _git_head_oid`（40 位纯文件读）；`:5495 serve_code_verdict`（digest 优先 / `history-only` / `schema-stale`）；`:5667 _report_serve_code_drift`（限频键）；`mw-runner.ts:301 serveStaleness`。实测本机 `mw status` 判 STALE CODE（A 组运行期） | **G-1**：判据内"重启后复核 pending 门禁未被新自动裁决意外改写"的机器检查（`answered_by=conductor-auto:` ∧ `answered_at > 新 started_at_ms`）全仓 grep 无实现、无测试（T-18 G-1，T-19 未新增代码） |
| AC-006 同通道复用 / 分工不重复 / 不自动重启 | **成立** | `conductor.py:5667 _report_serve_code_drift` 走 stderr + timeline `config`；`mw.py` serve 环路无重启调用；TS 只保留 `mw-runner.ts:301 serveStaleness`（交互恢复），无新增周期通知。实测 `test_mwgal_t13_drift_identity.py` 在 A 组绿（emit-once / fresh-emits-nothing） | — |
| AC-007 `blocker_class` 序外注册 fail-closed | **成立** | `gates.py:190 _SCALAR_EXTENSION_FIELDS`、`:197 BLOCKER_CLASSES`、`:753` 枚举校验；判定层 `conductor.py:7028 blocker_class_of` + `:7595 answered_by=conductor-auto:` 前缀 `blocker-class-not-paperwork`；TS `status-model.ts:769 blockerClassOf`。实测 `test_mwgal_t14_blocker_class.py`（Py 五形态）+ `mwgal-t14-blocker-class.test.ts`/`mwgal-t14b-monitor-blocker-class.test.ts`（TS 五形态）+ `autopilot-gate-presentation.test.ts`（40 名序差分锁）全绿 | 漏注册 ⇒ 整队列 fail-closed 并有 tick 级 `config` 事件（可见），符合设计 |
| AC-008 re-attest | **成立** | `conductor.py:4271 reattest_gate`（新 gate + `context_refs: reattest-of:<id>`，编号不复用）+ `:4324 _apply_reattests`（不依赖 `status=="stalled"`）。实测 `test_mwgal_t15_reattest_confirm.py` 在 A 组绿（VC-1/2/3 + stage-close 刷新重评三态） | — |
| AC-009 reject 二次确认 + 措辞校正 | **成立** | `conductor.py:7644 answer_gate_confirmed`（写前拒绝）+ `:102 REJECT_CONSEQUENCE_STATEMENT`；CLI `mw.py:6385 --confirm-destructive`。实测 `test_mwgal_t15_reattest_confirm.py` VC-6/VC-7 在 A 组绿；`mw autopilot answer --help` 逐字列出 `--confirm-destructive`（见 runtime-actions） | t15 VC-6 的 `[VERIFY]` 输出行布尔反义（`nothing_written=_true(... != before)`）为外观缺陷，断言本身正确（T-18 探针 7）；本卡不改行为 |
| AC-010 无 watch 丢弃留痕 | **成立** | `pm-orchestrator.ts:1312 GATE_REMINDER_DROPPED_ENTRY_TYPE`（no-watch/other-key/read-error，无 seq 不推 watermark）；`:1480 readGateReminders` 接通。实测 `mwgal-t10-state-surface.test.ts` no-watch drop 用例在 A 组绿 | — |
| AC-011 不新增 config 键 / parity | **成立** | 20 键冻结两侧锁定；`autopilot-config-parity.test.ts`（P1 73/73、P2 sha 相等、P6 20 键）+ `autopilot-config-sync.test.ts` + `mwgal-t20-config-parity.test.ts`（可选键 `envelope_fallback` 分类）。实测 A 组 `Test Files 5 passed / 61 tests` 与 `12 passed / 131 tests` | — |
| AC-012 不回归 / `GateView` 不破坏 | **成立** | `autopilot-console.test.ts` 的 `GateView` 精确 `toEqual`（`{id,kind,status,ageMs}`）+ `autopilot-gate-presentation.test.ts` 40 名序差分 + `autopilot-event-parity.test.ts`。实测 A 组全绿；TS 第 3 解析面（`listGates`）已显式处理读错误而非静默 | — |
| AC-013 回收契约角色分流（C-36） | **成立** | `change-ledger.ts:323 isInfrastructurePath`（R-1 后文件级）、`:426 deliverableDir`、`:812 unresolvable`；`output-writer.ts:78 unresolvableFiles`、`:356 ## Ledger Unresolvable`。**C-36 六子类全覆盖**：a（writeless 过判）/b（taskDir 外交付物漏计）/c（路径污染 `$var`）/d（系统写入误归因 `gate-writer.ts`）+ P-03（真实越界写仍红）+ role（runtime set 锁）。实测 `mwgal-t17*.test.ts`（3 文件，含 R-1 正面红断言）在 A 组绿 | R-1 只改"PM 侧在带检测器"判定，工具层守卫（`xkey-gate-guard.ts` 的 `write_text` marker 缺失、`.mw/**` 无守卫）仍属后续卡 |
| AC-014 派发不以 claim 为前置 | **成立（测试级）** | `conductor.py:225 SYNTHETIC_CLAIM_HEARTBEAT_SEC`、`:391 maintain_synthetic_claims`、`:280 _synthetic_claim_stale`、`:263 _foreign_synthetic_claim`；`index_parallel.py:126 set_claim`/`:149 clear_claim`；`index-store.ts:132/:157/:180`；`ui-bridge.ts:251 ClaimState`/`:267 claimState`；`pm-orchestrator.ts:319 tookOverFromConductor`。实测 `test_mwgal_t16_synthetic_claim.py` + `test_mwgal_t22_qg_fixes.py`（R-5）+ `mwgal-t16b/t16c` 全绿 | **G-2**：无真实无接管会话的运行期长跑；R-5 外机语义已按"宁可卡住不可双持"对齐，真多机未验证 |
| AC-015 `stage-close` 自动收证 + approve | **部分成立** | `conductor.py:6374 proposition_stage_close_credentials`（五判据）+ `:6932 _stage_close_facts`（磁盘现算）+ `:7576 answer_gate_auto`（`answered_by=conductor-auto:<rule>`）+ `:6554 STAGE_CLOSE_AUTO_RULE_ID` + `:7301 _append_auto_decision_row`（`phase:"decide"`）+ `:8130 auto_decide_gates`。实测 `test_mwgal_t12_stage_close_auto.py` 在 A 组绿（逐条翻转 / 回落点名 / 幂等 / stage-confirm 恒 guard / 48h 只升级） | **G-3**：默认 `off` + shadow 门槛（≥5 夜 ≥20 决策 ≥1 反例）⇒ 生产自动批准占比 0%（本机 `phase:"decide"`=0 行），第一性目标③的运行期"减少人门总数"未达成 |
| AC-016 stage 主闸行 | **成立** | `monitor.ts:638 deriveMonitorStages`（每 stage 状态 + 卡门 + age + frozen keys；`halted` 自名 blocker）+ `STAGE_BLOCKER_KINDS`。实测 `mwgal-t10-state-surface.test.ts` stage 行用例（pending 卡 stage-confirm 带 age、frozen k2、halted）在 A 组绿 | — |

### C. 对抗式质量门缺陷处置（R-1…R-5 + 风险链）

| 缺陷 | 判定 | 处置（卡） | 证据 |
|---|---|---|---|
| **R-1** 声明写 `_autopilot/**`/`.mw/**` 不再判未记录写入（C-37） | 已修 | T-21 | 删除 `INFRA_DIR_SEGMENTS`；`change-ledger.ts:323 isInfrastructurePath` 仅按 basename；`mwgal-t17b`/`mwgal-t21-qg-fixes.test.ts` 正面红断言（A 组 `12 passed`） |
| **R-2** monitor `partial` + 0 可读渲染 `gates: 0 pending` | 已修 | T-21 | 渲染阶梯插入 `partial && gates.length===0` 分支，输出 `gates: gate-queue-unreadable (N unreadable: samples) -> /mw doctor`；`MonitorSnapshot.queueFailures`。`mwgal-t21-qg-fixes.test.ts` 实测行见 T-21 report（A 组绿） |
| **R-3** TS `listGates` readdir 失败静默 0 pending | 已修 | T-21 | `status-model.ts:1146 listGates` catch 区分 `ENOENT`（合法空）与其他（`errors=[dir: err]` ⇒ `warning:` 行）。`mwgal-t21-qg-fixes.test.ts` R-3 用例（A 组绿） |
| **R-4** Python 面把"路径是文件"折叠为空队列 | 已修 | T-22 | `gates.py:373 queue_entries` 三情形单一落点 + `:230 GateQueueUnreadable`；`conductor.py:3518` tick `config` 留痕、`mw_common.py:3444` doctor `error`。`test_mwgal_t22_qg_fixes.py`（A 组 100 passed 内） |
| **R-5** Python 踩外机合成 claim（TS 面不放宽） | 已修（按卡面默认对齐） | T-22 | `conductor.py:263 _foreign_synthetic_claim` + `:280 _synthetic_claim_stale`（外机永不 stale）+ `:443/:472/:733` 不回收/不接管/跳过。`test_mwgal_t22_qg_fixes.py` VC-3/3b/5 |
| **R-6** 经 R-1 洞伪造 shadow 历史解锁 live | 随 R-1 关闭（判定面） | T-21 | `_autopilot/auto-decisions.jsonl` 越界写现在 ledger 报红；伪造仍可能但不再"零告警"。工具层拦截残留见 R-1 |
| **R-7** 漂移自证按设计成立（反证） | 确认 | — | `serve_code_verdict` 分支序 + `history-only`；本次 `mw status` 活体 STALE 样本（A 组运行期） |
| **R-8** stage-close 不可被"证据未齐"绕过（反证） | 确认 | — | 五判据逐条 falsifying + detail 点名；`test_mwgal_t12_stage_close_auto.py` 逐条翻转 |

### D. 过程发现（必须随收口归档）

1. **C-36 六子类**（回收契约量错对象，已修，AC-013）：a writeless 过判（散文标题被当 `改动清单`）；b taskDir 外交付物漏计（四份 research worker `trace.log` 里 `evidence/research` 出现 0 次而交付物都在，`Exit Reason=writes=none` 累计 8 例）；c 路径污染（`$dir`/`$env:TEMP…` 当路径）；d 系统写入误归因（`gate-writer.ts` 的 `write` 被当动词，残片 `r.ts` 成幽灵声明）；P-03 防放宽（真实越界写仍红）；role（writeless 集合与 `REGISTERED_WORKER_TYPES` 由测试单源锁定）。
2. **上一 key（`b65380d1b`）新增配置键未同步 TS 注册表与放行集合 ⇒ P5 锁红着出厂**：Python 侧新增可选键 `envelope_fallback`（注册在 `_BOOL_FIELDS`、故意不在 `DEFAULT_CONFIG`），TS 侧镜像漏了 `validateConfigData` 的放行集合与 `BOOL_FIELDS`/T-04 计数锁，导致 `autopilot-config-sync.test.ts` P5（`expected 21 to be 20`）与 console T-04 双红随发布出厂。T-20 以"可选键一等类别"（`OPTIONAL_CONFIG_KEYS` 派生 + 分类断言 + 独立差异测试）修复。
3. **根因：`npm run check` 不跑测试**。`check` 脚本 = `biome check --write . && check:pinned-deps && check:ts-imports && check:shrinkwrap && check:install-lock:coding-agent && tsgo --noEmit && check:browser-smoke`，**不含任何 pytest/vitest**。跨语言 config parity 是**测试**判据，因此 `npm run check` 绿不代表 parity 绿——P5/T-04 的红就是这样漏过 check 的。本 key 的收口判据因此把"定向测试全绿"与 `npm run check exit 0` 并列为两条（`plan.md §5`）。

### E. 文档/现实不一致（收口勘误记录）

- 卡面种子锚点行号陈旧（P-07 已知）：`proposition_stage_close_credentials` 卡面 `conductor.py:5742` → 实测 `:6374`；`answer_gate_confirmed` `:7193` → `:7644`；`_apply_reattests` `:3933` → `:4324`；`change-ledger.ts unresolvable` `:804` → `:812`；`output-writer.ts unresolvableFiles` `:76` → `:78`；`scanPendingGate` 函数名已不存在（实为 `readMonitorState`，`monitor.ts:420`）。**原因：实现卡在同一文件继续落地，行号整体下移。** 已在 `docs/autopilot-observability-guide.md` 顶部记录，并一律改用符号锚。
- `_stage_activation` 设计文档记 `conductor.py:671`，实测 `:1082`（同上）。
- `packages/coding-agent/README.md` 与 `packages/coding-agent/docs/**` **不承载** agent-team-loop / autopilot 的运行期说明（grep 零命中）；本仓 mw 运行期文档惯例在 `packages/multi-workers/README.md` + `packages/multi-workers/docs/`（`rag-config-guide.md` / `dual-toolchain-practice-guide.md`）。因此 9 个可观测面落在 `packages/multi-workers/docs/autopilot-observability-guide.md` + README 链接（见 `report.md` 改动清单）。

## 残留与未验证

1. **G-1（AC-005 子判据）**：重启后复核 pending 门禁未被新自动裁决意外改写的机器检查未实现（全仓无 `answered_at × started_at_ms` 检查代码）。本卡零行为改动，**报告不修**，建议另立卡。
2. **G-2（AC-014）**：无真实无接管会话的运行期长跑；全部证据为测试级（合成 claim 生命周期、人工让位、外机不抢）。多机共享文件系统未实测。
3. **G-3（AC-015）**：默认 `auto_gate_mode=off` + shadow 门槛 ⇒ 生产自动批准占比 0/0（本机 `phase:"decide"` = 0 行）。需先跑影子池（≥5 夜 / ≥20 决策 / 每规则 ≥1 反例）才可能 >0；本卡不启用。
4. **R-1 工具层拦截面未扩大**：收窄后越界写会在 ledger 上报红，但"拦住"仍依赖后续卡（`shared/xkey-gate-guard.ts` 的 `INLINE_WRITE_MARKER_RE` 缺 `write_text`/`write_bytes`/`os.replace`/`shutil.copy2`/`createWriteStream`/`fs.openSync`；`.mw/**` 与 `_autopilot/xkey/**` 无工具层守卫）。
5. **G-4**：`remind-suppressed` 无跨重启专项测试（结构上台账是文件真值即重启安全，但未以测试钉死）。
6. **未在本机产生运行期自动放行样本**：本仓无 `_autopilot/config.json`/`gates/` ⇒ AC-002/004/015 的运行期证据不在本机，全部落在测试语料（`test_mwgal_t11/t12`）。
7. **t15 VC-6 的 `[VERIFY]` 行布尔反义**：外观缺陷（输出行 `nothing_written=_true(... != before)` 应为 `==`），断言正确。本卡不改行为，登记。
8. **本卡未改任何源码/测试逻辑**（零行为改动）；`npm run check` 的 `biome check --write` 可能格式化工作树中其它 session 的既有未提交文件（本卡只对文档负责，逐条归属见 `report.md`）。
9. **未验证 TUI 真实渲染**：AC-001/016 的断言基于 `readMonitorState`/`renderMonitorLines` 纯函数，未起 `/autopilot monitor` 观察真实终端。
10. **未重跑 `packages/multi-workers` 全量 pytest**：本卡只跑 key 定向 + 跨语言锁面（A 组）。全量已知基线含 2 条外仓数据漂移失败（`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`，源自 `H:\git\E2Feature` 外仓基线，T-22 已判定与本 key 无关）。

## 上下文来源

- 需求/设计/计划：`.agenticdoc/mw-autopilot-gate-alarm-liveness/{spec.md,design.md,plan.md}`、`tasks/T-19-closeout.md`、`workers/mwgal-t19-closeout/task.md`
- 对抗式质量门：`.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/report.md`（R-1…R-8 / G-1…G-4 / 逐条 AC 对账）
- 实现卡自证：`workers/mwgal-t10..t22-*/report.md`（尤其 t21-qg-fixes-ts、t22-qg-fixes-python、t17*/t20）
- 文档惯例：`packages/multi-workers/README.md`、`packages/multi-workers/docs/{rag-config-guide.md,dual-toolchain-practice-guide.md}`（`packages/coding-agent/README.md`/`docs/**` grep 无 autopilot/agent-team-loop 命中）
- 运行期：`.mw/serve.meta`（本机旧 3 字段 schema，PID 168160）、`mw status` / `mw doctor` 实测输出（本文件 A 组）
- 目标锚点：`.agenticdoc/goal.md`
