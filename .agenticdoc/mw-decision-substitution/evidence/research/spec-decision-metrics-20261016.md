# spec-decision-metrics-20261016（RQ-5：决策度量可测性）

key: mw-decision-substitution / ds-rq5-decision-metrics · 类型 research · 2026-10-16
一句话裁定：**人工轮次与阻塞墙钟今天就能离线测出（数据源=pi 会话 JSONL + run.json，无需改代码）；一致率机制已就位但本项目样本为 0（DP-1 默认关）；人工推翻率与回滚率缺"决策接受/改回"的显式记录，需 4–6 个新埋点字段。**

---

## Q1 人工轮次可测性

结论：**能测（不改代码）**，唯一完整的逐轮数据源是 pi 会话日志；其余素材只能给聚合信号或定性线索。

| 素材 | 位置 / 格式 | 判定 | 依据 |
| --- | --- | --- | --- |
| 1. `_project_log.md` | 每完成 key 一行：`\| Completed \| Commit \| Key \| 核心问题 \| Supersedes \|` | **不能**测人工轮次；**能**当 key 生命周期锚（完成时刻+commit）。jev 行在 `_project_log.md:52` | `_project_log.md:5`（表头） |
| 2. `<key>/pm-state.md` | Snapshot `Started/Completed`（分钟精度）+ Process Log 文字行 | **部分**：`用户裁定/用户指令/用户要求` 行可正则提取（jev 有 3 处：`pm-state.md:68`、`pm-state.md:70`、Decisions 表 47–51 依据列），但非逐轮、无耗时、依赖 PM 手写 | `mw-jev-provider-integration/pm-state.md:8,10,47-51,68-70` |
| 3. `workers/<task>/{task.md,output.md,trace.log,run.json}` | run.json：schema/task_key/owner_key/kind/status/started_at/ended_at/exit/supersedes（`run-store.ts:43-55`）；trace.log：`[START]/[TOOL]/[HEARTBEAT]/[CHECKPOINT]` 毫秒时间戳 | worker 侧是**单人一次性派发，内部 0 人工轮次**；**能**测 worker 行为与返工信号，**不能**测人工 | `workers/jev-t03-dp1-ts-integration/run.json`；`workers/jev-t05-qg-review/trace.log` 尾部 |
| 4. `<key>/review/*` 与 `evidence/quality-gate-report-*.md` | verdict 散文：`0 blockers / 0 majors / 2 minors / 8 notes` | **能**正则提取 blockers/majors/minors 计数（回滚率输入），但无结构化字段 | `mw-jev-provider-integration/evidence/quality-gate-report-20261016.md:8`；`...-recheck.md:8` |
| 5. ledger 五行元组 | `.agenticdoc/_autopilot/auto-decisions.jsonl`，行=`{seq,phase,kind,count,detail}` | kind 枚举含 `triage-suggestion`（`pm-orchestrator.ts:538`）；detail 已带 `dp/triage_type/triage_risk/dispatched_type/disagreement/confidence_source`（`pm/triage-client.ts:340-349`）→ **一致率可测**。本项目现存 11 行、**0 条 triage 行**（`.mw/decide.json` 不存在 ⇒ 默认全关，`pm/triage-client.ts:131-148`） | `pm/pm-orchestrator.ts:645-664`；实测 `auto-decisions.jsonl` 11 行全为 out-of-scope/no-product/orphaned-keys/orphan-repair-skipped/model-error |
| 6. **pi 会话日志（关键面）** | `~/.pi/agent/sessions/--H--git-Multi-Workers--/<ISO时间>_<uuid>.jsonl`；首行 header 带 `cwd`（`session-manager.ts:474-480`），此后每条 entry 自带毫秒 UTC `timestamp`（`session-manager.ts:29-35`）。目录实测 1411 个文件（PM 窗与全部 worker 进程混在同目录） | **能**：按 cwd 过滤项目；逐轮统计人工消息 | `packages/coding-agent/src/core/session-manager.ts:29-35,474-480`；实测 2026-10-16 当日活跃 22 个会话文件 |

