# Quality Gate Report: mw-worker-timeout-convergence

**时间**: 2026-09-09T16:50+08:00
**触发**: 手动（用户 /quality-gate），Stage S1~S3 完成后
**范围**: 全量（AC-001~006，VC-001~006 + 交叉问题）

## 前置门禁

| 检查项 | 状态 | 说明 |
|--------|------|------|
| spec.md AC 编号 | ✅ | AC-001..006（6 条） |
| design.md VC 映射 | ✅ | D-001..D-006 全部回链 AC；VC-001..006 在 plan.md 声明 |
| AC→VC 覆盖 100% | ✅ | 每个 AC ≥1 VC |
| evidence-requirement.md | ⚠️ 缺失 | 本 key 采用适配格式：充分性标准内嵌于 spec §3（OverCode 四案例映射）+ plan VC 清单；未单独落文件 |
| ac_fingerprint | ⚠️ 无法校验 | 依赖上一项（无独立文件可对指纹）；以 spec §4 决策记录 D-1/D-2 锚定需求基线替代 |
| evidence/baseline/ | ⚠️ | 以改造前基线替代：既有 73 用例全绿 + 全仓 check 580 错误基线（见下） |
| tasks/*.md ac_refs | ⚠️ | 采用 plan.md 内联 T-01..T-08 + ac/vc 引用，未拆分单文件 |

前置项 4 个 ⚠️ 均为文档形态适配（本仓库 .agenticdoc 惯例），不影响证据链实质；如需完全对齐模板可后续补 evidence-requirement.md。

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | idle 判真挂死：无活动超阈值被杀，[TIMEOUT] 带判据 | ✅ 充分 | 集成测试×3（idle kill 60s 精准、delta 滴流 200s 不杀、phase 间隙仍覆盖）+ 单测 resolveIdleMs/appendTimeout(idle) | 质检中新补集成测试（原仅组件级） |
| Q-AC-002 | 预算优先级 + 墙钟兜底 | ✅ 充分 | 单测（task.md>env>60m 默认、锚点/steer 公式、parseTaskMd timeout 头）+ 集成（180s 小预算墙钟精准、exitReason 携判据）+ L2 Run 1（120s 实跑墙钟） | |
| Q-AC-003 | deadline steer 收尾 | ✅ 充分 | L2 Run 2：steer 注入在途 turn，agent 采用收尾结构，110s<120s 自行 settle exit=0 + 集成（steerAt=135s 触发、deliverAs=steer） | |
| Q-AC-004 | 收敛检查点 + 自评 + PM 升级 | ✅ 充分* | 单测（computeRisk 三分支、[CHECKPOINT] 行往返 last-wins、poll 循环 mid/high 一次 triggerTurn、low 不扰、跨 key 隔离）+ 集成（90s 锚点、followUp steer、risk=high、output.md 带摘要）+ L2 Run 2（60s 锚点实跑 + progress.md 自评落地） | *PM 升级的实机 triggerTurn 待窗口重启后首验（欠债 1 项） |
| Q-AC-005 | widget ck 徽标 | ✅ 充分 | 单测（ck30m high⚠ / low 无 ⚠） | |
| Q-AC-006 | 兼容性：格式不变、Python 零改动 | ✅ 充分 | git diff 范围核查：本 key 仅改 6 个扩展文件 + test + goal.md/.agenticdoc；mw.py/mw_common.py 改动属另一会话（doctor/init 工作，零 watchdog 交集，grep 验证）；PI_WORKER_TIMEOUT_MS 仍在 resolveBudgetMs 读取 | |
| Q-X-001 | 多 phase 任务 watchdog 存续（老 bug：首 settle 丢看门狗） | ✅ 充分 | 集成测试 3：phase-1 settle 后静默 60s 仍被 idle 杀，[END] phases=0/2 | 质检中新增覆盖 |
| Q-X-002 | 非流式 provider 退化（无 message_update） | ✅（推理级） | 设计 D-002：其余事件仍 touch；工具持续在跑就不可能 idle；10m 阈值 > 已观测 7m 合法长调用。集成测试 1 即"零事件"情形 | 无需专门测试：无 delta 且无工具 = 真死 |
| Q-X-003 | steer 在 agent 运行中的排队 | ✅ 充分 | L2 Run 1 发现缺陷（裸调用抛 already-processing）→ 修复 followUp/steer；L2 Run 2 干净；集成测试 4 断言两 steer 的 deliverAs 选项值 | 质检中补选项断言 |

## 汇总

- **总问题数**: 9（AC 6 + 交叉 3）
- **通过（充分）**: 9（100%；其中 Q-X-002 为推理级 + 结构性测试佐证）
- **有条件通过（不足）**: 0
- **未通过**: 0

**测试/静态核查基线**（2026-09-09 16:45 复跑）：

- vitest agent-team-loop：**87/87**（既有 73 + 本 key 新增 14：单测 10 + 集成 4），零回归
- biome（src+test，error-on-warnings）：17 文件全绿
- npm run check：全仓 580 TS 错误 = 既有基线（packages/ai model-ID 陈旧，另一会话域），agent-team-loop 交集 0
- 部署产物：bundle（mw build --install）与 dist built-in（npm run build）均已同步重建

**质检结论**: ✅ 通过

## 验证欠债（不阻塞，已记录）

| # | 项 | 触发条件 | 债主 |
|---|----|---------|------|
| 1 | PM 升级 triggerTurn 实机首验（mid/high → PM 主窗口唤醒 + 四选一判断） | 用户重启 pi 窗口后首个真实长任务 | 用户 + PM 窗口 |
| 2 | idle 阈值收紧（10m → 更小）前的流式确认（timi 路由 delta 到达率） | OverCode 重派观察 | 用户 |
| 3 | evidence-requirement.md / tasks 单文件化（模板完全对齐） | 下个 key 起或闲时 | PM |

## 二次印证结论

重读 spec/design/plan 全文后扫描：spec §3 四案例映射全部被 Q 覆盖（cpr-004→Q-AC-002、cpr-005→Q-AC-003、cpr-003→Q-AC-001/X-002、cpr-007→Q-AC-002/004）；D-001~D-006 每个设计节点对应 ≥1 Q；异常路径（idle/wall/steer 排队/phase 存续/跨 key）全覆盖；无 AC 有 VC 缺口。发现并当场修复两个覆盖缺口（X-001 多 phase 存续、X-003 steer 选项断言），即上表集成测试。


---

# Round 2（2026-09-09 晚，恢复复验 + 文档形态债补齐）

**触发**：worktree junction 删除事故后接管复跑；同时补齐 Round 1 标记 ⚠ 的文档形态项。

## 恢复完整性证据

- 重建扩展 bundle 与事故前（16:11 构建、16:1x 全局安装）bundle **SHA256 字节一致**——Round 1 质检所验证的扩展代码与恢复后工作区完全相同
- vitest agent-team-loop **90/90**（Round 1 时 87/87；增量 3 为 pm-state 守卫测试，与本 key 无交集且零回归；本 key 14 用例——单测 10 + workerModeActivate 集成 4——全数在场通过）
- biome 全绿；npm run check 本 key 范围 0 错误（全仓基线 580→26，均为 packages/ai models 域既有，数据重拉后收敛）
- 部署产物：全局 bundle 与 dist built-in 均已重建（dist 事故中被删，全仓 7 包依序重建；worker-mode dist 含 CHECKPOINT ×28）

## 文档形态债补齐（6 项 -> audit PASS）

- spec.md 补 §0 Goal Alignment（对齐/GC 继承/冲突/预期收益）+「可复用资产」「需规避坑点」前馈两节
- evidence/research/overcode-timeout-forensics-*.md 改名 spec-* 前缀；新增 design-watchdog-layers-2026-09-09.md（自 design.md/决策记录/实跑证据追溯补记）
- tasks/ 自 plan.md 内联清单拆分 8 文件（T-01~T-08，含 ac/vc refs；均标注 BACKFILLED 补记性质）
- audit_phase：**PASS**（design/plan/tasks/execute/done 全过）

## 结论更新

- Round 1 的 9/9 充分维持，零回退
- 遗留维持 3 项：PM 升级 triggerTurn 实机首验（待窗口重启）；idle 阈值收紧（待 timi 流式确认）；evidence-requirement.md 独立文件形态对齐（audit 未强制，择机）
