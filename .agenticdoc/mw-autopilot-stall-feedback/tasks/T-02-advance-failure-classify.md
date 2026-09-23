# T-02-advance-failure-classify

状态: done · 覆盖: AC-002, AC-005 · 依赖: T-01

## 目标

把 advance 失败变成可机读、可派生的信号：分类函数 + 尾部窗口读取 + 连击派生。

## 步骤

1. `autopilot/timeline.py`：新增 `tail_events(path, *, max_bytes=524288, limit=400) -> list[dict]`（读文件尾部字节、丢弃可能的半行、逐行 JSON 容错、返回尾部若干条）；`EVENT_TYPES` 增 `resume`、`l3-no-verdict`。
2. `autopilot/conductor.py`：
   - `_classify_advance_failure(text) -> str`（design D-3 的四类规则，纯函数）；
   - `_advance_failure_streak(project_root, key, edge) -> tuple[int, dict[str,int], str]`（design D-1 的扫描规则，用 `tail_events`；失败开放返回 0）；
   - 三个 advance 调用点的失败事件 detail 追加 `class={cls}`（成功保持 `exit=0` 原样）。
3. `autopilot/config.py`：新增 `advance_stall_ticks` 默认 5 + 范围 (1, 50)。

## 验证

- `pytest test_autopilot_timeline.py test_autopilot_conductor*.py`：既有用例不回归；`exit=\d+` 正则仍匹配。
- 新增单测：分类 4 类 + 未知 fallback；streak 在「成功 / 同 key 的 dispatch / stalled」处打断；不同 edge 不合并；`beat` 被忽略；尾部读取对损坏行容错；阈值缺失取 5。

## 执行记录

- 2026-09-22 23:55 完成。
- `autopilot/timeline.py`：`EVENT_TYPES` + `resume`/`l3-no-verdict`；新增 `tail_events(path, *, max_bytes=512KiB, limit=400)`（尾部字节窗口 + 逐行容错 + 半行丢弃）。
- `autopilot/conductor.py`：`_classify_advance_failure`（四类）、`_one_line`、`_advance_stall_ticks`、`_advance_failure_streak`（timeline 尾部派生，失败开放）、`_record_advance_result`（统一三处 advance 调用点，失败事件 detail 追加 `class=`）。
- `autopilot/config.py`：`advance_stall_ticks` 默认 5，范围 (1, 50)。
- 测试：`test_autopilot_stall.py`（分类 5 例 + streak 打断 3 例 + tail 有界/容错）；`test_autopilot_timeline.py` 事件计数锁 15 → 17。
- 结果：`python -m pytest test_autopilot_*.py` = **223 passed, 7 deselected**（0 failed）。
