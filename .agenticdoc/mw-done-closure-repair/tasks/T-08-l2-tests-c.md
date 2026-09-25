# T-08-l2-tests-c

状态: done（2026-09-25，随 worker dcr-t06t08-exec-tests 交付） · 覆盖: AC-009/011 · 依赖: T-06

## 目标

洪泛回归锁（4e874f5cc 行为）与 marker 生命周期 L2。

## 步骤

1. VC-011/AC-009：30 tick 混合场景（多 key、gate approve/reject、reprompt、in-flight 交替）→ 断言 gate-answered ≤1/gate id、gates 文件增量 ≤ key 数（approved stalled gate 恰一次消费，不洪泛）。
2. VC-013/AC-011 L2：(a) 覆盖成功后 marker 不存在（同锁删）；(b) advance exit=0 后 marker 不存在（惰性清理）；(c) 同 sha 重复失败 → marker 单文件原地更新不增殖；(d) 终态（DONE/closed-legacy）后 marker 不存在（终态清扫）。
3. AC-002 断言强化（与 VC-002 呼应）：reprompt task.md prompt 全文逐字节 == `_l3_prompt(key, N+1)` + `REPROMPT_INSTRUCTION` + 失败行列表——在真实 dispatch 产物上断言（非重组 mock）。

## 验证

- `python -m pytest test_autopilot_conductor_exec.py -q` 新用例绿 + 零回归。
