# T-06 回执：G1 用例集（P/N/X + 非空洞对照）

- 卡: `tasks/T-06-l3-tests.md`（worker 派发路径 `workers/mwg-t06-l3-tests/`）
- 依赖: T-01 `done`（实现已在工作区，见 `evidence/runs/t-01-l3-aborted-report.md`）
- 写面（独占，唯一新文件）: `packages/multi-workers/test_autopilot_l3_aborted.py`（20 个用例，643 行）
- 结果: **交付完成；`[VERIFY]`① 20 passed（绿）；`[VERIFY]`② 唯一红 = T-14 计数锁 2 处（预期红，未改）；X1 摘掉指纹后 P1 实际转红已贴原文**
- 外部语料: **零读取**；夹具全部合成，文件内含外部绝对路径数 = 0

## 1 基线快照（开工前）

```
$ git rev-parse --short HEAD
776b82d7f
$ git status --porcelain -- packages/multi-workers/autopilot/conductor.py
 M packages/multi-workers/autopilot/conductor.py
```

开工时 `conductor.py` 已处于 T-01 已落地 + T-07 进行中的状态（`git diff --stat` = +158/-26，与本卡 L3 写面无重叠）。本卡**未触碰** `conductor.py`、`gates.py`、`config.py`、`timeline.py`，也未触碰任何 `.agenticdoc/_workers.*` / `_index.parallel` 协调文件。收工 `git status` 中本卡只新增 `?? packages/multi-workers/test_autopilot_l3_aborted.py`。

## 2 交付清单（P/N/X 逐条绿/红）

全部 20 条**绿**。断言入口 = 生产路径 `conductor._l3_round_verdict`（分类类）或 `conductor.tick` 全链（事件/重掷/stall 类），无一条只测被抽出的 helper。

| ID | 用例（文件:行号） | 断言要点 | VC | 结果 |
|---|---|---|---|---|
| P1 | `test_p1_marker_without_qualifying_source_is_aborted` (`:194`) | marker + 无可读合格源 + 队列 `failed` ⇒ `aborted` | VC-001 | 绿 |
| P2 | `test_p2_aborted_event_data_is_fixed_eight_tuple` (`:214`) | `l3-aborted` 事件 `data` 键集=固定八元组，值逐项（round/task_key/status/output_bytes/done_exit_zero/retry_used/retry_limit/recorded_at） | VC-002 | 绿 |
| P3 | `test_p3_reroll_dispatches_dedicated_l3abort_round` (`:244`) | 专用计数未耗尽 ⇒ 派 `l3-a2`，`loop: l3abort:<key>`、`attempt: 1`、独立计数=1 | VC-004 | 绿 |
| P4 | `test_p4_reroll_ignores_shared_budget_exhaustion` (`:267`) | `round_budget=1` 下仍重掷（共享 `l3:` 已 1/1，abort 不占） | VC-005 | 绿 |
| P5 | `test_p5_reroll_verdict_resumes_normal_path` (`:292`) | 重掷轮出 meets ⇒ 走正常 done 事务（`verify->done exit=0`、phase DONE、`l3-verdict.txt=meets`） | AC-003 | 绿 |
| P6 | `test_p6_qualifying_report_source_is_not_aborted` (`:321`) | `report.md` 两节齐备 + marker ⇒ 不判 aborted；`done` ⇒ 判定源=report.md | VC-006 | 绿 |
| P7 | `test_p7_qualifying_output_source_is_not_aborted` (`:340`) | `output.md` 两节齐备 + marker ⇒ 不判 aborted；`done` ⇒ 判定源=output.md | VC-006 | 绿 |
| N1 | `test_n1_no_marker_is_not_aborted` (`:374`) | 无 marker ⇒ `no-verdict` | VC-006 | 绿 |
| N2 | `test_n2_marker_outside_tail_window_is_not_aborted` (`:383`) | marker 在首部 + 70,000 B 尾部填充（出尾 64 KiB）⇒ 不判 aborted | VC-006 | 绿 |
| N3 | `test_n3_provider_403_is_not_aborted` (`:399`) | provider 403（自带错误行 + `done exit=0`，无 stream marker）⇒ 不判 aborted | VC-006 | 绿 |
| N4 | `test_n4_real_fail_marker_is_below` (`:414`) | 真 FAIL 标记行 ⇒ `below` + fail_line；marker 与 FAIL 共存仍 `below`（指纹不得吞真红） | VC-006 | 绿 |
| N5 | `test_n5_prose_report_is_below` (`:439`) | 第四类：无节标题散文 `report.md` ⇒ `below`、源 None | VC-006 | 绿 |
| N6 | `test_n6_two_sections_with_marker_is_not_aborted` (`:356`) | 两节齐备 **且有 marker** ⇒ `meets`（不得只看 marker） | VC-006 | 绿 |
| 补 | `test_vc006_false_positive_sweep` (`:453`) | 6 个负例一次扫过，false_positives=0 | VC-006 | 绿 |
| 补 | `test_vc003_three_way_exclusivity` (`:487`) | A=meets / B=aborted / C=below 三类两两互斥 | VC-003 | 绿 |
| X1 | `test_x1_fingerprint_is_load_bearing` (`:516`) | 摘掉 `_l3_stream_aborted` ⇒ P1 转 `no-verdict`（红向） | VC-017 | 绿 |
| X2 | `test_x2_tail_window_is_fail_closed` (`:539`) | 窗内 marker ⇒ aborted；窗外 ⇒ 不判（fail-closed）+ 尾读 ≤64 KiB | VC-017 | 绿 |
| X3 | `test_x3_qualifying_source_clause_is_load_bearing` (`:566`) | 摘掉「无合格源」子句 ⇒ P6 转 `aborted`（第二条非空洞对照） | VC-017 | 绿 |
| 补 | `test_fixture_minimal_shape_matches_measurement` (`:592`) | worker.log=167 B（160~179）、marker 距 EOF=40 B、含 `[worker] done exit=0`、队列行 `failed` | AC-014 | 绿 |
| P8 | `test_p8_abort_budget_exhausted_stalls_l3_aborted` (`:613`) | 专用预算耗尽 ⇒ 无 `l3-a3`、stall `reason_code=l3-aborted`、`loop=l3abort:<key>`、1/1/0、`_stall_family=l3`、复算无 drift | AC-001/003 | 绿 |

