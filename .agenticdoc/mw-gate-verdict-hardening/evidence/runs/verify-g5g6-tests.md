# G5/G6 用例映射表（用例名 → AC/VC）

- key: `mw-gate-verdict-hardening` · 生成: 2026-10-10 · 覆盖 **AC-019 ~ AC-024**（+ AC-014 由 T-21 之外的既有卡承接）
- 口径：每条 VC 至少 1 条**正向**用例 + 至少 1 条**反向/对照**（见 §3 控制矩阵）；用例名与代码逐字一致

## 1. 用例 → AC/VC

| VC | AC | 用例（文件 :: 名称） | 落地卡 |
|---|---|---|---|
| VC-024 | AC-023 | `worker-store.test.ts :: reads every 9-column IN-3-shaped row and reports no unreadable line`<br>`worker-store.test.ts :: tolerates legacy 7/8-column rows (origin absent -> manual)`<br>`test_in3_queue_replay.py :: test_current_codec_reads_every_incident_row`<br>`test_in3_queue_replay.py :: test_current_codec_also_reads_the_legacy_column_shape`<br>`test_worker_queue_python_integrity.py :: test_parse_workers_queue_counts_rows_and_unparsable_slots` | T-15 / T-18 / **T-21** |
| VC-025 | AC-023、AC-020 | `test_in3_queue_replay.py :: test_ten_column_row_is_counted_and_survives_all_three_writers`<br>`worker-store.test.ts :: counts a 10-column row and keeps its slot across an upsert`<br>`worker-dispatch-guard.test.ts :: an unreadable queue row aborts the whole scan and is preserved` | T-15 / **T-21** |
| VC-026 | AC-023 | `worker-store.test.ts :: reads a declared header and never adds one to an existing header-less file`<br>`worker-store.test.ts :: replaces a row in place and leaves the rest of the file byte-identical`<br>`test_worker_queue_python_integrity.py :: test_headerless_file_is_version_one`<br>`test_worker_queue_python_integrity.py :: test_update_status_leaves_the_file_untouched_when_no_row_matches` | T-15 / T-18 |
| VC-027 | AC-020、AC-021 | `worker-dispatch-guard.test.ts :: an unreadable queue row aborts the whole scan and is preserved`<br>`worker-dispatch-guard.test.ts :: records a machine-readable alarm row the decision loop cannot see`<br>`test_worker_queue_python_integrity.py :: test_doctor_flags_unparsable_rows` | T-17 / T-18 |
| VC-028 | AC-020 | `worker-dispatch-guard.test.ts :: an empty queue plus product evidence refuses the scan; a fresh project dispatches` | T-17 |
| VC-029 | AC-021 | `worker-dispatch-guard.test.ts :: queues at most the per-scan quota and reports the refusal`<br>`worker-dispatch-guard.test.ts :: refuses a 10-candidate scan after the quota (the IN-3 scan shape, T-21)`<br>`worker-dispatch-guard.test.ts :: reads the quota from the project's dispatch_max_per_scan` | T-17 / **T-21** |
| VC-030 | AC-021 | `test_launcher.py :: TestLauncherMaxWorkersBound :: test_default_max_workers_is_eight_not_unbounded`<br>`:: test_project_config_cap_is_used` · `:: test_explicit_arg_wins_over_config` · `:: test_unreadable_config_falls_back_to_the_bounded_default` | T-18 |
| VC-031 | AC-021、AC-023 | `test_worker_queue_python_integrity.py :: test_doctor_burst_shape_flags_the_in3_fingerprint`<br>`:: test_doctor_burst_shape_needs_size_and_ratio` · `:: test_doctor_text_line_keeps_a_healthy_queue_byte_identical`<br>`test_in3_queue_replay.py :: test_doctor_reads_the_incident_shape_without_a_false_positive` | T-18 / **T-21** |
| VC-032 | AC-022 | `worker-dispatch-guard.test.ts :: never re-queues a task whose own run already ended AND says why`<br>`worker-dispatch-guard.test.ts :: refuses a candidate whose own run already ended and reports the conflict`<br>`run-store.test.ts :: refuses a task whose own run already ended` | T-20 |
| VC-033 | AC-022 | `worker-dispatch-guard.test.ts :: dispatches a replacement run that declares supersedes, leaving the old dir untouched`<br>`run-store.test.ts :: allows a replacement run only when the superseded run already ended`<br>`run-store.test.ts :: refuses a supersede target that is unknown or not terminal` | T-20 |
| VC-034 | AC-019 | `worker-dispatch-guard.test.ts :: scope pm queues only the watched key + _scratch and never rewrites another key's history` | T-19 |
| VC-035 | AC-019 | `worker-dispatch-guard.test.ts :: scope cli (the mw command surface) still dispatches across keys`<br>`worker-dispatch-guard.test.ts :: scope pm without a watched key still picks up _scratch (never the whole project)`<br>`worker-crosskey-readonly.test.ts :: dispatch_worker still creates an unclaimed key (new-key bootstrap) and this window's own key` | T-19 / T-22 |
| VC-036 | AC-024 | `worker-crosskey-readonly.test.ts :: list_tasks scope all/key expose the foreign key while its writes are refused`<br>`worker-crosskey-readonly.test.ts :: dispatch_worker refuses an explicit foreign live key and writes nothing` | T-22 |
| VC-037 | AC-024 | `worker-crosskey-readonly.test.ts :: advance_phase refuses a foreign live key before the gate script runs` | T-22 |
| VC-038 | AC-024 | `worker-crosskey-readonly.test.ts :: dispatch_worker still creates an unclaimed key (new-key bootstrap) and this window's own key` | T-22 |
| VC-039 | AC-023 | `test_worker_queue_python_integrity.py :: test_update_status_preserves_unparsable_rows`<br>`:: test_archive_stale_entries_preserves_unparsable_rows` · `:: test_upsert_worker_row_replaces_in_slot_and_appends`<br>`test_in3_queue_replay.py :: test_ten_column_row_is_counted_and_survives_all_three_writers` | T-18 / **T-21** |
| VC-040 | AC-021 | `test_launcher.py :: TestLauncherMaxWorkersBound`（4 例，见 VC-030） | T-18 |
| VC-041 | AC-021、AC-023 | `test_launcher.py :: TestLauncherAckConvergence :: test_acked_non_terminal_row_converges_and_is_not_spawned`<br>`:: test_acked_parse_failure_does_not_skip`<br>`test_worker_queue_python_integrity.py :: test_read_acked_skips_garbage_and_keeps_good_rows`<br>`:: test_read_acked_missing_file_is_no_information` | T-18 |
| VC-042 | AC-022 | `worker-run-identity.test.ts :: records running with its own identity before the first turn`<br>`run-store.test.ts :: reads a worker-written record and classifies its state`<br>`run-store.test.ts :: writes the record without leaving a temp file behind`<br>`run-store.test.ts :: treats a future/unknown status as no information instead of wedging dispatch` | T-20 |
| VC-043 | AC-022、R15 | `worker-run-identity.test.ts :: writes the terminal state and the run marker on a clean settle`<br>`worker-run-identity.test.ts :: keeps an agent-written machine-readable first line in place (D-117)`<br>`run-store.test.ts :: run_id is unique per run and the marker carries it`<br>`run-store.test.ts :: collects the deliverables that exist, sorted`<br>`worker-run-identity.test.ts :: still writes output.md when the run record cannot be written` | T-20 |
| VC-044 | AC-022 | `worker-dispatch-guard.test.ts :: refuses a live run that lost its queue row (no second writer)`<br>`run-store.test.ts :: refuses a live run instead of duplicating its directory writer`<br>`run-store.test.ts :: does not even read task.md when the task already has a run record`<br>+ VC-032/VC-033 的用例 | T-20 |
| VC-045 | AC-022 | `test_launcher.py :: TestReconcileRunState`（7 例：终态收敛 / `needs-clarification` 保留 / 活动+output ⇒ `lost` / 活动陈旧 ⇒ `lost` / 活动新鲜不动 / `[END]` 胜过陈旧 `running` / `lost` 属台账终态）<br>`test_run_identity.py :: test_mark_run_lost_preserves_the_scene` · `:: test_mark_run_lost_drops_a_stale_exit_code` · `:: test_mark_run_lost_is_fail_safe` | T-20 |
| VC-046 | AC-019 | `worker-dispatch-guard.test.ts :: reports the keys it did not scan instead of skipping them silently (T-19/T-20)`<br>`worker-dispatch-guard.test.ts :: a refused agent_settled scan writes one ledger row and alerts the PM once per kind` | T-19 / T-20 |

