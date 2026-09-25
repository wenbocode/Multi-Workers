# T-01-prefix-e2e-evidence

状态: done（2026-09-25） · 覆盖: AC-001 前置实证 · 依赖: -

产出：evidence/plan-prefix-e2e-20260925.md —— 判定 (a) 缺口复现；附带发现并修复 e2e 夹具 credentials.timi 漂移（+1 条目，跨 key 面问题已登记 D-105）；基线：e2e_l2 6 passed + 1 failed（full_chain 修复前红）。

## 目标

修复前跑一次 e2e_l2 全链，实证 done 门禁对 stub 词表缺口的实际行为（RQ-1 F-12 是代码级推断：stub `## Achieved` 含「无遗留阻塞项」但不含「系统行为变化」）。结果决定 D-007 证据链口径。

## 输入

- `packages/multi-workers/test_autopilot_e2e.py`（e2e_l2 marker；`python test_autopilot_e2e.py` 亦可直跑）
- 观察点：full-chain 用例的 stub worker 行为（:276-277 附近）、achieved.md 落盘内容、timeline advance 事件序列

## 步骤

1. `python -m pytest -m e2e_l2 -q`（package 根），记录退出码与用例结果。
2. 对 full-chain 场景：检查产物 achieved.md 是否含「系统行为变化」/「遗留」字面量；检查 timeline 里 verify->done 的 exit 值与失败详情（若 blocked）。
3. 判定二选一：(a) 缺口复现——gate 对 stub 词表 blocked（进入现状 gated→streak→stall 死路）→ 修复后该用例即回归面；(b) 不复现（stub 或转录路径恰好合规）→ 词表缺口复现改由 AC-008 合成词表夹具承担（D-007 预案），记录原因。
4. 写 `evidence/plan-prefix-e2e-20260925.md`（命令、退出码、字节级观察、判定 a/b）。

## 验证

- 证据文档含上述四项；判定 a/b 明确且与 AC-001/AC-008 的测试口径一致。
