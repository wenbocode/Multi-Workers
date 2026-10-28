---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r3/**
ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-007, AC-012, AC-040, AC-041, AC-042, AC-043, AC-044, AC-046, AC-051, AC-053]
vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-007, VC-012, VC-040, VC-041, VC-042, VC-043, VC-044, VC-046, VC-051, VC-053]
deps: [T01, T02]
execution: worker
---

# T03-R3 — 补齐第三项测试演进残留（同一逻辑T03，有界新尝试）

## 状态
本尝试代码未开始/验证需复验/task not-queued；原T03及R2均done/exit0/acked，事实不改。semantic_handoff_verified=false，T04未派。此卡不是第37/38个逻辑任务或新的目标/预算授权。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定spec.md:128/53AC、已批design.md:201/53VC及plan.md、implementation-isolated-dag.json、implementation-isolation.md。具体人工处置evidence/implementation/t03-r3-approval-20261026.md；当前主根为本key，产品root仅implementation-worktree；证据仍归本key。下列AC/VC从原T03/R2逐字继承，原“未锁”注记只是历史，当前已锁，不可改合同。
PM证据evidence/implementation/t03-r2-pm-handoff-20261026/{report.md,check.py,check.json,probe.json,pm-green.log,pm-probe.log}；原R2卡只读。当前测试test_decide_registry_contract.py:448解析成功仍强制dp4，:497 post-T04仍强制四旧行，两个active-only合成目标实测拒绝。两validator已局部修复/166绿测，不能再改生产协议或重新实现八入口。PM本轮predispatch baseline在evidence/implementation/t03-r3-pre-dispatch/；开工必须自己读取最新，不刷新copy。

## 要求
唯一产品任务是测试文件内两个相同第三项根因：把已退休编号存在性误当解析成功/合法活矩阵的永久前提。只做相关最小helper/断言与回归修复：
1. 不要求dp4或DP1_ID等旧名字作为解析非空/成功证明。真实parser须能接受八active合法required-field矩阵（无旧行），同时对未解析、截断/重复/非法key及字段异常保留有意义拒绝，不改生产TS/生成器以迎合测试。
2. 迁移阶段可保留当前真实TS债/四旧行的准确内容锁，但post-T04以及后续消费八合同不能永久强制旧行存在；独立只读历史/旧cases仍保持。T04只生成TS，T11才改triage-client，二者并不同时发生，不新增“必须同一轮同时迁移”或其他后继无写权的阶段锁。仅八active的目标矩阵合法；仍存在的旧行不得变更字段或混入未知ID，阶段/非法混合的实质反例不删。
3. 新行为回归写在本卡唯一允许测试文件；先保存真实red（原函数仍坏），再最小修改helper与断言后green。两个断言分别证明，不能用旧collection/测试自身拼写错误冒充产品red。真实TS文本fixture走parser正例，不只monkeypatch解析返回值；覆盖合法pre-T04债、post-T04旧consumer过渡、后继active-only、没有旧DP1_ID的合法新名常量/字面键形态及非法字段/未知ID/空或未解析/重复/混合生成IDs等适用反例。测试形态按已有合同，不自立完整TS解析器或新字段/限制，发现无法面内修复如实报告。
4. 保留本文件原有身份/字段type/位置/字节/枚举/八注册/独立retired/实际wiring声明验证与已修两validator的原验收；不可skip/xfail或删除验收换绿、不放宽任意输入。合成fixture明确标非T04真实生成/parity/接线/TS compile证明。导入测试函数或mock只能测试validator，不伪造业务PASS。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r3/**

## 写入禁止面
除此以外全部禁止。特别：decision_points.py、decide_registry.json、test_dp_consolidation_registry.py及13handoff同名镜像、triage-client.ts/生成TS/生成器/四旧case只读；原T03/R2证据及worker run/output/card、PM state/manifest/approval/baseline只读。活源码/所有框架clone/mirror、pi核心、spec/goal/53AC/VC、他key、config/policy/gate/brake/ledger/凭证/预算/签名、dependency/lock/dist/install/build/restart/commit/push无权。无symlink/junction/hardlink/重copy覆盖，不能重置watchdog、私设timeout/授权/无限重试。原服务dp4不可用不再请求/换渠道/修活桥或伪造receipt；本次由具体人工确认授权正常dispatch而非dp4成功。

## 开工和隔离约束
完整读唯一产品文件、另一验收测试及需要比较的最新只读协议/TS peer/生成TS到实际EOF；read工具分段续读，hash不代EOF。完整读已有本卡引用的两断言/红绿/报告，不覆盖他人dirty。保存当前四文件before/after bytes/SHA/EOL和完整实际diff、13交接hash（表仅一个协议变，两个测试不在13表，应如实区分）；保存其他受保护/主树及原证据边界的before/after，mtime需按真实run起点且不声称独占作者。
所有脚本/log/private fixture/home/project/temp仅本卡evidence，最小env不继承provider/worker/project config，PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、-p no:cacheprovider；逐实际import/subprocess argv核副本path。Fake backend/无真实HTTP/决策CLI/服务探针；测试通过生产writer的业务project只能独立fixture，不能写源码树/祖先活对象。read-only peer fixture副本限证据内，不造T04已生成。唯一产品改动按edit精确替换，避免全文件format/EOL变化。

## AC摘录及VC合同
- AC-001: 在目标注册/schema及运行入口迁移完成后，可调用DP集合精确等于§1.1八个目标名称，旧编号可调用别名数为0；六项职责迁移、19项旧独立职责退出与两个新增入口分开可核，不以原八项/17计数判定。[REVISED @ 2026-10-25：毕业考按已确认组成整合，原草案字节另存，完整AC未锁]

VC-001: 迁移后的注册、生成TS、CLI及观察提交集合都精确为§0八名；aliases=0，migrated_roles=6，retired_roles=19，added_entries=2。
       Layer: L2（L0生成锁辅助）
       Output: [VERIFY] VC-001: active=8 aliases=0 migrated=6 retired=19 added=2
       Source: AC-001

- AC-002: 在迁移后的各运行入口请求任一旧编号DP时，返回明确拒绝，模型请求数、业务执行数及新增有效业务决策数均为0；历史只读或安全拒绝审计不恢复调用，也不被错误当成新增成功裁决。[REVISED @ 2026-10-25：旧编号非默认别名，拒绝范围与业务/安全记录分清，完整AC未锁]

VC-002: 对每个25旧ID分别从所有运行入口及已有logical_id replay提交，明确retired拒绝；模型/业务动作/新增有效决定各0，安全审计不计成功。
       Layer: L2
       Output: [VERIFY] VC-002: rejected_old_ids=25 model_calls=0 business_actions=0 valid_decisions=0
       Source: AC-002

- AC-003: 在盘点生产源码/配置/提示词/case及UI提交面后，旧编号活跃注册/调用/可提交选项数为0；六迁移与19退出职责逐项对应目标/拒绝处理，必要历史解释、安全拒绝与回归测试标注用途，不因删DP删除硬检查或其他框架任务类型。[REVISED @ 2026-10-25：按最新组成替代旧范围，不作为源码删除授权，完整AC未锁]

VC-003: 受限生产caller/config/prompt/case/UI清单逐项分类后，旧ID活跃注册/调用/可提交数=0；六迁移与19退出逐项对应，硬检查和非菜单框架类型丢失=0。
       Layer: L2（L0清单辅助）
       Output: [VERIFY] VC-003: active_old_refs=0 unclassified_refs=0 lost_guards=0 lost_framework_types=0
       Source: AC-003

- AC-004: 在各DP提交其合法业务材料时，dp-sign-key保持mw-decision-context已确认的交付目标/实际完成/已验证与未验证证据/未完成影响及finalize/continue/user-confirm签收语义；dp-w-type四候选及图像硬门、dp-pm-steer四项不降目标、dp-w-check-task三项fire-and-forget均按§1.2。增权、缩减目标/验收、冒充执行/完成或新增Worker同步等待次数为0；各分支正向观测补充见AC-044～047、038/039。[REVISED @ 2026-10-25：毕业考点名业务基线/当前入口并保留原四职责修改确认，完整AC未锁]

VC-004: w-type/pm-steer/w-check/sign-key基线合法场景分别走其全部选择，原签收四部及三数组成立；增权/降目标/假执行完成/新增同步等待均0。
       Layer: L2
       Output: [VERIFY] VC-004: baseline_contract_violations=0
       Source: AC-004

- AC-005: 在PM提交完整质量审核材料时，dp-QG依§1.2已确认含义给出pass/fix/reopen正式结论，并带可复核证据、具体缺口/依据问题及未覆盖面；审核意见不冒充已整改，reopen导致未授权修改目标/验收次数为0。精确材料/消费留设计。[REVISED @ 2026-10-25：用户认可三业务选项及含义；完整AC未锁]

VC-005: QG三结论各附真实依据、具体缺口或依据问题及未覆盖面，正式意见与实际整改分开；自动改承诺/验收=0。
       Layer: L2
       Output: [VERIFY] VC-005: reviewed_choices=3 missing_required_evidence=0 unauthorized_contract_edits=0
       Source: AC-005

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

- AC-040: 在PM提交主体/对象/具体待决问题清楚的临时问题时，dp-route只选择§1.1其余七入口之一，入口选择及依据可见，所选业务结论/业务动作不得由路由答复推断，路由造成的业务放行/执行次数为0。目标材料仍按所选入口合同准备。[ADDED @ 2026-10-25：毕业考推导，技术字段/记录留设计，完整AC未锁]

VC-040: route分别选择七目标并显示依据，入口选择不能推出目标业务结论，路由业务放行/执行=0，目标材料另准备。
       Layer: L2
       Output: [VERIFY] VC-040: routed_targets=7 route_releases=0 route_actions=0
       Source: AC-040

- AC-041: 在固定业务节点有明确对应DP时可直调，额外强制路由次数为0；PM遇复合问题时拆清独立事项及主体，按对应合同判断，同事项重复审批为0。路由不能使PM冒充Worker自身判断或Worker调用PM专属DP，角色越权执行次数为0。[ADDED @ 2026-10-25：毕业考推导，不新增角色资格，完整AC未锁]

VC-041: 固定节点强制route=0；复合事项有独立owner，PM代Worker自身判断及Worker调PM入口成功=0，同事项额外审批=0。
       Layer: L2
       Output: [VERIFY] VC-041: mandatory_routes=0 role_impersonations=0 duplicate_approvals=0
       Source: AC-041

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

- AC-044: 在派发目标/要求/交付材料齐备且角色/写面允许时，dp-w-type候选精确为coding/research/review/vision；需读图且模型有图像能力的vision方案可合法派发，无图像能力时Worker启动数为0。不回退coding冒充图像能力，也不移除未列菜单的既有框架类型。[ADDED @ 2026-10-25：毕业考正反例，具体能力/派发证据留设计，完整AC未锁]

VC-044: w-type精确四候选，需图且已证能力的vision正例启动=1；无图能力负例启动=0，unknown无证亦不启动，coding降级=0，其他框架类型未删除。
       Layer: L2
       Output: [VERIFY] VC-044: offered_types=4 capable_vision_starts=1 incapable_or_unproven_starts=0 coding_downgrades=0
       Source: AC-044

- AC-046: 在Worker任务可达性分别具备充足条件、边界内不可完成及可有界查证未知时，dp-w-check-task对应选择继续/终止真实结论/继续补证；继续分支不立即伪造终态，终止分支输出完成/未完成/阻断及证据并结束本次执行。新增同步等PM指令链数为0，终止推断目标完成或key取消/收窄次数为0。[ADDED @ 2026-10-25：毕业考三分支观测，技术终态映射留设计，完整AC未锁]

VC-046: Worker充足/不可达/有界未知三场景对应三选择；continue即刻伪终态=0，terminate真实结论并结束本次=1，新增同步等待/目标取消收窄=0。
       Layer: L2
       Output: [VERIFY] VC-046: worker_choices=3 fake_immediate_terminals=0 truthful_terminations=1 added_pm_waits=0 goal_cancellations=0
       Source: AC-046

- AC-051: 在允许null的任务进展快照中，未记录null与明确无项[]保持可区分，投影不回填历史或由agent-report产生执行权限；dp-sign-key的verified/unverified/unfinished_impact仍按原数组契约，[]表示真实无，缺项不能改成null造有效材料。秘密明文或历史字节改写次数为0。[ADDED @ 2026-10-25：毕业考区分快照/签收契约，非新增材料schema，完整AC未锁]

VC-051: task进展null和[]序列化及投影可区分，sign三数组缺项/null拒绝而合法[]保留；agent-report增权、秘密泄漏或历史回写=0。
       Layer: L2
       Output: [VERIFY] VC-051: null_empty_conflations=0 invalid_sign_arrays_accepted=0 agent_report_grants=0 secret_or_history_violations=0
       Source: AC-051

- AC-053: 在正式质量审核分别具备要求满足/证据充分无阻断、明确依据下产物缺口、要求/设计/验收依据实质问题时，dp-QG按pass/fix/reopen给可复核依据、具体缺口或依据问题及未覆盖面；正式结论及后续实际处理可区分，自动改契约、派返工或代签收/审批次数为0。[ADDED @ 2026-10-25：毕业考QG正向观测，完整AC未锁]

VC-053: QG充分无阻断/明确产物缺口/实质依据问题三场景准确对应pass/fix/reopen，证据/缺口/未覆盖明确，自动改契约/派返工/代签收或审批=0。
       Layer: L2
       Output: [VERIFY] VC-053: qg_choices=3 wrong_business_conclusions=0 automatic_contract_dispatch_or_sign_actions=0
       Source: AC-053


## 验收命令
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_decide_registry_contract.py test_dp_consolidation_registry.py`
- 修改测试文件必须实际运行并迭代到通过；完整stdout/stderr/argv/cwd/rc及每项red→green留本卡evidence，不能只报count。只跑上述两文件，额外纯fixture探针可在本卡evidence；不执行T04/T05生成器/JSON再生、TS tests/full suite或npm check。npm run check有write formatter，仅原T32 PM-direct另建保护等价workspace，不在共享树跑。

## 改动历史
PM新建R3卡：用户对上轮具体定点返工问答“继续”，本轮收窄为一个原T03测试文件，继承原15AC/VC和依赖，独立证据rework-r3子集。未改原卡/run/红绿，不回填虚构before/进展。实际派发后PM只在编排记录保存run；worker开始时须补本卡证据原before。

## 交付格式
证据report.md和最终回复均独立五标题：## 结论、## 证据、## 残留与未验证、## 上下文来源、## 改动清单。逐两个残留断言的行为red/green、合法各阶段正例与非法反例、真实parser与合成边界、四文件bytes/SHA/EOL及13handoff hash（不得误报3变在13表内）、主树/原证据/禁止面变化限制、实际diff及EOF来源列清。只签局部测试返工成果，不放行T04/S1/L2/QG/签收；超面/预算/未知资格/新根因如实收口而非扩大或自重派。PM终态全文吸收独立复验后ack，done/acked不直接释放依赖。
