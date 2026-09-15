# PM State: goal-autopilot

## Section 1: Snapshot
- Key: goal-autopilot
- Claim-Id: —（已 release，待新会话认领）
- Phase: DONE
- Updated: 2026-09-10 19:32
- Completed: 2026-09-10 19:32
- 下一步行动（重启恢复锚点）: **key 已结案（DONE，2026-09-11 00:35）**——18/18 任务完成，QG run4 PASS（72/72 充分），done 三件套齐（achieved.md 1860B / pm-state PASS 行 / evidence/quality-gate-report-2026-09-11-qg.md），产品提交×4（4c7c07c43/c28edf7b2/fceae6eaf/5e8ecf39d）。无待办；若需重开，按框架 re-open 流程新开 key

## Section 2: Task Status

| Task | Stage | 代码状态 | 验证状态 |
|------|-------|---------|---------|
| T-01 基线冻结（含 5 个测试侧基线修复，用户批准 B 方案） | 完成 | test_e2e_real.py + smoke_test.sh 修复（47+/8-，已提交 f6cea320c） | 四套件全绿（121+1deselected / 1 passed / 9/9 / 90）；基线已冻结 evidence/baseline/baseline-manual-suites.md |
| T-02 config.py + advance.py（PM 直执） | 完成 | autopilot/__init__.py + config.py + advance.py + test_autopilot_config.py（未提交） | 26 passed（[VERIFY] VC-027 ×9）；全量 147 passed 零回归；真实框架定位验证通过 |
| T-03 roadmap（worker t03-roadmap，已验收） | 完成 | autopilot/roadmap.py + roadmap_check.py + test_autopilot_roadmap.py（32 passed，[VERIFY] VC-001 ×18）；key-status 缺省=合法新提案，存在则须与 Keys 表全等；更新助手纯文本变换不持锁 | PM 亲跑 32 passed 复核 + 代码走查通过；全套件 217 passed 零回归 |
| T-04 timeline（worker t04-timeline，已验收） | 完成 | autopilot/timeline.py + test_autopilot_timeline.py（16 passed，[VERIFY] VC-019 ×16） | PM 亲跑复核 + 代码走查；seq 恢复/轮转/pruned/§9 容错均超基线；append 接口为 T-06 消费契约 |
| T-05 gates（worker t05-gates，已验收） | 完成 | autopilot/gates.py + test_autopilot_gates.py（38 passed，[VERIFY] VC-005 ×7 / VC-026 ×3）；无锁设计：锁由调用方组合；YAML 子集手写解析；字段疑点裁决：12 字段为权威（任务书 13 为计数笔误已勘正） | PM 亲跑 38 passed 复核 + 代码走查通过；无散落文件 |
| T-08 audit（worker t08-audit，已验收） | 完成 | autopilot/audit_evidence.py + test_autopilot_audit.py（7 passed，[VERIFY] VC-009 ×4） | PM 亲跑复核 + 代码走查；真实 key 跑批 exit 1（25 AC 全提取、D-113/115 non-blocking 缺口）实战验证语义正确 |
| T-07 state.py（PM 直执） | 完成 | autopilot/state.py + test_autopilot_state.py（11 passed，[VERIFY] VC-015/016/020/024 ×7） | claim 四态（host 不匹配→dead 非对称已锁定）；rounds distinct-attempt 去重；[START] 观测；孤儿对账路径归一化；全量 228 passed 零回归 |
| T-06 dispatch（PM 直执） | 完成 | autopilot/dispatch.py + test_autopilot_dispatch.py（10 passed，[VERIFY] VC-023 ×7） | 5 类型注册表 + 拒绝零行/type-rejected 事件 + ap- 前缀队列行锁内追加读回校验；S1 全量 261 passed 零回归 |
| T-13 read_scope（worker t13-read-scope，已验收） | 完成 | worker/read-scope.ts（纯算法）+ worker-mode.ts 接线 + test/suite/autopilot-read-scope.test.ts（19 passed） | PM 亲跑 19/19 + 90/90 无回归；段边界/../逃逸/junction/盘符/不存在尾归一化/cap 双限全覆盖；4 个 writeOutput 退出点全走拒绝节写出 |
| T-09 conductor 骨架（PM 直执） | 完成 | autopilot/conductor.py + mw.py serve 监护 + mw_common doctor 行 + test_autopilot_conductor.py（15 passed） | [VERIFY] VC-021 ×3 / VC-027 ×2；goal-change gate 幂等/陈锁窃取/启动门禁/act-then-sleep；全量 276 passed 零回归 |
| T-14 worker 协议增量（worker t14-protocol，已验收） | 完成 | pm-orchestrator.ts origin 跳过 + worker-mode.ts（allowlist 5 条目/fail-closed/[START] pid/agenticdocRoot 拆分）+ test/suite/autopilot-protocol.test.ts（10 passed） | PM 亲跡三套件 119/119；allowlist 与 REGISTRY 逐类型逐序相等；[START] pid 行与 state.py 正则逐字匹配；手动 fallback GC-8 保留 |
| T-10 per-key phase 机（PM 直执） | 完成 | conductor.py orchestrate 全量（phase 机/L2 回路/预算/stalled 四产物/孤儿和解）+ 13 新用例（共 28） | [VERIFY] VC-007/008/010/013/015/016/019；advance 全走脚本 exit code 事件；全量 289 零回归 |
| T-15 /autopilot console（worker t15-console，已验收） | 完成 | autopilot/ 3 文件（console/status-model/gate-writer）+ pmActivate 注册 + 30 用例 | PM 亲跡 59/59 + 回归 90/90 + check 零新增；VC-017/020 parity 锁定；gate-writer 逐字节保留；S3 收口 |
| T-11 stage 机 + gate 生命周期（PM 直执） | 完成 | conductor.py stage 分支（§5.1 重构）+ gate 消费 + roadmap-writer 派发 + 闭环 dossier + 11 用例 | [VERIFY] VC-003 ×2/005/026 ×2；幂等双层（状态+时间线消费记录）；全量 299+1 抖动；S2 进度 3/4 |
| T-12 EXECUTE/L3/done（PM 直执） | 完成 | execute_loop（stem 身份/串行/预算/stalled）+ _verify_loop（L3 ≤2 轮/repair/below 三形态）+ _done_transaction（D-108 六步含 index 后验）+ dispatch.py upsert + 12 用例 | [VERIFY] VC-012 ×2/VC-025 ×2/VC-024；全量 312 零回归零抖动；**S2 收口（4/4）** |
| T-16 L2 e2e（PM 直执） | 完成 | test_autopilot_e2e.py（真 conductor/launcher/serve 进程 + 框架副本真门禁 + PATH 遮蔽 pi stub + 密闭 providers）+ pytest.ini e2e_l2 标记 | 5/5 默认窗口全绿（VC-002/004/006/014/018/021/022/027 全 pass=true）；默认套件 358 零回归 |
| T-17 L0 奇偶（PM 直执） | 完成 | test_autopilot_l0.py（AST 静态扫描 + 双源活解析奇偶 + 未知 type 动态拒绝 + vitest 活跑 fail-closed） | 5/5（VC-007/VC-023；autopilot-protocol 10/10 活跑）；subprocess encoding 修复；默认套件 363 零警告 |
| T-18 全量收口（PM 直执） | 完成 | bundle 重建安装 + 全套件证据跑 + VC-001~027 全索引 + AC-012 对照 + 遗留 7 项 | L1 363 / L0 5/5 / L2 5/5 / vitest 59+106 / e2e_real 1 / smoke 9-0 / check coding-agent 零错；VC 27/27；evidence/runs/final-verification.md；**S4 收口，18/18 全完** |
| ga-spec-design-review-2（spec+design 独立评审，pi + gpt-5.6-sol） | 完成 | 无代码改动（只读评审） | FAIL（10 blocking + 8 non-blocking）→ 全部处置：B1-B10 采纳（B4 部分：手动 fallback 为 GC-8 明文保留，实际修复 = origin fail-closed）、N1-N8 全采纳；design v2 + spec errata 落盘 |

