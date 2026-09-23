# Quality Gate Report: mw-autopilot-stall-feedback

- generated_by: PM 窗口（本 key 拥有者）+ 独立 L3 review worker（`mw-stall-feedback-l3-review`）
- generated_at: 2026-09-23T00:10+08:00
- 上游: spec.md AC-001..AC-013 · design.md D-1..D-9 · plan.md T-01..T-09

## VC 断言表

| VC | 断言 | 结果 | 证据 |
|----|------|------|------|
| VC-001 | advance 失败分类四类 + 未知 fallback；机读载荷写入事件 | PASS | `conductor._classify_advance_failure`；`test_autopilot_stall.py::test_classify_advance_failure_four_classes`；`_record_advance_result` 写 `{edge} exit=N class=...` |
| VC-002 | 连击判定：同 (key,edge) 计数、beat 忽略、成功/其它事件打断、不同 edge/不同 key 不合并 | PASS | `_advance_failure_streak`；3 个 streak 单测（含 `dispatch` 打断、其它 key 隔离） |
| VC-003 | 达阈值 → `stalled` 四件套 + 冻结（不再调用 advance） | PASS | `test_repeated_advance_failure_stalls_instead_of_spinning`（阈值 3：前两次 running，第三次 key-status=stalled + 遗留草稿 + pattern 文件 + 单行门禁 question；随后 4 tick 的 advance 事件数不增） |
| VC-004 | approve → 复位 + resume 事件 + 恰好一轮额度；幂等；reject → closed-legacy | PASS | `test_approved_stalled_gate_resumes_key`、`test_resume_credit_lifts_execute_retry_limit`、`test_resume_credit_lifts_l2_and_l3_limits`、`test_resume_credit_lifts_l3_and_repair_limits`、`test_rejected_stalled_gate_still_closes_legacy` |
| VC-005 | L3 worker 崩溃 ≠ verdict=below（含 harness 占位 output.md） | PASS | `test_l3_worker_failure_is_no_verdict`、`test_l3_failed_worker_with_placeholder_output_is_still_no_verdict`、`test_l3_no_verdict_stall_reason_names_worker`；**现场再次命中**：本 key 自己的 reviewer `mw-stall-feedback-l3-review` exit=0 但 provider 流提前结束、留下 264 B 占位 `output.md`，被状态优先规则判为 no-verdict（`evidence/e2e-recovery-20260923.md` §5） |
| VC-006 | 面板 autopilot 分节：tick 新鲜度/STALE、slots、每 key 相位+状态+in-flight、停滞连击+分类+时长+错误、stalled 行处置命令、110 列截断 | PASS | `test/suite/autopilot-monitor.test.ts`（派生 / STALE / 降级 / stall 规则 / 尾部读取 / config 镜像 6 例）；`deriveAutopilotPanel` + `renderMonitorLines` |
| VC-007 | 面板只读 + 缺失/损坏降级 | PASS | 单测断言读取前后 `hashTree` 不变（AC-007）；空项目与部分文件场景渲染占位行不抛 |
| VC-008 | autopilot enabled → session_start 自动显示；off 抑制本会话；disabled 不显示 | PASS（自动化）/ 未目视 | `autopilot-monitor.test.ts` 2 例；`pm-orchestrator.ts` session_start 调用。**真实窗口目视验证待 bundle/dist 重建（见遗留）** |
| VC-009 | Python 全包回归 | PASS | `python -m pytest -q`（packages/multi-workers，排除 test/ 基线夹具）= **818 passed / 9 deselected / 0 failed**；其中 autopilot 子集 224 passed |
| VC-010 | TS 回归 + 类型/风格门禁 | PASS | `vitest --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts` = 51 passed；`npm run check` = 0 error / 0 warning / 0 info |
| VC-011 | 现场止损（AC-001） | PASS | T-01：pm-state Phase 行字节级规范化（14396→14334 B，仅该行变化）→ 21:35:41 timeline `execute->verify exit=0`（此前 2242 次 exit=1）；dispatch.yml review 模型 id 修正（145 B 不变，仅 token） |
| VC-012 | 现场恢复走正式路径（AC-004/AC-011） | PASS | evidence/e2e-recovery-20260923.md：serve 重启（PID 97648→102084，conductor 102960→109732）→ approve `gate-0002` → `gate-answered ... approved → feature-params-service running` + `resume` 事件 + roadmap 回 `running` → 同 tick 重派 → `l3-a3` reviewer done → `advance verify->done exit=0` → roadmap `feature-params-service=done`、`_index.parallel` phase DONE |
| VC-015 | 面板与守卫同口径（AC-014） | PASS | `monitor.ts` 清除改为 `key|edge` 粒度且仅同 edge 成功结束连击；`autopilot-monitor.test.ts` 新增断言「跨 edge 成功不清除」「同 edge 成功后更早失败不复活」；spec AC-014 固化契约 |
| VC-013 | 文档与变更登记（AC-010） | PASS | 两个 CHANGELOG `[Unreleased]`（mw：Added 1 / Fixed 2；coding-agent：Added 1）；`README.md` 新增「Autopilot 配置与停滞处置」；`_pitfalls.md` 新增 P-009 |
| VC-014 | 并发边界留痕（AC-011） | PASS | `pm-orchestrator.ts` 仅 4 行纯追加（import 与对方 RAG import 共存）；未触碰 `ui-bridge.ts`/`task-dispatcher.ts`/`worker-mode.ts`/`shared/*`/`rag/*`/`mw.py`/`dist/`；bundle 未重建已记入遗留 |

