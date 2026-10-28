type: coding
images: no
card_path: tasks/T05-eight-cases-r2-envelope.md
card_sha256: 49ebb4b47c610493632647c386e0c7f3feee1805924a83736a321584dd52394d
envelope_producer: agent-team-loop-pm@0.83.0
write_face: .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/scripts/build_decide_cases.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_book_template.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_workbench.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-type.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-pm-steer.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-check-task.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-QG.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-gate-approve.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-sign-key.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-auto.json, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-route.json, .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/**
decision: dp1-dispatch-type:53a97714-b886-4f6e-8a98-6042a96e1410

<!-- mw-dispatch-card: v1 -->
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

## 交付格式

五节`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。changed-files用完整canonical副本路径，“文件”表头不混目录；实际源码/字节/fulldiff/命令/rc/28AST保留/新增红绿及未验范围可核。实现/局部验证/原suite失败/整体QG-signoff分清，不修parser或伪造receipt。

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

## 交付段契约（本角色）

本角色（type: coding）的恢复契约段：report.md / output.md 必须按下列标题成节（可直接复制；缺任一段即 settle 判缺失）：

- `## 结论`
- `## 证据`
- `## 残留与未验证`
- `## 上下文来源`
- `## 改动清单`

以上为种子，不是探索上界；可自行检索补充上下文
<!-- /mw-dispatch-card: v1 -->

执行原T05-R2同一两根因业务修复，仅修正信封后合法重派，不新增逻辑任务/业务方案/预算。原bad R2实际done/exit0/BLOCKED已吸收ack、守卫拒绝0字节，1891镜像/11产品/28测试函数/14pyc未变；不存在并发原writer。PM自己调用真实shipped extractor→renderer→parser，原卡12/坏卡1/新卡12 roundtrip通过，证据t05-r2-envelope-pre-dispatch-20261027/{check.json,carrier.json,before-metadata.json}，新card SHA49ebb4b47c610493632647c386e0c7f3feee1805924a83736a321584dd52394d。入场自己核task header12 entries=11 exact副本产品+自己rework-r2-envelope/**，不要绕守卫或改原task/card。业务只template旧dp3/dp6/schema2和8case未来UTC却注释实际准备时间；PM原负例t05-pm-handoff-20261027/probe.json保持不变。完整读源/test实际EOF，保存真实freshbefore bytes/hash/EOL/28原函数AST/source，追加两根因行为red→最小实现green，模板沿真实eight scaffold/schema3，时间真实记录明确时区固定可复现或明确纯合成fixture非实际发生，不猜-8h或回填旧run/material，不用每次wall-clock漂移。真实generator私有out→8随包case字节一致，basis/material/meta/provenance源path:line真实，四旧case字节保护。28原test全部AST/source/assertion强度不变，原12monitor/history/DOM安全断言不删/skip/xfail，-k focused绿不代原整文件suite，完整rc/log均保留；不动T10五文件/任何共享源码/其它旧tests/PM独立probe/check/原worker历史/evidence。T10已done，each测试前后真实共享module SHA/import根记录。所有Python含probe/subprocess-B及PYTHONDONTWRITEBYTECODE=1；禁cache/autoload，最小UTF8环境，自己evidence内私有HOME/TEMP/project，禁网络/provider/决策CLI/服务/观察submit、OS外部sink、多行python-c、任何pyc改删或基线重取抹旧漂移。冻结授权/预算/goal/spec/transport/model/config/live/build/check(仅T32)/依赖lock/dist/install/restart/commit/push/links不变。history owner=T27，不T06，monitor=T28/web=T29，自己不扩面。五节报告canonical产品路径/真实red-green/28AST保留/完整suite rc和未验范围。原bad R2耗时不是业务重试失败，不开新timeout/预算。终态自动PM吸收ack→同原negative fixtures新输出复验→按原36DAG合格才release，不跳S2/L2/QG/signoff。
