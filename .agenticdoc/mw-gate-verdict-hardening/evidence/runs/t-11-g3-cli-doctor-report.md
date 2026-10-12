# T-11 report: G3 CLI (`mw autopilot contract-guard`) + doctor surface

- Key: `mw-gate-verdict-hardening` (phase=EXECUTE)
- Card: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-11-g3-cli-doctor.md`
- Worker task: `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t11-g3-cli-doctor/task.md`
- Baseline HEAD: `776b82d7fa3af2a36a5a46717be6d5feac8ba0a0`
- Dependencies T-04 + T-10: both **done + acked** (reports read before starting)
- AC: AC-011, AC-013 · VC: VC-016
- Result: **PASS** - all three `[VERIFY]` commands green; the two required non-hollow contrasts are real and the two "strip the segment" counterfactuals turn their named cases red.

## 0. Write-face snapshot at start (`git status --porcelain`)

```
> git status --porcelain -- packages/multi-workers/mw.py packages/multi-workers/mw_common.py
 M packages/multi-workers/mw_common.py
> git rev-parse HEAD
776b82d7fa3af2a36a5a46717be6d5feac8ba0a0
```

`mw.py` clean; `mw_common.py` carries only this key's already-acked T-18/T-20 work (the diff grew, it was never reverted: `git diff --stat` for `mw_common.py` = 528 insertions / 54 deletions vs 378/46 before this card). No external key's uncommitted change is in either file.

T-18's three criteria are untouched and my new criterion is the same caliber:

```
mw_common.py:3200  queue-rows-unparsable   (T-18)
mw_common.py:3210  queue-burst-shape       (T-18)
mw_common.py:3217  run-ledger-conflict     (T-18)
mw_common.py:3301  contract-guard          (T-11, new; report + keep fail-closed)
```

## 1. Deliverables (symbol + actual line)

### 1.1 `packages/multi-workers/mw.py` (autopilot section, exclusive write face)

| What | Coordinate |
|---|---|
| `cmd_autopilot` dispatch of `contract-guard` (read-only, no lock, no write) | `mw.py:3560-3564` |
| `_ap_contract_guard()` - CLI body; delegates the whole judgement to T-04 `contract_guard.evaluate`, never re-derives freeze/diff/approval | `mw.py:3812-3879` |
| argparse: `mw autopilot contract-guard --project <dir> [--key <key>] [--json]` | `mw.py:5503-5517` |

Behaviour (exit code mirrors T-10's done gate, so the sanctioned PM tool path and the conductor agree):

- `--key K`: one entry; `freeze` present/absent, `changed_ids`, `carrier` (approval record hit or null), `refused`.
- no `--key`: every key that carries a usable freeze sidecar (same set the doctor reports).
- exit `0` = no refusal (includes "no anchor"); `1` = unauthorized frozen-contract change **or** unreadable gate queue (fail-loud, not fail-open).
- `--json` is `sort_keys=True`, keys sorted, freeze path project-relative posix: no timestamp, no absolute path (reproducible; asserted byte-equal across two runs).

### 1.2 `packages/multi-workers/mw_common.py` (exclusive write face)

| What | Coordinate |
|---|---|
| `_contract_guard_entry()` - one key's verdict in the wire shape; `no_anchor` stripped from the doctor shape | `mw_common.py:2989-3015` |
| `_contract_guard_scan()` - per-key scan; returns `None` when no key has a usable freeze (so the doctor key **never appears**) | `mw_common.py:3017-3058` |
| `_doctor_gates()` adds `contract_guard` only when the scan is non-None (computed before the missing-gates-dir early return) | `mw_common.py:3080-3082` |
| `_gates_text_alerted()` - new trigger condition (`unauthorized`) so the `gates:` text line appears for the alert | `mw_common.py:3140-3146` |
| `_doctor_issues()` - new fail-closed issue, inserted after the I9/VC-048 block, before `roadmap_section` | `mw_common.py:3295-3305` |
| `format_doctor_text()` - conditional `contract_suffix` (only when non-zero), same pattern as `prose_suffix` | `mw_common.py:3531-3541` |

New issue text (I9-style "report but keep fail-closed", T-18 prefix caliber):

```
contract-guard: key demo-key contract text changed without authorization (AC-001) since the
freeze (.agenticdoc/demo-key/evidence/contract-freeze.json) - advance-to-done refused; answer a
gate with authorizes: ["contract-change"] or revert the AC/VC text
```

Doctor section shape (JSON), only for freeze-carrying keys:

```json
"contract_guard": {
  "keys": [{"key": "demo-key",
            "freeze": ".agenticdoc/demo-key/evidence/contract-freeze.json",
            "changed_ids": ["AC-001"], "authorized": false,
            "carrier": null, "reasons": ["contract-unauthorized"]}],
  "unauthorized": 1
}
```

### 1.3 Tests (add-only, existing assertions untouched)

- `test_doctor_gates.py:738/748/780/810/822` - absent-without-freeze, unauthorized-is-an-issue (+ exit 1 + text suffix), authorized-is-silent, zero-write, reproducible/sorted/relative.
- `test_mw_autopilot_cli.py:497/514/533/546/562` - no-freeze read-only, refuse (exit 1), approved carrier clears it, all-keys + byte-reproducible, argparse shape (`--project` required -> exit 2).

## 2. `[VERIFY]` (commands verbatim, real output)

### 2.1 card command 2 - the three test files

```
> cd packages/multi-workers && python -X utf8 -m pytest test_mw_autopilot_cli.py test_doctor_gates.py test_autopilot_contract_guard.py -q -p no:randomly
82 passed, 66 warnings in 28.39s
```

(The 66 warnings are the pre-existing Windows subprocess `_readerthread` UTF-8 decode warnings of `test_mw_autopilot_cli.py`; they exist on the baseline too and are environment noise.)

`[VERIFY]` markers from the new cases (`-s -k contract_guard`):

```
[VERIFY] VC-016: freeze_keys=0 contract_guard_key=absent
[VERIFY] VC-016: unauthorized=1 changed_ids=AC-001 exit_code=1
[VERIFY] VC-016: carrier=gate-0001 unauthorized=0
[VERIFY] VC-016: zero_write=True entries=6
[VERIFY] VC-016: reproducible=True sorted_keys=k0,k1
[VERIFY] VC-016: no_freeze=exit 0 read_only=True
[VERIFY] VC-016: refused=True changed_ids=['AC-001'] carrier=None
[VERIFY] VC-016: carrier=gate-0001 refused=False
[VERIFY] VC-016: reproducible=True keys=k0,k1 unauthorized=2
10 passed, 57 deselected, 10 warnings in 5.03s
```

### 2.2 card command 1/3 - doctor before/after on the real (no-freeze) project

Before (captured **before** any edit; verbatim command shape, PowerShell `>` writes UTF-16LE):

```
> cd packages/multi-workers && python -X utf8 mw.py doctor --project H:\git\Multi-Workers --json > <tmp>/doctor-before.json
exit=0
sha256(file bytes) = 09CF24F7DF56848EEB018E8DBAC0ED1BDEBED80838C4C3A0B16EE58CDCB0C85C
```

After (final code, post-restore):

```
> cd packages/multi-workers && python -X utf8 mw.py doctor --project H:\git\Multi-Workers --json > <tmp>/doctor-after.json
exit=0
sha256(file bytes) = 0F255C0F3CB7E79FD8704452C9DBABFFCE74AD8C598D1674C2DB4C1C123F2D5B
```

Byte-level reconciliation (UTF-8 content after decoding the UTF-16 redirect):

```
[before] utf8_sha256 = 072d5d01706114e5f5dd50dc47069fa59d93ec4ee87fa331ff0d40fab4d44422
[after ] utf8_sha256 = aa772383874938eb291e9cd9e39983ddbdc9b336e9c3ca5b02e4c6e42c136f0b
full_json_diff_count = 2
   .worker_liveness[0].age_s            | 7 -> 29
   .worker_liveness[0].last_heartbeat   | 2026-10-10T10:33:06.959Z -> 2026-10-10T10:39:37.073Z
