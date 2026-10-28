"""
test_update_index_key_refusal.py — T-15 (AC-006 / DD-07b, DD-07c): Python <-> TS
key-name gate parity for the framework `update_index.py` claim choke point.

`update_index.py` and the TS `shared/index-store.ts` cannot physically share the
key-name judgement (one is Python, one is TypeScript), so "same semantics" is
made a measured fact instead of a comment:

  * an inline golden table (reserved names, reserved-name case variants,
    prefix names, legal unoccupied names, path escapes, empty / overlong /
    illegal-shape names) is judged by the real `update_index.key_name_refusal`
    and by the real TS `keyNameRefusal` through `node --experimental-strip-types`,
    then diffed entry by entry (verdict + stable code);
  * the 14-name reserved constant is compared to the TS `RESERVED_INDEX_NAMES`;
  * the direction contract is exercised on the real Python claim choke point:
    reserved/illegal names are refused without touching the index, a legal
    unoccupied name is allowed, `_scratch` is refused as a claimable key, and a
    case-variant claim resolves to the first-written row instead of appending a
    duplicate.

Fail-closed (P-016, copied from test_task_type_parity.py / the T-08 pattern): a
missing `node` executable is a hard failure, never a skip — a skipped case is a
hollow measurement.

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_update_index_key_refusal.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent

UPDATE_INDEX = _REPO / ".agents" / "skills" / "agentic-task" / "scripts" / "update_index.py"
TS_MODULE = (
    _REPO
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "index-store.ts"
)

# Stable refusal codes of the shared name gate (TS `KeyNameRefusal.code`).
CODES = ("empty-key", "reserved-key-name", "key-path-escape", "key-illegal-shape")


def _case(cid: str, category: str, key: str, code: str | None) -> dict:
    return {"id": cid, "category": category, "key": key, "code": code}


_LONG_64 = "a" * 64
_LONG_65 = "a" * 65

# The inline golden table. `code=None` means the name is usable (the new-key
# bootstrap path). Reserved names are the T-09 14-name constant; the case
# variants lock the lowercase comparison form, and the U+FEFF / U+0085 rows lock
# the two trim divergences between Python `str.strip()` and JS `String.trim()`
# (T-08 `_JS_TRIM_CHARS` precedent).
CASES: tuple[dict, ...] = (
    # ── the explicit 14 reserved names (RQ-5's 12 + _impl_gate.log + _incidents)
    _case("r01", "reserved", "_scratch", "reserved-key-name"),
    _case("r02", "reserved", ".mw", "reserved-key-name"),
    _case("r03", "reserved", "_index.parallel", "reserved-key-name"),
    _case("r04", "reserved", "_index.md", "reserved-key-name"),
    _case("r05", "reserved", "_workers.parallel", "reserved-key-name"),
    _case("r06", "reserved", "_workers.stale.parallel", "reserved-key-name"),
    _case("r07", "reserved", "_workers.acked", "reserved-key-name"),
    _case("r08", "reserved", "_autopilot", "reserved-key-name"),
    _case("r09", "reserved", "_project_log.md", "reserved-key-name"),
    _case("r10", "reserved", "_arch_snapshot.md", "reserved-key-name"),
    _case("r11", "reserved", "_pitfalls.md", "reserved-key-name"),
    _case("r12", "reserved", ".agenticdoc", "reserved-key-name"),
    _case("r13", "reserved", "_impl_gate.log", "reserved-key-name"),
    _case("r14", "reserved", "_incidents", "reserved-key-name"),
    # ── reserved-name case variants (Windows-insensitive lookup)
    _case("rc01", "reserved-case", "_SCRATCH", "reserved-key-name"),
    _case("rc02", "reserved-case", "_Index.Parallel", "reserved-key-name"),
    _case("rc03", "reserved-case", ".MW", "reserved-key-name"),
    _case("rc04", "reserved-case", ".AgenticDoc", "reserved-key-name"),
    _case("rc05", "reserved-case", "_WORKERS.PARALLEL", "reserved-key-name"),
    # ── prefix names: exempted before AC-006, now illegal shape
    _case("p01", "prefix", "_tmp", "key-illegal-shape"),
    _case("p02", "prefix", ".hidden", "key-illegal-shape"),
    _case("p03", "prefix", "_", "key-illegal-shape"),
    _case("p04", "prefix", "-lead", "key-illegal-shape"),
    _case("p05", "prefix", "~x", "key-illegal-shape"),
    _case("p06", "prefix", "-----", "key-illegal-shape"),
    _case("p07", "prefix", "_work", "key-illegal-shape"),
    _case("p08", "prefix", ".agentic", "key-illegal-shape"),
    # ── legal, unoccupied names (the new-key bootstrap path)
    _case("l01", "legal", "mw-ok", None),
    _case("l02", "legal", "mw.fresh-2", None),
    _case("l03", "legal", "MW-Key", None),
    _case("l04", "legal", "a", None),
    _case("l05", "legal", "A1_b.c-2", None),
    _case("l06", "legal", "x_9", None),
    _case("l07", "legal", "key-0", None),
    _case("l08", "legal", "  mw-ok  ", None),
    _case("l09", "legal", _LONG_64, None),
    _case("l10", "legal", "\ufeffmw-ok", None),  # JS trims U+FEFF, Python must too
    _case("l11", "legal", "0", None),
    # ── path escapes / separators / drive prefixes
    _case("e01", "path", "a/b", "key-path-escape"),
    _case("e02", "path", "a\\b", "key-path-escape"),
    _case("e03", "path", "../x", "key-path-escape"),
    _case("e04", "path", "..", "key-path-escape"),
    _case("e05", "path", ".", "key-path-escape"),
    _case("e06", "path", "C:x", "key-path-escape"),
    _case("e07", "path", "C:\\x", "key-path-escape"),
    _case("e08", "path", "\\\\server\\share", "key-path-escape"),
    # ── empty (after trim)
    _case("m01", "empty", "", "empty-key"),
    _case("m02", "empty", "   ", "empty-key"),
    _case("m03", "empty", "\t", "empty-key"),
    _case("m04", "empty", "\ufeff", "empty-key"),
    # ── illegal shape (overlong / trailing dot / control / ADS / metachars)
    _case("s01", "shape", _LONG_65, "key-illegal-shape"),
    _case("s02", "shape", "trailing.", "key-illegal-shape"),
    _case("s03", "shape", "a...", "key-illegal-shape"),
    _case("s04", "shape", "a b", "key-illegal-shape"),
    _case("s05", "path", "a:b", "key-path-escape"),  # `a:` is read as a drive prefix first (TS check order)
    _case("s06", "shape", "a*b", "key-illegal-shape"),
    _case("s07", "shape", "a?b", "key-illegal-shape"),
    _case("s08", "shape", 'a"b', "key-illegal-shape"),
    _case("s09", "shape", "a<b", "key-illegal-shape"),
    _case("s10", "shape", "a>b", "key-illegal-shape"),
    _case("s11", "shape", "a|b", "key-illegal-shape"),
    _case("s12", "shape", "a\x00b", "key-illegal-shape"),
    _case("s13", "shape", "a\x7fb", "key-illegal-shape"),
    _case("s14", "shape", "a\nb", "key-illegal-shape"),
    _case("s15", "shape", "\u0085mw-ok", "key-illegal-shape"),  # JS does not trim U+0085
    _case("s16", "shape", "a\u001cb", "key-illegal-shape"),  # Python strip() would trim \x1c
)

_TS_SCRIPT = r"""
const fs = require("node:fs");
const { pathToFileURL } = require("node:url");

