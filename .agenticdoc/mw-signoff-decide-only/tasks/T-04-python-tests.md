# T-04 — Python 测试重写：按新语义重写签收用例

- type: coding
- owner key: mw-signoff-decide-only
- 派生自：`design.md` §6、`spec.md` AC-001/AC-002/AC-002b/AC-003/AC-004/AC-005/AC-006

## 上下文

项目目标见 `.agenticdoc/goal.md`。实现（T-01/T-02）已落地：CLI 只剩决策模型一条路，门禁只在"该 key 有 `kind=decide` 行"时要求签收。现有一批用例断言的是被删掉的行为，必须重写而不是保留兼容。

必读证据：

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-gate-structure-20261022.md` §5 —— 逐条测试影响（604/613/623/633/649/667 的具体失败方式）。
- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-archive-scan-20261022.md` §6 —— 判据取 raw 行的实测。
- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-tui-surface-20261022.md` §3 —— `--auto` 与 `--dry-run` 的现状缺陷（本任务用测试把它们钉死）。

实现锚点（以实际改动后为准）：

- `packages/multi-workers/decide_signoff.py:103` `SIGNED_VIA_VALUES`（只保留 `auto-decide`）
- `packages/multi-workers/mw.py:3996` `_decide_sign`（`--dry-run` 已在 `auto_conclusion()` 之前）
- `.agents/skills/agentic-task/scripts/advance_phase.py:281` `_key_has_decide_rows`
- `packages/multi-workers/test_decide_signoff.py:604` `test_gate_ignores_keys_without_decision_scope_marker`
- `packages/multi-workers/test_decision_history.py:330` `_write_sign` 仍传旧参数

## 要求

### `packages/multi-workers/test_decide_signoff.py`

| 行 | 用例 | 动作 |
| --- | --- | --- |
| 388 | `test_write_signoff_auto_face_needs_the_flag` | 删除（`allow_agent_session`/`signed_via` 参数已不存在） |
| 432 | `test_write_signoff_refuses_inside_an_agent_session` | 反向重写为 `test_write_signoff_works_inside_an_agent_session`：置入 `AGENT_SESSION_ENV_VARS` 后仍能写 |
| 589 | `test_cli_refuses_inside_an_agent_session` | 删除 |
| 604 | `test_gate_ignores_keys_without_decision_scope_marker` | 改名 `test_gate_passes_a_key_without_any_decide_row`；**保留** `decision-scope.md` 夹具并断言通过（AC-002b） |
| 613 | `test_gate_blocks_continue_with_n_zero` | 先 `_append` 一条真 jev `kind=decide` 行再断言 `SIGNOFF` 失败 |
| 623 | `test_gate_passes_narrow_with_n_zero` | 同上补一行 |
| 633 | `test_gate_blocks_after_the_archive_is_appended` | 只删 marker 夹具，补一行 |
| 649 | `test_gate_blocks_a_missing_machine_line` | 补一行 |
| 667 | `test_signed_via_line_leaves_the_gate_and_dp_apply_parse_untouched` | 补一行（或改为写文件后直接调 `_decision_signoff_problems`） |
| 699 | `test_cli_records_signed_via_cli_by_default` | 删除 |
| 708/730/744/759 | `test_cli_human_confirmed_*` / `test_cli_without_human_confirmed_*` / `test_write_signoff_human_confirmed_is_the_only_exemption` | 全部删除 |
| 774/788 | `test_cli_preview_json_carries_every_conclusion_verdict` / `..._honours_allow_empty_for_continue` | 改用 `--dry-run --json`，并新增断言：**未注册 backend 时也返回 verdicts**（证明零模型调用）、`_autopilot/decisions.jsonl` 行数不变 |

新增用例：

- `test_gate_fails_a_key_with_decide_rows_and_no_file`（AC-002：有行无文件 → `SIGNOFF` MISSING）。
- `test_gate_ignores_rows_for_other_keys`（别人的 decide 行不触发本 key 要求）。
- `test_gate_treats_an_unreadable_archive_as_having_rows`（`UnicodeDecodeError` → fail-loud，不静默放行）。
- `test_signed_via_vocabulary_is_auto_decide_only`（`SIGNED_VIA_VALUES == ("auto-decide",)`）。

### `packages/multi-workers/test_decide_sign_auto.py`

- `_sign_args`（`:160` 附近）删除 `conclusion` / `human_confirmed` 参数，同步全部调用点。
- `test_sign_auto_persists_the_mode_and_exits_zero`（246）：改为断言 `--auto` 持久化**并继续签收**（注册 backend 后文件存在且 `signed_via: auto-decide`）。
- 删除 `test_low_confidence_falls_back_to_llm`（343）、`test_explicit_conclusion_without_a_mode_flag_keeps_cli_semantics`（541）、`test_explicit_conclusion_without_a_mode_flag_is_refused_in_an_agent_session`（555）。
- `test_unavailable_transport_falls_back_to_llm`（361）、`test_dp25_disabled_falls_back_and_names_the_reason`（376）、`test_dp25_not_registered_falls_back_to_llm`（392）：改为断言 `exit 0`、**不写文件**、输出含 `not required`。
- `test_auto_without_jev_and_without_conclusion_is_a_preview`（413）：改名并去掉"pass --conclusion"文案断言，改为断言不写文件 + 提示决策模型不可用。
- `test_write_signoff_only_opens_for_the_auto_values`（569）：改为 `test_write_signoff_has_no_session_gate`。
- 保留 `test_auto_decide_is_allowed_inside_an_agent_session`（312）、`test_auto_decide_writes_signed_via_auto_decide`（283）、`test_advance_phase_mirrors_are_byte_identical`（504）、`test_auto_keeps_the_gate_closed_without_the_file`（526）。

## 写入允许面

- `packages/multi-workers/test_decide_signoff.py`
- `packages/multi-workers/test_decide_sign_auto.py`
- `packages/multi-workers/test_decide_cli.py`（若其中引用了 `--conclusion`/`--human-confirmed`）
- `packages/multi-workers/test_decision_history.py`（`_write_sign` 辅助函数的 `:330-334` 仍传 `signed_via=`/`allow_agent_session=`/`AUTO_SIGNED_VIA`，必须改成新的两参 `write_signoff(root, key, text)`；历史读面断言保持不变）

## 写入禁止面

- 任何非测试源码（`mw.py`、`decide_signoff.py`、`advance_phase.py`、`ui-bridge.ts`、`mw-runner.ts`）
- `.agents/skills/agentic-task/scripts/test_advance_phase.py`
- `packages/coding-agent/test/**`

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decide_signoff.py test_decide_sign_auto.py test_decide_cli.py test_decision_history.py -q
```

必须全绿；不允许 `xfail`/`skip` 掩盖被删行为。

## 改动历史

| date | change |
| --- | --- |
| 2026-10-22 | 卡片创建 |
