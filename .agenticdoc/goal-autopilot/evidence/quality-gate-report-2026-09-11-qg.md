# Quality Gate Report: goal-autopilot

**时间**: 2026-09-11（修复轮冻结证据）  
**触发**: 合入前，全量质检（第 4 次运行）  
**范围**: spec AC-001~025、design VC-001~027、Coverage Matrix F1~F15、Function Flow、非功能约束与任务 Error Fingerprint  
**判定合同**: VC-018 按 2026-09-10 用户批准 erratum；平台按 Windows-only erratum，Q-X-UNIX 已关闭且不生成

## 前置门禁

| 检查项 | 结果 | 独立核查证据 |
|---|---|---|
| spec.md 存在 AC 编号 | PASS | `spec.md` §3，机械提取 AC-001~025，共 25 项 |
| design.md 存在 VC 编号 | PASS | `design.md` §7，VC-001~027，共 27 项 |
| AC→VC 映射覆盖 100% | PASS | `design.md` §8；机械比对 spec=25、mapping=25、missing=[] |
| evidence-requirement.md 存在 | PASS | `evidence-requirement.md` 存在且列出 25 AC / 27 VC 的充分性标准 |
| ac_fingerprint 一致 | PASS | 规范 bash 管道复算 `ccc2c018e052`，记录值同为 `ccc2c018e052` |
| evidence/baseline/ 非空 | PASS | `evidence/baseline/baseline-manual-suites.md` |
| 每个 task 有非空 ac_refs/vc_refs | PASS | `tasks/T-01~T-18*.md`，机械检查 18/18，empty_refs=[] |
| Error Fingerprint 无本 key open error | PASS | 逐读 18 个任务；任务内实现/测试错误均已修复或已处置。T-18 E1 已加固并列已知平台限制；E2b 的原子 edit 失误已通过 v3 指纹实际落盘及本次复算关闭。packages/ai tsgo 项为既存外部基线，不是本 key Error Fingerprint |

前置门禁 8/8 通过。未发现 `.migrator/config.json`，按工作流跳过 migrator 集成。

## 证据索引说明

以下结论独立读取/检索原始证据，不转抄 `final-verification.md` 的结论：

- `L1`: `evidence/runs/l1-verify-lines.log`（110 条 `[VERIFY]`，20 个 VC；末尾 367 passed）
- `L0`: `evidence/runs/l0-parity-final.log`（5/5）
- `L2`: `evidence/runs/l2-e2e-final.log`（7/7；10 组 `[VERIFY]`）
- `TS-src`: `packages/coding-agent/test/suite/autopilot-*.test.ts` 中 `it("VC-...` 测试名（15 个具名测试）
- `TS-run`: `evidence/runs/vitest-autopilot-final.log`（3 files / 59 tests passed）
- `BASE`: `evidence/baseline/baseline-manual-suites.md`
- `REG`: `evidence/runs/l1-python-final.log`、`vitest-agent-team-loop-final.log`、`e2e-real-final.log`、`smoke-final.log`

## 问题清单与核查结果