映射到 AC/VC：AC-001→P1/P2/P8；AC-002→VC-003 用例；AC-003→P3/P4/P5/P8；AC-004→P6/P7/N1-N6/sweep；AC-014→X1/X2/X3/形状锁。VC-001/002/003/004/005/006/017 全覆盖（VC-001 另由 P8 的 stall 面二次覆盖）。

## 3 `[VERIFY]` 命令原文 + 真实输出

### 3.1 命令 ①（卡内原文）

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_l3_aborted.py -q -p no:randomly
....................                                                     [100%]
20 passed in 0.27s
```

`[VERIFY]` 行（追加 `-s` 以显示用例内实测断言输出；命令本身同上加 `-s`）：

```
[VERIFY] VC-001: aborted=1 no_verdict=0 worker_status=failed deciding_source=none
[VERIFY] VC-002: keys=8 done_exit_zero=true retry_used=0 retry_limit=1
[VERIFY] VC-004: reroll=true abort_used=1
[VERIFY] VC-005: reroll=true used=1 limit=1
[VERIFY] VC-004: reroll_verdict=meets phase=DONE advance_exit=0 aborted_events=1
[VERIFY] VC-006: false_positives=0 case=report-qualifies failed_status=no-verdict done_status=meets
[VERIFY] VC-006: false_positives=0 case=output-qualifies failed_status=no-verdict done_status=meets
[VERIFY] VC-006: false_positives=0 case=two-sections-plus-marker marker_present=true verdict=meets
[VERIFY] VC-006: false_positives=0 case=no-marker verdict=no-verdict
[VERIFY] VC-006: false_positives=0 case=marker-outside-tail verdict=no-verdict
[VERIFY] VC-006: false_positives=0 case=provider-403 verdict=no-verdict
[VERIFY] VC-006: false_positives=0 case=real-fail verdict=below marker_variant=below
[VERIFY] VC-006: false_positives=0 case=prose-report verdict=below
[VERIFY] VC-006: false_positives=0 cases=6
[VERIFY] VC-003: exclusive=true classes=3 a=meets b=aborted c=below
[VERIFY] VC-017: counterfactual=fingerprint-removed with_fingerprint=aborted without_fingerprint=no-verdict p1_would_be_red=true
[VERIFY] VC-017: counterfactual=marker-outside-tail inside=aborted outside=no-verdict tail_bytes=167 fail_closed=true
[VERIFY] VC-017: counterfactual=qualifying-source-clause-removed with_clause=meets without_clause=aborted p6_would_be_red=true
[VERIFY] VC-002: worker_log_bytes=167 marker_from_eof=40 queue_status=failed
[VERIFY] VC-001: aborted_events=2 stalled=true reason_code=l3-aborted loop=l3abort:feature-inline-marker-patchkit cause_class=l3-aborted
20 passed in 0.28s
```

### 3.2 命令 ②（回归，卡内原文）

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py -q -p no:randomly
...................................FF.................                   [100%]
================================== FAILURES ===================================
____________________ test_reason_code_closed_set_is_closed ____________________

    def test_reason_code_closed_set_is_closed() -> None:
        assert set(conductor.STALL_REASON_CODES) <= conductor.REASON_CODES
>       assert len(conductor.STALL_REASON_CODES) == 12
E       AssertionError: assert 13 == 12
E        +  where 13 = len(('advance-class', 'l2-budget-rejected', 'l2-bonus-exhausted', 'l2-dispatch-refused', 'exec-exhausted', 'exec-dispatch-refused', ...))
E        +    where ('advance-class', 'l2-budget-rejected', 'l2-bonus-exhausted', 'l2-dispatch-refused', 'exec-exhausted', 'exec-dispatch-refused', ...) = conductor.STALL_REASON_CODES

test_autopilot_auto_decision.py:301: AssertionError
_________ test_all_twelve_mark_stalled_call_sites_pass_a_reason_code _________

    def test_all_twelve_mark_stalled_call_sites_pass_a_reason_code() -> None:
        source = pathlib.Path(conductor.__file__).read_text(encoding="utf-8")
        calls = _mark_stalled_calls(source)
>       assert len(calls) == 12, f"expected 12 call sites, found {len(calls)}"
E       AssertionError: expected 12 call sites, found 13
E       assert 13 == 12
E        +  where 13 = len(['mark_stalled(\n        project_root, st, key,\n        _one_line(\n            f"advance {edge} 连续 {count} 次失败（class...refused", loop=loop,\n                used_rounds=used, round_limit=budget, credits_used=credits,\n            )', ...])

test_autopilot_auto_decision.py:333: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed
FAILED test_autopilot_auto_decision.py::test_all_twelve_mark_stalled_call_sites_pass_a_reason_code
2 failed, 52 passed in 1.72s
```

