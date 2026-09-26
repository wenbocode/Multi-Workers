# T-07 解除 3 处 skip 并验证 T-03 依赖用例（小卡）

key: `xkey-repair-mechanism` · 依赖: T-03 已落地 · 覆盖: VC-008, VC-011（写侧）, VC-012

## 背景

`test_autopilot_xkey_registration.py` 有 3 个 `pytest.mark.skip`（T-03 依赖）：gate flood（VC-012）、开关关闭零扰动（VC-008）、写侧 prompt 锁（VC-011 写侧）。T-03 已落地（`conductor.py` + `config.py`），这些用例现在必须真跑。

## 任务

1. 读那 3 个 skip 用例，**逐个**去掉 `skip` 标记，按 T-03 的实际实现校正断言（只校正**测试侧**对实现的引用：函数名/参数/文件位置；**不得削弱判据**——若某判据在当前实现下真的不成立，停下来在报告里写清"哪条 AC/VC 不可满足 + 证据"，不要改成弱断言）。
2. 三个用例的判据（逐字来自设计）：
   - **VC-008**：`xkey_repair` 关闭 ⇒ `xkey/` 目录零新增工件，且既有 conductor 相关测试全绿（这一半由 PM 在最终回归覆盖，测试内只需断言零工件 + 零 xkey 事件）。
   - **VC-011 写侧**：`_l3_prompt`（`conductor.py:1113-1127` 附近）构造的 prompt 文本**必含机器行要求**，且该要求落在**必含节内**（不是节外附录）——断言 prompt 字符串包含机器行契约（`cross_key_test` / `owner` / `handoff` 键名）且位置在节内。
   - **VC-012**：同一 pending 工单经 N=5 tick ⇒ 为该 request_id 生成的 `xkey-authorize` gate 文件数 = 1（用 tmp_path + 直接调 conductor 的聚合函数，或复用 T-03 报告给出的调用方式）。
3. 跑通并给出证据：`cd packages/multi-workers && python -m pytest -q -s test_autopilot_xkey_registration.py`（`-s` 以便看到 print 的 `[VERIFY]` 行）。

## 验收

- 该文件 **0 skipped**（或跳过的原因已升级为 needs-clarification，不许留 skip）。
- 报告含：3 个用例的真实输出（含 `[VERIFY]` 行）、对实现的引用点 file:line、`git diff --stat`（应只含该测试文件）。

## 纪律

- **只写 `test_autopilot_xkey_registration.py`**（+ 报告）。不改实现、不改其它测试、不改 TS。
- 不跑全量套件；不 commit。