### A. AC 功能正确性

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-AC-001 | roadmap 三要素与校验是否正确 | ✅ 充分 | L1 VC-001 ×18；L2 VC-002 | 正常、缺项、依赖边界及真实 stub 产物均覆盖 |
| Q-AC-002 | stage-confirm 未答阻塞、答后及时派发是否正确 | ✅ 充分 | L1 VC-003；L2 VC-004 `delay_ms=968 interval_ms=1000` | 未答 0 派发；答后小于 2×interval |
| Q-AC-003 | stage 闭环 dossier 是否包含 L3 裁决/证据并创建下一 gate | ✅ 充分 | L1 VC-005 `dossier_verdict=meets report=l3-report.md verdict_file=true`；VC-005 closure 行 | meets→done→closure dossier 双层证据，下一 gate pending 且 next rows=0 |
| Q-AC-004 | ready key 是否及时并行派发 | ✅ 充分 | L2 VC-006 `parallel_dispatch=2 delay_ms=1979` | 两 key 并存且 <10s |
| Q-AC-005 | Phase/goal 零直写且只经脚本推进是否正确 | ✅ 充分 | L0 VC-007 ×2；L1 VC-007 | 静态 0 命中，运行期 advance exit 0/1 schema 均覆盖 |
| Q-AC-006 | L3 不收敛后的 stalled 全链路是否正确 | ✅ 充分 | L1 VC-008；VC-012 below-twice | 四产物、依赖阻塞、独立 key 继续 |
| Q-AC-007 | L1 dossier 双样例与结构是否正确 | ✅ 充分 | L1 VC-009 ×4 | complete=0、missing=1、gaps 非空、映射 parity |
| Q-AC-008 | L1↔L2 达上限后是否停止第 3 轮并建 gate | ✅ 充分 | L1 VC-010 | round3_rows=0、gate_pending=true |
| Q-AC-009 | verifier 定点读取拒绝与留痕是否正确 | ✅ 充分 | TS-src `autopilot-read-scope.test.ts:362`；TS-run 59/59 | block reason、output 留痕与界内放行同时断言 |
| Q-AC-010 | L3 二值裁决、repair 与收敛上限是否正确 | ✅ 充分 | L1 VC-012 meets / below-twice | meets 落盘；below→repair→复评；超限 stalled |
| Q-AC-011 | budget=1 是否同时约束三类回路 | ✅ 充分 | L1 VC-013：基础 L1↔L2 行、`loop=l3`、`loop=task-retry` | 三回路均 second_round_rows=0；L3/retry 均 escalated=stalled |
| Q-AC-012 | disabled 零足迹且手动工作流零回归是否正确 | ✅ 充分 | L2 VC-014；BASE；REG | 无 PID/状态行/写入；e2e_real 1、smoke 9/0、既有套件零失败 |
| Q-AC-013 | live claim skip 与 force takeover 后停派发是否正确 | ✅ 充分 | L1 VC-015 | skip_rows=0、skip event、post-takeover rows=0 |
| Q-AC-014 | EXECUTE 中途接手且不改既有 artifact 是否正确 | ✅ 充分 | L1 VC-016 | resumed_phase=EXECUTE、mtime unchanged |
| Q-AC-015 | console 仅凭文件重建、回放与视图奇偶是否正确 | ✅ 充分 | TS-src VC-017 ×5；TS-run | JSON、重开、view parity、水位回放覆盖 |
| Q-AC-016 | gate 回答是否在首个后续 tick 内消费 | ✅ 充分 | L2 VC-018 `delay_ms=967 interval_ms=1000 slack_ms=250 pass=true` | 满足修订合同 delay ≤ interval + tick 开销；测试断言 slack=250ms |
| Q-AC-017 | 状态转换时间线是否完整且 key 非 null | ✅ 充分 | L1 VC-019 ×16+ | 全事件、seq、哨兵、轮转和追加失败容错 |
| Q-AC-018 | console rounds 与 JSON/Python 推导是否一致 | ✅ 充分 | L1 VC-020；TS-src VC-020 ×3 | distinct-attempt 与 fallback 均覆盖 |
| Q-AC-019 | 60s 内 beat ≥12 是否正确 | ✅ 充分 | L2 VC-021 `beats=15 window_ms=60000` | 默认 4s 间隔，满足阈值 |
| Q-AC-020 | 并发写完整性与零丢失是否正确 | ✅ 充分 | L2 VC-022 `human_writes=291 conductor_rows=25 pass=true` | 60s 锁协议压测通过 |
| Q-AC-021 | typed allowlist、未知拒绝、worker fail-closed 是否正确 | ✅ 充分 | L0 VC-023 ×3；L1 VC-023；TS-src VC-023 ×5 | 双侧精确奇偶、未知 0 行、worker exit 1、手动 fallback 保留 |
| Q-AC-022 | conductor 真进程被杀并重启后是否满足恢复不变量 | ✅ 充分 | L2 VC-024 `kill=real-process respawned=true ...`; L1 VC-024 | 真 taskkill→新 PID；无重派、预算与 mtime 不变、[START]=1 |
| Q-AC-023 | worker 失败是否入预算且不阻塞其他 key | ✅ 充分 | L1 VC-025 ×2；VC-013 task-retry | exit1、spawn/watchdog、budget=1 与 other_key_rows≥1 |
| Q-AC-024 | stage/stalled reject 语义是否正确 | ✅ 充分 | L1 VC-026 | 一次重提、二拒停、遗留关闭解锁 |
| Q-AC-025 | enable 后 conductor 与提案是否及时启动 | ✅ 充分 | L2 VC-027 `delay_ms=748 interval_ms=1000`；L1 VC-027 | status/提案链与 act-then-sleep 均覆盖 |

