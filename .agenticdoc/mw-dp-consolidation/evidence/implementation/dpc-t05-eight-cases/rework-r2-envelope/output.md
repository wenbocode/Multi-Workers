# T05-R2-envelope — 交付摘要

## 结论

两根因已在声明写面内修完并局部验证绿；原整文件 suite 仍 12 失败（历史 monitor/history/DOM，owner T27/T28/T29），整体 L2/QG/签收未做，终态待 PM 复验/ack。

- 模板：`decide_book_template.json` = `decision_book.scaffold_book` 派生的八入口 schema3 骨架（8 本、无 `meta`/`state`、全占位符、`check_book` 仍拒绝）。
- 时间：`CASE_PREPARED_AT` = `2026-10-27T13:45:28+00:00`（一次真实读取并记录、明确 UTC、冻结常量、不读 wall-clock、不回填 run-start；明确只是合成 fixture 编写时刻，不是真实准备/授权证据）；8 case 各只改这一行。
- 验收状态：实现完成；focused 2 passed/rc=0；生产 gate 8/8 零 issue、逐 choice-basis 零 issue、8 case 私有 out 逐字节相等、四旧 case 不变、14 pyc 不变、28 原测试函数 AST/source/lineno 全同（纯追加 2 个）；整文件 `12 failed, 18 passed` rc=1。

## 证据

证据根 `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\evidence\implementation\dpc-t05-eight-cases\rework-r2-envelope\`：

- 入场：`readonly-protection.json`（写面 12 条 = 11 产品 + 自己的 `rework-r2-envelope\**`；`card_sha256` 与 task.md 头一致）。
- before：`before-metadata.json`、`before-bytes\**`、`test-functions-before.json`、`inventory-before.json`(1891)、`pyc-before.json`(14)、`fresh-before-check.json`（与 PM pre-dispatch 逐条相同、T10 五文件相同、四旧 case 相同）。
- 红：`logs\red-two-root-causes.*` → `2 failed, 28 deselected`, rc=1（模板仍是 `dp3-worker-clarify/dp6-qg-verdict`；`prepared_at 2026-10-27T20:56:00+00:00 is in the future`）。
- 绿：`logs\focused-green-window.*` → `2 passed`, rc=0；`product-check.json` → 8/8 零 issue、`prepared_at_future_cases: []`、模板 8 本 schema3、四旧 case 不变；`logs\generate-private-out-final.*` rc=0。
- 整文件：`logs\full-workbench-suite-window.*` → `12 failed, 18 passed`, rc=1，`T10_dependency_window_stable: true`，12 项与 T05 基线 `remaining_failures` 同名。
- 变更面：`changed-files.json`（1891→1891，changed=11 个面内产品，`outside_declared_face: []`，`pyc_unchanged: true`）、`full-diff.patch`、`test-function-delta.json`。
- 时间记录：`prepared-at-record.json`。

## 改动清单

产品（完整 canonical 副本路径）：`...\implementation-worktree\packages\multi-workers\scripts\build_decide_cases.py`、`...\decide_book_template.json`、`...\test_decision_context_workbench.py`、`...\decide_cases\{dp-w-type,dp-pm-steer,dp-w-check-task,dp-QG,dp-gate-approve,dp-sign-key,dp-auto,dp-route}.json`（sha/bytes 见 `report.md` 与 `changed-files.json`）。

证据：本目录下 `report.md`、`output.md`、`readonly-protection.json`、`before-metadata.json`、`before-bytes\**`、`test-functions-before|after.json`、`test-function-delta.json`、`inventory-before|after.json`、`pyc-before|after.json`、`fresh-before-check.json`、`prepared-at-record.json`、`product-check.json`、`case-install.json`、`changed-files.json`、`full-diff.patch`、`logs\**`、`tools\**`、`fixture\**`。

## 残留与未验证

- 原整文件 12 项失败未修（历史 owner，未弱化）；未跑其它 test/CLI/服务/真实 provider/`npm run check`。
- 未做 S2/L2/check/reviews/QG/signoff；PM 需用原 `t05-pm-handoff-20261027\probe.py`（未改）在新证据目录重跑复验。
- 真实浏览器/真实模型端到端、monitor 固定表向八入口迁移（T28 面）未做。
- 红那一轮无 T10 依赖窗口记录（窗口工具后置）；focused 与整文件两轮窗口稳定。
- 14 pyc（含原 1 历史漂移）保持原状，未清理/回填/重取基线。
- 过程偏差：新模板测试第一次绿的断言假设（issue code 顺序）与 `dp-auto` 早返回不符，仅修正该新测试自身断言（原 28 函数 AST/source/lineno/assert 数不变）。

## 上下文来源

`tasks\isolated\T05-eight-cases-r2-envelope.md`（写面）、`tasks\isolated\T05-eight-cases-r2.md`（业务）、`workers\dpc-t05-eight-cases-r2-envelope\task.md`（派发头）、`.agenticdoc\goal.md:5`、`spec.md:128`、`design.md:201`、PM `t05-pm-handoff-20261027\{probe.json,check.json,report.md}`、`t05-r2-envelope-pre-dispatch-20261027\{before-metadata.json,T10-products-protection.json}`、原 T05/坏 R2 证据（只读）、只读契约 `decision_book.py`/`decision_points.py`。
