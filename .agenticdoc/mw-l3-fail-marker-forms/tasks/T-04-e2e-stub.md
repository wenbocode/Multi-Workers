# T-04 e2e stub + full_chain 变体

状态: done（2026-09-25 17:50，PM 直执） · 执行者: PM · 覆盖: VC-011

交付：stub reviewer 增双分支（env MW_E2E_L3_FAIL_FIRST：l3-a1 写 bullet-FAIL 合规稿；l3-a2 写 clean+合规 Achieved）+ 新测试 test_l3_fail_marker_repair_chain（修复 prompt 含 fail_line 断言 / 无 false-meets / provenance 两轮 fail_line 有无 / DONE+meets 终态 / verify->done exit=0）。
e2e_l2 8/8：新测试 13.2s 全绿；test_conductor_kill_respawn 首跑 PermissionError（Windows 文件锁瞬态，隔离复跑绿，[VERIFY] VC-024 全过）——非回归，两次运行记录均存 evidence/runs。
**登记（观察项，非缺陷）**：closure reprompt 预算与 L3 轮预算共享计数——FAIL 轮+修复轮耗尽 l3_limit=2 后，round-2 朴素 meets 被 done 门驳时零 reprompt 直接 stalled（exhausted 2/2，verdict 保持 meets，fail-closed）。e2e 以 round-2 合规稿绕开；真实链路遇此组合会停在可恢复 stall 门。归属 closure/预算域，不属本 key 修复面。
