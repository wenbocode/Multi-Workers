# T-05-reprompt-branch

状态: done（2026-09-25，随 worker dcr-t03t05-conductor 交付） · 覆盖: AC-001/002/005/006/007 · 依赖: T-03, T-02

## 目标

D-005/D-006/D-002 落地：`_verify_loop` meets 分支四路展开 + gate-blocked(achieved.md) 失败原文回流 L3 reprompt（自持预算封顶）+ `l3-reprompt` timeline 事件。

## 输入

- T-00 漂移映射：meets 分支现行形状（评审时 `verdict == "meets" and l3_source is not None` + meets∧无源回退 below）、no-verdict/below 预算先例、in-flight 双前缀守卫、`l3_limit = budget + credits`
- advance 失败行格式（advance_phase.py:584-591）：`GATE BLOCKED:` 头 + `   - ` 前缀逐行 + exit 1
- closure.py：`failure_lines` / `has_achieved_failure` / `compose_reprompt_prompt` / `REPROMPT_INSTRUCTION`

## 步骤

1. meets 分支展开四路（T-00 锚点处）：
   - (1) 事务成功（advanced）→ 既有消费路径；
   - (2) `(verdict, err)` 中 err 非空且 `has_achieved_failure(failure_lines(err))` → **reprompt 路径**（下述 2-4）；
   - (3) err 非空但失败行不含 achieved.md → 既有 gated/streak 路径原样（AC-006 分流——advance_stall_ticks 归其所有）；
   - (4) below（含 meets∧无源回退）→ 既有 below/repair 路径不动。
2. reprompt 路径预算：**自持检查** `used < l3_limit`（不得依赖 advance streak——dispatch 事件打断 streak，F-11）；耗尽 → `mark_stalled`（reason 注明词表 gate 阻塞），**verdict 保持 meets**（不写 below——`_persist_l3_verdict` 双向刷新会失真 dossier，D-005）。
3. 预算内 → 派发 `l3:{key}` attempt=used+1（沿用 dispatch 既有 l3 家族签名；reviewer 工具集 read/find/grep/ls 不变），prompt = `closure.compose_reprompt_prompt(_l3_prompt(key, used+1), failure_lines(err))`。
4. timeline 事件 `l3-reprompt`：单行限长摘要（`_one_line` 同型，不进多行原文）；EVENT_TYPES 为开放词表（timeline.py:67-84 "NOT for rejection"），无需改枚举。
5. in-flight 双前缀守卫天然覆盖 reprompt 在飞期零 advance（AC-007）——验证不绕过。

## 验证

- 与 T-06..T-08 L2 用例共同验证（AC-001/002/005/006/007 场景）。
- `python -m pytest test_autopilot_conductor_exec.py -q` 零回归。
