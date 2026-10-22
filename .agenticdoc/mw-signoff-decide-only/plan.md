# plan — mw-signoff-decide-only

## 目标

按 `design.md` 落地三个改动面（门禁 / CLI / 窗口）与配套测试、文档；净效果是"决策模型参与过才签收，签收结论只能由决策模型给"。

## 执行波次

### Wave 1（三面并行，写面互不重叠）

| 任务 | 写面 | 内容 |
| --- | --- | --- |
| T-01 CLI 收敛 | `packages/multi-workers/decide_signoff.py`、`packages/multi-workers/mw.py` | 删 `auto-llm`/`cli`/`tui`、`--conclusion`、`--human-confirmed`；`write_signoff` 去 agent-session 拒绝；`--dry-run --json` 出 `verdicts`；写面词表收窄到 `("auto-decide",)`；`AGENT_SESSION_ENV_VARS` 保留 |
| T-02 门禁改造 | `.agents/skills/agentic-task/scripts/advance_phase.py`（+ `install.py` 同步镜像） | 删两条无条件旧规则；`DECISION_SIGNOFF_RULE_TARGET = ""` 哨兵规则；`_key_has_decide_rows` 廉价判据（导入前早退）；删死代码 |
| T-03 窗口改造 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`shared/mw-runner.ts` | preview 加 `--dry-run`；write 改 `--auto`；删 `hasUI` 门与确认框；删 `--conclusion`/`ParsedDecideArgs.conclusion`；回显真实结论 |

### Wave 2（依赖 Wave 1 的实现语义）

| 任务 | 写面 | 内容 |
| --- | --- | --- |
| T-04 测试重写（Python） | `packages/multi-workers/test_decide_signoff.py`、`test_decide_sign_auto.py`、`test_decide_cli.py` | 按 `design.md` §6 逐条改；补 AC-002b、`--dry-run --json` 零写入、jev 不可用不写文件 |
| T-05 测试重写（TS） | `packages/coding-agent/test/suite/decision-signoff.test.ts` | `hasUI=false` 可用、argv 断言、preview 带 `--dry-run` |
| T-06 文档同步 | `docs/decision-substitution.md`、`packages/multi-workers/README.md`、`packages/multi-workers/CHANGELOG.md`、`packages/coding-agent/CHANGELOG.md` | 删除"人写签收文件/agent 会话外执行/确认框"描述；写清新规则 |

### Wave 3

| 任务 | 内容 |
| --- | --- |
| T-07 验证 | pytest 三套 + vitest `decision-signoff.test.ts` + `npm run check` + 两个实跑（零行 key 过门禁、有行 key 签收）；产出 `evidence/quality-gate-report-*.md` |

## 依赖与并行约束

- T-04 依赖 T-01/T-02 落地（断言对象变了）；T-05 依赖 T-03。
- T-06 依赖 T-01/T-02/T-03（文档描述最终行为），可与 T-04/T-05 并行（写面不同）。
- T-02 的 `install.py` 会改写 `.agents/skills/agentic-task/{core,claude}/scripts/advance_phase.py` 与 `.claude/scripts/advance_phase.py`；它与任何写面都不重叠。
- T-07 最后执行，独占工作树（不并行）。

## 验收映射

| AC | 由哪个任务证明 |
| --- | --- |
| AC-001 / AC-002 / AC-002b | T-02 + T-04 + T-07 实跑 |
| AC-003 / AC-004 / AC-005 / AC-006 | T-01 + T-04 |
| AC-007 / AC-008 | T-03 + T-05 |
| AC-009 | T-06 |
| AC-010 | T-07 |

## 不做

- 不改 `dp25` 判据、`rows_sha256` 机制、`authority-change` 行格式。
- 不改 `mw decide dp apply` 的 agent-session 守卫。
- 不处理 `Trigger.key` 空串问题。
