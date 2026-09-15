# Quality Gate Report: goal-autopilot

**时间**: 2026-09-10T17:49:37+08:00  
**触发**: 合入前，全量质检（第 3 次运行）  
**范围**: spec AC-001~025、design VC-001~027、Coverage Matrix F1~F15、Function Flow、非功能约束与任务 Error Fingerprint

## 前置门禁

| 检查项 | 结果 | 证据 |
|---|---|---|
| spec.md 存在 AC 编号 | PASS | `spec.md` §3，AC-001~025，共 25 项 |
| design.md 存在 VC 编号 | PASS | `design.md` §7，VC-001~027，共 27 项 |
| AC→VC 映射覆盖 100% | PASS | `design.md` §8，25/25 AC 均有 VC |
| evidence-requirement.md 存在 | PASS | `evidence-requirement.md` |
| ac_fingerprint 一致 | PASS | 规范命令复算 `ccc2c018e052`；`evidence-requirement.md:9` 记录值相同 |
| evidence/baseline/ 非空 | PASS | `evidence/baseline/baseline-manual-suites.md` |
| 每个 task 有非空 ac_refs/vc_refs | PASS | `tasks/T-01~T-18*.md`，18/18 均非空 |
| Error Fingerprint 无本 key open error | PASS | T-01~T-18：实现/测试错误均“已修复/已处置/无需处置”；packages/ai tsgo 项明确为存量、非本 key |

前置门禁全部通过，继续执行全量证据链核查。

## 证据索引说明

- `L1`：`evidence/runs/l1-verify-lines.log`
- `L0`：`evidence/runs/l0-parity-final.log`
- `L2`：`evidence/runs/l2-e2e-final.log`
- `TS-src`：`packages/coding-agent/test/suite/autopilot-*.test.ts` 中含 VC 编号的测试名
- `TS-run`：`evidence/runs/vitest-autopilot-final.log:37`（59 passed）
- `BASE`：`evidence/baseline/baseline-manual-suites.md`
- `REG`：`evidence/runs/l1-python-final.log:19`（363 passed）、`vitest-agent-team-loop-final.log:16`（106 passed）、`e2e-real-final.log:11`（1 passed）、`smoke-final.log:24`（9/0）

## 问题清单与核查结果

