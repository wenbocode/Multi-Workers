# Quality Gate Report: mw-ue-toolchain

> 日期: 2026-09-21
> 门禁: /quality-gate（事后补登记模式——实现先于 key 完成，VC 证据全部来自本会话真实执行产物）

## AC 勾销表

| AC | 判定 | 证据 |
|----|------|------|
| AC-001 run 五工件 + ok=true | PASS | `test_toolchain_cli.py::TestToolchainRun::test_ok_run_artifacts_and_verdict`（cmd.txt/run.log/exit.txt/errors.txt/meta.json 断言全过）+ 真机冒烟 §3 run dir `20260921-204041-build_editor` |
| AC-002 错误签名双判 | PASS | `test_error_signature_and_bad_exit_fails`（exit 2 + `error C2039` → mw rc=1，errors.txt 含签名行） |
| AC-003 drift fail-even-on-exit-0 | PASS | `test_watch_drift_fails_even_on_exit_zero`（exit 0 + watch 被命令改 → rc=1，watched_drift_count=1） |
| AC-004 targets 现查 | PASS | `test_targets_lists_editor_and_game`（`Proj (game)`/`ProjEditor (editor)`）+ `test_targets_no_source_dir`（`no *.Target.cs` rc=0）+ 真机冒烟 §3 |
| AC-005 EOL 归一化 hash | PASS | `test_hash_prints_eol_normalized`（CRLF/LF 同摘要）+ `TestHelpers::test_sha256_eol_normalized_crlf_lf_equivalent`（等价 ∧ 与异内容不等）+ 真机冒烟 §3 hash 输出 |
| AC-006 占位符 fail-closed | PASS | `test_missing_engine_placeholder_fails_closed`（stderr 含 missing-field，rc=1） |
| AC-007 未知名 fail | PASS | `test_unknown_name_fails`（stderr 含 `no toolchain command named 'nope'` + 已配置列表，rc=1） |
| AC-008 动词派发/旧名拒绝 | PASS | evidence/runs/validation §4 四项 PASS（新动词 rc=0 ×3，旧 `toolchain` rc=2 无别名） |

## 回归

- 全量套件 722 passed / 9 deselected（基线 708 + 新增 14，无回归）。
- `npm run check` exit 0。

## 流程偏差（诚实记录）

本 key 为野生实施事后补登记：需求讨论后未走准入门禁（无 key、无 worker 派发），6 个任务全部主窗口直做。已按 AC/VC 证据链补齐可追溯性；偏差本身与补救记录在 key-decision.md「I（实施）」与 spec.md 状态行。后续 follow-up（见 achieved.md 遗留）必须按 spec → key → claim → dispatch 流程执行。

## 结论

**PASS** —— 8/8 AC 勾销，回归零破坏，定义域（dual UE / MSVC-UBT）已在动词名、help、README、指南头注、CHANGELOG 六处钉死。
