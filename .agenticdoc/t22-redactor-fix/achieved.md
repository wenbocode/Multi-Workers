# Achieved: T22 生产写链路修复

## 结论

`task_before` / `task_after` 现在真的能写进生产决策账本，并且读侧判为 `recorded`；
基线失败集合未变化。真实 dp1 记录已落盘（`dp1-dispatch-type:9f4c1d2e-aaaa-4bbb-8ccc-111122223333`），
修复前后对照与测试矩阵见 `evidence/fix-verification.md`。

## 系统行为变化

1. **决策写入（`mw decide run` / `mw decide sign` / `mw decide lifecycle`）**
   - 修复前：账本 filter 是 gate 形状的 `KnownSecretRedactor`，sanitizer 调用
     `scrub_tail_prefix` 抛 `AttributeError`，被 transport 吞掉 → 调用报成功、账本 0 行
     （带 `task_before` 的 dp1 记录全部丢失，2026-10-25T02:12–02:16Z 之后完全静默）。
   - 现在：注入 `decision.credential_redactor()`；wire 模块或凭证快照不可证时抛
     `LifecycleInputError` 并显式返回 `status=refused/error_class=input`（不再静默、不再 traceback）。
   - `KnownSecretRedactor` 的定位不变（book gate 过滤器，仍被拒绝当 capture filter）。

2. **metadata 键的清理语义**
   - `decision_wire._sanitize_metadata_key`：只有被裁掉的尾片段 ≥ 4 字符才改写键名。
   - 影响面：所有带嵌套 metadata 的捕获（`task_before`/`task_after` 等固定 schema 字段名）
     不再被截成 `observed_a`/`complete`；值侧脱敏与 `METADATA_KEY_LIMIT` 裁剪不变。

3. **决策看板展示**
   - `task_before`/`task_after` 从"标签：值"平铺行改为结构化卡片：状态徽标（按状态着色）
     + 状态来源 + 当时记录时间 + `已完成`/`待处理`/`阻塞` 分项列表。
   - 语义不变：`null` → 未记录，`[]` → 无，非法/被过滤 → 无法确认或不显示。

## 验证

- `test_decision_task_state.py` 23 passed（含 5 条新回归，其中 2 条修复前 RED）。
- `test_decision_task_state_ui.py` 8 passed（含 1 条结构化展示回归）。
- dashboard/readable/wire/lifecycle/redactor 相关 354 passed。
- 基线：`test_decision_coverage_safety.py` 6 + `test_decision_known_set_snapshot.py` 4 +
  `test_decision_credential_seam.py` 9 失败，与"临时回退本次改动"对照一致，非本次引入。

## 遗留

1. 扩展侧 `mw decide run` 非零退出仍是静默降级（`upstream-error`），
   `computeDispatchTriage` 在没写记录时仍打 `state=material`；
   `_scratch` 这类不可记录 key 在 trace 里看不到原因。→ 需 TS 改动 + 重新打 bundle，另立 key。
2. `implementation-gate` claim 路径失效：`.agenticdoc/_index.parallel` 无表头行，
   `parseIndexRows()` 找不到 `key/status/claimid` 列 → 永远"无 claim"。
   → 建议另立 key 修 gate（或给索引补表头）。
3. dashboard 资产在 `decision_monitor` 导入时读入，需 `/mw restart` 才生效。
4. 历史记录不回填（AC025）。
