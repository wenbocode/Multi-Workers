# T-08-docs-changelog-pitfalls

状态: done · 覆盖: AC-009, AC-010 · 依赖: T-03..T-07

## 目标

变更登记与教训沉淀，保证后续会话能查到契约。

## 步骤

1. `packages/multi-workers/CHANGELOG.md` `[Unreleased]`：`### Fixed`（advance 无界重试；L3 worker 崩溃被当作 below）、`### Added`（`advance_stall_ticks`；stalled approve 恢复语义；timeline `resume` / `l3-no-verdict` 事件）。
2. `packages/coding-agent/CHANGELOG.md` `[Unreleased]`：`### Added`（autopilot 监控分节 + 自动显示）。
3. `packages/multi-workers/README.md`（或对应 docs）：新增配置键 `advance_stall_ticks` 与 stalled 门禁 approve/reject 语义说明。
4. `.agenticdoc/_pitfalls.md`：追加「无界重试 + 无反馈」教训（现场：2242 次 / 2h35m 静默空转；F4 类别）。
5. 本 key 的 evidence/quality-gate-report 与 achieved.md 在 verify 阶段补齐。

## 验证

- `npm run check` 0/0/0。
- 两个 CHANGELOG 的 `[Unreleased]` 无重复小节（读全文后追加）。

## 执行记录

- 2026-09-23 00:10 完成。
- `packages/multi-workers/CHANGELOG.md` `[Unreleased]`：`### Added` 1 条（停滞守卫 + stalled approve 恢复 + 新事件类型）、`### Fixed` 2 条（无界 advance 重试；L3 worker 崩溃被当成 below）。
- `packages/coding-agent/CHANGELOG.md` `[Unreleased]` `### Added` 1 条（监控面板 autopilot 分节 + 自动显示 + config 镜像）。
- `packages/multi-workers/README.md`：新增「Autopilot 配置与停滞处置」节（配置键表含 `advance_stall_ticks`；approve=恢复一轮 / reject=closed-legacy；`resume`/`l3-no-verdict` 事件；面板行为）。
- `.agenticdoc/_pitfalls.md`：新增 **P-009**（P-001..P-008 后继续编号，CRLF 保持）。
- 验证：`npm run check` 全绿（含 biome）；两个 CHANGELOG 的 `[Unreleased]` 追加后无重复小节。
