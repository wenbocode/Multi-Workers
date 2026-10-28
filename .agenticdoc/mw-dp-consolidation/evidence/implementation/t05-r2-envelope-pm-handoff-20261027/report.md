# T05-R2-envelope PM独立交接复核

## 结论
接受两根因局部修复，不接受完整T05交接，不关闭S2。实际R2 done/exit0/已ack；PM在2026-10-27T13:56:39～40Z独立执行generate、原byte-identical probe、补充模板控制，三个rc0。原模板三负例与八未来时间负例归零；八case/生产book/逐choice-basis及生成字节一致，原28函数AST/source/位置及整文件旧byte前缀保持。
worker整文件仍12 failed/18 passed、rc1；本PM复核未运行assigned整文件suite，不能以局部门替代它。后续继续原T05/T10交接核查和原owner修复；当前完整handoff=false、S2/L2/check/reviews/QG/signoff未通过。

## 证据
本目录check.json记录实际三命令argv/cwd/rc、每条命令T10五输入前后SHA稳定；完整generate/probe/supplement stdout/stderr保存。probe.py与原t05-pm-handoff-20261027/probe.py字节相等，旧负例脚本及原输出未改。
- probe.json：八case生产check_book零issue、private generator字节相等、所有支持choice/适用basis核验通过；template_failures=[]、future_prepared_at_cases=[]。
- supplement.json：磁盘模板等build_template/render_template字节，private write_template同字节；八本逐本等真实scaffold_book，schema3通过，必填material/preparation/evidence保持占位，check_book必须拒绝。空骨架不是有效请求/身份授权。
- 时间值2026-10-27T13:45:28+00:00与原worker prepared-at-record.json一致，仅合成fixture编写时钟读数，不证明真实决策准备/授权，不有外部时钟校准或独占作者证明。八case原bytes仅替换该一个时间字符串，除此无变化。
- AST-source-preservation.json：28→30 test函数，旧28 AST/source/位置相等，整个旧95205B文件是当前100533B文件的精确前缀。原失败断言未删除/skip/xfail/弱化。
- product-diff-metadata.json、current-bytes/、diffs/：11实际授权面差异；1891mirror前后相等、当前14pyc保护(原1漂移仍在)，T10五产品及原T05/R2/T10/PM证据在该复核窗口相等。不是完整瞬态无写或全历史合规证明。

## 改动清单
PM不改产品，仅新增本目录私有脚本/日志/快照/报告。以下为独立核实的worker产品增量，完整路径统一根H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/；rawbytes/SHA/diff详见product-diff-metadata.json。

| 文件 | hunks | 增/删行 |
| --- | ---: | ---: |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/scripts/build_decide_cases.py | 4 | +43/-6 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_book_template.json | 1 | +296/-51 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_workbench.py | 1 | +94/-0 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-type.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-pm-steer.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-check-task.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-QG.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-gate-approve.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-sign-key.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-auto.json | 1 | +1/-1 |
| H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-route.json | 1 | +1/-1 |

## 残留与未验证
1. PM未运行整workbench；12F18P是worker真实记录，不当PM复现，需当前源码EOF及稳定fixture完整复验。T10两suite/真实链/旧断言及外部sink许可仍未完成。
2. 当前新probe为旧脚本的逐字节复跑，其case_source_read写死full902/61，不适用当前源，原硬编码结果保留而不采为阅读证据。原probe中的timestamp_claims_to_represent_actual_synthesis字段也是旧诊断标记，不证明真实授权。当前generator本次实际分段读到EOF(938LF/939逻辑行)，模板306LF全文读取；workbench本次仅人工读追加测试段，不能以AST对照冒充全部EOF。
3. test hunk @@ -2272,3 +2272,97 @@实际新增94行，不是新增97行。模板306LF，generator938LF与有无末尾newline须分清。旧摘要过强行数以此独立raw统计为准，原产物和报告不修改。
4. R2 run_isolated.py的run_exec仅继承env减DROP、socket patch没有自动传入subprocess；不能凭docstring断言child全禁网络/最小env。实际suite fake/网络路径须追源码，不推断已有真实调用。PM本目录原probe/supplement各独立进程确实最小env、进程内拒绝socket，未真实调用服务/CLI/provider。
5. 保留失日志、旧pyc漂移/越面及坏信封BLOCKED历史，不伪恢复/清缓存/追认OS写权限。无部署、live copyback、真实模型、TS/L2/T32 check、正式审计/QG/signoff。

## 上下文来源
.goal项目锚点 .agenticdoc/goal.md:5；原T05/R2-envelope卡及原36DAG；原PM t05-pm-handoff-20261027/probe.py和negative evidence；当前隔离generator/template/追加测试；worker rework-r2-envelope/{report.md,product-check.json,prepared-at-record.json}；本目录独立三命令结果/28函数及完整byte前缀/11增量与原证据保护。后续2026-10-28两只读交接补核是新尝试，不回填上述2026-10-27实测时刻。