norm_identical (age_s + last_heartbeat masked) = True
before norm_sha256 = f37e7e58464fce570ea1f4812be785af9d2b89bf6a045abdda1e105004365b4a
after  norm_sha256 = f37e7e58464fce570ea1f4812be785af9d2b89bf6a045abdda1e105004365b4a
gates_identical = True   (gates subtree sha256 = 9a890349223fd882760eec8d4f0101f8a3007c2df8d6e7d767198f1842d29e50)
contract_guard_in_before = False
contract_guard_in_after  = False
```

Difference cause: the only two differing leaves are a **live worker's heartbeat** (this very session) - `age_s` and `last_heartbeat`. Both are volatile and unrelated to this card; after masking exactly those two fields the full JSON is hash-identical. The `gates` subtree is byte-identical (the new key is absent because no freeze exists).

Text output - byte-identical **without** any masking:

```
> python -X utf8 mw.py doctor --project H:\git\Multi-Workers > <tmp>/doctor-before.txt   # sha256 = 30FD672CDC73AA675D664F1248BDD87F803810F53A4D67ADBCBF3E8F3604A2A7
> python -X utf8 mw.py doctor --project H:\git\Multi-Workers > <tmp>/doctor-after.txt    # sha256 = 30FD672CDC73AA675D664F1248BDD87F803810F53A4D67ADBCBF3E8F3604A2A7
text_identical_raw = True        (UTF-8 content sha256 68a2b985... both)
```

Second, heartbeat-free isolation of the delta (same code, scan patched to the pre-change `None` path):

```
scan_returns = None
gates_json_identical = True
gates_json_sha_without = 9a890349223fd882760eec8d4f0101f8a3007c2df8d6e7d767198f1842d29e50
gates_json_sha_with    = 9a890349223fd882760eec8d4f0101f8a3007c2df8d6e7d767198f1842d29e50
gates_text_alerted_without = False
gates_text_alerted_with    = False
```

### 2.3 wider blast-radius regression

```
> cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py test_doctor_autopilot.py test_serve_doctor.py test_autopilot_crosskey_prose.py test_autopilot_gates.py test_autopilot_conductor.py test_autopilot_done_contract_guard.py test_mw_autopilot_cli.py test_autopilot_contract_guard.py -q -p no:randomly
225 passed, 98 warnings in 58.70s
```

### 2.4 real end-to-end CLI + doctor on a tmp demo project

Setup (T-04 library writer; tmp dir, never the real project): freeze `AC-001/AC-002` + `VC-001`, then rewrite the `AC-001` cell, then (second phase) add an approved authorizing gate.

Unauthorized phase:

```
> python mw.py autopilot contract-guard --project <demo> --key demo-key --json
{"keys": [{"authorized": false, "carrier": null, "changed_ids": ["AC-001"], "freeze": true,
           "key": "demo-key", "reasons": ["contract-unauthorized"], "refused": true}],
 "ok": false, "refused": true, "unauthorized": 1}