### A. AC 功能正确性

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-AC-001 | roadmap 三要素与校验是否正确 | ✅ 充分 | L1:60-77；L2:4 | 正常、缺项、依赖边界均覆盖 |
| Q-AC-002 | stage-confirm 未答阻塞、答后及时派发是否正确 | ✅ 充分 | L1:24-25；L2:6 | 0 派发；1021ms ≤ 2×1000ms |
| Q-AC-003 | stage 闭环 dossier 是否包含 L3 裁决/证据并创建下一 gate | ⚠️ 不足 | L1:26；`final-verification.md:85` | 已证实 dossier/gate/阻塞，但 `l3-verdict.txt` 与 dossier 裁决字段未单独断言 |
| Q-AC-004 | ready key 及时并行派发是否正确 | ✅ 充分 | L2:11 | 263ms，parallel=2 |
| Q-AC-005 | Phase/goal 零直写且只经脚本推进是否正确 | ✅ 充分 | L0:4,8；L1:12,55-56 | 静态与运行期双证 |
| Q-AC-006 | L3 两轮 below 后 stalled 全链路是否正确 | ✅ 充分 | L1:17,22 | 四产物、依赖阻塞、独立 key 继续 |
| Q-AC-007 | L1 dossier 双样例与结构是否正确 | ✅ 充分 | L1:1-4 | complete=0、missing=1、gaps 非空 |
| Q-AC-008 | L1↔L2 达上限后停止第 3 轮并建 gate 是否正确 | ✅ 充分 | L1:13 | rows=0、gate pending |
| Q-AC-009 | verifier 定点读取拒绝与留痕是否正确 | ✅ 充分 | TS-src `autopilot-read-scope.test.ts:362`；TS-run | block reason、trace/output 留痕、界内放行 |
| Q-AC-010 | L3 二值裁决、repair 与两轮收敛是否正确 | ✅ 充分 | L1:21-22 | meets 与 below-twice 两路均覆盖 |
| Q-AC-011 | budget=1 是否同时约束 L1↔L2、L3、task retry | ⚠️ 不足 | L1:14；`test_autopilot_conductor.py:612` | 冻结证据只明确断言 L1↔L2；未给出三回路各自升级及第二轮 0 行的同配置证据 |
| Q-AC-012 | disabled 零足迹且手动工作流零回归是否正确 | ✅ 充分 | L2:23；REG；BASE | 隔离证据与四套基线对照闭合 |
| Q-AC-013 | live claim skip 与 force takeover 后停派发是否正确 | ✅ 充分 | L1:15,78；`test_autopilot_conductor.py:615-649` | 两方向均断言 0 行 |
| Q-AC-014 | EXECUTE 中途接手且不改既有 artifact 是否正确 | ✅ 充分 | L1:16,79 | phase 恢复、3 个 mtime 不变 |
| Q-AC-015 | console 仅凭文件重建、回放与视图奇偶是否正确 | ✅ 充分 | TS-src `autopilot-console.test.ts:336,386,414,812,833`；TS-run | 重开、JSON、人读视图、水位均覆盖 |
| Q-AC-016 | gate 回答后是否 ≤1 interval 消费推进 | ⚠️ 不足 | L2:5；`test_autopilot_e2e.py:492-516` | 实测 1021ms > 1000ms；测试额外放宽 250ms，却输出 `pass=true`，不满足锁定阈值 |
| Q-AC-017 | 状态转换时间线是否完整且 key 非 null | ✅ 充分 | L1:18,85-100 | 事件 schema/枚举、seq、key 哨兵、失败容错均有证据 |
| Q-AC-018 | console rounds 与 JSON/Python 推导是否一致 | ✅ 充分 | L1:80-81；TS-src `autopilot-console.test.ts:471,500,520`；TS-run | distinct-attempt 与 fallback 均覆盖 |
| Q-AC-019 | 60s 内 beat ≥12 是否正确 | ✅ 充分 | L2:15 | 60s/4s 实测 15 |
| Q-AC-020 | 并发写完整性与零丢失是否正确 | ✅ 充分 | L2:19 | 60s，294 human + 24 conductor，锁协议下通过 |
| Q-AC-021 | typed allowlist、未知拒绝、worker fail-closed 是否正确 | ✅ 充分 | L0:12,16,20；L1:38-44,57-59；TS-src `autopilot-protocol.test.ts:236-301` | 双侧精确奇偶与双保险闭合 |
| Q-AC-022 | conductor 真进程被杀并重启后是否满足恢复不变量 | ⚠️ 不足 | L1:23,82-84；`test_autopilot_conductor_exec.py:514-553` | 测试仅新建 `ConductorState` 模拟重启，并手工写 `[START] pid=4242`；没有真实 kill/respawn 进程证据 |
| Q-AC-023 | worker 各失败形态是否入预算且不阻塞其他 key | ✅ 充分 | L1:19-20 | exit1 与 spawn/watchdog 注入均覆盖 |
| Q-AC-024 | stage/stalled reject 语义是否正确 | ✅ 充分 | L1:27-28,52-54 | 一次重提、二拒停、遗留关闭解锁 |
| Q-AC-025 | enable 后 conductor 与提案是否在时限内启动 | ✅ 充分 | L2:24；L1:8-9,29-37 | 752ms ≤ 1000ms，act-then-sleep 有单测 |

