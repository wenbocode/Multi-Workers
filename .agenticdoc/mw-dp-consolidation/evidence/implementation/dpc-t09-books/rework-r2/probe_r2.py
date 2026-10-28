"""R2 independent boundary probe (17 card fixtures + redaction/shape extras).

Usage: python -B probe_r2.py <label> [book-module-dir]

Network denied, imports bound to the isolated copy, writes only
rework-r2/probe-<label>.json. The 17 base fixtures mirror the PM handoff probe
inputs (legal book, six non-object stdin shapes, JSON-string-is-not-a-path,
bundle and bad-JSON controls, invalid-file report, four known-secret schema
refusals, bool and float schema versions) with this script's own code so the
before/after comparison is independent of the PM script and its outputs.

``book-module-dir`` loads ``decision_book`` from that directory first: the red
run points at the frozen pre-fix snapshot, so no product file is ever swapped.
"""
from __future__ import annotations

import copy
import json
import pathlib
import socket
import sys
import time
from unittest import mock

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"
assert pathlib.Path(PKG).resolve() == PKG

LABEL = sys.argv[1]
BOOK_DIR = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
OBSERVED_AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

PROJECT = HERE / "fixture" / "probe-project"
PROJECT.mkdir(parents=True, exist_ok=True)
(PROJECT / ".git").mkdir(exist_ok=True)
(PROJECT / "notes.txt").write_text("R2 independent source\n" * 4, encoding="utf-8")

sys.path.insert(0, str(PKG))
if BOOK_DIR is not None:
    sys.path.insert(0, str(BOOK_DIR))


def deny(*_args, **_kwargs):
    raise AssertionError("R2 probe forbids real network")


socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny

import decision  # noqa: E402
import decision_book as books  # noqa: E402
import decision_context  # noqa: E402
import decision_points as points  # noqa: E402

for module in (decision, points, decision_context):
    assert pathlib.Path(module.__file__).resolve().parent == PKG.resolve(), module.__file__
if BOOK_DIR is not None:
    assert pathlib.Path(books.__file__).resolve() == (BOOK_DIR / "decision_book.py").resolve(), books.__file__
else:
    assert pathlib.Path(books.__file__).resolve().parent == PKG.resolve(), books.__file__

KNOWN = "pm-known-opaque-business-secret"
REDACTOR = decision.known_secret_redactor(extra_secrets=[KNOWN])
MATERIAL = {
    "task_goal": "Validate book stdin refusals with full layered requests",
    "task_requirements": (
        "Illegal JSON shapes produce issues, never filesystem lookup or escaped exception"
    ),
    "task_deliverables": "Book gate boundary red-green evidence",
    "images_required": False,
}
PREPARATION = {
    "basis_catalog": [
        {
            "id": "pm-checked",
            "text": "Input shape and complete material are the cited business facts",
            "material_refs": ["task_goal"],
            "applies_to": list(points.resolve_entry_choices("dp-w-type", MATERIAL)),
        }
    ],
    "prepared_at": "2026-10-27T09:10:00+00:00",
}
BOOK = {
    "schema_version": 3,
    "decision_point": "dp-w-type",
    "material": MATERIAL,
    "preparation": PREPARATION,
    "notes": {
        "evidence": {
            path: "notes.txt:1" for path in points.REQUIRED_STATE_FIELDS["dp-w-type"]
        }
    },
}
KWARGS = {"project_dir": PROJECT, "repo_root": PROJECT}
rows: list[dict] = []


def record(label: str, fn, predicate) -> None:
    try:
        result = fn()
        rows.append({"label": label, "passed": bool(predicate(result)), "result": repr(result)})
    except Exception as exc:  # noqa: BLE001 - a probe records the real failure
        rows.append(
            {"label": label, "passed": False, "exception": type(exc).__name__, "detail": str(exc)}
        )


def no_file_authority(*_args, **_kwargs):
    raise AssertionError("a non-object stdin payload must never load a file")


def stdin_issue(value: object):
    return lambda: books.prepare_stdin_request(json.dumps(value), **KWARGS)


def refuses_with_schema_issue(pair) -> bool:
    prepared, issues = pair
    return (
        prepared is None
        and bool(issues)
        and issues[0].code == "book-schema"
        and "one book object" in issues[0].detail
    )


# --- group 1: stdin accepts exactly one book object -----------------------
record(
    "legal-full-book-positive",
    lambda: books.prepare_stdin_request(json.dumps(BOOK), **KWARGS),
    lambda pair: pair[0] is not None and pair[1] == (),
)
for value in (None, [], [BOOK], True, 17, 3.14):
    record(
        "stdin-shape-" + ("empty-array" if value == [] else "array-with-book" if value == [BOOK] else type(value).__name__),
        stdin_issue(value),
        refuses_with_schema_issue,
    )


def string_is_not_a_path():
    path = PROJECT / "book.json"
    path.write_text(json.dumps(BOOK), encoding="utf-8")
    with mock.patch.object(books, "load_book", side_effect=no_file_authority), mock.patch.object(
        books, "_read_json", side_effect=no_file_authority
    ), mock.patch.object(books, "book_sha256", side_effect=no_file_authority):
        return books.prepare_stdin_request(json.dumps(str(path)), **KWARGS)


