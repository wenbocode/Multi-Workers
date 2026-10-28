type: coding
images: no
card_path: tasks/T05-eight-cases.md
card_sha256: 8a7d747000c0f0e2427f57d30d61ebd5d339c0ee93c3b170a3cdc256327b3e85
envelope_producer: agent-team-loop-pm@0.83.0
write_face: .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/scripts/build_decide_cases.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_book_template.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_workbench.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-type.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-pm-steer.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-check-task.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-QG.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-gate-approve.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-sign-key.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-auto.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-route.json, .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/**
decision: dp1-dispatch-type:c5e109b0-a879-44b6-8404-6c4a486b0c56

<!-- mw-dispatch-card: v1 -->
## 上下文

项目目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批模块/接口`.agenticdoc/mw-dp-consolidation/design.md:201`。确认见evidence/design-approval-20261026.md；plan.md及implementation-isolated-dag.json给依赖/单writer。已有RQ1～22为历史证据，不回填或冒充当前源码审计。

## 要求

生成真实可验证合成材料/note/basis及独立provenance；模型问题原文来自registry。修改原workbench断言仅为新八入口衔接，原既有失败fixture/原因保留，不能顺手修独立UI债。生成只写八目标文件，旧dp1/2/3/25不得再生成或修改。漂移验证在临时目录用生产generator，不能运行生产观察submit。

固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

## 交付格式

唯一证据/最终回复均有独立`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。给完整及key-relative证据路径、实际changed-files/命令/rc/原始断言定位、未验证范围；research/review用worker_file只写唯一证据并read回读。coding原始日志限本卡evidence目录，不写活对象或第二决策账本。blocked/failed与真实done分开；不得凭self-report补before、PASS或任务完成。PM吸收终态后ack，semantic未通过不因acked清债。

## 隔离实施覆盖（用户已批准，优先于旧物理路径）

实际源码/生成器/测试cwd根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`；证据仍写本卡主key evidence目录。只改本卡frontmatter/write_face列出的副本exact文件，原仓库同名文件禁止写。源卡为未执行历史，依赖/AC/VC/业务合同原样继承。
原字节/SHA/EOL/既有diff：evidence/implementation/isolation-baseline-20261026/；实施映射/入口条件见implementation-isolation.md与implementation-isolated-dag.json。下一writer必须读副本当前EOF并保存本卡before/after，不能拿原仓源码代最新副本。
所有测试先检查实际导入file/生成器输出/子进程脚本绝对路径在副本内；fixture project/home/TEMP限本卡evidence，采用最小环境（不继承provider/worker/项目配置），PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、禁pytest cache。测试源完整读后只跑已列具体文件，fake backend，不真实HTTP/决策CLI/服务探针。源码树内不写运行config/gate/ledger；仅独立fixture可由生产writer写测试对象，不能fixture伪造业务PASS。
只读mirror/旧case不可修改；不建源symlink/junction/hardlink、不重新复制覆盖已修改副本，不改权限/预算/watchdog或live对象。TS依赖解析与完整check等价性未证，届时先核再测；完整npm check只T32 PM-direct另建等价保护副本，不在共享实施副本运行写式formatter。human/H12实际资格及运行切换未证仍原验收阻塞，本覆盖不造真实grant。

# T05 — 八个完整隔离case从单源产生，四旧case原字节只读保留且不再出现在可提交菜单。

## 状态

代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。

## 写入允许面

- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/scripts/build_decide_cases.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_book_template.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_workbench.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-type.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-pm-steer.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-check-task.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-QG.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-gate-approve.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-sign-key.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-auto.json
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-route.json
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/**

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

- AC-013: 在载入含退役DP的历史记录时，列表和详情可只读查看，明确退役且不可发起新运行；原始历史文件字节变化为0，不按当前注册或状态补造事实。

VC-013: 退役历史列表详情读取后历史原文件逐字节相同，展示retired/readonly且新运行不可用，不新增当前配置/状态补造事实。
       Layer: L2
       Output: [VERIFY] VC-013: historical_byte_changes=0 historical_fact_fabrications=0 retired_reruns=0
       Source: AC-013

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

- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_decision_context_workbench.py`
- 每次改测试文件先红测/绿测，全部stdout/stderr/rc留证；Python隔离home/project/env并禁pycache/pytest自动插件和cache写，TS harness+faux。
- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。
- 全项目`npm run check`由T32串行保护检查，不在worker并行跑写入式formatter。

## 改动历史

- 初始：计划生成，无源码/测试改动，无通过声明。执行时逐次追加实际before/after/hash/红绿命令/rc/原失败/残留和后继writer交接，不伪写过去状态。

## 交付段契约（本角色）

本角色（type: coding）的恢复契约段：report.md / output.md 必须按下列标题成节（可直接复制；缺任一段即 settle 判缺失）：

- `## 结论`
- `## 证据`
- `## 残留与未验证`
- `## 上下文来源`
- `## 改动清单`

以上为种子，不是探索上界；可自行检索补充上下文
<!-- /mw-dispatch-card: v1 -->

按原T05卡实施八个单源完整隔离case。T03/T04/T09已获得局部技术交接，最新PM证据 evidence/implementation/t09-r2-pm-handoff-20261027/report.md 与 s2-t05-t10-pre-dispatch-20261027/check.json/frontier.json。这是原36任务之一，不扩scope/预算。先完整分段读自己当前源码和test至实际EOF（输出截断必须续读），保存自己before bytes/SHA/EOL/既有diff；不得覆盖当前副本或整文件重写旧测试以造green。仅原卡列的11个副本产品文件及自己dpc-t05-eight-cases/**证据可写；8个目标case原先不存在，四旧dp1/2/3/25与全部旧历史必须逐字节不变。生成器实际运行只在自己的隔离输出fixture；部署副本八目标文件也须由真实同源generator数据建立并精确比对，绝不生成旧case/运行活观察submit。真实完整schema3 material/preparation/meta，同次依据、真实合成来源、role/null/[]/七route/自由auto候选等合同保留。先真实行为红，再实现并跑原指定test_decision_context_workbench.py，日志完整保留、不得靠弱化既有UI/注入/秘密/历史断言通过。
并行协调：T10同时只写wire/lifecycle/task_state及其两测试，与你产品写面零重叠，但你的workbench直接import decision_lifecycle（51行），间接wire/task_state。代码编辑和单源case生成可并行；每个测试进程必须用当前真实隔离模块，记录T10三依赖测试前/后SHA、实际import __file__和读入时刻。观察到依赖运行间变化，该次保留为unstable证据，不据此改断言或声称最终qualified；不复制/shadow/stub共享模块、不改T10/PM卡或budget，不无期限轮询/等待。在原预算内交付真实实现和可验证证据，无法稳定全suite则明确残留，PM在两writer终态后新鲜重跑判断共同交接。T10变化不授权修其它UI/protocol/context模块。原卡外context/observation投影债明确列出路径与理由，不空挂T10。
所有Python含静态import/子进程均-B + PYTHONDONTWRITEBYTECODE=1；禁pytest autoload/cache、网络/fake backend、最小UTF8环境/private HOME/TEMP/project及绝对隔离cwd。14既有pyc精确保护、禁清理。不得活HTTP/provider/CLI/配置/ledger/gate/grant/brake/安装build/npm check/依赖lock/dist/commit/push/新budget/goal/spec/phase。完整check属于T32。报告使用五节 结论/证据/改动清单/残留与未验证/上下文来源；完整changed-files before/after/hash/diff表头只用“文件”不嵌副本目录路径（避免已证ledger表头误判）。每个路径实际可核，真实done与局部验证/整体L2/QG签收分开；终态PM自动吸收ack和独立资格判断后推进。
