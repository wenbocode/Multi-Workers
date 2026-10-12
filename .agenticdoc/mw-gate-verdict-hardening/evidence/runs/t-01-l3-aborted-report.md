# T-01 回执：G1 中止指纹 `l3-aborted` + 专用有界重掷

- 卡: `tasks/T-01-l3-aborted.md`（worker 派发路径 `workers/mwg-t01-l3-aborted/`）
- 写面: `packages/multi-workers/autopilot/conductor.py`（L3 段 + 卡点名的复算接线）
- 基线: HEAD `776b82d7f`（卡文写 `10446aefb`；两者之差仅 `1cf35637f` 一处 `:6326` 的 defer ledger 修复，**在本卡 L3 写面之外**）
- 结果: **实现完成；X1/X2/X3 全绿；`[VERIFY]` 唯一红 = 2 处 `STALL_REASON_CODES`/call-site 计数锁（12→13，归属 T-14，卡文已点名）**

## 1 基线核对（开工前）

```
$ git rev-parse --short HEAD
776b82d7f
$ git status --porcelain -- packages/multi-workers/autopilot/conductor.py
(空)
$ git diff --stat 10446aefb..HEAD -- packages/multi-workers/autopilot/conductor.py
 packages/multi-workers/autopilot/conductor.py | 9 ++++++++-
 1 file changed, 8 insertions(+), 1 deletion(-)
$ git log --oneline 10446aefb..HEAD -- packages/multi-workers/autopilot/conductor.py
1cf35637f fix(multi-workers): record the executed defer ledger row on a shadow->live flip
```

结论：写面干净；`10446aefb..HEAD` 的 8 行改动落在 `_auto_decide_one`（`:6326` 邻域），与 L3 回路 `:1556-1940` 不重叠；T-07/T-10 的 `tick`/`done` 段无落盘改动。

## 2 改动清单（文件:行号）

`packages/multi-workers/autopilot/conductor.py`（+158 / -26）：

| 位置 | 内容 |
|---|---|
| `:1546-1548` | 指纹常量 `_L3_ABORT_MARKER = "stream closed before response.completed"`、`_L3_ABORT_TAIL_BYTES = 64 * 1024`、`_L3_ABORT_DONE_ZERO_RE`（`\[worker\] done exit=0`） |
| `:1551` `_l3_worker_log_tail` | 尾 64 KiB 读；`open("rb")` + `seek(END)` + `seek(size-64KiB)`，镜像 `mw_common.parse_end_exit`（`mw_common.py:2279-2304`，`_TRACE_TAIL_BYTES = 64 * 1024`）；缺文件/OSError → `""`（fail-closed） |
| `:1566` `_l3_stream_aborted` | 谓词 = 尾窗含 marker **∧** 无任何可读源两节齐备（复用 `_l3_source_paths`/`_l3_read_source`/`_l3_qualifies`）。marker 单判不够；合格源永远优先 ⇒ 三类构成划分 |
| `:1583` `_l3_output_bytes` | 事件 `data.output_bytes`（该轮 `output.md` 字节数，缺失 → `None`） |
| `:1648` `_l3_round_verdict` | 指纹落在**状态门 `:1651` 之前**：`if _l3_stream_aborted(...): return "aborted", status or "no-row", None, None`。`key_dir` 上移；4 元组长度不变 |
| `:1922` | 专用 loop 标签 `l3_abort_loop = f"l3abort:{key}"` |
| `:1928-1931` | `abort_limit = max(0, int(cfg.get("l3_abort_retry_limit", 1)))`（缺键回落 1，不定义 T-02 的键）；`abort_used = rounds.get(l3_abort_loop, 0)`；`round_no = used + abort_used` |
| `:1933-1940 / :2035 / :2067 / :2103 / :2161` | 轮号 stem 与共享链同号：`l3-a{round_no}` / `l3-a{round_no+1}`；`attempt=` 仍 `used+1`（普通轮）/`abort_used+1`（abort 轮）；`repair-a{round_no}` |
| `:1960-2013` | `if verdict == "aborted":` 分支插在 `if verdict == "no-verdict":`（`:2014`）之前：发 timeline `l3-aborted` + 固定八元组 `data`；`abort_used < abort_limit` ⇒ 派 `l3-a{round_no+1}`（`loop=l3abort:{key}`）；否则 `_persist_l3_verdict` + `mark_stalled(reason_code="l3-aborted", loop=l3_abort_loop, used_rounds=abort_used, round_limit=abort_limit, credits_used=0)`（`:2002`） |
| `:1919-1931` | `l3_limit` 语义不变（`:1930`，= `l3_budget + _resume_credits`），只约束普通轮；abort 不占共享预算 |
| `:5021` | `STALL_REASON_CODES` 增 `"l3-aborted"`（12→13；**14 的收口含 T-10 的 `contract-unauthorized`，计数锁由 T-14 改**） |
| `:5411` | `_stall_family`：`loop.startswith("l3abort:") → "l3"`（否则 `recompute_stall_cause` 落 `advance-class` ⇒ `stalled-reason-drift`） |
| `:5469-5500` `_recompute_l3_stall_code` | `round_no = l3:{key} + l3abort:{key}`（原仅 `used`）；`verdict == "aborted" ⇒ "l3-aborted"`；判定放在 stale provenance-suspect 之前（abort 轮不写 provenance，旧轮 suspect 不得遮蔽终止轮结论） |
| `:5507` `recompute_false_negative_class` | 终止轮改 `round_no`（D-003 点名的第二处消费者）；abort 轮 ⇒ `undecidable`（fail-closed，卡文 D-004 反向保证） |

