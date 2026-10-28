---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_signoff_result.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_archive.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_signoff.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_archive.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_signoff.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_signoff.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t22-signoff-validator/**
ac_refs: [AC-004, AC-005, AC-006, AC-010, AC-013, AC-038, AC-039, AC-050, AC-051, AC-053]
vc_refs: [VC-004, VC-005, VC-006, VC-010, VC-013, VC-038, VC-039, VC-050, VC-051, VC-053]
deps: [T06, T10, T11, T12, T13, T14, T15, T16, T17, T18]
execution: worker
---

## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T22 — 当前valid且finalize与对应证据成立，key签收和authority-change typed消费严格隔离。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
保留原适用范围和三数组；continue/user-confirm无签收，旧词表/缺logical_id不走成功legacy。finalize不加入promote/demote词表；不删除helper/回写旧签收，不把QG文件或文件存在代完成。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_signoff_result.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_archive.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_signoff.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_archive.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_signoff.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_signoff.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t22-signoff-validator/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
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

- AC-006: 在质量证据缺失或机器硬门失败时，dp-QG不得产生可用于放行的有效通过结果，业务放行次数为0，缺失或失败项明确可见。

VC-006: 缺必要质量证据及每项硬门失败时，QG有效pass=0、业务放行=0，失败项逐项可见。
       Layer: L2
       Output: [VERIFY] VC-006: usable_pass=0 releases=0 hidden_failures=0
       Source: AC-006

- AC-010: 在PM提交阶段目标/必需交付、必需key有效签收、跨key集成/阶段验收证据及未完成/未验证影响时，由dp-gate-approve审批；缺必需交付/验证或只有done计数/key签收时，可用关闭次数为0。明确披露且不影响阶段验收的非阻断遗留不单独阻止关闭；需用户接受的风险/取舍未获具体确认时不得据此放行。approve不批准下一stage；steer/need_fix/reject不冒充达标关闭，获授权遗留收尾须与成功交付区分；不增加原dp20第二次审批，具体状态转换/消费待设计。[REVISED @ 2026-10-25：阶段关闭归属及H02关闭条件/遗留规则已认可；完整AC未锁]

VC-010: stage正例达标且非阻断遗留披露可关闭=1；缺必需交付/验证、仅done或签收、未接受风险负例关闭=0；下一stage自动批准=0，遗留关闭不计达标。
       Layer: L2
       Output: [VERIFY] VC-010: valid_closures=1 invalid_closures=0 next_stage_approvals=0 false_acceptance_closures=0
       Source: AC-010

- AC-013: 在载入含退役DP的历史记录时，列表和详情可只读查看，明确退役且不可发起新运行；原始历史文件字节变化为0，不按当前注册或状态补造事实。

VC-013: 退役历史列表详情读取后历史原文件逐字节相同，展示retired/readonly且新运行不可用，不新增当前配置/状态补造事实。
       Layer: L2
       Output: [VERIFY] VC-013: historical_byte_changes=0 historical_fact_fabrications=0 retired_reruns=0
       Source: AC-013

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

- AC-050: 在权限/claim/写面/硬门满足且PM或Worker真实执行所选动作时，动作证据与执行/本轮结算记录可关联，同key/task/logical_id及非递减观察时间可核；任务前后快照保留合法状态/来源，不以当前状态回填旧before，不以仅consumed/选择代执行。未执行或失败回合不得伪造成功executed，settled不代表任务done。[ADDED @ 2026-10-25：毕业考沿用既有来源/关联契约，具体消费者留设计，完整AC未锁]

VC-050: 真实执行与本轮结算关联同key/task/logical_id及非递减观察时间，before不由当前回填；未执行/失败伪成功executed=0、settled代done=0。
       Layer: L2
       Output: [VERIFY] VC-050: broken_action_links=0 backfilled_before=0 fabricated_executed=0 settlement_done_inferences=0
       Source: AC-050

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
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_decide_archive.py test_decide_signoff.py test_dp_consolidation_signoff.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
