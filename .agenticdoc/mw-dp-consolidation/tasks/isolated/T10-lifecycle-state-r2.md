---
type: coding
logical_id: T10
execution: worker
deps: [T03, T04, T09]
ac_refs: [AC-004, AC-012, AC-014, AC-049, AC-050, AC-051, AC-052]
vc_refs: [VC-004, VC-012, VC-014, VC-049, VC-050, VC-051, VC-052]
---
# T10 R2 — 真红测确认后原五面修复，不把静态预测当缺陷

## 上下文
项目目标 `.agenticdoc/goal.md:5`；原卡 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`；当前 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py:436`，`decision_wire.py:625`；已批spec/design/plan及implementation-isolated-dag.json只读。原36逻辑任务/7stage/依赖/权限预算/transport/53AC/VC不变，本卡是原T10有界R2，不是新第37逻辑实现任务。
原T10 done/exit0/acked及三次116P真实留史，但完整handoff=false。两取证唯一证据 `evidence/implementation/t10-handoff-audit-20261027.md`、`t05-handoff-audit-20261027.md` 已done/acked；前者九项S1～S9仅静态预测，过强表述已由 `evidence/implementation/t05-t10-audit-disposition-20261028/report.md` 纠正。
用户对上一具体目录授权请求回复“继续推进到任务结束”，限定授权见 `evidence/implementation/t10-r2-pre-dispatch-20261028/approval.md`；PM实际2026-10-28T06:25:08.416110Z独占mkdir成功，未重用现有目录，见同目录check.json。只允许本worker新私有 `C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/worker-t10-r2/**`；其父根及PM的pm-verification兄弟目录不得写。旧T10 OS目录/越面/首次40setup日志丢失/14pyc原1漂移不追认不清理。
当前五beforebytes/AST-source/1891mirror/14pyc/744原证据hash见pre-dispatch目录。镜像只这五face可变；actual_wire LF=2264，不沿用旧audit声称2263到EOF。必须本人读五当前文件到实际EOF，保存真实read范围，snapshot/AST不能代read。T03/T04/T09技术前置已合格；T05后继整体仍未放行。

