---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/dispatch.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/advance.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/closure.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_gate_effects.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t26-autopilot-recovery-closure/**
ac_refs: [AC-009, AC-010, AC-011, AC-015, AC-018, AC-021, AC-030, AC-031, AC-032, AC-033, AC-034, AC-035, AC-036, AC-037, AC-038, AC-039, AC-048, AC-049, AC-052]
vc_refs: [VC-009, VC-010, VC-011, VC-015, VC-018, VC-021, VC-030, VC-031, VC-032, VC-033, VC-034, VC-035, VC-036, VC-037, VC-038, VC-039, VC-048, VC-049, VC-052]
deps: [T11, T12, T13, T14, T15, T16, T17, T18, T19, T20, T21, T25]
execution: worker
---

## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T26 — H09/H10有界恢复/重规划、H11/H12受控入口及H13签收/阶段关闭实际接线保留旧失败与累计量。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
新stage仍独立H01，关闭须整体验收及非阻断遗留披露，不清标记/次数造成功；原phase硬失败先auto处置且复验后才推进。普通auto链不能自发恢复请求，实链负例必须覆盖；拒绝不默认关闭。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/dispatch.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/advance.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/closure.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_gate_effects.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t26-autopilot-recovery-closure/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-009: 在相位门禁失败且PM提交该场景专门背景及行动候选时，dp-auto承接处置选择并保留未解决项，不改写原门禁判据，未经重新通过硬门的相位推进次数为0。[REVISED @ 2026-10-25：用户认可dp7由通用入口承接，最新名dp-auto；完整措辞/schema仍待审核]

VC-009: phase硬门失败后，PM用专门背景和候选提交auto并实际受限处理，原硬门未复验通过前phase推进=0，原失败未丢失。
       Layer: L2
       Output: [VERIFY] VC-009: unchecked_phase_advances=0 erased_failures=0
       Source: AC-009

- AC-010: 在PM提交阶段目标/必需交付、必需key有效签收、跨key集成/阶段验收证据及未完成/未验证影响时，由dp-gate-approve审批；缺必需交付/验证或只有done计数/key签收时，可用关闭次数为0。明确披露且不影响阶段验收的非阻断遗留不单独阻止关闭；需用户接受的风险/取舍未获具体确认时不得据此放行。approve不批准下一stage；steer/need_fix/reject不冒充达标关闭，获授权遗留收尾须与成功交付区分；不增加原dp20第二次审批，具体状态转换/消费待设计。[REVISED @ 2026-10-25：阶段关闭归属及H02关闭条件/遗留规则已认可；完整AC未锁]

VC-010: stage正例达标且非阻断遗留披露可关闭=1；缺必需交付/验证、仅done或签收、未接受风险负例关闭=0；下一stage自动批准=0，遗留关闭不计达标。
       Layer: L2
       Output: [VERIFY] VC-010: valid_closures=1 invalid_closures=0 next_stage_approvals=0 false_acceptance_closures=0
       Source: AC-010

- AC-011: 在八入口处理同一具体事项时，职责表按主体/对象/动作及实质证据指定唯一业务审批归属；路由不代业务审批，同对象/实质证据版本重放不产生额外同事项审批或重复动作。实质影响变化的重审另留痕，不把所有不同gate文件或新材料一律当不同事项。[REVISED @ 2026-10-25：毕业考去除“四门”旧范围，完整AC未锁]

VC-011: 同主体对象动作实质版本在不同标签/文件重放及并发，只一个业务审批owner，额外同事项审批=0、重复动作=0；路由放行=0。
       Layer: L2
       Output: [VERIFY] VC-011: duplicate_approvals=0 duplicate_actions=0 route_releases=0
       Source: AC-011

- AC-015: 在项目goal、目标范围、写面与硬预算授权已明确、stage在授权内、硬检查满足且尚无有效启动决定时，autopilot首次评估该stage发起1次dp-gate-approve启动判断，逐stage人工确认要求数为0；第一个stage与后续stage使用相同授权规则。[REVISED @ 2026-10-25：毕业考按H10已确认归属点名启动gate，完整AC未锁]

VC-015: 授权条件齐备的首stage及后stage各首次评估只有1次启动gate判断；没有有效同事项决定才发起，逐stage人工要求=0。
       Layer: L2
       Output: [VERIFY] VC-015: first_stage_decisions=1 later_stage_decisions=1 per_stage_human_requirements=0
       Source: AC-015

- AC-018: 在启动路径任一机器硬检查失败时，autopilot记录具体阻断并保持该动作停止/等待/修复，因DP批准而豁免硬检查的次数为0。

VC-018: 启动各硬检查失败时停止对应动作，DP选approve也不得豁免，具体阻断无遗漏。
       Layer: L2
       Output: [VERIFY] VC-018: waived_hard_checks=0 hidden_start_blockers=0
       Source: AC-018

- AC-021: 在追加软轮次、steer或need_fix处理将突破硬预算时，不执行越界投入；提高硬预算须取得包含具体追加量/用途/风险的明确人工授权，因DP选择而自行提高硬预算或越界续跑次数为0。[ADDED @ 2026-10-25：由H04认可推导，未设置实际预算值，完整AC未锁]

VC-021: 软追加、steer或need_fix将越硬预算时越界执行=0、自行提高硬上限=0；必须具体追加量/用途/风险授权问题，累计消耗不重置。
       Layer: L2
       Output: [VERIFY] VC-021: hard_budget_overruns=0 self_granted_limits=0 reset_usage=0
       Source: AC-021

- AC-030: 在proposal派发耗尽恢复前，核实派发/执行/结果接收及pending/running状态、尝试/产物/预算/授权；未知或冲突在途执行时不盲目重派，明确动作/预算/结束判据后仅受控有界恢复，冲突/无依据重派次数为0。[ADDED @ 2026-10-25：H09验收推导，真实状态证明/限额/协调待设计，完整AC未锁]

VC-030: proposal恢复核派发/执行/接收和pending/running、尝试产物预算，未知/冲突在途重派=0；正例只有限定动作预算结束判据的受控恢复。
       Layer: L2
       Output: [VERIFY] VC-030: unknown_state_redispatches=0 conflicting_redispatches=0 unbounded_recoveries=0
       Source: AC-030

- AC-031: 在proposal耗尽恢复及标记处理时，保留失败记录，清标记仅通过有前置检查/可追踪的恢复机制，不靠改记录/状态制造成功或越权续跑；有效授权证据复用、实质变更重判，仅确有独立审批才追加gate，不因工程故障默认等人。[ADDED @ 2026-10-25：H09验收推导，锁/标记/消费者待设计，完整AC未锁]

VC-031: proposal失败保留且标记清理有前置检查/原恢复关联，改状态造成功=0、未经验证清标记=0、同事项额外gate=0。
       Layer: L2
       Output: [VERIFY] VC-031: erased_failures=0 unsafe_marker_clears=0 fake_successes=0 redundant_gates=0
       Source: AC-031

- AC-032: 在roadmap/stage提案耗尽时，核实被拒提案/原因及工程或业务缺口，授权内具实质修订依据、预算与结束判据可重规划；无依据无限相似提案或越授权/硬预算规划执行次数为0，缺目标/优先级/权限具体问人，不默认等人。[ADDED @ 2026-10-25：H10验收推导，触发/限额/消费者待设计，完整AC未锁]

VC-032: roadmap耗尽授权内有实质修订/余预算/结束判据才重规划，旧原因可见；无限相似提案/越权硬预算投入=0，缺业务事项具体问人。
       Layer: L2
       Output: [VERIFY] VC-032: unsupported_replans=0 unbounded_proposals=0 unauthorized_planning_actions=0
       Source: AC-032

- AC-033: 在提案重规划时，保留旧提案/拒绝/失败、新版本表达修订，不清次数/重写状态绕限制；新stage启动仍须按H01审批，由重规划直接授新权限或启动次数为0。[ADDED @ 2026-10-25：H10验收推导，版本/归档/状态待设计，完整AC未锁]

VC-033: 重规划保留旧提案拒绝失败并以新版本关联，重置尝试/改历史绕限=0，规划直接授新权/启动=0，新stage另按H01。
       Layer: L2
       Output: [VERIFY] VC-033: reset_attempts=0 rewritten_proposals=0 planning_grants_or_starts=0
       Source: AC-033

- AC-034: 在请求halted stage恢复时，PM note给停止原因/消除证据、stage版本/影响key、目标方案、授权/余预算及动作结束判据；仅条件成立且approve有效时限定恢复。原停止事实通过恢复记录或新版本关联保留，抹历史/重置消耗预算/无依据恢复次数为0。[ADDED @ 2026-10-25：H11验收推导，结构/状态/消费者待设计，完整AC未锁]

VC-034: halted正例note具停止消除证据/版本影响/目标权限余预算结束判据且approve有效才限定恢复；抹停止历史/重置消耗/无依据恢复=0。
       Layer: L2
       Output: [VERIFY] VC-034: erased_stop_facts=0 reset_usage=0 unsupported_resumes=0
       Source: AC-034

- AC-035: 在halted源于用户明确停止/撤权或硬保护时，技术原因消除/DP选择不能替代恢复所需明确授权与硬检查，未经恢复授权解除人工停止或绕硬保护次数为0；其他三项不冒充已恢复或授新权限。[ADDED @ 2026-10-25：H11验收推导，授权证明/状态待设计，完整AC未锁]

VC-035: 人工停止撤权或硬保护负例，技术修复/DP选择不能替代恢复授权，未授权解除人工停止/绕硬保护=0，非approve项假恢复/增权=0。
       Layer: L2
       Output: [VERIFY] VC-035: unauthorized_user_stop_unlocks=0 hard_guard_bypasses=0 false_resumes=0
       Source: AC-035

- AC-036: 在自动决策熔断后，仅原因消除有可复核证据、恢复预授权及机器检查满足时，经明确授权受控通道按PM note限定恢复；被熔断链路绕刹车自批、决策不可用默认批准/偷换通道或越能力/权限/预算恢复次数为0。[ADDED @ 2026-10-25：H12验收推导，通道隔离/状态/消费者待设计，完整AC未锁]

VC-036: 隔离H12来源/预授权/消除证据/硬检查正例才限定恢复；普通熔断链、伪origin、无权、不可用负例自批/换通道/默认恢复=0。
       Layer: L2
       Output: [VERIFY] VC-036: breaker_self_approvals=0 unauthorized_recoveries=0 transport_bypasses=0
       Source: AC-036

- AC-037: 在熔断缺恢复授权/证据或用户明确停用撤权时，保持刹车并提出具体授权/信息问题；不自行解除人工限制、删刹车/改历史造成功，原熔断/恢复记录保留，reject不自动关闭项目，恢复观察/停止/再熔断范围明确。[ADDED @ 2026-10-25：H12验收推导，实际预授权/观察规则未设置，完整AC未锁]

VC-037: H12缺授权证据或用户撤权保持刹车且具体问题可见；原熔断及恢复保留，reject项目关闭=0；观察原因再现正例再熔断=1。
       Layer: L2
       Output: [VERIFY] VC-037: unauthorized_unlocks=0 erased_breaker_history=0 reject_project_closures=0 observed_retrip=1
       Source: AC-037

- AC-038: 在已批准适用规则要求key签收时，仅有效finalize及对应签收证据满足签收条件；continue/user-confirm、签收文件或QG通过不冒充phase done/stage关闭，不豁免必需验收/claim/契约/证据硬门，不增加第二次PM批准。[ADDED @ 2026-10-25：H13验收推导，真实词表/关联/消费者待设计，完整AC未锁]

VC-038: 原适用必需签收场景，仅当前有效finalize及对应证据可满足该项；同次判断写入且第二批准=0，continue/user-confirm/QG/文件存在代done或stage关闭=0。
       Layer: L2
       Output: [VERIFY] VC-038: second_sign_approvals=0 false_signed_conditions=0 automatic_done_or_stage_closes=0
       Source: AC-038

- AC-039: 在签收命名/硬门衔接及证据实质变更时，正确识别finalize契约，不伪造旧标签/disable规避原必需签收，不自动扩大强制范围或无条件复用受影响旧签收；原历史不补造。具体有效性/版本/框架写面待设计。[ADDED @ 2026-10-25：H13验收推导，完整AC未锁]

VC-039: finalize正确词表与当前matter/实质证据校验成立；旧词表或disable绕原强制规则、强制范围扩大、受影响旧签收复用/历史补造=0。
       Layer: L2
       Output: [VERIFY] VC-039: legacy_word_bypasses=0 signoff_scope_expansions=0 stale_signoff_reuses=0 historical_fabrications=0
       Source: AC-039

- AC-048: 在stalled处置送审时，停滞原因/真实状态、已尝试及产物、剩余额度/硬预算、下一方案/结束判据或遗留未完成影响/授权明确；gate仅按note批准限定继续或获授权具体遗留处置，不以预算剩余单独放行，不抹停滞/消耗、不自动降验收或取消目标。缺上述必要证据的有效放行次数为0。[ADDED @ 2026-10-25：毕业考H03专门条件，完整AC未锁]

VC-048: stalled note具原因状态/尝试产物/额度预算/方案结束判据或获权遗留影响，正例仅限定动作；缺项或只硬余额放行=0、抹历史消耗/降验收取消目标=0。
       Layer: L2
       Output: [VERIFY] VC-048: unsupported_stall_releases=0 erased_usage_or_failures=0 reduced_acceptance_or_goals=0
       Source: AC-048

- AC-049: 在gate选steer/need_fix且PM已准备对应后继材料、角色/授权有效、尚无同事项在途后继请求时，PM发起对应dp-pm-steer/dp-auto请求且有可核调用证据；后继未发起、调用失败、返回选择及实际整改分别可见，不由gate选择推断完成。重复请求或本gate因此放行次数为0。[ADDED @ 2026-10-25：毕业考后继正反观测，不新增固定双批或执行权，完整AC未锁]

VC-049: 已备合法后继且无在途时，steer和need_fix各有一次真实PM目标请求；未备/在途/调用失败/有回答/已执行分别可见，重复后继和原gate放行=0。
       Layer: L2
       Output: [VERIFY] VC-049: steer_successor_requests=1 fix_successor_requests=1 duplicate_successors=0 parent_releases=0
       Source: AC-049

- AC-052: 在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC-052: 同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。
       Layer: L2
       Output: [VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0
       Source: AC-052


## 验收命令
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_dp_consolidation_gate_effects.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
