# T-09-live-recovery-evidence

状态: done · 覆盖: AC-001, AC-004, AC-011 · 依赖: T-03..T-05

## 目标

用**正式路径**（无临时配置改动）恢复 E2Feature 的 K2 `feature-params-service`，证明停滞自愈闭环在真实现场成立：approve stalled 门禁 → 复位 + 恢复一轮 → L3 → done → K3 解锁。

## 步骤

1. 重启前检查：E2Feature serve（`H:\git\E2Feature\.mw\serve.meta`）的 code_dir；`git status` 确认并发 key 的未提交文件已 `py_compile` 通过（serve 会 import 它们）。
2. 重启 E2Feature 的 `mw serve`（加载本 key 的 conductor/config 改动）；确认 conductor PID 变化、心跳恢复。
3. 人工 approve `gate-0002`（`kind=stalled`，key=`feature-params-service`）：改写门禁文件 `status: approved` + `answered_at/answered_by`（TS 命令或手工等价）。
4. 观察（文件事实）：
   - timeline `gate-answered … approved → feature-params-service running` + `resume`；
   - `_roadmap.md` `key-status: feature-params-service=running`；
   - L3 派发（`l3-a3`，reviewer 模型已修正）→ 若 worker 崩溃则应为 `l3-no-verdict` 而非 repair；
   - `verify->done exit=0`、key-status `done`、`_index.parallel` phase `DONE`；
   - K3 `feature-gui-backend` 随后被派发（依赖 K2=done）。
5. 写 `evidence/e2e-recovery-20260922.md`：时间线表 + 关键事件原文 + key-status 前后对照。

## 验证

- 上述五条均为文件事实（timeline / `_roadmap.md` / `_index.parallel` / `_workers.parallel`），不靠口述。
- 若某一步失败，记录失败点与真实错误（不粉饰），并按需回退到人工 `advance_phase.py done` 并注明 deviation。

## 执行记录

- 2026-09-23 00:01–00:16 完成，全链路为文件事实（`evidence/e2e-recovery-20260923.md`）：

| 时刻（UTC） | 事件（原文） |
|---|---|
| 16:01:29Z | `goal-snapshot: startup baseline mtime_ns=1790046982584464900`（serve PID 97648→102084，conductor 102960→109732） |
| 16:01:37Z | `beat seq=23619`（心跳恢复） |
| 16:01:56Z | 人工 approve `gate-0002`（字节级改写 4 个 frontmatter 标量，678→760 B；未改任何配置） |
| 16:01:57Z | `gate-answered: gate-0002 approved → feature-params-service running` |
| 16:01:57Z | `resume: feature-params-service resumed by gate-0002 (one extra round granted)` |
| 16:01:57Z | `dispatch: ap-feature-params-service-repair-a2-a2 type=repair attempt=2` |
| 16:13:54Z | `dispatch: ap-feature-params-service-l3-a3 type=reviewer attempt=3`（L3 额度 = 2 + 1 credit = 3） |
| 16:16:05Z | `advance: verify->done exit=0` → roadmap `feature-params-service=done`、`_index.parallel` phase `DONE` |
| 16:16:14Z | `dispatch: ap-feature-gui-backend-spec-writer-a1`（**K3 依赖解锁**，开始 spec 阶段） |

- 旁证（AC-012 在真实现场再次成立）：本 key 自己的复核 worker `mw-stall-feedback-l3-review` exit=0 但 provider 流提前结束、留下 264 B 占位 `output.md`，被“worker 状态优先”规则判为 no-verdict（e2e 证据 §5）。
- 偏差记录：现场 conductor 是 16:01:29Z 代码快照，`_l3_round_verdict` 的占位文件修正（16:05 落地）未加载，该轮 L3 走了 `below → repair` 分支；不影响最终闭环，已在 achieved.md「遗留」记录。
- 未改任何 autopilot 配置（拒绝临时调 `round_budget` 的临时方案）。
