# T-03-return-tuple

状态: done（2026-09-25，worker dcr-t03t05-conductor + PM 亲验） · 覆盖: AC-010 保持（回归面） · 依赖: T-00

产出：conductor.py +110/−19（T-03/04/05 合一交付）；PM 亲验：9 return 点元组化、meets 四分支、自持预算、终态清扫；两失败均 worktree 判定为外域先在。偏差 5 项均按任务卡授权且方向安全。

## 目标

D-001：`_done_transaction` 返回值从单 verdict 扩为 `(verdict, err)` 元组——advance 的 stderr 从丢弃（研究时 conductor.py:1381-1383）变为回传调用方。唯一调用点（研究时 :1229）同步适配。err 语义：advance exit≠0 时为捕获的完整 stderr（utf-8 + errors=replace，同 advance.py:164-192 透传口径）；其余路径为 `""`。

## 输入

- T-00 漂移映射的现行锚点：`_done_transaction` def 与 9 个 return 点（advanced×2 / below×3 / gated×4）
- 同型先例：`_l3_round_verdict`、`_advance_failure_streak`、`_set_index_phase`（元组返回范式）

## 步骤

1. 9 个 return 点逐一改为携带 `(verdict, err)`——除 advance exit≠0 的 gated 点携带 err 外，其余 err=`""`。
2. 调用点解包 `verdict, done_err = self._done_transaction(...)`；本任务不消费 done_err（T-05 消费），先以 `_ = done_err` 占位或直接绑定。
3. 跑现有 exec 用例确认零回归（两个测试文件对 `_done_transaction` 零直接调用/monkeypatch——RQ-1 F-8 已核验，断言全为副作用）。

## 验证

- `python -m pytest test_autopilot_conductor_exec.py -q` 全绿；`python -m pytest -q` 对照基线零新增失败。
