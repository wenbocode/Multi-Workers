---
type: coding
logical_id: T10
execution: worker
deps: [T03, T04, T09]
---
# T10 R2阶段A — 回归测试与PM离线执行脚本准备（不实现产品，不执行产品）

## 上下文
项目目标 `.agenticdoc/goal.md:5`；原卡 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`；当前 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py:812`，`decision_lifecycle.py:436`，`decision_wire.py:625`。原T10/36任务7stage/53AC/VC与依赖/验收/预算不变；只是原逻辑T10 R2 TDD交接分段，不新37实现任务或新timeout。
T10旧局部116P、完整semanticfalse；最新两audit.done/acked：`evidence/implementation/t10-handoff-audit-20261027.md`给9项静态预测，`t05-t10-audit-disposition-20261028/report.md`是PM限定处置。不预设9全真，不降断言或回退active8/retired25。
用户对具体OS许可问项要求继续到结束；授权与PM根mkdir真成功在 `evidence/implementation/t10-r2-pre-dispatch-20261028/{approval.md,check.json}`，准备/5beforebytes/old-functions/1891mirror/14pyc/744原证据均在同目录。原5+外部面R2 dispatch实际write-face-outside-base拒绝零task/queue，保留 `tasks/isolated/T10-lifecycle-state-r2.md` 与dispatch-refusal.md。人工OS权限不覆盖worker机器base，因此本worker绝不执行会写OS的测试/脚本。只写当前原两tests及key内PM脚本；PM随后直接在获批OS新pm-verification子面执行真red，再发原产品修复writer。

