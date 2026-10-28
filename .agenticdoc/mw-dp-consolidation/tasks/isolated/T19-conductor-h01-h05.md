---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/conductor.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_gate_effects.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t19-conductor-h01-h05/**
ac_refs: [AC-007, AC-008, AC-010, AC-011, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-048, AC-049, AC-052]
vc_refs: [VC-007, VC-008, VC-010, VC-011, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-048, VC-049, VC-052]
deps: [T11, T12, T13, T14, T15, T16, T17, T18]
execution: worker
---

## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T19 — H01启动/H02关闭/H03停滞/H04软追加/H05复核条件接入原conductor且不自批解锁。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
同事项一个owner；真实补证不是权限授予，软追加不提高硬量，reject不默认rework/halted。只在测试temp stage运行，不调用活tick/改真实gate/brake/roadmap；H12恢复handler不得注册到普通熔断链。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/autopilot/conductor.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_gate_effects.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t19-conductor-h01-h05/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-007: 在PM提交gate背景/当前状态及送审前预拟note（事项、批准后动作、目标/证据/预算/授权依据）时，dp-gate-approve按§1.2选择approve/steer/need_fix/reject；PM note与模型理由分别保存。steer交PM发起dp-pm-steer，need_fix交PM发起dp-auto，均不作为本gate放行或已整改证据；reject仅在有明确获授权遗留关闭方案时允许对应收尾，越权执行次数为0。精确schema/状态/消费留设计。[REVISED @ 2026-10-25：用户确认四选项及note/reject边界，替代二选项目标；完整AC未锁]

VC-007: gate四选择分别观测PM note与模型依据独立来源；steer/need_fix不放行不声明整改，reject无具体遗留授权时收尾=0。
       Layer: L2
       Output: [VERIFY] VC-007: gate_choices=4 mixed_note_basis=0 false_release_or_repair=0 unauthorized_closure=0
       Source: AC-007

- AC-008: 在具体gate的自动处理启用/授权条件缺失或硬检查失败时，dp-gate-approve任何结果均不产生有效放行，未授权业务副作用次数为0，缺失/失败条件明确记录；其他工程取证仍受原授权约束，不造启用或权限。[REVISED @ 2026-10-25：毕业考点名当前入口/可构造失败条件，完整AC未锁]

VC-008: 对启用、授权、预算、claim和机器条件逐项缺失/失败负例，任何gate选择的有效放行/越权副作用=0，并保留各具体原因。
       Layer: L2
       Output: [VERIFY] VC-008: unauthorized_releases=0 unauthorized_effects=0 missing_failure_reasons=0
       Source: AC-008

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

- AC-016: 在启动判断仅缺可在授权内补齐的工程证据时，autopilot安排补证/修订后重新判断，补齐前stage启动次数为0，不把该工程缺口直接作为必须人工授权的理由。

VC-016: 仅缺授权内工程证据先实际补证，补齐前stage启动=0、把工程缺口升级为新权限请求=0；补齐后可重新判断。
       Layer: L2
       Output: [VERIFY] VC-016: premature_starts=0 fabricated_permission_needs=0
       Source: AC-016

- AC-017: 在启动判断缺用户业务意图或超出目标/写面/硬预算授权时，autopilot升级信息明确列出缺失意图或所需新权限，越权启动和执行次数均为0，不推测授权代替用户。

VC-017: 缺真实用户业务意图或越目标/写面/硬预算的启动场景，具体缺失项/所需权限可见，越权启动及执行=0。
       Layer: L2
       Output: [VERIFY] VC-017: unauthorized_starts=0 unauthorized_actions=0 vague_escalations=0
       Source: AC-017

- AC-018: 在启动路径任一机器硬检查失败时，autopilot记录具体阻断并保持该动作停止/等待/修复，因DP批准而豁免硬检查的次数为0。

VC-018: 启动各硬检查失败时停止对应动作，DP选approve也不得豁免，具体阻断无遗漏。
       Layer: L2
       Output: [VERIFY] VC-018: waived_hard_checks=0 hidden_start_blockers=0
       Source: AC-018

- AC-019: 在影响启动的goal、stage目标、key交付范围/依赖或授权边界发生实质版本变化时，autopilot不以旧批准启动并重新判断；同一事项同一证据版本重复处理产生的额外同事项审批与业务动作次数均为0。

VC-019: 启动依赖实质变化使受影响旧批准复用=0；同版本及语义等价重复额外审批/动作=0；需要重新判断的新实质版本有真实关联。
       Layer: L2
       Output: [VERIFY] VC-019: stale_starts=0 duplicate_approvals=0 duplicate_actions=0
       Source: AC-019

- AC-020: 在软轮次耗尽且已有授权允许追加时，dp-gate-approve仅在PM note具备真实进展、预算依据及下一轮明确目标/方案/结束判据时可批准限定追加；不能以硬预算尚余自动批准，无授权或无依据重复追加次数为0。精确计量/消费待设计。[ADDED @ 2026-10-25：由H04认可推导，完整AC未锁]

VC-020: 有软追加授权且note具真实进展/预算/方案/结束判据正例仅限定delta追加；无授权/无计划或只凭硬余额负例追加=0。
       Layer: L2
       Output: [VERIFY] VC-020: unbounded_extensions=0 unsupported_extensions=0
       Source: AC-020

- AC-021: 在追加软轮次、steer或need_fix处理将突破硬预算时，不执行越界投入；提高硬预算须取得包含具体追加量/用途/风险的明确人工授权，因DP选择而自行提高硬预算或越界续跑次数为0。[ADDED @ 2026-10-25：由H04认可推导，未设置实际预算值，完整AC未锁]

VC-021: 软追加、steer或need_fix将越硬预算时越界执行=0、自行提高硬上限=0；必须具体追加量/用途/风险授权问题，累计消耗不重置。
       Layer: L2
       Output: [VERIFY] VC-021: hard_budget_overruns=0 self_granted_limits=0 reset_usage=0
       Source: AC-021

- AC-022: 在pending-review因到期、依赖交付或新证据触发复核时，触发不自动恢复或要求人工；仅目标有效、阻断解除且证据/授权/预算满足时，approve可按PM note恢复，无依据恢复次数为0。具体事件/阈值/状态待设计。[ADDED @ 2026-10-25：由H05认可推导，完整AC未锁]

VC-022: pending复核事件/到期只触发评估，不自动恢复/默认要求人工；正例目标有效且阻断消除及证据授权预算充分才approve恢复，无依据恢复=0。
       Layer: L2
       Output: [VERIFY] VC-022: event_only_resumes=0 unsupported_resumes=0 mandatory_human_waits=0
       Source: AC-022

- AC-023: 在pending-review处理选择steer/need_fix/reject时，按§1.2移交PM或拒绝当前方案，不把reject默认映射返工，不冒充已整改/恢复；越权预算/目标/写面变更及无授权遗留关闭次数为0，复用同份有效质量证据不重复审核。[ADDED @ 2026-10-25：由H05认可推导，完整AC未锁]

VC-023: pending三非approve项真实交PM或拒绝方案，reject默认返工=0、假恢复整改=0、越权目标预算写面/遗留关闭=0，同证据重复QG=0。
       Layer: L2
       Output: [VERIFY] VC-023: default_reworks=0 false_resumes=0 unauthorized_changes=0 redundant_qg=0
       Source: AC-023

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
