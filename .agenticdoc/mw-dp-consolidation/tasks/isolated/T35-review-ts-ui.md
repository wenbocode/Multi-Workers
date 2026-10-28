---
type: review
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t35-review-ts-ui.md
ac_refs: [AC-004, AC-007, AC-012, AC-013, AC-014, AC-027, AC-041, AC-044, AC-045, AC-046, AC-047, AC-049, AC-050, AC-051]
vc_refs: [VC-004, VC-007, VC-012, VC-013, VC-014, VC-027, VC-041, VC-044, VC-045, VC-046, VC-047, VC-049, VC-050, VC-051]
deps: [T27, T28, T29, T30, T32]
execution: worker
---

## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T35 — 独立只读审计PM/Worker/vision/窗口观察历史的资格、真实终态与来源安全。

## 状态
代码状态：不适用；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
审计目标：T11～T16/T27～T30及原始TS/DOM日志；原26AC/monitor8AC债不结清。源码审计采用EOF或明确缺口，任何need-image任务资格不能unknown猜补；不读取其他key图片、不运行命令/浏览器/provider，只写唯一证据。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t35-review-ts-ui.md

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
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

- AC-013: 在载入含退役DP的历史记录时，列表和详情可只读查看，明确退役且不可发起新运行；原始历史文件字节变化为0，不按当前注册或状态补造事实。

VC-013: 退役历史列表详情读取后历史原文件逐字节相同，展示retired/readonly且新运行不可用，不新增当前配置/状态补造事实。
       Layer: L2
       Output: [VERIFY] VC-013: historical_byte_changes=0 historical_fact_fabrications=0 retired_reruns=0
       Source: AC-013

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

- AC-041: 在固定业务节点有明确对应DP时可直调，额外强制路由次数为0；PM遇复合问题时拆清独立事项及主体，按对应合同判断，同事项重复审批为0。路由不能使PM冒充Worker自身判断或Worker调用PM专属DP，角色越权执行次数为0。[ADDED @ 2026-10-25：毕业考推导，不新增角色资格，完整AC未锁]

VC-041: 固定节点强制route=0；复合事项有独立owner，PM代Worker自身判断及Worker调PM入口成功=0，同事项额外审批=0。
       Layer: L2
       Output: [VERIFY] VC-041: mandatory_routes=0 role_impersonations=0 duplicate_approvals=0
       Source: AC-041

- AC-044: 在派发目标/要求/交付材料齐备且角色/写面允许时，dp-w-type候选精确为coding/research/review/vision；需读图且模型有图像能力的vision方案可合法派发，无图像能力时Worker启动数为0。不回退coding冒充图像能力，也不移除未列菜单的既有框架类型。[ADDED @ 2026-10-25：毕业考正反例，具体能力/派发证据留设计，完整AC未锁]

VC-044: w-type精确四候选，需图且已证能力的vision正例启动=1；无图能力负例启动=0，unknown无证亦不启动，coding降级=0，其他框架类型未删除。
       Layer: L2
       Output: [VERIFY] VC-044: offered_types=4 capable_vision_starts=1 incapable_or_unproven_starts=0 coding_downgrades=0
       Source: AC-044

- AC-045: 在PM准备真实目标/执行状态/约束并判断任务编排时，dp-pm-steer按四项分别给出不降目标的narrow、独立并行单元split、依赖当前PM上下文的direct-exec或具体人工必要性/问题的escalate；选择/实际编排证据可区分，未协调在途Worker/写面而冲突执行次数为0。[ADDED @ 2026-10-25：毕业考正向选项观测，完整AC未锁]

VC-045: pm-steer四项逐支有不降目标主线/独立并行/当前上下文依赖/具体人工问题证据，真实编排可区分，未协调在途冲突执行=0。
       Layer: L2
       Output: [VERIFY] VC-045: steering_choices=4 goal_reductions=0 uncoordinated_conflicting_actions=0 vague_human_questions=0
       Source: AC-045

- AC-046: 在Worker任务可达性分别具备充足条件、边界内不可完成及可有界查证未知时，dp-w-check-task对应选择继续/终止真实结论/继续补证；继续分支不立即伪造终态，终止分支输出完成/未完成/阻断及证据并结束本次执行。新增同步等PM指令链数为0，终止推断目标完成或key取消/收窄次数为0。[ADDED @ 2026-10-25：毕业考三分支观测，技术终态映射留设计，完整AC未锁]

VC-046: Worker充足/不可达/有界未知三场景对应三选择；continue即刻伪终态=0，terminate真实结论并结束本次=1，新增同步等待/目标取消收窄=0。
       Layer: L2
       Output: [VERIFY] VC-046: worker_choices=3 fake_immediate_terminals=0 truthful_terminations=1 added_pm_waits=0 goal_cancellations=0
       Source: AC-046

- AC-047: 在Worker选择继续补证时，待查具体未知、可实施证据来源、权限/预算及结束判据可核；结束后按真实条件继续或终止结论，不无限续跑，不用模型补造未知意图。无结束判据/不可在边界内查证却放行补证次数为0，不由本AC设固定次数/时长。[ADDED @ 2026-10-25：毕业考有界补证，完整AC未锁]

VC-047: 补证真实未知/来源/权限预算/结束判据成立后实施并真实继续或终止；无结束判据或边界不可查证放行=0、无限补证/凭空意图=0。
       Layer: L2
       Output: [VERIFY] VC-047: unsupported_investigations=0 unbounded_investigations=0 invented_intents=0
       Source: AC-047

- AC-049: 在gate选steer/need_fix且PM已准备对应后继材料、角色/授权有效、尚无同事项在途后继请求时，PM发起对应dp-pm-steer/dp-auto请求且有可核调用证据；后继未发起、调用失败、返回选择及实际整改分别可见，不由gate选择推断完成。重复请求或本gate因此放行次数为0。[ADDED @ 2026-10-25：毕业考后继正反观测，不新增固定双批或执行权，完整AC未锁]

VC-049: 已备合法后继且无在途时，steer和need_fix各有一次真实PM目标请求；未备/在途/调用失败/有回答/已执行分别可见，重复后继和原gate放行=0。
       Layer: L2
       Output: [VERIFY] VC-049: steer_successor_requests=1 fix_successor_requests=1 duplicate_successors=0 parent_releases=0
       Source: AC-049

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


## 审计目标
审计目标：T11～T16/T27～T30及原始TS/DOM日志；原26AC/monitor8AC债不结清。源码审计采用EOF或明确缺口，任何need-image任务资格不能unknown猜补；不读取其他key图片、不运行命令/浏览器/provider，只写唯一证据。

## 未覆盖面声明
明确逐文件/入口/日志未读未验证范围及影响；未知写未知，不把done/acked/机械PASS当产品验收。只读审计不执行bash/CLI/provider，唯一证据文件：.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t35-review-ts-ui.md

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
