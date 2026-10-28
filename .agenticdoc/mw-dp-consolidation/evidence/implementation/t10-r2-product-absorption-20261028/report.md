# T10 R2阶段B终态吸收与独立复验准备

## 结论
阶段B实际 `needs-clarification`、exit2、end2026-10-28T07:04:25.204Z；产品报告与两diff已完整回读并工具ack。该终态保持，不改成done/exit0/recovery-complete。只接受可核字节范围的局部产品交付，未有实际green或T10handoff，S2继续开放。
新阶段C `dpc-t10-r2-verification-preparation@2026-10-28T07:09:46.792Z` 实际running/PID72752、07:10:16Z heartbeat，实质进展未报告null。仅自己新key evidence一个面；当前全部产品/原tests只读，禁止worker产品import/pytest/OS写。任务是同T10独立复验准备，非第37逻辑task或提前正式S6review。

## 证据
- 原run、report.md(1..220及221..EOF)、wire.diff完整、lifecycle.diff(1..260及261..EOF)已回读。worker原摘要称根因已修是静态预期，不当8红已转绿。wire的真实append锁/guard/read_events/summarize源码1975..EOF读过；不是全wire EOF审计。
- `check.py`纯字节/JSON读取，rc0：1891mirror名称相等，仅wire/lifecycle两获准产品SHA变化；两tests/taskstate未改。14pyc字节与PM新鲜原before相等（原1漂移历史不恢复），live5相同；744旧evidence逐字节保持。before/after copies对应真实当前产品，report路径在原evidence面；该范围核是前后净字节，不证明全历史/瞬态无越面/独占作者。
- 当前wire82286B/SHA `429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc`，lifecycle65501B/SHA `73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5`，taskstate3871B/原SHA保持。worker静态器after_lines分别2314/1647/82（LF行数），报告2265/1549/83指before逻辑行，不能作为after EOF行数。原文本保留，当前全产品本人EOF未完成不回填。
- 机器缺口是真实记录缺失：trace中产品edit有[WRITE_FILE]；shell mkdir/重定向使用$e等产生[WRITE_UNRESOLVED]，before/after/pm-red-read copies和diff路径没有完整可用[WRITE_FILE]。保存本次抽取 `machine-write-lines.txt`；不能把它归成单纯表头误解析，更不能向原trace补造事件或修活parser使exit2变绿。所有列出路径当前落原批准face仅是范围事实，不等于正式recovery账本完备。
- PM本人本轮完整读取 `decision_task_state.py` 1..EOF和 `test_decision_task_state.py` 1..EOF；其他产品/生命周期suite仍待本人完整当前读取。阶段C强制独立读全部5文件/采用runner当前EOF并保存真实范围；PM完成读取前不再次违反顺序去运行green，不拿worker摘要/AST代本人阅读。
- 新卡SHA与实际seed/header单一face核由sync.json保存；seed label仍省略isolated的历史限制保持，实card路径和SHA一致。原36tasks/7stage、原依赖/AC/VC/commands/productfaces/status/history不改，仅T10阶段B终态/阶段C尝试metadata更新，其余35对象精确相等。

## 改动清单
| 文件 | 改动 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-r2-verification-preparation.md` | 同T10独立验证准备，产品全部只读、唯一新证据面 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/check.py` | before/after和真实许可面净字节核，不import产品 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/sync.py` | 真实终态/新seed-run核与仅T10 metadata同步 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/check.json` | 当前2产品变化、原tests/live/14pyc/744旧evidence保护及明确未green |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/machine-write-lines.txt` | 原trace只读抽取的实际write/unknown事件，不补事件 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-product-absorption-20261028/sync.json` | stageB原exit2/acked、stageC实际running/单面/SHA与契约保护 |
| `.agenticdoc/mw-dp-consolidation/implementation-isolated-dag.json` | T10当前R2尝试metadata，保留原attempt status和旧观察 |
| `.agenticdoc/mw-dp-consolidation/pm-state.md` | 当前资格、历史缺口、下一真实复验步骤，不改变Phase |

## 残留与未验证
- 原阶段Bneeds-clarification/exit2与ledger gaps保留，仅组织现有权内验证，不作gate恢复/正式receipt。范围核通过不是无历史违规证明；阶段A TEMP重定向后删除、原OS越面/失日志/pyc漂移均保留，未清理/追认。
- 当前130套件/focus未重跑。新green runner须是新副本绑定真实当前SHA，不覆盖旧red脚本/constants/log，再独立双writer/重放/秘密/guard正反控制；较新after floor是否误拒绝同event_id早期真实executed的幂等重放，是待验证预测，不据静态新增语义或改产品。
- PM全5当前文件EOF义务未完成，本轮仅两个taskstate文件全读。阶段C独立阅读全文准备不能替代PM本人全读；继续读取后再真测，不回填上一red先执行的阅读顺序偏差。没有新产品测试/import/OS fixture写。
- 8.3未验，S2/S6/S8未知语义不变；T05原12consumer红与producer局部/后期T27/T28资格顺序仍待解决。原全部L2/TS/realCLI/effects/H12/T32check/独立review/QG/signoff未完，禁止livecutover/provider/安装部署/预算/DAG变更/commit不扩大。

## 上下文来源
项目goal、当前state、原T10/stageB实际seed-card/run-report-diffs、两次PM真red及freshbefore、原trace事件、本目录新保护与实际stageC seed/run；采用源码读取范围如上，不称全仓审计。
