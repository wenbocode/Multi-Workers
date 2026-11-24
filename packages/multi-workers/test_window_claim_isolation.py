"""
T-02 (mw-window-claim-isolation) Python acceptance tests.

Covers design D-001..006 for the Python half: window-local demote, in-lock
conflict re-validation, verified caller ClaimId bridge, complete active-key
index.md projection (exact frozen bytes), partial-write visibility/recovery,
real shared-lock competition, and reachable script-mirror hash parity.

All tests are offline (temp roots, real local live/dead pids, no model calls,
no production index). VC lines are printed ONLY after their assertions pass.

Run (from repo root):
    python -m pytest packages/multi-workers/test_window_claim_isolation.py -q
"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import threading

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_UPDATE_INDEX = _REPO / ".agents" / "skills" / "agentic-task" / "scripts" / "update_index.py"
HOST = socket.gethostname()
DASH = "\u2014"
PROJECTION_PREFIX = "# AgenticTask Index\n\nactive_keys: "


def _load():
    spec = importlib.util.spec_from_file_location("wci_update_index", _UPDATE_INDEX)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_MOD = None


def ui():
    global _MOD
    if _MOD is None:
        _MOD = _load()
    return _MOD


def row(key, status, claim_id, phase="SPEC", deps=DASH, desc=DASH,
        updated="2026-01-01 00:00"):
    return {"key": key, "status": status, "phase": phase, "claim_id": claim_id,
            "deps": deps, "desc": desc, "updated": updated}


def _seed(root, rows):
    (root / "_index.parallel").write_bytes(ui()._serialize_rows(rows).encode("utf-8"))


def projection(root):
    p = root / "_index.md"
    if not p.is_file():
        return None
    return p.read_bytes().decode("utf-8")


def _fresh_root(tmp_path, name):
    r = tmp_path / name / ".agenticdoc"
    r.mkdir(parents=True)
    return r


def _quiet_claim(root, key, force=False, claim_id=None):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return ui().cmd_claim(root, key, force, claim_id=claim_id)


def _quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture()
def root(tmp_path):
    r = tmp_path / ".agenticdoc"
    r.mkdir()
    return r


# ---------------------------------------------------------------------------
# VC-001 / VC-006: two windows coexist; A's row fields untouched by B's claim.
# Two VERIFIED caller identities: current process and its direct live parent.
# ---------------------------------------------------------------------------

def test_two_windows_coexist_and_a_row_unchanged(root):
    pid, ppid = os.getpid(), os.getppid()
    assert not ui()._pid_is_gone(pid) and not ui()._pid_is_gone(ppid)
    a = f"{HOST}:{pid}"
    b = f"{HOST}:{ppid}"
    assert a != b
    assert ui()._resolve_claim_id(a) == a
    assert ui()._resolve_claim_id(b) == b

    assert _quiet_claim(root, "key-a", claim_id=a) == 0
    a_row_after_a = dict(next(r for r in ui().read_index(root / "_index.parallel")
                              if r["key"] == "key-a"))
    assert _quiet_claim(root, "key-b", claim_id=b) == 0

    rows = {r["key"]: r for r in ui().read_index(root / "_index.parallel")}
    assert rows["key-a"]["status"] == "active" and rows["key-a"]["claim_id"] == a
    assert rows["key-b"]["status"] == "active" and rows["key-b"]["claim_id"] == b
    # A's row is byte-for-byte unchanged after B's claim (AC-001).
    assert rows["key-a"] == a_row_after_a
    assert projection(root) == PROJECTION_PREFIX + '["key-a", "key-b"]' + "\n"
    print("[VERIFY] VC-001: coexist=true", flush=True)


# ---------------------------------------------------------------------------
# VC-002 / VC-006: self-only demote of multiple own old rows; foreign and
# legacy rows keep every field; projection is the exact active set (row order).
# ---------------------------------------------------------------------------

def test_self_switch_demotes_only_own_rows(root):
    pid, ppid = os.getpid(), os.getppid()
    a = f"{HOST}:{pid}"
    b = f"{HOST}:{ppid}"
    _seed(root, [
        row("own-1", "active", a),
        row("own-2", "active", a, phase="DESIGN", desc="mine"),
        row("foreign", "active", "someone-else:4242", phase="EXECUTE", desc="keep"),
        row("legacy", "idle", "20260101-000000-1"),
        row("foreign-2", "active", b, phase="PLAN", desc="also-keep"),
    ])
    idx = root / "_index.parallel"
    before = {r["key"]: dict(r) for r in ui().read_index(idx)}
    assert _quiet_claim(root, "own-3", claim_id=a) == 0
    rows = {r["key"]: r for r in ui().read_index(idx)}
    assert rows["own-1"]["status"] == "idle"          # own demoted
    assert rows["own-2"]["status"] == "idle"          # multiple own old rows demoted
    assert rows["own-3"]["status"] == "active" and rows["own-3"]["claim_id"] == a
    # Foreign / legacy / other-window rows: every field unchanged (AC-002).
    for k in ("foreign", "legacy", "foreign-2"):
        assert rows[k] == before[k], k
    active = [r["key"] for r in ui().read_index(idx) if r["status"] == "active"]
    assert active == ["foreign", "foreign-2", "own-3"]
    assert projection(root) == PROJECTION_PREFIX + json.dumps(active) + "\n"
    print("[VERIFY] VC-002: demote_scope=self", flush=True)
    print("[VERIFY] VC-006: projection_exact=true", flush=True)


# ---------------------------------------------------------------------------
# VC-003: foreign active LIVE target -> conflict with ZERO writes (index,
# target pm-state, projection); stale local target takeover without force;
# self reclaim allowed; force is explicit and still works.
# ---------------------------------------------------------------------------

def test_foreign_live_conflict_zero_writes(root):
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        foreign = f"{HOST}:{holder.pid}"
        assert not ui()._pid_is_gone(holder.pid)  # a genuinely LIVE foreign process
        _seed(root, [row("target", "active", foreign, phase="EXECUTE", desc="keep")])
        before_index = (root / "_index.parallel").read_bytes()
        stale_projection = PROJECTION_PREFIX + '["STALE"]' + "\n"
        (root / "_index.md").write_bytes(stale_projection.encode("utf-8"))

        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = ui().cmd_claim(root, "target", False)
        assert rc == 1
        assert "index.lock" in err.getvalue()          # re-validated under the shared lock
        assert "CONFLICT" in err.getvalue()
        assert (root / "_index.parallel").read_bytes() == before_index  # ZERO index write
        assert not (root / "target" / "pm-state.md").exists()          # ZERO target pm-state
        assert projection(root) == stale_projection                     # ZERO projection write
        print("[VERIFY] VC-003: conflict_zero_write=true", flush=True)
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_self_reclaim_stale_and_force(root):
    pid = os.getpid()
    self_id = f"{HOST}:{pid}"
    # self reclaim: active row held by the caller's own verified id -> allowed.
    _seed(root, [row("k", "active", self_id)])
    assert _quiet_claim(root, "k", claim_id=self_id) == 0
    assert ui().read_index(root / "_index.parallel")[0]["claim_id"] == self_id

    # stale local claim (dead pid) -> takeover WITHOUT --force.
    dead = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    dead_pid = dead.pid
    dead.kill()
    dead.wait(timeout=10)
    assert ui()._pid_is_gone(dead_pid)
    _seed(root, [row("k", "active", f"{HOST}:{dead_pid}")])
    assert _quiet_claim(root, "k") == 0

    # foreign live -> conflict without force; explicit force takes over.
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _seed(root, [row("k", "active", f"{HOST}:{holder.pid}")])
        assert _quiet_claim(root, "k", False) == 1
        assert _quiet_claim(root, "k", True) == 0
        assert ui().read_index(root / "_index.parallel")[0]["status"] == "active"
        print("[VERIFY] VC-003: self_reclaim_stale_force=true", flush=True)
    finally:
        holder.terminate()
        holder.wait(timeout=10)


# ---------------------------------------------------------------------------
# VC-009: caller bridge. current + direct parent accepted; foreign window,
# cross-host, dead pid, distant ancestor (no ancestor walk), garbage strings
# refused BEFORE any write/ensure (ZERO writes).
# ---------------------------------------------------------------------------

def test_bridge_current_parent_accepted_and_writes(root, tmp_path):
    pid, ppid = os.getpid(), os.getppid()
    for cid in (f"{HOST}:{pid}", f"{HOST}:{ppid}"):
        assert ui()._resolve_claim_id(cid) == cid
    assert _quiet_claim(root, "k-bridge", claim_id=f"{HOST}:{pid}") == 0
    rows = ui().read_index(root / "_index.parallel")
    assert rows[0]["claim_id"] == f"{HOST}:{pid}"
    assert projection(root) == PROJECTION_PREFIX + '["k-bridge"]' + "\n"
    print("[VERIFY] VC-009: current_parent_bridge_accepted=true", flush=True)


def test_bridge_forgery_rejected_with_zero_writes(tmp_path):
    pid = os.getpid()
    # A live foreign window pid (also stands in as a "distant ancestor": it is
    # neither this process nor its direct parent -> no ancestor walk).
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    # A dead pid.
    dead = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    dead_pid = dead.pid
    dead.kill()
    dead.wait(timeout=10)
    try:
        assert not ui()._pid_is_gone(foreign.pid)
        assert ui()._pid_is_gone(dead_pid)
        bad_cases = [
            "garbage",                       # no host:pid
            f"host:{pid}:extra",             # malformed, extra colon
            f"{HOST}:0",                     # zero pid (not positive)
            f"{HOST}:-3",                    # negative
            f"{HOST}:abc",                  # non-numeric
            f"NO-SUCH-HOST:{pid}",          # cross-host
            f"{HOST}:{foreign.pid}",        # foreign live window / distant ancestor
            f"{HOST}:{dead_pid}",           # dead pid
        ]
        for i, bad in enumerate(bad_cases):
            r = _fresh_root(tmp_path, f"case-{i}")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = ui().cmd_claim(r, "k", False, claim_id=bad)
            assert rc == 1, bad
            assert "refused --claim-id" in err.getvalue(), bad
            # ZERO writes: no _index.parallel, no pm-state, no _index.md, no .mw
            assert list(r.iterdir()) == [], (bad, list(r.iterdir()))
            assert not (r.parent / ".mw").exists(), bad
        print("[VERIFY] VC-009: forgery_zero_write=true", flush=True)
    finally:
        foreign.terminate()
        foreign.wait(timeout=10)


def test_bridge_dead_parent_pid_refused(monkeypatch):
    # Point the "direct parent" at a genuinely dead pid: the liveness guard
    # must still refuse (defense beyond the getpid/getppid membership check).
    dead = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    dead_pid = dead.pid
    dead.kill()
    dead.wait(timeout=10)
    assert ui()._pid_is_gone(dead_pid)
    monkeypatch.setattr(os, "getppid", lambda: dead_pid)
    with pytest.raises(ui()._ClaimRejected):
        ui()._resolve_claim_id(f"{HOST}:{dead_pid}")
    print("[VERIFY] VC-009: dead_parent_liveness_guard=true", flush=True)


# ---------------------------------------------------------------------------
# VC-004: REAL competition. A child process waits on the shared .mw/index.lock;
# while it waits a competing lock-holder inserts a foreign LIVE claim; after the
# lock is released the child re-reads FRESH rows inside the lock and rejects.
# ---------------------------------------------------------------------------

_CHILD = r'''
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("wci_child_ui", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root, key = Path(sys.argv[2]), sys.argv[3]
force = len(sys.argv) > 4 and sys.argv[4] == "force"
cid = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "-" else None
sys.exit(m.cmd_claim(root, key, force, claim_id=cid))
'''


def _child(root, key, force=False, claim_id=None):
    argv = [sys.executable, "-X", "utf8", "-c", _CHILD, str(_UPDATE_INDEX),
            str(root), key, "force" if force else "noforce", claim_id or "-"]
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")


def test_lock_wait_then_conflict_revalidated_inside_lock(root, tmp_path):
    _seed(root, [])  # authoritative table exists -> child _ensure_index is a no-op
    lock_dir = root.parent / ".mw"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "index.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)  # hold the REAL shared lock

    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        foreign = f"{HOST}:{holder.pid}"
        assert not ui()._pid_is_gone(holder.pid)
        child = _child(root, "k")
        try:
            import time as _t
            _t.sleep(0.4)
            assert child.poll() is None  # genuinely blocked on the shared lock
            # Competing writer (we hold the lock) inserts a foreign LIVE claim.
            _seed(root, [row("k", "active", foreign, phase="EXECUTE", desc="keep")])
            before = (root / "_index.parallel").read_bytes()
            lock_path.unlink()  # release the lock; the child now proceeds
            out, err = child.communicate(timeout=30)
            assert child.returncode == 1
            assert "index.lock" in err and "CONFLICT" in err
            assert (root / "_index.parallel").read_bytes() == before  # ZERO index write
            assert not (root / "k" / "pm-state.md").exists()          # ZERO pm-state
            assert not (root / "_index.md").exists()                   # ZERO projection
            print(f"[RACE] lock_wait: child_blocked_on_shared_lock=True "
                  f"foreign_live_pid={holder.pid} child_rc={child.returncode} "
                  "index_bytes_unchanged=True pm_state_written=False "
                  "projection_written=False", flush=True)
            print("[VERIFY] VC-004: locked_recheck=true", flush=True)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            if lock_path.exists():
                lock_path.unlink()
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_two_real_processes_different_keys_coexist(root):
    _seed(root, [])
    c1 = _child(root, "k-one")
    c2 = _child(root, "k-two")
    o1, e1 = c1.communicate(timeout=30)
    o2, e2 = c2.communicate(timeout=30)
    assert c1.returncode == 0 and c2.returncode == 0, (e1, e2)
    rows = {r["key"]: r for r in ui().read_index(root / "_index.parallel")}
    # Each child has a distinct short-lived pid ClaimId; self-only demote must
    # NOT demote the other window's row, so both survive the shared lock.
    assert rows["k-one"]["status"] == "active"
    assert rows["k-two"]["status"] == "active"
    assert rows["k-one"]["claim_id"] != rows["k-two"]["claim_id"]
    active = [r["key"] for r in ui().read_index(root / "_index.parallel")
              if r["status"] == "active"]
    assert sorted(active) == ["k-one", "k-two"]
    assert projection(root) == PROJECTION_PREFIX + json.dumps(active) + "\n"
    print(f"[RACE] two_processes: rc=({c1.returncode},{c2.returncode}) "
          f"active={active} distinct_claim_ids=True shared_lock=True", flush=True)
    print("[VERIFY] VC-004: distinct_keys_coexist_locked=true", flush=True)


# ---------------------------------------------------------------------------
# VC-006: projection exact for 0/1/N active across claim / set-phase /
# set-meta / release, and the _ensure_index boundary (ensure NEVER writes
# _index.md; an existing active table is never wiped to [] by a bare ensure).
# ---------------------------------------------------------------------------

def test_projection_all_mutations_and_ensure_boundary(root):
    idx = root / "_index.parallel"
    ui()._ensure_index(idx)
    assert not (root / "_index.md").exists()          # ensure writes NO projection

    pid, ppid = os.getpid(), os.getppid()
    a = f"{HOST}:{pid}"
    b = f"{HOST}:{ppid}"
    assert _quiet_claim(root, "ka", claim_id=a) == 0
    assert projection(root) == PROJECTION_PREFIX + '["ka"]' + "\n"          # 1 active
    assert _quiet_claim(root, "kb", claim_id=b) == 0
    assert projection(root) == PROJECTION_PREFIX + '["ka", "kb"]' + "\n"    # 2 active

    # set-phase / set-meta do not change the active set.
    assert _quiet(ui().cmd_set_phase, root, "ka", "EXECUTE") == 0
    assert projection(root) == PROJECTION_PREFIX + '["ka", "kb"]' + "\n"
    assert _quiet(ui().cmd_set_meta, root, "kb", "desc-x", None) == 0
    assert projection(root) == PROJECTION_PREFIX + '["ka", "kb"]' + "\n"

    # A bare ensure on an existing active table does NOT wipe the projection.
    ui()._ensure_index(idx)
    assert projection(root) == PROJECTION_PREFIX + '["ka", "kb"]' + "\n"

    assert _quiet(ui().cmd_release, root, "ka") == 0
    assert projection(root) == PROJECTION_PREFIX + '["kb"]' + "\n"          # 1 active
    assert _quiet(ui().cmd_release, root, "kb") == 0
    assert projection(root) == PROJECTION_PREFIX + "[]" + "\n"               # 0 active
    # set-phase on a fresh idle key keeps it empty.
    assert _quiet(ui().cmd_set_phase, root, "kc", "SPEC") == 0
    assert projection(root) == PROJECTION_PREFIX + "[]" + "\n"
    print("[VERIFY] VC-006: projection_exact_0_1_N=true", flush=True)


def test_projection_illegal_active_key_fails_closed(root):
    # T-08 contract correction: the old expectation allowed the authority to be
    # replaced before an illegal active key was detected, then called that a
    # recoverable PARTIAL write. That violated D-005/D-002: invalid new_rows
    # projection text must be validated BEFORE any authority/mirror/projection
    # write. The old expectation was a design violation, not a green baseline.
    _seed(root, [row("_index.parallel", "active", f"{HOST}:{os.getpid()}")])
    before = (root / "_index.parallel").read_bytes()
    stale = PROJECTION_PREFIX + '["STALE"]' + "\n"
    (root / "_index.md").write_bytes(stale.encode("utf-8"))
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        rc = ui().cmd_set_phase(root, "legal-key", "EXECUTE")
    assert rc == 1
    msg = err.getvalue()
    assert "illegal active key" in msg
    assert "zero" in msg.lower()
    assert "PARTIAL write" not in msg  # no authority was written, so no partial exists
    assert (root / "_index.parallel").read_bytes() == before
    assert "legal-key" not in (root / "_index.parallel").read_bytes().decode("utf-8")
    assert projection(root) == stale
    assert not (root / "legal-key").exists()
    # Recovery: repair the authority and confirm the next mutation rebuilds the
    # exact projection. This remains a recovery path, not a retroactive approval
    # of the old post-authority validation order.
    _seed(root, [row("legal-key", "idle", DASH, phase="EXECUTE")])
    assert _quiet(ui().cmd_set_meta, root, "legal-key", "d", None) == 0
    assert projection(root) == PROJECTION_PREFIX + "[]" + "\n"
    print("[VERIFY] VC-006: illegal_active_key_zero_write_recovered=true", flush=True)


def test_partial_projection_failure_visible_and_recovered(root, monkeypatch):
    _seed(root, [row("key-a", "active", f"{HOST}:{os.getpid()}")])
    real = ui()._write_projection
    calls = {"n": 0}

    def fail_once(md_path, rows, pid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ui()._ProjectionFailed(ui()._partial_failure_msg("simulated disk error"))
        return real(md_path, rows, pid)

    monkeypatch.setattr(ui(), "_write_projection", fail_once)
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        rc = ui().cmd_set_phase(root, "key-a", "EXECUTE")
    assert rc == 1
    assert "PARTIAL write" in err.getvalue()
    assert "authority may already reflect the change" in err.getvalue()
    # Authority was written; projection was not.
    assert ui().read_index(root / "_index.parallel")[0]["phase"] == "EXECUTE"
    assert not (root / "_index.md").exists()
    # A later successful mutation rebuilds the projection (no rollback needed).
    assert _quiet(ui().cmd_set_meta, root, "key-a", "recovered", None) == 0
    assert projection(root) == PROJECTION_PREFIX + '["key-a"]' + "\n"
    print("[VERIFY] VC-006: partial_write_visible_recovered=true", flush=True)


def test_projection_dedup_keeps_first_active_spelling_and_row_order(root):
    # Duplicate active rows (case variants) collapse by normalize_key, keeping
    # the FIRST active row's original spelling; order follows _index.parallel.
    cid = f"{HOST}:{os.getpid()}"
    _seed(root, [
        row("MW-Key", "active", cid),
        row("mw-key", "active", "someone-else:1"),  # same normalized key, 2nd
        row("z-last", "active", cid),
        row("idle-one", "idle", DASH),
    ])
    # Trigger a mutation through the shared write point to (re)build projection.
    assert _quiet(ui().cmd_set_phase, root, "z-last", "PLAN") == 0
    active = [r["key"] for r in ui().read_index(root / "_index.parallel")
              if r["status"] == "active"]
    expected = []
    seen = set()
    for k in active:
        nk = ui().normalize_key(k)
        if nk not in seen:
            seen.add(nk)
            expected.append(k)
    assert expected == ["MW-Key", "z-last"]
    assert projection(root) == PROJECTION_PREFIX + json.dumps(expected) + "\n"
    print("[VERIFY] VC-006: projection_dedup_order=true", flush=True)


# ---------------------------------------------------------------------------
# VC-008: reachable script mirrors are byte-identical (canonical junction
# paths + nested-git physical copies + installed .claude copy).
# ---------------------------------------------------------------------------

def _sha(p):
    import hashlib
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def test_script_mirrors_hash_parity():
    update_paths = [
        ".agents/skills/agentic-task/scripts/update_index.py",
        ".agents/skills/agentic-task/core/scripts/update_index.py",
        ".agents/skills/agentic-task/claude/scripts/update_index.py",
        ".claude/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/core/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/claude/scripts/update_index.py",
    ]
    test_paths = [
        ".agents/skills/agentic-task/scripts/test_update_index.py",
        ".agents/skills/agentic-task/core/scripts/test_update_index.py",
        ".agents/skills/agentic-task/claude/scripts/test_update_index.py",
        ".claude/scripts/test_update_index.py",
        "packages/multi-workers/.tmp/agentic-task/scripts/test_update_index.py",
        "packages/multi-workers/.tmp/agentic-task/core/scripts/test_update_index.py",
        "packages/multi-workers/.tmp/agentic-task/claude/scripts/test_update_index.py",
    ]
    for label, paths in (("update_index.py", update_paths),
                         ("test_update_index.py", test_paths)):
        for p in paths:
            assert (_REPO / p).is_file(), p
        hashes = {_sha(_REPO / p) for p in paths}
        assert len(hashes) == 1, (label, hashes)
    print("[VERIFY] VC-008: entrances_aligned=true mirrors=7+7", flush=True)


# ---------------------------------------------------------------------------
# Frozen CLI entry: --claim-id is parsed and validated through the same choke
# point (real short-lived CLI process, NOT claimed to be a live window binding).
# ---------------------------------------------------------------------------

def test_cli_claim_id_param_end_to_end(tmp_path):
    r = tmp_path / "proj" / ".agenticdoc"
    r.mkdir(parents=True)
    # A live process whose pid is a valid *parent* of the CLI child is not
    # predictable, so drive the CLI with a forbidden --claim-id: it must be
    # refused with ZERO writes (proves the param is wired and validated).
    child = subprocess.run(
        [sys.executable, "-X", "utf8", str(_UPDATE_INDEX), "claim", "k",
         "--claim-id", "NO-SUCH-HOST:12345"],
        cwd=str(tmp_path / "proj"), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    assert child.returncode == 1
    assert "refused --claim-id" in (child.stderr or "")
    assert not (r / "_index.parallel").exists()  # ZERO writes, before ensure
    print("[VERIFY] VC-009: cli_claim_id_validated=true", flush=True)
