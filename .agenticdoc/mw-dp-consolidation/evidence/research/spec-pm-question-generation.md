# RQ7 现状审计：PM 的问题枚举 / 描述 / 报人

只读静态审计，主审 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（2680 行，全文读完）。未跑测试/构建/服务，未调用 ask_decision/provider。

## 结论

1. **不存在系统统一问题枚举器。** 机器侧唯一成形的“问题集”是决策点注册表里每个 dp 固定的 question 清单，枚举的是“该决策点允许问哪些问题”，不是“当前项目/任务有哪些未决问题”：`pm-orchestrator.ts:1969-1971`（`DP2_QUESTIONS_CANONICAL = checkpoint_action ∈ narrow|split|direct-exec|escalate`，配 `DP2_QUESTIONS_VERSION`）、`worker/worker-mode.ts:5010`（`DP3_QUESTIONS_VERSION = "q-fcbd3847"`，注释说明问题集在 Python registry）、`pm/triage-client.ts:25-27`（“问题集 authoritative in the Python decision registry；TS 不再持有字面量”）。无任何函数扫描任务/产物生成问题列表。

2. **实际存在三类“问题来源”，全部由 PM 模型自行整合或机器模板生成，二者未在同一载体上合流：**
   - **(a) PM 模型按上下文自拟**：载体是固定提示词 `PM_CONTINUE_HINT`（`pm-orchestrator.ts:1869-1870`）：“needs-clarification→整理问题向用户澄清”。这里只有指令，没有结构、没有落盘、没有与 task_key 绑定的 question 字段；问题最终是模型在本轮回复里自然语言写出的。
   - **(b) 机器抽取既有产物/失败摘要**：`ui-bridge.ts:1112 readTerminalDetail` 的 needs-clarification 分支（1121-1124）取 `## Questions` 首行 → 回退 `worker.log` 末行（`readWorkerLogTail`, 1076-1091）→ 回退 `"no output.md"`；该 detail 只进 widget 行（`ui-bridge.ts:1316` 于 `renderWatchLines`/`rowLine`，`WATCH_LINE_MAX` 截断）。而 `## Questions` 正文本身是**机器模板**而非 worker 自由提问：`worker/worker-mode.ts:4415-4423` 计算一次 `questionsText = evidence.delivered ? (gaps.ok ? undefined : "recovery-incomplete: <gapsReason>") : "no-product: <evidence.detail>"`，经 `output-writer.ts:587` 写盘；gapsReason 来自 claim/gap/ledger 机器判据（4405-4413）。
   - **(c) 固定措辞告警/提醒**：dispatch alarm 文本模板 `describeDispatchAlarm`（`pm-orchestrator.ts:593`）+ 判定前缀 `formatDispatchAlarm`（649，`提示` vs `已拒绝`）；`no-product` 固定写 “needs-clarification, awaiting human judgement”（622）；checkpoint 发散唤醒固定文本 + 证据路径（2220-2227）；doc-gate 跳过通知 `makeScopedDocGateNotifier`（`ui-bridge.ts:1453`）；gate reminder 固定文本（`pm-orchestrator.ts:2366-2370`，来源 `autopilot/status-model.ts:1222 readGateReminders` 读 `.agenticdoc/_autopilot/auto-decisions.jsonl` 的 `phase:"remind"` 行，阈值判定在 Python conductor）。

3. **结构化决策材料是“提问者自填”，一决策一问题。** dp3 的 `question/background/handling_options` 由调用方模型填（`decision-tool.ts:759-763` 的 dp3 准备提示；`worker/worker-mode.ts:5363-5366` `Dp3DecisionInput.material` 注释：“The ASKING agent's business material … When absent the clarification is NOT answered from local guesses — the human path proceeds”）。worker 侧传给 dp3 的 question 串是机器拼的 `evidence.detail; gapsReason`（`worker-mode.ts:4426`）。没有把多个任务的未决问题聚合、去重或排序的机器逻辑。

4. **“报 PM”与“报人”是两条不同通道，且只在极少数位置才真正触达人：**
   - **报 PM** = `deliverPmAlert`（`ui-bridge.ts:218`）：`pi.sendMessage(..., {triggerTurn:true})`，仅唤醒/steer PM 的 LLM turn；`deliverWorkerResult`（232）是同一通道的别名。终态回读走它（`pm-orchestrator.ts:2296/2303`），doc-gate、dispatch alarm、checkpoint 唤醒亦走它（2537、2562、2220）。
   - **报人**只有三处可指认：gate reminder 文本显式给出人工应答动作 `/autopilot gate <id> approve|reject`（`pm-orchestrator.ts:2368-2370`，应答写入器 `autopilot/gate-writer.ts:2`）；决策服务不可用时的契约“上报 `blocked on decision <dp>` 并等待人工裁决”（`decision-tool.ts:1136-1141 unavailableDirective`，机器不再有第二步）；`/goal` 提醒用 `pi.sendUserMessage` 直接对用户发起（`pm-orchestrator.ts:245-255 nudgeGoalUnestablished`）。
   - **本扩展无 ask_user 类工具**：grep 全 `agent-team-loop` 无 `ui.select/ui.input/ui.confirm`、无 `ask_user|request_human|askHuman`；PM 工具表面只有 `mw_status`(ui-bridge.ts:1703)、`dispatch_worker`(3120)、`ack_worker_result`(3459)、`switch_key`(3563)、`advance_phase`(3650) 加 ask_decision/decision_receipt。

