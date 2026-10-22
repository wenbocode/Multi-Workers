# RQ-1 — 决策点普查：全仓"现在会停下来等人"的位置清单

- key: mw-decision-substitution · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（`.agenticdoc/goal.md`）：PM Agent 管多个 Worker 并行开发，减少人工介入。用户 2026-10-16 重定义：**jev 是决策模型，目标是替换中低风险的人工决策**（省掉人出现与等待的墙钟），因此第一步必须把"现在会去找人"的所有位置枚举清楚，否则无法知道要替换什么。

决策底座已完成（可复用，不必重建）：`packages/multi-workers/decision.py:1`（决策客户端 + 8 键契约）、`decision_backends.py:1`（三传输后端）、`mw.py:953`（`cmd_decide`）、`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:1`。现状只接了 1 个点：`ui-bridge.ts:1257` `planDispatchFrontmatter`（派发前分诊）。

已知锚点（**起点，不是全部**）：
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts:1` 与 worker 模式：`needs-clarification` 终态
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:188` `deliverPmAlert`；`pm-orchestrator.ts:532` 附近的 `NOTICE_DISPATCH_ALARM_KINDS`
- 相位门禁：`.agents/skills/agentic-task/core/scripts/advance_phase.py:191` `check_gate`
- `AGENTS.md` 里的"必须先问用户"类规则（user override、删除功能、依赖升级、发布）

## 审计目标（调研问题）

- **Q1 枚举面**：把框架里所有"agent 会停下来等人"的位置列全。至少覆盖：worker 澄清（`needs-clarification`）、checkpoint 升级（`[CHECKPOINT]` mid/high → triggerTurn）、PM 告警处置、相位门禁失败、QG 结论处置、派发参数选择、破坏性操作确认（pi 权限/confirm）、用户 override 冲突、提交/发布时机、变更范围（扩/删功能）、依赖升级与安全评审、测试失败归类、模型降级选择、凭据/权限配置。**必须给出 `path:line`**，并说明该处"等人"的具体表现形式（工具返回文本 / 触发新 turn / 阻塞进程 / 仅提示）。
- **Q2 频率与成本**：每一项的典型触发条件是什么？能从既有产物反推频率吗（`_project_log.md`、`.agenticdoc/*/pm-state.md` 的 Process Log、`workers/*/trace.log`、`run.json`）？有没有可以在不做新埋点的情况下统计出来的？
- **Q3 分类**：每项标 (a) 可逆性（可逆/半可逆/不可逆）、(b) 风险（P0 不可委派 / P1 需确认 / P2 可 binding）、(c) 是否已有机器可读的输入（现在的 prompt 里有多少上下文）、(d) 现在的失败处置（人不在会怎样）。
- **Q4 漏项排查**：用 grep 扫"ask/confirm/clarify/approve/permission/需要用户/请确认/waiting"等词，找出上面清单之外的位置；pi core（`packages/coding-agent/src/core/**`）里与用户交互的入口（工具确认、`ask` 类工具、权限门）具体在哪。
- **Q5 已委派的先例**：仓里有没有"已经用机器判断替代人判断"的先例（例如 watchdog 自动判挂死、自动归档、自动 ack、自动降级），它们的阈值与失败回退是怎么设计的？这些是最有价值的参考模式。

## 唯一证据文件

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-decision-inventory-20261016.md`（新建，全文中文，每条结论附 `文件:行号`）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-decision-inventory-20261016.md`

## 写入禁止面

- 一切源码/配置/测试/其它 evidence 文件；禁止 `git add`/`git commit`；禁止改动其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-decision-substitution\evidence\research\spec-decision-inventory-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5'] if q in t))"
```

## 交付格式

- 证据文件：`Q1` 一张主表（决策点 / 位置 `path:line` / 触发条件 / 等人形式 / 可逆性 / 建议等级 / 现有机器输入），`Q2..Q5` 各一节；末尾「替换优先级建议」按"省人时间最多且风险最低"排序。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**write-first**：前 10 次写调用内先落一版骨架（Q1 表头 + 已确认行），再增量补。
