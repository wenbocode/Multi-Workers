# spec 证据（PM 侧）：签收机制现状与改造边界

- date: 2026-10-22
- key: mw-signoff-decide-only
- 性质：PM 直接读取源码得到的基线证据（不是 worker 研究），用于解锁 spec 阶段的 research note 要求，并作为 RQ1..RQ4 的起点。

## 1. 签收产物与门禁

| 事实 | 位置 |
| --- | --- |
| 签收文件唯一落位 `<key>/evidence/review/sign-final.md` | `packages/multi-workers/decide_signoff.py:81` |
| 机器行词表：`conclusion|counted_rows|rows_sha256|engine|allow_empty|key|claim|ts|reason|promote|demote|p0-open|signed_via|decide_fallback` | `decide_signoff.py:120-125`（`_MACHINE_LINE_RE`） |
| `conclusion:` 必须列 0 单行才被门禁识别 | `.agents/skills/agentic-task/scripts/advance_phase.py:39` |
| 内容校验入口 | `advance_phase.py:271` `_decision_signoff_problems` |
| 现状触发条件 = key 目录存在 `decision-scope.md` | `advance_phase.py:37`、`:123-131`、`:420-427` |
| `signoff: disable` 跳过三条签收规则 | `advance_phase.py:256`（`_decision_signoff_disabled`）、`:343` |
| 校验内容：文件 → `conclusion:` → `counted_rows`/`rows_sha256` → 重算 sha → `continue` 时 `verdict()` | `advance_phase.py:271-340` |

结论：门禁只看内容，不看"谁写的"。`signed_via` 不是门禁输入。

## 2. 四张脸与分流点

| 事实 | 位置 |
| --- | --- |
| `auto_flow = conclusion is None or mode_flag is not None` | `packages/multi-workers/mw.py:4049` |
| jev 可用时**覆盖**调用方结论 | `mw.py:4066` `conclusion = auto_conclusion` |
| `signed_via` 默认 `cli`，`--human-confirmed` → `tui` | `mw.py:4048` |
| 自动面只允许 `auto-decide|auto-llm` | `decide_signoff.py:100` `AUTO_SIGNED_VIA`、`write_signoff()` |
| `write_signoff` 在 agent 会话内拒绝非 auto 面 | `decide_signoff.py` `write_signoff`（`agent_session_vars()` + `allow_agent_session and signed_via in AUTO_SIGNED_VIA`） |
| argparse：`--conclusion` / `--auto` / `--disable` / `--human-confirmed` | `mw.py:11752`、`:11756`、`:11766` |
| `auto_conclusion` 只在 jev 配好且 dp25 enabled 时调用 | `decide_signoff.py` `auto_conclusion()` |

## 3. preview 的真实行为（重要缺陷）

`ui-bridge.ts:4730` 的 preview argv 是 `["sign","--key",k,"--json"]`，**不含 `--dry-run`**。而 `mw.py:4049` 在 `conclusion is None` 时 `auto_flow=True`，jev 答得出就会走完 `verdict()` 并直接写文件（`mw.py` 的 `if dry_run:` 分支不成立）。

`test_decide_signoff.py:456 test_cli_preview_writes_nothing` 之所以通过，是因为夹具没有 `.mw/decide.json`，jev 不可用 → 落到 `_decide_sign_auto.py` 的 `_decide_sign_preview` 分支。

本仓库 `.mw/decide.json` = `{"enabled":true,"transport":"timi-decisions","model":"jev-latest","signoff":"auto"}`，`.mw/decide-points.json` 已含 `dp25-signoff-conclusion`（tier P2 / enabled / mode auto），因此这条"预览即写入"的路径在本项目是活的。

## 4. 现存签收文件

| key | conclusion | signed_via |
| --- | --- | --- |
| mw-decision-substitution | narrow | auto-decide |
| mw-signoff-per-key | narrow | auto-decide |
| mw-usage-monitor | narrow | auto-decide |

`decision-scope.md` 仅 `mw-decision-substitution` 存在（1 个 key）。三份签收全部来自 jev，没有一份是人写的——说明"人签"在实跑中从未发生，只为它维护了一整套回退链。

## 5. 窗口面

| 事实 | 位置 |
| --- | --- |
| `ctx.hasUI !== true` 直接拒绝 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4823` |
| 确认框 | `ui-bridge.ts:4871` `ctx.ui.confirm(...)` |
| 写入 argv 硬拼 `--human-confirmed` | `ui-bridge.ts:4884` |
| 命令注册 | `ui-bridge.ts:5058` |
| `decideMw` 自动追加 `--project=<control root>` | `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:573-580` |

## 6. 用户裁定（本轮对话）

1. 修法不是给人签找入口，而是**取消人签这条路**；用代码逻辑绕开"人去 loop 外写文件"是把问题合理化。
2. decide model 启用时，**默认由 decide model 决定**；调用方不提供结论。
3. `decision-scope.md` 不是硬约束，不再作为门禁条件，忽略它。

## 7. 待 RQ 补齐的空白

- `signed_via` 在 `decision_history.py` / dashboard / 报告里的全部消费点（RQ1）。
- `check_gate` 规则无条件化的最小写法、`advance_phase.py` 多副本同步范围（RQ2）。
- `decision-signoff.test.ts` 的逐条用例去向、`xkey-gate-guard` 是否拦窗口转发（RQ3）。
- `collect()` 的真实成本、`_row_matches_key` 的边界、档案行数统计（RQ4）。