## 要求
1. 单writer独占五面，不改live同名文件/其他副本；源码cwd固定implementation-worktree/packages/multi-workers。先完整EOF读当前五源码/测试、采用的相关协议/设计材料，再自保存鲜before与PM快照相符；原37/22函数说法须分test/helper及原116items，逐原AST/source/assert/位置证明未削弱，允许只追加真正回归，不删/skip/xfail/随意改原测试。
2. 优先真实fake生产writer红测：S3非法材料/缺动态handling_options/非legal choice是否记business_decisions=1；S1同request拒绝→后来有效决定是否被event_id吞掉；S5 executed/settled已记录after倒序是否放行。分别合法材料/正确basis/不同尝试与真正同内容duplicate/冲突/执行失败回合/非递减正控。先保存完整原产品真实red及每项输入/出口/ref/code，再最小修复，不能预设9个全真或只绿新测试。
3. S4只在本卡新外部私有fixture里构造假 `.AgenticDoc`/大小写/可用8.3路径，核当前Windows/Python realpath实行为；严禁指向任何活ledger/配置的攻击探针、不建源码链接。大小写遗漏若真则仅紧安全门，不通过换case或短名绕test guard当合法sink。8.3未能合法构造就明记未验，不猜API，不动依赖、不私装工具。
4. S7秘密含量before合法等值复述与不等值/null/[]红字一致性：原redactor和原摘要/metadata契约复用，不存秘密原文/发明原文digest授权。S2/S6/S8/S9先对已批合同判别：不同decision_id/DP父后继在同logical是否已允许、终态修订规则/公共builder真实调用者/冻结元组实际漂移。只修真实违反已批合同的项；不擅加全局唯一decision_id/单一terminal规则、私有化/删intentional builder、改或扩decision.py/decision_points.py面。证伪项给真实控制和原因，契约仍未知明记。T10内可加既有常量同源一致性测试，不新第二schema/ledger/权限。
5. 修复仅T10 original5面，既有O_CREAT|O_EXCL锁与安全过滤/单源catalog/prepared_request复核保留，失败不当有效选择、请求/依据/note/consumed/executed/settled/terminal独立。记录不是effect授权，terminal不是stage/key/signoff。时序与去重须考虑真实并发：检查和append不得绕已有锁；给最小同logical多writer行为测试，不能因单进程绿承诺全面并发。超面真实缺陷具体报告不硬改。
6. 本卡测试必须最小env白名单，不继承worker/provider/项目类任何变量，凭证值从不回显；HOME/USERPROFILE/TEMP/TMP/project/pytest basetemp全在本worker获批外部face；所有代码工具/harness/sitecustomize/pytest plugin/日志仅自己的rework-r2证据面。不得复用任何旧TEMP/basetemp/label；目录子项在每次运行前新建且唯一，运行后保留不清理，不建symlink/junction/hardlink。
7. 每个Python调用/import/subprocess均-B，PYTHONDONTWRITEBYTECODE=1，UTF8，禁pytest plugin autoload/cache；即便纯静态import也必须同纪律。不嵌多行python-c，临时脚本写卡内evidence后运行。真实孤立模块__file__打印并断言，禁止复制/shadow/stub共享production模块来修绿。fake backend必须实际注入每条可能调用的路径，网络护栏进入每个Python/子进程；本两suite不需真实provider/HTTP/决策CLI/服务探针，全部拒绝。若使用node也不得真实网络。不得只父进程patch或继承减DROP冒充最小env/子进程隔离。先验证护栏拒绝socket/读取credential边界的正反控制，不能无护栏先测再补证。
8. 假fixture允许真实生产writer写合成对象，这是原卡允许的测试路径；必须新外部私有fake project且明确不活对象。不换production scope规避test-scope拒绝key的门，不写活ledger/第二业务账本；假对象不是真实业务PASS/签收。
9. 每次run唯一label，完整stdout/stderr/rc/argv/cwd/env键名/真实imports先落证据再解析。两assigned suite全部执行至少两次，原116items必须仍被收集且强度不减，新增测试后total可大于116；不得“非116自动失败”。新回归由原产品真red→修复green，旧消费者测试全结果如实列；局部green不代assigned套件。
10. 每次验证前后保护非本面输入SHA，至少decision_points/decision_context/decision_book/decision/decision_backends及四旧cases/八新cases/TS registry/T05 test/T28 monitor/T27 history/14pyc；全1891 inventory非五面零变化、旧744证据不改。动态窗口受污染留原日志不qualified、不重复制旧before或清缓存抹历史；source/live/check守卫异常如实记录，不修活parser/ledger来消warning。
11. 不运行npm check/build/install/full tests/真实HTTP/model/CLI/serve/observe submit，不改live/root同名代码、config/gate/policy/brake/goal/spec/transport/模型/预算/watchdog/timeout/deps/lock/dist，不commit/push。完整npm run check仅T32 PM-direct保护等价workspace；本任务不声称整体T05/S2/L2/QG/signoff完成。30m实际检查点按现有流程，无新预算/timeout；若预算不足，收尾真实已做/剩余/阻塞，不以token/role/fixture/预算作grant。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_task_state.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/**
- C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/worker-t10-r2/**

## 写入禁止面
上述exact面以外一切；禁止OS父根/pm-verification兄弟与任何旧OS目录。原T10 evidence rework-r2以外全部、原run/output/卡/取证/PM snapshots/DAG/state全只读；不得写新的业务账本/活凭证/config/ledger/gate/authority/brake。卡授权先于运行；scope拒绝必须停止并报告不能绕过。

## 验收命令
- cwd=H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；最小白名单env及child护栏下，`python -B -m pytest -p no:cacheprovider -q --basetemp C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/worker-t10-r2/<唯一run-label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py`；至少两次不同label，原116与新增items分别可核。
- 每次新增/修改测试，完整实际red/green/负例正控先落盘；可用key evidence内wrapper确保fake/网络护栏，但不能换成子集验收。原冻结producer结果及single-source contract一致性要验证，真实caller链/T27投影/TS后继明确未验。
- 本卡不运行npm run check；保全五before/after rawbytes/SHA/EOL/diff、旧AST/source/assert/真实test收集、1891 inventory/14pyc/744旧证据/live5保护和真实imports。

## 改动历史
原T10 116P/首次40setup丢stdout/旧OS与live-baseline/red-prefix/1pyc漂移只读留史；本卡新R2记录从当前before起，不能伪造过去red/恢复日志或清标记。每阶段写真实进度，不能heartbeat代完成。原卡和两audit所有勘误留原产物，此新卡不改原合同/36DAG。

## 交付格式
最终及rework-r2/report.md均五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。改动表头“文件”，canonical exact5产品及各自证据列清、before/after/真实diff统计；S1～S9逐项证真/伪/未知与actual red/green出处，不用函数数或green总数替行为依据。本卡只local工程结果，不写正式QG/PASS/签收/receipt；PM全文吸收终态后ack并独立复验才放后继。
