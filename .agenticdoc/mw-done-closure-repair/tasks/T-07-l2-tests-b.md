# T-07-l2-tests-b

状态: done（2026-09-25，随 worker dcr-t06t08-exec-tests 交付） · 覆盖: AC-004/005/006/007 · 依赖: T-06

## 目标

场景 B/C/D 用例：人工修稿保护、预算耗尽 stall、非结案类分流、in-flight 零 advance。

## 步骤

1. VC-006/AC-004 场景 B：gate-blocked 失败后外部按工程词表重写 achieved.md → 断言此后事务不覆盖（**reprompt 在飞期间与收敛后全程字节不变**）→ reprompt 轮收敛后 advance exit=0（AC-004 修订后口径：不写"下一 tick"）。
2. VC-007/AC-005 场景 C：round_budget=1 耗尽（reprompt 轮仍不合规）→ stalled=True、l3 家族 dispatch 总数 ≤ l3_limit（含首轮，不随后续 tick 增长）、l3-verdict.txt 保持 meets、stall reason 含词表 gate 阻塞。
3. VC-008/AC-006 场景 D：失败行不含 achieved.md（如 pm-state/QG 类失败行）→ reprompt 派发增量=0 + 既有 streak stall 四件套照旧（advance_stall_ticks 归其所有）。
4. VC-009/AC-007：reprompt 在飞期注入多 tick → advance 事件增量=0（in-flight 双前缀守卫未被绕过）。
5. 附：mark_stalled 追加「## 遗留问题（stalled 草稿）」后 marker sha 失配路径——stall 后 approve → resume credits → 事务重跑不覆盖（T-04 注记的交互闭环）。

## 验证

- `python -m pytest test_autopilot_conductor_exec.py -q` 新用例绿 + 零回归。