### B. VC 证据充分性

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-VC-001 | roadmap_check 正反样例证据是否充分 | ✅ 充分 | L1:60-77 | 18 个输出面 |
| Q-VC-002 | roadmap-writer 真实产物校验证据是否充分 | ✅ 充分 | L2:4 | stages_valid=all，exit 0 |
| Q-VC-003 | 未答 gate ≥3 tick 零派发证据是否充分 | ✅ 充分 | L1:24-25 | rows=0，pending gate=1 |
| Q-VC-004 | stage 回答至首派发 ≤2 interval 证据是否充分 | ✅ 充分 | L2:6 | 1021ms ≤ 2000ms |
| Q-VC-005 | stage 闭环文件/gate/下一 stage 阻塞证据是否充分 | ✅ 充分 | L1:26 | 三项均满足 evidence-requirement |
| Q-VC-006 | 双 key 并行与 <10s 证据是否充分 | ✅ 充分 | L2:11 | 263ms，parallel=2 |
| Q-VC-007 | 零直写与脚本 exit code 证据是否充分 | ✅ 充分 | L0:4,8 | 静态 0 命中 + exit 0/1 |
| Q-VC-008 | stalled 四产物与依赖传播证据是否充分 | ✅ 充分 | L1:17 | 4/0/1 |
| Q-VC-009 | audit 双样例证据是否充分 | ✅ 充分 | L1:1-4 | JSON 三键、缺口与映射 parity |
| Q-VC-010 | 第三轮零派发与 gate 证据是否充分 | ✅ 充分 | L1:13 | 符合标准 |
| Q-VC-011 | read_scope block/log/allow 三断言证据是否充分 | ✅ 充分 | TS-src `autopilot-read-scope.test.ts:362`；TS-run | 具名测试 + 59/59 |
| Q-VC-012 | L3 二值/复评/产物证据是否充分 | ✅ 充分 | L1:21-22；L2 full-chain | meets、below、repair、done 事务 |
| Q-VC-013 | budget=1 三回路证据是否充分 | ⚠️ 不足 | L1:14 | 输出缺 `escalations=3`，源码测试只覆盖 L1↔L2 |
| Q-VC-014 | disabled 隔离与基线全绿证据是否充分 | ✅ 充分 | L2:23；REG；BASE | 进程/写入/四套基线闭合 |
| Q-VC-015 | claim skip/takeover 证据是否充分 | ✅ 充分 | L1:15,78 | 源码断言补足 takeover |
| Q-VC-016 | EXECUTE 接手 mtime 证据是否充分 | ✅ 充分 | L1:16 | resumed + unchanged |
| Q-VC-017 | console JSON/重建/奇偶证据是否充分 | ✅ 充分 | TS-src `autopilot-console.test.ts:336,386,414,812,833`；TS-run | 具名测试闭合 |
| Q-VC-018 | gate 消费 ≤interval 证据是否充分 | ⚠️ 不足 | L2:5；`test_autopilot_e2e.py:501-512` | 1021ms 超过 1000ms；250ms grace 不在 VC 合同中 |
| Q-VC-019 | 时间线全事件/schema 证据是否充分 | ✅ 充分 | L1:18,85-100 | per_type=all、key 非 null、追加/轮转容错 |
| Q-VC-020 | rounds parity 证据是否充分 | ✅ 充分 | L1:80-81；TS-src `autopilot-console.test.ts:471-536` | Python/TS 同源推导 |
| Q-VC-021 | 60s beat 证据是否充分 | ✅ 充分 | L2:15 | beats=15 |
| Q-VC-022 | 并发写 60s 证据是否充分 | ✅ 充分 | L2:19 | parse/loss 断言由测试源码执行后 PASS |
| Q-VC-023 | 注册表奇偶/拒绝/fail-closed 证据是否充分 | ✅ 充分 | L0:12,16,20；TS-src `autopilot-protocol.test.ts:236-301` | 静态+动态齐全 |
| Q-VC-024 | 真 kill/restart 证据是否充分 | ⚠️ 不足 | L1:23；`test_autopilot_conductor_exec.py:514-553` | 文件状态重建单测，不是真进程杀重启测试 |
| Q-VC-025 | 失败计预算且他 key 继续证据是否充分 | ✅ 充分 | L1:19-20 | 两类注入、other rows=1 |
| Q-VC-026 | reject 语义证据是否充分 | ✅ 充分 | L1:27-28,52-54 | 三分支均覆盖 |
| Q-VC-027 | enable 链路时限证据是否充分 | ✅ 充分 | L2:24；L1:8-9 | 752ms ≤ interval |

