# PM State: mw-widget-terminal-lifecycle

## Section 1: Snapshot
- Key: mw-widget-terminal-lifecycle
- Claim-Id: WENBOZHOU-PC4:10484
- Phase: DONE
- Updated: 2026-09-10 19:27
- Completed: 2026-09-10 19:27
- 下一步行动（重启恢复锚点）: ①✅T-01~T-09 全部完成 + /review LGTM（3 项 Suggestion 已修复：S1 live 排序/S2 beat 清理/S3 转义，各带回归测试）→ ②✅/quality-gate 通过（38/38 问题充分，报告 evidence/quality-gate-report-2026-09-10T1755.md；指纹重锚 95d6a253ba12 已留痕；1 项门禁 ⚠️ baseline 空待用户确认）→ ③⏳用户确认 ⚠️ 后 done（achieved.md）+ 提交（等用户指令）；遗留：packages/ai 基线漂移拆 key（26 tsgo + 8 runtime + agent 2 + core 85 Windows 环境败，均预存非本 key）

## Section 2: Task Status

| Task | Stage | 代码状态 | 验证状态 |
|------|-------|---------|---------|
| T-01 AckStore（sidecar 读写） | 1 | 代码完成 | PM 验收通过（07:26Z：diff 审查锁/tmp+rename/幂等/坏行容忍全符合，复跑 5/5 + [VERIFY] VC-004） |
| T-02 mw_common 证据与 beat | 1 | 代码完成 | PM 验收通过（07:33Z：+127 行五函数实现镜像 TS 语义，复跑 61 passed + VC-012/013 双埋点；test_integration 曾现一次 Windows PermissionError flake，隔离重跑绿） |
| T-03 TL;DR 归一化 | 2 | 代码完成 | PM 验收通过（07:36Z：headline 四步归一化 + writeOutput 首节 + steer 文案，diff 干净；复跑 98/98（8 新 + 90 旧零回归）+ [VERIFY] VC-009；`##` 无尾空白不剥契约已锁） |
| T-04 starter 首行结论指令 | 2 | 代码完成 | PM 验收通过（07:30Z：diff 仅 _starter_prompt 单句 + 5 用例，复跑 52 passed + 埋点） |
| T-05 终态 detail 取源 | 3 | 代码完成 | 验证通过（07:39Z：PM 直执；100/100 + VC-007/008/009 埋点） |
| T-06 widget 三区渲染 | 3 | 代码完成 | 验证通过（07:46Z：PM 直执；100/100 + VC-001/002/003 埋点；21 调用点同步） |
| T-07 ack 通道与提示 | 3 | 代码完成 | 验证通过（08:02Z：PM 直执；106/106 + VC-004/005/006/010/011 埋点） |
| T-08 launcher reconcile | 4 | 代码完成 | 验证通过（07:52Z：wtl-t08；diff 审查 + 复跑 69/69 + VC-012/013 埋点 + 全量 358 零回归；_exit_to_status 复用、beat→archive→reap→reconcile→discover 顺序） |
| T-09 回归收口 | 5 | 代码完成 | 验证通过（08:40Z：VC 13/13 + bundle 冒烟 + evidence/runs 落盘 + CHANGELOG；npm run check 阻塞于预存 packages/ai 26 错，已记录并建议拆 key） |

## Section 3: Evidence Ledger

| 证据 | 类型 | 结果 | 证据文件 |
|------|------|------|---------|
| spec-widget-terminal-forensics | 调研 | widget 终态行无生命周期 + detail 取 Summary 首行 + ack 删行会重派（发现 1-6） | evidence/research/spec-widget-terminal-forensics-2026-09-10.md |
| spec-orphan-running-reconcile | 调研 | serve 停止不杀 worker + 只有 spawn 方更新行 + [END] 机器可读 + pi 无 exit2 产出者（发现 1-10） | evidence/research/spec-orphan-running-reconcile-2026-09-10.md |
| design-ack-and-reconcile | 调研 | PM-only 工具构造保证 + TS 无 running_procs 归属 + beat 协议必要性（发现 1-9） | evidence/research/design-ack-and-reconcile-2026-09-10.md |
| design-terminal-summary-quality | 调研 | Summary 首行质量样本 + starter 唯一跨 CLI 注入点 + 归一化规则回测（发现 1-7） | evidence/research/design-terminal-summary-quality-2026-09-10.md |
| spec 锁定 + design/plan 门禁 | 机械校验 | AC 13/13 + VC 13/13 全引用；mermaid PASS；audit VERDICT PASS | 命令输出（2026-09-10 12:13-15:12） |

