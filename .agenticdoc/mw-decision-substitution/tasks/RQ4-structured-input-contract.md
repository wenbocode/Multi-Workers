# RQ-4 — 每个决策点的最小结构化输入 + 脱敏分层

- key: mw-decision-substitution · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（`.agenticdoc/goal.md`）：PM 管多 Worker 并行，减少人工介入。用户 2026-10-16 重定义：jev 要**替换**中低风险人工决策。要替代人的判断，输入质量是上限：现在 DP-1 是把派发描述**截断 16KB 的纯文本**喂给模型（`pm/triage-client.ts:44` `MAX_TRIAGE_STATE_BYTES = 16_000`），这不足以支撑"替代人"。

另外用户在 2026-10-16 明确要求：`state` 经内网 llmproxy 发给 B2 模型，**不得包含凭据/敏感原文**。

已知锚点：
- 现状输入构造：`pm/ui-bridge.ts:241-247`（`planDispatchFrontmatter` 内组装 state）
- 预算与校验：`packages/multi-workers/decision.py`（`max_state_bytes` / `max_questions` / `max_tokens`）、`mw_common.py:224-252`（fail-soft 配置读）
- 问题类型：`decision.py:104`（`QUESTION_TYPES`：choice/score/noul/box；B2 不支持 box）
- 已有结构化产物（可作输入源）：`tasks/*.md` 卡片、`_workers.parallel` 行、`pm-state.md`、`workers/<task>/run.json` + `trace.log` + `output.md`、`_project_log.md`、`review/` 证据

## 审计目标（调研问题）

- **Q1 输入源盘点**：对 RQ-1 的决策类别（若证据未到，按"派发前 / 执行中 / 收尾 / 处置"四类）分别列出**可从仓里直接读到的结构化字段**：卡片 frontmatter、任务类型、风险标注、受影响文件白名单、历史同类任务的结果（成功/返工/回滚）、失败模式（最近 N 条的 `runner.error_kind`/`[MODEL_ERR]`/exit code）、当前阶段、预算剩余。每项给 `文件:行号`，并标注"可得 / 需解析 / 不存在"。
- **Q2 最小充分输入**：对每一类决策，回答"人做这个判断时会看哪 3–7 个字段"。给出一张表：决策类别 → 必需字段 → 可选字段 → 明确**不需要**的字段（避免把全文塞进去）。
- **Q3 脱敏分层**：把可能的字段按敏感度分三级（可外发 / 需摘要 / 绝不外发）。至少要覆盖：文件绝对路径、代码片段、用户原话、凭据（`TIMI_API_KEY`/`ZAI`）、内部域名与端口、个人信息。给出**机读规则**（正则/白名单）建议，以及"脱敏后如何仍保持决策有效性"的做法（例如路径只留相对路径与扩展名、代码只留符号名）。
- **Q4 体积与成本**：结构化输入的目标体积（token 量级）与现有 16KB 文本的对比；如果要做缓存（同 `(dp, state_digest)` 复用），digest 应该覆盖哪些字段（哪些字段变了必须让缓存失效）。
- **Q5 现有校验的适配**：`decision.py` 现在校验 `questions` 形状与预算；引入结构化 `state`（JSON 对象而非纯文本）需要改哪些校验点？向后兼容怎么做（旧调用方传字符串）？给 `文件:行号`。
- **Q6 失败模式**：结构化输入缺失关键字段时该怎么做（禁止默认动作 → 上抛人）；给出"字段完整性"的判定规则（required / optional / 缺失即拒绝）。

## 唯一证据文件

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-structured-input-contract-20261016.md`（新建，全文中文，每条结论附 `文件:行号`）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-structured-input-contract-20261016.md`

## 写入禁止面

- 一切源码/配置/测试/其它 evidence 文件；禁止 `git add`/`git commit`；禁止改动其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-decision-substitution\evidence\research\spec-structured-input-contract-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：`Q1` 现有字段盘点表；`Q2` 决策类别 × 最小字段表；`Q3` 三级敏感度表 + 机读规则；`Q4/Q5/Q6` 各一节。末尾给出**一个 state schema 草案**（字段名 + 类型 + 必填性 + 敏感级），可直接进 design。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**write-first**：前 10 次写调用内先落骨架。
