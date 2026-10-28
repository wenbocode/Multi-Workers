# Candidate Write Scope: mw-dp-consolidation

> 状态：待用户联合审核；不是当前写权限。Phase=DESIGN。设计批准后仍须PLAN/任务门禁与逐文件独占writer。本清单不授权安装/部署/活业务迁移/签收或预算恢复。

## 1. 本轮文档面

只写本key的design.md、evidence-requirement.md、本清单、pm-state.md及本轮独立研究/检查证据；锁定spec及原历史/worker产物不写。key-decision A定案只在用户确认设计后追加。本轮无源码修改。

## 2. 候选产品修改面（逐文件，不是目录授权）

下列每行均为repo-relative exact path。M编号对应design §3；共有文件交接必须有before/after hash、差异与接口版本，下一writer先吸收。旧独立key已有改动须保留并协调，不能覆盖其formatter/测试债。

| 文件 | 模块/允许的限定变化 |
|---|---|
| packages/multi-workers/decision_points.py | M01，八活动注册/25拒绝/材料/依据/角色/候选及白名单 |
| packages/multi-workers/decision_context.py | M01，新入口context资格及核心材料不可裁剪边界，历史不改 |
| packages/multi-workers/decision.py | M02/M03，活动身份在调用与replay前校验、生成合同消费、保留预算/失败/凭证语义 |
| packages/multi-workers/decision_backends.py | M03，D012同次依据问题渲染/答案校验，不猜自由文本、不改provider/model/重试合同 |
| packages/multi-workers/decision_book.py | M01/M03，八入口book准备/严格校验及独立依据、禁止legacy绕行 |
| packages/multi-workers/decision_wire.py | M03，真实新入口引用/材料与依据来源、既有安全过滤 |
| packages/multi-workers/decision_lifecycle.py | M03，真实request/action/settled/意图引用，不能第二ledger/回填历史 |
| packages/multi-workers/decision_task_state.py | M03/M07，前后来源及null/[]保真，原独立26AC保留 |
| packages/multi-workers/decision_signoff_result.py | M08，finalize/当前事项证据有效性与只读validator边界 |
| packages/multi-workers/decide_archive.py | M08/M09，新入口/当前签收引用，历史只读分类 |
| packages/multi-workers/decide_signoff.py | M08，authority-change独立typed消费，拒绝key-signoff/退役ID；不合并词表 |
| packages/multi-workers/decision_history.py | M09，新八入口来源投影/退役只读，不改原记录 |
| packages/multi-workers/decision_monitor.py | M09，活动八集合和readonly目录投影、状态来源；不顺带monitor重启 |
| packages/multi-workers/decision_playground.py | M09，隔离新八合同验证/submit/cases，观察无executor |
| packages/multi-workers/decision_dashboard.js | M09，八合同表单、独立note/模型依据/后继/执行/结算与安全DOM |
| packages/multi-workers/decision_dashboard.html | M09，必要语义组件/标签，不修独立dropdown缺陷 |
| packages/multi-workers/decision_dashboard.css | M09，新增语义显示的必要样式，不额外页面重设计 |
| packages/multi-workers/mw.py | M01～M09，CLI active-before-replay、生产/观察/签收/权限产物隔离、human功能边界及正确help；不删有意helper |
| packages/multi-workers/mw_common.py | M07，Worker真实终止原因消费，类型/进程/凭证硬检查不删 |
| packages/multi-workers/autopilot/gates.py | M04，三轴合同writer/parser、事项关联及既有锁 |
| packages/multi-workers/autopilot/conductor.py | M04/M05，四分支与H01～H13条件化消费者接线；不自解除刹车 |
| packages/multi-workers/autopilot/xkey.py | M04，受限跨key版本/claim/权限协调与真实恢复 |
| packages/multi-workers/autopilot/dispatch.py | M04，八入口派发处置/真实在途与受控恢复引用 |
| packages/multi-workers/autopilot/advance.py | M04/M10，真实phase失败→auto处置，不改原推进判据 |
| packages/multi-workers/autopilot/closure.py | M04/M08，有效签收/整体stage验收与非阻断遗留区分 |
| packages/multi-workers/autopilot/contract_guard.py | M02/M04，具体冻结条目差异/授权/影响重验，不授任意改契约权 |
| packages/multi-workers/scripts/gen_decide_registry_ts.py | M01，现有单源生成字段/角色/候选/依据并锁定TS，不另造生成器 |
| packages/multi-workers/scripts/build_decide_cases.py | M01/M09，八活动case生成，四旧case明确readonly regression不进入菜单 |
| packages/multi-workers/decide_registry.json | M01，仅由单源再生成，活动points八，退役解释独立 |
| packages/multi-workers/decide_book_template.json | M01，八入口合法准备模板，原签收四部及辅助依据分开 |
| packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts | M01，仅上述生成器产出，不手写第二合同 |
| packages/coding-agent/src/extensions/agent-team-loop/shared/decide-policy.ts | M01/M02，活动合同/真实角色与原策略衔接，不自授权限 |
| packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts | M04，受限审批新名与claim/写面guard不放宽 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts | M03/M06，八工具schema与合法material/preparation、真实本地meta/同次签收 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts | M06，PM预备note/依据/后继、真实窗口上下文及在途协调 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts | M06/M07，四类型vision能力硬门与派发前协调，不删其他框架类型 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts | M03/M06，退役hook不代造材料/签收，不隐藏失败 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts | M06/M09，真实入口/角色/能力与独立投影；不顺带旧formatter决定 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/decision-task-state.ts | M03/M07，前后快照/关联及null/[]，保留旧key独立契约 |
| packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts | M07，自主三选择/真实结论/有界补证，不同步等PM |
| packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts | M04，新三轴/事项关联与既有写锁 |
| packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts | M07/M09，真实原因/三轴显示，不擅加终态闭集 |
| packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts | M04/M09，条件/拒绝/恢复状态界面，不能改变活policy/授权 |