## Section 4: Hypothesis Queue

| 假设 | 状态 | 关联证据 |
|------|------|---------|
| packages/ai 26 个 tsgo 错误为预存基线漂移（非本 key 引入）：全部在 packages/ai（src/providers/cloudflare-ai-gateway.ts + 10 个 test 文件：过时 model ID、ProviderStreams 类型面、TS1294 非可擦语法）；git status 干净→已提交 HEAD 即红；本 key 文件域零错误。可疑诱因：node_modules 漂移（models.generated.ts mtime 09-09 23:42 但内容同 08-14 提交）或 09-09 后某次水化。阻塞 T-09 的 npm run check 门禁 | 待验证（候选处置：①npm 重新水化后重跑 tsgo ②拆独立 key 修 ③本 key 顺手修——待用户定） | tsgo --noEmit 输出 2026-09-10 15:2x；git log packages/ai |

## Section 5: Decisions

- D-001~D-009: design.md §10（sidecar ack / 双通道 / 三区渲染 / detail 取源 / TL;DR 双保险 / launcher reconcile / 正证据+静默 / beat 退让 / L1 测试）
- 2026-09-10 用户决策: done 行无需 ack 直接折叠（已决 1）；孤儿 reconcile 纳入本 key（已决 2）；sidecar 文件名 _workers.acked（已决 3）；design 确认；plan 确认
- 派发策略（待用户定案）: Wave1 = T-01~T-04 并行 worker（零交叉：ack-store+新测试文件 / mw_common+test_common / output-writer+worker-mode+新测试文件 / launcher._starter_prompt+test_launcher）；Wave2 = T-05→T-06→T-07 PM 直执（同文件链）∥ T-08；Wave3 = T-09 直执

## Section 6: Turn End Records

### Turn 2026-09-10 15:19 (Wave1 派发)
1. 顶层目标: 派发 Wave1 四 worker 并建立恢复锚点
2. 新增证据: _workers.parallel 四行 running（07:18:47Z）；mw serve PID 57036 确认存活
3. 假设变化: 无
4. 需重开 Task: 无
5. 阻塞点: 无
6. 新增 Task: 无（T-01~T-04 已在库）
7. 下一轮首要动作: 四 worker done/failed 后逐个验收（diff 审查 + 测试重跑 + 埋点核对 + 任务文件执行记录），再定 Wave2 启动
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: 无新增

### Turn 2026-09-10 (EXECUTE 启动)
1. 顶层目标: spec/design/plan/tasks 四阶段产物落盘并进入 EXECUTE
2. 新增证据: 4 份 research note；AC/VC 覆盖校验 13/13×2；mermaid 门禁 PASS（R2 边标签引号修正一次）；audit_phase VERDICT PASS
3. 假设变化: 无
4. 需重开 Task: 无
5. 阻塞点: 无（等待用户定案派发策略）
6. 新增 Task: T-01~T-09（plan.md 5 Stage / 9 Task）
7. 下一轮首要动作: 用户定案后 Wave1 派发（dispatch_worker ×4，key=mw-widget-terminal-lifecycle）
8. 已写入 pm-state.md: 是
9. 可提炼 pattern: ①claim stub 的 Phase (pending) + 缺 Updated 行会让 advance_phase 双重拒绝——手工补 init + Updated 后即通（goal-autopilot 2026-09-07 已踩，本次确认仍在，候选 _pitfalls.md）；②mermaid 边标签不可带引号（check_mermaid R2，与节点标签规则相反，须写进 checklist）

## Section 7: Process Log