## 要求
1. 先完整本人读当前T10五source/test到实际EOF及采用的关联协议/已批合同；原wire2264LF非旧audit2263，原各文件bytes匹配precheck。保存本人read范围/before/AST-source-assert，不拿snapshot当read。5product三个implementation文件只读！本阶段只写原2test追加回归和自己的测试工具证据。
2. 针对真规格优先新增最小回归/合法正控：S3缺dynamic handling_options/invalid entry材料非法choice不得record业务决定；S1同request拒绝后later有效choice不得被吞，而真正同内容重复仍幂等且冲突可见；S5 executed/settled after不倒序（含顺序合法对照/失败回合不fakeexecuted）；S4 Windowscase/8.3安全门只用PM外部私有fixture假路径，8.3无法合法构造记录未验不猜；S7秘密redactor before等值复述/null与[]。每项对真实writer/单源校验入口，不stub/shadow production模块，不测试fake实现。新增tests原产品预计red，但你未执行，不能写真实red或PASS。
3. S2/S6/S8/S9先核已批合同/parent逻辑：不要新增未经确认的decision_id全局唯一/单终态、私有化或删public builder、扩decision.py面。若实际不同DP同logical合法就报告为什么，不写错误期望的失败测试；冻结producer常量同源可append一致性测试。未知保留不是静态9缺陷都已确认。
4. 原当前test文件完整原函数AST/source/assert强度保留，原116items收集不漏，不skip/xfail/弱化既有测试；可追加所需top imports但所有旧函数正文源码/AST保持，行号变化原因明确。区分原37/22函数与实际test/helper数；新增回归后item数可>116，不套总数锁。对PM将修改产品前真实红测留单项q和整两文件commands。
5. 编写完整PM可审计/直接运行的 `rework-r2/test-preparation/run_pm_tests.py` 和必要 `sitecustomize.py`/纯guard preflight脚本，仅在你key evidence面，不执行它们或import产品。入口接显式 `--fixture-root C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification` 与唯一 `--label`；对子目录必须不存在→新建，已有对象拒绝，不清理/重用旧路径。工具和原始全stdout/stderr/rc/argv/cwd/env键名/真正imports/依赖prepost/hash/完整inventory差异均在本key新自己evidence面，fake HOME/TEMP/project/basetemp仅该PMOS子目录。
6. Runner最小env白名单，不继承provider/worker/PI_*/项目/credential类变量，值不打印；所有Python-B/PYTHONDONTWRITEBYTECODE=1/UTF8/PYTEST_DISABLE_PLUGIN_AUTOLOAD=1，-p no:cacheprovider。实际产品__file__由真实解释器确认current5isolated和相关decision_points/book/context/decision；不可让缓存或live模块替代。每个Python子进程通过受控PYTHONPATH载key内sitecustomize，进入guard先记录可核sentinel；硬拒绝DNS/TCP/UDP/HTTP/provider及未知非Python子进程。此两suite不需要真实网络/CLI服务，原faux monkeypatch/fixtures必须覆盖实际call路径；guard前置自己正反控制证明child也拒绝socket/未继承creds，不能仅父patch或继承减DROP。没有网络抓包就不说绝对瞬态未外连。
7. 保留既有O_CREAT|O_EXCL锁/原fixture生产writer允许写假项目，不用production scope规避test-scope guard；全部假对象来自明确PM新外部fixture。脚本生成本身只keyevidence写，没有OS写；你可以-B做纯AST/文本/syntax读取校验但不import/pytest/执行产品/生成器，不多行python-c。所有脚本顶层imports，不内嵌多行临时bash/python代码。
8. 每次PM run同原assigned两文件执行，可先列出建议baseline/focusedred/fullred命令，但脚本不把已知失败当rc0；raw logs先存再解析，独立重跑不同label，不同结果留原artifact。运行前后保护当前14pyc(原1漂移不恢复)、四旧/八新cases/decision_points/context/book/decision/backends/T05test/T28monitor/T27history/TS registry、全1891mirror/744旧evidence与live5，脚本本身不得写产品。新增两test变化是本阶段唯一合法mirror差异；PMrun应零额外mirror变化。旧fixture/auth/ledger/失日志不动、不追认旧OS写。
9. 不运行测试/产品导入/生成器/HTTP/决策CLI/service/model/node/observe submit/npm check/build/install/commit，不改implementation文件/其他test/旧证据/DAG/state/卡或OS对象。PM不是业务codewriter，仅执行你生成且完整审阅的测试runner；你的终态是test-preparation局部完成待PM红测，绝不是T10修复/semantic通过/整体完成。
10. 原预算内完成有界必要回归和完整安全runner，不无限研究，不自加timeout。若执行/范围守卫冲突，真实报告未做/剩余，禁止借已批OS目标绕自己写面。最终给PM下一条准确argv和预期是否red，不能把预计写成执行证据。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_task_state.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/**

## 写入禁止面
除以上3面一切；特别所有OS目录(含已批准测试根及其兄弟)、三个implementation源码、live全树、原证据/卡/worker run-output/state/DAG/cache/旧cases。生成PM runner不是允许你执行runner；机器不允许OS面所以本人不做会产生OS文件的动作。

## 验收命令
本worker仅-B纯AST/source检查，真实产品/pytest由PM直接执行：
- PM argv：`python -B <rework-r2/test-preparation/run_pm_tests.py> --fixture-root C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification --label <唯一label>`。
- runner内部cwd真实implementation-worktree/packages/multi-workers；最小env/child护栏下 `python -B -m pytest -p no:cacheprovider -q --basetemp <PM新label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py`。
- 原116items与追加回归收集列表/旧AST-source/assert保护、预期红的输入及合法正控/guardpreflight/真实imports/全log路径完整。新增tests必须由PM跑真red后原产品writer才允许实现；不删原验收、不少收集。

## 改动历史
原R2外部face信封拒绝零task/queue留史；本新阶段A只两test+key工具，没有真red/implementation改动。保存本阶段before/after bytes、真实diff/AST-source/assert/item估计与未运行记录，PM后续红测和产品修复为同逻辑T10的后续attempt，不重写原历史或增36总数。

## 交付格式
最终及 `rework-r2/test-preparation/report.md` 五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。表头“文件”，两个test与所有脚本canonical paths/diffs、旧函数保护和本人EOF、每S项哪些有规格回归/哪些未知/证伪依据；写明本worker未执行产品/tests/未实现/未写OS/预期red不是真red。PM准确argv、原全suite合同及下一需运行条件明确。回读工具和报告完整；不写正式QG/PASS/签收/receipt；PM吸收终态后ack。