pi 会话日志的判别口径（实测验证）：
- **人工消息** = `type:"message"` 且 `message.role=="user"`，且**不**属于以下三类机器源：
  a. worker 会话的首条 user 消息 = 派发卡（内容含 `.agenticdoc/<key>/workers/<task>` 路径，10-16 当日 18 个此类文件，每文件恰 1 条）；
  b. 扩展注入的 custom 唤醒：`deliverPmAlert` 走 `pi.sendMessage({customType:"agent-team-loop:worker-summary"})`，在会话中是 `custom_message` 条目而非 user 消息（`pm/ui-bridge.ts:198-208`；10-16 实测 635 条）；
  c. `sendUserMessage` 型扩展提示（goal 未建立 nudge `pm/pm-orchestrator.ts:232`、/pm-save `pm/ui-bridge.ts:1215`）——这些**会**落成 user 消息，只能按 `[agent-team-loop]` 前缀过滤，best-effort（精度限制，见 Q2）。
- **per-key 归属**：worker 会话首条 user 消息带卡路径 → 精确归属；PM 窗会话跨 key，人工消息需按 key 活跃窗（pm-state Started/Completed 或 run.json min/max）做时间窗归属 → 近似（多 key 并行窗会重叠）。
- 实测（jev key 窗 2026-10-16 17:09–21:5x local，`pm-state.md:8,10`）：窗内人工消息 5 条（09:05"路线B"、09:16"D-1 修正"、09:20"按你推荐"、12:43"起 review worker"、13:23"流程图/文档"，UTC），与 Process Log 的用户指令行一一对应。

## Q2 阻塞时长可测性

结论：**能算出近似墙钟**（分钟级可信），但有 3 个精度限制；worker 侧 checkpoint 由 PM 自动应答**不算**人工等待，且两者在数据上可分离。

算法（已实测跑通）：
```
对 PM 窗会话文件 F（首条 user 非 dispatch 卡）：
  人工等待(H) = t_H − t_prev(H)
  其中 t_prev = H 之前最后一条 type∈{message(assistant), message(toolResult), custom_message} 的 entry timestamp
按 key 活跃窗过滤后求和/取中位数
```
- 时间戳为 entry 追加时刻、UTC ISO 毫秒（`session-manager.ts:29-35`），assistant/toolResult entry 在回合产物完成时落盘 → 差值≈"agent 停止工作 → 人开口"的墙钟。
- 实测（PM 窗文件 `2026-10-15T06-30-17_*.jsonl`，2026-10-16）：9 条人工消息，gap 分别 2.0/241.1/53.0/6.4/13.6/6.7/2.3/50.4/20.3 分钟；jev key 窗内 5 条合计 ≈93.3 分钟、中位 13.6 分钟。
- **checkpoint 归属实证**：`jev-t05-qg-review` 于 `11:26:10Z` 写 `[CHECKPOINT] elapsed=1800s risk=mid`（`workers/jev-t05-qg-review/trace.log` 尾部）→ `11:26:13Z` PM 收 custom_message 唤醒（会话实测）→ `11:26:17Z` PM 自主开查、随后杀掉重派 t05b（`pm-state.md:65`）。全程 3 秒级、0 人工参与 → 由 PM 自动回答的 checkpoint 不计入人工等待，且因走 `custom_message` 通道天然被过滤掉（`pm/pm-orchestrator.ts:1683-1687`）。