(async () => {
	const mod = await import(pathToFileURL(process.env.MW_T15_TS_MODULE).href);
	const keys = JSON.parse(fs.readFileSync(process.env.MW_T15_KEYS, "utf8"));
	const refusals = {};
	for (const item of keys) {
		const refusal = mod.keyNameRefusal(item.key);
		refusals[item.id] = refusal === null ? null : refusal.code;
	}
	const out = {
		refusals,
		reserved: mod.RESERVED_INDEX_NAMES,
		scratchGuardAllows: mod.isScratchKey("_scratch"),
	};
	process.stdout.write("TS_JSON_BEGIN\n");
	process.stdout.write(JSON.stringify(out) + "\n");
	process.stdout.write("TS_JSON_END\n");
})().catch((error) => {
	console.error(error && error.stack ? error.stack : String(error));
	process.exit(1);
});
"""


def _load_update_index():
    spec = importlib.util.spec_from_file_location("mwgf_t15_update_index", UPDATE_INDEX)
    if spec is None or spec.loader is None:
        pytest.fail(f"cannot load update_index.py at {UPDATE_INDEX} (fail-closed)")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MOD: object | None = None


def _mod():
    global _MOD
    if _MOD is None:
        _MOD = _load_update_index()
    return _MOD


def _py_refusal(key: str) -> str | None:
    """Stable code from the Python half of the gate (None = usable name)."""
    refusal = _mod().key_name_refusal(key)
    return None if refusal is None else refusal[0]


def _py_refusal_message(key: str) -> str | None:
    refusal = _mod().key_name_refusal(key)
    return None if refusal is None else refusal[1]


def _run_typescript(cases: tuple[dict, ...]) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; TS parity cannot be measured (fail-closed, P-016)")
    if not TS_MODULE.is_file():
        pytest.fail(f"TS module missing: {TS_MODULE} (fail-closed)")
    if not UPDATE_INDEX.is_file():
        pytest.fail(f"update_index.py missing: {UPDATE_INDEX} (fail-closed)")
    with tempfile.TemporaryDirectory(prefix="mwgf-t15-keys-") as tmp:
        keys_file = pathlib.Path(tmp) / "keys.json"
        keys_file.write_text(
            json.dumps([{"id": case["id"], "key": case["key"]} for case in cases]),
            encoding="utf-8",
        )
        env = dict(**os.environ)
        env.update({"MW_T15_TS_MODULE": str(TS_MODULE), "MW_T15_KEYS": str(keys_file)})
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


def _measured() -> dict:
    """Measure both sides exactly once and cache (mirrors test_task_type_parity)."""
    global _MEASURED
    if _MEASURED is None:
        py = {case["id"]: _py_refusal(case["key"]) for case in CASES}
        ts = _run_typescript(CASES)
        _MEASURED = {"py": py, "ts": ts["refusals"], "ts_reserved": ts["reserved"], "ts_scratch": ts["scratchGuardAllows"]}
    return _MEASURED


def _claim(module, root: pathlib.Path, key: str) -> int:
    """Run the real claim choke point, swallowing its stdout/stderr."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return module.cmd_claim(root, key, force=True)