## Section 3: Evidence Ledger

| 证据 | 类型 | 结果 | 证据文件 |
|------|------|------|--------|
| spec-existing-capability-survey | 调研 | 7 项可复用 + 6 项新增，B+C 可行 | evidence/research/spec-existing-capability-survey-2026-09-06.md |
| spec-ac-lock | 决策留底 | 用户确认 spec，AC 锁定于 2026-09-08T20:31:02Z | spec.md §3 锁标 |
| design-conductor-mounting | 调研留底 | 子进程挂载/零私有状态/claimId 互操作/良性竞态 4 项结论 | evidence/research/design-conductor-mounting-and-state-2026-09-08.md |
| design-gate-l2-protocol | 调研留底 | tool_call block 可行/双侧注册表/L3 机械落盘/gate 文件协议 4 项结论 | evidence/research/design-gate-l2-worker-protocol-2026-09-08.md |
| design-mermaid-gate | 机械校验 | check_mermaid.py PASS（0 err 0 warn，修正边标签引号后） | 命令输出 |
| design-ac-vc-coverage | 机械校验 | spec 25 AC ⊆ design 25/25，MISSING none | 命令输出 |
| design-d111-plan-format | 事实取证 | plan.md Stage 总览表+T-NN 行、tasks/ 命名 T-NN-slug.md（实测两个既有 key） | evidence/research/design-conductor-mounting-and-state-2026-09-08.md 发现 8 |
| ga-spec-design-review-2（worker review） | 独立评审 | FAIL → 10 blocking + 8 non-blocking，处置完成（B8 goalMtime 恒 0 已本人复现；B10 调研算术错误自纠） | workers/ga-spec-design-review-2/output.md |
| design-v2 门禁复跑 | 机械校验 | mermaid PASS / AC→VC 25-25 / VC↔ER 27-27 全对齐 | 命令输出 |
| spec-gate-semantics-decision | 决策留底 | 用户 4 轮决策 + pm-mind 交叉验证 | evidence/research/spec-gate-semantics-2026-09-06.md |
| ga-spec-review-1（worker review） | 独立评审 | FAIL → 4 blocking + 12 non-blocking，已全部处置 | ../agent-team-loop/workers/ga-spec-review-1/output.md |
| B2 代码事实验证 | 静态检查 | toolsForType() 未知 type 回退全量集（含 write/edit/bash）属实 | worker-mode.ts:10-18 |
| design-v2 用户过审 | 决策留底 | 用户确认 design v2（2026-09-09 本会话），准入 /plan | 对话记录 + Turn 记录 |
| plan-ac-vc-coverage | 机械校验 | plan.md AC 25/25 + VC 27/27 全引用（全 ID 形式，缩写形式已修正），11053B > 300B 门禁 | 命令输出 |
| baseline-manual-suites | 基线冻结 | 四套件全绿（L1 121+1d / L2 e2e 1 / smoke 9/9 / TS 90）；5 个测试侧缺陷修复后冻结；基点 commit f6cea320c；AC-012 唯一对照口径 | evidence/baseline/baseline-manual-suites.md |
| t02-config-advance | L1 | config/advance 模块 + 26 用例（[VERIFY] VC-027 ×9：默认零足迹/fail-closed/round-trip/缓存失效/框架缺失拒1/stub 透传/无 shell/超时124）；全量 147 passed 零回归；真实框架定位验证 | 命令输出 |
| t05-gates | L1 | gates 协议层 38 用例（[VERIFY] VC-005 ×7 / VC-026 ×3：seq=max+1 重扫/round-trip 12 字段/损坏显式异常/5 kind/3 status）；PM 验收亲跑复核 | 命令输出 + 任务文件执行记录 |
| t03-roadmap | L1 | roadmap 解析/校验/依赖图/更新辅助 32 用例（[VERIFY] VC-001 ×18：三要素/缺项报 stderr/前向依赖非法/自依赖环/跨 stage 重复/容错/CRLF 保留）；PM 验收亲跑复核 | 命令输出 + 任务文件执行记录 |
| t07-state | L1 | state 推导层 11 用例（[VERIFY] VC-015/016/020/024 ×7：claim 四态含 host 不匹配→dead 非对称/7 列+legacy 5 列/rounds distinct-attempt 修复同回合不另计/[START] 行数+活性/孤儿对账/mtime 快照）；PM 直执 | 命令输出 + 任务文件执行记录 |
| t08-audit | L1 | audit CLI 7 用例（[VERIFY] VC-009 ×4：齐全 exit 0 三键/缺失 exit 1 gaps 非空/errata AC 提取/decision_map 键集 parity）；真实 key goal-autopilot 跑批 dossier 实战验证 | 命令输出 + 任务文件执行记录 |
| t04-timeline | L1 | timeline 模块 16 用例（[VERIFY] VC-019 ×16：seq 单调恢复/key 哨兵非 null/轮转旧→新回放/watermark 过滤/pruned 提示/追加失败容错/LF 对称）；PM 验收亲跑复核 | 命令输出 + 任务文件执行记录 |
| t13-read-scope | L1 | read_scope 拦截 19 用例（VC-011 三断言/段边界/逃逸/junction/win32/不存在尾/cap-file/cap-byte/无 scope 零拦截）；npm run check 本任务零新增；PM 亲跑复核 | 命令输出 + 任务文件执行记录 |
| t09-conductor | L1 | conductor 层 15 用例（[VERIFY] VC-021：beat 首位/禁用仍跳/gate 幂等/tick 异常存活；VC-027：--once 首 tick 即动作/决策矩阵）；AC-005 静态无 goal/Phase 写；全量 276 零回归；PM 直执 | 命令输出 + 任务文件执行记录 |
| t14-protocol | L1 | 协议增量 10 用例（origin 跳过/allowlist 查表/verifier 缺 scope fail/未注册 type exit 1+原因/手动 fallback 保留/[START] pid 恰一条/goalMtime 真根）；三套件 119/119；PM 亲跑复核 | 命令输出 + 任务文件执行记录 |
| t10-phase-machine | L1 | phase 机 13 用例（[VERIFY] VC-007 直推走脚本/VC-010 第 3 轮 0 行+gate/VC-013 budget=1 升级/VC-015 claim skip+接管 0 行/VC-016 EXECUTE 接手 mtime 不变/VC-008 四产物+依赖阻塞/VC-019 事件 key 非 null；L2 一回合闭环/孤儿重插/并行 cap）；PM 直执 | 命令输出 + 任务文件执行记录 |
| t15-console | L1 | console 30 用例（VC-017 --json schema+view parity/VC-020 rounds parity Python 探针标注/D-110 config 镜像验证/AC-016 gate 答复+未知 id+路径穿越拒绝/D-109 水位回放+beat 过滤+pruned/AC-025 enable 启 mw）；PM 亲跡复核 + 回归 90/90 | 命令输出 + 任务文件执行记录 |
| t11-stage-machine | L1 | stage 机 11 用例（VC-003 未答 ≥3 tick rows=0+writer 不重派/VC-005 全终态 1 tick dossier+close gate+下一 stage rows=0+不重复/VC-026 stalled-reject 同 tick 解锁闭环+拒后重提恰 1 次+二拒停；损坏 gate 跳 tick；halt 人工恢复；gate-answered 恰一次）；PM 直执 | 命令输出 + 任务文件执行记录 |
| t12-exec-l3-done | L1 | exec/L3 12 用例（VC-025 exit1 重试成功+超限 stalled 且他 key rows≥1/needs-clarification 计失败/VC-012 meets 全套三件套+below-twice stalled/缺节+短 achieved below/VC-024 杀重启 [START]=1+预算不变+mtime 不变+2 tick 续推；plan 序/孤儿注记/plan 缺失走 L2）；PM 直执 | 命令输出 + 任务文件执行记录 |

