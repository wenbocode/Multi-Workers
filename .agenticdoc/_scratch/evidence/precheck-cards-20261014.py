"""Pre-dispatch self-check (P-033 rules 2 + 2b): the launcher's spawn-stage
envelope gate must see all sections and type extras, and the card must carry the
seed minimum (a literal `goal.md` reference + at least one literal
`name.ext:NNN`)."""

import pathlib
import re
import sys

PKG = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers")
sys.path.insert(0, str(PKG))

from launcher import inspect_envelope, type_extras_missing  # noqa: E402

SEED_GOAL = re.compile(r"goal\.md")
SEED_LOC = re.compile(r"[\w./@-]+\.[A-Za-z][\w]*:\d+")

CARDS = [
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I06-operator-py-defer.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I07-render-comma-safe.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I08-pm-gate-render.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I09-queue-single-writer.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I10-runtime-guard.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I11-carrier-convergence.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I12-e2e-parity.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I13-pm-refusal-audit.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I14-reject-reason-parity.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\tasks\T-W-I15-doctor-refusal-surface.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\tasks\T-C-M02-conductor-frontier.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\tasks\T-C-M03-config-panel.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\tasks\T-C-M04-dispatch-identity-dedup.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\tasks\T-C-M05-tests-python.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\tasks\T-C-M05-tests-ts.md",
    r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\tasks\T-C-M06-e2e-concurrency.md",
]

failures = 0
for card in CARDS:
    text = pathlib.Path(card).read_text(encoding="utf-8")
    ok, missing, type_value, detail = inspect_envelope(text)
    extras = type_extras_missing(type_value, text)
    goals = SEED_GOAL.findall(text)
    locs = SEED_LOC.findall(text)
    print(f"--- {pathlib.Path(card).name}")
    print(f"    envelope ok={ok} missing={missing} type={type_value!r}")
    print(f"    type_extras_missing={extras}")
    print(f"    seed goal.md x{len(goals)}  name.ext:NNN x{len(locs)}  first={locs[:3]}")
    if not ok or missing or extras or not goals or not locs:
        failures += 1
        print("    RESULT: REFUSED")
    else:
        print("    RESULT: ok")
print("failures:", failures)
raise SystemExit(1 if failures else 0)
