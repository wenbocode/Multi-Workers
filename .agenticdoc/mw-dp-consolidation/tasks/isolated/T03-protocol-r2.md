---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_registry.json
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_registry.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r2/**
ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-007, AC-012, AC-040, AC-041, AC-042, AC-043, AC-044, AC-046, AC-051, AC-053]
vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-007, VC-012, VC-040, VC-041, VC-042, VC-043, VC-044, VC-046, VC-051, VC-053]
deps: [T01, T02]
execution: worker
---

## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T03-R2 — 八活动ID/独立退役目录、材料/角色/选择/依据投影单源成立，25旧ID在replay之前明确拒绝。

## 状态
本次尝试代码状态：未开始；验证状态：需复验；task状态：not-queued。原T03真实done/exit0/acked及142 passed保留，不代表语义交接通过。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
只改注册/描述/纯validator及对应生成快照，不建执行权限。固化八入口和技术选择ID，auto不套旧2..5/cN，route静态七目标。D012辅助依据与sign四部材料独立，[]不转null。先红测各旧ID/非法角色/八合法合同及四选择基线，再实现；生成快照走已核离线单源writer，仅授权本卡输出，保留只读历史解释。若字段/新接口需改变已确认职责或传输预算，报告而非偷改契约。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_registry.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_registry.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r2/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

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
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。


## 本次定点返工范围（优先于原初次实现描述）
人工批准见`.agenticdoc/mw-dp-consolidation/evidence/implementation/t03-rework-approval-20261026.md`；原卡tasks/isolated/T03-protocol.md不改；本轮仅修三项已实测缺口，同一逻辑T03非新增DAG任务。PM探针/校验见evidence/implementation/t03-pm-handoff-20261026/{report.md,probe.py,probe.json,check.json}；原报告evidence/implementation/dpc-t03-protocol/report.md只读。
1. 副本decision_points.py:4265的prepared_request_issues缺actor_role时通过：实际请求资格缺失/非法角色必须拒绝，八入口合法角色保持通过。角色参数校验不冒充生产身份认证；不新增self-report/token/TTY授权。纯preparation校验不提前要求模型产出的choice/basis答案。
2. 副本decision_points.py:4226的preparation_issues接受prepared_at='not-an-ISO-timestamp'：按既有ISO时间合同加非法/缺失/type及合法时间正反例。不凭空扩大合同格式或增加预算/年龄阈值。
3. 副本test_decide_registry_contract.py:443的test_generated_ts_regeneration_belongs_to_t04永久要求旧dp1且拒八新入口，违反后继T04目标。修成可演进的真实契约断言；一并审视同文件约330的all-unwired与432的legacy-TS-row阶段锁，避免后继已获权接线后必须越面改本测试。保留实质字段/字节锁/位置/错误拒绝覆盖，不无条件skip/xfail、删验收、只放宽为任意输入或伪造T04产物。当前旧TS债和合成八入口fixture各明示，合成验证不是T04实际生成/parity/TS通过。
只做本轮三项相关最小差异；原八职责/退役25/53AC-VC/锁/隔离/预算不变。当前四文件hash与PM交接一致；开工仍重新读取四文件EOF、保存本轮before bytes/SHA/EOL及原dirty差异，再写测试行为反例取真实red日志，最小实现后跑原两文件green。不得拿初次T03 collection-error充本轮red，不刷新主树覆盖副本。
证据仅`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r2/**`，包括脚本、private fixture/home/temp/project、before/after、diff、红绿、路径/禁写核对及report.md；不得改父目录原证据/原worker记录。测试执行最小env、禁插件/cache/pycache、fake backend/零HTTP；导入路径实际绑定副本。只跑上文两文件命令，不调用决策CLI/provider/生成器/服务/全npm check。JSON仅如快照改变时由既有纯函数离线单源生成。
返工交付与最终回复均须五个独立标题：## 结论、## 证据、## 残留与未验证、## 上下文来源、## 改动清单；列出三项逐例红绿证据、合法正例、原四文件及13交接路径新hash、实际修改/未修改、stage-lock处理依据和未覆盖下游。不签全L2或放行T04。scope/资格不明或超预算时如实收口报告，不绕失败/重置watchdog/自行重派。

## 改动历史（R2卡）
- PM新建本轮卡：保留原卡及原worker全部事实，仅收窄新证据子目录并添加已获人工批准的三项返工；本卡尚未派发，不写虚构运行/通过。