精度限制：
1. **blocked vs idle 不可分**：gap 只测"人多久没说话"。241.1 分钟那条是 PM 干完活等人发起新任务的纯空闲，不是阻塞；要区分需"PM 结束回合时是否留有待答问题/待应答 gate"标记（→ 埋点 E3）。2026-10-19 当日 4 条消息 gap 合计 4088 分钟（中位 70.6 分钟），即为纯空闲放大的反例。
2. **`sendUserMessage` 型扩展提示混入**：前缀过滤是启发式（Q1-c）。
3. **多窗口并行**：10-16 存在第二活动窗（文件 `2026-10-16T03-51-18_*.jsonl`，15:27–17:14 local 有 4 条人工消息），同一人的等待会分散到多窗；per-key 归属在多 key 并行窗重叠时只能近似。

## Q3 三类比率的定义与算法

### 3.1 一致率（jev 建议 vs 实际派发）
- 分子：时间窗内 `triage-suggestion` 行中 `disagreement=no` 的行数；分母：`triage-suggestion` 行总数（`confidence_source=api` 的行，硬规则 D-5，`pm-state.md:51`）。时间窗=key 活跃窗或 --since。去重：每行 count=1 天然一行一次（`pm/ui-bridge.ts:262`）。
```
agree(rate) :
  rows = ledger.lines.where(kind=="triage-suggestion" && detail.confidence_source=="api")
  hit  = rows.where(detail.disagreement=="no").count
  return {n: rows.count, rate: hit/rows.count}
```
- 现状：机制在（`pm/triage-client.ts:340-349`），样本=0（`auto-decisions.jsonl` 无 triage 行 + `.mw/decide.json` 缺失默认关）。detail 是空格分隔 KV 字符串，可正则解析，但建议升级为行尾 JSON（→ 埋点 E1）。

### 3.2 人工推翻率（jev 决策生效后被改回）
- 识别"改回"需要**决策→任务→后续人工动作**的链接记录，今天没有：ledger 行不带任务 key，会话日志只有散文。可行近似：jev 建议类型 T 的派发完成后，同 key 后续出现人工消息触发的、类型 ≠ T 的重派/修正（按时间窗 + session 文本匹配 key 名）。精确口径必须新埋点（→ E2）。
```
override_rate :
  pairs = [(s.row.seq, dispatch.task_key, s.detail.triage_type)]   # 需 E1/E2 链接
  overturned = pairs.where( exists human_msg h in key window
                            after dispatch ended
                            and h 触发的后续任务.type != s.detail.triage_type )
  return overturned.count / pairs.where(accepted).count   # 分母=被接受的建议数
```

### 3.3 回滚率（决策导致返工/回滚）
机器信号（按可信度排序，均已实测存在）：
1. `run.json.status ∉ {done}` 且进程死亡（watchdog 杀树/模型耗尽）：jev-t05 `status=running` 无 ended_at；`output.md` 头 `<!-- mw-run: ... status=failed -->` + "Model exhausted"（`workers/jev-t05-qg-review/output.md:1`）。
2. 同 key 内新任务承接旧任务：`task.md supersedes:` 头 → run.json.supersedes（`shared/run-store.ts:49-50`、`worker/worker-mode.ts:2621`）；但实测 t05→t05b 重派**未用** supersedes，需约定强制（→ E4）。
3. QG blockers/majors>0 触发快修任务（jev-t07 3.1 分钟，`workers/jev-t07-b2-refeed-quickfix/run.json`；报告 `quality-gate-report-20261016.md:8` 4 minors）。
4. ledger `model-error` 连击行（`pm/pm-orchestrator.ts:769`）与 `no-product` 行。
5. git revert commit（`_project_log.md:5-6` Commit 列可 grep `revert`）——本仓库基线期暂无。
```
rollback_rate(key, window) :
  runs    = key.workers.*/run.json
  rework  = runs.where(status!="done")                      # 信号1
              + runs.where(supersedes 或 同前缀重派, 需 E4)   # 信号2
              + quickfix 任务.where(前驱 QG.blockers+majors>0) # 信号3
  return {n: runs.count, rework: rework.count, rate: rework.count/runs.count}
```