契约遵守：
- `_L3_SOURCE_ORDER` / FAIL 判据（`_L3_FAIL_*_RE`）/ `_l3_resolve_source` / `_l3_provenance_record` / `l3-verdict-provenance.json` **零改动**。
- 不要求队列行 `status=done`；指纹在 `failed` 短路之前生效（6/6 真例形态）。
- 尾窗口径复用 64 KiB 先例，未新造第二种尾读语义。
- 只改 `conductor.py`（不含 T-07/T-10 段）；未动 `config.py`（T-02 已落 `l3_abort_retry_limit` 默认 1、域 `(0,10)`）、`timeline.py`（T-03 已落 `l3-aborted` 词表）、`gates.py`。

## 3 `[VERIFY]` 命令原文 + 实跑输出

### 3.1 卡内命令 1（既有套件）

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py -q -p no:randomly
...................................FF.................                   [100%]
================================== FAILURES ===================================
____________________ test_reason_code_closed_set_is_closed ____________________
    def test_reason_code_closed_set_is_closed() -> None:
        assert set(conductor.STALL_REASON_CODES) <= conductor.REASON_CODES
>       assert len(conductor.STALL_REASON_CODES) == 12
E       AssertionError: assert 13 == 12
...
_________ test_all_twelve_mark_stalled_call_sites_pass_a_reason_code _________
        calls = _mark_stalled_calls(source)
