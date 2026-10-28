"""
test_task_type_parity.py — T-08 (AC-005 / VC-040, VC-042): Python <-> TS
task.md header parity.

`mw_common.read_task_type` is the Python half of the AC-005 single-source role
judgement (the TS half is `shared/task-frontmatter.ts`). The two sides cannot
physically share code (one is Python, one is TypeScript), so this module makes
"same semantics" a measured fact instead of a comment:

  * the golden fixture `packages/coding-agent/test/fixtures/task-md-header-cases.json`
    (18 base64-inlined cases: BOM, fence, unclosed fence, no-blank-line
    truncation, body `type:`, illegal/near-miss values, CRLF/LF) is read by the
    real `mw_common` implementation and by the real TS module through
    `node --experimental-strip-types`, then diffed field for field;
  * every `.agenticdoc/**/task.md` is read by both sides and compared per file
    (`py_md5 == ts_md5`), with the 7 named historical BOM books asserted to
    yield a `type:` again.

Fail-closed (P-016, copied from test_autopilot_config_parity.py): a missing
`node` executable is a hard failure, never a skip — a skipped case is a hollow
measurement.

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_task_type_parity.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_HERE))

import mw_common  # noqa: E402

FIXTURE_FILE = _REPO / "packages" / "coding-agent" / "test" / "fixtures" / "task-md-header-cases.json"
TS_MODULE = (
    _REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "task-frontmatter.ts"
)
CORPUS_ROOT = _REPO / ".agenticdoc"

# The 7 historical books whose UTF-8 BOM hid the header from the old `^type:`
# regex (design.md 4.6 C-3 / design-role-key-identity 0.2 E-1). Paths are
# relative to CORPUS_ROOT with forward slashes.
BOM_BOOKS = (
    "_scratch/workers/mw-dr-autodispatch/task.md",
    "mw-dispatch-reliability/workers/mw-dr-glm53/task.md",
    "mw-dispatch-reliability/workers/mw-dr-keyed-probe/task.md",
    "mw-dispatch-reliability/workers/mw-dr-live-claude/task.md",
    "mw-dispatch-reliability/workers/mw-dr-live-ok/task.md",
    "mw-dispatch-reliability/workers/mw-dr-pi-timi-test/task.md",
    "mw-dispatch-flow-fixes/workers/smoke-ac015-ac016/task.md",
)

_TS_SCRIPT = r"""
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

// Runtime power-tool view used only by the escalation predicate. Mirrors the
// table in the TS suite (test/suite/task-frontmatter.test.ts) and worker-mode's
// TOOL_ALLOWLISTS power subset; an unregistered type resolves to `fallback`.
const POWER_TOOLS = {
	coding: ["read", "write", "edit", "bash"],
	review: ["read", "ls", "find", "grep"],
	research: ["read", "ls", "find", "grep", "bash"],
	vision: ["read"],
	verifier: ["read"],
	fallback: ["read", "write", "edit", "bash"],
};
const toolsFor = (type) => POWER_TOOLS[type] ?? POWER_TOOLS.fallback;

function readingOf(mod, text) {
	const reading = mod.readTaskType(text);
	const region = mod.extractTaskHeader(text);
	const bodyLines = mod.scanBodyTypeLines(text);
	const headerType = reading.type === undefined ? "" : reading.type;
	const escalation = mod.findTypeEscalation(bodyLines, headerType, toolsFor);
	return {
		type: reading.type === undefined ? null : reading.type,
		source: reading.source,
		bom_stripped: reading.bomStripped,
		fenced: region.fenced,
		truncated: region.truncated,
		body_type_lines: bodyLines.map((line) => [line.line, line.value]),
		escalates: escalation !== undefined,
	};
}