## Section 4: Hypothesis Queue

| 假设 | 状态 | 关联证据 |
|------|------|---------|
| H-1（dispatch_worker owner key 解析取自窗口 watch 状态而非 active 指针） | 已转移 | 转入 mw-dispatch-flow-fixes key 修复（AC-001/002），本 key 不再追踪 |

## Section 5: Decisions

- D-001: 架构 = B+C（conductor 状态机 + typed 判断-worker + console 监控台），否决 A（无头 PM 可观测性差/断点成本高）
- D-002: 门禁 = 混合三层（L1 脚本审计 → L2 worker 裁决 → L3 QG 后终局裁决），全部发散回路回合上限默认 2，单处配置
- D-003: 人工门禁 = stage 确认 / stage 闭环 / stalled / goal 变更 / 预算耗尽；key 内 phase 边界分层自动
- D-004: additive 零侵入手动工作流；opt-in per project；模式互换无缝（状态全在文件）
- D-005: console 无状态，一切从文件推导；断点重开 = 正常重开；离线事件按 last-seen 回放
- D-006: review B1-B4 全部接受：§2.2 门禁时延分域（读取 1 间隔/stage 首派发 2 间隔）；GC-8 + AC-021（类型白名单显式 + 未知 type 拒绝）；AC-022（conductor 崩溃恢复）；AC-023（worker 失败计入 retry 预算）；AC-024（gate reject 语义）；AC-025（启用正路径）
- D-007: design 架构决策 D-101~D-112 落盘（详见 key-decision.md A 章）：conductor = mw serve 第三子进程；零私有状态全推导；gate = per-gate md+frontmatter；L2 = read_scope+tool_call block；typed 双侧注册表+奇偶测试；L3 产物机械落盘；单 timeline+beat+轮转；config 在 _autopilot/config.json；轮询默认 4s
- D-008: review B1-B10 + N1-N8 处置：spec errata（AC-020 列数/AC-017 哨兵，编号不动）；design v2（origin 标记消竞态、containment 算法、worker fail-closed、done 三件套后验、seq/watermark、stem 身份+串行、stale-lock 窃取、act-then-sleep、[START] 观测、agenticdocRoot 拆分）；指纹 v2=475a2958a5ca
- D-009: EXECUTE 执行方式（用户指令 2026-09-10）：T-01 及后续任务按需直执或派发 worker；长时任务与关键验证依赖任务适合直执。T-01 已直执；基线发现的 5 个测试侧缺陷经用户批准 B 方案修复后冻结（修复属基线修复，不单独立 key，记入 T-01 执行记录）
- D-010: S1 并行派发策略（用户指令 2026-09-10）：T-03/T-04/T-05/T-08（自包含、零文件交叉）派发 4 worker 并行；T-02/T-07（关键路径/语义最重）PM 直执；T-06 待 T-04 timeline 接口落地后接力。worker 指令统一约束：只碰自己 task 列出的新文件、显式路径参数、禁 import autopilot.config（避免与 T-02 在飞冲突）、[VERIFY] 埋点、完成后更新对应任务文件

