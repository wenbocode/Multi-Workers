# Task T-11: bundle 重建 + L2 同规格重跑

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-001, AC-003, AC-006, AC-008, AC-012]
- vc_refs: [VC-012]
- pattern_refs: []

## 描述
端到端验证（design D-007 L2，ga-spec-review-1 同规格回归）：
1. `/mw build`（packages/multi-workers/build-extension.sh）重建扩展 bundle——worker 心跳代码随 bundle 进 worker 进程；doctor 侧 python 直接生效
2. L2 重跑（VC-012，对照 ga-spec-review-1 规格）：
   - 派发 `type: review` 任务至 goal-autopilot key 名下（ga-spec-review-2 之类新 task-key），无人工路由干预
   - 断言三项：task.md 落 `goal-autopilot/workers/`；执行期 trace.log 相邻 [HEARTBEAT] 间隔 ≤60s（含长生成阶段）；队列行/完成经 pi/timi 默认路由
   - 观察项：PM 窗口 widget running 行 ph/hb 进度与终态摘要统计（AC-012/013 现场形态）
   - 附加：`python mw.py doctor --project=. --json` 的 worker_liveness 在任务运行中显示 alive
3. 证据留底 `evidence/runs/l2-rerun-<date>.md`：派发命令/队列行/trace 间隔统计（首末条目 + 最大间隔）/output.md 摘要/doctor 输出节选
4. 前置条件：mw serve 运行、timi 凭证可用；不可用则按 plan 风险条款记录 L2 pending（验证欠债 +1），不得虚报

## 输入
- 依赖文件: 全部改动 + build-extension.sh 产物
- 依赖 Task: T-10
- AC 约束:
  > AC-008: 修复后重复 goal-autopilot review 派发场景：task 落 goal-autopilot/workers/、心跳持续、默认 pi 完成、无人工干预，三项全部满足

## 预期产出
- 新 bundle + L2 运行证据（evidence/runs/）
- 验证方式: 实跑 + trace/队列断言
- 验证等级: Level 2

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 12:31 | mw.py build --install：bundle 重建 + 全局安装成功，doctor bundle stale=False | done |
| 2 | 2026-09-08 12:33 | L2 阻塞分析：AC-008 字面落点 goal-autopilot 被 docs gate 拦截（其 SPEC 阶段缺 design 侧文档，窗口存活）→ 用户决策 9：改在当前窗口认领 key（mw-dispatch-flow-fixes，docs 完整）名下重放；spec/evidence-requirement/design 三处同步修订 | REVISED |
| 3 | 2026-09-08 14:25-14:33 | L2 实跑：task.md（type: review、无 cli/model 行）+ headless 新 bundle 窗口扫描触发 → 队列行 pi/timi → worker 6m30s → done。三项断言：① task 落 mw-dispatch-flow-fixes/workers/ ② 14 条心跳、全部间隔 30.0-30.012s≤60s（贯穿无 tool call 长生成段）③ pi/timi 默认路由完成、零人工干预。附 AC-004 现场（doctor worker_liveness alive, age_s=13）。证据：evidence/runs/l2-rerun-2026-09-08.md | PASS: VC-012 三项全符 |
| 4 | 2026-09-08 14:40 | 评审 worker 反馈处理：AC-001 精度修订（_index.md 充分条件过宽 → 按 D-001 解析链表述）；design §0 anchor 13、VC-012 同步；AC-005（exit code 枚举在 AC 行自身 + VC-008 既有 vitest，可追溯性可接受）与 AC-008「无人工干预」可观测性（= task.md 无 cli 行 + 队列行 pi/timi）在 evidence 中注记；mermaid 门禁与 AC→VC 覆盖复检 PASS | done |

### 阻塞详情（已解决）
- 2026-09-08 12:33：AC-008 字面「goal-autopilot/workers/」不可满足（该 key SPEC 阶段被 docs gate 正确拦截 + 存活窗口持有 claim）。用户决策 9：改在派发窗口认领 key 名下重放，三项断言不变。goal-autopilot 下派发被拦截本身即 D-006 语义正确的现场证据
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