>       assert len(calls) == 12, f"expected 12 call sites, found {len(calls)}"
E       AssertionError: expected 12 call sites, found 13
E       assert 13 == 12
test_autopilot_auto_decision.py:333: AssertionError
=========================== short test summary info ===========================
FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed
FAILED test_autopilot_auto_decision.py::test_all_twelve_mark_stalled_call_sites_pass_a_reason_code
2 failed, 52 passed in 1.74s
```

**这 2 处红是计数锁，本卡按卡文「12→14 的计数锁由 T-14 收口」不改测试文件。** 语义半边已自洽（点名校验）：

```
$ python -X utf8 <tmp>/mwg_t01_map.py
call_sites 13
missing_reason_code []
codes == STALL_REASON_CODES True
stall_codes_len 13
l3-aborted in codes True
```

即：13 个 `mark_stalled` 调用点全部带 `reason_code=`，且源码内码集合与 `STALL_REASON_CODES` 完全相等 —— T-14 只需把 `test_autopilot_auto_decision.py:301` 的 `== 12` 与 `:333` 的 `== 12` 各 +1（T-10 的 `contract-unauthorized` 再 +1 到 14）。

### 3.2 卡内命令 2（新测试文件）

```
$ test -f test_autopilot_l3_aborted.py && python -X utf8 -m pytest test_autopilot_l3_aborted.py -q -p no:randomly
test_autopilot_l3_aborted.py NOT PRESENT (T-06 pending) -> skipped
```

`test_autopilot_l3_aborted.py` 是 **T-06 的交付**，本卡不新建（遵守卡文「不要自己另建同名文件」）。**新文件待 T-06。**

### 3.3 追加回归（L3 消费者 + 卡文点名的复算面）

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_stall.py test_autopilot_conductor_exec.py \
    test_autopilot_verdict_source_fallback.py test_autopilot_verdict_provenance_guard.py \
    test_autopilot_fail_marker_forms.py test_autopilot_timeline.py \
    test_autopilot_conductor.py test_autopilot_auto_decision.py -q -p no:randomly
FAILED test_autopilot_timeline.py::test_append_line_schema_all_event_types - ...
FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed
FAILED test_autopilot_auto_decision.py::test_all_twelve_mark_stalled_call_sites_pass_a_reason_code
3 failed, 179 passed in 12.07s
```

- `test_autopilot_timeline.py` 的红是 `len(EVENT_TYPES) == 23` vs 实际 26：**T-03 已把 3 个事件名（含 `l3-aborted`）写进 `timeline.py`**（工作区 `git diff --stat -- autopilot/timeline.py` = 11 insertions），计数锁归 **T-14**（plan §5.5：23→26）。该测试文件只 `from autopilot import timeline`（`test_autopilot_timeline.py:25`），不 import conductor ⇒ **与本卡改动无关**。
- 其余 179 通过，覆盖 L3 meets / below / no-verdict / provenance-suspect / reprompt / repair 全部既有路径（无 abort 轮时 `round_no == used` 逐路径不变）。

## 4 非空洞对照 X1/X2/X3（实跑，脚本原文见 §6）

> 说明：T-06 用例尚未落地，以下为本卡**临时**最小对照脚本（仓库外 `%TEMP%/mwg_t01_control.py`），走**真实** `conductor._l3_round_verdict` 与**真实** `conductor.tick` 链。**它不替代 T-06**（T-06 还需 P1-P7/N1-N6 完整矩阵 + 真实 160~179 B 夹具 + 双语言 parity）。

```
$ python -X utf8 %TEMP%/mwg_t01_control.py
== X2: tail-window boundary (fail-closed) ==
[PASS] marker inside tail 64KiB -> aborted :: verdict=aborted
[PASS] marker outside tail 64KiB -> NOT aborted :: verdict=no-verdict
[PASS] tail helper reads only the last 64KiB :: bytes=65536
== X3: three-way classification is a partition ==
[PASS] A (report.md fallback) -> meets :: A=meets
[PASS] B (marker, no qualifying source) -> aborted :: B=aborted
[PASS] C (two sections + FAIL) -> below :: C=below
[PASS] three verdicts pairwise distinct :: {A,B,C}={meets,aborted,below}
[PASS] C carries a fail line :: fail='| VC-002 | FAIL | (missing) |'
== X1: counterfactual (remove fingerprint -> red) ==
[PASS] fingerprint on: l3-aborted event recorded :: n=1
[PASS] data key set == fixed eight-tuple :: got=['done_exit_zero', 'output_bytes', 'recorded_at', 'retry_limit', 'retry_used', 'round', 'task_key', 'worker_status']
[PASS] retry_used=0 retry_limit=1 :: used=0 limit=1
[PASS] done_exit_zero=True :: done_exit_zero=True
[PASS] fingerprint on: reroll ap-k1-l3-a2 dispatched with loop l3abort:k1 :: a2 loop=True
[PASS] fingerprint off: NO l3-aborted event (counterfactual turns red) :: n=0
[PASS] fingerprint off: falls back to l3-no-verdict :: n=1
[PASS] fingerprint off: reroll uses shared loop l3:k1
== shared budget is not consumed (round_budget=1) ==
[PASS] round_budget=1 + one abort still rerolls (shared l3_limit untouched) :: a2 dispatched
== stall + recompute wiring (dedicated budget spent) ==
[PASS] key marked stalled :: status=stalled
[PASS] no ap-k1-l3-a3 dispatched
[PASS] stalled gate found :: n=1
[PASS] gate.reason_code == l3-aborted :: 'l3-aborted'
[PASS] gate.loop == l3abort:k1 :: 'l3abort:k1'
[PASS] counts used=1 limit=1 credits=0 :: 1/1/0
[PASS] _stall_family -> l3 :: l3
[PASS] recompute_stall_cause == l3-aborted (no stalled-reason-drift) :: cause='l3-aborted'

RESULT: all controls passed
```

