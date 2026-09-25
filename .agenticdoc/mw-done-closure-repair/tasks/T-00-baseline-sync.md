# T-00-baseline-sync

状态: done（2026-09-25） · 覆盖: 前置门禁（全部任务） · 依赖: -

产出：evidence/plan-baseline-drift-map-20260925.md（基线 commit a0c36fcce，结构性论断三条 ✅，锄点映射表，9 return 点现行行号锁定）

## 目标

并发基线对齐：另一会话正在 `conductor.py` 实现 L3 verdict source fallback（评审时 +93/-30 未提交）。本任务确认其已提交、工作树净空，然后以**现行树**重定位 design 全部 conductor 锚点并记录漂移映射，作为 T-03..T-05 的实施基准。

## 输入

- dcr-review 报告发现 5 的漂移快照：调用点 1229→:1292、def 1319→:1382、mark_stalled 1835→:1898、in-flight 守卫 1188-1190→:1245-1247、meets 分支 1225-1230→:1288-1294（评审时快照，提交后可能再变）
- design.md D-005 分支 4 注记：meets∧`l3_source is None` 新回退归入 below 既有路径

## 步骤

1. `git status --short packages/multi-workers/autopilot/conductor.py` 非净空 → 停，报告用户协调；净空 → 继续。
2. 重定位锚点清单（逐条 file:line + 3 行上下文摘录）：`_verify_loop` def / in-flight 双前缀守卫 / `l3_limit` 赋值 / no-verdict 与 below 的预算先例 / meets 分支 / `_done_transaction` def + 9 return 点 + step-2 覆盖守卫 + step-5 advance / `mark_stalled` 四件套 / `_apply_stalled_rejections` / `_mark_key_done`。
3. 复核结构性论断三条仍成立：唯一调用点、meets 分支无预算检查、`_done_transaction` 步骤序不变。
4. 写 `evidence/plan-baseline-drift-map-20260925.md`（旧锚点→新锚点映射表 + 论断复核结论）。

## 验证

- 漂移映射文档存在且每条锚点带现行行号；三条结构性论断逐条 ✅/❌（❌ 即回 design 修订）。
