# T-06 conductor / dispatch 根锚定（verify cwd + 同族 5 锚点）

- AC: AC-013 · VC: VC-013 · 波次: 2（依赖 T-02/T-03）
- 写面：`packages/multi-workers/autopilot/conductor.py`、`packages/multi-workers/autopilot/dispatch.py` + **新建** `test_autopilot_xkey_cwd.py`

## 契约（design D-008）

- `xkey_verify_cwd` 解析：枚举 `{"", "control", "partition", "parent", "<root name>"}`；`""` = auto = `mw_common.workspace_root(config)`（partition→partition 根、**dual→game 根**、single/legacy→control 根）；**未知根名 ⇒ fail-closed**（kind `invalid-config`，不新增 kind）。
- 现状 `conductor.py:3459` 的 `root = str(project_root)` 与 `:3471` 的 `cwd=root` 改为解析后的工作区根。
- **同族 5 处一起重锚**（`:2513/:2576/:2942/:3408/:3651`，均为工作区相对文件路径）；**协调根（ledger/tickets/evidence）恒为 control 根不变**。
- 配置读取切到 `effective_config.load_effective`（`:169/:1874/:2036/:3975`）；`dispatch.py:227-241` 同样切换。**只读不得建目录**。
- ticket 的 `verification`（`:2579`）同时记录**展开后** argv 与解析后 cwd（原未展开值可保留）。
- 全部改动在 `cfg["xkey_repair"]` 门内；`xkey_repair` 关闭时行为逐字不变。

## 验证

- `python -m pytest -q test_autopilot_xkey_cwd.py test_autopilot_e2e.py test_autopilot_xkey_registration.py test_autopilot_conductor.py` 全绿。
- 新用例：`control≠partition≠parent` fixture（复用 `test_partition_dispatch.py:178` 的 `_write_partition_yml` 形状）断言 verify cwd = partition 根、同族重锚生效；E2 形状回归（partition=`H:\git\E2Feature`、parent=`E:\UEMigrator`，绝对路径用例允许 skipif live 检查）；非法根名 fail-closed。
- 非空洞对照：把 cwd 改回 `project_root` ⇒ 新用例必须红（记录输出）。
- `[VERIFY]` 行：cwd 真值、同族锚点、关闭时零变化。
