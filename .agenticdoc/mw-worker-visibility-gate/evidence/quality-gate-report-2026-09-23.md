# Quality Gate Report — mw-worker-visibility-gate

- Key: `mw-worker-visibility-gate`
- 日期: 2026-09-23
- 门禁执行: PM（基于 T-5 独立验证的原始产物 + PM 自身复跑；独立验证角色由 T-5 worker 承担）
- 输入: `spec.md`（AC-001~013）、`design.md`（§6 Coverage F1~F6、§7 VC-001~013）、`evidence-requirement.md`、`evidence/verify-independent-2026-09-23.md`、四个 worker 的 `output.md`/`trace.log`

## 0. 证据充分性总览

- **总核查项**: 13 条 AC / 13 条 VC + 6 条交叉项（Q-X）= 32
- **充分（有可机械判定证据）**: 31
- **有条件通过（证据不足，已记录去向）**: 1（Q-X-006）
- **未通过（无证据）**: 0

**门禁结论：✅ 通过**

## 1. AC → VC 逐条证据核查

| AC | VC | 判定 | 证据（原始输出） | 复核方式 |
|----|----|------|------------------|----------|
| AC-001 | VC-001 | ✅ 充分 | `[VERIFY] VC-001: spec_phase_pass=true task_md=true`（T-1 单测 + T-5 探针走真实 `dispatch_worker` 工具入口，夹具 goal.md established） | PM 复跑 5 文件 204/204；读探针原文（报告 §1） |
| AC-002 | VC-002 | ✅ 充分 | `[VERIFY] VC-002: blocked=true design_gap=1 task_dir=false` | 同上；缺项字符串与改造前逐字一致（T-1 用 deep-equal 锁定六项顺序） |
| AC-003 | VC-003 | ✅ 充分 | `[VERIFY] VC-003: blocked=true design_evidence_gap=1` | 同上 |
| AC-004 | VC-004 | ✅ 充分 | `[VERIFY] VC-004: tier=spec design_gaps=0 variants=4`（`—`/`""`/`init`/未知串） | T-1 表驱动 13 拼写 × 两侧；T-5 独立重做 4 变体 |
| AC-005 | VC-005 | ✅ 充分 | `[VERIFY] VC-005: spec_gaps=4 design_gaps=0` | 同上 |
| AC-006 | VC-006 | ✅ 充分 | `[VERIFY] VC-006: agg_lines=1 owner_in_line=true count_in_line=true max_len=36`（T-3）/ `max_len=59`（T-5 独立夹具） | 两方各自的实测长度；D-106 格式逐字段断言 |
| AC-007 | VC-007 | ✅ 充分 | `[VERIFY] VC-007: agg_lines=0 identical_baseline=true` | **最强证据**：T-5 用 `git show HEAD:…ui-bridge.ts` 提取改造前面板模块，同夹具逐行比对，并覆盖 4 种调用形态（缺参/undefined/空 Set/仅本键 Set）；既有 13 处调用零改动 |
| AC-008 | VC-008 | ✅ 充分 | `[VERIFY] VC-008: agg_lines=1 terminal_counted=1` | failed/未 ack 计入聚合计数 |
| AC-009 | VC-009 | ✅ 充分 | `[VERIFY] VC-009: risk_marker=risk=high:1` | 夹具按 `readTaskProgress` 真实解析源（trace.log `[CHECKPOINT] … risk=high`）+ 一条 risk=low 对照，证明 K 只计 high |
| AC-010 | VC-010 | ✅ 充分 | `[VERIFY] VC-010: claim_ids_equal=true headings=7 updated_lines=1 crlf=27->27`；`VC-010 (restoreWatch path): claim_ids_equal=true …` | T-5 覆盖 D-108 的两个调用点（`takeOverKey` 与 `restoreWatch` quiet re-claim）；PM 读 ui-bridge/pm-orchestrator diff 确认两处都调用 sync |
| AC-011 | VC-011 | ✅ 充分（修订语义） | `[VERIFY] VC-011: inserted=true ok=true outside_identical=true` / `no_key_line ok=false untouched=true` / `claim_ok=true warnings=0 claim_ids_equal=true` | AC-011 已按 [REVISED @ 2026-09-23] 修订（D-111）；T-5 明确“旧语义视为 FAIL”并按新语义复现；字节级 `crlf=26->27 lf_only=0 headings=7->7 updated_lines=1->1 bytes=571->597` |
| AC-012 | VC-012 | ✅ 充分 | `[VERIFY] VC-012: coding_at_spec_allowed=true`（T-1 门禁层 + T-3/T-5 工具入口） | T-3 另加 DESIGN 相位反例，证明“传的是真相位而非缺省” |
| AC-013 | VC-013 | ✅ 充分（一次修订） | `[VERIFY] VC-013: pitfalls_entry=true keywords=3 note=两处同值-appears-as-两处必须同值-contiguous-hits=0` | T-5 发现字面缺口后 PM 立即修订 P-011 措辞（`**两处同值**（两处必须同值）`）；修订后本机复核 `索引行=5 / 两处同值=1 / liveness=2` 三处连续命中 |

