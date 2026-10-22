# RQ-D4 — 决策建议的反馈通道：既有 PM 可见面盘点与推荐路径

- key: mw-jev-provider-integration · type: research · DESIGN 相位调研
- timeout: 40

## 上下文

本 key 的 DP-1（派发前分诊）产出的是**旁路建议 + 置信度**（不改派发行为）。设计必须回答：这条建议写到哪里，PM 才会自然看到，而不是又造一条只有机器看得见的通道。

goal.md 第 2 条（有效反馈）。已知锚点：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1698-1731`（终端 readback：`deliverWorkerResult`/`deliverPmAlert` + `triggerTurn`）、`pm-orchestrator.ts:623-641`（`recordDispatchAlarm` 写 autopilot ledger）、`pm-orchestrator.ts:601-604`（`describeDispatchAlarm`）、`packages/multi-workers/mw_common.py:4460-4496`（doctor 行）。

## 审计目标（调研问题）

- Q1 终端 readback 机制：worker 终态结果如何被注入 PM 会话（`deliverWorkerResult`/`deliverPmAlert` 的触发条件、数据来源、`triggerTurn` 语义、去重/节流）；给 path:line。
- Q2 PM 侧告警面：派发告警（dispatch-alarm）与 model-error 告警各写到哪里、ledger 行格式与 `phase=` 取值、谁读它、PM 何时被唤醒；给 path:line。
- Q3 autopilot 侧的 PM 可见面：`.agenticdoc/**` 下有哪些文件会被 PM/conductor 读取并呈现（台账、报告、证据文件），哪些是"写了但没人看"的死面。
- Q4 候选落点对比表：把"DP-1 建议 + 置信度"送到 PM 的最小改动路径候选（例如：新增一条 ledger/alarm 行 / 写进既有的派发回执文件 / 写进 worker trace 并由 readback 带出 / 只进 doctor），每项给出：实现位置（path:line）、改动量、是否触发 PM 唤醒、是否与并行 key 冲突、失败影响。
- Q5 命名与格式避让：既有机器可读行/告警类型/phase 值的**完整清单**（含 TS 侧常量与 Python 侧前缀），用于给决策建议选一个不撞名的标识；同时确认 `confidence` 与"来源标识"（`api` vs `model-self-report`）放在哪个字段最自然。
- Q6 结论：推荐通道（单一首选 + 备选）+ 理由（PM 自然会看到 / 改动最小 / 无并行冲突）+ 该通道下"决策不可用时"的降级呈现（必须能与"决策已生效"区分）。

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-feedback-channel-20261016.md`（新建，全文中文，每条结论附 文件:行号）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-feedback-channel-20261016.md`

## 写入禁止面

- 一切源码/配置；禁止 git add/commit；禁止写入其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\design-feedback-channel-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：六问逐条结论（含 path:line）+ 「候选落点对比表」+ 「既有标识/前缀清单」+ 「推荐通道与降级呈现」。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
