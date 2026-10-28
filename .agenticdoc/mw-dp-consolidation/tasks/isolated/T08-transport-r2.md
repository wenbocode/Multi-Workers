---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_backends.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_materials.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport/rework-r2/**
ac_refs: [AC-002, AC-004, AC-007, AC-012, AC-014, AC-040, AC-042, AC-043, AC-051]
vc_refs: [VC-002, VC-004, VC-007, VC-012, VC-014, VC-040, VC-042, VC-043, VC-051]
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
读PM `.agenticdoc/mw-dp-consolidation/evidence/implementation/t08-pm-handoff-20261026/report.md:1`、probe.json；不能执行会覆盖原证据的PM脚本。
- max_questions=1等现有边界必须返回明确prepared失败/零业务决定/零HTTP，不让DecisionInputError直接逃逸；不得提高/放宽原额度，保留generic decide契约/原retry-budget/box拒绝。
- replay_check仅明确合法bool可证明hit/miss；null、unknown字符串或其他非法/未知结果失败关闭，不伪造replayed成功/novelty而发请求。true/false正例保留，25retired在replay/credential/backend前拒绝，实际T10store/T23CLI仍后继。
- 同请求choice+basis无默认/补请求、不裁剪核心、timi POST/v1/decisions、jev-latest、bare Authorization保留。缺/错/不适用basis保持业务0。
- 额外核清raw transport成功记录与业务拒绝分层：PM只证generic transport行true与prepared业务false并存，未证明已新增有效业务裁决。不要贸然改冻结generic response/REASON_CODES、增加第二决策账本或越面修T10/T23；若本面能无破坏明确分层则测试证实，否则把准确约束/未覆盖链/后继验收说明写入报告，不用假全链绿解除债。
新pytest行为red→green覆盖cap/非法lookup及控制，fake_http始终阻断真实socket；原73用例保留按合法预期修缺陷，不去跑其它既有套件。唯一测试test_dp_consolidation_materials.py。


## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T08 — 原timi通道同次业务choice与basis选择校验成立，失败无默认执行，完整材料不截断。

## 状态
本次R2代码状态：未开始；验证状态：需复验；task状态：not-queued。原任务done/exit0/acked及旧失败留史，本句不代新尝试完成。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
固定POST /v1/decisions、jev-latest、bare Authorization，保留原重试/预算/box拒绝；不猜自由reason字段、不换provider、无第二补理由调用。fake HTTP覆盖缺回答/错basis/引用不存在/不适用/超界、25ID及replay零请求；记录attempt与业务决定分别计数。禁止真实endpoint/凭证。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_backends.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_materials.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport/rework-r2/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-002: 在迁移后的各运行入口请求任一旧编号DP时，返回明确拒绝，模型请求数、业务执行数及新增有效业务决策数均为0；历史只读或安全拒绝审计不恢复调用，也不被错误当成新增成功裁决。[REVISED @ 2026-10-25：旧编号非默认别名，拒绝范围与业务/安全记录分清，完整AC未锁]

VC-002: 对每个25旧ID分别从所有运行入口及已有logical_id replay提交，明确retired拒绝；模型/业务动作/新增有效决定各0，安全审计不计成功。
       Layer: L2
       Output: [VERIFY] VC-002: rejected_old_ids=25 model_calls=0 business_actions=0 valid_decisions=0
       Source: AC-002

- AC-004: 在各DP提交其合法业务材料时，dp-sign-key保持mw-decision-context已确认的交付目标/实际完成/已验证与未验证证据/未完成影响及finalize/continue/user-confirm签收语义；dp-w-type四候选及图像硬门、dp-pm-steer四项不降目标、dp-w-check-task三项fire-and-forget均按§1.2。增权、缩减目标/验收、冒充执行/完成或新增Worker同步等待次数为0；各分支正向观测补充见AC-044～047、038/039。[REVISED @ 2026-10-25：毕业考点名业务基线/当前入口并保留原四职责修改确认，完整AC未锁]

VC-004: w-type/pm-steer/w-check/sign-key基线合法场景分别走其全部选择，原签收四部及三数组成立；增权/降目标/假执行完成/新增同步等待均0。
       Layer: L2
       Output: [VERIFY] VC-004: baseline_contract_violations=0
       Source: AC-004

- AC-007: 在PM提交gate背景/当前状态及送审前预拟note（事项、批准后动作、目标/证据/预算/授权依据）时，dp-gate-approve按§1.2选择approve/steer/need_fix/reject；PM note与模型理由分别保存。steer交PM发起dp-pm-steer，need_fix交PM发起dp-auto，均不作为本gate放行或已整改证据；reject仅在有明确获授权遗留关闭方案时允许对应收尾，越权执行次数为0。精确schema/状态/消费留设计。[REVISED @ 2026-10-25：用户确认四选项及note/reject边界，替代二选项目标；完整AC未锁]

VC-007: gate四选择分别观测PM note与模型依据独立来源；steer/need_fix不放行不声明整改，reject无具体遗留授权时收尾=0。
       Layer: L2
       Output: [VERIFY] VC-007: gate_choices=4 mixed_note_basis=0 false_release_or_repair=0 unauthorized_closure=0
       Source: AC-007

- AC-012: 在八入口任一请求决策不可用、材料非法或返回无有效裁决时，对应受门控动作保持阻塞并显示具体原因，默认放行次数为0，不用当前状态补造结果、偷换入口或把失败冒充业务选项；不编造decision_id/执行回执。[REVISED @ 2026-10-25：毕业考明确全入口失败防御，合法失败审计不被禁止，完整AC未锁]

VC-012: 八入口材料非法/不可用/无有效选择，各受门控动作=0且原因可见；伪造decision_id/执行回执、默认选择及换入口绕失败=0。
       Layer: L2
       Output: [VERIFY] VC-012: default_actions=0 fabricated_results=0 failure_bypasses=0
       Source: AC-012

- AC-014: 在审核及反馈跨Python/TS/观察界面传递时，真实producer→writer→consumer→projection链可由隔离生产路径测试核验，建议、实际处理和完成状态不互相冒充；秘密明文和注入脚本执行次数为0。

VC-014: Python/TS真实producer→writer→consumer→projection链可关联，选择/执行/完成不混同；请求、记录、DOM秘密明文及注入执行=0。
       Layer: L2
       Output: [VERIFY] VC-014: broken_links=0 false_execution_or_completion=0 secret_leaks=0 script_executions=0
       Source: AC-014

- AC-040: 在PM提交主体/对象/具体待决问题清楚的临时问题时，dp-route只选择§1.1其余七入口之一，入口选择及依据可见，所选业务结论/业务动作不得由路由答复推断，路由造成的业务放行/执行次数为0。目标材料仍按所选入口合同准备。[ADDED @ 2026-10-25：毕业考推导，技术字段/记录留设计，完整AC未锁]

VC-040: route分别选择七目标并显示依据，入口选择不能推出目标业务结论，路由业务放行/执行=0，目标材料另准备。
       Layer: L2
       Output: [VERIFY] VC-040: routed_targets=7 route_releases=0 route_actions=0
       Source: AC-040

- AC-042: 在PM为现场问题准备合法可区分行动候选及后果/约束时，dp-auto仅从该候选集合选择，选择、理由及关键依据可核，未准备新方案出现数为0；实际动作仍由PM按权限执行，不代固定审核/签收/审批。不套用旧dp3候选数量/技术ID限制。[ADDED @ 2026-10-25：毕业考推导，候选schema留设计，完整AC未锁]

VC-042: auto覆盖不同现场候选数目/非cN ID，实际choice只在提交集合且依据匹配真实引用；未备方案/伪理由/增权或代固定审批签收=0。
       Layer: L2
       Output: [VERIFY] VC-042: invented_candidates=0 invalid_basis_refs=0 unauthorized_or_substituted_actions=0
       Source: AC-042

- AC-043: 在八入口分别构造非法/缺失材料、服务不可用及不匹配或缺失选择时，均可观察具体失败/阻塞且受门控业务动作次数为0；不默认首候选/approve、不偷换通道、不造用户意图/授权或有效选择。原失败保留，可记录真实安全/失败审计而不伪造成功裁决。[ADDED @ 2026-10-25：毕业考异常对照，完整AC未锁]

VC-043: 八入口分别构造缺项、错type、不可用、缺选择、错选择或依据不匹配，具体失败逐例可见，受门控动作=0、默认首项/approve/换通道/造授权=0。
       Layer: L2
       Output: [VERIFY] VC-043: failed_entries=8 failure_actions=0 fabricated_approvals=0 hidden_failure_cases=0
       Source: AC-043

- AC-051: 在允许null的任务进展快照中，未记录null与明确无项[]保持可区分，投影不回填历史或由agent-report产生执行权限；dp-sign-key的verified/unverified/unfinished_impact仍按原数组契约，[]表示真实无，缺项不能改成null造有效材料。秘密明文或历史字节改写次数为0。[ADDED @ 2026-10-25：毕业考区分快照/签收契约，非新增材料schema，完整AC未锁]

VC-051: task进展null和[]序列化及投影可区分，sign三数组缺项/null拒绝而合法[]保留；agent-report增权、秘密泄漏或历史回写=0。
       Layer: L2
       Output: [VERIFY] VC-051: null_empty_conflations=0 invalid_sign_arrays_accepted=0 agent_report_grants=0 secret_or_history_violations=0
       Source: AC-051


## 验收命令
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_dp_consolidation_materials.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 本R2不运行任何生成器或额外suite，唯一assigned测试按上文。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