(async () => {
	const mod = await import(pathToFileURL(process.env.MW_TS_MODULE).href);
	const fixture = JSON.parse(fs.readFileSync(process.env.MW_TS_FIXTURE, "utf8"));
	const cases = {};
	for (const testCase of fixture.cases) {
		const text = Buffer.from(testCase.content_b64, "base64").toString("utf8");
		cases[testCase.id] = readingOf(mod, text);
	}
	// T-19/C-15+C-16: the newline index-space cases travel as base64 so the
	// bytes reach both parsers untouched.
	const extra = JSON.parse(process.env.MW_TS_EXTRA_CASES || "[]");
	for (const testCase of extra) {
		cases[testCase.id] = readingOf(mod, Buffer.from(testCase.content_b64, "base64").toString("utf8"));
	}
	// The file list is discovered once on the Python side and handed over, so
	// both parsers run on exactly the same instant-in-time corpus (a concurrent
	// worker writing a task.md cannot desync the two walks).
	const root = process.env.MW_TS_CORPUS_ROOT;
	const rels = JSON.parse(process.env.MW_TS_CORPUS_FILES);
	const corpus = {};
	for (const rel of rels) {
		corpus[rel] = readingOf(mod, fs.readFileSync(path.join(root, rel), "utf8"));
	}
	process.stdout.write("TS_JSON_BEGIN\n");
	process.stdout.write(JSON.stringify({ cases, corpus }) + "\n");
	process.stdout.write("TS_JSON_END\n");
})().catch((error) => {
	console.error(error && error.stack ? error.stack : String(error));
	process.exit(1);
});
"""


# ── T-19/C-15+C-16: newline index-space normalization ──────────────────────
#
# F-A4-1 (lone/embedded CR) and F-A4-2 (U+2028) were cross-language divergences:
# the header boundary was judged in different line spaces on the two sides. Both
# extractors now fold `\r\n`, `\r`, U+2028 and U+2029 to `\n` before indexing,
# so the same bytes yield the same header. Three classes, each with 1 positive
# and 1 "must not misjudge" negative; `expected` is the folded reading.
EOL_CASES: list[dict] = [
    {
        "id": "eol-cr-lone-fenced",
        "group": "cr",
        "text": "---\rtype: verifier\rloop: l2\r---\r",
        "expected": {
            "type": "verifier", "source": "header", "bom_stripped": False,
            "fenced": True, "truncated": False, "body_type_lines": [],
        },
    },
    {
        "id": "eol-cr-body-negative",
        "group": "cr",
        "text": "type: coding\n\nbody\rphase: SPEC\n",
        "expected": {
            "type": "coding", "source": "header", "bom_stripped": False,
            "fenced": False, "truncated": False, "body_type_lines": [],
        },
    },
    {
        "id": "eol-crlf-mixed-fenced",
        "group": "crlf",
        "text": "---\r\ntype: review\r\n---\r\n\r\ntype: coding\r\n",
        "expected": {
            "type": "review", "source": "header", "bom_stripped": False,
            "fenced": True, "truncated": False, "body_type_lines": [[5, "coding"]],
        },
    },
    {
        "id": "eol-crlf-body-negative",
        "group": "crlf",
        "text": "type: coding\r\n\r\nphase: SPEC\r\n",
        "expected": {
            "type": "coding", "source": "header", "bom_stripped": False,
            "fenced": False, "truncated": False, "body_type_lines": [],
        },
    },
    {
        "id": "eol-u2028-fenced",
        "group": "u2028",
        "text": "---\u2028type: verifier\u2028---\u2028",
        "expected": {
            "type": "verifier", "source": "header", "bom_stripped": False,
            "fenced": True, "truncated": False, "body_type_lines": [],
        },
    },
    {
        "id": "eol-u2028-body-negative",
        "group": "u2028",
        "text": "type: coding\nloop: l1\n\nwork\u2028with\u2028separators\n",
        "expected": {
            "type": "coding", "source": "header", "bom_stripped": False,
            "fenced": False, "truncated": False, "body_type_lines": [],
        },
    },
]


def _fixture() -> dict:
    return json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))


def _decode(case: dict) -> str:
    return base64.b64decode(case["content_b64"]).decode("utf-8")


def _py_reading(text: str) -> dict:
    reading = mw_common.read_task_type(text)
    _lines, region = mw_common.read_task_header_region(text)
    return {
        "type": reading.type,
        "source": reading.source,
        "bom_stripped": reading.bom_stripped,
        "fenced": region.fenced,
        "truncated": region.truncated,
        "body_type_lines": [[line, value] for line, value in mw_common.scan_body_type_lines(text)],
    }


def _canonical(reading: dict) -> str:
    body = ",".join(f"{line}:{value}" for line, value in reading["body_type_lines"])
    return (
        f"type={reading['type']}|source={reading['source']}|bom={reading['bom_stripped']}"
        f"|fenced={reading['fenced']}|truncated={reading['truncated']}|body={body}"
    )


def _md5(reading: dict) -> str:
    return hashlib.md5(_canonical(reading).encode("utf-8")).hexdigest()


def _py_corpus() -> dict:
    out: dict = {}
    for path in sorted(CORPUS_ROOT.rglob("task.md")):
        rel = path.relative_to(CORPUS_ROOT).as_posix()
        out[rel] = _py_reading(path.read_text(encoding="utf-8", errors="replace"))
    return out


def _run_typescript(corpus_files: list[str], extra_cases: list[dict] | None = None) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; TS parity cannot be measured (fail-closed, P-016)")
    if not TS_MODULE.is_file():
        pytest.fail(f"TS module missing: {TS_MODULE} (fail-closed)")
    if not FIXTURE_FILE.is_file():
        pytest.fail(f"golden fixture missing: {FIXTURE_FILE} (fail-closed)")
    env = dict(**os.environ)
    env.update(
        {
            "MW_TS_MODULE": str(TS_MODULE),
            "MW_TS_FIXTURE": str(FIXTURE_FILE),
            "MW_TS_CORPUS_ROOT": str(CORPUS_ROOT),
            "MW_TS_CORPUS_FILES": json.dumps(corpus_files),
            "MW_TS_EXTRA_CASES": json.dumps(extra_cases or []),
        }
    )
    proc = subprocess.run(
        [node, "--experimental-strip-types", "-e", _TS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or "TS_JSON_BEGIN" not in proc.stdout or "TS_JSON_END" not in proc.stdout:
        pytest.fail(
            f"node TS parity harness failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    text = proc.stdout.split("TS_JSON_BEGIN", 1)[1].split("TS_JSON_END", 1)[0].strip()
    return json.loads(text)


_MEASURED: dict | None = None


def _measured() -> dict:
    """Measure both sides exactly once and cache."""
    global _MEASURED
    if _MEASURED is None:
        fixture = _fixture()
        py_cases = {case["id"]: _py_reading(_decode(case)) for case in fixture["cases"]}
        py_cases.update({case["id"]: _py_reading(case["text"]) for case in EOL_CASES})
        py_corpus = _py_corpus()
        extra_cases = [
            {"id": case["id"], "content_b64": base64.b64encode(case["text"].encode("utf-8")).decode("ascii")}
            for case in EOL_CASES
        ]
        ts = _run_typescript(sorted(py_corpus), extra_cases)
        _MEASURED = {
            "fixture": fixture,
            "py_cases": py_cases,
            "ts_cases": ts["cases"],
            "py_corpus": py_corpus,
            "ts_corpus": ts["corpus"],
        }
    return _MEASURED


def test_node_missing_is_fail_not_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """P-016: a hollow skip is not an acceptable measurement."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception):
        _run_typescript([])