## Section 6: Turn End Records

### Turn 2026-09-09 (PLAN)
1. 顶层目标: design v2 过审确认 → plan.md 生成并推进至 TASKS
2. 新增证据: design-v2 用户过审（决策留底）；plan-ac-vc-coverage 机械校验（25/25 + 27/27）
3. 假设变化: 无
4. 需重开 Task: 无
5. 阻塞点: 无
6. 新增 Task: tasks/T-01~T-18 全 18 个任务文件落盘（S0 基线 1 / S1 基础设施 7 / S2 conductor 4 / S3 TS 3 / S4 收口 3）；plan.md 「8 命令」笔误修正为命令集全量（design §4.1 实为 9 动词）；T-01 直执完成（含 5 个测试侧基线修复，D-009）；T-02 直执完成（26 passed，D-010 并行策略下 4 worker 在飞）
7. 下一轮首要动作: review 4 worker 产物（t03/t04/t05/t08）并验收更新状态；T-07 state.py PM 直执；T-06 待 T-04 接口落地接力
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: ①plan/tasks 的 AC/VC 引用必须用全 ID 形式（缩写会让机械覆盖校验漏配，本 turn 实际踩到并修正）；②tasks/ 生成后跑 stem 唯一性 + AC/VC 全引用校验（与 plan 同口径），一次通过；③CJK 文本编辑时 unicode 码位笔误（械 U+68B0 误成 U+68C8）会让后续 oldText 匹配静默失败——长行编辑前先用码位校验；④基线冻结前首跑发现的存量测试缺陷应逐一受控实验归因（本次 5 项全部实验定位后才修复，产品与测试责任分清）；⑤set -o pipefail 下 cmd | grep -q 会把被测命令的非零退出码传导为管道失败——断言「消息存在」类检查必须分离捕获输出与退出码；⑥MSYS/Git Bash 只转换 argv 不转换文件内容——跨 bash/Windows Python 边界的路径必须 cygpath 显式转换；⑦Git Bash kill -0 看不见 DETACHED_PROCESS——存活探测用 tasklist 回退

