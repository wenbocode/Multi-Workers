# T05/T10终态吸收与下一工程动作

## 结论
两只读取证实际done/exit0，T05 end2026-10-28T04:11:23.599Z、T10 end04:12:21.460Z，PM已全文吸收两唯一证据并分别工具ack。接受其核心定位，不把research done当产品handoff；完整T05/T10/S2仍false。当前不派后继coding、不改变36任务7stage/deps或提前正式review/QG/signoff。
T05剩余12项的最早失败链为11项T28 monitor case只读壳与活动registry混用，1项T27 history退役fixture投影，测试面T05；7项DOM未进入node，无T29缺陷证据。T10提供9项静态预测，下一步是合法fake红测逐项判真/伪，再组织原五面修复，不继续泛化研究。

## 证据
- finish.json（2026-10-28T04:19:26Z）：只T05/T10取证attempt metadata改变，其他34任务及原36任务7stage全契约/面/命令/deps保持，旧running观察留史，两报告原字节未变；1891产品及当前14pyc相同，无新产品执行或OS对象创建使用。新sanctioned audit EXECUTE PASS仅结构，不是L2/QG/历史无越面证明。
- check.json：实际两run.done/exit0、全文报告SHA/bytes/行数、1891镜像及当前14pyc与派发前相同；PM本轮未运行产品测试/import/真实provider。该hash不证明全部瞬态无写/独占作者，旧1pyc漂移仍在。
- t05-handoff-audit-20261027.md（20488B，df2b1e218769fdb98a9c934ecb0741652f71633fa0b4003a64f7224ae54abe65）PM实际全文读到EOF：12项与旧16项基线对照、11项monitor.py:378-380/1941-1946、1项history.py:2168-2220/test:1145-1149；T03 retire不可回退。writer源EOF未完成，旧两stdout未全文读，不以此代PM完整复现。
- t10-handoff-audit-20261027.md（32318B，264c0d613a7ad583521504617a34dfeeaf8f72b4c6922bdaaf99437b61c514a4）PM按1..110与111..EOF完整读取。原五SHA/旧断言保留为worker静态证据；request/basis/PM-note/terminal已扩充但独立fake复验未做。report真实341逻辑行，非终态摘要192行；日期标题2026-10-27不是实际新run日期，真实28日记录不回填。
- PM已核原T05/T10卡全文：T05原要求“既有失败fixture/原因保留”，但目标也要求四旧case不再出现在可提交菜单；完整旧测试/原case字节及最终验收不删除。T10原卡明确只隔离fixture可由生产writer写假对象，TEMP原本限keyevidence，与test-scope拒绝.agenticdoc冲突需具体目录许可，不能靠换production scope规避。

## 改动清单
| 文件 | 改动 |
| --- | --- |
| .agenticdoc/mw-dp-consolidation/implementation-isolated-dag.json | 只T05/T10取证attempt真实done/exit0/acked及当前观察；旧running观察保留，原面/命令/deps/语义false不变 |
| .agenticdoc/mw-dp-consolidation/pm-state.md | 吸收、具体根因/预测勘误、下一fake红测/原面修复计划及待权限，不改Phase |
| .agenticdoc/mw-dp-consolidation/evidence/implementation/t05-t10-audit-disposition-20261028/ | 新check/原DAG-state与mirror保护/报告；没有产品或外部OS写入 |