- **X1（摘掉判据 ⇒ 转红）**：`conductor._l3_stream_aborted` 恒 `False` 后，同一输入**无** `l3-aborted` 事件、回落 `l3-no-verdict`、重掷用共享链 `loop: l3:k1`。判据生效。
- **X2（尾窗边界，fail-closed）**：marker 埋在首部 + 70,000 B 尾部填充（在尾 64 KiB 之外）⇒ `verdict=no-verdict`（**不**判 aborted）；同时证明读取字节数 `= 65536`。
- **X3（三类两两不同）**：同一输入造 A=`report.md` 回退（meets）/ B=marker+无合格源（aborted）/ C=两节+FAIL（below+fail_line）⇒ 集合 `{meets,aborted,below}`，两两不同。
- 额外：专用上限耗尽 ⇒ `mark_stalled` 后 `recompute_stall_cause == "l3-aborted"`（**无** `stalled-reason-drift`）；`round_budget=1` 下 abort 仍重掷（不占共享预算）。

## 5 未验证 / 遗留（明说）

- **`test_autopilot_l3_aborted.py` 未创建**（T-06 交付）；本卡的 P1-P7/N1-N6 完整矩阵与真实语料最小形状（160~179 B、marker 距 EOF ≤40 B）**未由正式用例锁**，仅有 §4 临时对照。
- **`STALL_REASON_CODES` 计数锁（12→13/14）未改**：归 **T-14**（卡文点名）。当前 `test_autopilot_auto_decision.py` 2 红为**已知预期红**。
- **`test_autopilot_timeline.py` 事件计数锁（23→26）已红**：归 **T-03（语义）/T-14（锁）**，非本卡写面。
- **`gates.py` 当前被另一 worker（T-04）改到不可 parse**（`NameError: name 'authorizes' is not defined`，`gates.py:699`）——这导致 §4 的 `gates.parse` 路径不可用，临时脚本改为从 gate 原文读机器字段并手工构造 `gates.Gate`。该文件不在本卡写面，**未触碰**。
- `mw_common.py:2287-2295` 等处 "the 12 `mark_stalled` call sites" 的注释未同步（非本卡写面，T-11/T-18 属地）。
- 真实语料（E2Feature/FeatureMigrator 的 6/6 abort 轮）**只读复算未在本卡重跑**（会话未读外部项目根）；判据正确性由 §4 合成夹具 + RQ-1 快照（6/6 marker 距 EOF 40 B、体积 160-179 B、max 14,120 B）背书。

## 6 临时对照脚本原文（不替代 T-06）