### C. Coverage Matrix

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-COV-F1 | roadmap 正常/边界/缺项路径是否覆盖 | ✅ 充分 | L1:60-77；L2:4 | — |
| Q-COV-F2 | stage gate 阻塞/放行/损坏回答路径是否覆盖 | ✅ 充分 | L1:24-25；L2:6；REG | 损坏 gate 源码用例包含于 363 passed |
| Q-COV-F3 | stage closure 与下一 stage 阻塞路径是否覆盖 | ✅ 充分 | L1:26 | 文件、pending gate、0 rows |
| Q-COV-F4 | L1 clean/L2 repair/超限路径是否覆盖 | ✅ 充分 | L1:12-14 | — |
| Q-COV-F5 | exec done/retry/超限 stalled 路径是否覆盖 | ✅ 充分 | L1:19-20 | — |
| Q-COV-F6 | L3 meets/repair/两轮不收敛路径是否覆盖 | ✅ 充分 | L1:21-22 | — |
| Q-COV-F7 | stalled 产物/传播/reject 遗留关闭是否覆盖 | ✅ 充分 | L1:17,27 | — |
| Q-COV-F8 | 默认预算与 budget=1 全回路路径是否覆盖 | ⚠️ 不足 | L1:14 | budget=1 只明确覆盖 L1↔L2，未覆盖 L3/retry |
| Q-COV-F9 | claim/force/stale 路径是否覆盖 | ✅ 充分 | L1:15,78 | — |
| Q-COV-F10 | console 正常/重开/回放/奇偶路径是否覆盖 | ✅ 充分 | TS-src console VC-017/020；TS-run | — |
| Q-COV-F11 | 时间线转移/节拍/轮转/追加失败是否覆盖 | ✅ 充分 | L1:85-100；L2:15 | — |
| Q-COV-F12 | 并发写/高频/完整性失败检测是否覆盖 | ✅ 充分 | L2:19 | 60s 压测 |
| Q-COV-F13 | 真崩溃重启与不变量是否覆盖 | ⚠️ 不足 | L1:23；`test_autopilot_conductor_exec.py:514-553` | 仅内存状态对象重建，不含真实进程 kill/serve respawn |
| Q-COV-F14 | disabled/enable/框架缺失路径是否覆盖 | ✅ 充分 | L2:23-24；L1:33 | — |
| Q-COV-F15 | 五类型/奇偶/未知拒绝路径是否覆盖 | ✅ 充分 | L0:12,16,20 | — |

### D. 交叉问题与二次印证补项

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-X-GOAL | goal.md 变更是否 halt 且幂等创建 gate | ✅ 充分 | L1:6-7 | 重复 tick 后 gates=1，status=halted-goal-change |
| Q-X-CREDENTIAL | autopilot worker 是否继承 provider 凭证隔离 | ✅ 充分 | `test_launcher.py:111-185,208-224`；REG | 队列统一走 launcher；目标 key 全量 Python 回归通过 |
| Q-X-WATCHDOG | worker 失败/看门狗路径是否进入预算且隔离其他 key | ✅ 充分 | L1:19-20 | 注入证据满足失败收敛合同 |
| Q-X-UNIX | Windows + Unix 双平台锁/原子替换/newline 是否均有运行证据 | ❌ 无证据 | — | 冻结证据环境全部为 Windows；未找到 Unix/Linux/macOS 运行日志 |
| Q-X-MULTIPROJECT | mw serve 托管多项目时是否每项目独立 conductor、无共享状态 | ❌ 无证据 | — | 未找到双项目并行 serve/conductor 隔离测试或运行日志 |
| Q-X-L3-DOSSIER | L3 verdict 是否落入 stage closure dossier 的裁决字段 | ⚠️ 不足 | `final-verification.md:85` | 已知低风险限制：`l3-verdict.txt` 未单独断言，跨 F6→F3 交互证据未闭合 |

