# Quality Report: mw-crosskey-risk-escalation

> 日期: 2026-09-24 | Phase: VERIFY → DONE
> 结论: ✅ 通过（4/4 AC 有证据，0 无证据，1 项交叉项为已登记的接受项）

## 1. 交付面

| # | 文件 | 类型 | 规模 |
|---|------|------|------|
| 1 | `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | 改 | +19 / -3（D-101 过滤条件 + D-102 `workerLabel` 文案 + 注释修正） |
| 2 | `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | 改 | +159 / -0（纯追加 VC-001/002/003 三个用例） |
| 3 | `packages/coding-agent/CHANGELOG.md` | 改 | `[Unreleased]` 首段 `### Added` 追加 1 条（CRLF 保留 5408→5409，bare LF=0） |

不含 `dist/**`（收口时统一重建）、不含任何 Python、不含框架仓库。

## 2. AC 勾销表

| AC | 结论 | 关键证据 |
|----|------|----------|
| AC-001 | PASS | `VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0`（文本含 `'t-xkey'（owner key=key-b）`） |
| AC-002 | PASS | `VC-002: undefined_alerts=0 empty_set_alerts=0` + 既有反例用例独立重跑通过（M-2 变异使其变红，证明守卫有效） |
| AC-003 | PASS | `VC-003: low_alerts=0 high_alerts=1 dup=0` |
| AC-004 | PASS | `VC-004: watched_key_alerts=1 trigger_turn=true dup=0` + 机械字节证据 `text_byte_identical=true`（HEAD vs current，同夹具 sha256 全等，533 bytes） |

## 3. 任务与相位

| 相位 | 产物 |
|------|------|
| SPEC | `spec.md`（§0 GC-1~GC-5 + 预期收益、AC-001~004、§5 记忆前馈）+ `evidence/research/spec-crosskey-escalation-baseline-2026-09-23.md`（F1~F4） |
| DESIGN | `design.md`（D-101~D-104、§7 VC 表、mermaid classDiagram+graph TD）+ `evidence/research/design-crosskey-escalation-alternatives-2026-09-23.md` |
| PLAN / TASKS | `plan.md`（并行性分析：单点逻辑 ⇒ 1 实现 worker + PM 文档 + 1 验证 worker）、`tasks/T-1`、`tasks/T-3` |
| EXECUTE | T-1（worker `mwcre-t1-crosskey-escalation`，10m/59 tools）+ T-2（PM 直执 CHANGELOG） |
| VERIFY | T-3（worker `mwcre-t3-verify`，28m/79 tools）：VC-001~004 独立复现 + M-1/M-2/M-3 变异 |

门禁链：init → DESIGN → PLAN → TASKS → EXECUTE → VERIFY → DONE（`audit_phase` 四门 PASS）。

## 4. 独立验证与反例

- 独立验证：T-3 自建探针（系统临时目录，真实 `startWorkerPollLoop` + 自建 fake pi），不采信 T-1 断言 → 4/4 VC 与 T-1 数值一致，0 FAIL。
- 变异反例：M-1（去 `owned` 支）→ VC-001 红；M-2（全局广播）→ VC-002 红 + 既有反例用例红；M-3（`?? true`）→ VC-002 红。三次复原后 sha256 == H0 `C261B903…ECCC3`（PM 独立复核该 sha256）。
- PM 复核：读源码 diff（仅条件 + 文案）、复跑 183/183、确认测试文件 159+/0-、确认无临时用例残留、`npm run check` 在 T-1/T-3 两处各自 EXIT=0。

## 5. 遗留（去向明确）

| ID | 内容 | 去向 |
|----|------|------|
| R-1 | `dispatchedTaskKeys` 进程内语义 → 窗口重启后异地高风险 worker 不再主动升级（面板聚合行仍可见） | 接受不处理；未决 Q-1（是否持久化）保留 |
| R-2 | 更早会话派发的异地高风险 worker 仅被动可见 | 同 R-1（面板 `risk=high:K` 覆盖） |
| R-3 | 跨窗口/跨会话的升级去重（同一 worker 在多窗口同时被 watch 的情形） | 未决（本 key 不改窗口边界语义） |
| — | `mw build --install` + 提交推送 | 收口步骤执行（bundle 需重启窗口生效） |
