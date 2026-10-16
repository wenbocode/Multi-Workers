# Quality Gate Report: framework-drift-guard (maintenance, no key)
**时间**: 2026-09-02T16:09:09+08:00
**触发**: 手动（用户 "review and quality gate"）
**范围**: commits b308441 + 67508e5（AgenticTask clone）+ goal.ts 写入门禁（全局扩展，未入库）

> **前置门禁偏离说明**：本次为框架维护工作，无对应 .agenticdoc key（无 spec.md/design.md/evidence-requirement.md）。
> 形式化 QG 不适用；按"从变更意图推导问题清单 → 证据链核查"的适配模式执行。
> 事实 spec = 根因分析（中文模板静默无操作 + 假 OK）+ "必改" 决策。

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-DRIFT-1 | 漂移文件写入被拦截且文件逐字节不变 | ✅ 充分 | test_advance_phase.py VC-023 drift_write_guard | — |
| Q-DRIFT-2 | 缺 `- Updated:` 行被拦截 | ✅ 充分 | VC-023 drift_missing_updated | — |
| Q-DRIFT-3 | 读守卫在 gate 前拦截、索引零触碰 | ✅ 充分 | VC-023 drift_read_guard（_index.parallel 未创建）| — |
| Q-DRIFT-4 | 未知 Phase 值拦截 | ✅ 充分 | VC-023 drift_unknown_phase | 覆盖 agent-team-loop 带注解值实况 |
| Q-REGRESS-1 | 英文模板正常路径零回归 | ✅ 充分 | 既有 11 测试 VC-001~006/020/022/W1/W2 ×3 副本 | — |
| Q-CONSIST-1 | 三副本字节一致 | ✅ 充分 | git diff --no-index 空 + test_sync_framework ×3 | — |
| Q-RELEASE-1 | 发布完整性 | ✅ 充分 | 67508e5 pushed；.tmp 缓存已刷至 67508e5 | — |
| Q-GOAL-1 | goal.md 写入门禁全路径需用户确认 | ⚠️ 不足 | 9/9 + 5/5 临时测试（已删） | goal.ts 在仓库外，无永久回归网 |
| Q-LIVE-1 | 存量漂移文件处置 | ⚠️ 不足 | agent-team-loop pm-state `- Phase: EXECUTE → DONE（待…）` | 下次 advance 将响亮报错，需手改回接口格式 |
| Q-LIVE-2 | 存量事实源分叉 | ⚠️ 不足 | timi-gpt-pi-routing：pm-state=DONE vs 索引=EXECUTE | 历史 bug 实际损伤，需人工对账 |

**证据运行**（2026-09-02T16:09:09）：advance_phase 15/15 ×3（OK）、sync_framework ×3、detect_root 全部 exit 0。

## 汇总
- 总问题数: 10
- ✅ 充分: 7（70%）
- ⚠️ 不足: 3
- ❌ 无证据: 0

**质检结论**: ⚠️ 有条件通过（验证欠债 3 项，无阻断项）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 |
|------|------|---------|
| Q-GOAL-1 | goal.ts 位于 ~/.pi，仓库测试不可及 | 接受欠债；或将门禁逻辑迁入 agent-team-loop 扩展（有仓库测试） |
| Q-LIVE-1 | 手写注解漂入接口行 | 将 agent-team-loop pm-state 的 Phase 行改回 `- Phase: EXECUTE` |
| Q-LIVE-2 | 历史静默失败损伤 | 人工对账 timi-gpt-pi-routing 的真实相位并统一两源 |

## 二次印证
- 发现 1 个遗漏：update_index.py `_sync_claim_to_pm_state`（:199-215）对 `- Claim-Id:` / `- Key:` 行使用同款未守卫 re.sub——同类静默无操作 bug 在兄弟路径漏网（review W3，建议下迭代补 subn 守卫 + 用例）。

## 处置记录（2026-09-02 16:25）

- W1 已修：agent-team-loop pm-state Phase 行恢复 `- Phase: EXECUTE`（注解信息已在""下一步行动""行，无丢失；真态 EXECUTE 待用户确认后 advance）
- W2 已修：timi-gpt-pi-routing 经 `update_index.py set-phase` 正规通道对齐索引至 DONE（真态判定依据：pm-state DONE + 7 任务全完 + ready for merge；索引 EXECUTE 为滞后）
- W3 已修（commit 6b22bd3）：_update_pm_state_claim 补 subn 守卫（Claim-Id 更新/Key 后插入双路径响亮失败）；cmd_claim 改 pm-state 先写（漂移时索引零触碰）；顺带修复两个预存 bug——CRLF 读写不对称（双 \r 腐败）与 `.*` 吞行尾 \r。新增 test_update_index.py VC-024~029 ×3 副本，全套 10 个测试文件回归全过

## 处置记录（2026-10-16，mw-goal-gate-write-intent）

- **Q-GOAL-1 关闭**：goal.ts 门禁模板已入库 —— `packages/multi-workers/goal.ts`（紧邻 mw.py，与 agentictask-update.ts 同机制），`mw.py::_goal_gate_install()` 在 `mw setup` / `mw build --install` 安装（字节精确、幂等、漂移覆盖）。
- **永久回归网**：`packages/multi-workers/test_goal_gate.py` 从模板哨兵 `GOAL-GATE-CLASSIFIER-BEGIN/END` 之间原样抽取判定块，node（`--experimental-strip-types`）执行 31 条只读 + 30 条写入向量，另加安装三态（缺失/幂等/漂移覆盖）；AC-004 以字节比较保证本机安装副本 == 仓库模板。
- **触发事件**：2026-10-16 用户报告「读 goal.md 也被拦」——旧 bash 启发式（`(python|node|perl|ruby|awk|pwsh|powershell) ... goal.md` 与 `(mv|move|rm|del|cp|copy|...) ... goal.md`）把只读命令判成写：worker trace 共 8 处 `[TOOL_ERR] ... 只读的项目目标锚点`（mw-worker-output-contract / mw-autopilot-slot-capacity / mw-done-closure-repair / mw-autopilot-gate-alarm-liveness），交互窗口弹 yes/no。新口径按引号感知分段 + 写意图判定，只读形态全放行；write/edit 工具门禁语义不变。
- 残留（未做）：门禁逻辑未并入 agent-team-loop 扩展（该扩展 worker 写面守卫 `bashWriteDenyReason` 已覆盖 worker 写 goal.md）；本次只解决「读被拦 + 仓库外无测试」。
- 勘误：W3 原文函数名应为 _update_pm_state_claim（非 _sync_claim_to_pm_state）
