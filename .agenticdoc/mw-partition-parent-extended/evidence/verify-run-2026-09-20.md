# Verify Run: mw-partition-parent-extended（2026-09-20）

> 执行方式：PM 本窗口直执（T-01~T-04 串行）；全部命令与输出在本 session 产生。

## VC 证据链

- [VERIFY] VC-001: expanded=[entries, control, parent], dedup=pass, legacy=unchanged
  - 来源：`test_partition_dispatch.py::TestExpandReadScopePartition`（断言翻转 + 新增 `test_partition_parent_dedup`），`python -m pytest test_partition_dispatch.py -q -k "ExpandReadScope or duplicate" -s` → 4 passed，两行 [VERIFY] VC-001 输出（expanded/dedup）
- [VERIFY] VC-002: parentRoot=P (old+new label), null (no mode/no line/dual)
  - 来源：`autopilot-read-scope.test.ts` 新 describe 纯函数矩阵
- [VERIFY] VC-003: union=appended (non-empty scope), unchanged (undefined/null/empty)
  - 来源：同上（`applyParentRootUnion` 矩阵：非空 scope 追加；undefined/deny-only(scope=null)/空 scope([]) 原引用返回）
- [VERIFY] VC-004: parent_read=allowed, outside=blocked; VC-006: write/edit/bash=unintercepted
  - 来源：wiring 用例（task.md 带 v2 profile body + read_scope；parent 内 read 放行、scope 外 block rule=scope、parent 路径 write/edit/bash 三工具零拦截、output.md 无对应 rejection）
- [VERIFY] VC-005: parent_deny=blocked (rule=deny-glob), parent_ok=allowed
  - 来源：wiring 用例（deny_globs `**/DerivedDataCache/**` + union 并存；annotated 标签形态过 wiring）
- [VERIFY] VC-007: label=extended-workspace, parity=byte-identical
  - 来源：`test_partition_dispatch.py::test_partition_profile_matches_ts_golden`（golden fixture 标签更新后双侧逐字节一致）；TS `agent-team-loop-profile-injection.test.ts` 标签断言
- [VERIFY] VC-008: read_only_residual=0, wording=extended-writable-workspace
  - 来源：`test_mw_partition.py::test_set_missing_parent_rejected`（capsys stderr 断言：不含 "read-only"、含 "extended writable workspace"）+ `mw.py` grep 审计（残留 2 处 "read-only" 均为无关语义：env 覆盖说明 :1293、rmtree 注释 :1824）
- [VERIFY] VC-009: legacy=green-zero-mod, partition_diff=bounded, check=0/0/0-on-key-surface
  - Py 全量：`python -m pytest -q`（packages/multi-workers）→ **678 passed, 8 deselected, 0 failed**
  - TS 目标套件：agent-team-loop 全家族 12 文件 → **433 passed | 1 skipped, 0 failed**
  - `npm run check`：biome / check:pinned-deps / check:ts-imports / check:shrinkwrap / check:install-lock:coding-agent 全部 PASS；`tsgo --noEmit` 14 个错误**全部位于 packages/ai**（并发 session 在途改动：`packages/ai/src/providers/kimi-coding.models.ts` 处于删除态 + models.generated.ts 修改中），**本 key 触达面（packages/coding-agent + packages/multi-workers）0 error / 0 warning / 0 info**——非本 key 回归，不予触碰（AGENTS.md 多 session 规则）
  - 修改面审计（git diff hunk 清单）：
    - `autopilot-read-scope.test.ts`：import 块 +2 行、文件尾新 describe +149 行（既有 describe 零修改）
    - `agent-team-loop-profile-injection.test.ts`：:345 标签断言 1 行（partition 用例）
    - `test_partition_dispatch.py`：:92 模板标签、:473 注入断言标签、:613 展开翻转+判重 case（全部 partition 用例）
    - `test_mw_partition.py`：missing-parent 用例 capsys + stderr 断言（partition CLI 用例）
    - dual/single 既有用例：**零修改**
  - bundle 重建：`build-extension.sh` → Built + Self-check OK（default export loads as a function (activate)）；bundle 含 parentRootFromTaskContent / applyParentRootUnion / 新标签

## 源码触达面（8 文件 +219/-16）

- `packages/multi-workers/autopilot/dispatch.py`（_expand_read_scope partition 分支 +parent 追加）
- `packages/multi-workers/mw.py`（--parent 报错 + argparse help 措辞）
- `packages/multi-workers/mw_common.py`（render_partition_profile_md 标签）
- `packages/coding-agent/.../worker/read-scope.ts`（+parentRootFromTaskContent / +applyParentRootUnion）
- `packages/coding-agent/.../worker/worker-mode.ts`（wiring union）
- `packages/coding-agent/.../pm/task-dispatcher.ts`（renderPartitionProfileBlock 标签）
- 测试/夹具 4 文件（见上审计）

## 环境备注

- `packages/multi-workers/dist/extensions/agent-team-loop.js` 在本 key 重建前已携带 mw-worker-tree-kill 的未提交 4 行 diff（exit try/catch）——另一 session 已完成工作，未触碰
- `packages/ai` kimi-coding WIP 为并发 session 在途，未触碰
- 生效时机：JS bundle 对新 spawn 的 worker 即时生效；Py 侧（dispatch.py/mw_common.py）在 `mw serve` 下次重启后生效（serve 进程内存中为旧模块）
