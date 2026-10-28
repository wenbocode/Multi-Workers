---
type: coding
write_face:
  - packages/multi-workers/autopilot/decision_recovery.py
  - packages/multi-workers/test_dp_consolidation_recovery.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t21-recovery-handler/**
ac_refs: [AC-008, AC-021, AC-030, AC-031, AC-034, AC-035, AC-036, AC-037, AC-052]
vc_refs: [VC-008, VC-021, VC-030, VC-031, VC-034, VC-035, VC-036, VC-037, VC-052]
deps: [T11, T12, T13, T14, T15, T16, T17, T18]
execution: worker
---

# T21 — H11/H12独立受控handler验证真实来源/预授权/原因消除/观察再熔断，普通链自调用明确拒绝。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
先吸收T02资格缺口结论；无法在已批面证明真实来源则对应任务blocked，不能造布尔授权/人类身份。handler不改policy/权限/预算，失效/撤权/不可用保持停止，无新通道。入口实链须和T24/T26验证，纯handler测试不代入口证明。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- packages/multi-workers/autopilot/decision_recovery.py
- packages/multi-workers/test_dp_consolidation_recovery.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t21-recovery-handler/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-008: 在具体gate的自动处理启用/授权条件缺失或硬检查失败时，dp-gate-approve任何结果均不产生有效放行，未授权业务副作用次数为0，缺失/失败条件明确记录；其他工程取证仍受原授权约束，不造启用或权限。[REVISED @ 2026-10-25：毕业考点名当前入口/可构造失败条件，完整AC未锁]

VC-008: 对启用、授权、预算、claim和机器条件逐项缺失/失败负例，任何gate选择的有效放行/越权副作用=0，并保留各具体原因。
       Layer: L2
       Output: [VERIFY] VC-008: unauthorized_releases=0 unauthorized_effects=0 missing_failure_reasons=0
       Source: AC-008

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

- AC-052: 在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC-052: 同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。
       Layer: L2
       Output: [VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0
       Source: AC-052


## 验收命令
- cwd=packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_dp_consolidation_recovery.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