### B. VC 证据充分性

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-VC-001 | roadmap_check 正反样例 | ✅ 充分 | L1 VC-001 ×18 | 完整、缺失、边界与格式容错 |
| Q-VC-002 | roadmap-writer 产物校验 | ✅ 充分 | L2 VC-002 | stages_valid=all，exit 0 |
| Q-VC-003 | 未答 gate ≥3 tick 零派发 | ✅ 充分 | L1 VC-003 | ticks=3 rows=0 |
| Q-VC-004 | stage 回答至首派发 ≤2 interval | ✅ 充分 | L2 VC-004 | 968ms ≤ 2000ms |
| Q-VC-005 | stage 闭环、gate、下一 stage 阻塞及裁决链 | ✅ 充分 | L1 VC-005 closure + dossier_verdict | 文件、pending gate、0 rows、meets/report/verdict 文件 |
| Q-VC-006 | 双 key 并行且 <10s | ✅ 充分 | L2 VC-006 | parallel=2，1979ms |
| Q-VC-007 | 零直写与脚本 exit code | ✅ 充分 | L0 VC-007 ×2 | 静态 + 运行期双证 |
| Q-VC-008 | stalled 四产物与依赖传播 | ✅ 充分 | L1 VC-008 | 4/0/1 |
| Q-VC-009 | audit 双样例 | ✅ 充分 | L1 VC-009 | 三键、缺口、AC 提取和映射 |
| Q-VC-010 | 第三轮零派发与 gate | ✅ 充分 | L1 VC-010 | 符合充分性标准 |
| Q-VC-011 | read_scope block/log/allow | ✅ 充分 | TS-src VC-011；TS-run | 三断言同一具名用例，扩展边界用例共 19 个 |
| Q-VC-012 | L3 二值/复评/产物 | ✅ 充分 | L1 VC-012；L2 full-chain | meets、below、repair、done 事务 |
| Q-VC-013 | budget=1 三回路 | ✅ 充分 | L1 VC-013 三类回路行 | L1↔L2、L3、task-retry 均一轮升级且无第二轮 |
| Q-VC-014 | disabled 隔离与基线全绿 | ✅ 充分 | L2 VC-014；BASE；REG | 进程、写入、既有套件闭合 |
| Q-VC-015 | claim skip/takeover | ✅ 充分 | L1 VC-015 | 双方向 0 行 |
| Q-VC-016 | EXECUTE 接手 mtime | ✅ 充分 | L1 VC-016 | resumed + unchanged |
| Q-VC-017 | console JSON/重建/奇偶 | ✅ 充分 | TS-src VC-017 ×5；TS-run | 具名测试闭合 |
| Q-VC-018 | 修订后的首 tick gate 消费阈值 | ✅ 充分 | L2 VC-018 | 967ms ≤ 1000ms + 250ms，pass=true |
| Q-VC-019 | 时间线全事件/schema | ✅ 充分 | L1 VC-019 | per_type=all、key 非 null、轮转/容错 |
| Q-VC-020 | rounds parity | ✅ 充分 | L1 VC-020；TS-src VC-020 ×3 | Python/TS 同源推导 |
| Q-VC-021 | 60s beat | ✅ 充分 | L2 VC-021 | beats=15 |
| Q-VC-022 | 并发写 60s | ✅ 充分 | L2 VC-022 | pass=true；测试源码断言 parse/loss 不变量 |
| Q-VC-023 | 注册表奇偶/拒绝/fail-closed | ✅ 充分 | L0 VC-023 ×3；L1；TS-src | 静态与动态双证 |
| Q-VC-024 | 真 kill/respawn | ✅ 充分 | L2 VC-024；`test_autopilot_e2e.py:test_conductor_kill_respawn` | 真进程、新 PID、续推及四项不变量 |
| Q-VC-025 | 失败计预算且他 key 继续 | ✅ 充分 | L1 VC-025 ×2 | 两类失败注入，other rows=1 |
| Q-VC-026 | reject 语义 | ✅ 充分 | L1 VC-026 | 三分支覆盖 |
| Q-VC-027 | enable 链路时限 | ✅ 充分 | L2 VC-027；L1 VC-027 | 748ms ≤ interval |