## 残留与未验证
### A. T05资格/验证顺序
1. 同意12项不是新增T05回归的现有日志/静态证据；不把未读完整基线或未跑PM suite说成独立行为复现。新取证中T05.status=running为派发时旧观察，当前manifest已是原worker.done且semantic=false；不改旧证据。
2. 不立即采用C1让完整T05通过：原卡窄任务允许带具名既有红记录局部producer交接，但是否可释放已批准后继须依据完整VC/交接边界；不得静默把命令rc1改rc0。C1声称“整文件绿保留S2关闭”又需S5/T27/T28落地，若S2关闭是S3前置，仍有资格顺序问题，不能当已解循环。当前仅两个根因局部通过，不改DAG或新授顺序例外。
3. T28后续本卡已要求active8可提交、旧4只读保留；不是任意二选一设计问题。实现需明确只读历史/活动提交的不同门，不把旧case送回可提交菜单。T27不得以当前registry问句回填旧事实；明确retired/readonly/未记录。待真实owner阶段与前置资格后实现，T05原测试面做相应迁移，30项完整断言及旧case byte lock均保留，不能靠skip/xfail修绿。
### B. T10有界原五面修复计划（先复现，再定点）
- 优先验证S3：材料/动态候选缺失却catalog合法化非法choice入账。必须用真实entry/material/prepared request入口和合法正控区分拒绝与有效业务事实；若复现，T10调用既有单源校验，不改decision_points/decision.py、不开备用provider、不造审批。
- 同波验证S1与S5：同请求的拒绝→有效选择是否被event-id吞掉；executed/settled的after是否可倒序。真实writer/原O_CREAT锁、重复同内容正控/变内容冲突/失败回合证据/顺序正控一起测。按事实区分合法去重与丢事件，不新增第二ledger/授effect权限。
- S4 Windows大小写路径安全门：只用新授权私有fixture内假production路径，不能给任何活路径写“攻击探针”。8.3/realpath是否扩短名必须依当前Windows/Python实证，不采静态断言“realpath不展开8.3”。不能以大小写/短名绕过作合法sink。
- S7 canonical红字before等值复述：合法秘密含量正控与null/[]分清，不记秘密明文/新原文摘要授权限。若确认bug，仅复用现有redactor。
- S2/S6/S8/S9先核已批真实链合同：不同DP/parent/同logical是否已合法定义、终态修订是否需supersedes、builder原调用者及冻结元组是否实际漂移。不能把研究建议变成未经确认的全局唯一ID/唯一终态、删公开builder或扩decision.py写面。只对真实违反已批合同的项修复；未列面另具体报告。
- 新回归先真实red后最小green，原37/22函数及断言/116旧items保护；新增测试后总item可能合法大于116，不能采用“不是116就自动失败”。原test源完整EOF、原字节保存、两assigned suite至少两次及新负例正控，再PM独立资格，尚无新执行/修复或green。
### C. 取证的过强结论不采纳
1. “9项全部fail-closed且无伪审批”未证，S3预测恰为非法choice记business_decisions=1，S4预测为scope可能放行，不能一概称fail-safe；记录不是动作授权，但有污染后继依据风险待证。
2. “外部sink是唯一阻塞”不成立；真实语义缺口、并发/重放/消费者未接线也未验。9项全部是预测，不算9个PM实证缺陷。
3. 当前pyc未变/mtime/old缓存不证明全部Python都带-B；已留T10早期无-B trace、其他作者不确定性，不能洗历史。旧before文本不变亦不证明新增代码不改旧行为。
4. fixture内4个production账本存在事实须保留，原“无账本”声明不准确；原卡允许在独立fixture由生产writer写假对象，不能单凭scope_kind=production就等同活ledger或独立外部越面。实际TEMP/路径/日志覆盖逐项判断，不追认未批OS写，也不新跑production-scope绕test guard。
5. T05 run_exec继承减DROP，报告env名单显示额外credential类变量名进入child；无值回显、未证被读取或真实网络。后续最小env白名单和进入每个子进程的网络护栏必须重新落实，不能只改旧report/借旧绿证明无网络。
### D. 下一动作的具体权限（等待用户，不已授予）
请求一次限定授权：仅当 C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/ 不存在时新建，供本key PM独立复验及随后原T10五面有界返工的离线测试使用各不重叠新子目录；若已存在则不重用/覆盖并回报。只写合成HOME/TEMP/project、pytest fixture及假账本，运行后留存不清理。
脚本/sitecustomize或pytest网络护栏/全部stdout/stderr/rc/argv/env键名仍写本key新的证据面，不需把脚本落OS目录；可由PYTHONPATH加载key内护栏，因此“必须另授权仓外sitecustomize”不是既定事实。假测试自身的受控loopback仅允许已注册fixture服务，不接现有proxy/decision服务/真实provider；子进程同样最小env和-B，保留旧cache/账本/历史。此请求不授活config/ledger/gate/grant、修改guard减安全、外部真实效果、预算/timeout、部署/build/install/commit权限，也不追认原T10 OS写。
许可前不创建/复用该目录，不派会因测试无合法sink而零进展的coding worker；收到具体许可后立刻按原面组织fake红测→定点修复→全suite/独立资格，而不是再派泛研究或要求第二次一般工程批准。

## 上下文来源
.agenticdoc/goal.md:5；两original isolated卡全文；两取证完整唯一报告、实际run及工具ack结果；原PM两个根因独立证据和1891mirror；当前DAG两attempt与未释放后继。原8职责/53AC/VC/36任务7stage/transport/写面/硬门均不变，本处置不写正式QG/签收/receipt。
