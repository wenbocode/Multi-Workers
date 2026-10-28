---
type: coding
write_face:
  - packages/multi-workers/decision_validity.py
  - packages/multi-workers/test_dp_consolidation_concurrency.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/**
ac_refs: [AC-011, AC-019, AC-025, AC-027, AC-028, AC-029, AC-039, AC-052]
vc_refs: [VC-011, VC-019, VC-025, VC-027, VC-028, VC-029, VC-039, VC-052]
deps: [T03, T04]
execution: worker
---

# T06 — 实现只读事项/实质依赖/授权及证据适用性核验，不以全字节hash变动强制重复审批。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
结构化依赖语义等价、受影响变更、撤权、claim/版本冲突、自然语言unknown均有负例；纯函数不import CLI/conductor或写grant。T20/T31后续接管同一测试文件须依赖及hash交接；本卡先测纯判断，不冒充实际并发对账已验证。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- packages/multi-workers/decision_validity.py
- packages/multi-workers/test_dp_consolidation_concurrency.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-011: 在八入口处理同一具体事项时，职责表按主体/对象/动作及实质证据指定唯一业务审批归属；路由不代业务审批，同对象/实质证据版本重放不产生额外同事项审批或重复动作。实质影响变化的重审另留痕，不把所有不同gate文件或新材料一律当不同事项。[REVISED @ 2026-10-25：毕业考去除“四门”旧范围，完整AC未锁]

VC-011: 同主体对象动作实质版本在不同标签/文件重放及并发，只一个业务审批owner，额外同事项审批=0、重复动作=0；路由放行=0。
       Layer: L2
       Output: [VERIFY] VC-011: duplicate_approvals=0 duplicate_actions=0 route_releases=0
       Source: AC-011

- AC-019: 在影响启动的goal、stage目标、key交付范围/依赖或授权边界发生实质版本变化时，autopilot不以旧批准启动并重新判断；同一事项同一证据版本重复处理产生的额外同事项审批与业务动作次数均为0。

VC-019: 启动依赖实质变化使受影响旧批准复用=0；同版本及语义等价重复额外审批/动作=0；需要重新判断的新实质版本有真实关联。
       Layer: L2
       Output: [VERIFY] VC-019: stale_starts=0 duplicate_approvals=0 duplicate_actions=0
       Source: AC-019

- AC-025: 在实质goal变更影响key/验收/依赖/写面时，不以受影响旧批准放行；缺新业务意图/权限/风险取舍明确用户决定项，工程补证不造授权，不影响事项有效证据复用且纯非实质变更不重复实质审批。越权限/预算/承诺变化自动执行次数为0。[ADDED @ 2026-10-25：由H06认可推导，具体失效/授权绑定待设计，完整AC未锁]

VC-025: 实质goal变更只失效受影响key/验收/依赖/写面批准，缺意图权限具体问人；越权执行=0、无关/纯排版重复审批=0。
       Layer: L2
       Output: [VERIFY] VC-025: stale_affected_releases=0 unauthorized_actions=0 irrelevant_reapprovals=0
       Source: AC-025

- AC-027: 在跨key受限修复派发/执行时，明确执行者及受限写面且仍通过claim/角色/独占写面检查；因DP批准而抢占他窗claim、双Worker同文件并写、越权限修改或拒绝后自动关闭次数均为0，选择不冒充已派发/修改。[ADDED @ 2026-10-25：H07验收推导，具体授权绑定/协调/消费待设计，完整AC未锁]

VC-027: 实际跨key执行者/claim/角色/独占面检查成立；抢他窗claim、双Worker同文件并写、越权及reject自动关闭=0，选择不得冒充派发/修改。
       Layer: L2
       Output: [VERIFY] VC-027: claim_thefts=0 concurrent_file_writers=0 unauthorized_actions=0 fake_dispatches=0
       Source: AC-027

- AC-028: 在申请冻结AC/VC变更时，PM note明确指定key/条目、前后差异/理由、承诺与证据影响、授权/重验安排；approve只批准限定具体变更，旧批准用于未经批准的新变更、无授权删减验收或伪造完成次数为0。越授权或意图不明具体问人。[ADDED @ 2026-10-25：H08验收推导，具体绑定/消费待设计，完整AC未锁]

VC-028: 冻结变更仅指定key/条目/前后差异/承诺影响/权限/重验安排获准，旧批准套新变更、未授权降验收和伪完成=0。
       Layer: L2
       Output: [VERIFY] VC-028: reused_unrelated_change_approvals=0 unauthorized_acceptance_reductions=0 fabricated_completion=0
       Source: AC-028

- AC-029: 在冻结AC/VC获准变更后，重新验证受影响部分，不直接沿用旧条件通过；原要求/失败/变更历史不改写，dp-QG reopen不直接授予修改权限，reject不自动改契约/关闭/签收。不受影响有效证据依既有规则复用。[ADDED @ 2026-10-25：H08验收推导，具体版本/失效/状态待设计，完整AC未锁]

VC-029: 冻结变更后受影响旧证据通过=0，需真实重验；历史原要求/失败/批准字节不改；QG reopen或gate reject自动改契约/签收关闭=0。
       Layer: L2
       Output: [VERIFY] VC-029: stale_acceptance_passes=0 rewritten_history=0 automatic_contract_or_closure_changes=0
       Source: AC-029

- AC-039: 在签收命名/硬门衔接及证据实质变更时，正确识别finalize契约，不伪造旧标签/disable规避原必需签收，不自动扩大强制范围或无条件复用受影响旧签收；原历史不补造。具体有效性/版本/框架写面待设计。[ADDED @ 2026-10-25：H13验收推导，完整AC未锁]

VC-039: finalize正确词表与当前matter/实质证据校验成立；旧词表或disable绕原强制规则、强制范围扩大、受影响旧签收复用/历史补造=0。
       Layer: L2
       Output: [VERIFY] VC-039: legacy_word_bypasses=0 signoff_scope_expansions=0 stale_signoff_reuses=0 historical_fabrications=0
       Source: AC-039

- AC-052: 在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC-052: 同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。
       Layer: L2
       Output: [VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0
       Source: AC-052


## 验收命令
- cwd=packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_dp_consolidation_concurrency.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
