# Plan: mw-partition-parent-extended

> 目标：partition 模式 parent 语义修正——只读上下文 → 扩展可写工作区（读包含性并入 + 写路径零拦截回归锁定 + 措辞/golden 同步），dual/single 零回归。
> spec: `.agenticdoc/mw-partition-parent-extended/spec.md`（AC-001~006，指纹 b28ae1d8b531）
> design: `.agenticdoc/mw-partition-parent-extended/design.md`（D-001~D-007，VC-001~009）

## Stage 1 — Py 派发展开并入 parent（AC-001 / VC-001）

- 目标：conductor 路径 read_scope 展开包含 parent root（透明化），dual/single 零变化
- 改动：`autopilot/dispatch.py::_expand_read_scope`（partition 分支 control 追加后追加 parent，normcase 判重；docstring 红线翻转）+ `test_partition_dispatch.py`（`test_partition_anchors_at_partition_root` 断言翻转 + parent 判重新 case）
- 验证：`test_partition_dispatch.py` 全绿；`test_autopilot_config.py` / dispatch 相关既有用例零修改全绿
- 独立性：不依赖其它 stage；TS 侧未动时 union 未生效，但 Py 展开本身即完整行为（frontmatter 显式含 parent）

## Stage 2 — TS worker 侧 union（AC-002 / AC-003 / AC-004；VC-002~006）

- 目标：一切携带 read_scope 的 partition 任务（含 PM 窗口 TS 路径派发）在 worker 层把 parent root 并入允许集；deny 优先与空 scope 全拒不回退；写路径零拦截回归锁定
- 改动：`worker/read-scope.ts`（+`parentRootFromTaskContent` / +`applyParentRootUnion` 纯函数）+ `worker/worker-mode.ts`（wiring：重读 task.md 内容 + union，~3 行）+ `test/suite/autopilot-read-scope.test.ts`（新 describe：纯函数矩阵 + `startScopedWorker` 变体带 profile body 的 wiring 用例 + parent 路径 write/edit/bash 不拦截 + deny 优先用例）
- 验证：`node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-read-scope.test.ts`（coding-agent 包根）全绿；既有 describe 零修改
- 依赖：无（与 Stage 1 可并行，但建议串行：Stage 2 测试需要 profile 块——标签在 Stage 3 才改，本 stage 测试用现行 `Parent root:` 旧标签 + 兼容断言双形态）

## Stage 3 — 标签与措辞同步（AC-005 / VC-007、VC-008）

- 目标：profile 行标签 `Parent root (extended workspace, writable):` 双侧一致；mw.py 两处去 "read-only"
- 改动：`pm/task-dispatcher.ts::renderPartitionProfileBlock` + `mw_common.py::render_partition_profile_md`（标签行）+ `test/fixtures/partition-profile-block.golden.md`（Py golden）+ `test_partition_dispatch.py` 标签三触点（期望模板 :92 区、conductor 注入断言 :473 区）+ `agent-team-loop-profile-injection.test.ts`（:345 区标签断言）+ `mw.py` 两处文案（--parent 缺参报错 ~:1302、argparse help ~:2812）+ `test_mw_partition.py`（missing-parent 用例补 stderr 断言 "extended writable workspace"）
- 验证：`test_partition_dispatch.py`（含 golden parity 用例）+ `test_mw_partition.py` + TS profile-injection 用例全绿
- 依赖：Stage 2 的解析器为前缀匹配，本 stage 标签变更不需回改 Stage 2 代码；但 Stage 2 的 wiring 测试若断言了旧标签字面量则在本 stage 一并更新（写测试时直接断言双形态可避免）

## Stage 4 — 全量验证与零回归审计（AC-006 / VC-009）

- 目标：两侧全量测试 + check + 修改面审计 + dist 重建
- 动作：
  1. Py 全量（`packages/multi-workers` 既有测试入口）+ TS 相关套件全绿
  2. `npm run check` 0 error / 0 warning / 0 info
  3. 修改面审计：dual/single 既有用例零修改（git diff 核对）；partition 用例修改限于 Stage 1/3 触点
  4. argparse help 无 "read-only" 残留（grep 审计，VC-008 证据）
  5. bundle 重建 `packages/multi-workers/dist/extensions/agent-team-loop.js`
- 依赖：Stage 1~3 全部完成

## Stage 5 — verify 与结案（质检门禁）

- 目标：[VERIFY] VC-001~009 证据链落盘 `evidence/verify-run-<date>.md`，quality gate 复核，achieved.md + tasks 归档
- 依赖：Stage 4

## 任务清单

| Task | Stage | 内容 | ac_refs | vc_refs |
|------|-------|------|---------|---------|
| T-01-PY-EXPAND | 1 | dispatch.py 展开追加 parent + 测试翻转/判重 case | [AC-001] | [VC-001] |
| T-02-TS-UNION | 2 | read-scope.ts 两纯函数 + worker-mode wiring + union/deny/write 测试 | [AC-002, AC-003, AC-004] | [VC-002, VC-003, VC-004, VC-005, VC-006] |
| T-03-LABEL-WORDING | 3 | 双侧标签 + golden + 断言 + mw.py 文案 | [AC-005] | [VC-007, VC-008] |
| T-04-VERIFY-BASELINE | 4 | 全量测试 + check + 修改面审计 + dist 重建 | [AC-006] | [VC-009] |

执行顺序：T-01 → T-02 → T-03 → T-04（串行；T-01 与 T-02 理论可并行，体量小不值得并行开销）。