## 3. 候选新增产品文件

| exact path | 限定职责 |
|---|---|
| packages/multi-workers/decision_validity.py | 纯事项/实质版本/授权引用/证据适用性，只读不自授权 |
| packages/multi-workers/decision_policy.py | 只读授权旁载校验与原config硬条件衔接，无grant writer |
| packages/multi-workers/autopilot/gate_effects.py | 条件化四选项/受限效果/CAS与对账，不新ledger |
| packages/multi-workers/autopilot/decision_recovery.py | H12隔离来源与预授权/检查/限定观察恢复handler，普通链不可自调用 |
| packages/coding-agent/src/extensions/agent-team-loop/pm/decision-followup.ts | PM已准备意图的恢复/去重/真实请求关联，复用原文件协调 |
| packages/multi-workers/decide_cases/dp-w-type.json | 活动隔离case |
| packages/multi-workers/decide_cases/dp-pm-steer.json | 活动隔离case |
| packages/multi-workers/decide_cases/dp-w-check-task.json | 活动隔离case |
| packages/multi-workers/decide_cases/dp-QG.json | 活动隔离case，保留大小写 |
| packages/multi-workers/decide_cases/dp-gate-approve.json | 活动隔离case |
| packages/multi-workers/decide_cases/dp-sign-key.json | 活动隔离case，四部material/三数组不改 |
| packages/multi-workers/decide_cases/dp-auto.json | 动态现场候选而非固定菜单 |
| packages/multi-workers/decide_cases/dp-route.json | 七目标，无业务executor |

## 4. 候选测试修改/新增面

### 既有文件（修改）

- packages/multi-workers/test_decide_registry_contract.py
- packages/multi-workers/test_decide_registry_ts_lock.py
- packages/multi-workers/test_decision_context_contract.py
- packages/multi-workers/test_decision_context_lifecycle.py
- packages/multi-workers/test_decision_context_workbench.py
- packages/multi-workers/test_decision_monitor.py
- packages/multi-workers/test_decision_dashboard_playground.py
- packages/multi-workers/test_decision_history_feedback.py
- packages/multi-workers/test_decision_task_state.py
- packages/multi-workers/test_decide_archive.py
- packages/multi-workers/test_decide_signoff.py
- packages/coding-agent/test/suite/decision-context-agent-materials.test.ts
- packages/coding-agent/test/suite/decision-context-pm-producers.test.ts
- packages/coding-agent/test/suite/decision-task-state.test.ts