## Q4 历史基线（现有产物可算近似值）

**能**给出近似基线，标注推断与误差：

| 指标 | mw-jev-provider-integration（2026-10-16） | mw-console-storm-hardening（2026-10-15） |
| --- | --- | --- |
| key 生命周期 | 17:09→19:52（163 min，`pm-state.md:8,10`）；Process Log 尾延至 21:2x（`pm-state.md:70`） | 14:40→23:15（515 min，storm `pm-state.md:7-10`） |
| worker 墙钟 | **139.0 min**（13 个 run.json 求和：4 research/6 coding/3 review；t05 被杀无 ended_at 未计入，推断真实 ≈169 min，误差=被杀 run 实际耗时） | 未逐个核算（同法可得；推断误差同上） |
| 人工消息（key 窗内） | **5 条**（推断：session user 消息按 key 时间窗过滤；误差=多窗并行 10-16 第二窗 4 条未计入，若归属 jev 则 9 条） | 弱：PM 窗当日 17 条人工消息跨 storm+jev 筹备多 key，无法干净归属（误差来源：时间窗重叠） |
| 人工等待墙钟 | 窗内 5 条 gap 合计 **≈93.3 min**、中位 13.6 min（推断：含"人思考+打字"时间；且无法剔除 blocked/idle） | 当日 sum≈369.6 min / 中位 5.0 min（跨 key，仅量级参考） |
| 一致率 | **不可测**：DP-1 上线当日 `.mw/decide.json` 未启用，ledger 0 条 triage 行（缺环=配置+样本） | 不可测（同因） |
| 返工 | ≥2 次：t05 被杀重派 t05b（22.1 min）、t07 快修（3.1 min）；QG 两轮 0 blockers/0 majors（`quality-gate-report-20261016.md:8`、`-recheck.md:8`） | 快修 1 轮（4 minors 处置，storm `pm-state.md` Evidence Ledger QG 行）；4 commits（13a0ce4de/4980da301/3c02d7227/bf2547cce） |

缺的一环：**一致率/推翻率基线为 0 样本**——需要 `mw decide` 启用运行一段时间才有；这正是"授权升级先开 DP-1 采集"的论据。

## Q5 存储与查询

建议：**混合——原始行继续 append-only（写时埋点），指标读时聚合，phase 末 review 由 CLI 生成报告段**。不建新的聚合状态文件。
- 理由：append-only 已有三条流——`triage-decisions.jsonl`（Python 决策证据行，`decision.py:74` 路径、`decision.py:940-967` 写入，11 字段 `decision.py:121-131`）、`auto-decisions.jsonl`（TS ledger 五行元组，`pm-orchestrator.ts:645-664`）、per-task `run.json`（`run-store.ts:43-55`）。数据量极小（本项目 ledger 11 行、jev run 13 个），按需计算成本可忽略；写时聚合会引入第二写者与锁，违背现有单写者契约（`pm-orchestrator.ts:641-644`）。
- 查询接口形态：`mw decide metrics [--key K] [--since 2026-10-16] [--window key|day] [--format table|json]`，输出字段：`suggestions / disagreements / agree_rate_wilson_lb / human_msgs / human_wait_min(p50,p90,sum) / rework_n / rework_rate / rollback_commits`。数据源 join：ledger + triage-decisions + run.json + `~/.pi/agent/sessions/<encoded-cwd>/*.jsonl`（`session-manager.ts:474-480`）。phase 末 review：`mw decide metrics --key K --format table` 输出直接粘进 `quality-gate-report-*.md` 的新小节（报告已是散文+数字混排，`quality-gate-report-20261016.md:8`）。

## Q6 授权升级的输入

需要"样本量 + 置信下界"两者兼备，给两种做法：

