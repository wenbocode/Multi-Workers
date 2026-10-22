# RQ1 — `signed_via` 词表与签收四张脸的消费方清单

- type: research
- owner key: mw-signoff-decide-only
- 唯一证据文件：`.agenticdoc/mw-signoff-decide-only/evidence/research/spec-signoff-faces-20261022.md`

## 上下文

项目目标见 `.agenticdoc/goal.md`（PM 管理多 Worker 并行，中低风险决策交给决策模型而不是人）。本 key 要把收尾签收从"人签"改为"决策模型签"，删掉 `auto-llm` / `cli` / `tui` 三张脸，只保留 `auto-decide`。设计前必须知道删掉它们会波及哪些消费方，否则会留下半死分支。

已知锚点：

- `packages/multi-workers/decide_signoff.py` — `AUTO_SIGNED_VIA`、`SIGNED_VIA_VALUES`、`write_signoff` 的 agent-session 拒绝、`auto_conclusion`。
- `packages/multi-workers/mw.py:3996` 起 `_decide_sign`（四张脸分流），`:11730-11770` argparse 定义。
- `packages/multi-workers/decision_history.py` — `signed_via` 的解析与 basis 归类（约 `:713`、`:1768-1815`、`:2148`）。

## 要求（只读）

1. 穷举 `signed_via` 的**所有**读写点（ts + py + js + docs + tests），逐条给出 `path:line` 与用途，区分：
   - 生产者（写这个值的地方）
   - 消费者（读这个值做判断的地方）
   - 仅展示（dashboard / 报告）
2. 列出 `AUTO_SIGNED_VIA`、`SIGNED_VIA_VALUES`、`AGENT_SESSION_ENV_VARS`、`write_signoff(allow_agent_session=...)` 的每个调用点。
3. 判断删除 `auto-llm|cli|tui` 后哪些地方会**编译/类型/测试失败**（给出具体符号），哪些会静默降级（值不再出现但代码仍接受）。
4. 找出 `decision_history.py` 里把 `signed_via in ("cli","tui")` 归为 `human_basis` 的逻辑：删掉这两个值后，`human_basis` / `system_basis` 的分类是否需要新分支，还是自然退化。
5. 回答：`signed_via` 是否被 `advance_phase.py` 的门禁读取（给证据），如果不是，说明它只是审计字段。

## 写入允许面

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-signoff-faces-20261022.md`
- `.agenticdoc/mw-signoff-decide-only/workers/sdo-rq1-faces/**`

其它文件一律只读。

## 交付格式

Markdown，四节：

1. `## 读写点总表`（表格：path:line | 值 | 角色 | 删除后影响）
2. `## 删除面`（符号清单 + 失败类型）
3. `## 分类逻辑`（`human_basis`/`system_basis` 的处理建议，含行号）
4. `## 结论`（≤10 行，回答"是否只是审计字段"）

每条断言必须带 `path:line`；不确定的写"未验证"而不是猜。只写这一个文件，不改任何源码。
