---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t02-ts-framework-preflight.md
ac_refs: [AC-003, AC-014, AC-027, AC-036, AC-037, AC-038, AC-039, AC-044, AC-052]
vc_refs: [VC-003, VC-014, VC-027, VC-036, VC-037, VC-038, VC-039, VC-044, VC-052]
deps: []
execution: worker
---

# T02 — 实施前核对TS/框架原diff、真实PM/Worker与human/H12入口身份边界、单writer及未列迁移面。

## 状态
代码状态：不适用；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
25分钟静态取证；复用RQ15/16/20和既有源码证据，不读其他key活状态/图片/凭证。盘点TS旧ID调用/提示/工具枚举和框架签收validator。真实身份只能来自可证进程/受控生产入口，page token、自报role、TTY或布尔origin不单独证明human/H12资格；明确当前机制可证部分与缺口，缺口阻塞相应编码而非删功能或自建授权。框架只有scripts/advance_phase.py及test_advance_phase.py可改，其既有diff必须保存/协调；mirrors/安装/重启只读不碰。主要采用源码读EOF或明确范围，不把报告EOF当独立全仓审计。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t02-ts-framework-preflight.md

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-003: 在盘点生产源码/配置/提示词/case及UI提交面后，旧编号活跃注册/调用/可提交选项数为0；六迁移与19退出职责逐项对应目标/拒绝处理，必要历史解释、安全拒绝与回归测试标注用途，不因删DP删除硬检查或其他框架任务类型。[REVISED @ 2026-10-25：按最新组成替代旧范围，不作为源码删除授权，完整AC未锁]

VC-003: 受限生产caller/config/prompt/case/UI清单逐项分类后，旧ID活跃注册/调用/可提交数=0；六迁移与19退出逐项对应，硬检查和非菜单框架类型丢失=0。
       Layer: L2（L0清单辅助）
       Output: [VERIFY] VC-003: active_old_refs=0 unclassified_refs=0 lost_guards=0 lost_framework_types=0
       Source: AC-003

- AC-014: 在审核及反馈跨Python/TS/观察界面传递时，真实producer→writer→consumer→projection链可由隔离生产路径测试核验，建议、实际处理和完成状态不互相冒充；秘密明文和注入脚本执行次数为0。

VC-014: Python/TS真实producer→writer→consumer→projection链可关联，选择/执行/完成不混同；请求、记录、DOM秘密明文及注入执行=0。
       Layer: L2
       Output: [VERIFY] VC-014: broken_links=0 false_execution_or_completion=0 secret_leaks=0 script_executions=0
       Source: AC-014

- AC-027: 在跨key受限修复派发/执行时，明确执行者及受限写面且仍通过claim/角色/独占写面检查；因DP批准而抢占他窗claim、双Worker同文件并写、越权限修改或拒绝后自动关闭次数均为0，选择不冒充已派发/修改。[ADDED @ 2026-10-25：H07验收推导，具体授权绑定/协调/消费待设计，完整AC未锁]

VC-027: 实际跨key执行者/claim/角色/独占面检查成立；抢他窗claim、双Worker同文件并写、越权及reject自动关闭=0，选择不得冒充派发/修改。
       Layer: L2
       Output: [VERIFY] VC-027: claim_thefts=0 concurrent_file_writers=0 unauthorized_actions=0 fake_dispatches=0
       Source: AC-027

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

- AC-044: 在派发目标/要求/交付材料齐备且角色/写面允许时，dp-w-type候选精确为coding/research/review/vision；需读图且模型有图像能力的vision方案可合法派发，无图像能力时Worker启动数为0。不回退coding冒充图像能力，也不移除未列菜单的既有框架类型。[ADDED @ 2026-10-25：毕业考正反例，具体能力/派发证据留设计，完整AC未锁]

VC-044: w-type精确四候选，需图且已证能力的vision正例启动=1；无图能力负例启动=0，unknown无证亦不启动，coding降级=0，其他框架类型未删除。
       Layer: L2
       Output: [VERIFY] VC-044: offered_types=4 capable_vision_starts=1 incapable_or_unproven_starts=0 coding_downgrades=0
       Source: AC-044

- AC-052: 在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC-052: 同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。
       Layer: L2
       Output: [VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0
       Source: AC-052


## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t02-ts-framework-preflight.md
只写此证据，baseline/hash/diff/未覆盖表置同文件，不建第二报告。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
