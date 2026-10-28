# T10 R2：两次真实原套件绿、独立重放真红、原产品面继续修复

## 结论
PM真正原assigned 130项 **两次130passed/rc0**，stageA focus **两次14passed/rc0**；此前8红已转绿于这组契约，非T10全handoff。之后真实独立AC052重放最小回归 **1failed/rc1**，揭示新时间floor与既有event-id幂等冲突。继续原T10阶段D `dpc-t10-r2-replay-repair@2026-10-28T07:29:44.606Z` 实际running/PID104036，不增加37task、预算/DAG/验收目标，不把独立红或原机器缺口洗掉。
阶段C真实needs-clarification/end07:24:46.085Z/exit2，完整report1..200+201..EOF、delivery.json与run回读并tool ack；两个JSON确缺机器写入记录，范围/摘要可核但原exit2/ledger-gap保持。未正式recovery-complete，不需要新增OS/跨面权限，也不向原trace补造记录。

## 证据
- PM已实际个人读取当前全部5文件到EOF：wire1..650、651..1300、1301..1980、1981..EOF；lifecycle1..350、351..750、751..1150、1151..EOF；taskstate1..EOF；lifecycle test1..650、651..1300、1301..EOF；taskstate test1..EOF。之前07:11仅两文件全读是真实过去观察，不改旧check/report假已读；完成本次读取在新green/probe执行前，原red阅读顺序偏差仍历史保留。
- 新PM `pm-postfix-tests/run_pm_tests.py`与guard实际全文读完后运行；源自已阅读全文的旧pm-controlled，但新副本SHA绑定当前产品与两个tests，原红runner/const/log未改。collect与旧真实130nodeids集合/数量相等，PID来自实际Popen；每直接child安装哨兵逐PID核，focus返回码独立保真。guard补Popen真实signature.bind包括位置参数/可选executable/shell/环境，缺run配置终止；完整安全负分支仍不是全系统无网络/无瞬态写证明。
- `pm-postfix-tests/runs/t10-r2-postfix-first` 与 `...second` 原pytest.stdout全文分别130passed in2.25s/2.26s，focus.json14passed in0.51s/0.50s；actual pytest.meta.json的argv/cwd/真实UTC/PID、完整raw stdout/stderr/rc保存，label只目录标识不是clock。preflight/import/collect/pytest/focus均0，摘要无unexpected失败或harness problems。
- `pm-postfix-tests/runs/t10-r2-replay-probe-first/pytest-replay.stdout`实际全文：原09executed同event_id在后来10settled之后重复，`record_lifecycle:1070 -> _recorded_after_floor:440`抛LifecycleInputError：task after observation precedes task before observation；这是重复旧事实，不是新旧after追加。实际1failed in0.34s/rc1、problems=[]，wrapper真实07:25:26.110134Z记录。wire锁内guard也先于dedupe是静态第二路径，单独本probe失败发生前置检查，不把第二路径冒充同时动态命中。
- prepare.py rc0独立校验两个完整green reports/raw metadata与probe实际红；1891mirror、两tests/taskstate/14pyc、live5、744旧证据前后相同；原stageB全部evidence摘要保持。stageC delivery13条磁盘bytes/SHA相等、report==output；两个缺machine JSON是获准evidence内且真实存在，但不能推独占作者/全无瞬态越面。
- C全部16边界和新1352行runner仅worker静态准备，PM尚未阅读全文/运行它们；预测15/1不是观测，本次只采已真实自写probe红为D修复依据。C报告TLDR“14项”与实际12functions/16Windows items相区别，保原文字，只据actual manifest与AST/collect后续核。
- D实际seed/header4面与cardSHA核在sync.json，3原products+自己replay-repair evidence；tests/C/PM旧证据均只读，本人禁pytest/collect/import产品/OS写。仅T10 metadata新attempt与实测观察，其余35任务/原contracts/36task7stage/DAG均相等，stage/Phase无改动。

## 改动清单
| 文件 | 改动 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/prepare-green.py` | 新PM受控runner副本/实际SHA绑定准备，标准库API签名核 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/green-preparation.json` | 真实观察时刻/新旧脚本SHA和本次EOF状态，不改旧check |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/run_pm_tests.py` | 独立新副本，双tests SHA/130旧nodeids/每childPID护栏与rc保真 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/sitecustomize.py` | 新受控guard副本，真实Popen签名含位置参数/覆写exe边界 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/guard_preflight.py` | 旧安全控制新字节相等副本，实际已两次/一次probe控制执行 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/probe_imports.py` | 新独立副本，实际isolated产品来源核 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/test_replay_probe.py` | 原AC052已有事实重放独立真实test，非产品实现 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/run_replay_probe.py` | PM获批新label最小env/guard/真实pytest/protection，rc1保真 |
| `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-r2-replay-repair.md` | 真红原面修复D卡，无新37task/权限或语义 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-green-replay-disposition-20261028/prepare.py` | C范围/13manifest/PM双greens与replay1F/freshbefore独立核 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-green-replay-disposition-20261028/check.json` | 原130局部绿、真实probe红、C静态未整体验清晰区分 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-green-replay-disposition-20261028/sync.py` | C终态acked与D实际seed/header/SHA-run、仅T10 metadata同步 |
| `.agenticdoc/mw-dp-consolidation/implementation-isolated-dag.json` | T10当前尝试/实测metadata，其他35及原契约相等 |
| `.agenticdoc/mw-dp-consolidation/pm-state.md` | 当前原suite绿/独立重放真红/D运行，无Phase变更 |
完整本次PM落盘logs/before snapshots/actual seeds及此目录补充JSON的逐文件列表与摘要在 `pm-postfix-evidence-before.json`、`stage-c-evidence-before.json`、`old-stage-b-evidence-before.json`；五before raw copies、mirror/pyc/live snapshots、dag-before/after、sync.json、stage-d-actual-task/run保留。

## 残留与未验证
AC052真红修复等待D终态后独立EOF/diff/SHA/新runner再跑；D运行期间不执行产品/资格验证。之后原130/focus至少两次、probe绿及C全部16并发/旧新after/secret/guard合法正反控制必须真实验证。新绑定不能覆盖本次green runner/旧红/C准备文件。
阶段B/C原exit2与机器缺口、阶段A TEMP写删/原OS越面、pyc漂移/失日志等历史均未清/恢复/追认。secret等价类尚待原契约判断，S2/S6/S8/8.3未验不偷加语义；T05原12consumer红和资格次序仍未完。T10/T05完整handofffalse、S2开放/后继未放行；全L2/TS/T32check/reviews/QG/signoff/livecutover均未完成，不提交/部署。

## 上下文来源
项目goal/原T10合同、当前源码本人的完整读取、实际B/C终态及原报告/Cmanifest、PM新runner真实raw双130绿/focus双14绿/probe真1红、本目录新freshbefore及D实际seed/run。结构phase audit只结构不代表产品通过。
