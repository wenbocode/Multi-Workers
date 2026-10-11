# Quality Gate Report: mw-console-title-clobber

**时间**: 2026-10-11 23:25 +08:00
**触发**: 手动（PM 收口 `advance_phase … done` 前的质检门）
**范围**: 本 key 全量（trivial-fix fast path）
**执行形态**: PM 直执（无 review worker）

## 前置说明（本 key 与标准 QG 的差异）

本 key 走 mini-spec 快径，**无 `design.md` / `evidence-requirement.md` / `tasks/`**，标准 QG 的前置门禁
（AC→VC 映射、ac_fingerprint、baseline 目录）不适用。问题清单按 `workflow-quality-gate.md` Step 2 的机械
生成口径，由 `mini-spec.md` 的 **AC-1 / AC-2 / AC-3 / VC-1** 生成，另加 1 条交叉问题（CLI 相关测试回归）。

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-1 | win32 下探针 spawn 携带 `creationflags = CREATE_NO_WINDOW`；非 win32 不携带，且真实 spawn 路径透传 kwargs | ✅ 充分 | `evidence/probe-flags-20261011.txt`（`78 passed`，含 `[VERIFY] AC-1: probe_creationflags=134217728 platform=win32`）+ `test_common.py::test_probe_child_isolated_from_the_parent_console` | 134217728 = 0x08000000；测试同时断言 `linux`/`darwin` 返回 `{}` 且假 `run` seam 收到同一 kwargs |
| Q-AC-2 | 端到端：哨兵标题下 `mw model show` 不再改标题；旧调用形态仍会改（负向对照） | ✅ 充分 | `evidence/e2e-sentinel-20261011.txt` 三行：A `pi --list-models`（旧调用形态）= CLOBBERED→`pi`；B `_probe_model_rows()`（修后、真实 spawn、rows=31）= safe；C `mw.py model show --project <repo>`（用户可见命令）= safe | 哨兵法：同一控制台、同一子命令，唯一变量是 spawn 方式 / 源码版本 |
| Q-AC-3 | pi 侧：`process.title` 被 `process.stdout.isTTY` 包裹；管道 stdout 不再改标题、交互运行不变 | ✅ 充分 | 同文件 A'/B'：A' = HEAD 版 `cli.ts` 拷贝（改前，管道 stdout）= CLOBBERED→`pi`；B' = 修后 `src/cli.ts`（管道 stdout）= safe；`temp HEAD copy removed … exists=False`；代码锚点 `packages/coding-agent/src/cli.ts:12-20` | A' 是同一份源码的前后对照，排除了"dist 陈旧"这一混杂因素（临时拷贝在脚本 finally 里删除） |
| Q-VC-1 | 最小面：不加事件类型/配置项，非 AC 行为不变；全量检查全绿 | ✅ 充分 | `evidence/check-20261011.txt`（`npm run check` exit=0：biome `Checked 1119 files … No fixes applied`、pinned-deps、ts-imports、shrinkwrap、install-lock、`tsgo --noEmit` 无输出、browser-smoke 全过）+ `git diff --stat` = 3 文件（实现 2 处，其余为注释与测试） | 未改 dist/CHANGELOG（D-002） |
| Q-X-1（交叉派生） | CLI 入口相关的既有测试是否回归 | ✅ 充分 | `evidence/ts-cli-tests-with-change-20261011.txt`（7 文件：`1 failed | 6 passed`，`3 failed | 82 passed`）对照 `evidence/ts-cli-tests-baseline-head-20261011.txt`（把 `cli.ts` 临时换回 HEAD 版重跑同一失败文件：`3 failed | 24 passed`） | 3 个失败（`test/package-command-paths.test.ts` 的 `pi update` 自更新路径断言）在改前同样失败 ⇒ 环境基线，非本改动引入；`cli.ts` 已按 sha256 还原（`match=True`） |

## 汇总

- **总问题数**: 5
- **通过（充分）**: 5（100%）
- **有条件通过（不足）**: 0
- **未通过（无证据）**: 0

**质检结论**: ✅ 通过

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|------|------|---------|---------|
| —（无） | — | — | — |

## 二次印证结论

- 检查 1（spec 中每个约束是否被覆盖）：本 key 无性能/安全类约束；平台约束（win32）由 Q-AC-1 / Q-AC-3 覆盖，
  非 win32 分支由 Q-AC-1 的 `linux`/`darwin` 断言覆盖。
- 检查 2（design Function Flow 每个节点是否有 Q）：快径无 design.md → N/A。
- 检查 3（Coverage Matrix 异常路径行）：异常路径 = ① 子进程仍继承控制台（旧调用形态 A / A' 实测仍 CLOBBERED，
  证明对照有效）② 非 win32 行为漂移（Q-AC-1 分支断言）——均有证据。
- 检查 4（task 的 vc_refs 空绑定）：无 tasks/（PM 直执）→ N/A。

**结论：无遗漏问题。**

## 范围外（已登记，不在本次质检判定内）

1. `interactive-mode.ts` 的"扩展命令结束后恢复标题"路径（D-001：需在 core 事件层加钩子，改动面大；
   本轮以"源头不让改"替代"事后恢复"）。
2. 其它 CLI（codex / claude）探针的同类 spawn 隔离。
3. dist/bundle 重建与运行时切换（`/mw build` + `/mw restart`，由用户执行）；不新增 CHANGELOG 条目（D-002）。

以上不影响本 key 的 5 条问题判定。
