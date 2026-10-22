# spec — mw-signoff-decide-only

## §0 Goal Alignment

项目目标（`goal.md`）：PM Agent 管理多个 Worker 并行开发，中低风险决策由决策模型完成，**而不是阻塞在人身上**。

本 key 修正一处与该目标相悖的实现：收尾签收（`sign-final.md`）目前把人放在 agent loop 之外，并要求一个本不该存在的人工动作。签收凭据的本意只是「决策模型真的替代了人的判断」；决策模型没参与时，理应没有任何签收要求。

预期收益：

1. 决策模型参与过的 key 才能产生签收要求；没参与（未启用 / 不可用 / 未触发）的 key 走正常 LLM 判断直接收尾，零环外动作。
2. 默认决策者回归决策模型：`mw decide sign` 不带结论参数时由 `dp25-signoff-conclusion`（jev）给出 `continue|narrow|revoke`；调用方（PM/agent/人）不再提供结论，也不再有"调用方自己算出的结论"这条回退面。

## §1 问题

现状（`packages/multi-workers/decide_signoff.py`、`packages/multi-workers/mw.py`、`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`.agents/skills/agentic-task/scripts/advance_phase.py`）：

1. `_decision_signoff_problems`（`advance_phase.py:271`）的触发条件挂在 `decision-scope.md` 这个手工标记上（`GATES["done"]` 里 `(DECISION_SCOPE_MARKER, "decision_signoff", ...)`），且只要 `signoff != disable` 就要求 `evidence/review/sign-final.md` 存在。决策模型全程不可用时，该文件无从产生 → 门禁把一个环外人工动作变成硬前置。标记文件本身没有任何语义，却被当成"要不要校验"的开关。
2. `mw decide sign` 有四张脸：`auto-decide`（jev）、`auto-llm`（调用方自己的结论）、`cli`、`tui`。后三者是为「人签」服务的回退链；`--human-confirmed` 是绕过 `write_signoff` agent-session 拒绝的显式旗标。
3. `ui-bridge.ts` 的 `/mw decide sign` 硬编码 `--human-confirmed`，并在 `ctx.hasUI !== true` 时直接拒绝——把「窗口内签收」定义成「必须人工点一次确认框」。
4. 文档（`docs/decision-substitution.md:434-444`、`:485`）把这套人签流程写成规范动作。

结论：修法不是给人签找更多合规入口，而是**取消人签这条路**，并把签收要求绑定到决策模型的真实参与。

## §2 已定设计

- `decision-scope.md` **不再是条件**：门禁不再读它（`GATES["done"]` 的 `decision_signoff` 规则改为无条件执行，由检查函数自己判断适用性）。文件可以留在既有 key 里，但完全惰性。
- 签收门禁成立需同时满足：① `.mw/decide.json` 未写 `signoff: disable`；② 该 key 档案里有 `>=1` 条 raw `kind=decide` 行（**含 dp25 自己追加的那行**；`collect().rows` 会排除 dp25，导致有 dp25 行的 key 判据反转，故不用它）。任一不成立 → 门禁跳过，不要求文件、不要求任何人工动作。
- `mw decide sign` 只保留一条路：读档案 → `auto_conclusion()`（jev）→ 写出结论。jev 不可用 → 不写文件、exit 0、说明「decision model unavailable; sign-off not required」。
- 删除 `auto-llm` 回退、`--conclusion` 的人类语义、`--human-confirmed`、`signed_via: cli|tui`，以及 `write_signoff` 的 agent-session 拒绝逻辑。
- `signoff: disable` 保留，语义是「本项目即使有 jev 记录也不要收尾文件」；这是唯一的显式关闭面。

## §3 验收标准

AC-001：给定 key 档案无任何 `kind=decide` 行，`advance_phase.py` 对 `done` 的 `decision_signoff` 检查通过，且不要求 `evidence/review/sign-final.md`——无论 key 目录是否存在 `decision-scope.md`。

AC-002：给定 key 存在 `>=1` 条 jev 决策行但 `sign-final.md` 缺失，`done` 门禁失败并给出可定位原因（要求先跑 `mw decide sign`），不是静默通过——同样无论是否存在 `decision-scope.md`。

AC-002b：给定 key 存在 `decision-scope.md` 但档案无 jev 决策行，`done` 门禁通过（证明标记已被忽略，不再有"有标记就要签收"的暗规则）。

AC-003：`mw decide sign --key <k> --dry-run --json` 在任何情况下零写入，且返回 `verdicts`（三个结论各自的 `{ok, problems}`）与档案 facts。

AC-004：`.mw/decide.json` 启用且 jev 可用时，`mw decide sign --key <k>`（不带结论参数）写出的 `sign-final.md` 含 `signed_via: auto-decide`，其 `conclusion` 等于 dp25 返回的答案；调用方无法通过参数改变该结论。

AC-005：jev 不可用时，`mw decide sign --key <k>` exit 0、不写文件、输出说明决策模型不可用；不产生 `auto-llm` 回退，也不接受任何调用方结论参数。

AC-006：`mw decide sign --conclusion ...`、`--human-confirmed` 不再被接受（argparse 报错）或不再改变行为；`signed_via` 词表只剩 `auto-decide`。

AC-007：`/mw decide sign`（pi 窗口命令）在 `ctx.hasUI === false`（headless / `-p` / rpc）下正常工作，不弹确认框、转发 argv 中不含 `--human-confirmed`。

AC-008：`decide_signoff.write_signoff` 在 agent 会话内不再拒绝 `auto-decide` 写入；人类与 agent 走完全相同的路径，不存在"人工确认"特权分支。

AC-009：`docs/decision-substitution.md` 与 `packages/multi-workers/README.md` 中"人写签收文件 / agent 会话外执行 / 确认框点击"的描述被移除或改写为"决策模型决定，未参与则不需要签收"。

AC-010：受影响的测试套件全部通过：`packages/multi-workers/test_decide_sign_auto.py`、`test_decide_signoff.py`、`test_decide_cli.py`、`packages/coding-agent/test/suite/decision-signoff.test.ts`；`npm run check` 零 error/warning/info。

## §4 非目标

- 不改 `dp25-signoff-conclusion` 的判据（`continue` 仍要求 N>=1 + 每行真 jev + 链完整；`narrow`/`revoke` 只要求链完整）。
- 不改 `rows_sha256`／`counted_rows` 的重算机制与 `authority-change` 档案行。
- 不放开 `dp on|off|set|apply`（授权表仍由人翻开关）。
- 不处理其他未接线 dp 的 `REQUIRED_STATE_FIELDS`。

## §5 可复用资产

- `decide_signoff.collect()` 已经把「该 key 的决策行」算成 `SignoffFacts.rows`，同时提供 `_row_matches_key` 的归属判据；廉价扫描必须与它对齐。
- `_decision_signoff_problems` 已有 `_decision_signoff_disabled` 的跳过分支，新条件挂在同一处，失败信息沿用现有词表。
- `test_decide_sign_auto.py` 的 26 例覆盖了 auto-decide 的主路径，改造时以它为回归基线。
- `decide_signoff.auto_conclusion()` 已经实现了「jev 决定」这条唯一需要的语义，无需新逻辑。
- `decision_history.py` 已经能读历史 `cli`/`tui` 值（`human_basis` 分支），所以收窄写面不需要数据迁移。

## §6 需规避坑点

- `GATES["done"]` 里还有两条**无条件**的旧规则：`evidence/review/sign-final.md` 的 `glob_has_files` 与 `content_match(conclusion:)`（`advance_phase.py:107-121`）。只要它们还在，任何 key（即使零决策行）都必须有签收文件 —— AC-001 不可能成立。必须与 `decision_signoff` 规则一起处理（删掉旧两条，全部下沉到新检查）。
- `_decide_sign` 的 `auto_flow = conclusion is None or mode_flag is not None` 是四张脸的分流点；删 `auto-llm` 时必须同时删掉 `--conclusion` 传入路径，否则 4066 行的 `conclusion = auto_conclusion` 仍会被调用方值覆盖。
- 当前 preview argv 不带 `--dry-run`（`ui-bridge.ts:4730`），jev 可用时会真的写文件；AC-003 必须先在 Python 侧让 `--dry-run --json` 也返回 `verdicts`，否则窗口的前置拒绝会静默失效。
- `decision-signoff.test.ts` 现存断言围绕 `--human-confirmed` 与 `hasUI` 拒绝；改造时按 AC-007/AC-008 反向重写，不要保留"两套语义都支持"的兼容层。
- 门禁规则变成无条件执行后，`_decision_signoff_problems` 会对**每个** key 调用；`decide_signoff` 的导入依赖 `packages/multi-workers` 在项目路径上，导入失败时现有代码直接报 SIGNOFF 失败。因此必须在导入之前先做一次廉价的档案扫描（文件不存在或该 key 无 `kind=decide` 行 → 直接返回 `[]`），否则所有没装 mw 的项目 `done` 门禁会集体变红。
- 档案行归属判据必须与 `decide_signoff._row_matches_key` 保持一致（`key` 列，或 `decision_id` 的 `:<key>` 后缀），两处漂移会让"有没有决策行"的结论不一致。
- `AGENT_SESSION_ENV_VARS` **不能删**：`mw.py:1854` 在模块级用它初始化 `_DP_AGENT_ENV_VARS`（`dp apply` 的守卫），删掉会让整个 CLI 导入失败。只删 `write_signoff` 里的拒绝分支。
- `decision_history.py:713` 的读面词表（四个值）与 `decide_signoff.py:103` 的写面词表是**两套**；只收窄写面，读面保留旧值，否则历史签收会被判 `unknown signed_via`、`human_basis` 归类翻转。

## §7 证据要求

- 代码：`advance_phase.py`、`mw.py`、`decide_signoff.py`、`ui-bridge.ts` 的改动行 + 对应测试行。
- 运行：`python -m pytest packages/multi-workers/test_decide_sign_auto.py test_decide_signoff.py test_decide_cli.py`、`node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-signoff.test.ts`（在 `packages/coding-agent`）、`npm run check`。
- 行为：一个"无决策行 key"的 `done` 门禁实跑（AC-001）；一个"有 `decision-scope.md` 但无决策行"的 key 实跑（AC-002b）；一个"有决策行 key"的 `mw decide sign` 实跑（AC-004/AC-005）。
