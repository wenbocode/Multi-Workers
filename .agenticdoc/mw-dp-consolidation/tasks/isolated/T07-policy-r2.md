---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_policy.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_recovery.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t07-policy/rework-r2/**
ac_refs: [AC-008, AC-020, AC-021, AC-022, AC-034, AC-035, AC-036, AC-037]
vc_refs: [VC-008, VC-020, VC-021, VC-022, VC-034, VC-035, VC-036, VC-037]
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
读PM `.agenticdoc/mw-dp-consolidation/evidence/implementation/t07-pm-handoff-20261026/report.md:1`、probe.json、supplement.json（七负例+已撤policy规则ref换request otherref绕过）；不能执行会覆盖原证据的PM脚本。
- pending-review同时核policy与请求required_scope，缺失/越scope不能给allowed=true空scope；合法非空范围正例保留，事件/到期只触发评估。
- 恢复核policy.recovery.authority_ref及请求引用的适用关系/撤权/范围，不只解析request的otherref。已撤/无关引用不得绕过；但不要盲强制两ref相等而拒绝H11真实新human授权。新授权须可验证明确替代/恢复原停止的关系，不造自报或可编辑文件trust源。生产资格证明不在本层创造。
- halted硬guard验证缺失/非法未知、停止origin未知不默认cleared/技术停止；人工停止/撤权须明确恢复授权，保持硬保护。breaker缺user_disabled/非法未知等不默认为False，伪origin/未知消除证据保持阻塞。
- 保留预算单位/累计消耗、原停止/熔断事实、受控H12来源、合法disable；不修改冻结21键/defaults或设新预算/授权/时限。read-only config只按原只读依赖，不import CLI/conductor/在写T08。
每组真实行为red→green，含合法原引用/受限scope及合法明确新H11human恢复控制。唯一测试test_dp_consolidation_recovery.py。


## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T07 — 只读policy校验真实授权引用/范围/单位/累计预算及恢复条件，缺失或非法fail-closed。

## 状态
本次R2代码状态：未开始；验证状态：需复验；task状态：not-queued。原任务done/exit0/acked及旧失败留史，本句不代新尝试完成。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
不修改冻结config21键/默认值，不创建活policy或新grant，不把round_budget/worker_timeout当项目硬授权。模拟授权只在隔离fixture有真实受控writer来源；自报origin/TTY/token等不充分。缺原因消除/观察/停止条件保持阻塞，不设新预算数值。T21在本卡后接管恢复测试。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_policy.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_recovery.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t07-policy/rework-r2/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-008: 在具体gate的自动处理启用/授权条件缺失或硬检查失败时，dp-gate-approve任何结果均不产生有效放行，未授权业务副作用次数为0，缺失/失败条件明确记录；其他工程取证仍受原授权约束，不造启用或权限。[REVISED @ 2026-10-25：毕业考点名当前入口/可构造失败条件，完整AC未锁]

VC-008: 对启用、授权、预算、claim和机器条件逐项缺失/失败负例，任何gate选择的有效放行/越权副作用=0，并保留各具体原因。
       Layer: L2
       Output: [VERIFY] VC-008: unauthorized_releases=0 unauthorized_effects=0 missing_failure_reasons=0
       Source: AC-008

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


## 验收命令
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_dp_consolidation_recovery.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 本R2不运行任何生成器或额外suite，唯一assigned测试按上文。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