record(
    "stdin-string-is-not-file-authority",
    string_is_not_a_path,
    lambda pair: pair[0] is None and bool(pair[1]) and pair[1][0].code == "book-schema",
)
record(
    "stdin-bundle-refusal-control",
    lambda: books.prepare_stdin_request(json.dumps({"books": {"one": BOOK}}), **KWARGS),
    lambda pair: pair[0] is None and bool(pair[1]) and pair[1][0].code == "book-schema",
)
record(
    "stdin-bad-json-refusal-control",
    lambda: books.prepare_stdin_request("{broken", **KWARGS),
    lambda pair: pair[0] is None and bool(pair[1]) and pair[1][0].code == "book-schema",
)

# --- group 2: an invalid file still reports a complete, serializable result
legacy = PROJECT / "legacy.json"
legacy.write_text(
    json.dumps({"schema_version": 2, "decision_point": "dp-w-type", "state": MATERIAL}),
    encoding="utf-8",
)


def invalid_file_report():
    return books.check_book_file(legacy, **KWARGS).as_dict()


record(
    "invalid-file-report-as-dict-safe",
    invalid_file_report,
    lambda data: data["ok"] is False and bool(data["issues"]) and data["books"][0]["ok"] is False,
)

# --- group 3: a schema refusal never echoes a known secret ----------------
for layer in ("unknown-top-key", "unknown-notes-key", "bad-version", "unknown-dp"):
    changed = copy.deepcopy(BOOK)
    if layer == "unknown-top-key":
        changed[KNOWN] = "x"
    elif layer == "unknown-notes-key":
        changed["notes"][KNOWN] = "x"
    elif layer == "bad-version":
        changed["schema_version"] = KNOWN
    else:
        changed["decision_point"] = KNOWN
    record(
        "schema-secret-refusal-" + layer,
        lambda book=changed: books.check_book(book, redactor=REDACTOR, **KWARGS),
        lambda issues: bool(issues) and all(KNOWN not in issue.format() for issue in issues),
    )

# --- group 4: schema_version is a real non-bool integer 3 -----------------
for value in (True, 3.0):
    changed = copy.deepcopy(BOOK)
    changed["schema_version"] = value
    record(
        "schema-type-" + type(value).__name__,
        lambda book=changed: books.check_book(book, **KWARGS),
        lambda issues: bool(issues) and issues[0].path == "schema_version",
    )


# --- extras: nested schema shapes, detail specificity, bundle independence
def nested_secret_shapes():
    results = []
    for layer in ("notes-not-object", "material-not-object", "meta-not-object", "context-not-object"):
        changed = copy.deepcopy(BOOK)
        if layer == "notes-not-object":
            changed["notes"] = [KNOWN]
        elif layer == "material-not-object":
            changed["material"] = [KNOWN]
        elif layer == "meta-not-object":
            changed["meta"] = [KNOWN]
        else:
            changed["context"] = [KNOWN]
        issues = books.check_book(changed, redactor=REDACTOR, **KWARGS)
        results.append(
            {
                "layer": layer,
                "codes": sorted({issue.code for issue in issues}),
                "echoes_secret": any(KNOWN in issue.format() for issue in issues),
                "first_path": issues[0].path if issues else None,
            }
        )
    return results


record(
    "extra-nested-schema-shapes-no-echo",
    nested_secret_shapes,
    lambda results: all(row["echoes_secret"] is False and row["codes"] for row in results),
)


def non_secret_unknown_dp_detail():
    changed = copy.deepcopy(BOOK)
    changed["decision_point"] = "dp-not-a-real-entry"
    return [issue.format() for issue in books.check_book(changed, **KWARGS)]


record(
    "extra-unknown-dp-still-specific",
    non_secret_unknown_dp_detail,
    lambda lines: bool(lines) and any("dp-not-a-real-entry" in line for line in lines),
)


def mixed_bundle_flags():
    good = copy.deepcopy(BOOK)
    bad = copy.deepcopy(BOOK)
    del bad["material"]["task_goal"]
    path = PROJECT / "bundle.json"
    path.write_text(json.dumps({"books": {"sign": good, "bad": bad}}), encoding="utf-8")
    data = books.check_book_file(path, **KWARGS).as_dict()
    flags = {entry["label"]: entry["ok"] for entry in data["books"]}
    return {"ok": data["ok"], "flags": flags}


record(
    "extra-mixed-bundle-independent",
    mixed_bundle_flags,
    lambda data: data["ok"] is False and data["flags"] == {"sign": True, "bad": False},
)


def strict_version_controls():
    accepted = []
    for value in (3, 3.0, "3", True):
        changed = copy.deepcopy(BOOK)
        changed["schema_version"] = value
        issues = books.check_book(changed, **KWARGS)
        accepted.append({"value": repr(value), "refused": bool(issues)})
    return accepted


record(
    "extra-version-controls",
    strict_version_controls,
    lambda rows_: [row["refused"] for row in rows_] == [False, True, True, True],
)

result = {
    "source": "agent-report",
    "label": LABEL,
    "observed_at": OBSERVED_AT,
    "book_module": str(pathlib.Path(books.__file__).resolve()),
    "product_write_performed": False,
    "network": "denied",
    "fixtures": rows,
    "passed": sum(row["passed"] for row in rows),
    "failed": sum(not row["passed"] for row in rows),
    "base_17_passed": sum(row["passed"] for row in rows[:17]),
    "base_17_failed": sum(not row["passed"] for row in rows[:17]),
}
(HERE / f"probe-{LABEL}.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps({key: result[key] for key in ("label", "passed", "failed", "base_17_passed", "base_17_failed", "network")}, indent=2))
for row in rows:
    status = "PASS" if row["passed"] else "FAIL"
    detail = row.get("detail") or row.get("result") or ""
    print(f"{status} {row['label']}: {detail[:220]}")
raise SystemExit(0 if result["failed"] == 0 else 1)
