"""T07b RED evidence: revert one fix at a time and require the new tests to fail.

The pre-fix ``decision_history.py`` was never committed (both files are untracked
in this worktree), so it cannot be checked out for a true "before" run. Each
entry below is a *single-behaviour* revert of one fix inside a temporary copy of
the module (the T07 ``mutate_and_run.py`` isolation method: the working tree is
never modified, ``PYTHONPATH`` points at the real package for the dependencies).

A mutant that *passes* means the test does not lock the fixed behaviour. Every
run below is expected to exit non-zero, and the failure text in ``red-*.txt``
must be an assertion about the leaked/behaved data - not a collection error.

Usage: ``python red_mutants.py`` (from this directory or anywhere).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
PACKAGE = REPO / "packages" / "multi-workers"
SOURCE = PACKAGE / "decision_history.py"
TESTS = PACKAGE / "test_decision_history.py"

TESTS_P1_1 = [
    "test_free_text_is_redacted_across_every_carrier",
    "test_missing_redactor_withholds_free_text_instead_of_echoing",
    "test_unknown_carrier_fields_are_not_treated_as_schema",
    "test_long_free_text_is_clipped_with_honest_markers",
    "test_clip_boundary_never_keeps_a_partial_secret",
]
TESTS_P1_2 = [
    "test_record_key_is_validated_before_any_path_is_built",
    "test_out_of_root_signoff_symlink_is_refused_before_read",
    "test_out_of_root_gate_and_test_ledger_are_refused",
]

MUTANTS: dict[str, tuple[list[tuple[str, str]], list[str]]] = {
    # P1-1: pre-fix free-text policy - redact/clip/withhold replaced by raw echo.
    "p1-1-raw-free-text": (
        [
            (
                """        if not value:
            return ""
        if self.redactor is None:
            self._withhold(label)
            return None
        result = self.redactor.redact(value)""",
                """        if not value:
            return ""
        return value  # MUTANT: pre-fix free-text policy (raw echo)
        result = self.redactor.redact(value)""",
            ),
            (
                """        if self.redactor is None:
            self._withhold(label)
            return None
        if isinstance(value, str):
            return self.text(label, value)""",
                """        if self.redactor is None:  # MUTANT: pre-fix container echo
            return value
        if isinstance(value, str):
            return self.text(label, value)""",
            ),
        ],
        TESTS_P1_1,
    ),
    # P1-2: pre-fix key/path handling - record key built into a path, no root guard.
    "p1-2-key-as-path": (
        [
            (
                """    if not valid_key(key):
        blocked.append("key")
        return None, [f"signoff skipped: key {key!r} is not a directory name"]
    path = decide_signoff.signoff_path(control_root, key)
    if not _inside(root_real, path):
        blocked.append("signoff")
        return None, [
            f"signoff for key {key} refused before read: resolved path leaves the control root"
        ]""",
                """    path = decide_signoff.signoff_path(control_root, key)  # MUTANT: no key/root guard""",
            ),
            (
                """        if not valid_key(builder.key):
            stats["invalid_keys"] += 1""",
                """        if False:  # MUTANT: record keys are not validated
            stats["invalid_keys"] += 1""",
            ),
        ],
        TESTS_P1_2,
    ),
    # P2-1: pre-fix engine echo - source=model even when no answer was recorded.
    "p2-1-engine-echo-without-answer": (
        [
            (
                """    if base is not None and base.get("available") is True:""",
                """    if base is not None:  # MUTANT: engine echo without an answer""",
            ),
            (
                """    if folded_calls.last_call_end is not None and folded_calls.last_call_end.get("available") is True:""",
                """    if folded_calls.last_call_end is not None:  # MUTANT: same for call-end""",
            ),
        ],
        [
            "test_authority_human_is_not_proof_of_a_human_action",
            "test_ledger_call_without_answer_does_not_claim_a_model_source",
        ],
    ),
    # P2-2: pre-fix usage folding - counters merged across attempts, no semantics.
    "p2-2-usage-merge-without-semantics": (
        [
            (
                """                    # One attempt's counters, never merged with a sibling attempt:
                    # merging would attribute one number to a different request.
                    usage_counters = dict(attempt_usage)""",
                """                    for _counter, _value in attempt_usage.items():
                        usage_counters[_counter] = _value  # MUTANT: pre-fix merge""",
            ),
            (
                """    usage = UsageFact(
        recorded=usage_recorded,
        counters=counters,
        missing=missing if usage_recorded else (),
        complete=usage_recorded and not missing,
        semantics=_usage_semantics(usage_variants),
        attempts_with_usage=len(usage_variants),
        conflicting=len(set(usage_variants)) > 1,
        basis=_usage_basis(usage_variants),
    )""",
                """    usage = UsageFact(  # MUTANT: pre-fix counters, no semantics
        recorded=usage_recorded,
        counters=counters,
        missing=missing if usage_recorded else (),
        complete=usage_recorded and not missing,
    )""",
            ),
        ],
        ["test_record_usage_names_its_semantics_and_keeps_per_attempt_values"],
    ),
    # P2-3: pre-fix status - first settled event wins, stage keeps the last one.
    "p2-3-first-settled-status": (
        [
            (
                """    settled_event = _last_lifecycle(builder.events, "settled")
    if settled_event is not None:
        result = settled_event.get("result")
        return result if result in STATUSES else "unknown"
    return "unknown\"""",
                """    for event in builder.events:  # MUTANT: pre-fix first-match settled status
        if event.get("kind") == "lifecycle" and event.get("lifecycle") == "settled":
            result = event.get("result")
            return result if result in STATUSES else "unknown"
    return "unknown\"""",
            )
        ],
        ["test_repeated_settled_events_agree_with_the_stage"],
    ),
    # P2-4: pre-fix gate visibility - keyless gates dropped, no gate-only record.
    "p2-4-silent-gate-drop": (
        [
            (
                """        if gate.key is None:
            stats["gates_keyless"] += 1
            warn(
                "gate-keyless",
                f"gate {gate.id} has no key: attribution unknown, not folded into a key record",
            )
            continue""",
                """        if gate.key is None:  # MUTANT: pre-fix silent drop
            continue""",
            ),
            (
                """    for key in sorted(set(gates_by_key) - recorded_keys - signoff_keys):
        builder = builder_for("production", f"gate|{key}")
        builder.kind_hint = "gate"
        builder.key = key
        builder.gates = list(gates_by_key.get(key, ()))""",
                """    # MUTANT: pre-fix - a gate-only key has no record""",
            ),
        ],
        ["test_keyless_gate_is_counted_and_gate_only_key_stays_visible"],
    ),
    # P2-5a: an auto sign-off must stay a machine fact, never a human answer.
    "p2-5-auto-signoff-as-human": (
        [
            (
                """        if signed_via in ("cli", "tui"):
            human_basis.append(f"signoff:signed_via={signed_via} (declared)")""",
                """        if signed_via in ("cli", "tui", "auto-decide", "auto-llm"):  # MUTANT
            human_basis.append(f"signoff:signed_via={signed_via} (declared)")""",
            )
        ],
        ["test_auto_signoff_is_system_not_a_human_answer"],
    ),
    # P2-5b: a (dp,key) authority change must reach every decision of that key.
    "p2-5-no-dp-level-broadcast": (
        [
            (
                """    # Authority changes are dp-level: every decision of that (key, dp) sees them.
    for builder in builders.values():
        if builder.kind_hint == "authority" or builder.scope != "production":
            continue
        if builder.dp is None:
            continue
        rows = by_authority.get((builder.dp, builder.key or ""), ())
        if rows:
            builder.archive_authority = [dict(row) for row in rows]""",
                """    # MUTANT: pre-fix - no dp-level authority broadcast""",
            )
        ],
        ["test_dp_level_authority_change_reaches_every_decision_of_the_key"],
    ),
    # P2-5c: refresh / signoff:* authority writers are machines, not humans.
    "p2-5-refresh-actor-human": (
        [
            (
                """            actor="human" if is_human_identity(by) else "system",""",
                """            actor="human",  # MUTANT: every authority writer labelled human""",
            )
        ],
        ["test_refresh_authority_change_is_system"],
    ),
    # Isolation: the test must notice a write performed by the reader.
    "isolation-reader-writes": (
        [
            (
                """    root_real = _real_root(control_root)""",
                """    root_real = _real_root(control_root)
    (control_root / ".agenticdoc" / "_autopilot" / "history-probe.txt").write_text(
        "probe", encoding="utf-8"
    )  # MUTANT: the reader writes""",
            )
        ],
        ["test_history_read_never_writes_or_creates_paths"],
    ),
}