### Turn 2026-09-07 (SPEC)
1. 顶层目标: goal-autopilot spec 起草并经独立 worker review 修复
2. 新增证据: 2 份 research note；ga-spec-review-1 独立评审（FAIL, 4 blocking）；B2 代码事实验证
3. 假设变化: 新增 H-1（dispatch owner key 解析机制待验证）
4. 需重开 Task: 无
5. 阻塞点: 无（等用户 spec 确认）
6. 新增 Task: 无（spec 阶段）
7. 下一轮首要动作: 用户确认 spec → 锁定 AC（§3 顶部加锁标记）→ /system-design
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: 独立 worker review spec 的流程本身可行（12 分钟、产出结构化 blocking/non-blocking 清单）；候选 pattern：spec 评审任务模板（checklist + coverage matrix + verdict）

### Turn 2026-09-08 (DESIGN，重启前状态封存)
1. 顶层目标: 封存可重启状态，用户重开 pi 更新框架
2. 新增证据: 无（状态维护 turn）
3. 假设变化: 无
4. 需重开 Task: 无（ga-spec-design-review-2 已终态 done）
5. 阻塞点: 无
6. 新增 Task: 无
7. 下一轮首要动作: 按 Section 1 恢复锚点执行（认领 → design v2 过审 → /plan）
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: 无新增

### Turn 2026-09-08 (DESIGN，review 处置轮)
1. 顶层目标: ga-spec-design-review-2 结果评估 + 全量处置
2. 新增证据: review output.md（FAIL，10B+8N）；B8 事实复现（goalMtime 恒 0，无 GOAL_CHECK 痕迹佐证）；门禁复跑三绿
3. 假设变化: 无
4. 需重开 Task: 无
5. 阻塞点: 无（design v2 待用户过审）
6. 新增 Task: 无
7. 下一轮首要动作: 用户过审 design v2 → /plan（拆解顺序建议：Python 基础设施（含 stale-lock/act-first/origin）→ conductor 核心 → TS console/worker-mode（含 D-115/116 修复）→ L2 计时/E2E → 奇偶与静态门禁；AC-012 baseline 冻结文件列入首个 task）
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: ①独立评审 worker 交叉验证设计引用（发现调研算术错误与存量 bug 各一处）证明「设计事实必须对着源码验」不是形式主义；②erratum 机制处理锁定 spec 的措辞错误（编号不动、显式标注、指纹重算留链）

### Turn 2026-09-08 (DESIGN)
1. 顶层目标: spec 确认锁定 + design.md 全套产物生成
2. 新增证据: 2 份 design 调研留底；mermaid 门禁 PASS；AC→VC 覆盖机械校验 25/25
3. 假设变化: 无（H-1 已在别的 key 处置）
4. 需重开 Task: 无
5. 阻塞点: 无（等用户 design 审核）
6. 新增 Task: 无（design 阶段）
7. 下一轮首要动作: 用户过审 design → /plan 生成 plan.md（建议拆解顺序：Python 基础设施 → conductor 核心 → TS console/worker-mode → L2 计时/E2E → 奇偶与静态门禁）
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: 跨语言协议（task.md frontmatter 扩展）用双侧注册表+奇偶测试防漂移；mermaid 边标签不能带引号（R2，与 SKILL 文档示例矛盾，以 check_mermaid.py 实际规则为准）

### Turn 2026-09-07 (SPEC，重启前状态封存)
1. 顶层目标: 封存可重启状态，用户重启 pi 加载最新框架
2. 新增证据: 无（状态维护 turn）
3. 假设变化: H-1 已转移至 mw-dispatch-flow-fixes
4. 需重开 Task: 无
5. 阻塞点: 无
6. 新增 Task: 无
7. 下一轮首要动作: 按Section 1 下一步行动执行（认领 key → spec 确认 → 锁 AC → /system-design）
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: 无新增

## Section 7: Process Log