### C. Coverage Matrix

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-COV-F1 | roadmap 正常/边界/缺项路径 | ✅ 充分 | L1 VC-001；L2 VC-002 | — |
| Q-COV-F2 | stage gate 阻塞/放行/损坏回答 | ✅ 充分 | L1 VC-003；L2 VC-004/018；L1 全量 367 passed | 损坏 frontmatter 用例包含于冻结套件 |
| Q-COV-F3 | stage closure 与下一 stage 阻塞 | ✅ 充分 | L1 VC-005 ×2 | 含修复后的 L3 裁决链 |
| Q-COV-F4 | L1 clean/L2 repair/超限 | ✅ 充分 | L1 VC-007/010/013 | — |
| Q-COV-F5 | exec done/retry/超限 stalled | ✅ 充分 | L1 VC-025、VC-013 task-retry | — |
| Q-COV-F6 | L3 meets/repair/不收敛 | ✅ 充分 | L1 VC-012、VC-013 l3 | — |
| Q-COV-F7 | stalled 产物/传播/reject 遗留关闭 | ✅ 充分 | L1 VC-008/026 | — |
| Q-COV-F8 | 默认预算与 budget=1 全回路 | ✅ 充分 | L1 VC-013 三回路 | 修复轮补齐 L3 与 task-retry |
| Q-COV-F9 | claim/force/stale | ✅ 充分 | L1 VC-015；state claim 四态行 | — |
| Q-COV-F10 | console 正常/重开/回放/奇偶 | ✅ 充分 | TS-src VC-017/020；TS-run | — |
| Q-COV-F11 | 时间线转移/节拍/轮转/追加失败 | ✅ 充分 | L1 VC-019；L2 VC-021 | — |
| Q-COV-F12 | 并发写/高频/完整性 | ✅ 充分 | L2 VC-022 | 60s 压测 |
| Q-COV-F13 | 真崩溃重启与不变量 | ✅ 充分 | L2 VC-024；L1 VC-024 | 真进程 kill/serve respawn + 状态单测 |
| Q-COV-F14 | disabled/enable/框架缺失 | ✅ 充分 | L2 VC-014/027；L1 VC-027 missing-framework | — |
| Q-COV-F15 | 五类型/奇偶/未知拒绝 | ✅ 充分 | L0 VC-023；TS-src VC-023 | — |

