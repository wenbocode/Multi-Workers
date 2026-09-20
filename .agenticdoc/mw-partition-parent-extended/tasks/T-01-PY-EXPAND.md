# Task T-01-PY-EXPAND: Py 派发展开并入 parent root

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM（本窗口）或 worker
- ac_refs: [AC-001]
- vc_refs: [VC-001]
- pattern_refs: []

## 描述

`packages/multi-workers/autopilot/dispatch.py::_expand_read_scope`（约 :146-176）partition 分支行为修正：

1. 在 control root 追加逻辑之后，追加 parent root：取 `config["parent_root"]`（load_target_config 已 realpath 归一），`str(pathlib.Path(...).resolve())` 幂等兜底；追加条件 = 展开列表中无 normcase 等值项（与 control 判重同一模式）。
2. 返回顺序锁定：[原条目（相对条目锚定 partition root，原序与既有绝对条目不变）..., control（缺失才加）, parent（缺失才加）]。
3. docstring 更新：删除/翻转 "The parent root is NEVER appended by virtue of parentness (AC-008 red line)" —— 改为 mw-partition-parent-extended AC-001 语义（parent = 扩展工作区，展开包含 parent root；空 scope 短路行为不变）。
4. 函数签名与 dual/single 分支零变化。

测试（`packages/multi-workers/test_partition_dispatch.py`）：

- `TestExpandReadScopePartition::test_partition_anchors_at_partition_root`（:604 区）断言翻转：expected == [partition/src, partition/docs/readme.md, outside, control, **parent**]；删除 "parent never appears" 注释断言。
- 新增 case：parent 已显式列于 scope 条目 → 不重复追加；parent == control（构造 parent 指向 control 目录的合法配置，partition 独立）→ 追加位不产生重复项。
- 既有 `test_partition_no_duplicate_control` / `test_dual_single_unchanged` 零修改全绿（dual/single 路径未动）。

## 完成判定

- `python -m pytest test_partition_dispatch.py -q`（multi-workers 包根）全绿
- `python -m pytest test_autopilot_config.py -q`（若存在 dispatch 相关既有用例）零修改全绿
- 输出 `[VERIFY] VC-001: expanded=[entries, control, parent], dedup=pass, legacy=unchanged`