## 2. 变异反例（对抗性证据充分性）

| 变异 | 目标 | 结果 | 复原 |
|------|------|------|------|
| M-1 | `gateTierOf` 未知串返回 `"design"` | VC-001/VC-004/VC-005 红（SPEC 相位被 design 侧缺项拦下 = 本次修复的事故形态复现） | sha256 `9925fb91…20719` 前后相等 |
| M-2 | 聚合行删除 `risk=high` 段 | VC-009 红（`risk_marker=MISSING`） | sha256 `6a9c5390…d71c6` 前后相等 |
| M-3 | `takeOverKey` 内 sync 调用短路 | VC-010 红（`fileClaim='OLDHOST:1234'` ≠ `indexClaim='WENBOZHOU-PC4:112564'`），且分叉静默无 warning；`restoreWatch` 路径保持绿（证明 D-108 双调用点的必要性） | sha256 相同 |

结论：三处关键判据均具备“改坏即红 + 逐字节复原即绿”的双向证据，不是单向断言。

## 3. 回归与影响面

| 命令 | 结果 | 判定 |
|------|------|------|
| 5 个测试文件（agent-team-loop / phase-docs-gate / pm-state-claim / watch-aggregate / pm-state-sync） | **204 passed / 0 failed**（PM 与 T-5 各自复跑） | ✅ |
| `npm run check`（biome 1092 files + pinned-deps + ts-imports + shrinkwrap + install-lock + tsgo --noEmit + browser-smoke） | **EXIT=0** | ✅ |
| `test/extensions` 全目录 | 537 passed / 4 failed | ⚠️→ 判定为**环境基线**：失败全在 `test/extensions-runner.test.ts`（pi core ExtensionRunner），失败形态 `Hook timed out in 10000ms`，该文件对本 key 改动模块（phase-docs/pm-state-claim/ui-bridge/pm-orchestrator）的引用数为 **0** |
| `audit_phase.py mw-worker-visibility-gate` | VERDICT: PASS（design/plan/tasks/execute 四门） | ✅ |
| `git status --short` 起止 | T-5 起止 15 行逐行相同；PM 终态仅本 key 改动（+3 处会话前既有未跟踪文件） | ✅ |

## 4. 交叉检查（Q-X）

