# Achieved: mw-autopilot-stall-feedback

- key: mw-autopilot-stall-feedback
- 阶段: EXECUTE/VERIFY · 2026-09-23
- 上游: spec.md（AC-001..AC-013）· design.md（D-1..D-9）· plan.md（T-01..T-09）

## 系统行为变化

1. **advance 失败有界化（此前无界）**：conductor 对每次失败的 phase 推进记录机读分类（`{edge} exit=N class=interface-drift|gate-blocked|timeout-env|other`），并从 timeline 尾部（有界读）重派生「同一 `(key, edge)` 连续失败数」；达 `advance_stall_ticks`（默认 5，可配）即调用既有 `mark_stalled` 四件套（key-status + `stalled` 门禁 + achieved 遗留草稿 + pattern 文件），key 随后被既有 skip 规则冻结。此前现场 `execute->verify` 连续失败 2242 次 / 2h35m 只写一行自由文本，无计数、无门禁、无上报；同日另有 3891 次 / 4h25m 的同型空转。零私有状态：连击每 tick 重派生，conductor 重启不丢。

2. **`stalled` 门禁 approve 从 no-op 变为真实恢复路径**：`_apply_stalled_approvals` 把 key-status `stalled` → `running`（roadmap 锁内），写 `gate-answered` 消费记录 + 新增 `resume` 事件，并就地更新本 tick 的 `status_of`；`_resume_credits`（= 该 key 已批准的 stalled 门禁数）为该 key 的 L2 / EXECUTE / L3 / repair 四个预算点各恢复**恰好一轮**。此前门禁问句写着「人工介入后重试」但只消费 `reject`（→ closed-legacy），approve 不产生任何效果，key 永久停在 stalled。

3. **L3 裁决失真修正**：`_l3_round_verdict` 先看该轮 worker 队列表状态——`failed` / `needs-clarification` 直接判 `no-verdict`（即使 harness 留下了占位 `output.md`），不派 repair，直接进入下一轮 L3，并记 `l3-no-verdict` 事件；预算耗尽时停滞原因写明 `L3 无裁决（worker <status>: <task_key>）`。此前 reviewer 6 秒崩溃（模型 id 笔误 → 403）被当成 `below`，于是派 repair 去修一份不存在的报告、烧完两轮预算并报「L3 below 2 rounds」，把原因指向错误的层。

4. **失败可见（PM 窗口底部）**：`/autopilot monitor` 面板新增 autopilot 分节——tick 新鲜度（`tick seq N (3s ago)`，超 `max(30s, 5×poll)` 判 `STALE (conductor not ticking)`）、槽位 `slots u/m`、需要关注的每个 key（phase / roadmap 状态 / in-flight / 依赖阻塞）、停滞连击（次数 + 主分类 + 时长 + 错误摘要）、`stalled` 行的处置命令 `/autopilot gate <id> approve|reject`；派生全部只读、可注入 `nowMs`、缺失/损坏文件降级为占位行、timeline 用尾部窗口读（不随 4MB 历史线性放大）。autopilot enabled 的项目在 PM 窗口 session_start 自动显示；`/autopilot monitor off` 本会话抑制、`monitor on` 解除。

5. **配置契约双侧同步**：`advance_stall_ticks`（默认 5，范围 1..50）加入 Python `config.DEFAULT_CONFIG`/`_INT_RANGES` 与 TS `AutopilotConfig`/`DEFAULT_CONFIG`/`INT_RANGES`/`readConfig`/`saveConfig` 镜像（两侧都 fail-closed 拒绝未知键，缺一不可）；旧 config.json 缺该键取默认。timeline 事件词表两侧各增 `resume` / `l3-no-verdict`。

## 目标收益

- 现场（E2Feature `feature-params-service`）：停摆从「2h35m 静默空转」变为可处置——`gate-0002` approve 后同一 tick 内出现 `gate-answered` + `resume` 事件、roadmap 回到 `running`、并按正式路径继续 VERIFY 回路，最终 `16:16:05Z advance verify->done exit=0` → roadmap `feature-params-service=done`、`_index.parallel` phase DONE，K2 闭环（全程零配置改动：只回答了门禁）。
- 回归面：Python `test_autopilot_*` **47 passed / 0 failed**（含复核后新增 2 例）；`packages/multi-workers` 全包 **818 passed / 9 deselected / 0 failed**；TS 面板与 console **51 passed**；`npm run check` 0 error / 0 warning / 0 info。
- 反馈闭环：停滞从「只躺在 timeline 的一行文本里」变为「门禁 + 面板 STUCK 行 + 处置命令 + 事件分类」，且面板与守卫同口径（AC-014）。
- 独立复核：收窄范围的只读 reviewer 给出 3 条发现（额度语义措辞、尾部窗口边界、面板跨 edge 清除），已逐条核对并处置（额度按精确语义改写 spec/design/代码/文档并补消费断言；面板清除对齐守卫并补断言），详见 `evidence/quality-gate-report-20260923.md`。

## 遗留

- **扩展 bundle/dist 未重建**：`packages/coding-agent` 的 TS 改动（monitor/status-model/console/pm-orchestrator）尚未 `mw build --install`，因此监控面板与自动显示在真实 pi 窗口**未做目视验证**。原因：`dist/extensions/agent-team-loop.js` 与并发 key `mw-rag-integration-fix` 的未提交改动重叠（GC-4 边界）。AC-008 的自动化测试通过，目视验证待该 key 提交后执行。
- **E2Feature 的 conductor 未加载 `_l3_round_verdict` 的状态优先修正**：serve 在 16:01:29Z 重启（加载了本 key 的 T-02..T-04），而该修正在 16:05 才落地；现场那次 L3 已按「占位 output.md → below」走了 repair 分支（仍正常推进到 `l3-a3` 并 done）。下次 serve 重启即生效。
- **额度语义取舍**：一次 approve 会同时放宽 L2/EXECUTE/L3/repair 四个回路各一轮（由各回路单调的轮次计数消费，不可复用），而不是字面的「全局恰好一轮」。要收紧为「只放宽一个回路」需新增消费台账 + 并发写入协议，取舍理由已记 design D-6，待用户决定。
- **streak 窗口是有界的**：连击从 timeline 尾部（400 事件/512 KiB）派生，窗口需容纳整段连击；算术已写入 docstring 并由 `test_beat_flood_does_not_break_streak` 钉死，真被截断时降级为 fail-open（0），不误冻结。
- **framework 侧容错未做（U-2）**：`advance_phase.py` 对 `- Phase:` 行的解析仍要求裸 token，写入方（worker）仍可能写坏。本 key 只在 mw 侧做防呆 + 上报；放宽解析属 AgenticTask 框架仓改动，需用户另批。
- **阈值默认值未在生产压测**：`advance_stall_ticks=5`（4s × 5 = 20s）对「慢门禁」类临时失败可能过早升级；升级可 approve 恢复一轮，但真实长期观察数据尚缺。
- **面板与 watch widget 未同屏（U-1）**：autopilot 信息落在既有 monitor 面板；是否并入 key+worker watch widget（`pm/ui-bridge.ts`）待并发 key 提交后由用户决定。
- **未提交**：本 key 的全部改动仍在工作区（未 commit），且与 `mw-rag-integration-fix` 的脏文件共存于同一 worktree。