跨语言一致性：`test_run_identity.py :: test_terminal_status_sets_are_identical_across_languages` · `:: test_lost_is_terminal_for_the_ledger`（VC-042 的集合恒等前提）。

## 2. T-21 `[VERIFY]` 要求的四组数字

| 数字 | 值 | 来源 |
|---|---|---|
| 9 列样本行数 | **250**（事故当次为 252 行 / 28 owner；夹具冻结时线上仍可读 250 行 / 27 owner，缺口见报告 §2） | `test_fixture_is_the_incident_shape`（TS 侧同断言） |
| 旧解析器丢弃行数 | **250 / 250 全丢**（`WORKER_COLS = 8` 的 pre-`b8bc115ff` codec） | `test_legacy_codec_drops_every_incident_row`、TS `the pre-fix codec drops every incident row` |
| `unparsable` 计数 | 夹具本体 **0**；注入 1 行 10 列 ⇒ **1**（且该行原文在三个写者回写后仍在） | `test_ten_column_row_is_counted_and_survives_all_three_writers`、TS `counts a 10-column row and keeps its slot across an upsert` |
| 单轮配额截断数 | 10 个候选 ⇒ 新增 **3** 行（`dispatch_max_per_scan` 默认 3）+ 1 条 `dispatch-quota` 告警；配置 `dispatch_max_per_scan: 1` ⇒ 新增 **1** 行；5 个候选 ⇒ 3 | `refuses a 10-candidate scan after the quota`、`reads the quota from the project's dispatch_max_per_scan`、`queues at most the per-scan quota` |

## 3. 控制矩阵（摘掉 → 哪条用例红）

| 控制脚本 | 变异数 | 结果 | 覆盖 |
|---|---|---|---|
| `evidence/scripts/t15-controls.ps1` | 3 | A 5 failed / B 1 failed / C 1 failed | 丢行计数、槽位保留、版本头 |
| `evidence/scripts/t17-controls.ps1` | 5 组 | 全红 | fail-closed、配额、告警落盘、接线 |
| `evidence/scripts/t18-controls.ps1` | 6 (A~F) | 全红 | Python 三写者、launcher 有界、acked、doctor 判据 |
| `evidence/scripts/t20-controls.ps1` | 7 (A~G) | 全红 | run.json 终态、`supersedes`、best-effort、越界可见、launcher `lost` |
| `evidence/scripts/t21-controls.ps1` | 5 (A~E) | 全红 | 9 列可读（TS/Python）、8 列可读（TS/Python）、写者不丢行 |
| `evidence/scripts/t22-controls.ps1` | 4 | 全红 | 跨 key 写面守卫 + 读面不盲 |
