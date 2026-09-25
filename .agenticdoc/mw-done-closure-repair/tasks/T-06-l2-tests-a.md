# T-06-l2-tests-a

状态: done（2026-09-25，worker dcr-t06t08-exec-tests，T-06/07/08 合一交付） · 覆盖: AC-001/008/010 · 依赖: T-04, T-05

产出：test_autopilot_conductor_exec.py +610（14 test_dcr：13 场景 + stderr 形状锁）；红控 12/14 对 HEAD conductor 预期红（非空洞）。

## 目标

exec 测试夹具升级 + 场景 A 主路径与词表可移植性用例。

## 输入

- `test_autopilot_conductor_exec.py` 现有 fixture：`_fake_advance_factory`（def :158-185、done 失败分支 return 在 **:175**——勘误后行号，现有用例不可达该分支）
- advance_phase.py:584-591 真实 stderr 形状：`GATE BLOCKED: <key> (current phase: <phase>)` 头 + `Current phase: <phase>` + `   - ` 前缀失败行（`NO MATCH: achieved.md missing pattern '<pat>' — <desc>`）+ exit 1

## 步骤

1. 夹具：fake advance 增加 done 失败模式——逐字节复刻上述 stderr 形状（词表行从注入参数取，不硬编码进 autopilot/ 源码；fixture 文件在包根、扫描面之外——VC-003 口径已核验）。
2. VC-001/AC-001 场景 A：标准词表 fixture（reviewer stub 产出不含「系统行为变化」「遗留」的 Achieved）→ tick 驱动 → reprompt 派发 → 修正轮产出合规稿 → 三条件真 → 覆盖 → advance exit=0 → phase=DONE、stalled_gates=0、gate_answered=0。
3. VC-010/AC-008：第二词表「行为影响」「未了事项」同流程（证明词表字面量零硬编码、机制可移植）。
4. VC-012/AC-010：断言 achieved.md 与 l3-a{N}/output.md `## Achieved` 节逐字节相等（尾部换行 ≤1）。
5. 断言事件序列：gate-blocked 失败 tick → `l3-reprompt` 事件 + dispatch 事件 → reprompt 终态 → advance exit=0。

## 验证

- `python -m pytest test_autopilot_conductor_exec.py -q` 新用例绿 + 旧用例零回归。
