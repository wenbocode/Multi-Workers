# Task 011: 全量回归基线对照

- Stage: S4
- 代码状态: 代码完成（含 2 条 biome info 修复）
- 验证状态: 验证通过（2026-09-11，check 0/0/0 + test.sh 全量 + 可比口径基线对照 new-failures=0；ai/evals/server 口径外观察项已记录，证据 evidence/runs/011-regression-baseline.md）
- ac_refs: [AC-001]
- vc_refs: [VC-002]
- pattern_refs: []
- deps: [001, 002, 003, 004, 005, 006, 007, 008, 009, 010]
- 预估: ~1h

## 交付物

- `npm run check` 全量输出（0 error/0 warning/0 info，AGENTS.md 要求不 tail）
- `./test.sh`（仓库根，非 e2e 全量）输出
- Windows 89 例环境基线对照表（agent 13 + coding-agent 76，AGENTS.md 2026-09-10 分类）：逐例标注 本次是否仍失败 / 是否新增
- 新增失败=0 判定；若出现新失败逐例归因（环境噪声 vs 本 key 回归），回归项回开对应 task

## AC 摘录（spec.md §3）

- AC-001: 单目录模式零回归——check 干净 + 测试相对基线无新增失败

## 验证方式（VC 断言）

- VC-002: `[VERIFY] VC-002: check-clean=true new-failures=0`
- 证据落盘: `evidence/runs/011-regression-baseline.md`（check 全文 + test 输出 + 基线对照表）

## 依赖与阻塞

- 依赖 001-010 全部完成（回归对象是全量改动）。
