# T10 R2阶段A吸收、真实红测与阶段B派发

## 结论
阶段A真实done/exit0已回读并工具ack；只接受测试准备，不认可产品修复。PM两次真实完整两suite收集130，均8failed/122passed/rc1；两次新增focus均8failed/6passed/rc1，没有unexpected failures。原116items与6新增正控通过，8新增失败已从预测转成实际红。T10完整semantic仍false，S2开放，T05及后继资格不默认放行。
产品修复实际派发 `dpc-t10-r2-product-repair@2026-10-28T06:51:39.278Z`，PID20580；06:52:09Z heartbeat/随后06:52实读run为running，实质进展未报告=null，不能当完成。默认coding模型、无外部写面；只3个原implementation产品及自己新evidence，tests只读。原36tasks/7stage/deps/AC/VC/预算不变。

## 证据
- 阶段A `workers/dpc-t10-r2-test-preparation/output.md` 完整回读并 `ack_worker_result` 成功。实测旧50/20顶层test函数，64/24顶层函数；此前37/22计数不采纳。阶段A worker声明EOF，不替代PM本人读取。
- PM完整审阅原729LF runner、sitecustomize/preflight/import-probe；发现前条件或自检失败仍继续产品执行、sitecustomize异常会被解释器吞掉继续启动、Python-family仅凭basename。保留worker原交付，独立 `rework-r2/pm-controlled/` 四脚本副本定点改安全执行护栏：严格授权根、-B、前置/自检/import/collect失败即停止；guard初始化异常os._exit(86)；子进程仅同一解释器且-B/无-S/-I/-E、guard环境继承且不shell。不是产品业务实现。
- 两次真red在 `evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/`：`t10-r2-red-20261028T065500Z` 与 `t10-r2-red-controls-20261028T064853Z`。第一label为选定目录标识，实际pytest `06:48:00.481515～06:48:03.977632Z`，不将label冒称真实UTC；所有run的真实时刻在meta。完整stdout/无stderr/rc/argv/env键名/provenance/collection/protection/sentinel/report保留，不重用目录。
- 首次pytest.stdout分两段1..240及241..EOF回读。真失败：S1 refusal后有效request被duplicate吞掉、同request不同choice静默duplicate；S3 dp-auto缺候选及非法单候选两items没有raise；S5 settled旧after没有raise；S7原秘密before与存储redactedbefore比较拒绝；S4两类.AgenticDoc路径没有raise。没有推断8.3已验或其他S2/S6/S8缺陷已证。
- 第二guardpreflight：child内DNS/TCP/UDP/未知非Python拒绝，新增missing-B/-S/丢guard env拒绝，合法同Python孙进程-B继承、文件IO正控通过；凭据键名为空。每轮保护报告problems=[]，1891mirror/14pyc/744旧evidence/live5/3products前后净SHA相等，imports为实际isolated路径。不是抓包或全部历史瞬态无写证明。
- `check.json`06:51:11Z新鲜五beforebytes/hash/1891mirror/14pyc/原DAG/state；`dispatch-check.json`及actual-task.md/actual-run.json核原cardSHA `b7e04eaafc9dcdebf563564fabc74511f2c987834d2a9a889d8e18232e5d28e3`，实际机器4exact面一致。seed label省略isolated段的旧追踪限制保留，实卡路径/SHA/body核一致。

## 改动清单
| 文件 | 改动 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/run_pm_tests.py` | 原worker副本定点补执行前置fail-closed；原文件不改 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/sitecustomize.py` | 原worker副本补初始化失败终止、严格guarded Python子进程 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/guard_preflight.py` | 新增-B/site/env继承负控 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/probe_imports.py` | 原worker字节副本；实际isolated provenance |
| `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-r2-product-repair.md` | 原逻辑T10阶段B最小product-only返工卡，禁止worker产品执行/OS写 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-red-disposition-20261028/prepare.py` | 纯字节before保护，不import产品 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-red-disposition-20261028/record.py` | 实际seed/run/card/4face回读 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-red-disposition-20261028/sync.py` | 仅原T10 R2 metadata新增及资格说明，核原契约/其余35tasks相等 |

## 残留与未验证
- 阶段A曾用机器TEMP重定向随后删除的披露，与此前OS越面/失日志/1pyc漂移分开留存；未追认/恢复/清理，没有再次绕worker机器权限。Ledger Malformed/Unresolvable告警源自省略路径/混合文字，不修活parser或旧报告。
- PM尚未本人完整读当前所有3产品/2tests到EOF；本轮真实red基于worker已审阅测试和PM当前新回归/runner审阅，不能称完整独立EOF审计或资格完成。该执行顺序与此前要求先PM EOF存在偏差，明确留档，后续完整资格前补读，不回填。
- 原runner被冻结PRODUCTS SHA：绿测必须在新的受控runner副本中绑定真正已审阅修复后SHA，不能编辑旧red runner/hash消去历史或直接关闭保护。后续PM两次assigned/focus及真实并发、秘密不同快照/合法guard、完整旧断言再验证；净SHA不证明全部瞬态无写。
- 初始化失败退出86、严格授权根与stop-before-products分支本轮静态审阅，尚未逐一专门动态负测；普通guard及新增child负控有实际证据。不声称全harness所有失败分支测试齐备。
- S2/S6/S8未决语义、8.3未验、T0512consumer红/原owner顺序、全L2/TS/T32check/独立review/QG/signoff仍需完成。没有live copyback/cutover/provider/HTTP/CLI/effects/配置授权/预算/安装部署/commit或阶段关闭。

## 上下文来源
`.agenticdoc/goal.md:5`；原T10卡；阶段A卡/output/脚本/新测试；t05-t10-audit-disposition-20261028；两实际red完整日志/元信息；本目录freshbefore和实际seed/run。当前code writer正在运行，PM不在漂移窗口认资格。