### D. 交叉问题与二次印证补项

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-X-GOAL | goal.md 变更是否 halt 且幂等创建 gate | ✅ 充分 | L1 VC-021 goal-change 行 | repeat 后 gate=1、halted-goal-change |
| Q-X-CREDENTIAL | autopilot worker 是否继承 provider 凭证隔离 | ✅ 充分 | 统一 launcher 路径；L1 全量 367 passed；BASE/REG | conductor 只入队，凭证由 launcher `_build_env` 隔离 |
| Q-X-WATCHDOG | worker 失败/看门狗是否入预算且隔离其他 key | ✅ 充分 | L1 VC-025 spawn-watchdog；VC-013 task-retry | stalled 与 other_key_rows=1 |
| Q-X-MULTIPROJECT | 多项目是否各自独立 conductor/队列且故障互不影响 | ✅ 充分 | L2 `[VERIFY] MULTI-PROJECT: conductors=2 per_project_pids=true queues_isolated=true p2_unaffected=true p1_respawned=true` | 双 serve 实例；杀 p1 conductor 不影响 p2 |
| Q-X-L3-DOSSIER | L3 verdict 是否落入 closure dossier 裁决字段 | ✅ 充分 | L1 VC-005 `dossier_verdict=meets report=l3-report.md verdict_file=true`；对应源码断言 | l3-verdict.txt + l3-report.md + dossier 行闭合 |

> Q-X-UNIX 未生成：spec §2.1 已按用户 2026-09-10 裁决修订为 Windows-only，Unix/Linux 明确出范围。

## 遗留清单复核

对 `evidence/runs/final-verification.md` §5 的限制逐项复核：

1. Windows tmp→replace 窗口：在文档化锁协议下 VC-022 60s 压测零丢失；读侧具备重试/容错。属于平台已知限制，不形成当前 AC 欠债。
2. L2 caps 未由 dispatch 显式写入：worker 默认 8/65536，cap-file/cap-byte 机制已有定向单测；真实 workload 标定是运维调优，不影响 AC-009 的安全边界判定。
3. VC-022 以双方遵守 O_CREAT|O_EXCL 锁协议为前提：该前提就是 GC-4/D-113 合同；裸写不在验收范围。
4. AC-005 静态扫描无法穷尽任意变量间接：L0 静态扫描与运行期 advance exit-code 双证互补，证据充分。
5. e2e_l2 默认排除：冻结证据已按完整窗口独立运行 7/7，不形成缺证。
6. 并行会话工作树：冻结验证在同一工作树完成；属于合入顺序管理事项，不改变本 key 功能证据。
7. L3 dossier 裁决字段：修复轮已关闭，见 Q-AC-003 / Q-VC-005 / Q-X-L3-DOSSIER。

补充说明：`npm-check-final.log` 的全仓 `npm run check` 因 packages/ai 既存类型错误非零结束；不能表述为“全仓 check 通过”。本 key 涉及的 coding-agent 检查及定向套件无新增错误，此项不映射本 key AC/VC，故不降级本报告。

## 汇总

- **总问题数**: 72
- **通过（充分）**: 72（100%）
- **有条件通过（不足）**: 0（0%）
- **未通过（无证据）**: 0（0%）

**质检结论**: ✅ 通过。符合全量合入前口径：无 ❌、无 ⚠️。

## 未通过问题行动计划

无。

## 二次印证结论

- spec 的平台、性能、安全约束均已覆盖；VC-018 按修订合同检查，967ms/1000ms/250ms 为 PASS；Windows-only 边界明确。
- Function Flow §5.1~§5.4 各节点均至少映射一个 Q-AC/Q-VC/Q-COV；L3→stage dossier 的交叉链已由修复轮证据闭合。
- Coverage Matrix F1~F15 全部机械生成问题并核查；正常、边界、异常路径均有冻结证据。
- 18/18 task 的 ac_refs/vc_refs 非空；无遗漏绑定。
- Error Fingerprint 全关闭：T-18 E1 已处置，E2b 已由实际指纹落盘和本次规范复算验证；无本 key open error。
- 多项目隔离已由双 serve 真进程 E2E 覆盖；Unix 依据用户裁决不属于本次问题空间。