- 2026-09-06: key 创建（claim 20260906-165217-7704）；4 轮需求讨论（架构/门禁/stage/共存）
- 2026-09-07: 2 份 research note 落盘；spec.md v1（20 AC）写入；advance_phase init→spec
- 2026-09-07: 框架坑点：claim stub 的 Phase (pending) + 缺 Updated 行被 advance_phase 拒绝，需手工补 init + Updated（候选 _pitfalls.md 条目）
- 2026-09-07: 派发 ga-spec-review-1（pi/timi，12 分钟，exit 0）；review FAIL（B1-B4）→ spec 修复为 25 AC
- 2026-09-07: 流程测试发现：dispatch_worker owner key 落到窗口 watch 的 key（agent-team-loop）而非 active key；claude 路由缺凭证（已知问题）；worker 长生成期间（约 7 分钟）trace 无心跳，仅 30 分钟看门狗兜底
- 2026-09-07: 用户确认三项修复单独立 key 交其它窗口：mw-dispatch-flow-fixes 已建（spec 8 AC + research note，Phase SPEC，已 release 供其它窗口认领）
- 2026-09-07 20:07: 重启前封存：spec 25 AC（draft）待确认；claim 已 release 供新会话认领；讨论全部决策已落盘（research notes + D-001~006），不依赖对话记忆
- 2026-09-07 20:15: 新会话 /pm-key switch 认领（WENBOZHOU-PC4:39760），旧 active key mw-dispatch-flow-fixes 转 idle；Turn Start 恢复完成，等待用户 spec 确认
- 2026-09-08 20:31: 用户确认 spec；AC 锁定（🔒 AC Locked at 2026-09-08T20:31:02Z）；advance_phase spec→design
- 2026-09-08 20:35-21:00: 通读 mw.py/launcher.py/mw_common.py/pm-orchestrator/ui-bridge/worker-mode/index-store/goal-reader/advance_phase/types.ts；2 份 design 调研留底；design.md（D-101~D-112 + 4 图 + Coverage F1-F15 + VC-001~027 + AC→VC 25/25）；mermaid 门禁一次 FAIL（边标签引号）修正后 PASS；key-decision A 章 12 条；evidence-requirement.md（指纹 09522ef47912）
- 2026-09-08 21:10: 补证 D-111（plan.md/tasks/ 实测格式）；用户派发 ga-spec-design-review-2（pi + gpt-5.6-sol，只读评审 spec+design，A/B/C 三段 checklist：B1-B4 修复验证 + AC 保真 + 决策证据抽查 + VC 可判定性）
- 2026-09-08 21:40: review 完（4m，52 工具调用）：FAIL，10 blocking + 8 non-blocking；B1-B4 前次修复确认落地
- 2026-09-08 22:20: 处置完成：逐项验证（B8 亲自复现、B10 自纠）→ spec errata ×2 → design v2（D-101/102/104/105/106/107/108/109/111 改写 + 新增 D-113~D-116 + round 单位表 + --json schema + VC 修订 ×6）→ 调研留底修正段 → key-decision v2（含 GC-1 澄清行）→ evidence-requirement v2（指纹 475a2958a5ca，baseline 冻结约定）→ 门禁复跑三绿（mermaid PASS / AC 25-25 / VC↔ER 27-27）
- 2026-09-08 22:30: 重启前封存：无在飞 worker；claim 已 release；全部决策落盘（D-001~008 + A 章 v2），不依赖对话记忆
- 2026-09-09 23:50: 新会话接手（WENBOZHOU-PC4:8420，switch_key）；Turn Start 恢复 + audit PASS
- 2026-09-09 23:57: 用户确认 design v2 过审 → plan.md 生成（5 Stage / T-01~T-18，按 pm-state 处置轮第 7 条拆解顺序 + AC-012 baseline 冻结列入 T-01 首 task）→ 覆盖校验修正（缩写→全 ID）→ advance plan→tasks，audit PASS
- 2026-09-10 00:40: 用户「继续」→ tasks/ 18 文件生成（新版结构化格式：基本信息/描述/输入/预期产出/状态与证据；初始未开始）→ stem 唯一 + AC 25/25 + VC 27/27 全引用校验通过 → plan.md 命令数笔误修正（8→命令集全量，design 实为 9 动词）→ advance tasks→execute，audit PASS；修正 pm-state 锚点行码位笔误（U+68C8→U+68B0）
- 2026-09-10 00:43-01:20: T-01 直执（用户指令）：首跑四套件→ e2e_real FAIL + smoke 5/4 → 受控实验逐一归因（探针 serve / tee 管道捕获 / tasklist 对照）→ 5 项全部测试侧缺陷、产品行为正确 → 用户批准 B 方案 → 修复（test_e2e_real keyed 布局 ×2 / smoke T1 全局安装断言 + T3 pipefail 分捕+timeout + T5 cygpath + T6 tasklist 回退 + Requires 行）→ 重跑全绿（121+1d / 1 passed 17.1s / 9/9 / 90）→ 基线冻结 evidence/baseline/baseline-manual-suites.md（基点 357296d89，AC-012 对照口径）；D-009 执行方式决策落盘
- 2026-09-10 01:25-01:45: 用户指令「先 commit → 继续 T-02 → 规划轻量任务同步」：基线+修复提交 f6cea320c（仅 2 测试文件，key 目录按约定不入库；基线文件锚点同步更新）→ 依赖图分析（T-03/04/05/08 自包含零交叉 / T-06 依赖 T-04 / T-07 语义最重）→ D-010：建 autopilot 包骨架后派发 4 worker（t03-roadmap/t04-timeline/t05-gates/t08-audit，统一约束：显式路径/禁 config import/[VERIFY] 埋点/只碰自身新文件）→ PM 直执 T-02：读 mw_common 原子写模式 + detect_root 探测协议 + advance_phase CLI 签名 → 实现 config.py（D-110 全字段 fail-closed + mtime 缓存）+ advance.py（marker→标准布局引导→detect_root 权威定位→子进程封装）+ 26 用例 → 全绿 + 全量 147 passed 零回归 + 真实框架定位验证；T-02 任务文件 + pm-state 更新
- 2026-09-10 12:05: T-05 worker 终态 done（22m，38 passed）→ PM 验收：亲跑复核 + [VERIFY] 行 ×10 + git status 无散落 + 代码走查（seq 重扫/无锁/GateFormatError/id↔文件名/ISO Z 形式均合规）→ 裁决字段疑点：design §4.1 枚举 12 字段为权威，任务书「13」为 PM 计数笔误，勘正任务文件并加验收行；T-11/T-15 依赖 schema 锁定 12 字段
- 2026-09-10 12:40-13:15: T-03 worker 终态 done（29m，32 passed，全套件 217 零回归）→ PM 验收亲跑 + 代码走查（key-status 缺省=合法新提案语义确认采纳，T-11 激活 stage 时需初始化全部 key 条目）；PM 直执 T-07 完成：读 design §4.1/D-102/103/115 + TS ui-bridge claimState + update_index 协议 → state.py（claim 四态含 host 不匹配→dead 非对称、rounds distinct-attempt 去重、[START] 观测、孤儿对账 normcase 归一化、mtime 快照）+ 11 用例全绿；T-08 worker 终态 done（36m，7 passed，[VERIFY] VC-009 ×4）→ PM 验收：真实 key 跑批 dossier 实战验证（25 AC 全提取、D-113/115 non-blocking 缺口 exit 1 语义正确）；S1 进度 6/7（仅 T-04 在飞 + T-06 待接力）
- 2026-09-10 13:30: T-04 worker 终态 done（37m，16 passed，[VERIFY] VC-019 ×16，E1 测试期望修正已闭环）→ PM 验收：亲跑复核 + 代码走查（seq 尾行恢复/轮转链纯 rename/pruned 不静默/§9 失败不耗 seq/撕裂尾行隔离，超基线）；S1 七模块全落地，T-06（dispatch，最后一个 S1 任务）解除阻塞，PM 直执开始
- 2026-09-10 14:00: T-06 PM 直执完成：dispatch.py（D-107 注册表 5 类型/task.md 模板全字段/锁内队列行+读回校验/拒绝 0 行+type-rejected/dispatch 成功事件）+ 10 用例全绿；S1 全量回归 261 passed 零回归——S1 阶段全部 7 任务收口（直执 3 + worker 4，总用时约 2.5h）；下一步待用户确认 S1 批 commit，随后 S2（T-09 PM 直执）与 S3（T-13 worker）并行开路
- 2026-09-10 14:35: T-13 worker 终态 done（25m，19 passed + 90/90 无回归，npm run check 零新增）→ PM 验收：亲跑复核 + 代码走查（纯算法拆分 read-scope.ts 可单测/缺省 path 归为 . 堵省参绕过/拒绝双落盘 4 退出点全覆盖）；随即派发 t14-protocol（依赖 T-13 同文件先合入）；PM 开始 T-09 conductor 直执。插曲：首派 T-13 时 dispatch 默认抓了另一会话 key（mw-widget-terminal-lifecycle）的最新 active 位被拒，显式指定 key 重派成功——后续所有派发都带显式 key 参数
- 2026-09-10 15:20: T-09 PM 直执完成：conductor.py（beat/enabled 门/goal-change 幂等 halt/陈锁窃取/启动门禁/--once）+ mw.py serve 每秒监护（三源活性判定，conductor 死不破 serve）+ status/doctor conductor 行（timeline 尾水位）+ 15 用例；全量 276 passed 零回归（test_integration 并发用例首跑 1 次抖动，复跑均绿）；S2 进度 1/4，PM 串行接 T-10 per-key phase 机
- 2026-09-10 15:40: T-14 worker 终态 done（21m，protocol 10 + 三套件 119/119，npm run check 零新增）→ PM 验收：亲跑复核 + 代码走查（allowlist 逐类型逐序相等/[START] pid 逐字匹配/拒派双条件+手动豁免/根拆分契约不变）；随即派发 t15-console（S3 最后一个实现任务，依赖 T-14 先合入）；PM 接 T-10 直执
- 2026-09-10 16:45: T-10 PM 直执完成：orchestrate 全量（phase artifact 映射/L1 审计直推/L2 verifier+同回合 fix/预算门 approve bonus+reject stalled/stalled 四产物+closed-legacy 同 tick 解锁依赖/孤儿同 attempt 重插/并行 cap/claim skip）+ 13 用例；全量 289 零回归；S2 进度 2/4，PM 接 T-11 stage/gate 生命周期
- 2026-09-10 17:50: T-15 worker 终态 done（38m，30 用例 + 回归 29+90，check 零新增）→ PM 验收通过：亲跡 59/59 + 走查（命令集全落/watermark D-109/gate-writer 逐字节保留/usedRounds 与 state.py 同口径 VC-020 parity）；S3 三任务全部收口；检查点 risk=mid 裁决继续等待事后验证正确（8m 后收敛）；PM 继续 T-11 直执
- 2026-09-10 19:05: T-11 PM 直执完成：§5.1 顺序重构（gate 消费→和解→stage 分支→per-key 机）+ stage-confirm/close 生命周期 + roadmap-writer 派发（D-105 输入清单，≤2 尝试）+ 闭环 dossier + 双层幂等（状态转移+时间线消费记录）；11 用例；T-10 28 无回归；全量 299+1 已知抖动（隔离 ×2 过）；S2 进度 3/4，PM 接 T-12 EXECUTE/L3/done（S2 收口）
- 2026-09-10 20:10: T-12 PM 直执完成：execute_loop（stem 身份/plan 序/每 key 串行/失败预算超限 stalled）+ _verify_loop（L3 ≤2 轮/below → repair → 复评/缺节-FAIL-短 achieved 三形态统一 below）+ _done_transaction（D-108 六步）+ dispatch.py upsert；12 用例；全量 312 零回归零抖动；**S2 收口**。批 commit 经用户确认：Python S1+S2=4c7c07c43（23 文件 +8755）、TS S3=c28edf7b2（9 文件 +4182）
- 2026-09-10 21:15: T-16 PM 直执完成：test_autopilot_e2e.py（真 conductor/launcher/mw serve 进程 + 框架副本真门禁 + PATH 遮蔽 pi stub + 密闭 fixture providers）；5 测试 8 组 [VERIFY] 默认窗口全绿；pytest.ini 增 e2e_l2 标记；默认套件 358 passed 零回归。教训（E3）：非 ASCII 文件禁用 PowerShell -replace
- 2026-09-10 21:45: T-17 PM 直执完成：test_autopilot_l0.py（AST 静态扫描：零 Phase 字面量/零 goal 写族段 + 运行期 exit 码 schema 双码验证；奇偶：双源活解析逐类型序精确相等 + TS 键集恰为并集 + fallback==coding；未知 type 动态拒绝；fail-closed：TS 形状断言 + vitest 活跑 T-14 套件 10/10）；修复 subprocess GBK 解码警告；默认套件 363 零警告
- 2026-09-10 22:25: T-18 PM 直执完成（**全 key 收口**）：mw build --install（bundle 含 S3 TS 改动）；全套件证据跑全绿（L1 363/L0 5/5/L2 5/5 exit 0/vitest 59+106/e2e_real 1 passed/smoke 9-0/check coding-agent 零错）；VC-001~027 全索引（Python 107 行 [VERIFY] 20 VC + vitest 15 VC 名测试，27/27 覆盖）；AC-012 对照 PASS（基线零回归，演进项归因：本 key 为独立新文件、agent-team-loop 90→106 与基线六文件 121→167 归因并行会话 launcher 工作）；遗留 7 项如实列出（Windows 替换窗口竞态已知限制/l2 cap 不落盘/锁协议前提/静态扫描限度/e2e_l2 排除/并行会话工作树/l3-verdict.txt 未单独断言）。**发现并处置 E1：压测中 Windows tmp→replace 竞态 PermissionError（生产读方全带兜底，测试线程加同型重试）**。用户确认后 S4 产物已提交 fceae6eaf；key 推 VERIFY
- 2026-09-10 22:35: QG run1（worker t18-quality-gate，model gpt-5.6-sol，1m）前置门禁中止：ac_fingerprint 失配 + evidence/baseline/ 目录缺失（T-01 冻结为文件形态）。PM 核实两发现均属实但均属元数据层：指纹 v1/v2 历史值三种命令变体均不可复现→口径漂移非 AC 集变更（ac_ids 交叉验证恰 AC-001~025）；处置：指纹以 QG 规范命令重算落 v3（ccc2c018e052）；基线文件迁入 evidence/baseline/baseline-manual-suites.md 并同步全引用点；run1 报告归档 -run1-aborted；重派 t18-quality-gate-2
- 2026-09-10 22:58: QG run2（t18-quality-gate-2，3m）仍中止于同一指纹失配——根因是 PM 自己：run1 处置的 edit 调用含两个 edits，edits[1] 不匹配整批原子回滚，指纹 v3 替换未落盘而误判已改（**教训：edit 整批原子，处置后逐项 rg 验证**）。已单独重放指纹编辑并双重复核（文件 rg + 规范命令复算 ccc2c018e052/25AC）；run2 报告归档 -run2-aborted；重派 t18-quality-gate-3
- 2026-09-10 23:20: QG run3（t18-quality-gate-3，5m/83 工具调用）全流程跑完：前置门禁 8/8 全过（指纹一致），结论 **FAIL（A=61 充分/B=10 不足/C=2 无证据，总 73 问题）**。PM 逐项亲核 6 类阻塞发现全部属实且均在 spec 合同内（§2.1 双平台明文/多项目隔离明文/AC-011 三回路明文/AC-022「被杀死并重启」字面/VC-018 阈值 1021ms>1000ms 且根因是 tick 处理 epsilon 字面不可达/遗留#7 自认）：Q-X-UNIX、Q-X-MULTIPROJECT、VC-018、budget=1 三回路、真进程 kill/respawn、l3-verdict 断言。报告 evidence/quality-gate-report-2026-09-10-qg.md
- 2026-09-11 00:05: 用户裁决：**A 批准 VC-018 erratum；B Unix 出范围（Windows-only）**。QG 修复轮 PM 直执：产品修复×2（L3 预算配置化【揭出真缺陷：硬编码 2 违 AC-011 三回路共用预算源】+ l3-verdict/l3-report 落盘）；新用例×4（VC-013 双回路、VC-005 裁决链、e2e kill/respawn、e2e 多项目隔离）；erratum×2 落地（VC-018 阈值 + §2.1 平台）。L1 367 passed 零回归（1 个 test_integration 抖动重跑全绿）；e2e 7/7 exit=0；指纹不变。证据刷新（l1 双日志/l2 全窗口/final-verification 修复轮块）
- 2026-09-11 00:25: QG run4（t18-quality-gate-4，4m/75 工具调用）复检 **PASS（A=72 B=0 C=0，100%充分，无 ❌无 ⚠️）**——合入前口径达标。前置门禁 8/8；六类原阻塞项全部闭合（引用 MULTI-PROJECT/VC-024 kill=real-process/VC-013 三回路/VC-005 裁决链/VC-018 修订合同 967ms 实测）；Unix 按用户裁决关闭；Error Fingerprint 全关闭（E1/E2b）。PM 亲读报告验收：引用与冻结证据一致。报告 evidence/quality-gate-report-2026-09-11-qg.md。**待：修复轮产品 commit（conductor.py + 两测试文件，待用户确认）→ achieved.md + pm-state PASS → advance done（三件套齐：QG 报告已就位）**
- PASS: L3 quality gate meets — evidence/quality-gate-report-2026-09-11-qg.md (autopilot 2026-09-11T00:35:00Z)
