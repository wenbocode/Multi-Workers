# Evidence Requirement: mw-worker-visibility-gate

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-worker-visibility-gate/spec.md` |
| spec_locked_at | 2026-09-23T09:45:00Z |
| ac_ids | AC-001 … AC-013（13 条，见 spec §3） |
| vc_ids | VC-001 … VC-013（13 条，见 design §7） |
| generated_at | 2026-09-23T09:55:00Z |

## 证据分层口径

- **L0（静态）**：文档/字段存在性（AC-013）。
- **L1（局部）**：针对 `phase-docs.ts` / `pm-state-claim.ts` 的纯函数单测 + 通过工具入口（`dispatch_worker`/`switch_key`/`renderWatchLines`）的集成断言。
- **L2（E2E）**：真模型冒烟（本 key 可选，若做则记录 task key 与产物路径）。

## AC → 证据需求

| AC | 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|----|----------|----------|----------|-----------|
| AC-001 | `[VERIFY] VC-001` | 工具入口集成断言（构造 SPEC 相位 + design 缺失的 key） | 放行 + task.md 存在 | 单次 PASS |
| AC-002 | `[VERIFY] VC-002` | 同上（DESIGN 相位 + design.md 缺失） | blocked + 1 条 design 缺项 + 无 task 目录 | 单次 PASS |
| AC-003 | `[VERIFY] VC-003` | 同上（DESIGN + design 证据 0） | blocked + design 证据缺项 1 条 | 单次 PASS |
| AC-004 | `[VERIFY] VC-004` | 单测（phase 取值 4 种） | tier=spec、design 缺项 0 | 4 个取值全过 |
| AC-005 | `[VERIFY] VC-005` | 单测 + 工具入口 | 缺项列表 design 侧为 0 | 单次 PASS |
| AC-006 | `[VERIFY] VC-006` | 面板渲染单测 | 1 行聚合、含 owner 与计数、≤110 | 单次 PASS |
| AC-007 | `[VERIFY] VC-007` | 面板渲染单测（未传参数） | 0 行 + 与基线逐行相同（同文件基线断言） | 单次 PASS |
| AC-008 | `[VERIFY] VC-008` | 面板渲染单测（failed/未 ack） | 终态计入 | 单次 PASS |
| AC-009 | `[VERIFY] VC-009` | 面板渲染单测（risk=high 检查点） | 含 `risk=high` 与数量 | 单次 PASS |
| AC-010 | `[VERIFY] VC-010` | 集成断言（走 `takeOverKey` 真路径后读两处） | Claim-Id 与索引列逐字相等、模板未变 | 单次 PASS |
| AC-011 | `[VERIFY] VC-011` | 集成断言（手改掉 Claim-Id 行） | claim 成功 + 1 warning + 文件未重建 | 单次 PASS |
| AC-012 | `[VERIFY] VC-012` | 工具入口集成断言（SPEC + type=coding） | 不被相位门禁拒（回归） | 单次 PASS |
| AC-013 | `[VERIFY] VC-013` | 静态检查（`_pitfalls.md` 文本） | 三个口径关键词齐全 | 单次 PASS |

## 质检门禁使用说明

- 本文件由 `/quality-gate` 读取，对每个 AC/VC 逐条核查证据充分性；证据行必须能在**原始输出**里 grep 到（P-006）。
- 本 key 无 L2 真模型冒烟（改造面为门禁/面板/claim 同步三处纯 TS 逻辑，L1 集成断言已走真实工具入口）；若质检判定需要 L2，按 design §6 的 F4/F5 补一次真派发场景。
