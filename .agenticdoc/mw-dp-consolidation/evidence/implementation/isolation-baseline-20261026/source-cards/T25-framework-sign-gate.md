---
type: coding
write_face:
  - .agents/skills/agentic-task/scripts/advance_phase.py
  - .agents/skills/agentic-task/scripts/test_advance_phase.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t25-framework-sign-gate/**
ac_refs: [AC-008, AC-010, AC-038, AC-039, AC-052]
vc_refs: [VC-008, VC-010, VC-038, VC-039, VC-052]
deps: [T11, T12, T13, T14, T15, T16, T17, T18, T24]
execution: worker
---

# T25 — 只在原必需范围用只读validator识别当前valid且finalize及对应证据，不豁免其他phase硬门。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
保存/吸收独立clone既有diff，先确认与原作者写面无冲突；仅两个特批文件，不碰任何mirror/install/commit/push。测试临时key，不拿本活key执行done/sign或改门来让当前任务通过。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agents/skills/agentic-task/scripts/advance_phase.py
- .agents/skills/agentic-task/scripts/test_advance_phase.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t25-framework-sign-gate/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
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

- AC-052: 在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC-052: 同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。
       Layer: L2
       Output: [VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0
       Source: AC-052


## 验收命令
- cwd=.；`python -m pytest -p no:cacheprovider -q .agents/skills/agentic-task/scripts/test_advance_phase.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