5. **唤醒 ≠ 提问，通知 ≠ 回答绑定。** `## Questions` 首行只进 widget 展示（理由同上 4 的 detail 通路），用户口头回答没有任何写回 task/queue/decision 的路径；唯一带 id 绑定的问答是决策服务（`ask_decision` → `decision_id` → `decision_receipt`，`decision-tool.ts:1841-1843`）。机器明确把“下一个主体是人”写在注释而非队列里：`pm-orchestrator.ts:843` “needs-clarification | NO row（the human is the next settle subject）”，`mapTerminalToSettle` 875-876 因此不写 settle 行。`escalate_to_human` 也是“记录不告警”（`triage-client.ts:26/356`，消费点 `ui-bridge.ts:642` 仅用于 skipReason），不会叫醒任何人。

## 证据

| 生产者 | 载体 | PM 消费者 | 人工出口 |
|---|---|---|---|
| PM 模型自身（无工具） | 本轮自然语言回复 | 用户直接看到 | 仅模型自己措辞；无结构、无 id |
| `PM_CONTINUE_HINT`（pm-orchestrator.ts:1869-1870） | 注入 PM 上下文的固定提示词 | PM 模型 | 无（"整理问题向用户澄清" 是给模型的指令） |
| worker 终态产物 | `output.md` `## Questions`（机器合成，worker-mode.ts:4415-4423 + output-writer.ts:587） | `readTerminalDetail`（ui-bridge.ts:1121-1124）→ widget 首行；全文经 `readOutputBody` 进 PM readback（pm-orchestrator.ts:2294-2296） | 无；用户只能看到 PM 转述 |
| conductor（Python） | `_autopilot/auto-decisions.jsonl` `phase:"remind"` 行 | `readGateReminders`（status-model.ts:1222）→ poll loop（pm-orchestrator.ts:2318-2370）→ `deliverPmAlert` | 有：文本给出 `/autopilot gate <id> approve|reject`（gate-writer.ts:2） |
| 扫描/判据（TS） | dispatch alarm 行 `_autopilot/auto-decisions.jsonl` + `deliverPmAlert` 文本 | `describeDispatchAlarm`/`formatDispatchAlarm`（593/649） | 无（no-product 622 只写 "awaiting human judgement"，无应答动作） |
| checkpoint 机器判据（worker trace `[CHECKPOINT]`） | `readCheckpointTrend`（2000）/`readTaskProgress` | poll loop 2220-2227 `deliverPmAlert` | 无（提示 PM 自己判断 continue/narrow/终止分拆/直执） |
| 提问方模型（PM 或 worker） | decision 材料 `question/background/handling_options` | 决策服务 → `ask_decision` 返回 payload | 仅 unavailable 时："上报 blocked on decision \<dp\> 并等待人工裁决"（decision-tool.ts:1136-1141） |
| 扩展自身 | `pi.sendUserMessage` | 直接对用户（nudgeGoalUnestablished，245-255） | 有，但只用于 goal 未确立提醒 |

补充事实：
- dp2 机器通路已被显式退休：`pm-orchestrator.ts:2081-2092` 注释“RETIRED … dp2 是 PM-INITIATED decision only”，poll loop 里对 dp2 只有唤醒、无提问、无执行（`pm-orchestrator.ts:2146`、`2210-2213` 注释）。
- 机器摘要有明确的不猜测边界：`recordDecisionSettle`（1054）对无 `decision:` 头的任务记 `no-decision-header` 而不是猜关联；`planDecisionSettle` 的幂等键是 `(decision_id, outcome, run_id)`（pm-orchestrator.ts:905-935）。
- 唯一“问题序号”概念是 worker 侧 `nc<N>`（`worker-mode.ts:5348`，dp3 澄清事件序号），是**同类澄清的计数**，不是跨任务问题清单。

## 残留与未验证

- 未全文读外围文件（仅按需读片段，属声明而非全链断言）：`ui-bridge.ts`（4110+ 行，读了 195-264、630-690、1060-1180、1290-1350、1440-1470）、`decision-tool.ts`（读 1100-1170、字符串 grep）、`worker/worker-mode.ts`（读 4404-4463、5085-5145、5340-5395）、`triage-client.ts`（读 18-48、grep）、`autopilot/status-model.ts`（读 1195-1265）、`autopilot/gate-writer.ts`（仅读头注释）。
- Python 侧未读：conductor（reminder 阈值、gate 创建）、`decision_points.py` registry、`gates.py`；本审计对这些只通过 TS 镜像注释引用。
- 运行中 bundle 与模型实际效果未知：PM 实际会把问题问到多清楚、会不会漏问或一次问多个、`## Questions` 首行被 widget 截断后 PM 是否仍读到全文以外的信息，均属运行时行为，静态无法确认。
- 边界：RQ8（DP 返回/动作执行）与 RQ9（决策材料注入 API）按卡不算本 RQ；本文件未评价其实现是否正确。
- 未验证“用户回答后系统是否在别处（如 session entry / 快照）隐式绑定任务”——只确认扩展内无工具/无写回路径。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq7-pm-question-generation/task.md`（card `tasks/RQ7-pm-question-generation.md`, sha256 6f2657c4…6131c）
- 目标锚点：`.agenticdoc/goal.md:5`
- 入口：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（全文 2680 行）、`.../pm/ui-bridge.ts:1121`（实为 1112 起 `readTerminalDetail`，needs-clarification 分支 1121-1124）
- 引用文件：`pm/decision-tool.ts`、`pm/triage-client.ts`、`worker/worker-mode.ts`、`worker/output-writer.ts`、`autopilot/status-model.ts`、`autopilot/gate-writer.ts`
- 本审计为只读静态：未执行 tests/build/install/commit，未调用 ask_decision/provider 探针，未起停服务，未读凭证/活 gate/ledger。
