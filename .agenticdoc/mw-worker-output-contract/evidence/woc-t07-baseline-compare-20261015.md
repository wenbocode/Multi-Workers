T-07 baseline comparison (24-file set, per-test-name diff) — 2026-10-15

Commands (re-runnable):
  cd H:/git/Multi-Workers/packages/coding-agent
  node ../../node_modules/vitest/dist/cli.js --run --reporter=json \
    --outputFile=../../.agenticdoc/mw-worker-output-contract/evidence/woc-t07-after-vitest.json \
    test/suite/output-recovery-contract.test.ts test/suite/dispatch-recovery-terminal.test.ts \
    test/suite/change-ledger.test.ts test/suite/mwds-t02-write-intent.test.ts \
    test/suite/mwds-t03-bash-write-scope.test.ts test/suite/mwds-t04-deliverable.test.ts \
    test/suite/mwds-t05-output-sections.test.ts test/suite/mwds-t06-output-informativeness.test.ts \
    test/suite/mwds-t12-regression.test.ts test/suite/mwds-t21-write-intent-soundness.test.ts \
    test/suite/mwds-t23-cutover-recheck.test.ts test/suite/mwds-t25-version-and-dotless.test.ts \
    test/suite/mwds-t26-closeout-verify.test.ts test/suite/mwgal-t17-ledger-role-aware.test.ts \
    test/suite/mwgal-t17b-ledger-infra-writes.test.ts test/suite/mwgal-t17c-ledger-unresolvable.test.ts \
    test/suite/mwgal-t21-qg-fixes.test.ts test/suite/rag-research-doc.test.ts \
    test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-worker-file-tool.test.ts \
    test/extensions/agent-team-loop-checkpoint-wiring.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts \
    test/suite/autopilot-protocol.test.ts test/suite/mwgal-t10-state-surface.test.ts
  python ../../.agenticdoc/mw-worker-output-contract/workers/woc-dr6-verification-matrix/diff-vitest.py \
    ../../.agenticdoc/mw-worker-output-contract/workers/woc-dr6-verification-matrix/baseline-vitest.json \
    ../../.agenticdoc/mw-worker-output-contract/evidence/woc-t07-after-vitest.json

Baseline: .agenticdoc/mw-worker-output-contract/workers/woc-dr6-verification-matrix/baseline-vitest.json
  (DR6 snapshot: 24 files / 558 tests / 5 pre-existing reds, taken 2026-10-14 before batch A/B landed)
After:   .agenticdoc/mw-worker-output-contract/evidence/woc-t07-after-vitest.json (this run, 2026-10-15)

Result (raw diff in woc-t07-baseline-diff-20261015.txt):
  baseline tests = 558, after tests = 558
  NEW FAILURES (this change) = 0
  STILL FAILING (pre-existing) = 5
  FIXED = 0
  MISSING FROM AFTER = 7

HEAD 5 reds (pre-existing, NOT introduced by this change — R8 hard split):
  1. test/extensions/agent-team-loop-worker-file-tool.test.ts:177
     "writeWorkerFile (VC-005) VC-005: appends progress.md after a sentinel and writes report files; bytes match UTF-8 length"
     -> directory snapshot includes the new trace.log (write-event side effect)
  2. test/extensions/agent-team-loop-worker-file-tool.test.ts:285
     "size and slug limits enforces the slug length boundary (41 allowed, 42 rejected)"
     -> same snapshot-trace.log mismatch
  3. test/extensions/agent-team-loop.test.ts:6381
     "T-17/B-1 anchor integrity (VC-MWGF-038 / AC-011) every spec.md / design.md `file:line` reference is anchored to the current tree"
     -> another key's stale file:line references (mw-guard-form-hardening design.md worker/worker-mode.ts:747 x2)
  4. test/suite/mwds-t02-write-intent.test.ts:345
     "AC-005a corpus replay (VC-015) the writeless-without-shell corpus yields 0 false positives"
     -> falsePositives = [wjg-qg-evidence-closure] (live corpus member declared evidence write)
  5. test/suite/mwds-t23-cutover-recheck.test.ts:295
     "T-23 requirement 4 — same-source bundle sha expectation"
     -> expected bundle sha 975D4066... != rebuilt digest 9544D8A4... (bundle rebuilt by other sessions)

NEW REDS = 0 declaration:
  The per-test-name diff shows ZERO tests that passed in the DR6 baseline and
  fail in the after run. The only failures are the 5 pre-existing HEAD reds
  listed above (they failed at DR6 and still fail, unchanged).