1. **Wilson 95% 下界（推荐主判据）**：`LB = wilson_lower_bound(hit, n)`；升级条件 `n≥N_min(建议 30) 且 LB≥阈值(建议 0.9)`。实现成本：纯函数 ~15 行 + 埋点 E1/E2 提供分子分母。数据不足（n<N_min）→ LB 无意义 → 判定函数自动返回 `hold`，不会误升级。
```
wilson_lb(hit, n, z=1.96) :
  if n == 0: return 0
  p = hit/n; d = 1 + z*z/n
  c = p + z*z/(2*n); s = z*sqrt(p*(1-p)/n + z*z/(4*n*n))
  return (c - s)/d
upgrade_decision :
  return "advance" if n>=30 and wilson_lb(...)>=0.9 else "hold"
```
2. **稀疏样本延后（最小成本兜底）**：不做统计推断，只设双门——最小样本数 N_min + 最小观察时长（如 DP-1 连续运行 ≥2 周、≥K 个 key 完成）。实现成本≈0（两个计数比较）；代价是解锁慢、对高一致率小样本过于保守。可与做法 1 并用：N_min/时长不过 → 直接 `hold`，过了才看 Wilson LB。
- 补充：Beta 后验下界（`Beta(hit+α, n-hit+β)` 分位数）与 Wilson 成本相同，优点是可注入先验（如"coding 类型建议先验更准"），列为备选。
- 硬约束沿用 D-5：`confidence_source != api` 的样本一律不进门控（`pm-state.md:51`）。

## 最小埋点集（支撑 phase 末 review，最少新增 4–6 个字段）

| # | 字段 | 落点 | 写者/时机 | 支撑 |
| --- | --- | --- | --- | --- |
| E1 | `triage-suggestion` ledger 行 detail 追加 `task_key`（或行尾 JSON 化：`{dp,triage_type,triage_risk,dispatched_type,disagreement,confidence_source,task_key,ts}`） | `auto-decisions.jsonl`（append 不改 schema） | `emitDispatchTriage`（`pm/ui-bridge.ts:258-267`），派发时已有 task 上下文 | 3.1 一致率、Q4 基线 |
| E2 | `decision_outcome ∈ {accepted,overridden,ignored}` + `decider ∈ {pm,human}` | 同上一行后续追加行（`kind:"triage-outcome"`），携带 `suggestion_seq` 外链 | PM 派发落定时（`pm-orchestrator` 派发路径）；人工 steer 时由 PM 以 human 身份写 | 3.2 推翻率、Q6 分母 |
| E3 | `awaiting=human` 标记：PM 回合结束且留待答问题/gate 时在会话写 `custom` 条目（复用 `agent-team-loop:watch` 通道模式，`session-manager.ts:96-103`） | 会话 JSONL | PM 回合结束钩子 | Q2 blocked/idle 区分，等待墙钟去噪 |
| E4 | `rework_of: <task_key>`：task.md 头新字段（与 `supersedes` 并列，`worker/worker-mode.ts:2621` 解析处 +1 行），重派/快修卡强制填写 | task.md → run.json | 派发卡生成处 | 3.3 回滚率信号 2 补漏（t05→t05b 实测未用 supersedes） |
| E5 | `blockers/majors/minors` 结构化行：QG 报告头部加一行机器可读 front-matter（`<!-- qg: blockers=0 majors=0 minors=4 -->`） | `quality-gate-report-*.md` 头部 | QG worker 模板 | 3.3 信号 3、review 段聚合 |
| E6 | key 人工轮次快照：`advance_phase done` 时把 `{human_msgs, human_wait_min_sum}` 追加进 `_project_log.md` 该行（或 achieved.md） | `_project_log.md:5-6` 表行扩展列 | advance_phase 脚本（跑 Q2 算法一次性） | Q1/Q2 的跨 key 时间序列免重算 |

其中 E1、E2、E4 为一致率/推翻率/回滚率的**最小充分集**；E3、E5、E6 把 Q2 从"近似"提升为"可审计"。