def run_mutant(name: str, edits: list[tuple[str, str]], tests: list[str]) -> int:
    workdir = HERE / f"mutant-{name}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()
    text = SOURCE.read_text(encoding="utf-8")
    for old, new in edits:
        if old not in text:
            print(f"[{name}] MUTATION TARGET NOT FOUND", flush=True)
            return 2
        text = text.replace(old, new, 1)
    (workdir / "decision_history.py").write_text(text, encoding="utf-8", newline="\n")
    shutil.copyfile(TESTS, workdir / "test_decision_history.py")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PACKAGE)
    nodes = [f"test_decision_history.py::{test}" for test in tests]
    log = HERE / f"red-{name}.txt"
    with log.open("wb") as handle:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", *nodes],
            cwd=workdir,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    body = log.read_text(encoding="utf-8", errors="replace")
    summary = [line for line in body.splitlines() if line.startswith(("FAILED", "ERROR"))]
    print(f"[{name}] exit={completed.returncode} (expected non-zero)", flush=True)
    for line in summary[:4]:
        print("  " + line, flush=True)
    return completed.returncode


def main() -> int:
    survived = 0
    for name, (edits, tests) in MUTANTS.items():
        code = run_mutant(name, edits, tests)
        if code == 0:
            survived += 1
            print(f"[{name}] SURVIVED: the test does not lock this behaviour", flush=True)
        elif code == 2:
            return 2
    print(f"mutants={len(MUTANTS)} survived={survived}", flush=True)
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
