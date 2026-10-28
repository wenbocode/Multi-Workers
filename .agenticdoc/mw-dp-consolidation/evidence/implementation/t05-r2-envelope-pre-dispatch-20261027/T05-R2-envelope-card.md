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
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/**
ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-013, AC-040, AC-042, AC-043, AC-051]
vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-013, VC-040, VC-042, VC-043, VC-051]
deps: [T03, T04, T09]
execution: worker
---

# T05-R2-envelope — 原R2业务不变，仅显式补齐派发写面枚举

## 上下文
`.agenticdoc/goal.md:5`、`.agenticdoc/mw-dp-consolidation/spec.md:128`、`design.md:201`；原逻辑T05/36任务/7stage不变。业务要求全文承接`tasks/isolated/T05-eight-cases-r2.md`，此卡不新增业务方案、权限/预算或旧测试修改权。
已批原T05为11副本产品+自己的证据目录；R2因`## 写入允许面`仅引用frontmatter而无explicit产品条目，实际seed header只包含evidence。这是PM卡片格式错误，不修活parser/原task/run，也不绕当前worker守卫。旧R2card SHA与seed/evidence保持，必须先确认旧attempt收口、保存freshbefore才派此修正attempt，不双writer。旧R2未完成目标不按成功交接。
PM真实缺陷与正例：`evidence/implementation/t05-pm-handoff-20261027/{report.md,check.json,probe.json}`。原T05/T10真实done/exit0/acked，T10五文件只读保护；原16P12F和116P分别仍需PM共享稳定复验。卡外history owner=T27，monitor=T28，web=T29，不扩此面。

## 要求
1. 仅两根因原面修复：模板仍旧dp3/dp6/schema2；8case未来UTC时间却声称实际准备发生。完整继承原R2七项要求，原goal/AC-VC/验收原样保留。
2. 编码前完整分段读当前11产品及workbench test到实际EOF，截断续读；保存fresh beforebytes/hash/EOL、28原test函数AST/source与原断言强度、fulldiff/inventory/14pyc；真实focused红→同一断言绿。模板只由原生eight scaffold/schema3与registry派生，骨架仍未准备、不造有效请求/授予身份，不legacy fallback。
3. 时间来源须真实记录、明确时区、固定可重现，或明确纯合成fixture不冒充已发生准备/授权；不猜时区/按run-start回填旧材料，不用每次wall-clock造成漂移。8随包case由真实generator同步更新，字节与自己private out相等，evidence源path:line真实，basis/material/meta不无关重写，四旧case字节不变。
4. 28当前test函数AST/source保持，只追加两根因回归；不删/skip/xfail/弱化原12monitor/history/DOM安全断言或改旧独立tests。原整文件验收仍实际运行，保留真实rc；focused绿不代完整验收。原失败日志和未知保留，scope故障不伪造产品red。
5. 每个Python含静态import/子进程-B与PYTHONDONTWRITEBYTECODE=1，禁pytest cache/autoload/真实网络/provider/决策CLI/服务/观察submit；最小UTF8环境/private自己的evidence HOME/TEMP/project，实际隔离import/cwd、fake backend。脚本写自己证据后-B运行，不多行python-c，不外部OS sink，不改guard为过测试。
6. 14现存pyc和原1漂移历史保护，不清理/回填/基线重取抹偏差。T10三产品/两tests、原卡/原run/output/worker证据、PM negative/check/probe/状态与DAG禁止写。不得新增budget/timeout/watchdog/授权/改冻结transport/model/config/goal/spec/live/build/安装/依赖lock/dist/重启/commit/push/link。只在现有授权内修这两项，终态需PM复验/ack，不跳S2/L2/check/reviews/QG/signoff。

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
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/**

## 写入禁止面
允许面外全部。允许面内也不无关重写；特别四旧case、原R2 evidence/rework-r2、原T05/T10/PM证据及live/历史/授权/预算/配置/源码链接等上述禁止面不可因相对路径或fixture名称扩大。

## 验收命令
- cwd=`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`；`python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py`，新两根因可同文件-k focused红→绿，不代全suite；完整stdout/stderr/rc/环境/import/依赖hash保存。
- `python -B -X utf8 scripts/build_decide_cases.py --out <自己rework-r2-envelope/private-fixture/generator-out> --quiet`；八case生成/字节/生产book+逐choice-basis/原生template-scaffold/四旧锁。PM原probe不得改，PM将在新证据目录重跑。
- 不跑其它test/CLI服务；完整npm check仅T32 PM-direct。

## 改动历史
原T05done/exit0/acked及全部16P12F/8case/pyc偏差记录不变；原R2信封故障及seed/card hash保留，不伪写旧attempt新面。该卡只是原面信封修正待派，当前没有产品改动或通过声明。

## 交付格式
五节`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。changed-files用完整canonical副本路径，“文件”表头不混目录；实际源码/字节/fulldiff/命令/rc/28AST保留/新增红绿及未验范围可核。实现/局部验证/原suite失败/整体QG-signoff分清，不修parser或伪造receipt。