- 这 2 处红即卡文点名的 **T-14 计数锁（12→13/14，工作区实际 13）**，与开工前实测基线逐字节一致（开工前同样 `2 failed, 52 passed`）；**未改该文件**。
- 卡文预告的 `:338`（`codes == set(conductor.STALL_REASON_CODES)`）实测**不红**：13 个调用点与 13 个原因码集合相等，T-14 收口时只需把 `:301` 与 `:333` 的 `== 12` 各 +1（T-10 的 `contract-unauthorized` 再 +1 到 14）。

## 4 非空洞对照（贴实际失败输出）

### 4.1 X1：摘掉指纹判定 ⇒ P1 实跑转红

复现方式（仓库外临时 harness，`%TEMP%/mwg-t06/x1_red.py`，**不修改任何仓库文件**）：autouse fixture 把 `conductor._l3_stream_aborted` 置为恒 `False`，然后**直接调用交付文件里的 P1 用例本体**。实跑：

```
$ cd packages/multi-workers && python -X utf8 -m pytest %TEMP%/mwg-t06/x1_red.py -q -p no:randomly
F                                                                        [100%]
================================== FAILURES ===================================
______________________ test_p1_with_fingerprint_removed _______________________
    def test_p1_with_fingerprint_removed(tmp_path: pathlib.Path) -> None:
>       t06.test_p1_marker_without_qualifying_source_is_aborted(tmp_path)
C:\Users\wenbozhou\AppData\Local\Temp\mwg-t06\x1_red.py:29:
    def test_p1_marker_without_qualifying_source_is_aborted(
        tmp_path: pathlib.Path,
    ) -> None:
        _write_round(tmp_path, "l3-a1", log=_round_log("l3-a1", marker=True))
        assert not conductor._l3_qualifies(_PLACEHOLDER)
        verdict, status, source, fail_line = _round_verdict(tmp_path, "l3-a1", "failed")
>       assert (verdict, status, source, fail_line) == (
            "aborted", "failed", None, None,
        ), (verdict, status, source, fail_line)
E       AssertionError: ('no-verdict', 'failed', None, None)
E       assert ('no-verdict'...', None, None) == ('aborted', '...', None, None)
E         At index 0 diff: 'no-verdict' != 'aborted'
E         Use -v to get more diff
test_autopilot_l3_aborted.py:203: AssertionError
=========================== short test summary info ============================
FAILED ::test_p1_with_fingerprint_removed
1 failed in 8.47s
```

即：判据在位时 P1 得 `aborted`，摘掉后得 `no-verdict`（状态门短路）⇒ P1 的断言确实锚在 T-01 指纹上。

