---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_validity.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_concurrency.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/rework-r2/**
ac_refs: [AC-011, AC-019, AC-025, AC-027, AC-028, AC-029, AC-039, AC-052]
vc_refs: [VC-011, VC-019, VC-025, VC-027, VC-028, VC-029, VC-039, VC-052]
deps: [T03, T04]
execution: worker
---

## 本次 R2 有界覆盖（优先于下方历史卡文字）
本次是用户明确批准的原逻辑任务定点返工，不是新增逻辑任务或扩大交付。授权：`.agenticdoc/mw-dp-consolidation/evidence/implementation/s2-r2-approval-20261026.md:1`。原卡/原run/原红绿/原报告和PM复验证据全部只读留史；下方AC摘录的旧“未锁”注记是历史，当前完整SPEC/53AC已锁，不能据此放宽。
产品仅本卡frontmatter列出的原隔离文件；证据仅本次rework-r2目录（frontmatter/write_face为准）。先在实际副本完整读当前产品及测试到EOF，保存当前before bytes/SHA/EOL/既有diff，再把缺口写成指定测试内真实业务断言，亲自观察正确行为失败的red后才修改产品；import/collection错误不代行为红。保存所有失败迭代与完整stdout/stderr/rc，不以事后mutation或删原用例代红绿。
所有Python命令，包括静态import、脚本、子进程及临时探针，均python -B且PYTHONDONTWRITEBYTECODE=1；私有minimal UTF8 env、HOME/USERPROFILE/TEMP/project只在本次证据fixture、禁pytest plugin autoload/cache；真实HTTP/CLI/provider/服务和活对象禁用。测试导入路径必须绑实际副本。不得删除14个既有pyc或其他越面文件，不因gitignore/清洁要求/工具守卫拒绝绕写。任何新越面事件原样报告。
只跑本卡唯一assigned pytest文件；不跑生成器/其它测试/npm check/build/install，不改T03/T04、peer/消费者/TS/框架/config/预算/watchdog/权限/live原源/goal/spec或旧证据，不复制或刷新mirror。T06/T07不引入在写T08模块或未交接peer依赖；新发现接口/共享测试需求先报告PM，不能自改DAG或等peer写完偷读冒充独立性。
最后给完整after bytes/EOL/hash与增量diff、每项red→green的断言定位/命令/rc、peer-aware面核对（共享镜像合法peer变更不归自身，净hash不能证明作者独占或历史瞬时无写）、五节报告。只称本层已验证，不称生产授权/L2/真实并发/QG/签收/原stage已通过。普通原任务的终态由PM独立验证后自动决定原DAG后继；worker不得自己派后继、交接通过或改phase。

### 本次精确修复与验收重点
读PM `.agenticdoc/mw-dp-consolidation/evidence/implementation/t06-pm-handoff-20261026/report.md:1`、probe.json、supplement.json（九当前失败边界），不能执行会覆盖原证据的PM脚本。
- required successful signoff仅有效finalize；continue/user-confirm保留合法业务菜单但不能判required签收valid。核真实key/matter/scope关联及非空可追溯signoff引用；不要用fixture artifact文本声称生产产物已验；不扩大签收强制范围。当前SignoffRef不记合同等缺口只在本卡可证明范围内修，生产引用解析仍原后继，不造trust源。
- 请求合同变更的相关旧证据不能仅记reason后仍applies/reusable；保留语义等价/不受影响依赖复用、自然语言unknown，不用全字节hash制造全量重审。
- 混合法/非法路径时完整claim请求失败关闭；同owner不同task的同文件active claim不可当clear，合法同任务复入/无冲突正例仍成立；不抢claim或执行锁操作。
- 匹配已存effect记录的非法/缺失状态不能当未执行而proceed；unknown/in-progress保持blocked，已applied去重、明确失败及真实无记录等合法正例按原契约保留，不把所有状态无差别冻结。
证据至少逐项genuine red→green与正向控制，保持pure stdlib模块，无I/O/CLI/conductor/peer imports。唯一测试test_dp_consolidation_concurrency.py。


## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T06 — 实现只读事项/实质依赖/授权及证据适用性核验，不以全字节hash变动强制重复审批。

## 状态
本次R2代码状态：未开始；验证状态：需复验；task状态：not-queued。原任务done/exit0/acked及旧失败留史，本句不代新尝试完成。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
结构化依赖语义等价、受影响变更、撤权、claim/版本冲突、自然语言unknown均有负例；纯函数不import CLI/conductor或写grant。T20/T31后续接管同一测试文件须依赖及hash交接；本卡先测纯判断，不冒充实际并发对账已验证。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_validity.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_concurrency.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/rework-r2/**

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
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_dp_consolidation_concurrency.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 本R2不运行任何生成器或额外suite，唯一assigned测试按上文。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