def test_fixture_shape() -> None:
    fixture = _fixture()
    assert fixture["version"] == 1
    cases = fixture["cases"]
    assert len(cases) == 18, f"golden fixture must carry 18 cases, got {len(cases)}"
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"
    for case in cases:
        assert "content_b64" in case, f"{case['id']}: fixture must inline content as base64"
        assert "content" not in case, f"{case['id']}: raw content would be eol-rewritten by .gitattributes"
        _decode(case)
    texts = [_decode(case) for case in cases]
    assert any(text.startswith("\ufeff") for text in texts), "fixture misses a BOM case"
    assert any(text.startswith("---\n") for text in texts), "fixture misses a fenced case"
    assert any("---\ntype:" in text and text.count("---") == 1 for text in texts), "fixture misses an unclosed fence"
    assert any(text.endswith("\r\n") for text in texts), "fixture misses a CRLF case"
    assert any("\n\ntype:" in text for text in texts), "fixture misses a body type: case"
    print(f"[VERIFY] fixture: cases={len(cases)} base64_inlined=true", flush=True)


def test_fixture_expected_python() -> None:
    measured = _measured()
    py_cases = measured["py_cases"]
    compared = 0
    for case in measured["fixture"]["cases"]:
        case_id = case["id"]
        expected = case["expected"]
        got = py_cases[case_id]
        for field in ("type", "source", "bom_stripped", "fenced", "truncated", "body_type_lines"):
            assert got[field] == expected[field], f"{case_id}: py {field} {got[field]!r} != {expected[field]!r}"
        registered = got["type"] in mw_common.TASK_TYPE_TO_ROLE
        assert registered == expected["registered"], f"{case_id}: py registered {registered} != {expected['registered']}"
        compared += 1
    print(f"[VERIFY] py_vs_fixture={compared}/{len(py_cases)}", flush=True)


