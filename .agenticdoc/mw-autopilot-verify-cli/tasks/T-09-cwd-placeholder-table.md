# T-09 cwd / 占位符真值表 + E2 形状回归

- AC: AC-013, AC-014 · VC: VC-013, VC-014 · 波次: 3（依赖 T-03/T-06）
- 写面：**新建** `packages/multi-workers/test_autopilot_verify_cwd_table.py`（只新建测试，不改实现）

## 契约（design D-008）

- ≥18 行真值表：`mode ∈ {single, dual, partition}` × 根组合（含 `control≠partition≠parent`） × `xkey_verify_cwd ∈ {"", 各枚举}` × argv（0 占位 / 1 占位 / 多占位 / 含未知占位 / 嵌入占位）。
- 每行断言：**精确展开 argv**（逐元素字符串）+ **精确 cwd** + 非法时的**精确错误**（kind 与文本形状）。
- 必含：E2 形状回归（`active: partition`、`partition=H:\git\E2Feature`、`parent=E:\UEMigrator`；绝对路径断言允许 `skipif` live 存在性检查）；`{control}` token；dual 缺省 = game 根；嵌入占位 `{partition}/tests` ⇒ fail-closed。
- 必须证明 `render_toolchain_command` 未变：跑 `test_common_target_config.py` 的 parity 集。

## 验证

- `python -m pytest -q test_autopilot_verify_cwd_table.py test_common_target_config.py` 全绿。
- 非空洞对照：把 `workspace_root` 临时改为返回 control 根 ⇒ partition 行必须红。
- `[VERIFY]` 行：真值表行数、control≠partition 断言、嵌入占位负例、parity 集。