| 编号 | 问题 | 判定 | 说明 |
|------|------|------|------|
| Q-X-001 | 两个派发入口（`dispatch_worker` / `/worker`）是否同改？ | ✅ 充分 | T-3 同任务内改完 `ui-bridge.ts:1093`/`:1498`；T-5 用两个入口各自独立驱动 |
| Q-X-002 | 后台扫描（D-110 第三调用点）是否接线？ | ✅ 充分 | T-3 传目标 key 相位 + 反例用例；T-5 独立重做 DESIGN 拦截与“补齐后可派” |
| Q-X-003 | 面板既有调用是否零改动？ | ✅ 充分 | 既有 13 处调用 + 断言零改动（diff 只有一个 hunk，位于断言计数处且属门禁行为变化）；T-5 逐行基线比对 |
| Q-X-004 | pm-state 写入是否会破坏框架模板？ | ✅ 充分 | 字节级：headings 7→7、`- Updated:` 1→1、行外逐字节相等、CRLF 不翻转、原子写、无 `.tmp` 残留；未复用 `StateManager.write()` |
| Q-X-005 | claim 同步失败是否会阻断 claim？ | ✅ 充分 | `ok` 与 `claimSync` 解耦；M-3 证明短路后分叉静默（正是 warning 存在的理由）；AC-011 修订后“缺 Key 行”才是 warning 条件 |
| Q-X-006 | monitor 的**跨 key** risk 升级投递 | ⚠️ 有条件通过 | 面板现在会显示 `risk=high:K`（AC-009 已验），但 `pm-orchestrator.ts:541-557` 的 PM 升级通知仍只覆盖 watched key → 跨 key 的高风险 worker 不会主动唤醒 PM。**去向**：spec §4 R-3/未决 Q-1，属用户决策项（本次明确选 B2，不含 monitor 改造） |

## 5. 既有测试的语义变更登记（透明性）

- `test/extensions/agent-team-loop.test.ts:1516`：`gaps` 断言由 5 改为 3 + 注释说明（相位分层后该夹具 key 无 pm-state → spec 层 = spec.md + spec 证据 + AC）。这是 D-110 的直接后果，已由 T-3 在同一 hunk 内完成，且该用例其余语义（跳过 / 单次上报 / 文档齐备后派发）原样保留并通过。
- `AC-011` 由"缺行不写 + warning"改为"缺行插行"（D-111）；`design.md` 同步登记 D-110/D-111 与 VC-011 修订。

## 6. 结论

13/13 AC 与 VC 均具备可机械判定的证据（其中 VC-013 经一次措辞修订后成立），3 个变异反例双向成立，回归面无本 key 引入的失败。**质量门禁通过**，可进入 `done`。

遗留项（接受不处理 / 另案）：
- R-1（框架仓库）：`update_index.py claim` 的桩只有三行接口行——`advance_phase.py:313-341` 有**显式**升级路径把它补成完整 7 段模板并保留 Claim-Id，**非缺陷**（本 key 早先的记录已更正）；新行索引 Phase `—`（python claim）/`SPEC`（TS `IndexStore.claim`）与 pm-state 桩 `init` 的 pending 等价性，已在框架仓库用测试钉住（`d0834ae`：`test_update_index.py` VC-030 + `test_audit_phase.py` AG-008 + 两处文档注释，`scripts/`/`core/scripts/`/`claude/scripts/` 三镜像逐字节相同，21 项测试全绿，已推送 `origin/master`）。残留：其他项目（如 OverCode）的 `.agents/skills/agentic-task` clone 仍是旧提交，需各自 `git pull` 或重跑 `install.py` 才会带上。
- R-2：D-111 只在"pm-state 存在但缺 Claim-Id 行"时插行；**新 key 首次 claim 时 pm-state 尚不存在**，此时仍回一条 `pm-state.md missing` warning（有意为之：镜像未建立）。`advance_phase` 建好文件后，下一次 claim/takeover 会插行收敛。
- R-3（API 形状）：`phaseDocGaps(status, tier?)` 的 tier 缺省为 `design`（为保住既有 9 处单参调用）。未来新增调用点若忘记传 tier，会静默回到"六项全查"。建议在既有单参调用清零后把参数改为必填。
- R-4（环境基线）：`test/extensions-runner.test.ts` 的 4 个 hook 超时失败与本次改动无关（该文件零引用本 key 模块），归入 Windows 基线，不在本 key 处理。
- Q-X-006：跨 key risk 升级投递待用户决定（见 §4）。