exit=1
> python mw.py autopilot contract-guard --project <demo> --key demo-key
contract-guard: demo-key freeze=yes changed=AC-001 carrier=none ok=no refused
exit=1
```

Doctor on the same demo (exit 1; directory listing unchanged before/after => read-only):

```
contract_guard_present = True
contract_guard = {"keys": [{"authorized": false, "carrier": null, "changed_ids": ["AC-001"],
                  "freeze": ".agenticdoc/demo-key/evidence/contract-freeze.json", "key": "demo-key",
                  "reasons": ["contract-unauthorized"]}], "unauthorized": 1}
contract_guard_issues = ['contract-guard: key demo-key contract text changed without authorization
   (AC-001) since the freeze (.agenticdoc/demo-key/evidence/contract-freeze.json) - advance-to-done
   refused; answer a gate with authorizes: ["contract-change"] or revert the AC/VC text']
text: gates: 0 pending (0s oldest, 0 parse error(s), 0 drift, 1 contract-guard)
read_only=True
```

Authorized phase (approved `gate-0001` with `authorizes: ["contract-change"]`, same key):

```
> python mw.py autopilot contract-guard --project <demo> --json
{"keys": [{"authorized": true, "carrier": "gate-0001", "changed_ids": ["AC-001"], "freeze": true,
           "key": "demo-key", "reasons": ["authorized"], "refused": false}],
 "ok": true, "refused": false, "unauthorized": 0}
exit=0
contract_guard_issues = []      # doctor: no gates: text line (healthy)
```

## 3. Non-hollow contrasts (real red / green, restored byte-for-byte)

The write faces were restored after each counterfactual; final `sha256`:
`mw.py = B9985AC5A83C5AF5A8306F9F33EB28471711F3C2583A9072176D941C6E33F8AC`,
`mw_common.py = 1D507687B3989E97C7B796DE41FDD0449A736B0454A3A5A434F0DA6131C11D6E`.

### C1 - no-freeze project is byte-identical (the required zero-perturbation contrast)

Two sha256 for the same project with no freeze sidecar (the repo itself):
`09CF24F7...` (before) vs `0F255C0F...` (after, UTF-16 file bytes); after masking only the live worker's `age_s`/`last_heartbeat`, `f37e7e58...` on both sides, `gates_identical=True`, `contract_guard` absent in both. Text output byte-identical *unmasked* (`30FD672C...` both). See §2.2.

### C2 - strip the doctor `contract_guard` segment => red

Temporarily changed `mw_common.py:3081` to `if contract_section is not None and False:`:

```
> python -X utf8 -m pytest test_doctor_gates.py -q -p no:randomly -k "contract_guard"
FAILED test_doctor_gates.py::test_contract_guard_unauthorized_change_is_an_issue
FAILED test_doctor_gates.py::test_contract_guard_authorized_change_is_silent
FAILED test_doctor_gates.py::test_contract_guard_section_is_reproducible - Ke...
3 failed, 2 passed, 32 deselected
```

(The 2 passers are the "absent without freeze" and "zero-write" cases, which are correct without the segment.) Restored => green again (82 passed §2.1).

### C3 - strip the CLI dispatch => red

Temporarily changed `mw.py:3563` to `if args.autopilot_action == "contract-guard" and False:`:

```
> python -X utf8 -m pytest test_mw_autopilot_cli.py -q -p no:randomly -k "contract_guard"
FAILED test_mw_autopilot_cli.py::test_contract_guard_cli_no_freeze_is_readonly
FAILED test_mw_autopilot_cli.py::test_contract_guard_cli_refuses_unauthorized_change
FAILED test_mw_autopilot_cli.py::test_contract_guard_cli_authorizing_gate_clears_it
FAILED test_mw_autopilot_cli.py::test_contract_guard_cli_all_keys_and_reproducible
FAILED test_mw_autopilot_cli.py::test_contract_guard_cli_argparse_shape - Ass...
5 failed, 25 deselected
```

Restored => green again.

## 4. Contract compliance

- **Single judgement source**: the doctor scan and the CLI call `autopilot.contract_guard.evaluate` (T-04). No freeze parse / diff / approval logic is copied into `mw.py` or `mw_common.py` (grep: `mw_common.py`/`mw.py` contain no `parse_acs`/`parse_vcs`/`canonical_sha` and no `authorizes` membership test).
- **Read-only doctor path**: the scan only opens paths for reading; no `.tmp`, no lock, no directory creation. Asserted by `test_contract_guard_scan_is_zero_write` (snapshot identical) and by the tmp demo (`read_only=True`). No existing test's zero-write guarantee changed.
- **Zero perturbation (P-018)**: `contract_guard` is absent unless a usable freeze exists; `_gates_text_alerted` gains a condition that can only fire when the key is present; `format_doctor_text` appends only a non-zero suffix. Measured: text byte-identical, JSON identical after masking only the live worker heartbeat.
- **No `gates.create()` / `_REQUIRED_FIELDS` / 40-name change**: untouched (T-04's locks still green in §2.1/§2.3).
- **Write-face / process discipline**: only `mw.py`, `mw_common.py`, `test_mw_autopilot_cli.py`, `test_doctor_gates.py` were touched; `autopilot/conductor.py`, `autopilot/gates.py`, `autopilot/contract_guard.py`, `autopilot/dispatch.py` untouched. No commit, no `git add -A`/`git checkout .`/`git stash`/`git reset`/`git clean`; no coordination file touched; no test wrote the real project's `evidence/` (all fixtures under `tmp_path` / `%TEMP%`); no `npm run build`/`npm test`/full vitest.
- **`--json` stability**: `sort_keys=True`, key entries sorted by key, changed ids sorted by `evaluate`, project-relative posix freeze path, no timestamp - asserted reproducible across two runs (`test_contract_guard_cli_all_keys_and_reproducible`, `test_contract_guard_section_is_reproducible`).

## 5. Residual risks / handoff

1. **No production freeze writer exists (R1 - PM decision needed).** Design D-014/D-015 §4.5 lists `mw autopilot contract-freeze` and freezing at the `spec->design` / `design->plan` edges, but no card owns the writer: `contract_guard.freeze_contract` is called only from tests, and the conductor's advance path calls only `evaluate` (T-10). Until a writer lands, G3 is dormant (no freeze => `no_anchor` => no refusal), so every no-freeze zero-perturbation property holds trivially but AC-011 is also unfired in production. This card's deliverables did not include `contract-freeze` (card deliverable list item 1 is `contract-guard` only), so I did **not** add a fourth CLI surface unilaterally; the doctor issue text therefore points at the machine field + revert, not at a not-yet-existing command.
2. **Corrupt freeze sidecar** reads back as "no anchor" (`read_freeze` -> `None`, same as T-10): the doctor neither reports nor refuses it. A present-but-unusable anchor is therefore invisible on the doctor surface. Aligned with T-10/`evaluate`; flagging as a possible follow-up if a fail-closed "corrupt anchor" issue is wanted.
3. **Unreadable gate queue**: `_contract_guard_scan` skips the key (its parse error is already an issue in the gate section, and a corrupt file can never authorize). The CLI treats the same condition as fail-loud (exit 1).
4. `--key <missing>` returns `freeze=false`, `refused=false` (exit 0), mirroring `evaluate`'s no-anchor semantics; the JSON makes the state explicit.
5. Runtime was an older copy while this session ran (per the task's concurrency warning); every claim above is from output produced by this session's own runs.
