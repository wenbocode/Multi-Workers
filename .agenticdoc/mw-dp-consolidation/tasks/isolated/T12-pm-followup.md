---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/coding-agent/src/extensions/agent-team-loop/pm/decision-followup.ts
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/coding-agent/test/suite/dp-consolidation-pm-followup.test.ts
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t12-pm-followup/**
ac_refs: [AC-011, AC-012, AC-027, AC-041, AC-045, AC-049, AC-050, AC-052]
vc_refs: [VC-011, VC-012, VC-027, VC-041, VC-045, VC-049, VC-050, VC-052]
deps: [T05, T06, T07, T08, T09, T10]
execution: worker
---

## 隔离实施覆盖（用户已批准，优先于旧物理路径）
实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T12 — 已准备PM意图恢复/去重和真实后继请求可核，不新建决策账本或同步等待Worker。

## 状态
代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求
父决定、材料/依据版本、真实PM身份、pending/running/未知结果逐项核；未发起/失败/有回答/实际执行分开。窗口失联不可凭文件代造Worker判断；崩溃未知停止对账，不承诺无事务exactly-once。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/coding-agent/src/extensions/agent-team-loop/pm/decision-followup.ts
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/coding-agent/test/suite/dp-consolidation-pm-followup.test.ts
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t12-pm-followup/**

## 写入禁止面
除允许面外所有写入；common所列禁止面绝不因相对路径或fixture名称获权。既有同文件diff必须保留/协调，不全文件格式化或覆盖其他session。框架仅两特批文件，其他mirror当前已有diff不归本任务。

## AC摘录及VC合同
- AC-011: 在八入口处理同一具体事项时，职责表按主体/对象/动作及实质证据指定唯一业务审批归属；路由不代业务审批，同对象/实质证据版本重放不产生额外同事项审批或重复动作。实质影响变化的重审另留痕，不把所有不同gate文件或新材料一律当不同事项。[REVISED @ 2026-10-25：毕业考去除“四门”旧范围，完整AC未锁]

VC-011: 同主体对象动作实质版本在不同标签/文件重放及并发，只一个业务审批owner，额外同事项审批=0、重复动作=0；路由放行=0。
       Layer: L2
       Output: [VERIFY] VC-011: duplicate_approvals=0 duplicate_actions=0 route_releases=0
       Source: AC-011

- AC-012: 在八入口任一请求决策不可用、材料非法或返回无有效裁决时，对应受门控动作保持阻塞并显示具体原因，默认放行次数为0，不用当前状态补造结果、偷换入口或把失败冒充业务选项；不编造decision_id/执行回执。[REVISED @ 2026-10-25：毕业考明确全入口失败防御，合法失败审计不被禁止，完整AC未锁]

VC-012: 八入口材料非法/不可用/无有效选择，各受门控动作=0且原因可见；伪造decision_id/执行回执、默认选择及换入口绕失败=0。
       Layer: L2
       Output: [VERIFY] VC-012: default_actions=0 fabricated_results=0 failure_bypasses=0
       Source: AC-012

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

- AC-045: 在PM准备真实目标/执行状态/约束并判断任务编排时，dp-pm-steer按四项分别给出不降目标的narrow、独立并行单元split、依赖当前PM上下文的direct-exec或具体人工必要性/问题的escalate；选择/实际编排证据可区分，未协调在途Worker/写面而冲突执行次数为0。[ADDED @ 2026-10-25：毕业考正向选项观测，完整AC未锁]

VC-045: pm-steer四项逐支有不降目标主线/独立并行/当前上下文依赖/具体人工问题证据，真实编排可区分，未协调在途冲突执行=0。
       Layer: L2
       Output: [VERIFY] VC-045: steering_choices=4 goal_reductions=0 uncoordinated_conflicting_actions=0 vague_human_questions=0
       Source: AC-045

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

- AC-052: 在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC-052: 同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。
       Layer: L2
       Output: [VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0
       Source: AC-052


## 验收命令
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/coding-agent；`node ../../node_modules/vitest/dist/cli.js --run test/suite/dp-consolidation-pm-followup.test.ts`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史
- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付格式
唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。