def test_fixture_expected_typescript() -> None:
    measured = _measured()
    ts_cases = measured["ts_cases"]
    compared = 0
    for case in measured["fixture"]["cases"]:
        case_id = case["id"]
        expected = case["expected"]
        got = ts_cases[case_id]
        for field in ("type", "source", "bom_stripped", "fenced", "truncated", "body_type_lines", "escalates"):
            assert got[field] == expected[field], f"{case_id}: ts {field} {got[field]!r} != {expected[field]!r}"
        compared += 1
    print(f"[VERIFY] ts_vs_fixture={compared}/{len(ts_cases)}", flush=True)


def test_fixture_reverse_diff() -> None:
    measured = _measured()
    py_cases, ts_cases = measured["py_cases"], measured["ts_cases"]
    assert set(py_cases) == set(ts_cases), sorted(set(py_cases) ^ set(ts_cases))
    compared = 0
    for case_id, py in py_cases.items():
        ts = ts_cases[case_id]
        for field in ("type", "source", "bom_stripped", "fenced", "truncated", "body_type_lines"):
            assert py[field] == ts[field], f"{case_id}: py {field} {py[field]!r} != ts {ts[field]!r}"
        compared += 1
    print(f"[VERIFY] py_ts_field_diff={compared}/{len(py_cases)} equal=true", flush=True)


def test_eol_normalization_cross_language() -> None:
    """T-19/C-15+C-16: CR / CRLF / U+2028 read identically on both sides and
    match the folded `\n` expectation (1 positive + 1 negative per class)."""
    measured = _measured()
    groups = {case["group"] for case in EOL_CASES}
    assert groups == {"cr", "crlf", "u2028"}, f"EOL fixture classes drifted: {sorted(groups)}"
    positives = [case for case in EOL_CASES if case["expected"]["fenced"]]
    assert len(positives) == 3 and len(EOL_CASES) == 6, "each class needs 1 positive + 1 negative"
    compared = 0
    for case in EOL_CASES:
        case_id = case["id"]
        py = measured["py_cases"][case_id]
        ts = measured["ts_cases"][case_id]
        for field in ("type", "source", "bom_stripped", "fenced", "truncated", "body_type_lines"):
            expected = case["expected"][field]
            assert py[field] == expected, f"{case_id}: py {field} {py[field]!r} != {expected!r}"
            assert ts[field] == expected, f"{case_id}: ts {field} {ts[field]!r} != {expected!r}"
        compared += 1
    print(f"[VERIFY] eol_cross_language={compared}/{len(EOL_CASES)} py_eq_ts_eq_expected=true", flush=True)


def test_corpus_cross_language() -> None:
    measured = _measured()
    py_corpus, ts_corpus = measured["py_corpus"], measured["ts_corpus"]
    assert set(py_corpus) == set(ts_corpus), sorted(set(py_corpus) ^ set(ts_corpus))
    py_md5 = {rel: _md5(reading) for rel, reading in py_corpus.items()}
    ts_md5 = {rel: _md5(reading) for rel, reading in ts_corpus.items()}
    mismatched = [rel for rel in py_md5 if py_md5[rel] != ts_md5[rel]]
    assert not mismatched, f"py_md5 != ts_md5 for {len(mismatched)} file(s): {mismatched[:5]}"
    print(f"[VERIFY] corpus_py_md5_eq_ts_md5={len(py_md5)}/{len(py_md5)}", flush=True)


def test_bom_historical_books() -> None:
    measured = _measured()
    py_corpus, ts_corpus = measured["py_corpus"], measured["ts_corpus"]
    for rel in BOM_BOOKS:
        assert rel in py_corpus, f"historical BOM book missing from corpus: {rel}"
        py = py_corpus[rel]
        ts = ts_corpus[rel]
        assert py["bom_stripped"] is True, f"{rel}: Python did not report the BOM"
        assert py["source"] == "header", f"{rel}: Python source {py['source']!r} != 'header'"
        assert py["type"], f"{rel}: Python still cannot read a type: ({py['type']!r})"
        assert py["type"] == ts["type"], f"{rel}: py type {py['type']!r} != ts type {ts['type']!r}"
        assert _md5(py) == _md5(ts), f"{rel}: py/ts reading diverges"
    print(f"[VERIFY] bom_books_readable={len(BOM_BOOKS)}/{len(BOM_BOOKS)}", flush=True)