```python
"""Ad-hoc, repo-external control script for T-01 (mw-gate-verdict-hardening).

It does NOT replace T-06 (`test_autopilot_l3_aborted.py`); it only proves the
three non-vacuous controls the card demands (X1/X2/X3) against the real code
path (`conductor._l3_round_verdict` + the production `conductor.tick` chain).

Run:  python -X utf8 mwg_t01_control.py
"""
import pathlib
import shutil
import sys
import tempfile

MW = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers")
sys.path.insert(0, str(MW))

import test_autopilot_conductor_exec as harness  # noqa: E402
from autopilot import conductor, gates, state  # noqa: E402

MARKER = "stream closed before response.completed"
_ROUND_TAIL = (
    "[worker] start task=ap-k1-l3-a1 type=reviewer phases=-\n"
    "[worker] done exit=0 elapsed=1m tools=41 phases=-\n"
    + MARKER + "\n"
)

_failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def _bare_round(root: pathlib.Path, attempt: int, *, log: str | None,
                output: str | None, report: str | None = None) -> str:
    key_dir = root / ".agenticdoc" / "k1"
    tk = conductor.dispatch.task_key_for("k1", f"l3-a{attempt}")
    d = key_dir / "workers" / tk
    d.mkdir(parents=True, exist_ok=True)
    if log is not None:
        (d / "worker.log").write_text(log, encoding="utf-8", newline="\n")
    if output is not None:
        (d / "output.md").write_text(output, encoding="utf-8", newline="\n")
    if report is not None:
        (d / "report.md").write_text(report, encoding="utf-8", newline="\n")
    return tk


PLACEHOLDER = "# Task completed\n\nTools used: 0\n"

print("== X2: tail-window boundary (fail-closed) ==")
x2 = pathlib.Path(tempfile.mkdtemp(prefix="mwg-t01-x2-"))
try:
    _bare_round(x2, 1, log=_ROUND_TAIL, output=PLACEHOLDER)
    rows = [{"task_key": conductor.dispatch.task_key_for("k1", "l3-a1"),
             "status": "failed"}]
    inside = conductor._l3_round_verdict(x2, rows, "k1", 1)[0]
    check("marker inside tail 64KiB -> aborted", inside == "aborted", f"verdict={inside}")

    # marker in the FIRST bytes, >64 KiB of trailing padding -> outside the tail
    far_log = MARKER + "\n" + ("y" * 70000) + "\n"
    _bare_round(x2, 2, log=far_log, output=PLACEHOLDER)
    rows2 = [{"task_key": conductor.dispatch.task_key_for("k1", "l3-a2"),
              "status": "failed"}]
    outside = conductor._l3_round_verdict(x2, rows2, "k1", 2)[0]
    check("marker outside tail 64KiB -> NOT aborted",
          outside != "aborted", f"verdict={outside}")
    check("tail helper reads only the last 64KiB",
          len(conductor._l3_worker_log_tail(
              x2 / ".agenticdoc/k1/workers/"
              / conductor.dispatch.task_key_for("k1", "l3-a2") / "worker.log")) <= 64 * 1024,
          f"bytes={len(conductor._l3_worker_log_tail(x2 / '.agenticdoc/k1/workers/' / conductor.dispatch.task_key_for('k1', 'l3-a2') / 'worker.log'))}")
finally:
    shutil.rmtree(x2, ignore_errors=True)

print("== X3: three-way classification is a partition ==")
x3 = pathlib.Path(tempfile.mkdtemp(prefix="mwg-t01-x3-"))
try:
    _L3_MEETS = harness._L3_MEETS
    _L3_BELOW = harness._L3_BELOW
    # A: qualifying carrier written but wrong one (report.md fallback), marker present
    _bare_round(x3, 1, log=_ROUND_TAIL, output=PLACEHOLDER, report=_L3_MEETS)
    # B: marker + no qualifying source
    _bare_round(x3, 2, log=_ROUND_TAIL, output=PLACEHOLDER)
    # C: two sections + real FAIL marker
    _bare_round(x3, 3, log=_ROUND_TAIL, output=_L3_BELOW)
    verdicts = {}
    for attempt, status in ((1, "done"), (2, "failed"), (3, "done")):
        tk = conductor.dispatch.task_key_for("k1", f"l3-a{attempt}")
        v, _s, _src, fail = conductor._l3_round_verdict(
            x3, [{"task_key": tk, "status": status}], "k1", attempt)
        verdicts[attempt] = (v, fail)
    a, b, c = verdicts[1][0], verdicts[2][0], verdicts[3][0]
    check("A (report.md fallback) -> meets", a == "meets", f"A={a}")
    check("B (marker, no qualifying source) -> aborted", b == "aborted", f"B={b}")
    check("C (two sections + FAIL) -> below", c == "below", f"C={c}")
    check("three verdicts pairwise distinct", len({a, b, c}) == 3, f"{{A,B,C}}={{{a},{b},{c}}}")
    check("C carries a fail line", verdicts[3][1] is not None, f"fail={verdicts[3][1]!r}")
finally:
    shutil.rmtree(x3, ignore_errors=True)


def _tick_run(root: pathlib.Path, *, disable_fingerprint: bool,
              round_budget: int | None = None,
              second_abort: bool = False) -> dict:
    """Drive the real conductor.tick chain over one abort round (+optional
    2nd abort -> stall). Returns the observable outcome."""
    project = harness._verify_key_project(root)
    if round_budget is not None:
        cfg = harness.config.load_config(project)
        cfg["round_budget"] = round_budget
        harness.config.save_config(project, cfg)
    fake_advance, _calls = harness._fake_advance_factory(project)
    old_advance = conductor.advance.advance
    conductor.advance.advance = fake_advance
    old_fp = conductor._l3_stream_aborted
    if disable_fingerprint:
        conductor._l3_stream_aborted = lambda key_dir, task_key: False
    try:
        st = harness._state(project)

        def _write_abort_round(tk: str) -> None:
            d = project / ".agenticdoc" / "k1" / "workers" / tk
            d.mkdir(parents=True, exist_ok=True)
            (d / "worker.log").write_text(
                _ROUND_TAIL.replace("ap-k1-l3-a1", tk),
                encoding="utf-8", newline="\n")
            harness._worker_output(project, "k1", tk, PLACEHOLDER)
            harness._set_row(project, tk, "failed")

        conductor.tick(project, st)          # dispatch ap-k1-l3-a1
        _write_abort_round("ap-k1-l3-a1")
        conductor.tick(project, st)          # evaluate round 1
        if second_abort:
            _write_abort_round("ap-k1-l3-a2")
            conductor.tick(project, st)      # evaluate round 2 -> stall
        events = harness._events(project)
        rows = harness._rows(project, "ap-k1-l3-")
        a2_md = ""
        a2 = project / ".agenticdoc" / "k1" / "workers" / "ap-k1-l3-a2" / "task.md"
        if a2.is_file():
            a2_md = a2.read_text(encoding="utf-8")
        rm = None
        try:
            from autopilot import roadmap
            rm = roadmap.load_roadmap(
                project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
        except Exception:
            pass
        return {"project": project, "events": events, "rows": rows,
                "a2_md": a2_md, "verdict_rounds": harness._state(project)}
    finally:
        conductor.advance.advance = old_advance
        conductor._l3_stream_aborted = old_fp


print("== X1: counterfactual (remove fingerprint -> red) ==")
x1 = pathlib.Path(tempfile.mkdtemp(prefix="mwg-t01-x1-"))
try:
    on = _tick_run(x1 / "on", disable_fingerprint=False)
    on_events = [e for e in on["events"] if e["ev"] == "l3-aborted"]
    check("fingerprint on: l3-aborted event recorded",
          len(on_events) == 1, f"n={len(on_events)}")
    eight = {"round", "task_key", "worker_status", "output_bytes",
             "done_exit_zero", "retry_used", "retry_limit", "recorded_at"}
    if on_events:
        got = set(on_events[0].get("data", {}))
        check("data key set == fixed eight-tuple", got == eight,
              f"got={sorted(got)}")
        d = on_events[0]["data"]
        check("retry_used=0 retry_limit=1",
              d.get("retry_used") == 0 and d.get("retry_limit") == 1,
              f"used={d.get('retry_used')} limit={d.get('retry_limit')}")
        check("done_exit_zero=True", d.get("done_exit_zero") is True,
              f"done_exit_zero={d.get('done_exit_zero')!r}")
    check("fingerprint on: reroll ap-k1-l3-a2 dispatched with loop l3abort:k1",
          "ap-k1-l3-a2" in [r["task_key"] for r in on["rows"]]
          and "loop: l3abort:k1" in on["a2_md"]
          and "attempt: 1" in on["a2_md"],
          f"a2 loop={'l3abort:k1' in on['a2_md']}")

    off = _tick_run(x1 / "off", disable_fingerprint=True)
    off_aborted = [e for e in off["events"] if e["ev"] == "l3-aborted"]
    off_noverdict = [e for e in off["events"] if e["ev"] == "l3-no-verdict"]
    check("fingerprint off: NO l3-aborted event (counterfactual turns red)",
          len(off_aborted) == 0, f"n={len(off_aborted)}")
    check("fingerprint off: falls back to l3-no-verdict",
          len(off_noverdict) == 1, f"n={len(off_noverdict)}")
    check("fingerprint off: reroll uses shared loop l3:k1",
          "loop: l3:k1" in off["a2_md"] and "loop: l3abort:k1" not in off["a2_md"])
finally:
    shutil.rmtree(x1, ignore_errors=True)

print("== shared budget is not consumed (round_budget=1) ==")
x4 = pathlib.Path(tempfile.mkdtemp(prefix="mwg-t01-x4-"))
try:
    r = _tick_run(x4, disable_fingerprint=False, round_budget=1)
    check("round_budget=1 + one abort still rerolls (shared l3_limit untouched)",
          "ap-k1-l3-a2" in [x["task_key"] for x in r["rows"]]
          and "loop: l3abort:k1" in r["a2_md"],
          "a2 dispatched")
finally:
    shutil.rmtree(x4, ignore_errors=True)

print("== stall + recompute wiring (dedicated budget spent) ==")
x5 = pathlib.Path(tempfile.mkdtemp(prefix="mwg-t01-x5-"))
try:
    r = _tick_run(x5, disable_fingerprint=False, second_abort=True)
    project = r["project"]
    from autopilot import roadmap
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    check("key marked stalled", rm.stages[0].key_status["k1"] == "stalled",
          f"status={rm.stages[0].key_status['k1']}")
    check("no ap-k1-l3-a3 dispatched", "ap-k1-l3-a3" not in [x["task_key"] for x in r["rows"]])
    def _field(text: str, name: str) -> str | None:
        import re
        m = re.search(rf"^{name}:\s*(.*)$", text, re.M)
        return m.group(1).strip() if m else None

    # NB: gates.parse is currently broken by another worker's in-progress edit
    # (T-04 `authorizes` in gates.py) — outside this card's write face. Build
    # the Gate from the raw machine fields instead.
    stalled = []
    for p in conductor.gates_dir(project).glob("gate-*.md"):
        text = p.read_text(encoding="utf-8")
        if "kind: stalled" not in text:
            continue
        stalled.append(gates.Gate(
            id="gate-0001", kind="stalled", stage=None, key="k1",
            created_at="", created_by="", question="", context_refs=[],
            status="pending", answered_at=None, answered_by=None, note=None,
            path=p,
            reason_code=_field(text, "reason_code"),
            loop=_field(text, "loop"),
            used_rounds=int(_field(text, "used_rounds")),
            round_limit=int(_field(text, "round_limit")),
            credits_used=int(_field(text, "credits_used")),
        ))
    check("stalled gate found", len(stalled) == 1, f"n={len(stalled)}")
    if stalled:
        g = stalled[0]
        check("gate.reason_code == l3-aborted", g.reason_code == "l3-aborted", f"{g.reason_code!r}")
        check("gate.loop == l3abort:k1", g.loop == "l3abort:k1", f"{g.loop!r}")
        check("counts used=1 limit=1 credits=0",
              (g.used_rounds, g.round_limit, g.credits_used) == (1, 1, 0),
              f"{g.used_rounds}/{g.round_limit}/{g.credits_used}")
        check("_stall_family -> l3", conductor._stall_family(g) == "l3",
              conductor._stall_family(g))
        cause = conductor.recompute_stall_cause(project, g)
        check("recompute_stall_cause == l3-aborted (no stalled-reason-drift)",
              cause == "l3-aborted", f"cause={cause!r}")
finally:
    shutil.rmtree(x5, ignore_errors=True)

print()
if _failures:
    print(f"RESULT: {len(_failures)} control(s) FAILED: {_failures}")
    sys.exit(1)
print("RESULT: all controls passed")
```