## 遗留清单复核

`final-verification.md:79-85` 的 7 项逐项判定：

1. Windows replace 窗口：锁协议下 60s 数据完整性已证实，属于已知平台限制，不单独降级 AC-020。
2. L2 cap 使用默认值：cap 机制已有单测；真实 LLM 容量未标定是运维调优项，不改变当前 AC/VC 判定。
3. VC-022 依赖文档化锁协议：与 GC-4/D-113 的系统前提一致；裸写不在验收合同内。
4. AC-005 静态扫描限度：已有运行期 advance exit-code 二次印证，不单独降级。
5. e2e_l2 默认排除：冻结证据已完整运行 5/5，不构成缺证。
6. 并行会话工作树：本次证据在同一工作树全绿，但后续合入应确保相关提交顺序；不改变本报告证据状态。
7. L3 dossier 裁决字段未单独断言：形成 Q-AC-003 / Q-X-L3-DOSSIER 验证欠债。

## 汇总

- **总问题数**: 73
- **通过（充分）**: 61（83.6%）
- **有条件通过（不足）**: 10（13.7%，验证欠债 10 项）
- **未通过（无证据）**: 2（2.7%）

**质检结论**: ❌ 未通过。合入前口径要求无 ❌ 且无 ⚠️；当前存在 2 项无证据和 10 项证据不足。

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|---|---|---|---|
| Q-X-UNIX | 证据仅来自 Windows | 在 Linux/Unix runner 执行 L0/L1、TS 三套件及锁/newline 定向 E2E，冻结原样日志 | reopen T-18 / 新平台验证 task |
| Q-X-MULTIPROJECT | T-16 仅单项目 fixture | 新增双项目 `mw serve` 集成测试：两个 enabled 项目各自 PID/timeline/queue，停止或崩溃一个不影响另一个 | reopen T-16 |
| Q-AC/VC-016/018 | 测试允许合同外 250ms grace；冻结结果 1021ms > 1000ms | 删除或明确排除合同外 grace；以事件时间戳/更稳健采样重跑，必须得到 `delay <= interval` | reopen T-16 |
| Q-AC/VC-011/013、Q-COV-F8 | budget=1 只明确验证 L1↔L2 | 同一 `round_budget=1` fixture 分别驱动 L2、L3、exec retry，输出 `escalations=3` 且每类第二轮 rows=0 | reopen T-10/T-12 |
| Q-AC/VC-022/024、Q-COV-F13 | “kill restart”测试只重建 Python 状态对象 | 启动真实 serve/conductor/launcher，杀 conductor PID，验证 serve respawn、2 tick 续推、单 `[START]`、预算及 mtime 不变 | reopen T-16 |
| Q-AC-003、Q-X-L3-DOSSIER | closure dossier 的 L3 verdict 文件/字段未单独断言 | 在 L3 meets→done→stage closure 链路断言 `l3-verdict.txt` 与 dossier 中每 key verdict/report/evidence refs | reopen T-12/T-16 |

## 二次印证结论

- spec 的性能约束已逐项扫描；发现 VC-018 冻结值违反“≤1 interval”的字面阈值。
- spec 的安全约束已扫描；read_scope、typed allowlist、凭证隔离有证据。
- spec 的平台约束未闭合：只有 Windows，无 Unix 运行证据。
- Function Flow §5.1~§5.4 节点均映射到 Q-AC/Q-VC/Q-COV；跨 L3→stage dossier 的裁决字段证据不足，已补 Q-X-L3-DOSSIER。
- Coverage Matrix 15/15 行均生成 Q-COV；异常路径均有问题项。
- task 绑定 18/18 非空，无遗漏；Error Fingerprint 中本 key 错误均已处置。packages/ai 的 tsgo 错误为已声明存量，但 `npm-check-final.log` 的全仓命令本身仍以非零结束，不能表述为“全仓 check 通过”，只能表述为“coding-agent 无新增错误”。

本报告不接受遗留项 override；需按行动计划补证后重新执行合入前 quality gate。
