"""
test_autopilot_config_parity.py — Python half of the TS <-> Python autopilot
config parity table (mw-autopilot-verify-cli T-07, design D-013, AC-006 /
VC-006).

The CI judge is the TS vitest suite `autopilot-config-parity.test.ts`, which
spawns this package's `autopilot.config` as a subprocess. This module is the
mirror half-table for offline development: it runs the SAME shared corpus
(`test/fixtures/autopilot-config-corpus.json`) through the real Python module,
then runs the real TS module through `node --experimental-strip-types` and diffs
the two sides — so the Python half is a genuine reverse differential, not a
hand-copied expectation.

Criteria:
  P1 accept/reject + offending-field-name set identical per payload
  P2 `save_config` and `saveConfig` byte-identical (sha256)
  P3 read-modify-write byte-idempotent in both directions
  P4 corpus sha256 + case count + D1-D6 coverage
  P5 registry dump is exercised by the TS suite (kept out of this mirror)
  P6 view layering (D-004 was withdrawn, 0d11cc22d): a partial file yields a
     partial dict from the Python *raw* loader (``config.load_config``), while
     the Python *parsed* view (``effective_config.load_effective().values``)
     and the TS merged ``readConfig`` both yield the full 13-key shape. The
     cross-side comparison is parsed-vs-parsed; the raw loader has no TS
     counterpart because ``readConfig`` is deliberately merge-on-read.

Fail-closed (P-016): a missing `node` executable is a hard failure, never a
skip — a skipped case is a hollow measurement.

Run: cd packages/multi-workers && python -m pytest -q test_autopilot_config_parity.py
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_HERE))

from autopilot import config, effective_config  # noqa: E402

CORPUS_FILE = _HERE / "test" / "fixtures" / "autopilot-config-corpus.json"
TS_MODULE = (
    _REPO / "packages" / "coding-agent" / "src" / "extensions"
    / "agent-team-loop" / "autopilot" / "status-model.ts"
)

FROZEN_CORPUS_SHA256 = "951987eaf2abebfa256365ed6642ce1ae0b077a2a6a6c18b4f974729c7dc594d"
FROZEN_CORPUS_COUNT = 53

KNOWN_FIELDS = list(config.DEFAULT_CONFIG)

_TS_SCRIPT = r"""
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { pathToFileURL } = require("node:url");