## 独立复核（L3 worker，2026-09-23）

- `mw-stall-feedback-l3-review`（reviewer，timi/gpt-5.6-sol）：运行 8 分钟后 provider 流提前结束（`stream closed before response.completed`），worker exit=0 但未产出结论，harness 留下 264 B 占位 `output.md` → 队列标 `failed`。
  **这正好是真实现场再一次命中 AC-012**：队列表状态优先的规则把它判为 `no-verdict`（而不是拿占位文件当裁决）——见 `evidence/e2e-recovery-20260923.md` §5。
- `mw-stall-feedback-l3-review-a2`（收窄范围后重派，14 次工具调用，2 分钟）：**FAIL**，三条发现（已逐条核对代码后处置）：

| # | 复核发现 | 我的判定 | 处置 |
|---|---------|---------|------|
| 1 | `_resume_credits` 无消费台账：一次 approve 会同时放宽四个回路，而 spec/AC 写的是「恰好一轮」 | **部分同意**：实现行为是「一次 approve = 四个受管回路各放宽一轮」，且因各回路 `used` 计数由 append-only 的 dispatch 行派生而单调，额度**不会被反复受益**（用掉即再封顶）——所以不是「无界可复用」，但与 AC-004/AC-013 的「恰好一轮」措辞不符 | 按精确语义修：改 spec AC-004/AC-013、design D-6、`_resume_credits`/`_apply_stalled_approvals` docstring、`resume` 事件文本、README、CHANGELOG；新增 `test_one_credit_is_spent_by_one_round_per_loop` 把「用掉即失效」写成断言。不做「每回路消费台账」：需新增私有状态 + 并发写入协议，收益不匹配（已在 design D-6 记录取舍） |
| 2 | streak 只依赖有界 timeline 尾部，超过 400 事件/512 KiB 会丢掉旧失败而重置计数 | 同意（理论风险） | `_advance_failure_streak` docstring 写清窗口与「每 tick 2 事件、阈值 5 只需 ~10 事件/20s」的算术；新增 `test_beat_flood_does_not_break_streak`（每间隔 100 条 beat 仍收敛）——若未来缩小窗口先挂此测试。不改窗口大小：fail-open（读失败→0）不会造成误冻结 |
| 3 | TS `deriveAdvanceStalls` 在任意 edge 成功时都清除该 key 的连击，与注释声称的「仅同 edge 成功清除」矛盾；面板可能显示已恢复而 guard 仍在计数 | **同意**（注释与实现矛盾，且掩盖早期告警） | 改 `monitor.ts`：清除改为 `key|edge` 粒度、仅同 edge 成功才结束该连击（相邻边界的成功既不打断也不计入，与 `conductor._advance_failure_streak` 逐字对齐）；注释重写为「唯一允许差异是尾部事件保留」；新增 spec AC-014 + 测试断言（跨 edge 成功不清除、同 edge 成功后更早失败不复活） |
| 4 | Q3（`_l3_round_verdict` 状态优先） | PASS | 无改动 |

复核后回归：Python `test_autopilot_*` **47 passed / 0 failed**（含 2 个新用例）；TS 面板 + console **51 passed**；`npm run check` 绿。

## 未覆盖 / 已知缺口

- 面板自动显示与 `advance_stall_ticks` 生效的**目视验证**（需 `mw build --install` + 窗口重启；受并发 key 的 `dist/` 冲突限制）。
- E2Feature 现场运行的是 16:01:29Z 的代码快照：`_l3_round_verdict` 的「worker 状态优先」修正（16:05 落地）未加载，该处 L3 走了 `below → repair` 分支；该轮最终仍由 `l3-a3`（reviewer 模型已修）收口，现场已 done。
- L3 复核的三条发现已全部处置（见上节）；发现 1 属「措辞与语义不符」，按精确语义修正而非新增消费台账（取舍理由已记 design D-6）。
- `advance_stall_ticks=5` 默认值未做长期生产观测；过早升级的风险已由「approve 恢复一轮」兜底。
