# achieved — mw-signoff-decide-only

## 改了什么

1. **门禁（`.agents/skills/agentic-task/scripts/advance_phase.py`，含 `core`/`claude`/`.claude` 三份镜像）**
   - `GATES["done"]` 删除两条无条件旧规则（`sign-final.md` 的 `glob_has_files` 与 `content_match(conclusion:)`），它们此前让**所有** key 都必须在收尾时交签收文件（本仓库 77 key 中 74 个被拦）。
   - `decision_signoff` 改为哨兵路径 `DECISION_SIGNOFF_RULE_TARGET = ""` 并无条件执行；`DECISION_SCOPE_MARKER` 与循环级 disable 短路（死代码）删除。
   - 新增 `_key_has_decide_rows()` 廉价判据（纯标准库、命中即停），插在 `disable` 判断之后、`decide_signoff` 导入与文件存在性检查**之前**：无 raw `kind=decide` 行 → `[]`。读不清（IO/编码）→ 按"有行"fail-loud。
   - `mw decide report` 子进程固定 UTF-8 解码，修掉中文输出在 cp936 环境下让 `decision-review-*.md` 静默不写的问题。

2. **CLI（`packages/multi-workers/mw.py`、`decide_signoff.py`）**
   - 删 `auto-llm` / `cli` / `tui` 三张脸与 `--conclusion`、`--human-confirmed`、`_decide_sign_signed_via`、`_decide_sign_write`；`write_signoff(project_dir, key, text)` 去掉 `allow_agent_session` / `signed_via` 与 agent-session 拒绝。
   - `--dry-run` 移到 `auto_conclusion()` 之前：零模型调用、零档案行、零文件，输出三个结论的 `verdicts`。
   - jev 不可用 → exit 0、不写文件、`decision model unavailable (<reason>); sign-off not required`。
   - 写面词表收窄为 `("auto-decide",)`；读面（`decision_history.py`）保留四值，历史 `cli`/`tui` 签收不再告警。

3. **窗口（`ui-bridge.ts`、`mw-runner.ts`）**
   - preview `sign --key k --dry-run --json`；写面 `sign --key k --json`（不传 `--auto`，保留 `signoff: disable` 的效力）。
   - 删 `ctx.hasUI` 门、`ctx.ui.confirm` 确认框、逐结论前置拒绝、`ParsedDecideArgs.conclusion`。
   - `exit 0` 不再等于"已签收"：按 stdout `signed_via:` 或 JSON `path` 区分，headless 结果走命令返回值 + `displaySummary`。

4. **测试**：`test_decide_signoff.py` / `test_decide_sign_auto.py` / `test_decide_cli.py` / `test_decision_history.py` 重写（176 passed）；`decide-command.test.ts` / `decision-signoff.test.ts` / `decision-dashboard-command.test.ts` 重写（34 passed）。

5. **文档**：`docs/decision-substitution.md`（§5.2/§5.3、FIX-Q 段、故障表）、`packages/multi-workers/README.md`、两个包 CHANGELOG。

## 系统行为变化、影响面

- **收尾签收只在决策模型参与过时存在**：无 `kind=decide` 行的 key 不再需要 `sign-final.md`；有行的 key 缺文件仍然阻断（`MISSING`），签收后档案被追加仍会 `rows_sha256` 不匹配。
- **结论不可由调用方给出**：`--conclusion` 消失（argparse exit 2），窗口无确认框，人不再有"回结论"的入口；`signed_via` 只剩 `auto-decide`。
- **`decision-scope.md` 完全惰性**：所有既有 key 的该文件不再影响任何门禁分支。
- **受影响的下游**：`claim-driven-review`、`mw-decision-dashboard` 这类有 jev 行但没有签收文件的 key，改造后必须在 `done` 前跑一次 `mw decide sign`（预期，非回归）；外部依赖"缺 `sign-final.md` 就红"的脚本会失效（仓库内无此依赖）。
- 性能：`done` 门禁对 74 个 key 的检查 123.8 ms → 52 ms。

## 可复用经验 / 坑点

- **先确认"这条规则是不是本来就无条件生效"**：旧文档写"仅当 `decision-scope.md` 存在时校验"，实际只有"内容重算"那一层带条件，存在性与 `conclusion:` 两条对全部 key 无条件生效。只改标记会让目标 AC 不可达。
- **廉价判据必须放在导入之前**：`advance_phase` 对没有 `packages/multi-workers` 的项目会 import 失败并硬报 `SIGNOFF`，先扫描档案再决定是否导入。
- **判据口径要与"签收内容"一致**：`collect().rows` 排除 dp25，用它当"是否需要签收"会让有 dp25 行的 key 判据反转（本仓库 5 个 key 里 2 个相反）。取 raw `kind=decide`。
- **删"人签"必须同时删三处**：CLI 参数、窗口 pre-check（`ctx.hasUI` / 确认框 / 逐结论拒绝）、`write_signoff` 的 agent-session 拒绝；少一处就会留下绕过面。
- **常量不能连带删**：`AGENT_SESSION_ENV_VARS` 被 `mw.py` 模块级用于 `dp apply` 守卫，删它会整个 CLI 导入失败；只删使用它的拒绝分支。
- **两套词表**：`decide_signoff` 写面与 `decision_history` 读面各一套，只收窄写面并保留读面遗留值，否则历史档案被判未知值。
- **Windows 子进程解码**：`subprocess.run(text=True)` 走 cp936，读 UTF-8 中文输出会 `UnicodeDecodeError` 且异常发生在读线程里、`stdout` 变成 `None`；显式 `encoding="utf-8", errors="replace"` 并给 `result.stdout` 兜底。

## 后续（未做）

- `Trigger.key` 默认空串（`decision_points.py:229`）导致"无 key 的 decide 行"对所有 key 不可见（今天 0 实例）。
- `mw decide dp apply` 在 agent 会话内仍然拒绝（另一条写面，本 key 未动）。
