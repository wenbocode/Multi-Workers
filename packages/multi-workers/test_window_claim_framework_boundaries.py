"""
T-17 (mw-window-claim-isolation) — Python framework raw-row strictness regressions.

Independent, self-contained regression for the PM-reproduced N1/N2/Key-data
findings (evidence/final-findings/pm-preflight-20261112-1842.md):

  N1  bare / missing-leading-or-trailing-pipe "active" rows are silently
      dropped (or accepted non-canonically) by the full-table rewrite;
  N2  6-column rows are mis-parsed as legacy 5-column (wrong claim_id/phase),
      8-column rows are truncated to 7 (extra column discarded);
  Key  a legal 7-column data row whose key is literally "Key" is mistaken for
      the header row, dropped, and omitted from the projection.

All assertions exercise the REAL cmd_claim / cmd_release / cmd_set_phase /
cmd_set_meta on private temp roots through the shared write choke point. NO
mock/monkeypatch of the parser or the validation predicate is used to obtain
green. Each refusal asserts a zero-write tree snapshot (content + mtime_ns +
directory), a released shared index.lock, and no leftover *.tmp* files.

Run from repo root:
    python -m pytest packages/multi-workers/test_window_claim_framework_boundaries.py -q -s
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import socket
import sys

import pytest

sys.dont_write_bytecode = True

_REPO = pathlib.Path(__file__).resolve().parents[2]
# Anchor canonical physical copy (task anchor). The three .agents/skills paths
# are junction aliases onto the .tmp/agentic-task tree; all 7 paths must stay
# byte-identical (asserted below).
_CANONICAL = (_REPO / "packages/multi-workers/.tmp/agentic-task/scripts/update_index.py")
HOST = socket.gethostname()
DASH = "\u2014"
PROJECTION_PREFIX = "# AgenticTask Index\n\nactive_keys: "

_PATHS_7 = [
    "packages/multi-workers/.tmp/agentic-task/scripts/update_index.py",
    "packages/multi-workers/.tmp/agentic-task/core/scripts/update_index.py",
    "packages/multi-workers/.tmp/agentic-task/claude/scripts/update_index.py",
    ".claude/scripts/update_index.py",
    ".agents/skills/agentic-task/scripts/update_index.py",
    ".agents/skills/agentic-task/core/scripts/update_index.py",
    ".agents/skills/agentic-task/claude/scripts/update_index.py",
]
_PHYSICAL_4 = [
    "packages/multi-workers/.tmp/agentic-task/scripts/update_index.py",
    "packages/multi-workers/.tmp/agentic-task/core/scripts/update_index.py",
    "packages/multi-workers/.tmp/agentic-task/claude/scripts/update_index.py",
    ".claude/scripts/update_index.py",
]
_HEADER_LINES = [
    "# Index Parallel",
    "",
    "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
    "|-----|--------|-------|---------|------|------|---------|",
]
_HEADER_ROW = "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |"


def _load():
    spec = importlib.util.spec_from_file_location("t17_boundaries_update_index", _CANONICAL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ui():
    return _load()


# ── fixture helpers (all writes are private OS-temp roots) ─────────────────

def _line(key, status, phase, claim, deps, desc, updated):
    return f"| {key} | {status} | {phase} | {claim} | {deps} | {desc} | {updated} |"


def _anchor_row():
    return _line("anchor", "idle", "SPEC", "-", "-", "desc", "2026-01-01 00:00")


def _seed_raw(root, data_lines, *, with_header=True):
    lines = (list(_HEADER_LINES) if with_header else []) + list(data_lines)
    (root / "_index.parallel").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _project(tmp_path, name):
    project = tmp_path / name / "proj"
    (project / ".agenticdoc").mkdir(parents=True)
    # Pre-create .mw so acquiring the shared index.lock does not add a directory
    # to the zero-write tree snapshot (the lock file itself is released).
    (project / ".mw").mkdir(parents=True)
    return project


def _root(project):
    return project / ".agenticdoc"


def _stale(root, keys=("STALE",)):
    text = PROJECTION_PREFIX + json.dumps(list(keys)) + "\n"
    (root / "_index.md").write_bytes(text.encode("utf-8"))
    return text


def projection(root):
    p = root / "_index.md"
    return p.read_bytes().decode("utf-8") if p.is_file() else None


def _snapshot(project):
    """Zero-write snapshot: relative path -> (sha256, mtime_ns, size)."""
    out = {}
    for p in sorted(project.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(project)).replace("\\", "/")
        if rel.endswith("index.lock"):
            continue
        st = p.stat()
        out[rel] = (hashlib.sha256(p.read_bytes()).hexdigest(),
                    st.st_mtime_ns, st.st_size)
    return out


def _assert_zero_write(project, before):
    assert _snapshot(project) == before, "refusal changed the tree (content/mtime/dir)"
    assert not (project / ".mw" / "index.lock").exists(), "shared index.lock not released"
    leftovers = sorted(str(p.relative_to(project)) for p in project.rglob("*.tmp*"))
    assert leftovers == [], f"tmp leftovers: {leftovers}"


def _assert_clean(project):
    assert not (project / ".mw" / "index.lock").exists(), "shared index.lock not released"
    leftovers = sorted(str(p.relative_to(project)) for p in project.rglob("*.tmp*"))
    assert leftovers == [], f"tmp leftovers: {leftovers}"


def _quiet(fn, *a, **k):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **k)
    return rc, out.getvalue(), err.getvalue()


def _run_command(ui, root, command, key):
    if command == "claim":
        return _quiet(ui.cmd_claim, root, key, False, claim_id=f"{HOST}:{os.getpid()}")
    if command == "release":
        return _quiet(ui.cmd_release, root, key)
    if command == "set-phase":
        return _quiet(ui.cmd_set_phase, root, key, "PLAN")
    if command == "set-meta":
        return _quiet(ui.cmd_set_meta, root, key, "d", None)
    raise AssertionError(command)


# ── N1 / N2 / header-masquerade: unsupported structures -> zero-write refusal ─

# Every line here is table-shaped but NOT a supported 5-/7-column framed row.
# Pre-fix these are either accepted/mis-parsed (rc 0) or silently dropped by the
# full-table rewrite; post-fix each must be refused BEFORE any write.
_BAD_LINES = [
    ("bare7-active", "lost | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00 |"),
    ("bare7-idle", "lost | idle | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00 |"),
    ("no-trailing-pipe", "| lost | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00"),
    ("six-active", "| lost | active | EXECUTE | foreign:1 | desc | EXTRA |"),
    ("eight-active", "| lost | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00 | EXTRA |"),
    ("keymasquerade-badshape", "| Key | idle |"),
    ("empty-first-cell", "|  | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00 |"),
]


@pytest.mark.parametrize("name,bad", _BAD_LINES, ids=[n for n, _ in _BAD_LINES])
def test_unsupported_row_zero_write_before_full_table_rewrite(ui, tmp_path, name, bad):
    project = _project(tmp_path, "m-" + name)
    root = _root(project)
    _seed_raw(root, [bad, _anchor_row()])
    stale = _stale(root)
    before = _snapshot(project)
    rc, out, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 1, (name, "unsupported row was accepted", rc, out, err)
    assert "refused" in err.lower() and "zero" in err.lower(), (name, err)
    # ZERO writes: index bytes (bad line must remain), projection, mirror dir.
    assert bad.encode() in (root / "_index.parallel").read_bytes(), (name, "raw row lost")
    assert projection(root) == stale, (name, "projection was written on refused data")
    assert not (root / "anchor").exists(), (name, "target mirror created")
    _assert_zero_write(project, before)
    print(f"[T17] matrix {name}: zero-write-refusal OK", flush=True)


# Already-hardened shapes (T-08/F-02) must keep being refused, not regress into
# silent decoration drops. These are controls: they pass both RED and GREEN.
@pytest.mark.parametrize("bad,kind", [
    ("| broken | active |", "unparsed active row"),
    ("| broken | idle |", "untrusted table row"),
])
def test_existing_f02_shapes_still_zero_write(ui, tmp_path, bad, kind):
    project = _project(tmp_path, "f02-" + str(abs(hash(bad))))
    root = _root(project)
    _seed_raw(root, [bad, _anchor_row()])
    stale = _stale(root)
    before = _snapshot(project)
    rc, out, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 1, (bad, rc, out, err)
    assert kind in err, (bad, err)
    _assert_zero_write(project, before)
    assert projection(root) == stale
    print(f"[T17] f02-control {kind}: zero-write-refusal OK", flush=True)


# ── shape rejection applies to the SAME write choke point for all 4 commands ─

@pytest.mark.parametrize("command", ["claim", "release", "set-phase", "set-meta"])
def test_shape_refusal_applies_to_claim_release_setphase_setmeta(ui, tmp_path, command):
    project = _project(tmp_path, "w-" + command)
    root = _root(project)
    bad = "| lost | active | EXECUTE | foreign:1 | desc | EXTRA |"  # 6 columns
    _seed_raw(root, [bad, _anchor_row()])  # 'anchor' is a valid, parseable target
    stale = _stale(root)
    before = _snapshot(project)
    rc, out, err = _run_command(ui, root, command, "anchor")
    assert rc == 1, (command, "bad shape reached the writer", rc, out, err)
    assert "zero" in err.lower(), (command, err)
    assert projection(root) == stale, (command, "projection written on refused data")
    _assert_zero_write(project, before)
    print(f"[T17] common-write-point {command}: zero-write-refusal OK", flush=True)


# ── N3 / Key-data: a legal 7-column "Key" row is DATA, not a header ─────────

def test_legal_keydata_active_row_preserved_and_projected(ui, tmp_path):
    project = _project(tmp_path, "keydata")
    root = _root(project)
    keyline = _line("Key", "active", "EXECUTE", "foreign:1", "-", "desc",
                    "2026-01-01 00:00")
    _seed_raw(root, [keyline, _anchor_row()])
    _stale(root)
    rc, out, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 0, (rc, out, err)
    raw_after = (root / "_index.parallel").read_bytes().decode("utf-8")
    assert keyline in raw_after, "legal | Key | active ... | row was dropped"
    # The ONE true header is still emitted exactly once as decoration; a
    # "Key"-first-column data row must not be duplicated/absorbed into it.
    assert raw_after.count(_HEADER_ROW) == 1, raw_after
    rows = ui.read_index(root / "_index.parallel")
    assert any(r["key"] == "Key" and r["status"] == "active" for r in rows), rows
    assert any(r["key"] == "anchor" and r["phase"] == "PLAN" for r in rows), rows
    assert projection(root) == PROJECTION_PREFIX + '["Key"]' + "\n", projection(root)
    _assert_clean(project)
    print("[T17] Key-data: row preserved + projected [\"Key\"] OK", flush=True)


# ── ORIGINAL active-name pre-validation: self-demote must not launder a bad row ─

def test_self_demote_illegal_active_cannot_evade_original_validation(ui, tmp_path):
    project = _project(tmp_path, "selfdemote")
    root = _root(project)
    self_cid = f"{HOST}:{os.getpid()}"  # REAL verified bridge to this process
    # A legal-SHAPE but out-of-bounds active key owned by 'self'. cmd_claim on a
    # different key would demote it to idle, so validating only new_rows would
    # let this bad ORIGINAL input through. It must be refused before any write.
    illegal = _line("_index.parallel", "active", "SPEC", self_cid, "-", "-",
                    "2026-01-01 00:00")
    _seed_raw(root, [illegal, _anchor_row()])
    stale = _stale(root)
    before = _snapshot(project)
    rc, out, err = _quiet(ui.cmd_claim, root, "newkey", False, claim_id=self_cid)
    assert rc == 1, (rc, out, err)
    assert "illegal active key" in err, err
    assert "zero" in err.lower(), err
    assert illegal.encode() in (root / "_index.parallel").read_bytes(), "raw row lost"
    assert projection(root) == stale
    assert not (root / "newkey").exists(), "target mirror created on refused data"
    _assert_zero_write(project, before)
    print("[T17] self-demote illegal-active: original pre-validation OK", flush=True)


# ── preserved contracts: 5/7 cols, header/title/separator/comments, 0/1/N, ──
#    foreign/empty/legacy ClaimId ─────────────────────────────────────────────

def test_precise_decorations_and_normal_header_success(ui, tmp_path):
    project = _project(tmp_path, "deco")
    root = _root(project)
    lines = list(_HEADER_LINES) + [
        "# a title/comment line",
        "# another comment | with a pipe",
        "prose line that is not a row and has no pipe",
        "",
        _line("k1", "active", "EXECUTE", "foreign:1", "-", "desc", "2026-01-01 00:00"),
        _line("k2", "idle", "SPEC", "-", "-", "desc", "2026-01-01 00:00"),
    ]
    (root / "_index.parallel").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    _stale(root)
    rc, out, err = _quiet(ui.cmd_set_phase, root, "k2", "PLAN")
    assert rc == 0, (rc, out, err)
    rows = ui.read_index(root / "_index.parallel")
    assert {r["key"] for r in rows} == {"k1", "k2"}, rows
    assert projection(root) == PROJECTION_PREFIX + '["k1"]' + "\n", projection(root)
    _assert_clean(project)
    print("[T17] precise decorations + normal header: success OK", flush=True)


def test_legal_five_column_legacy_row_preserved_and_projected(ui, tmp_path):
    project = _project(tmp_path, "legacy5")
    root = _root(project)
    legacy = "| legacy | active | oldhost:1 | legacy-desc | 2026-01-01 00:00 |"
    _seed_raw(root, [legacy, _anchor_row()])
    _stale(root)
    rc, out, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 0, (rc, out, err)
    rows = ui.read_index(root / "_index.parallel")
    assert {"legacy", "anchor"}.issubset({r["key"] for r in rows}), rows
    assert projection(root) == PROJECTION_PREFIX + '["legacy"]' + "\n", projection(root)
    _assert_clean(project)
    print("[T17] legal 5-col legacy: preserved + projected OK", flush=True)


@pytest.mark.parametrize("name,active_keys,expected", [
    ("zero", [], "[]"),
    ("one", ["ka"], '["ka"]'),
    ("many", ["ka", "kb", "kc"], '["ka", "kb", "kc"]'),
])
def test_0_1_N_projection_exact(ui, tmp_path, name, active_keys, expected):
    project = _project(tmp_path, "proj-" + name)
    root = _root(project)
    lines = [_line(k, "active", "EXECUTE", "foreign:1", "-", "desc",
                   "2026-01-01 00:00") for k in active_keys]
    lines.append(_anchor_row())
    _seed_raw(root, lines)
    _stale(root)
    rc, out, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 0, (name, rc, out, err)
    assert projection(root) == PROJECTION_PREFIX + expected + "\n", (name, projection(root))
    _assert_clean(project)
    print(f"[T17] projection {name}: {expected} OK", flush=True)


def test_foreign_empty_legacy_claimid_controls_preserved(ui, tmp_path):
    project = _project(tmp_path, "claimids")
    root = _root(project)
    rows = [
        _line("foreign-live", "active", "EXECUTE", "other-host:4242", "-", "keep",
              "2026-01-01 00:00"),
        _line("empty-claim", "active", "EXECUTE", "", "-", "keep", "2026-01-01 00:00"),
        _line("legacy-claim", "active", "EXECUTE", "20260101-000000-1", "-", "keep",
              "2026-01-01 00:00"),
        _anchor_row(),
    ]
    _seed_raw(root, rows)
    _stale(root)
    before = {r["key"]: (r["claim_id"], r["phase"], r["desc"], r["status"])
              for r in ui.read_index(root / "_index.parallel")}
    rc, out, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 0, (rc, out, err)
    after = {r["key"]: (r["claim_id"], r["phase"], r["desc"], r["status"])
             for r in ui.read_index(root / "_index.parallel")}
    for k in ("foreign-live", "empty-claim", "legacy-claim"):
        assert after[k] == before[k], (k, "claim_id/fields changed")
    assert projection(root) == PROJECTION_PREFIX + (
        '["foreign-live", "empty-claim", "legacy-claim"]') + "\n", projection(root)
    _assert_clean(project)
    print("[T17] foreign/empty/legacy ClaimId: preserved OK", flush=True)


def test_seven_path_hash_parity_and_four_physical_copies():
    hashes = {}
    for p in _PATHS_7:
        path = _REPO / p
        assert path.is_file(), p
        hashes[p] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(set(hashes.values())) == 1, hashes  # 7 reachable paths in sync
    inodes = {}
    for p in _PHYSICAL_4:
        inodes[p] = (_REPO / p).stat().st_ino
    assert len(set(inodes.values())) == 4, inodes  # 4 distinct physical copies
    print(f"[T17] 7-path sha256={next(iter(hashes.values()))[:12]} "
          "4 physical copies distinct OK", flush=True)
