# T-04-marker-guard

状态: done（2026-09-25，随 worker dcr-t03t05-conductor 交付） · 覆盖: AC-003/AC-004/AC-011 · 依赖: T-03, T-02

## 目标

D-003/D-004 落地 conductor 侧：step-2 覆盖守卫改为三条件授权 + 原子写 + 同锁删；step-5 advance 失败现场写 marker；exit=0 惰性清理；终态清扫。

## 输入

- T-00 漂移映射：step-2 现状守卫（研究时 :1363-1369，stat st_size → write_text，非原子）、step-5 advance（:1381-1389）、入口 DONE 短路（:1330-1332）、`_mark_key_done`、`_apply_stalled_rejections`
- closure.py API（T-02 契约）；`gates._write_atomic` 形状先例（gates.py:198-204）

## 步骤

1. step-2（锁内）：读 `current_bytes = achieved_md.read_bytes()`；`marker = closure.read_bad_draft_marker(key_dir)`；`closure.overwrite_authorized(marker, current_bytes, ...)` 为 True → `closure.write_bad_draft_marker` 语义外的**草稿覆盖**也走原子写（tmp + os.replace）+ `closure.delete_bad_draft_marker(key_dir)` 同锁删；False → 不触碰 achieved.md（现状 ≥200B 后验 below 路径保持）。
   - 注：覆盖内容 = L3 reviewer output.md 的 `## Achieved` 转写（AC-010 逐字节，既有逻辑不动），本任务只换守卫与写入方式。
2. step-5 advance exit≠0：在 key-{key} 锁内 `closure.write_bad_draft_marker(key_dir, failure_lines)`（失败行来自 T-05 的解析；本任务先接 `closure.failure_lines(err)`）；`ConductorLockHeld` → 当 tick 放弃（返回 gated，W1 形退化）。
3. advance exit=0：锁内惰性清理 `closure.delete_bad_draft_marker(key_dir)`（人工修稿路径的失配 marker）。
4. 终态清扫：`_mark_key_done` 与 `_apply_stalled_rejections` 置终态（DONE/closed-legacy）时 `closure.delete_bad_draft_marker(key_dir)`（幂等）。
5. 注记（评审 R4）：mark_stalled 向 achieved.md 追加「## 遗留问题（stalled 草稿）」会改变绑定字节 → marker sha 失配 → 不覆盖（方向保守，无害）。

## 验证

- VC-004/005（T-02 单测已覆盖纯逻辑）；本任务集成验证并入 T-06..T-08 的 L2 用例（AC-003/004/011 场景）。
- `python -m pytest test_autopilot_conductor_exec.py -q` 零回归。