**还原并复验全绿**（仓库外 harness 未触碰仓库；随后原样重跑交付文件）：

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_l3_aborted.py -q -p no:randomly
....................                                                     [100%]
20 passed in 0.27s
```

### 4.2 X2（尾窗 fail-closed）+ X3（合格源子句）

- X2（`test_x2_tail_window_is_fail_closed`，交付文件内绿）：同一 marker 在尾窗内 ⇒ `aborted`；把 marker 移到文件首部 + 70,000 B 尾部填充 ⇒ `no-verdict`（不判 aborted），且 `_l3_worker_log_tail` 只读 167 B（≤64 KiB）。方向明确：宁可漏判也不误判。
- X3（`test_x3_qualifying_source_clause_is_load_bearing`，追加的第三条对照）：把 `_l3_qualifies` 置假 ⇒ P6 夹具（marker + 合格 `report.md`）从 `meets` 翻成 `aborted`；证明 P6/P7/N6 由「无合格源」子句承重，而非只看 marker。

## 5 关键坐标（文件:行号）

实现（T-01，只读对照，本卡未改）:

| 坐标 | 内容 |
|---|---|
| `conductor.py:1546` | `_L3_ABORT_MARKER = "stream closed before response.completed"` |
| `conductor.py:1551` | `_l3_worker_log_tail`（尾 64 KiB） |
| `conductor.py:1566` | `_l3_stream_aborted`（marker ∧ 无合格源） |
| `conductor.py:1583` | `_l3_output_bytes` |
| `conductor.py:1648` | 指纹调用点（状态门之前） |
| `conductor.py:1922` / `:1928` | `l3abort:{key}` / `abort_limit` |
| `conductor.py:1960` | `if verdict == "aborted":` |
| `conductor.py:1969` / `:1978-1986` | timeline 事件名 / 固定八元组 data |
| `conductor.py:1990` / `:2002` | 专用重掷 dispatch / `mark_stalled(reason_code="l3-aborted")` |
| `conductor.py:5127`+`:5139` | `STALL_REASON_CODES` 含 `l3-aborted` |
| `conductor.py:5529` | `_stall_family` 把 `l3abort:` 归 `l3` |
| `conductor.py:5600/5614` | `_recompute_l3_stall_code` 以 `used+abort_used` 复算、aborted ⇒ `l3-aborted` |

用例（本卡交付）: 见 §2 表格的 `(:行号)`；夹具形状锁在 `test_autopilot_l3_aborted.py:592`，固定八元组常量在 `:73`，marker 常量在 `:60`。

## 6 契约遵守与口径说明

- 夹具**逐字**含 `stream closed before response.completed`（`:60`），子串匹配、不断言出处；`worker.log`=167 B、marker 距 EOF=40 B、含 `[worker] done exit=0`、队列行 `status=failed`（形状锁用例实测）。
- **N3 口径**：卡文写「provider 403（有 marker 但不属本类）」。按 RQ-1 F4/F5，D 类 （provider 403） 的 `worker.log` **没有** stream marker（语料上 marker 把它切成 6B/2D），且实现谓词是「marker ∧ 无合格源」——marker 在位且无合格源必判 aborted。故 N3 按语料实测形状复刻：403 错误行 + `done exit=0`（两者都在），但**无** stream marker，断言不判 aborted（AC-004 0 假阳性）。这一点在用例 docstring（`:399`）与本节留痕。
- 真实语料（E2Feature / FeatureMigrator）**未读取**、**未入仓**、**未引用外部绝对路径**（`Select-String` 扫 `E2Feature|FeatureMigrator|C:\|H:\|E:\|AppData` 零命中）。
- 未 commit、未 `git add`、未触碰 `_workers.parallel`/`_workers.acked`/`_index.parallel`，未 kill 进程。

## 7 并发与遗留（明说）

- 并发：本卡会话期间并行的 T-07 已把 tick 段改动落盘，`conductor.py` 行号相对 T-01 回执整体下移（如指纹谓词 `:1566`、状态门前调用 `:1648` 未变，abort 分支 `:1960`、`_stall_family:5529`、`_recompute_l3_stall_code:5600+` 下移）。本卡用例在**当前**工作树上实跑全绿；未观察到 T-04 `gates.py` / T-07 `tick` 相关的瞬时失败（`test_p8` 的 stall 路径经 `gates.enumerate` 正常）。
- 遗留：`test_autopilot_timeline.py` 的 `EVENT_TYPES` 计数锁（归 T-14/T-03）不在本卡 `[VERIFY]` 范围，未纳入本卡红数；本卡只负责「新原因码不引入 drift 类失败」，命令 ② 的 2 红即该口径的全部差异。
- 自审：20 个用例全部打印 `[VERIFY]` 行（§3.1），数值均来自实跑；非空洞对照 3 组（X1/X2/X3），X1 附实际失败输出（§4.1）。