(async () => {
	const mod = await import(pathToFileURL(process.env.MW_TS_MODULE).href);
	const corpus = JSON.parse(fs.readFileSync(process.env.MW_TS_CORPUS, "utf8"));
	const work = process.env.MW_TS_WORK;
	const cross = process.env.MW_TS_CROSS;
	const known = Object.keys(mod.DEFAULT_CONFIG);
	const errorFields = (message) => {
		const found = new Set();
		for (const field of known) {
			if (new RegExp("\\b" + field + "\\b").test(message)) found.add(field);
		}
		const unknown = /unknown field\(s\): ([^;]+)/.exec(message);
		if (unknown) {
			for (const token of unknown[1].split(",")) {
				const trimmed = token.trim();
				if (trimmed.length > 0) found.add(trimmed);
			}
		}
		return [...found].sort();
	};
	const fileOf = (root) => path.join(root, ".agenticdoc", "_autopilot", "config.json");
	const cases = {};
	corpus.cases.forEach((testCase, index) => {
		const root = path.join(work, String(index).padStart(2, "0") + "-" + testCase.id);
		const file = fileOf(root);
		fs.mkdirSync(path.dirname(file), { recursive: true });
		fs.writeFileSync(file, testCase.payload_text, "utf8");
		const read = mod.readConfig(root);
		if (!read.ok) {
			cases[testCase.id] = { verdict: "reject", error_fields: errorFields(read.error) };
			return;
		}
		const keys = Object.keys(read.config);
		const saved = mod.saveConfig(root, read.config);
		if (!saved.ok) {
			console.error("saveConfig refused " + testCase.id + ": " + saved.error);
			process.exit(3);
		}
		const before = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
		cases[testCase.id] = { verdict: "accept", error_fields: [], keys, sha256: before };
	});
	const crossRead = {};
	corpus.cases.forEach((testCase, index) => {
		const root = path.join(cross, String(index).padStart(2, "0") + "-" + testCase.id);
		const file = fileOf(root);
		const before = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
		const read = mod.readConfig(root);
		if (!read.ok) {
			crossRead[testCase.id] = { verdict: "reject", before_sha256: before, after_sha256: "" };
			return;
		}
		const saved = mod.saveConfig(root, read.config);
		if (!saved.ok) {
			console.error("cross saveConfig refused " + testCase.id + ": " + saved.error);
			process.exit(3);
		}
		crossRead[testCase.id] = {
			verdict: "accept",
			before_sha256: before,
			after_sha256: crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex"),
		};
	});
	process.stdout.write("TS_JSON_BEGIN\n");
	process.stdout.write(JSON.stringify({ cases, crossRead }) + "\n");
	process.stdout.write("TS_JSON_END\n");
})().catch((error) => {
	console.error(error && error.stack ? error.stack : String(error));
	process.exit(1);
});
"""


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _error_fields(message: str) -> list[str]:
    found = {field for field in KNOWN_FIELDS if re.search(r"\b" + re.escape(field) + r"\b", message)}
    unknown = re.search(r"unknown field\(s\): ([^;]+)", message)
    if unknown:
        for token in unknown.group(1).split(","):
            token = token.strip()
            if token:
                found.add(token)
    return sorted(found)


def _case_root(work: pathlib.Path, index: int, case_id: str) -> pathlib.Path:
    return work / f"{index:02d}-{case_id}"


def _measure_python(corpus: dict, work: pathlib.Path) -> dict:
    """Seed each payload, read it through both Python views, re-save on accept.

    D-004 was withdrawn (0d11cc22d), so ``load_config`` is the *raw* loader:
    it returns exactly the keys the file carries. The full 13-key view is the
    *parsed* view, ``effective_config.load_effective().values`` — a canonical
    write materializes that view, which is what the TS ``saveConfig`` does too,
    so P2/P3 byte parity still compares full-view writes on both sides.
    """
    records: dict = {}
    for index, case in enumerate(corpus["cases"]):
        root = _case_root(work, index, case["id"])
        path = config.config_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(case["payload_text"], encoding="utf-8")
        before = _sha256_file(path)
        try:
            loaded = config.load_config(root)
            record = {"verdict": "accept", "error_fields": []}
        except config.ConfigError as exc:
            loaded = None
            record = {"verdict": "reject", "error_fields": _error_fields(str(exc))}
        if loaded is not None:
            record["raw_keys"] = list(loaded.keys())
            # env={} pins the parsed view to the project layer only (no HOME
            # machine defaults), so the measurement is hermetic.
            effective = effective_config.load_effective(root, env={}).values
            record["effective_keys"] = list(effective.keys())
            config.save_config(root, effective)
            record["before_sha256"] = before
            record["after_sha256"] = _sha256_file(path)
        records[case["id"]] = record
    return records


def _crossread_python(corpus: dict, work: pathlib.Path) -> dict:
    """Read a tree the TS side wrote, re-save, and report before/after bytes."""
    records: dict = {}
    for index, case in enumerate(corpus["cases"]):
        root = _case_root(work, index, case["id"])
        path = config.config_path(root)
        if not path.exists():
            pytest.fail(f"TS side did not write {path}")
        before = _sha256_file(path)
        try:
            config.load_config(root)
            effective = effective_config.load_effective(root, env={}).values
            config.save_config(root, effective)
            records[case["id"]] = {
                "verdict": "accept",
                "before_sha256": before,
                "after_sha256": _sha256_file(path),
            }
        except config.ConfigError as exc:
            records[case["id"]] = {
                "verdict": "reject",
                "before_sha256": before,
                "after_sha256": "",
                "error": str(exc),
            }
    return records


def _run_typescript(corpus: dict, work: pathlib.Path, cross: pathlib.Path) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; TS parity cannot be measured (fail-closed, P-016)")
    if not TS_MODULE.is_file():
        pytest.fail(f"TS module missing: {TS_MODULE} (fail-closed)")
    env = dict(**os.environ)
    env.update(
        {
            "MW_TS_MODULE": str(TS_MODULE),
            "MW_TS_CORPUS": str(CORPUS_FILE),
            "MW_TS_WORK": str(work),
            "MW_TS_CROSS": str(cross),
        }
    )
    proc = subprocess.run(
        [node, "--experimental-strip-types", "-e", _TS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
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
_TMP_ROOT: pathlib.Path | None = None


def _measured() -> dict:
    """Measure both sides exactly once and cache (mirrors the TS suite)."""
    global _MEASURED, _TMP_ROOT
    if _MEASURED is not None:
        return _MEASURED
    corpus = json.loads(CORPUS_FILE.read_text(encoding="utf-8"))
    _TMP_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="mw-apcfg-parity-"))
    atexit.register(shutil.rmtree, _TMP_ROOT, ignore_errors=True)
    py_dir = _TMP_ROOT / "py"
    ts_dir = _TMP_ROOT / "ts"
    py_dir.mkdir()
    ts_dir.mkdir()
    py = _measure_python(corpus, py_dir)
    ts = _run_typescript(corpus, ts_dir, py_dir)
    py_cross = _crossread_python(corpus, ts_dir)
    _MEASURED = {
        "corpus": corpus,
        "py": py,
        "ts": ts["cases"],
        "ts_cross": ts["crossRead"],
        "py_cross": py_cross,
    }
    return _MEASURED


def _payload_keys(case: dict) -> list[str] | None:
    """Keys the payload literally writes, in file order (None when not an object)."""
    try:
        parsed = json.loads(case["payload_text"])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return list(parsed.keys())


def _single_key_cases(corpus: dict) -> list[tuple[dict, str]]:
    out: list[tuple[dict, str]] = []
    for case in corpus["cases"]:
        if case["expected"]["verdict"] != "accept":
            continue
        keys = _payload_keys(case)
        if keys is None or len(keys) != 1:
            continue
        out.append((case, keys[0]))
    return out


def test_p4_corpus_integrity() -> None:
    digest = hashlib.sha256(CORPUS_FILE.read_bytes()).hexdigest()
    assert digest == FROZEN_CORPUS_SHA256, "corpus sha256 drifted; re-freeze deliberately"
    corpus = json.loads(CORPUS_FILE.read_text(encoding="utf-8"))
    assert len(corpus["cases"]) == FROZEN_CORPUS_COUNT
    categories = {c for case in corpus["cases"] for c in case["categories"]}
    assert {"D1", "D2", "D3", "D4", "D5", "D6"} <= categories, categories
    payloads = [case["payload_text"] for case in corpus["cases"]]
    for needle in ("4.0", "4.00", "1e2", "-0.0", "4.5", '"4"', '""', "9007199254740992", "9007199254740991"):
        assert any(needle in payload for payload in payloads), f"missing payload {needle}"
    assert any(any(ord(ch) > 0x7F for ch in payload) for payload in payloads), "missing non-ASCII payload"
    print(f"[VERIFY] P4: corpus_sha256={digest} cases={len(corpus['cases'])} categories={sorted(categories)}", flush=True)


def test_p1_crosslang_verdicts() -> None:
    measured = _measured()
    corpus, py, ts = measured["corpus"], measured["py"], measured["ts"]
    compared = 0
    for case in corpus["cases"]:
        case_id = case["id"]
        expected = case["expected"]
        assert py[case_id]["verdict"] == expected["verdict"], f"{case_id}: py vs corpus"
        assert ts[case_id]["verdict"] == expected["verdict"], f"{case_id}: ts vs corpus"
        assert py[case_id]["verdict"] == ts[case_id]["verdict"], f"{case_id}: py vs ts verdict"
        if expected["verdict"] == "reject":
            assert py[case_id]["error_fields"] == expected["error_fields"], f"{case_id}: py fields"
            assert ts[case_id]["error_fields"] == expected["error_fields"], f"{case_id}: ts fields"
        compared += 1
    assert compared == len(corpus["cases"])
    print(f"[VERIFY] P1: crosslang_verdict_match={compared}/{len(corpus['cases'])}", flush=True)


def test_p2_crosslang_bytes() -> None:
    measured = _measured()
    corpus, py, ts = measured["corpus"], measured["py"], measured["ts"]
    compared = 0
    for case in corpus["cases"]:
        case_id = case["id"]
        if py[case_id]["verdict"] != "accept":
            continue
        assert ts[case_id]["verdict"] == "accept", f"{case_id}: ts verdict"
        assert py[case_id]["after_sha256"] == ts[case_id]["sha256"], (
            f"{case_id}: canonical bytes differ (py={py[case_id]['after_sha256']} ts={ts[case_id]['sha256']})"
        )
        compared += 1
    assert compared >= 31, compared
    print(f"[VERIFY] P2: canonical_sha_match={compared} sha256_equal=true", flush=True)


def test_p3_crossread_idempotence() -> None:
    measured = _measured()
    corpus = measured["corpus"]
    py, ts, ts_cross, py_cross = measured["py"], measured["ts"], measured["ts_cross"], measured["py_cross"]
    py_to_ts = 0
    ts_to_py = 0
    for case in corpus["cases"]:
        case_id = case["id"]
        if py[case_id]["verdict"] != "accept":
            continue
        # Python wrote -> TS read + re-wrote (`ts_cross`).
        assert ts_cross[case_id]["verdict"] == "accept", f"{case_id}: ts cross-read"
        assert ts_cross[case_id]["before_sha256"] == py[case_id]["after_sha256"], f"{case_id}: ts cross-read before"
        assert ts_cross[case_id]["after_sha256"] == ts_cross[case_id]["before_sha256"], f"{case_id}: py -> ts idempotence"
        assert ts_cross[case_id]["before_sha256"] == ts[case_id]["sha256"], f"{case_id}: ts canonical"
        py_to_ts += 1
        # TS wrote -> Python read + re-wrote (`py_cross`).
        assert py_cross[case_id]["verdict"] == "accept", f"{case_id}: py cross-read"
        assert py_cross[case_id]["before_sha256"] == ts[case_id]["sha256"], f"{case_id}: py cross-read before"
        assert py_cross[case_id]["after_sha256"] == py_cross[case_id]["before_sha256"], f"{case_id}: ts -> py idempotence"
        ts_to_py += 1
    assert py_to_ts >= 31 and ts_to_py == py_to_ts
    print(f"[VERIFY] P3: py_to_ts_idempotent={py_to_ts} ts_to_py_idempotent={ts_to_py}", flush=True)


def test_p6_partial_single_key() -> None:
    """Layered-view contract after D-004 was withdrawn (0d11cc22d).

    Python exposes two distinct views and they must not be conflated:

      * raw: ``config.load_config`` returns exactly the keys the file carries
        (a partial file yields a partial dict — no silent default fill);
      * parsed: ``effective_config.load_effective(root).values`` returns the
        full 13-key view (same set/order as :func:`config.default_config`).

    TS ``readConfig`` is merge-on-read (view-side robustness: absent fields
    fall back to defaults), so it is comparable only to the Python *parsed*
    view. There is no TS counterpart to the raw loader, which is why the raw
    assertion below is Python-only and the cross-side comparison is
    parsed-vs-parsed.
    """
    measured = _measured()
    corpus, py, ts = measured["corpus"], measured["py"], measured["ts"]
    expected_keys = set(KNOWN_FIELDS)
    # Raw view, every accepted payload: exactly the keys the file wrote (this
    # also covers the 0-key and 2-key partials, not just the single-key ones).
    for case in corpus["cases"]:
        case_id = case["id"]
        if case["expected"]["verdict"] != "accept":
            continue
        written = _payload_keys(case)
        assert written is not None, f"{case_id}: accepted payload is not a JSON object"
        assert py[case_id]["raw_keys"] == written, (
            f"{case_id}: raw load_config keys {py[case_id]['raw_keys']} != written keys {written}"
        )
    partials = _single_key_cases(corpus)
    covered: set[str] = set()
    for case, key in partials:
        case_id = case["id"]
        assert py[case_id]["verdict"] == "accept", f"{case_id}: py"
        assert ts[case_id]["verdict"] == "accept", f"{case_id}: ts"
        # Python raw loader: only the single key the file actually carries.
        assert py[case_id]["raw_keys"] == [key], f"{case_id}: py raw key set"
        # Python parsed view: the full 13-key shape.
        assert len(py[case_id]["effective_keys"]) == 13, f"{case_id}: py effective key count"
        assert set(py[case_id]["effective_keys"]) == expected_keys, f"{case_id}: py effective key set"
        # TS readConfig merged (parsed) view: the full 13-key shape.
        assert len(ts[case_id]["keys"]) == 13, f"{case_id}: ts merged key count"
        assert set(ts[case_id]["keys"]) == expected_keys, f"{case_id}: ts merged key set"
        # Cross-side parsed comparison: TS merged vs Python effective. Never
        # TS vs the Python raw loader (that view is deliberately partial here).
        assert set(ts[case_id]["keys"]) == set(py[case_id]["effective_keys"]), (
            f"{case_id}: ts merged vs py effective key set"
        )
        covered.add(key)
    assert covered == expected_keys, sorted(expected_keys - covered)
    print(
        f"[VERIFY] P6: partial_single_key={len(partials)} raw_view_partial=true "
        f"effective_view_13=true fields_covered={len(covered)}",
        flush=True,
    )
