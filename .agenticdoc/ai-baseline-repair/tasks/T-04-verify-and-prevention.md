# T-04: 验证链 + 运行时失败 + 预防文档

> Key: ai-baseline-repair | 依赖: T-01/02/03 | 模式: PM 直执 | AC refs: AC-005, AC-006, AC-008 | VC refs: VC-001, VC-002, VC-003, VC-008, VC-009

## 目标

D-006 + D-008：全链验证收口 + 运行时 8 失败处置 + 预防约定落文档。

## 步骤

1. `npx tsgo --noEmit` = 0 错；`npm run check` exit 0（VC-001/002）
2. packages/ai 套件 `node ../../node_modules/vitest/dist/cli.js --run`（包根）；8 个预存运行时失败逐个处置：修复 / 同根自愈留痕 / 超 GC-A4 面升级用户决策（R-4）（VC-003）
3. agent-team-loop 基线复跑：TS 121/121 + Python 365 passed（零回归证据）
4. biome 触碰文件零告警 + diff 范围 = 声明面（VC-009）
5. 预防约定：`packages/ai/README.md` 加节（fork 特有测试禁硬编码版本号 ID；共享文件以 upstream 为同步参照）+ `packages/ai/CHANGELOG.md` 条目（VC-008）

## 验收

- [x] VC-001/002：tsgo 0 错 + npm run check exit 0
- [x] VC-003：ai 套件 838 passed / 0 failed（基线 7~8 failed → 0，逐个处置见 evidence §3）
- [x] 扩展域/Python 基线：123/123 + 367 passed（含其他会话在飞改动，零失败）
- [x] VC-008：README「Model Catalog and Test Hygiene」节 + CHANGELOG Unreleased Fixed 3 条
- [x] VC-009：diff 面 = 声明面 17 文件；biome 零告警

## 验证状态

验收通过（2026-09-10）：全链证据 evidence/runs/regression-2026-09-10.md §1；运行时失败逐个留痕 §3；上游镜像跳过清单 §5