The 7 MISSING tests are EXPECTED renames (not deletions, not new reds):
  - dispatch-recovery-terminal.test.ts "AC-003 terminal flip (T-07 requirement 1) ..."
    -> renamed by T-13 to "T-13/D-015: a delivered reply missing a substantive section
       gets one self-check round, then settles" (two-settle flow, R8 expected change)
  - mwds-t03-bash-write-scope.test.ts "AC-005b zero impact on write roles (VC-024) VC-024: coding/repair/vision
    registers no write-scope guard ..." x3 -> renamed by batch A/B to "VC-024: coding/repair/vision
    registers the write-scope guard; declared-face writes pass and off-face writes block" (behavior
    flipped by the write-scope guard landing, R8 expected change)
  - mwds-t03 "AC-007 write-scope audit line + summary (VC-029/VC-030) the summary is written once at
    recordEnd and only for the writeless guard role" -> split/renamed into the current
    VC-029/VC-030 + "the summary is written once at recordEnd for every guarded role" (D-115 rule 7)
  - mwgal-t21 "T-21 contract locks no config key was added (AC-011): the default set stays at 20"
    -> renamed to "one config key was added by MDC M-03: the default set moves to 21" (expected
    MDC M-03 change, R8 expected change)
  - output-recovery-contract.test.ts "recovery contract at settle (AC-003) missing section =>
    needs-clarification and the read-back names it" -> renamed by T-13 to "missing section =>
    one self-check round, then the terminal needs-clarification names it verbatim" (two-settle flow)

All 7 MISSING correspond to test names that exist in the after run under their
new names (verified in woc-t07-after-vitest.json), and all pass.

Conclusion: NEW REDS = 0. The 5 HEAD reds are the only failures and are
pre-existing (R8 hard split respected). No stop-and-report condition triggered.

Per-file green/red table (raw, from woc-t07-after-vitest.json):
  test/extensions/agent-team-loop-checkpoint-wiring.test.ts  PASS (10)
  test/extensions/agent-team-loop-watch-aggregate.test.ts    PASS (7)
  test/extensions/agent-team-loop-worker-file-tool.test.ts   FAIL 2 (9)   <- HEAD reds 1+2
  test/extensions/agent-team-loop.test.ts                    FAIL 1 (197) <- HEAD red 3
  test/suite/autopilot-protocol.test.ts                      PASS (10)
  test/suite/change-ledger.test.ts                           PASS (12)
  test/suite/dispatch-recovery-terminal.test.ts              PASS (16)
  test/suite/mwds-t02-write-intent.test.ts                   FAIL 1 (39) <- HEAD red 4
  test/suite/mwds-t03-bash-write-scope.test.ts               PASS (63)
  test/suite/mwds-t04-deliverable.test.ts                    PASS (19)
  test/suite/mwds-t05-output-sections.test.ts                 PASS (11)
  test/suite/mwds-t06-output-informativeness.test.ts          PASS (9)
  test/suite/mwds-t12-regression.test.ts                      PASS (11)
  test/suite/mwds-t21-write-intent-soundness.test.ts          PASS (13)
  test/suite/mwds-t23-cutover-recheck.test.ts                 FAIL 1 (10) <- HEAD red 5
  test/suite/mwds-t25-version-and-dotless.test.ts             PASS (13)
  test/suite/mwds-t26-closeout-verify.test.ts                 PASS (5)
  test/suite/mwgal-t10-state-surface.test.ts                  PASS (16)
  test/suite/mwgal-t17-ledger-role-aware.test.ts              PASS (15)
  test/suite/mwgal-t17b-ledger-infra-writes.test.ts           PASS (16)
  test/suite/mwgal-t17c-ledger-unresolvable.test.ts           PASS (15)
  test/suite/mwgal-t21-qg-fixes.test.ts                       PASS (19)
  test/suite/output-recovery-contract.test.ts                 PASS (14)
  test/suite/rag-research-doc.test.ts                         PASS (9)

AC-017(d) "12 existing cases no regression": the 12 ledger-family files locked
by T-02 (change-ledger 12, checkpoint-wiring 10, dispatch-recovery-terminal 16,
mwds-t03 63, mwgal-t17 15, t17b 16, t17c 15, mwds-t21 13, mwds-t25 13,
mwds-t26 5, mwgal-t21 19, agent-team-loop 196) are ALL in the 24-file set above
and all PASS in the after run (the agent-team-loop 1 fail is the HEAD red 3,
pre-existing). Per-test-name diff confirms zero same-name flips.

