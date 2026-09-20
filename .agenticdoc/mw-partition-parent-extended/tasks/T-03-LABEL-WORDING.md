# Task T-03-LABEL-WORDING: 标签与措辞同步

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM（本窗口）或 worker
- ac_refs: [AC-005]
- vc_refs: [VC-007, VC-008]
- pattern_refs: []

## 描述

新标签统一为 `Parent root (extended workspace, writable):`（`:` 后接归一路径）。

### 源码（4 处）

1. `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts` `renderPartitionProfileBlock`（:135 区）：`` `Parent root: ${config.parentRoot}` `` → `` `Parent root (extended workspace, writable): ${config.parentRoot}` ``。
2. `packages/multi-workers/mw_common.py` `render_partition_profile_md`（:2239 区）：`f"Parent root: {config['parent_root']}"` → `f"Parent root (extended workspace, writable): {config['parent_root']}"`。
3. `packages/multi-workers/mw.py` `--parent` 缺参报错（~:1302）："read-only context for the partition" → "extended writable workspace for the partition"。
4. `packages/multi-workers/mw.py` argparse help（~:2812）："Parent project root (required; read-only context for the partition)" → "Parent project root (required; extended writable workspace for the partition)"。

两侧渲染输出必须逐字节一致（既有 golden parity 用例锁定）。

### 测试/夹具（5 处触点）

5. `packages/multi-workers/test/fixtures/partition-profile-block.golden.md`（:6）：标签行。
6. `packages/multi-workers/test_partition_dispatch.py`：期望 profile 模板中的 `Parent root: {parent}`（:92 区）与 conductor 注入断言 `f"Parent root: {parent.resolve()}"`（:473 区）→ 新标签。
7. `packages/coding-agent/test/extensions/agent-team-loop-profile-injection.test.ts`（:345 区）：`` `Parent root: ${dirs.parent}` `` → 新标签。
8. `packages/multi-workers/test_mw_partition.py` missing-parent 用例（~:188 区）：补 stderr 断言含 "extended writable workspace"（capsys）。
9. T-02 的 wiring 测试若已按双形态断言则零回改；若只断言旧标签则同步。

### 审计（VC-008 证据）

- `mw.py` 全文 grep "read-only"：partition 相关仅余 0 处（无关命中除外，如 worker liveness 注释属 mw_common.py 不在范围）。

## 完成判定

- `python -m pytest test_partition_dispatch.py test_mw_partition.py -q` 全绿（含 golden parity）
- TS profile-injection 用例全绿
- 输出 `[VERIFY] VC-007: label=extended-workspace, parity=byte-identical`、`[VERIFY] VC-008: read_only_residual=0`