- 2026-09-10 12:00: key 创建（用户指令「用新 key」）；spec 起草（用户 4 点反馈：不手改在跑行/不用 TTL/摘要要状态卡点/新 key）
- 2026-09-10 12:13: spec 锁定（AC-001~013）；调研 2 份落盘（含 AC-008 前提核查修正：pi 无 exit2 产出者，加回退链）
- 2026-09-10 12:14: advance design；design.md（D-001~D-009 + 2 图 + F1-F9 + VC-001~013 + AC→VC 13/13）；mermaid R2 修正后 PASS；key-decision A 章；evidence-requirement.md（指纹 4340acf7b818）
- 2026-09-10 15:12: 用户确认 design → plan.md（5 Stage / 9 Task，AC/VC 全引用）→ advance tasks→execute，audit PASS；tasks/ 9 文件落盘；pm-state Section 1-7 初始化（pm-state 守卫拦截一次：接口行字节校验，改定点编辑绕开接口行）
- 2026-09-10 15:19: 用户确认派发方案 → Wave1 四 worker 派发（wtl-t01-ack-store / wtl-t02-mw-common / wtl-t03-tldr / wtl-t04-starter，key=mw-widget-terminal-lifecycle），15s 后四行均 running
- 2026-09-10 15:30: wtl-t04 done（4m）→ PM 验收通过：launcher.py diff 仅 _starter_prompt +2/-1；test_launcher.py +5 用例与 _emit_verify；复跑 52 passed + [VERIFY] VC-009 埋点；worker 自报全量 317 passed 零回归（留待 T-09 统一全量复核）；任务文件已由 worker 更新
- 2026-09-10 15:26: wtl-t01 done（6m）→ PM 验收通过：ack-store.ts 实现审查 + 复跑 5/5 + [VERIFY] VC-004；worker 上报 npm run check 中 packages/ai 26 个预存 tsgo 错误（详见 Section 4）
- 2026-09-10 15:33: wtl-t02 done（10m）→ PM 验收通过：mw_common.py +127（五函数）/ test_common.py +200（26 用例），复跑 61 passed + VC-012/VC-013 埋点；全量 341 passed 零回归（worker 自报）
- 2026-09-10 15:35: wtl-t03 done（16m）→ PM 验收通过：headline + TL;DR 首节 + steer 文案；复跑 98/98（8 新 + 90 旧）+ VC-009 埋点；Wave1 4/4 验收完毕。→ 派发 wtl-t08-reconcile（T-08，Python 域）+ PM 启动 T-05 直执
- 2026-09-10 15:47: T-05 + T-06 PM 直执完成：三区渲染 + 终态 detail 取源落地（ui-bridge.ts 重构 + pm-orchestrator 调用链）；vitest 113/113（三文件）+ 六埋点（VC-001/002/003/007/008/009）；biome --write 修 2 文件格式后零告警。→ T-07 启动
- 2026-09-10 15:52: wtl-t08 done（12m）→ PM 验收通过：_reconcile_orphans（正证据无条件 + 静默 90m + beat 退让 + _record_reconcile）接入 _poll_once；复跑 69/69 + 双埋点 + 全量 358 零回归。→ T-07（最后一个代码任务）实现中
- 2026-09-10 16:05: T-07 PM 直执完成：ackTasks + /mw ack + ack_worker_result 工具 + list_tasks 徽标 + PM_CONTINUE_HINT ack 指示；vitest 119/119（三文件）+ 11 埋点（VC-001~011）。代码任务全部完成 → T-09 收口启动（全量回归 + models 重生成试探 + /mw build + 冒烟 + evidence + CHANGELOG）
- 2026-09-10 16:45: T-09 完成：models 重生成零变化（26 错误为真实漂移，defer 拆 key）；本 key 域 TS 119/119 + Python 363 全绿；全量套件预存败分类在案（agent 2/ai 8/coding-agent core 85，零 import 交叉）；/mw build + 全局安装 + mw serve 重启（新 launcher beat 实证）；bundle 级冒烟全过（ack 拒绝/落盘/工具/徽标）；evidence/runs/regression-2026-09-10.md + CHANGELOG 4 条落盘。T-01~T-09 全部完成 → advance VERIFY
- 2026-09-10 17:58: /review LGTM（0 Critical/0 Warning/3 Suggestion，报告 evidence/runs/review-2026-09-10.md）→ 用户指示修复 S1~S3：live 区 newestFirst 排序 / other_live_launcher 过期且死 pid 的 beat unlink / readOutputSection regex 转义，各带回归测试（TS +2 用例 121/121，Python +2 用例 365 passed，biome 零告警，bundle 重建重装）。/quality-gate：38/38 问题充分 ✅；指纹失配根因定位为原值口径不可复现（AC 集合零漂移已独立证实：ac_ids 一致 + mtime 时序），canonical 管道重锚 95d6a253ba12 并在 evreq/plan 留痕；修正 T-01/02/03/08 四处滞留「未验证」表头。1 项门禁 ⚠️（baseline 空，D-009 设计定性）待用户确认
