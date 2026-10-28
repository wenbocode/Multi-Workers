---
type: coding
write_face:
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
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2/**
ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-013, AC-040, AC-042, AC-043, AC-051]
vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-013, VC-040, VC-042, VC-043, VC-051]
deps: [T03, T04, T09]
execution: worker
---

# T05-R2 — 原面修复八入口模板与准备时间出处

## 上下文
目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`；已批`design.md:201`；原卡`tasks/isolated/T05-eight-cases.md`。用户已允许完整开发及原面普通问题主动返工，PM不另索重复批准。本R2仍原逻辑T05/原11产品面/原AC-VC与预算，不第37任务，不改7stage DAG。
原attempt `workers/dpc-t05-eight-cases/run.json`实际done，output已吸收acked，保留原日志与真实16P12F/定向16P。PM实际focused复验`evidence/implementation/t05-pm-handoff-20261027/{report.md,check.json,probe.json}`：八case生产generator/字节/book/choice-basis通过，但模板三项失败、八prepared_at皆未来且注释称实际准备发生时间。
当前源码root/cwd只`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`。T10在原wire/lifecycle/taskstate面运行，不能改它或copy/shadow共享模块。

## 要求
1. 本卡自己的before来自当前R2前真实11文件，不从主树或旧before覆盖副本。所有采用源码及当前workbench测试分段读到实际EOF，工具截断必须续读。保存bytes/SHA/EOL/full增量diff、原函数AST/source、当前1891inventory和14pyc。先新增针对下列两根因的真实行为红，再定点实现、同一红测转绿。
2. 已授权`decide_book_template.json`不再携带旧dp3/dp6、schema2/state/questions_version活模板。按真实`decision_book.scaffold_book`与八入口registry建立schema3八入口模板；保持模板是待填骨架而非伪造有效请求/授予身份。模板book顶层/material/preparation/context/evidence与真实原生scaffold一致；旧编号仍拒绝，缺材料/依据仍fail-closed，不加legacy fallback。旧独立测试文件不在面，不修改它们；旧pin不是冻结这个已批产品的权限依据，其未迁移处如实列债。
3. 生成器`CASE_PREPARED_AT`当前`2026-10-27T20:56:00+00:00`却说明是实际准备/合成时刻；PM13:16:41+00:00的8fixture证明它未来。修正时间及出处语义：真实准备时刻必须用本R2实际一次准备记录及明确时区、冻结为可再现值，并记录来源；不能猜测“减8h”、用run start回填材料准备、修改旧证据或编造旧发生时间。如果采用纯合成fixture时间，必须明确不是实际发生/授权证据，不能继续声称未来时刻是已发生实际准备。生成器再跑不使用当前wall-clock导致永久漂移，不新加服务预算或clock策略。
4. 8随包case只能由真实更新generator输出建立，重新生成后逐字节与私有out一致；provenance源path:line必须真实可解析，所有basis/material/meta及固定eight/自由auto/七route/sign数组/role/图像硬门保留。四旧case精确字节不变。case业务内容不借本R2无关重写；若源码行变化需同步真实生成结果。
5. 当前所有workbench test函数及原assertion强度保留（前后AST/source对比），只加两根因回归；不全文件重写、跳过/xfail/删原12红、弱化history/DOM/注入/凭证/锁断言。原整文件suite仍需运行且真实rc保留；定向两根因green不代原验收。T10共享输入仍在写，每次测试记录其三模块before/after SHA和真实__file__。窗口变化保留为unstable，不从变化造产品red或最终qualified，不无限等待/轮询/修改timeout。
6. 不把monitor/DOM/history原12失败全部归单根因，原comparison/log完整保留。真实owner history=T27（不是T06），monitor/playground=T28，web=T29；这些writer不拥有本workbench test。完整消费者迁移与最终共享suite需要PM协调，自己不扩面。准备/选择/实际执行/settled/done/QG/签收各自独立。
7. Python所有调用（含静态import、临时probe、子进程）都必须-B及PYTHONDONTWRITEBYTECODE=1；禁pytest cache/自动插件、最小UTF8环境/私有HOME/TEMP/project、真实副本import绝对路径、无真实网络/provider/loopback submit/决策CLI/服务探针，fake backend。继承14pyc现存状态，原1漂移及其原SHA历史不抹除，不删/重写/基线重取宣称修复。不得用多行python-c临时脚本，脚本写自己evidence后-B运行。

## 写入允许面
只frontmatter列出的原11个副本exact产品及`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2/**`。读范围不限于种子，写面不随探索扩展。允许面内也只两根因定点改动及其真实再生成，不重新复制实施树。

## 写入禁止面
其它全部文件。特别原T05 evidence（不含自己的新rework-r2子目录）、原run/task/output/卡、PM独立fixture/check/probe/状态/DAG、T10五产品、decision/points/context/book/backend/monitor/playground/history/TS/其它tests、四旧case/14pyc均禁止写。live/config/gate/brake/ledger/grant/claim/goal/spec/冻结配置/权限/预算/新watchdog/timeout/transport/provider/model/重试/安装build/npm check/依赖lock/dist/服务重启/commit/push/link禁止。不伪造dp2 steer/id/receipt或人批准。

## 验收命令
- cwd=`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`：`python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py`；本两根因新测试红→绿可额外同文件-k focused运行，不取代全suite。
- `python -B -X utf8 scripts/build_decide_cases.py --out <自己rework-r2私有fixture/generator-out> --quiet`；8文件/逐字节/四旧原SHA/生产check_book真实repo_root及逐choice-basis/真实scaffold-template比对。
- 全部stdout/stderr/rc/实际argv/import根/环境/依赖SHA保留；不改PM原probe.py来造green。完整npm check仅T32 PM-direct。

## 改动历史
原T05done/exit0、16P12F完整日志及subset16P、八文件输出、pyc自报偏差和ledger warning都保持。PM原模板三red和未来时间八red在t05-pm-handoff-20261027，不修改历史。R2逐次记录实际before/after bytes/hash/EOL/diff、red-green、inventory及未验证，不补写过去事实。

## 交付格式
report/output按五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。完整/relative路径可核，changed-files表只使用“文件”表头，不在表头混副本目录；给完整canonical副本路径避免已有ledger短路径warn，但不修活解析器。代码完成、局部验证、原suite未过、整体L2/QG/签收明确分开；未完整验证就如实报告，PM终态吸收ack再独立资格并继续原DAG。