def _read_keys(module, root: pathlib.Path) -> list[str]:
    index = root / "_index.parallel"
    if not index.is_file():
        return []
    return [row["key"] for row in module.read_index(index)]


# ── fail-closed ──────────────────────────────────────────────────────────────


def test_node_missing_is_fail_not_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """P-016: a hollow skip is not an acceptable measurement."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception):
        _run_typescript(CASES)


# ── golden table ─────────────────────────────────────────────────────────────


def test_gate_case_table_shape() -> None:
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"
    for case in CASES:
        assert case["code"] is None or case["code"] in CODES, case
    categories = {case["category"] for case in CASES}
    assert {
        "reserved",
        "reserved-case",
        "prefix",
        "legal",
        "path",
        "empty",
        "shape",
    } <= categories, sorted(categories)
    reserved = [case for case in CASES if case["category"] == "reserved"]
    assert len(reserved) == 14, f"reserved category must carry the 14 names, got {len(reserved)}"
    print(f"[VERIFY] table: cases={len(CASES)} categories={len(categories)} reserved={len(reserved)}", flush=True)


def test_python_gate_matches_expected() -> None:
    py = _measured()["py"]
    compared = 0
    for case in CASES:
        assert py[case["id"]] == case["code"], (
            f"{case['id']} ({case['key']!r}): python code {py[case['id']]!r} != expected {case['code']!r}"
        )
        if case["code"] is not None:
            assert isinstance(_py_refusal_message(case["key"]), str) and _py_refusal_message(case["key"])
        compared += 1
    print(f"[VERIFY] py_vs_table={compared}/{len(CASES)}", flush=True)


def test_typescript_gate_matches_expected() -> None:
    ts = _measured()["ts"]
    compared = 0
    for case in CASES:
        assert ts[case["id"]] == case["code"], (
            f"{case['id']} ({case['key']!r}): ts code {ts[case['id']]!r} != expected {case['code']!r}"
        )
        compared += 1
    print(f"[VERIFY] ts_vs_table={compared}/{len(CASES)}", flush=True)


def test_cross_language_gate_diff() -> None:
    measured = _measured()
    py, ts = measured["py"], measured["ts"]
    assert set(py) == set(ts), sorted(set(py) ^ set(ts))
    compared = 0
    for case in CASES:
        cid = case["id"]
        assert py[cid] == ts[cid], (
            f"{cid} ({case['key']!r}): py {py[cid]!r} != ts {ts[cid]!r} "
            "(Python and TS name gates disagree — direction divergence)"
        )
        compared += 1
    print(f"[VERIFY] py_ts_code_diff={compared}/{len(CASES)} equal=true", flush=True)


def test_reserved_constant_parity() -> None:
    measured = _measured()
    module = _mod()
    py_reserved = list(module.RESERVED_INDEX_NAMES)
    ts_reserved = list(measured["ts_reserved"])
    assert py_reserved == ts_reserved, f"reserved constants diverge:\n py={py_reserved}\n ts={ts_reserved}"
    assert len(py_reserved) == 14
    assert len(set(py_reserved)) == 14
    assert all(name == name.lower() for name in py_reserved), py_reserved
    assert module.RESERVED_INDEX_NAME_SET == frozenset(py_reserved)
    print(f"[VERIFY] reserved_constant_parity={len(py_reserved)} equal=true", flush=True)


# ── direction contract on the Python claim choke point ───────────────────────


def test_reserved_and_illegal_names_refused_without_touching_the_index(tmp_path: pathlib.Path) -> None:
    module = _mod()
    refused = [case for case in CASES if case["code"] is not None]
    assert len(refused) >= 40
    for case in refused:
        root = tmp_path / case["id"] / ".agenticdoc"
        root.mkdir(parents=True)
        before = sorted(child.name for child in root.iterdir())
        rc = _claim(module, root, case["key"])
        assert rc == 1, f"{case['id']} ({case['key']!r}): claim rc {rc} != 1 (name gate did not refuse)"
        after = sorted(child.name for child in root.iterdir())
        assert after == before, f"{case['id']}: claim touched the tree: {before} -> {after}"
        assert _read_keys(module, root) == [], f"{case['id']}: claim wrote an index row"
    print(f"[VERIFY] claim_refused={len(refused)} index_untouched=true", flush=True)


def test_reserved_names_refuse_before_any_filesystem_write(tmp_path: pathlib.Path) -> None:
    """`_index.parallel` was crash-prone for this name (FileExistsError) — the
    gate must reject it before `_ensure_index` runs."""
    module = _mod()
    root = tmp_path / ".agenticdoc"
    root.mkdir()
    rc = _claim(module, root, "_index.parallel")
    assert rc == 1
    assert not (root / "_index.parallel").exists(), "claim created/truncated the index for a reserved name"
    assert list(root.iterdir()) == [], f"unexpected writes: {[p.name for p in root.iterdir()]}"
    print("[VERIFY] reserved_index_parallel: rc=1 disk_untouched=true", flush=True)


def test_path_escape_name_creates_nothing_outside_the_root(tmp_path: pathlib.Path) -> None:
    module = _mod()
    root = tmp_path / "proj" / ".agenticdoc"
    root.mkdir(parents=True)
    rc = _claim(module, root, "../x")
    assert rc == 1
    assert not (tmp_path / "proj" / "x").exists(), "path-escape claim wrote outside the .agenticdoc root"
    print("[VERIFY] path_escape: rc=1 escaped=false", flush=True)


def test_legal_unoccupied_name_is_allowed(tmp_path: pathlib.Path) -> None:
    module = _mod()
    root = tmp_path / ".agenticdoc"
    root.mkdir()
    rc = _claim(module, root, "mw-fresh-1")
    assert rc == 0, "a legal, unoccupied key must pass the new-key bootstrap path"
    assert _read_keys(module, root) == ["mw-fresh-1"]
    assert (root / "mw-fresh-1" / "pm-state.md").is_file()
    print("[VERIFY] legal_unoccupied: rc=0 row_written=true", flush=True)


def test_scratch_is_refused_as_a_claimable_key(tmp_path: pathlib.Path) -> None:
    """`_scratch` stays owner-exempt in the TS guard but is never claimable."""
    module = _mod()
    assert _py_refusal("_scratch") == "reserved-key-name"
    assert _measured()["ts_scratch"] is True, "TS guard must still treat _scratch as the owner-exempt name"
    root = tmp_path / ".agenticdoc"
    root.mkdir()
    rc = _claim(module, root, "_scratch")
    assert rc == 1
    assert _read_keys(module, root) == []
    print("[VERIFY] scratch: py_gate=reserved ts_guard_allow=true claim_rc=1", flush=True)


def test_case_variant_claim_keeps_the_first_written_row(tmp_path: pathlib.Path) -> None:
    module = _mod()
    root = tmp_path / ".agenticdoc"
    root.mkdir()
    (root / "_index.parallel").write_text(
        "| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |\n",
        encoding="utf-8",
    )
    rc = _claim(module, root, "MW-KEY")
    assert rc == 0
    keys = _read_keys(module, root)
    assert keys == ["mw-key"], f"case-variant claim appended a duplicate row: {keys}"
    rows = module.read_index(root / "_index.parallel")
    assert len(rows) == 1
    assert rows[0]["key"] == "mw-key"  # first-written casing preserved, no migration
    assert rows[0]["claim_id"] == module.now_claim_id()
    print(f"[VERIFY] case_variant: rows={len(rows)} stored={rows[0]['key']} duplicate=false", flush=True)


# ── T-16: claim/phase command family gate (AC-006 / DD-07c) ─────────────────
#
# T-15 gated `claim` only. `set-phase` / `set-meta` / `release` / `get-claim`
# still compared keys byte-exact and bypassed the name gate, so
# `set-phase _index.parallel EXECUTE` could create a framework-name row and
# `set-phase MW-KEY` could append a second, case-variant row next to `mw-key`.
# This block extends the same two-sided measurement to the 4 commands: the
# shared key-name gate is diffed against the real TS `keyNameRefusal` on a
# second fixture table (node missing = fail, never skip), and the real Python
# commands are run to pin rc=1 + zero-write for refused names and
# normalization for legal / case-variant names.

COMMANDS = ("set-phase", "set-meta", "release", "get-claim")
WRITE_COMMANDS = ("set-phase", "set-meta", "release")


def _cc(cid: str, category: str, key: str, code: str | None) -> dict:
    return {"id": cid, "category": category, "key": key, "code": code}


COMMAND_CASES: tuple[dict, ...] = (
    # reserved names / their case variants
    _cc("k01", "reserved", "_index.parallel", "reserved-key-name"),
    _cc("k02", "reserved", "_workers.parallel", "reserved-key-name"),
    _cc("k03", "reserved", "_incidents", "reserved-key-name"),
    _cc("k04", "reserved", ".mw", "reserved-key-name"),
    _cc("k05", "reserved-case", "_SCRATCH", "reserved-key-name"),
    _cc("k06", "reserved-case", "_Index.Parallel", "reserved-key-name"),
    # prefix / illegal shape
    _cc("k07", "prefix", "_tmp", "key-illegal-shape"),
    _cc("k08", "shape", "trailing.", "key-illegal-shape"),
    _cc("k09", "shape", "a b", "key-illegal-shape"),
    _cc("k10", "shape", _LONG_65, "key-illegal-shape"),
    # path escapes
    _cc("k11", "path", "../x", "key-path-escape"),
    _cc("k12", "path", "a/b", "key-path-escape"),
    _cc("k13", "path", "C:\\x", "key-path-escape"),
    # empty after trim
    _cc("k14", "empty", "", "empty-key"),
    _cc("k15", "empty", "   ", "empty-key"),
    # legal names (new-key bootstrap; the requested casing is the first write)
    _cc("k16", "legal", "mw-cmd-1", None),
    _cc("k17", "legal", "mw-cmd-2", None),
    _cc("k18", "legal", "MW-CMD-3", None),
)


def _run_command(module, root: pathlib.Path, command: str, key: str) -> tuple[int, str]:
    """Run one of the 4 real command entry points, returning (rc, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        if command == "set-phase":
            rc = module.cmd_set_phase(root, key, "EXECUTE")
        elif command == "set-meta":
            rc = module.cmd_set_meta(root, key, desc="cmd-desc", deps=None)
        elif command == "release":
            rc = module.cmd_release(root, key)
        elif command == "get-claim":
            rc = module.cmd_get_claim(root, key)
        else:
            raise AssertionError(f"unknown command {command}")
    return rc, out.getvalue()


_COMMAND_MEASURED: dict | None = None


def _command_measured() -> dict:
    """Measure the command fixture table on both sides exactly once."""
    global _COMMAND_MEASURED
    if _COMMAND_MEASURED is None:
        py = {case["id"]: _py_refusal(case["key"]) for case in COMMAND_CASES}
        ts = _run_typescript(COMMAND_CASES)["refusals"]
        _COMMAND_MEASURED = {"py": py, "ts": ts}
    return _COMMAND_MEASURED


def _snapshot(root: pathlib.Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _seed_case_variant(root: pathlib.Path) -> None:
    (root / "_index.parallel").write_text(
        "| mw-key | active | SPEC | other-host:4242 |  |  | 2026-10-12 00:00 |\n",
        encoding="utf-8",
    )


def test_command_node_missing_is_fail_not_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """P-016 for the command fixture table: a skip is not a measurement."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception):
        _run_typescript(COMMAND_CASES)


def test_command_gate_table_shape() -> None:
    ids = [case["id"] for case in COMMAND_CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"
    assert len(COMMAND_CASES) >= 18
    for case in COMMAND_CASES:
        assert case["code"] is None or case["code"] in CODES, case
    reserved = [case for case in COMMAND_CASES if case["category"] == "reserved"]
    assert len(reserved) == 4, f"reserved command cases: {len(reserved)}"
    print(f"[VERIFY] command_table: cases={len(COMMAND_CASES)} reserved={len(reserved)}", flush=True)


def test_python_command_gate_matches_expected() -> None:
    py = _command_measured()["py"]
    for case in COMMAND_CASES:
        assert py[case["id"]] == case["code"], (
            f"{case['id']} ({case['key']!r}): python code {py[case['id']]!r} != expected {case['code']!r}"
        )
    print(f"[VERIFY] command_py_vs_table={len(COMMAND_CASES)}/{len(COMMAND_CASES)}", flush=True)


def test_typescript_command_gate_matches_expected() -> None:
    ts = _command_measured()["ts"]
    for case in COMMAND_CASES:
        assert ts[case["id"]] == case["code"], (
            f"{case['id']} ({case['key']!r}): ts code {ts[case['id']]!r} != expected {case['code']!r}"
        )
    print(f"[VERIFY] command_ts_vs_table={len(COMMAND_CASES)}/{len(COMMAND_CASES)}", flush=True)


def test_cross_language_command_gate_diff() -> None:
    measured = _command_measured()
    py, ts = measured["py"], measured["ts"]
    assert set(py) == set(ts), sorted(set(py) ^ set(ts))
    for case in COMMAND_CASES:
        cid = case["id"]
        assert py[cid] == ts[cid], (
            f"{cid} ({case['key']!r}): py {py[cid]!r} != ts {ts[cid]!r} "
            "(Python and TS name gates disagree for the command family)"
        )
    print(f"[VERIFY] command_py_ts_code_diff={len(COMMAND_CASES)}/{len(COMMAND_CASES)} equal=true", flush=True)


def test_write_commands_refuse_bad_names_without_writing(tmp_path: pathlib.Path) -> None:
    module = _mod()
    refused = [case for case in COMMAND_CASES if case["code"] is not None]
    checked = 0
    for case in refused:
        for command in WRITE_COMMANDS:
            root = tmp_path / f"{case['id']}-{command}" / ".agenticdoc"
            root.mkdir(parents=True)
            before = _snapshot(root)
            rc, _ = _run_command(module, root, command, case["key"])
            assert rc == 1, f"{command} {case['key']!r}: rc {rc} != 1 (name gate did not refuse)"
            assert not (root / "_index.parallel").exists(), f"{command} {case['key']!r}: created the index"
            assert _snapshot(root) == before, f"{command} {case['key']!r}: tree changed {before} -> {_snapshot(root)}"
            checked += 1
    print(f"[VERIFY] command_refused={checked} index_untouched=true", flush=True)


def test_get_claim_refuses_bad_names(tmp_path: pathlib.Path) -> None:
    module = _mod()
    refused = [case for case in COMMAND_CASES if case["code"] is not None]
    for case in refused:
        root = tmp_path / case["id"] / ".agenticdoc"
        root.mkdir(parents=True)
        rc, _ = _run_command(module, root, "get-claim", case["key"])
        assert rc == 1, f"get-claim {case['key']!r}: rc {rc} != 1"
    print(f"[VERIFY] get_claim_refused={len(refused)}", flush=True)


def test_command_path_escape_creates_nothing_outside_the_root(tmp_path: pathlib.Path) -> None:
    module = _mod()
    for command in WRITE_COMMANDS:
        base = tmp_path / command
        root = base / ".agenticdoc"
        root.mkdir(parents=True)
        # Pre-seed an escaping row: without the gate, `release ../x` reaches the
        # pm-state mirror write at `root/../x/pm-state.md` (outside .agenticdoc).
        (root / "_index.parallel").write_text(
            "| ../x | idle | SPEC | — | — | — | 2026-10-12 00:00 |\n",
            encoding="utf-8",
        )
        rc, _ = _run_command(module, root, command, "../x")
        assert rc == 1, f"{command} ../x: rc {rc} != 1"
        assert not (base / "x").exists(), f"{command}: path-escape wrote outside the .agenticdoc root"
    print("[VERIFY] command_path_escape: rc=1 escaped=false", flush=True)


def test_legal_names_are_accepted_by_every_command(tmp_path: pathlib.Path) -> None:
    module = _mod()
    legal = [case for case in COMMAND_CASES if case["code"] is None]
    checked = 0
    for case in legal:
        for command in COMMANDS:
            root = tmp_path / f"{case['id']}-{command}" / ".agenticdoc"
            root.mkdir(parents=True)
            # Seed the row so `release` (which only updates an existing row) is
            # exercised on the same footing as the other three commands.
            (root / "_index.parallel").write_text(
                f"| {case['key']} | idle | SPEC | — | — | — | 2026-10-12 00:00 |\n",
                encoding="utf-8",
            )
            rc, out = _run_command(module, root, command, case["key"])
            assert rc == 0, f"{command} {case['key']!r}: rc {rc} != 0"
            rows = module.read_index(root / "_index.parallel")
            if command == "get-claim":
                assert out.strip() == "—", f"get-claim on an unclaimed key printed {out!r}"
            assert [r["key"] for r in rows] == [case["key"]], (command, case["key"], rows)
            checked += 1
    print(f"[VERIFY] command_legal_accepted={checked}", flush=True)


def test_command_case_variant_normalizes_to_the_first_written_row(tmp_path: pathlib.Path) -> None:
    module = _mod()
    root = tmp_path / ".agenticdoc"
    root.mkdir()
    _seed_case_variant(root)

    rc, out = _run_command(module, root, "get-claim", "MW-KEY")
    assert rc == 0
    assert out.strip() == "other-host:4242", f"get-claim MW-KEY printed {out!r}"

    rc, _ = _run_command(module, root, "set-phase", "MW-KEY")
    assert rc == 0
    rows = module.read_index(root / "_index.parallel")
    assert [r["key"] for r in rows] == ["mw-key"], f"set-phase appended a case-variant row: {[r['key'] for r in rows]}"
    assert rows[0]["phase"] == "EXECUTE"

    rc, _ = _run_command(module, root, "set-meta", "MW-KEY")
    assert rc == 0
    rows = module.read_index(root / "_index.parallel")
    assert [r["key"] for r in rows] == ["mw-key"], f"set-meta appended a case-variant row: {[r['key'] for r in rows]}"
    assert rows[0]["desc"] == "cmd-desc"

    rc, _ = _run_command(module, root, "release", "MW-KEY")
    assert rc == 0
    rows = module.read_index(root / "_index.parallel")
    assert [r["key"] for r in rows] == ["mw-key"], f"release appended a case-variant row: {[r['key'] for r in rows]}"
    assert rows[0]["status"] == "idle"
    assert rows[0]["claim_id"] == "—"

    print(f"[VERIFY] command_case_variant: rows={len(rows)} stored={rows[0]['key']} duplicate=false", flush=True)


# ── T-16: caseVariantOf audit is observably consumed by takeOverKey ────────
#
# The `ClaimOutcome.caseVariantOf` field is only "observable" if a real caller
# consumes it. `takeOverKey` is that caller: every takeOverKey surface
# (/pm-key new, /pm-key switch, the switch_key tool, the pm-orchestrator
# doc-write auto-claim) already notifies `result.audit`, so the case-variant
# line rides the existing audit/alarm channel instead of a new one. This runs
# the real TS modules through node (fail-closed) and pins the field + the
# audit line + the single stored row (no migration, no duplicate).

_CASE_VARIANT_TS_SCRIPT = r"""
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

(async () => {
	const base = path.join(process.env.MW_T16_REPO, "packages/coding-agent/src/extensions/agent-team-loop");
	const storeMod = await import(pathToFileURL(path.join(base, "shared/index-store.ts")).href);
	const bridgeMod = await import(pathToFileURL(path.join(base, "pm/ui-bridge.ts")).href);
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mwgf-t16-audit-"));
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		"| mw-key | idle | SPEC | other-host:4242 |  |  | 2026-10-12T00:00:00Z |\n",
		"utf8",
	);
	const store = new storeMod.IndexStore(root);
	const outcome = await store.claim("MW-KEY", "probe:1", () => false, { force: true });
	const result = await bridgeMod.takeOverKey(store, "MW-KEY", true, root);
	const auditLine = result.audit.find((line) => line.includes("case-variant")) ?? null;
	const rows = store.readAll().map((row) => row.key);
	const out = { caseVariantOf: outcome.caseVariantOf ?? null, auditLine, rows };
	process.stdout.write("T16_JSON_BEGIN\n" + JSON.stringify(out) + "\nT16_JSON_END\n");
})().catch((error) => {
	console.error(error && error.stack ? error.stack : String(error));
	process.exit(1);
});
"""


def test_case_variant_audit_is_observable_through_take_over_key() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; the TS case-variant audit cannot be measured (fail-closed, P-016)")
    env = dict(**os.environ)
    env["MW_T16_REPO"] = str(_REPO)
    proc = subprocess.run(
        [node, "--experimental-strip-types", "-e", _CASE_VARIANT_TS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or "T16_JSON_BEGIN" not in proc.stdout or "T16_JSON_END" not in proc.stdout:
        pytest.fail(
            f"node case-variant audit harness failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    text = proc.stdout.split("T16_JSON_BEGIN", 1)[1].split("T16_JSON_END", 1)[0].strip()
    measured = json.loads(text)
    assert measured["caseVariantOf"] == "mw-key", measured
    assert measured["auditLine"] == "[KEY] case-variant 'MW-KEY' -> stored 'mw-key'", measured
    assert measured["rows"] == ["mw-key"], measured
    print(
        f"[VERIFY] case_variant_audit: field={measured['caseVariantOf']} caller_audit=1 rows={len(measured['rows'])}",
        flush=True,
    )
