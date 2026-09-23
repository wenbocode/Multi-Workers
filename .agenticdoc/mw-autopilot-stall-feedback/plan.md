# Plan: mw-autopilot-stall-feedback

> Key: mw-autopilot-stall-feedback · 阶段: plan · 2026-09-22
> 上游: spec.md（AC-001..AC-013）· design.md（D-1..D-9）· 证据: evidence/research/*
> 执行方式：PM 窗口直接实施（本窗口持有 key claim，conductor 会 skip 该 key；不需派 worker）

## 任务表

| 任务 | 目标 | 产出 | 覆盖 AC | 依赖 | 验证 |
|------|------|------|---------|------|------|
| T-01-e2feature-site-repair | 现场止损：pm-state Phase 行规范化 + dispatch.yml review 模型 id 修正 | 两个字节级修复脚本 + 证据节 | AC-001 | - | timeline `execute->verify exit=0`（已完成，21:35:41） |
| T-02-advance-failure-classify | advance 失败分类 + timeline 机器可读载荷 + 尾部 streak 派生 | `timeline.tail_events`、`_classify_advance_failure`、`_advance_failure_streak` | AC-002, AC-005 | T-01 | 单测（分类 4+1、streak 打断规则） |
| T-03-advance-stall-freeze | 达阈值 → `mark_stalled` 升级 + 冻结；未达阈值照旧重试 | 三个 advance 调用点的接入 | AC-003, AC-005 | T-02 | 行为单测（达/未达阈值、幂等、无追加 advance） |
| T-04-stalled-approve-resume | stalled 门禁 approve → 复位 `running` + 恢复一轮额度（L2/exec/L3/repair） | `_apply_stalled_approvals`、`_resume_credits` | AC-004, AC-013 | T-03 | 行为单测（复位、恰好一轮、reject 不变、幂等） |
| T-05-l3-no-verdict | L3 worker 崩溃与 reviewer `below` 分离 | `_l3_round_verdict` + stall reason 携带 worker 状态 | AC-012 | T-04 | 行为单测（崩溃轮不派 repair、原因分类正确） |
| T-06-monitor-autopilot-panel | 面板增加 autopilot 分节：tick 新鲜度 / 槽位 / 每 key 状态 / 停滞连击 / 门禁 | TS `deriveAutopilotPanel` + `renderMonitorLines` 扩展 | AC-006, AC-007 | T-02 | TS 单测（降级、STALE、截断）+ `npm run check` |
| T-07-monitor-autoshow | autopilot enabled 项目自动显示面板（可关闭） | `console.ts` 接线 | AC-008 | T-06 | TS 单测 + 手工 tmux 验证（若扩展已重载） |
| T-08-docs-changelog-pitfalls | 变更登记与教训沉淀 | 两个 CHANGELOG、README、`_pitfalls.md` | AC-009, AC-010 | T-03..T-07 | `npm run check`；文档 diff 自检 |
| T-09-live-recovery-evidence | 用正式路径恢复 E2Feature K2 → K3 解锁，并留证 | `evidence/e2e-recovery-20260922.md` | AC-001, AC-004, AC-011 | T-03..T-05 | timeline `verify->done exit=0`、key-status done、K3 dispatch |

## 顺序与门禁

1. T-01 已在 spec 阶段完成（现场止血，独立于框架改动）。
2. T-02 → T-03 → T-04 → T-05 严格串行（同一控制流，逐个补测试）。
3. T-06 → T-07 依赖 T-02 的事件契约（分类载荷 + streak 规则）。
4. T-09 需要 T-03..T-05 生效，并且必须重启 E2Feature 的 `mw serve`（conductor 重载新代码）后才执行；`dist/` 重建与扩展加载验证受并发 key 限制，未验证即记录（AC-011）。

## 验证口径

- Python：`packages/multi-workers` 下 `node ../../node_modules/vitest/dist/cli.js` 不适用；用 `pytest test_autopilot_*.py`（package 根目录），对照 Windows 已知基线。
- TS：`npm run check`（0 error/warning/info）+ 相关 vitest 用例。
- 现场：只看 timeline 与 `_roadmap.md` 的文件事实，不靠日志口述。

## 风险登记

| 风险 | 缓解 |
|------|------|
| 阈值过激（20s 即升级） | `advance_stall_ticks` 可配；升级可 approve 恢复一轮 |
| 新增 config 键与旧 TS 读取器不兼容 | Python/TS 同批次；旧文件缺键取默认（T-06 验证读取器宽松度） |
| E2Feature serve 重启会加载并发 key 的未提交改动 | 重启前 `git status` + `py_compile` 校验被 import 的模块 |
| `dist/` 重建与并发 key 冲突 | 推迟到对方提交后；未验证记 AC-011 |
