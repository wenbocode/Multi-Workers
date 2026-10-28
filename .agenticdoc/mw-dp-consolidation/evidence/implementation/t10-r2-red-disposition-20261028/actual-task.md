type: coding
images: no
card_path: tasks/T10-r2-product-repair.md
card_sha256: b7e04eaafc9dcdebf563564fabc74511f2c987834d2a9a889d8e18232e5d28e3
envelope_producer: agent-team-loop-pm@0.83.0
write_face: .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py, .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/**

<!-- mw-dispatch-card: v1 -->
## 上下文

项目目标 `.agenticdoc/goal.md:5`；原任务 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`，沿用其中 AC-004/012/014/049/050/051/052、VC及全部验收。当前产品 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py:378`、`:517`、`:1018`、`:1315`；`decision_wire.py:625`。这是原36任务/7stage中的T10分段TDD返工，不增加逻辑任务/预算/timeout，不改变DAG、目标或权限。
阶段A `workers/dpc-t10-r2-test-preparation/output.md` 实际done/exit0/已由PM吸收ack，新增14items。原研究37/22函数计数不实；阶段A实测旧50/20 test函数、64/24顶层函数，116旧items。仅新增lifecycle测试，task-state未变。
PM已真实执行两次完整两文件suite，均130 collected、8failed/122passed、rc1；两次focus均8failed/6passed。完整stdout/meta/report/protection在 `evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/t10-r2-red-20261028T065500Z/` 与 `runs/t10-r2-red-controls-20261028T064853Z/`。第一label是目录标识，实际pytest时刻06:48:00.481515～06:48:03.977632Z，不按label回填时刻。无unexpected failures，旧116及6新增正控绿。三个product仍冻结SHA、1891mirror/14pyc/744旧证据/live5前后相等。八项真红不等于所有9静态预测真。
原外部write-face dispatch被拒且零task/queue；机器不允许你写外部目录。OS fixture人工权限仅供PM独立执行；本worker完全不执行产品/pytest/runner/import，不写OS或绕机器守卫。PM在你终态后运行新label绿测；缺测试执行是明确分段，不可声称worker PASS。

## 要求

1. 本人完整读当前三个产品、两assigned测试与采用的单源协议/原批准合同到实际EOF，保留读取范围与真实before/after bytes/SHA/EOL/diff。先吸收两次真red完整stdout到EOF；不要拿worker摘要/静态预测代根因。原三个product和两tests可读；不得改tests。
2. S1真红：同request event_id导致refusal→真实choice、不同choice都静默duplicate。保留原O_CREAT|O_EXCL写锁与幂等；同内容重复必须仍duplicate/零增量；不同事实必须记录可区分新事实或返回明确failed/conflict，不覆盖首行/伪成功/偷偷二次业务裁决。冲突判定应在既有原子写锁控制下，不能以读前检查绕并发。
3. S3真红：dp-auto缺handling_options及非法单候选集仍记录业务选择。通过decision_points单源entry_material_issues/resolve_entry_choices及preparation校验修复动态材料/合法choice，缺/非法候选集fail closed、合法2..5候选及选中basis正控继续成立；不是legal集合为空便忽略检查。不要复制候选语法或依据词表。注意旧dp-pm-steer `_material()`测试helper未提供全部producer业务材料，writer原职责是记录已验证结果及依据；不能未经合同依据将完整所有entry producer材料新硬门强套到writer而破坏旧116，或改旧helper/弱断言来蒙绿。若实际必须扩全entry验证且与已批边界/原断言冲突，具体报告，不偷偷放宽动态验证或造新授权。
4. S5真红：executed/settled只核before，不核此前同事项已记录after。沿用terminal非递减时间与同key/task/logical关联，顺序合法/失败锁回合正控保留；新事实不能倒序。使用既有锁/读写机制，检查实际并发TOCTOU而非仅单线程绿。unknown/null不得猜或改为当前时间。
5. S7真红：creation的已redact before与调用方原secret snapshot比对失败。沿注入redactor做记录表示的等值复述，保持before不回填、实质不同快照拒绝、null与[]/顺序敏感/秘密不落盘。不得为了绿移除校验，或把任何masked snapshot当任意before/权限。
6. S4真红：Windows .AgenticDoc与.agenticdoc同路径但case-sensitive parts门放过。只修test-scope guard对平台同路径的识别，保留production scope合法假fixture路径与test scope禁止所有.agenticdoc组件规则。不能利用大小写/8.3作为许可、放松守卫、在live路径探测。8.3当前未构造/未验证，若无法合法离线证明保留明确未验，不声称已覆盖。
7. S2/S6/S8仍未知，不引入全局decision_id唯一/单terminal/public builder私有化等未批准语义，不扩decision.py。S9一致性正控现绿，保持producer常量同源。不要趁机重构不相关代码、删功能、恢复25退役入口可调用或修改旧history/cases。
8. 原两tests包括stageA新增14items完全只读；旧116、原函数AST/source/assert强度、新增正控/失败期望保持；任何需要额外测试先报告具体test建议由下一原test-face交接，不自行写其他test。保存三个产品最小diff；未改task-state可不改，不为凑面改动。
9. 只允许-B的纯AST/文本/syntax读取校验器（不得import产品）。禁止pytest、产品import、runner、generator、服务/HTTP/decision CLI/provider/observe_submit/npm check/build/install/commit、OS写、临时日志%TEMP%及删除。上轮阶段A曾%TEMP%重定向后删除为独立越面披露，不是合法模式；你全部工具/日志落自己新key evidence面，保留不清理。不得覆盖原red/原runner/worker历史。
10. PM终态后新label跑原assigned完整两suite/focus至少两次并独立复验保护、原断言及边界；你的done只表示局部产品交付未验证，不是T10handoff/S2/QG/signoff。未来green允许增加items，不把116当固定总数；最终原L2/T32check/独立review/全部gate不降低。

## 交付格式

最终回复与 `product-repair/report.md` 五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`；改动表头必须 `文件`，每路径完整canonical且独立一行，不用省略号/目录标签混进表。给三产品before/after SHA、diff、实际读取EOF、每真red根因→最小修复定位、原锁/秘密/合法正控如何保留、纯静态校验及未执行命令。写明本人没有运行pytest/产品import/OS写，无绿测/PASS/签收，PM下一步可精确执行，未验8.3与S2/S6/S8不改语义。PM吸收终态后ack并继续独立测试。

## 写入允许面

- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/**

## 写入禁止面

除上述4面所有路径；特别两test、pm-controlled/test-preparation及其runs、原evidence/卡/worker/state/DAG、live、14pyc、所有OS（含获批PM fixture根）、其他key、history/monitor/web/TS/registry/cases/config/ledger/gate/grant/预算/依赖/lock/dist。不能借产品import/临时文件绕面，不能删除/恢复已有偏差。

## 验收命令

本阶段worker仅 `python -B <自己evidence纯AST/文本校验器>`（不import产品，完整原始stdout/stderr/rc落自己evidence）。实际红测已经PM两次执行；后续完整绿测由PM在获批OS新label独占执行：真实isolated cwd下 `python -B -m pytest -p no:cacheprovider -q --basetemp <PM新label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py`，最小env/禁cache插件/有效child网络护栏。完整npm check原T32 PM-direct不提前执行。

## 改动历史

原T10三次116局部绿、失日志/OS越面/pyc漂移历史不变。阶段A新增14items，PM本轮两次130items实际8F122P及focus8F6P；这次阶段B才修真red根因，全部before/after及旧保护/未验证写新product-repair，不覆盖旧artifact。

## 交付段契约（本角色）

本角色（type: coding）的恢复契约段：report.md / output.md 必须按下列标题成节（可直接复制；缺任一段即 settle 判缺失）：

- `## 结论`
- `## 证据`
- `## 残留与未验证`
- `## 上下文来源`
- `## 改动清单`

以上为种子，不是探索上界；可自行检索补充上下文
<!-- /mw-dispatch-card: v1 -->

执行原逻辑T10 R2阶段B，严格按卡：PM已经两次真实130items/8F122P，focus8F6P；只修卡列三个isolated产品及自己product-repair证据。先全文读实际当前产品/tests/真red stdout到EOF并保护before；S1/S3/S5/S7/S4最小修复保原锁/同源/秘密/正控，S2/S6/S8未知不造新语义。机器无外部写面：本人绝不pytest/产品import/runner/OS写（包括%TEMP%重定向），仅-B纯AST文本静态检查；PM在终态后原suite新label绿测。两test和stageA/PM red/artifacts只读。最新freshbefore与cardSHA在evidence/implementation/t10-r2-red-disposition-20261028/check.json。最终五节canonical路径报告，说明产品交付未验证，不能声称绿/PASS/全handoff/S2/QG/signoff。不改36任务/DAG/预算/timeout/live/旧历史。
