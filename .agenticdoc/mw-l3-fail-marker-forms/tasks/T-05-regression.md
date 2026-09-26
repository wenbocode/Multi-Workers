# T-05 全量回归 + 证据

状态: done（2026-09-25 17:55，PM 直执） · 执行者: PM · 覆盖: VC-008/010

默认套件（python -m pytest -q）：2 failed, 978 passed, 10 deselected（88s）。
对账：d20a270d5 基线 927 + 16（76d5d612e provenance）+ 30（T-01 L1）+ 5（T-03 L2）= 978 ✓，零新增失败。
2 失败 = 已知外域先在（readcap 冻结 blob / verdict-freshness true-below 读 E2Feature 外部树），与基线完全一致。
e2e_l2：8/8 终稿（新测试 13.2s）；kill_respawn 首跑 Windows 文件锁瞬态 PermissionError，隔离复跑绿（run-kill-respawn-rerun）。
证据：evidence/runs/{run-suite,run-e2e-l2,run-e2e-l2-attempt1,run-kill-respawn-rerun,run-e2e-diag}-20260925.txt。
另登记：closure-reprompt/L3-轮预算共享计数交互（见 run-e2e-diag，观察项非缺陷）。