修改旧独立测试只做本次八入口衔接，保留26AC/旧失败fixture及历史语义。现有workbench失败与formatter决定不能“顺手修掉”；若新入口必须触及该断言，明确记录原失败、原因与本key限定修订，先协调再改。

### 新增文件

- packages/multi-workers/test_dp_consolidation_registry.py
- packages/multi-workers/test_dp_consolidation_materials.py
- packages/multi-workers/test_dp_consolidation_gate_effects.py
- packages/multi-workers/test_dp_consolidation_recovery.py
- packages/multi-workers/test_dp_consolidation_cli.py
- packages/multi-workers/test_dp_consolidation_signoff.py
- packages/multi-workers/test_dp_consolidation_history.py
- packages/multi-workers/test_dp_consolidation_concurrency.py
- packages/coding-agent/test/suite/dp-consolidation-materials.test.ts
- packages/coding-agent/test/suite/dp-consolidation-pm-followup.test.ts
- packages/coding-agent/test/suite/dp-consolidation-worker.test.ts
- packages/coding-agent/test/suite/dp-consolidation-vision.test.ts
- packages/coding-agent/test/suite/dp-consolidation-projection.test.ts

TS使用suite/harness.ts+faux provider，Python调用真实生产入口并隔离home/project/env，无真实provider/凭证。每个修改测试文件必须运行具体测试；不跑full vitest/npm test/build。新增test路径若已有他窗文件必须先协调，不覆盖。

## 5. 框架特批面（须明确批准，不随产品面默认授予）

- `.agents/skills/agentic-task/scripts/advance_phase.py`：仅`_decision_signoff_problems`与只读validator衔接/适用范围/当前valid∧finalize识别；保留原其他门禁、claim与日志语义。
- `.agents/skills/agentic-task/scripts/test_advance_phase.py`：仅本签收硬门正反例，隔离tempdir，不动活key。

本框架是独立git clone；此处设计审批不授权commit/push/install或任何canonical/mirror同步。其他clone、`.claude`/用户全局技能镜像、全局bundle或正在运行代码不在写面。最终源码变化还要记录framework diff与未部署证据，不能把repo文件存在当运行身份。

## 6. 明确禁止面/功能保留

- 锁定spec.md、goal.md、所有原历史、worker run/output/evidence、他key文档及未认领源码改动。
- 活`.agenticdoc/_autopilot/config.json`、拟议decision-policy.json、roadmap/stage/gate/brake文件、真实权限配置/预算/签收与任何活ledger。所有业务写测试仅在隔离fixture，由生产writer产生。
- packages/multi-workers/autopilot/config.py与effective_config.py的冻结21键/默认值，本次只读，不用新schema默许覆盖授权。
- pi核心、provider切换、依赖/lock/shrinkwrap、package版本、dist/global bundle、安装脚本、monitor重启模块。
- 四旧case `decide_cases/dp1.json`、`dp2.json`、`dp3.json`、`dp25.json`保留只读回归/历史输入，不生成活动可提交选项，不删除或改原字节。
- 不删除human ask、legacy显示或死签收helper；human-only隔离边界须具体审核。退出旧DP活动职责按锁定SPEC与批准方案处理，不将其余有意功能删除混入改名。
- 未列生产caller、测试或配置出现真实迁移需要时先补影响与exact path并请求批准，不能以grep结果自动扩写面。

## 7. 并行与串行实施边界（仅设计）

可并行：M02纯有效性及独立测试、M06后继独立文件、M09纯UI样式与独立测试；接口稳定后Python/TS各自生产链测试可并行。共享文件M01 registry/decision-tool、mw.py、conductor、history、generated TS每时刻一个writer；相邻模块按版本交接。

必须串行：先单源合同冻结/生成→各producer/consumer适配；最终统一caller/生成锁/保护check；PM整合设计与正式QG。H12生产来源/写面资格证明不成立时保持blocked，不能为了并行交付删检查。框架特批面与产品签收validator须协调接口后才独立执行。

## 8. 批准语义

需要用户批准design.md+evidence-requirement.md+本清单的完整候选，并明确D012理由形式、human功能保留边界、框架特批面。批准后才可通过框架进入PLAN；预算数值、恢复预授权、活对象迁移/恢复、部署、删除保留功能和提交均不由此产生。
