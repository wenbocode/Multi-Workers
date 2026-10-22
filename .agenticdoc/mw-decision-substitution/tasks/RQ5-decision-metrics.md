# RQ-5 — 度量：人工轮次/阻塞时长能不能测出来，以及各类决策率的算法

- key: mw-decision-substitution · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（`.agenticdoc/goal.md`）：PM 管多 Worker 并行，减少人工介入。用户 2026-10-16 重定义：jev 要替换中低风险人工决策，**目标是省人的时间**。用户已裁定：授权要分档（`disable`/`enable`/`advance`），review 在 phase 末自动出报告、key 收尾强制签收。**授权能否升级，取决于指标**——所以先要回答"这些指标现在能不能测出来"。

现状：只有 `packages/multi-workers/decision.py:945-960` 的 11 字段证据行（`ts/dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source`），没有任何"人是否介入 / 决策是否有效"的字段。

可用素材（要核实是否真的可用）：
- `.agenticdoc/_project_log.md`（每 key 一行，含 commit 与 summary）
- `.agenticdoc/<key>/pm-state.md` 的 Process Log 与 Task Status
- `.agenticdoc/<key>/workers/<task>/{task.md,output.md,trace.log,run.json}`
- `.agenticdoc/<key>/review/*` 与 `evidence/quality-gate-report-*.md`
- ledger：`recordDispatchAlarm` 写入的五行元组（`pm-orchestrator.ts:532`）
- 会话侧：pi 的 session 文件/消息记录（`packages/coding-agent/src/core/**`），是否能离线统计"人发了多少条消息"

## 审计目标（调研问题）

- **Q1 人工轮次可测性**：能不能不改代码就从已有产物统计出"某个 key 里人对 agent 说了多少次话 / 做了多少次决定"？逐个检查 Q 上文列出的素材，给 `文件:行号` 与"能/不能/需新埋点"。特别确认：pi 的会话日志落在哪、格式如何、能否按 key 或按 cwd 过滤。
- **Q2 阻塞时长可测性**：agent 等人生话的墙钟能不能算出来（例如相邻一条 assistant 结束到 user 下一条之间的间隔）？worker 侧等待（`[CHECKPOINT]` 判据触发的 triggerTurn）算不算人工等待（如果由 PM 自动回答就不算）？给出可行算法与精度限制。
- **Q3 三类比率的定义与算法**：给出精确算法（分子/分母/时间窗/去重口径）：
  1. **一致率**：jev 建议 vs 实际执行（现在只有 `disagreement=yes/no` 进 ledger detail，需要更结构化的口径）。
  2. **人工推翻率**：jev 决策生效后被人改回的比例——怎么识别"改回"（需要什么记录）。
  3. **回滚率**：决策导致返工/回滚。返工的机器信号有哪些（新任务重做同一文件、`output.md` 的 exit reason、commit 里的 revert、QG 的 blockers 计数）？
- **Q4 基线**：用现有产物能给历史 key 算出**近似基线**吗？如果可能，给出 2–3 个历史 key 的粗略数字（例如 `mw-console-storm-hardening`、`mw-jev-provider-integration`），并明确标注"哪些数字是推断、误差来源是什么"。如果不可能，说明缺哪一环。
- **Q5 存储与查询**：指标落哪（新文件 vs 扩展证据行 vs 从原始记录按需计算）？"按需计算"与"写时聚合"的取舍（append-only 约束下）。给出建议的查询接口形态（CLI 子命令 + 输出字段）。
- **Q6 授权升级的输入**：授权是否需要"样本量 + 置信下界"？给出至少两种可选做法（如 Wilson 下界 / 稀疏样本延后决策），说明各自的实现成本与对"数据不足"的处理。

## 唯一证据文件

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-decision-metrics-20261016.md`（新建，全文中文，每条结论附 `文件:行号`）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-decision-metrics-20261016.md`

## 写入禁止面

- 一切源码/配置/测试/其它 evidence 文件；禁止 `git add`/`git commit`；禁止改动其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-decision-substitution\evidence\research\spec-decision-metrics-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：`Q1/Q2` 可测性表（指标 / 数据源 / 可行 / 需补什么）；`Q3` 三个算法伪代码（≤15 行/个）；`Q4` 基线数字或"不可测"结论；`Q5/Q6` 各一节。末尾「最小埋点集」：为支撑 phase 末 review，最少要新增记录哪 4–6 个字段。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**write-first**：前 10 次写调用内先落骨架。
