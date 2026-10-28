# T10 report corrections (T10b) - original report NOT overwritten

Owner of the original: `.agenticdoc/mw-decision-dashboard/workers/dd-monitor-service/report.md`.
This file is the correction record; the T10 report and its evidence are left verbatim.

## 1. Artifact line counts

| artifact | original T10 report | review-cited actual | measured at T10b baseline | after T10b |
|---|---:|---:|---:|---:|
| `packages/multi-workers/decision_monitor.py` | 1830 | 2090 | 2089 | 2535 |
| `packages/multi-workers/test_decision_monitor.py` | 1267 | 1433 | 1432 | 1865 |
| monitor test count | 38 (37 passed + 1 skipped) | 38 | 38 | 53 (52 passed + 1 skipped) |

Measurement method (evidence/runs/T10b-monitor-fixes/green-files.txt): UTF-8 decode then
`splitlines()`; the newline count is identical (each file ends with exactly one newline), so the
2090/1433 vs 2089/1432 difference is a counting convention (1-based last-line label), not a different
file. Both numbers are recorded as required; the 1830/1267 figures in the T10 report were stale
draft sizes and are corrected to the on-disk values.

## 2. "full range exhaustion" metric

T10 report `[VERIFY] unrelated_kills=0 (range 耗尽仍可连接占用者)` and verify-summary called the
test "range exhaustion", but the test held only one candidate port. Corrected metric:
`test_full_100_port_isolated_range_exhaustion_leaves_every_occupant_alive` binds and holds a
contiguous 100-port local block outside the monitor range, asserts
`attempted_count=100` (echo truncated to 20), and connects to all 100 occupants afterwards.
Evidence: `probe-observations.txt` (block 25101..25200, `attempted_count 100`,
`occupants still accepting 100`, `occupant sockets open 100`) and the green monitor log.
The former single-port test is retained under the honest name
`test_single_occupied_candidate_fails_explicitly_without_touching_the_occupant`.

## 3. Application-window metric

The original `app_window_false_success=0` was backed by `launch_app_window(...)["ok"] is True`.
That `ok` only meant "Popen returned". The result now has `spawned` plus
`visibility="not-verified"` (or `not-opened` on failure), and `ok` is gone; `spawned=True` is never
reported as a visible window. VC-006 (real window, 2 tabs) remains with T12/T14 and is not claimed.

## 4. Stale-recovery metric

The original `stale_recovery=pass` covered two of the three D-001 conditions (dead PID + identity
recheck). It now also requires a real loopback `ECONNREFUSED` (Windows `WSAECONNREFUSED`/10061) on
the recorded port, observed under the verified start-lock guard, with timeout/permission/unknown and
"an unrelated listener answered" all keeping the state. Evidence: `probe-observations.txt`
(real closed loopback -> `refused`, errno 10061, 2.06 s) and the recovery tests.

## 5. POSIX 0600 skip (retained, not re-labelled)

`test_secret_file_is_owner_only_on_posix` still skips on Windows. The skip is not evidence of Windows
user isolation; the T10 statement "Windows does not treat chmod as the user boundary" stands.
