# T-00 基线锚点核验

状态: done（2026-09-25 17:10 二次核验） · 执行者: PM

HEAD 更新为 >d5d612e\（provenance-guard 已落地：conductor.py +266、新测试 test_autopilot_verdict_provenance_guard.py 867 行）。
漂移图（76d5d612e 实测）：锚点函数 def 行全部未漂（provenance 插入在 _l3_round_verdict 之后）：_persist_l3_verdict:619（签名 key_dir/verdict/report_src/st，B 加 reason 无冲突）/ _l3_prompt:1113 / _repair_prompt:1129 / _L3_FAIL_RE:1148 / _PROVENANCE_FILENAME:1152 / _l3_resolve_source:1180 / _l3_round_verdict:1196 / _l3_provenance_record:1230 / _verify_loop 内裁决调用 :1481（3 元组解包）/ provenance 记录 :1514 / below-stall :1584/:1597 / repair 派发 _repair_prompt(:1609) / meets persist :1715。
约束：B 不得破坏 provenance-guard 的 867 行测试；fail_line 线程与 suspect 流程复合（record 先于 suspect 分支构造）。
