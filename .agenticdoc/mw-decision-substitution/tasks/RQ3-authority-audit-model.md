# RQ-3 — 授权状态机 + 决策档案 schema + phase/收尾 review 判据

- key: mw-decision-substitution · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（`.agenticdoc/goal.md`）：PM 管多 Worker 并行，减少人工介入。用户 2026-10-16 重定义：jev 要**替换**中低风险人工决策，因此必须解决"凭什么相信它"的问题。用户已裁定三件事（不要再论证是否需要，直接按此设计）：
- 授权三档：`disable`（全关）/ `enable`（**默认**，仅 P2 可 binding）/ `advance`（P1+P2 可 binding）；P0（不可逆/凭据/对外通信/花钱/删他人工作/人已表态）**永不委派**。
- review 节奏：每个 phase 末自动出报告；每个 key 收尾**强制签收**，签收结论 `continue`/`narrow`/`revoke` 必须能**写回配置**。
- 失败/低置信/超授权面 → 一律上抛人，禁止默认动作。

已有底座（要复用，不要另造）：
- 决策客户端与证据行：`packages/multi-workers/decision.py:74`（`EVIDENCE_RELATIVE_PATH`）、`:945-960`（证据行 11 字段）
- 结论枚举：`decision.py:88-99`（`REASON_CODES` 8 类）
- 配置：`.mw/decide.json` + `DecisionConfig`（`decision.py`）+ `mw.py:672`（`_DECIDE_SET_KEYS`，`set` 只接受白名单键）
- ledger：`ui-bridge.ts:258` `emitDispatchTriage` → `recordDispatchAlarm`（五行元组 seq/phase/kind/count/detail，`pm-orchestrator.ts:532-563` 的 kind 白名单）
- 门禁与相位：`.agents/skills/agentic-task/core/scripts/advance_phase.py:191`（`check_gate`）、`:292`（`update_pm_state`）

## 审计目标（调研问题）

- **Q1 授权状态机**：给出可实现的晋升/降级规则。要回答：用什么指标决定晋升（建议 vs 实际一致率？结果回滚率？人工推翻率？样本量 N 取多少）；如何避免小样本噪声（滑动窗口 / 置信下界 / 最小样本）；降级的触发条件与冷却期；`advance` 档下 P1 是否要**逐类**授权（而不是一刀切全开）；状态存在哪（`.mw/decide.json` 的哪个键，还是独立 `.mw/decide-authority.json`）；与现有 `_DECIDE_SET_KEYS` 白名单如何兼容。
- **Q2 决策档案 schema**：设计一行一条的 decision record。必须解决：`decision_id` 生成规则（可幂等、可在日志里反查）；如何记录"输入指纹"而不存原文（state_digest 用什么算法/截断）；如何记录"是否真的生效"（`acted`）与"实际动作"；如何记录结果（`outcome: ok|rework|rollback|pending`）以及**结果如何回填**（谁来更新这一行——append-only 时是新增结算行还是原地改）；如何记录人工推翻（`human_override` + 理由）；`prompt_version`/`questions_version` 怎么定。
- **Q3 结果关联（关键）**：决策发生后，怎么把"后来发生的事"挂回该决策？仓里现有哪些可关联的证据（`workers/<task>/run.json`、`trace.log`、`output.md`、`_project_log.md`、pm-state Process Log、ledger）？给出可落地的关联机制（例如 dispatch 时把 `decision_id` 注入 task.md 头，worker 终态时由 PM 结算；或按 `(key, task_key)` 关联）。若某些结果无法可靠关联，明确写"只能人工标注"。
- **Q4 review 报告结构与判据**：phase 末报告要回答哪几个问题、用什么判据算通过（给出具体阈值建议与"数据不足时不结论"的规则）；报告放哪（`evidence/` 命名规范）；key 收尾签收怎么强制（门禁？），签收结论如何写回授权档并留痕。
- **Q5 不可篡改**：append-only 怎么保证（无 update 路径 / 每行 `prev_sha` 哈希链 / 只追加文件），以及"结算行"与"原始行"的读侧合并规则（`mw decide show`/doctor 现在只读最后一行，扩展后怎么读）。
- **Q6 与既有格式的兼容**：现有 11 字段证据行（`triage-decisions.jsonl`）是否保留、升级还是并存？升级方案要给出旧行可读（向后兼容读取）的具体做法。

## 唯一证据文件

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-authority-audit-model-20261016.md`（新建，全文中文，每条结论附 `文件:行号`）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-authority-audit-model-20261016.md`

## 写入禁止面

- 一切源码/配置/测试/其它 evidence 文件；禁止 `git add`/`git commit`；禁止改动其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-decision-substitution\evidence\research\spec-authority-audit-model-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：`Q1` 状态机（状态 + 迁移条件 + 存储位置）；`Q2` decision record 字段表（字段 / 类型 / 来源 / 是否可缺）；`Q3` 关联机制一节（含无法关联的清单）；`Q4` 报告骨架 + 判据表；`Q5/Q6` 各一节。末尾「最小可用版本（MVP）建议」：先做哪几条字段/规则就够 review，避免一次设计过大。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**write-first**：前 10 次写调用内先落骨架。
