"""Independent product gates (mirrors the PM probe without touching it).

Checks the regenerated eight cases and the rewritten template against the real
production gates: generator byte parity with this attempt's private output,
``check_book`` with the implementation copy as repository root, one prepared
basis per supported choice, the schema gate + scaffold equality for the
template, and the recorded non-future ``prepared_at``. Writes
``product-check.json``.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import pathlib
import socket
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent
KEY = EVIDENCE.parents[3]
WT = KEY / "implementation-worktree"
PKG = WT / "packages" / "multi-workers"
PRIVATE = EVIDENCE / "fixture" / "generator-out"
GEN = PKG / "scripts" / "build_decide_cases.py"


def deny(*_args, **_kwargs):
    raise AssertionError("no real network permitted in this isolated product check")


socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny

sys.path.insert(0, str(PKG))

import decision_book  # noqa: E402
import decision_points  # noqa: E402

assert pathlib.Path(decision_book.__file__).resolve().parent == PKG
assert pathlib.Path(decision_points.__file__).resolve().parent == PKG

ACTIVE = (
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route",
)
LEGACY_SHA = {
    "dp1.json": "3131c02f4830b96994e3bea94efe1be8511fd7936f8c983cf579596218a6c9ff",
    "dp2.json": "a03e1a29540ba9636a0a37bf478598bb530c357fc65d54b5eaaf6326e16342ea",
    "dp3.json": "82ff47e50ab5f24cfd84c793c07e2d15484ea89c24a90c8595306c468f407f2d",
    "dp25.json": "bda25144a8c5cd73978603a3dc4c9b429d8d451485679d99ef46cfcc4c2cc7fd",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_generator():
    spec = importlib.util.spec_from_file_location("r2_envelope_generator", GEN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_generator()
    assert set(module.CASE_IDS) == set(ACTIVE)
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    failures: list[str] = []
    for dp in ACTIVE:
        name = module.CASE_IDS[dp]
        shipped_bytes = (PKG / "decide_cases" / name).read_bytes()
        private_bytes = (PRIVATE / name).read_bytes()
        case = json.loads(shipped_bytes.decode("utf-8"))
        book = case["book"]
        issues = decision_book.check_book(book, project_dir=EVIDENCE / "fixture" / "project", repo_root=WT)
        supported = [
            choice
            for choice in decision_points.resolve_entry_choices(dp, book["material"])
            if not decision_points.entry_choice_issues(dp, choice, book["material"])
        ]
        basis_rows = []
        for choice in supported:
            matches = [
                item for item in book["preparation"]["basis_catalog"] if choice in item["applies_to"]
            ]
            if not matches:
                failures.append(f"{dp}:{choice} has no prepared basis")
            for item in matches:
                prepared_issues = decision_points.prepared_request_issues(
                    dp,
                    book["material"],
                    book["preparation"],
                    choice=choice,
                    basis_id=item["id"],
                    actor_role=book["meta"]["actor_role"],
                )
                basis_rows.append({"choice": choice, "basis_id": item["id"], "issues": len(prepared_issues)})
                if prepared_issues:
                    failures.append(f"{dp}:{choice}:{item['id']} {prepared_issues}")
        prepared = datetime.datetime.fromisoformat(book["preparation"]["prepared_at"])
        row = {
            "dp": dp,
            "file": f".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/{name}",
            "bytes": len(shipped_bytes),
            "sha256": sha(shipped_bytes),
            "private_out_byte_identical": shipped_bytes == private_bytes,
            "equals_generator_build_case": case == json.loads(json.dumps(module.build_case(dp), ensure_ascii=False)),
            "offline_check_book_issues": len(issues),
            "issue_detail": [issue.format() for issue in issues],
            "supported_choices": supported,
            "basis_checks": basis_rows,
            "prepared_at": book["preparation"]["prepared_at"],
            "prepared_at_future": prepared > now,
            "prepared_at_zone": str(prepared.tzinfo),
        }
        if issues:
            failures.append(f"{dp}: check_book issues {[i.format() for i in issues]}")
        if shipped_bytes != private_bytes:
            failures.append(f"{dp}: shipped bytes differ from the private generator output")
        if prepared > now:
            failures.append(f"{dp}: prepared_at is in the future")
        rows.append(row)

    template_path = PKG / "decide_book_template.json"
    template_text = template_path.read_text(encoding="utf-8")
    template = json.loads(template_text)
    template_failures = []
    if set(template) != {"books"}:
        template_failures.append("top level is not exactly {'books'}")
    books = template.get("books", {})
    if set(books) != set(ACTIVE):
        template_failures.append(f"books are {sorted(books)}, expected the eight active entries")
    for dp, book in books.items():
        if book != decision_book.scaffold_book(dp):
            template_failures.append(f"{dp}: book is not decision_book.scaffold_book(dp)")
        if decision_book._schema_issues(book):
            template_failures.append(f"{dp}: schema issues {[i.format() for i in decision_book._schema_issues(book)]}")
        if "meta" in book:
            template_failures.append(f"{dp}: template invents meta")
        if book.get("schema_version") != 3:
            template_failures.append(f"{dp}: schema_version != 3")
        if not decision_book.check_book(book, repo_root=WT):
            template_failures.append(f"{dp}: the blank skeleton passed the send gate")
    if template_text != module.render_template(module.build_template()):
        template_failures.append("shipped template bytes != render_template(build_template())")

    legacy = {
        name: {"sha256": sha((PKG / "decide_cases" / name).read_bytes()), "expected": expected}
        for name, expected in LEGACY_SHA.items()
    }
    payload = {
        "source": "agent-report",
        "observed_at": now.isoformat(),
        "repo_root": WT.as_posix(),
        "private_out": PRIVATE.as_posix(),
        "cases": rows,
        "template": {
            "file": ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_book_template.json",
            "bytes": len(template_text.encode("utf-8")),
            "sha256": sha(template_text.encode("utf-8")),
            "books": sorted(books),
            "schema_version": sorted({book.get("schema_version") for book in books.values()}),
            "failures": template_failures,
            "is_skeleton": {dp: bool(decision_book.check_book(book, repo_root=WT)) for dp, book in books.items()},
        },
        "legacy_cases": legacy,
        "legacy_cases_unchanged": all(item["sha256"] == item["expected"] for item in legacy.values()),
        "failures": failures + template_failures,
        "ok": not failures and not template_failures and all(
            item["sha256"] == item["expected"] for item in legacy.values()
        ),
    }
    (EVIDENCE / "product-check.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "ok": payload["ok"],
                "cases": len(rows),
                "offline_check_book_zero_issues": all(r["offline_check_book_issues"] == 0 for r in rows),
                "private_out_byte_identical": all(r["private_out_byte_identical"] for r in rows),
                "prepared_at_future_cases": [r["dp"] for r in rows if r["prepared_at_future"]],
                "template_failures": template_failures,
                "legacy_cases_unchanged": payload["legacy_cases_unchanged"],
                "failures": payload["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
