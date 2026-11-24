"""
T-08 (mw-window-claim-isolation) dedicated Python framework fix regressions.

These tests are intentionally red against the T-02 terminal source. They cover
review findings 1..5/8/9 and T-05B F-02..F-05 with a strict split:
  * real child processes and the shared .mw/index.lock for the ensure/release
    interleavings (never a mock-only claim of concurrency);
  * in-process monkeypatches only for deterministic IO failure and CAS probes.

Run from repo root:
    python -m pytest packages/multi-workers/test_window_claim_python_fixes.py -q -rA
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / ".agents" / "skills" / "agentic-task" / "scripts" / "update_index.py"
HOST = socket.gethostname()
DASH = "\u2014"
PROJECTION_PREFIX = "# AgenticTask Index\n\nactive_keys: "


def _load():
    spec = importlib.util.spec_from_file_location("t08_update_index", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ui():
    return _load()


def row(key, status, claim_id, phase="SPEC", deps=DASH, desc=DASH,
        updated="2026-01-01 00:00"):
    return {"key": key, "status": status, "phase": phase, "claim_id": claim_id,
            "deps": deps, "desc": desc, "updated": updated}


def _project(tmp_path, name, with_mw=True):
    project = tmp_path / name / "proj"
    (project / ".agenticdoc").mkdir(parents=True)
    if with_mw:
        (project / ".mw").mkdir(parents=True)
    return project


def _adoc(project):
    return project / ".agenticdoc"


def _seed(ui, root, rows):
    (root / "_index.parallel").write_bytes(ui._serialize_rows(rows).encode("utf-8"))


def projection(root):
    path = root / "_index.md"
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def _stale(root, keys=("STALE",)):
    text = PROJECTION_PREFIX + json.dumps(list(keys)) + "\n"
    (root / "_index.md").write_bytes(text.encode("utf-8"))
    return text


def _quiet(fn, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*args, **kwargs)
    return rc, out.getvalue(), err.getvalue()


def _assert_clean(project):
    assert not (project / ".mw" / "index.lock").exists(), "shared index.lock was not released"
    leftovers = sorted(str(p.relative_to(project)) for p in project.rglob("*.tmp*"))
    assert leftovers == [], f"tmp leftovers: {leftovers}"


def _assert_cli_zero_write(project):
    root = _adoc(project)
    assert not (root / "_index.parallel").exists(), "argument error wrote the authority index"
    assert not (root / "_index.md").exists(), "argument error wrote the projection"
    assert not (root / "k").exists(), "argument error wrote the key mirror directory"
    assert not (project / ".mw").exists(), "argument error created the lock directory"


def _sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _write_script(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _wait_file(path, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def _signal(path):
    path.write_text("go", encoding="utf-8")


def _reap(proc):
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _communicate(proc, timeout=60):
    try:
        return proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _reap(proc)
        raise


_SLEEP_CHILD = """import time
time.sleep(30)
"""


def _dead_pid(tmp_path, tag):
    script = _write_script(tmp_path, tag + "-sleep.py", _SLEEP_CHILD)
    proc = subprocess.Popen([sys.executable, "-X", "utf8", str(script)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid = proc.pid
    proc.kill()
    proc.wait(timeout=10)
    return pid


_ENSURE_CHILD = r'''
import importlib.util, json, os, socket, sys, time
from pathlib import Path
script, root_s, key, marker_s, gate_s, result_s = sys.argv[1:7]
spec = importlib.util.spec_from_file_location("t08_ensure_ui", script)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
root, marker, gate, result = Path(root_s), Path(marker_s), Path(gate_s), Path(result_s)
real_is_file = Path.is_file
state = {"gated": False}

def gated_is_file(self):
    value = real_is_file(self)
    if not state["gated"] and self.name == "_index.parallel" and not value:
        state["gated"] = True
        marker.write_text(json.dumps({
            "pid": os.getpid(), "observedMissing": True,
            "phase": "ensure-check-done", "lockHeld": (root.parent / ".mw" / "index.lock").exists()
        }), encoding="utf-8")
        deadline = time.time() + 20
        while not gate.exists() and time.time() < deadline:
            time.sleep(0.02)
    return value

Path.is_file = gated_is_file
rc = ui.cmd_claim(root, key, False, claim_id=f"{socket.gethostname()}:{os.getpid()}")
result.write_text(json.dumps({"rc": rc, "pid": os.getpid(),
                              "gated": state["gated"]}), encoding="utf-8")
sys.exit(0 if rc == 0 else 3)
'''


_CLAIM_CHILD = r'''
import importlib.util, json, os, socket, sys
from pathlib import Path
script, root_s, key, cid, started_s, result_s = sys.argv[1:7]
spec = importlib.util.spec_from_file_location("t08_claim_ui", script)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
root, started, result = Path(root_s), Path(started_s), Path(result_s)
started.write_text(json.dumps({"pid": os.getpid(), "phase": "claim-started"}),
                   encoding="utf-8")
claim_id = None if cid == "-" else cid
rc = ui.cmd_claim(root, key, False, claim_id=claim_id)
result.write_text(json.dumps({"rc": rc, "pid": os.getpid(),
                              "claimId": claim_id or ui.now_claim_id()}),
                  encoding="utf-8")
sys.exit(0 if rc == 0 else 3)
'''


_RELEASE_CHILD = r'''
import contextlib, importlib.util, io, json, os, sys, time
from pathlib import Path
script, root_s, key, marker_s, gate_s, result_s = sys.argv[1:7]
spec = importlib.util.spec_from_file_location("t08_release_ui", script)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
root, marker, gate, result = Path(root_s), Path(marker_s), Path(gate_s), Path(result_s)
orig_prepare = ui._prepare_pm_state_claim
orig_update = ui._update_pm_state_claim
state = {"signaled": False}

def maybe_gate():
    if state["signaled"]:
        return
    state["signaled"] = True
    marker.write_text(json.dumps({
        "pid": os.getpid(), "phase": "mirror-commit-gate",
        "lockHeld": (root.parent / ".mw" / "index.lock").exists()
    }), encoding="utf-8")
    deadline = time.time() + 20
    while not gate.exists() and time.time() < deadline:
        time.sleep(0.02)

def gated_prepare(key_dir, claim_id):
    commit = orig_prepare(key_dir, claim_id)
    def gated_commit():
        maybe_gate()
        return commit()
    return gated_commit

def gated_update(key_dir, claim_id):
    maybe_gate()
    return orig_update(key_dir, claim_id)

ui._prepare_pm_state_claim = gated_prepare
ui._update_pm_state_claim = gated_update
out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    rc = ui.cmd_release(root, key)
result.write_text(json.dumps({"rc": rc, "stdout": out.getvalue(),
                              "stderr": err.getvalue(),
                              "signaled": state["signaled"]}), encoding="utf-8")
sys.exit(0 if rc == 0 else 3)
'''


def _popen_child(script, *args):
    return subprocess.Popen(
        [sys.executable, "-X", "utf8", str(script), *map(str, args)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )


# ── review #4 / T-05B F-02: validate projection BEFORE authority replace ────

def test_f02_illegal_active_key_zero_write_before_authority(ui, tmp_path):
    project = _project(tmp_path, "f02-illegal")
    root = _adoc(project)
    _seed(ui, root, [row("_index.parallel", "active", f"{HOST}:{os.getpid()}")])
    before = (root / "_index.parallel").read_bytes()
    stale = _stale(root)
    rc, _, err = _quiet(ui.cmd_set_phase, root, "legal-key", "EXECUTE")
    assert rc == 1
    assert "illegal active key" in err
    assert "zero" in err.lower()
    assert (root / "_index.parallel").read_bytes() == before, "authority was replaced after validation"
    assert "legal-key" not in (root / "_index.parallel").read_bytes().decode("utf-8")
    assert projection(root) == stale, "projection was written on refused data"
    assert not (root / "legal-key").exists(), "key mirror directory was created"
    _assert_clean(project)
    # A later mutation on repaired authority still rebuilds the projection.
    _seed(ui, root, [row("legal-key", "idle", DASH, phase="EXECUTE")])
    rc, _, _ = _quiet(ui.cmd_set_meta, root, "legal-key", "recovered", None)
    assert rc == 0
    assert projection(root) == PROJECTION_PREFIX + "[]\n"


@pytest.mark.parametrize("bad_line,expected_fragment", [
    ("| broken | active |", "unparsed active row"),
    ("| broken | idle |", "untrusted table row"),
])
def test_f02_untrusted_structure_zero_write_before_full_table_rewrite(
        ui, tmp_path, bad_line, expected_fragment):
    project = _project(tmp_path, "f02-structure-" + str(abs(hash(bad_line))))
    root = _adoc(project)
    lines = ui._serialize_rows([row("anchor", "idle", DASH)]).splitlines()
    lines.insert(2, bad_line)
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    (root / "_index.parallel").write_bytes(raw)
    stale = _stale(root)
    rc, _, err = _quiet(ui.cmd_set_phase, root, "anchor", "PLAN")
    assert rc == 1
    assert expected_fragment in err
    assert "zero" in err.lower()
    assert (root / "_index.parallel").read_bytes() == raw, "unparsed row was silently dropped"
    assert projection(root) == stale
    assert not (root / "anchor").exists()
    _assert_clean(project)


# ── review #1 / T-05B F-03: first-create ensure inside the shared lock ─────

def test_f03_ensure_first_create_race_both_real_children_survive(ui, tmp_path):
    project = _project(tmp_path, "f03-ensure")
    root = _adoc(project)
    tag = tmp_path / "f03"
    ensure_script = _write_script(tmp_path, "f03-ensure-child.py", _ENSURE_CHILD)
    claim_script = _write_script(tmp_path, "f03-claim-child.py", _CLAIM_CHILD)
    marker = tag.with_name("f03-marker.json")
    gate = tag.with_name("f03-gate")
    result_a = tag.with_name("f03-result-a.json")
    started_b = tag.with_name("f03-started-b.json")
    result_b = tag.with_name("f03-result-b.json")
    child_a = _popen_child(ensure_script, _SCRIPT, root, "key-a", marker, gate, result_a)
    child_b = None
    try:
        _wait_file(marker)
        seen = json.loads(marker.read_text(encoding="utf-8"))
        assert seen["observedMissing"] is True
        child_b = _popen_child(claim_script, _SCRIPT, root, "key-b", "-", started_b, result_b)
        _wait_file(started_b)
        time.sleep(0.5)
        blocked = child_b.poll() is None
        lock_held = (project / ".mw" / "index.lock").exists()
        _signal(gate)
        out_a, err_a = _communicate(child_a)
        out_b, err_b = _communicate(child_b)
        assert child_a.returncode == 0, (out_a, err_a)
        assert child_b.returncode == 0, (out_b, err_b)
        rows = ui.read_index(root / "_index.parallel")
        assert {r["key"] for r in rows} == {"key-a", "key-b"}, [
            r["key"] for r in rows
        ]
        active = [r["key"] for r in rows if r["status"] == "active"]
        assert set(active) == {"key-a", "key-b"}
        assert json.loads(projection(root).split("active_keys: ", 1)[1]) == active
        assert blocked, "competing child did not queue on the shared index.lock"
        assert lock_held, "shared index.lock was not held during first-create ensure"
        _assert_clean(project)
    finally:
        if not gate.exists():
            _signal(gate)
        if child_b is not None:
            _reap(child_b)
        _reap(child_a)


# ── review #2 / T-05B F-04: release mirror commit inside the same lock ─────

def test_f04_release_mirror_race_preserves_later_claim(ui, tmp_path):
    project = _project(tmp_path, "f04-release")
    root = _adoc(project)
    dead_pid = _dead_pid(tmp_path, "f04-dead")
    assert ui._pid_is_gone(dead_pid)
    _seed(ui, root, [row("k", "active", f"{HOST}:{dead_pid}")])
    stale = _stale(root)
    key_dir = root / "k"
    key_dir.mkdir()
    (key_dir / "pm-state.md").write_text(
        "# PM State: k\n- Key: k\n- Claim-Id: old-id\n- Phase: init\n",
        encoding="utf-8",
    )
    tag = tmp_path / "f04"
    release_script = _write_script(tmp_path, "f04-release-child.py", _RELEASE_CHILD)
    claim_script = _write_script(tmp_path, "f04-claim-child.py", _CLAIM_CHILD)
    marker = tag.with_name("f04-marker.json")
    gate = tag.with_name("f04-gate")
    result_a = tag.with_name("f04-result-a.json")
    started_b = tag.with_name("f04-started-b.json")
    result_b = tag.with_name("f04-result-b.json")
    new_claim = f"{HOST}:{os.getpid()}"
    child_a = _popen_child(release_script, _SCRIPT, root, "k", marker, gate, result_a)
    child_b = None
    try:
        _wait_file(marker)
        child_b = _popen_child(claim_script, _SCRIPT, root, "k", new_claim, started_b, result_b)
        _wait_file(started_b)
        time.sleep(0.5)
        blocked = child_b.poll() is None
        lock_held = (project / ".mw" / "index.lock").exists()
        _signal(gate)
        out_a, err_a = _communicate(child_a)
        out_b, err_b = _communicate(child_b)
        assert child_a.returncode == 0, (out_a, err_a)
        assert child_b.returncode == 0, (out_b, err_b)
        rows = ui.read_index(root / "_index.parallel")
        assert len(rows) == 1
        assert rows[0]["status"] == "active" and rows[0]["claim_id"] == new_claim
        assert projection(root) == PROJECTION_PREFIX + '["k"]' + "\n", (stale, projection(root))
        pm_text = (key_dir / "pm-state.md").read_text(encoding="utf-8")
        assert f"- Claim-Id: {new_claim}" in pm_text, pm_text
        assert DASH not in pm_text, "release mirror overwrote the later claim"
        assert blocked, "claim did not queue behind the release's in-lock mirror"
        assert lock_held, "shared index.lock was not held during mirror commit"
        _assert_clean(project)
    finally:
        if not gate.exists():
            _signal(gate)
        if child_b is not None:
            _reap(child_b)
        _reap(child_a)


# ── review #3 / T-05B F-05: mirror IO failure still tries projection ───────

def test_f05_mirror_commit_failure_projects_and_reports_exact_partial(ui, tmp_path, monkeypatch):
    project = _project(tmp_path, "f05-mirror")
    root = _adoc(project)
    stale = _stale(root)
    error_text = "simulated pm-state mirror commit failure (T-08)"

    def bad_prepare(key_dir, claim_id):
        def commit():
            raise OSError(error_text)
        return commit

    with monkeypatch.context() as patch:
        patch.setattr(ui, "_prepare_pm_state_claim", bad_prepare)
        rc, _, err = _quiet(ui.cmd_claim, root, "k-mirror", False,
                            claim_id=f"{HOST}:{os.getpid()}")
    assert rc == 1
    assert "PARTIAL write" in err
    assert error_text in err
    assert "pm-state mirror: NOT written" in err
    assert "_index.md active_keys projection: refreshed successfully" in err
    assert "authority may already reflect the change" in err
    assert "No cross-file atomic transaction" in err
    assert [r["key"] for r in ui.read_index(root / "_index.parallel")] == ["k-mirror"]
    assert projection(root) == PROJECTION_PREFIX + '["k-mirror"]' + "\n"
    assert not (root / "k-mirror" / "pm-state.md").exists()
    _assert_clean(project)
    # Next successful mutation is a real recovery path, not an assertion-only claim.
    rc, _, err = _quiet(ui.cmd_set_meta, root, "k-mirror", "recovered", None)
    assert rc == 0, err
    assert projection(root) == PROJECTION_PREFIX + '["k-mirror"]' + "\n"


def test_f05_mirror_and_projection_failures_both_reported(ui, tmp_path, monkeypatch):
    project = _project(tmp_path, "f05-both")
    root = _adoc(project)
    stale = _stale(root)
    mirror_error = "simulated pm-state mirror commit failure (T-08 both)"
    projection_error = "simulated projection write failure (T-08 both)"

    def bad_prepare(key_dir, claim_id):
        def commit():
            raise OSError(mirror_error)
        return commit

    def bad_projection(md_path, rows, pid):
        raise ui._ProjectionFailed(ui._partial_failure_msg(projection_error))

    with monkeypatch.context() as patch:
        patch.setattr(ui, "_prepare_pm_state_claim", bad_prepare)
        patch.setattr(ui, "_write_projection", bad_projection)
        rc, _, err = _quiet(ui.cmd_claim, root, "k-both", False,
                            claim_id=f"{HOST}:{os.getpid()}")
    assert rc == 1
    assert "PARTIAL write" in err
    assert mirror_error in err
    assert projection_error in err
    assert "pm-state mirror: NOT written" in err
    assert "_index.md active_keys projection: NOT refreshed" in err
    assert "authority may already reflect the change" in err
    assert "No cross-file atomic transaction" in err
    assert [r["key"] for r in ui.read_index(root / "_index.parallel")] == ["k-both"]
    assert projection(root) == stale
    _assert_clean(project)
    rc, _, err = _quiet(ui.cmd_set_meta, root, "k-both", "recovered", None)
    assert rc == 0, err
    assert projection(root) == PROJECTION_PREFIX + '["k-both"]' + "\n"


# ── review #5: strict claim CLI parsing, zero writes before ensure ──────────

_CLI_BAD_CASES = (
    ("missing-claim-id", ("--claim-id",)),
    ("flag-as-claim-id", ("--claim-id", "--force")),
    ("flag-as-desc-value", ("--claim-id", "--desc", "text")),
    ("duplicate-claim-id", ("--claim-id", f"{HOST}:{os.getpid()}",
                            "--claim-id", "NO-SUCH-HOST:1")),
    ("duplicate-force", ("--force", "--force")),
    ("missing-desc", ("--desc",)),
    ("flag-as-deps-value", ("--deps", "--force")),
    ("unknown-flag", ("--bogus", "value")),
    ("extra-positional", ("extra",)),
)


def _run_cli(project, *args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(_SCRIPT), *args],
        cwd=str(project), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )


@pytest.mark.parametrize("name,bad_args", _CLI_BAD_CASES)
def test_f05_cli_invalid_claim_args_rc2_zero_write(tmp_path, name, bad_args):
    project = _project(tmp_path, "cli-" + name, with_mw=False)
    proc = _run_cli(project, "claim", "k", *bad_args)
    assert proc.returncode == 2, (name, proc.returncode, proc.stdout, proc.stderr)
    assert proc.stderr.strip(), "argument error produced no explanation"
    _assert_cli_zero_write(project)


def test_f05_cli_legal_desc_deps_force_and_claim_id(ui, tmp_path):
    project = _project(tmp_path, "cli-legal", with_mw=False)
    cid = f"{HOST}:{os.getpid()}"
    proc = _run_cli(project, "claim", "k", "--desc", "hello world",
                    "--deps", "dep-a,dep-b", "--force", "--claim-id", cid)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    root = _adoc(project)
    rows = ui.read_index(root / "_index.parallel")
    assert len(rows) == 1
    assert rows[0]["key"] == "k" and rows[0]["claim_id"] == cid
    assert rows[0]["desc"] == "hello world"
    assert rows[0]["deps"] == "dep-a,dep-b"
    assert projection(root) == PROJECTION_PREFIX + '["k"]' + "\n"
    assert (root / "k" / "pm-state.md").is_file()
    _assert_clean(project)


def test_f05_cli_default_claim_without_claim_id_remains_legal(ui, tmp_path):
    project = _project(tmp_path, "cli-default", with_mw=False)
    proc = _run_cli(project, "claim", "k")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    root = _adoc(project)
    rows = ui.read_index(root / "_index.parallel")
    assert len(rows) == 1 and rows[0]["key"] == "k"
    assert rows[0]["claim_id"].startswith(HOST + ":")
    assert projection(root) == PROJECTION_PREFIX + '["k"]' + "\n"


# ── review #8: duplicate normalized target is identity ambiguity ───────────

def test_f08_duplicate_normalized_claim_target_refused_zero_write(ui, tmp_path):
    project = _project(tmp_path, "f08-claim")
    root = _adoc(project)
    sleep_script = _write_script(tmp_path, "f08-holder.py", _SLEEP_CHILD)
    holder = subprocess.Popen([sys.executable, "-X", "utf8", str(sleep_script)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        foreign = f"{HOST}:{holder.pid}"
        assert not ui._pid_is_gone(holder.pid)
        _seed(ui, root, [row("K", "idle", DASH), row("k", "active", foreign)])
        before = (root / "_index.parallel").read_bytes()
        stale = _stale(root)
        rc, _, err = _quiet(ui.cmd_claim, root, "K", False,
                            claim_id=f"{HOST}:{os.getpid()}")
        assert rc == 1
        assert "AMBIGUOUS" in err or "duplicate" in err.lower()
        assert (root / "_index.parallel").read_bytes() == before
        assert not (root / "K" / "pm-state.md").exists()
        assert not (root / "k" / "pm-state.md").exists()
        assert projection(root) == stale
        _assert_clean(project)
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_f08_duplicate_normalized_release_target_refused_zero_write(ui, tmp_path):
    project = _project(tmp_path, "f08-release")
    root = _adoc(project)
    cid = f"{HOST}:{os.getpid()}"
    _seed(ui, root, [row("K", "active", cid), row("k", "active", cid)])
    before = (root / "_index.parallel").read_bytes()
    stale = _stale(root, ["STALE"])
    rc, _, err = _quiet(ui.cmd_release, root, "K")
    assert rc == 1
    assert "AMBIGUOUS" in err or "duplicate" in err.lower()
    assert (root / "_index.parallel").read_bytes() == before
    assert projection(root) == stale
    _assert_clean(project)


def test_f08_projection_still_deduplicates_pure_active_set(ui, tmp_path):
    project = _project(tmp_path, "f08-dedup")
    root = _adoc(project)
    cid = f"{HOST}:{os.getpid()}"
    _seed(ui, root, [row("MW-Key", "active", cid),
                     row("mw-key", "active", "other-host:1"),
                     row("z-last", "active", cid)])
    rc, _, err = _quiet(ui.cmd_set_phase, root, "z-last", "PLAN")
    assert rc == 0, err
    assert projection(root) == PROJECTION_PREFIX + '["MW-Key", "z-last"]' + "\n"
    _assert_clean(project)


# ── review #9: final CAS mtime change refuses replace and cleans tmp/lock ──

def test_f09_final_cas_mtime_change_refuses_authority_replace(ui, tmp_path, monkeypatch):
    project = _project(tmp_path, "f09-cas")
    root = _adoc(project)
    _seed(ui, root, [row("k", "idle", DASH)])
    before = (root / "_index.parallel").read_bytes()
    stale = _stale(root)
    real_read = ui.read_index
    real_replace = ui.os.replace
    base_ns = 1_700_000_000_000_000_000
    state = {"reads": 0, "authority_replaces": 0}

    def changing_read(path):
        state["reads"] += 1
        stamp = base_ns + state["reads"] * 1_000_000_000
        os.utime(path, ns=(stamp, stamp))
        return real_read(path)

    def counting_replace(src, dst, *args, **kwargs):
        if pathlib.Path(dst).name == "_index.parallel":
            state["authority_replaces"] += 1
        return real_replace(src, dst, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(ui, "read_index", changing_read)
        patch.setattr(ui.os, "replace", counting_replace)
        rc, _, err = _quiet(ui.cmd_set_phase, root, "k", "PLAN")
    assert rc == 1
    assert "final CAS" in err or "refused" in err.lower()
    assert state["reads"] == 3, state
    assert state["authority_replaces"] == 0, "final CAS overwrote the authority"
    assert (root / "_index.parallel").read_bytes() == before
    assert projection(root) == stale
    _assert_clean(project)


# ── mirror parity remains a hard gate after the fix ────────────────────────

def test_t08_reachable_script_mirrors_are_byte_identical():
    paths = [
        ".agents/skills/agentic-task/scripts/update_index.py",
        ".agents/skills/agentic-task/core/scripts/update_index.py",
        ".agents/skills/agentic-task/claude/scripts/update_index.py",
        ".claude/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/core/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/claude/scripts/update_index.py",
    ]
    hashes = {(_REPO / p): _sha(_REPO / p) for p in paths}
    assert all((_REPO / p).is_file() for p in paths)
    assert len(set(hashes.values())) == 1, hashes
    assert len(hashes) == 7
