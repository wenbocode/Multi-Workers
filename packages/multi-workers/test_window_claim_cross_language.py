"""T-12 post-fix: REAL cross-language integration acceptance (design contracts).

Offline runner for TS / framework Python / conductor Python writers. Every
subprocess is started with an argv list (no shell, no inline -c/-e scripts);
multi-line Node / Python helpers are materialised into a session-scoped OS temp
directory and deleted by the fixture. Node loads the PRODUCTION TypeScript
``shared/index-store.ts`` directly through ``--experimental-strip-types``, never
the stale ``dist`` bundle. All roots are temporary; no production index, model,
claim tool, decision service, sign-off or QG is touched. Product sources are
STRICTLY READ-ONLY here; only this test file and the T-12 postfix evidence are
written by the card.

T-05B measured five unfixed defects with 5 ``xfail(strict=True)`` markers. T-07
..T-10 changed the products, so those markers and the stale repro probes are
NOT valid post-fix evidence. Each of the five is now a POSITIVE CONTRACT test
using the real production entry, and every strict xfail was removed ONLY after
that contract was measured through a real subprocess:

  F-01  legal legacy 5-column rows: a writer either succeeds with the FULL
        active set preserved (exact projection), or refuses with ZERO writes;
        mixed bad-active rows make ALL THREE writers refuse with zero writes.
        D-002 pure set/normalize dedup stays; authority bytes are NOT required
        to be identical across writers. D-005 conductor non-target bytes have
        their own byte-exact assertion.
  F-02  an illegal active key makes all three writers refuse with ZERO writes.
  F-03  first creation is inside the shared lock: the instrument wraps ONLY
        the real O_CREAT|O_EXCL header-create IO (production exists/write logic
        intact) and two REAL processes must both keep their rows.
  F-04  the instrument wraps ONLY the real in-lock pm-state mirror commit
        (``_prepare_pm_state_claim``'s returned commit); a later claim must wait
        on the same lock and its mirror must survive.
  F-05  a mirror IO failure reports a clear PARTIAL write; the projection is
        still attempted/refreshed, and a later real mutation rebuilds it.

Retained from T-05B: 0/1/N three-writer byte comparison, real Node+Python
shared-lock races in both orders, winner alive until the loser's verdict, refused
tree snapshot zero-write, TS reader fail-closed, mirror hash parity (7 paths /
4 physical copies), cross-language partial-projection recovery. Added: same-self
reclaim and explicit low-level force in a temp root only (explicitly NOT a proof
of the tool's user-confirmation path).

Run (repo root):
    python -m pytest packages/multi-workers/test_window_claim_cross_language.py -q -s
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_PKG = _HERE
_TS_MODULE = _REPO / "packages" / "coding-agent" / "src" / "extensions" / "agent-team-loop" / "shared" / "index-store.ts"
_UPDATE_INDEX = _REPO / ".agents" / "skills" / "agentic-task" / "scripts" / "update_index.py"
_HOST = socket.gethostname()
_DASH = "\u2014"

_HEADER_LINES = [
    "# Index Parallel",
    "",
    "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
    "|-----|--------|-------|---------|------|------|---------|",
]


# ── Multi-line subprocess helpers (written to OS temp files, cleaned up) ─────

NODE_HELPER = r"""
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const argv = process.argv.slice(2);
const mode = argv[0];
const tsModule = argv[1];
const emit = (data) => { process.stdout.write('MWCL_JSON ' + JSON.stringify(data) + '\n'); };
const writeJson = (file, data) => { if (file && file !== '-') fs.writeFileSync(file, JSON.stringify(data), 'utf8'); };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function waitFor(file, timeoutMs = 90000) {
  if (!file || file === '-') return true;
  const deadline = Date.now() + timeoutMs;
  while (!fs.existsSync(file)) {
    if (Date.now() > deadline) throw new Error('timeout waiting for ' + file);
    await sleep(20);
  }
  return true;
}
function projectionText(root) {
  const p = path.join(root, '_index.md');
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
}
function authorityText(root) {
  const p = path.join(root, '_index.parallel');
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
}
async function load() { return await import(pathToFileURL(tsModule).href); }

async function main() {
  if (mode === 'upsert' || mode === 'invalid-active') {
    const root = argv[2];
    const entry = JSON.parse(argv[3]);
    const M = await load();
    const store = new M.IndexStore(root);
    const before = authorityText(root);
    try {
      await store.upsert(entry);
      emit({ ok: true, mode, pid: process.pid, host: os.hostname(),
             authorityChanged: before !== authorityText(root),
             projection: projectionText(root), authority: authorityText(root) });
    } catch (e) {
      emit({ ok: false, mode, pid: process.pid, host: os.hostname(),
             error: String(e && e.message || e),
             authorityChanged: before !== authorityText(root),
             projection: projectionText(root), authority: authorityText(root) });
      process.exitCode = 2;
    }
    return;
  }
  if (mode === 'claim') {
    const [root, key, selfSpec, gate, ready, waiting, result, hold, forceArg, mirrorArg] = argv.slice(2);
    const self = selfSpec === 'self' ? os.hostname() + ':' + process.pid : selfSpec;
    writeJson(ready, { pid: process.pid, host: os.hostname(), self, key, phase: 'ready', at: Date.now() });
    await waitFor(gate);
    const M = await load();
    const store = new M.IndexStore(root);
    const held = (claimId) => M.conductorClaimState(claimId, self) === 'live';
    writeJson(waiting, { pid: process.pid, self, key, phase: 'waiting-for-lock', at: Date.now() });
    const outcome = await store.claim(key, self, held, { force: forceArg === 'force' });
    // Real TS claim path (ui-bridge.takeOverKey) syncs the pm-state mirror via
    // shared/pm-state-claim.ts AFTER a successful claim. Raw IndexStore.claim
    // alone never touches pm-state.md; using it as a "claim mirror" competitor
    // would fabricate a product failure. This calls the PRODUCTION writer.
    let mirrorSync = null;
    if (outcome.ok && mirrorArg === 'mirror') {
      const pmModule = await import(
        pathToFileURL(path.join(path.dirname(tsModule), 'pm-state-claim.ts')).href);
      mirrorSync = pmModule.syncPmStateClaimId(root, key, self);
    }
    const data = { ok: outcome.ok, mode, rc: outcome.ok ? 0 : 3,
      pid: process.pid, host: os.hostname(), self, key,
      blockedBy: outcome.blockedBy ?? null, refusal: outcome.refusal ?? null,
      entry: outcome.entry ?? null, mirrorSync, at: Date.now(),
      projection: projectionText(root) };
    writeJson(result, data);
    emit(data);
    if (hold && hold !== '-') await waitFor(hold);
    if (!outcome.ok) process.exitCode = 3;
    return;
  }
  if (mode === 'switch') {
    const [root, newKey, ready, gate, result] = argv.slice(2);
    const self = os.hostname() + ':' + process.pid;
    writeJson(ready, { pid: process.pid, host: os.hostname(), self, newKey, phase: 'ready' });
    await waitFor(gate);
    const M = await load();
    const store = new M.IndexStore(root);
    const held = (claimId) => M.conductorClaimState(claimId, self) === 'live';
    const outcome = await store.claim(newKey, self, held);
    const data = { ok: outcome.ok, mode, pid: process.pid, self, newKey,
      blockedBy: outcome.blockedBy ?? null, projection: projectionText(root), rows: store.readAll() };
    writeJson(result, data);
    emit(data);
    if (!outcome.ok) process.exitCode = 3;
    return;
  }
  if (mode === 'read-keys-many') {
    const M = await load();
    const results = [];
    for (const root of argv.slice(2)) {
      try { results.push({ root, ok: true, keys: M.readIndexMdActiveKeys(root) }); }
      catch (e) { results.push({ root, ok: false, error: String(e && e.message || e) }); }
    }
    emit({ ok: true, mode, results });
    return;
  }
  emit({ ok: false, mode, error: 'unknown mode' });
  process.exitCode = 2;
}
main().catch((e) => {
  emit({ ok: false, mode, fatal: String(e && e.stack || e) });
  process.exitCode = 1;
});
"""

PY_HELPER = r"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import socket
import sys
import time

A = sys.argv[1:]
MODE = A[0]
UI_PATH = A[1]
HOST = socket.gethostname()

def load_ui():
    spec = importlib.util.spec_from_file_location('mwcl_ui', UI_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

UI = load_ui()

def emit(data):
    print('MWCL_JSON ' + json.dumps(data, ensure_ascii=False), flush=True)

def write_json(p, data):
    if p and p != '-':
        pathlib.Path(p).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

def wait_for(p, timeout=90.0):
    if not p or p == '-':
        return True
    f = pathlib.Path(p)
    end = time.time() + timeout
    while not f.exists():
        if time.time() > end:
            raise RuntimeError('timeout waiting for ' + str(p))
        time.sleep(0.02)
    return True

def capture(fn):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = fn()
            exc = None
        except BaseException as e:
            rc = None
            exc = repr(e)
    return rc, out.getvalue(), err.getvalue(), exc

def projection_text(root):
    p = pathlib.Path(root) / '_index.md'
    return p.read_text(encoding='utf-8') if p.is_file() else None

def authority_text(root):
    p = pathlib.Path(root) / '_index.parallel'
    return p.read_text(encoding='utf-8') if p.is_file() else None

def rows_of(root):
    return UI.read_index(pathlib.Path(root) / '_index.parallel')

def base(root, rc, out, err, exc, extra=None):
    data = {'mode': MODE, 'pid': os.getpid(), 'host': HOST, 'rc': rc,
            'exception': exc, 'stdout': out[-800:], 'stderr': err[-1600:],
            'projection': projection_text(root), 'authority': authority_text(root),
            'rows': rows_of(root)}
    if extra:
        data.update(extra)
    return data

def resolve_self(spec):
    if spec == 'self':
        return HOST + ':' + str(os.getpid())
    if spec == 'parent':
        return HOST + ':' + str(os.getppid())
    if spec == 'auto' or spec == '-':
        return None
    return spec

def main():
    if MODE == 'framework':
        root = pathlib.Path(A[2])
        cmd = A[3]
        args = A[4:]
        if cmd == 'set-phase':
            fn = lambda: UI.cmd_set_phase(root, args[0], args[1])
        elif cmd == 'set-meta':
            fn = lambda: UI.cmd_set_meta(root, args[0], desc=args[1], deps=None)
        elif cmd == 'claim':
            fn = lambda: UI.cmd_claim(root, args[0], False, claim_id=resolve_self(args[1]))
        elif cmd == 'claim-force':
            fn = lambda: UI.cmd_claim(root, args[0], True, claim_id=resolve_self(args[1]))
        elif cmd == 'release':
            fn = lambda: UI.cmd_release(root, args[0])
        else:
            raise RuntimeError('unknown framework command ' + cmd)
        rc, out, err, exc = capture(fn)
        emit(base(root, rc, out, err, exc))
        return 0
    if MODE == 'conductor':
        project = pathlib.Path(A[2])
        pkg = pathlib.Path(A[3])
        key, claim_id = A[4], A[5]
        sys.path.insert(0, str(pkg))
        from autopilot import index_parallel
        root = project / '.agenticdoc'
        before = (root / '_index.parallel').read_bytes()
        rc, out, err, exc = capture(
            lambda: index_parallel.set_claim(project, key, claim_id=claim_id))
        after = (root / '_index.parallel').read_bytes()
        emit(base(root, rc, out, err, exc,
                  {'ok': rc is True, 'value': rc if isinstance(rc, bool) else str(rc),
                   'authorityChanged': before != after}))
        return 0
    if MODE == 'claim-hold':
        (root, key, spec, gate, ready, waiting, result, hold) = A[2:10]
        root = pathlib.Path(root)
        self_claim = resolve_self(spec)
        write_json(ready, {'pid': os.getpid(), 'host': HOST, 'self': self_claim,
                           'key': key, 'phase': 'ready', 'at': time.time()})
        wait_for(gate)
        write_json(waiting, {'pid': os.getpid(), 'self': self_claim, 'key': key,
                             'phase': 'waiting-for-lock', 'at': time.time()})
        rc, out, err, exc = capture(
            lambda: UI.cmd_claim(root, key, False, claim_id=self_claim))
        data = {'ok': rc == 0, 'mode': MODE, 'rc': rc, 'exception': exc,
                'pid': os.getpid(), 'host': HOST, 'self': self_claim, 'key': key,
                'stdout': out[-800:], 'stderr': err[-1600:], 'at': time.time(),
                'projection': projection_text(root), 'rows': rows_of(root)}
        write_json(result, data)
        emit(data)
        if hold and hold != '-':
            wait_for(hold)
        return 0 if rc == 0 else 3
    if MODE == 'switch-parent':
        root = pathlib.Path(A[2])
        new_key = A[3]
        self_claim = HOST + ':' + str(os.getppid())
        rc, out, err, exc = capture(
            lambda: UI.cmd_claim(root, new_key, False, claim_id=self_claim))
        emit(base(root, rc, out, err, exc,
                  {'ok': rc == 0, 'self': self_claim, 'parentPid': os.getppid()}))
        return 0 if rc == 0 else 3
    if MODE == 'sleep-hold':
        marker, hold = A[2], A[3]
        write_json(marker, {'pid': os.getpid(), 'host': HOST, 'phase': 'alive'})
        emit({'mode': MODE, 'pid': os.getpid(), 'host': HOST, 'phase': 'alive'})
        wait_for(hold, 180.0)
        emit({'mode': MODE, 'pid': os.getpid(), 'phase': 'released'})
        return 0
    if MODE == 'ensure-race':
        # T-12 F-03: DO NOT replace UI._ensure_index. Its production
        # exists-check, O_CREAT|O_EXCL header write and shared index.lock stay
        # EXACTLY as shipped. Only the REAL exclusive-create IO call is wrapped
        # as a barrier, so a second REAL process must queue on the same lock.
        root = pathlib.Path(A[2])
        key, marker, gate, result = A[3], A[4], A[5], A[6]
        index_path = root / '_index.parallel'
        lock_path = root.parent / '.mw' / 'index.lock'
        real_open = os.open
        state = {'gated': False, 'observedMissing': None, 'lockHeld': None,
                 'realCreateCalls': 0}

        def instrumented_open(path, flags, *rest, **kwargs):
            if str(path) == str(index_path) and (flags & os.O_EXCL):
                state['realCreateCalls'] += 1
                if not state['gated']:
                    state['gated'] = True
                    state['observedMissing'] = not index_path.is_file()
                    state['lockHeld'] = lock_path.exists()
                    write_json(marker, {'pid': os.getpid(),
                                        'observedMissing': state['observedMissing'],
                                        'lockHeld': state['lockHeld'],
                                        'phase': 'real-exclusive-create-io'})
                    wait_for(gate, 30.0)
            return real_open(path, flags, *rest, **kwargs)

        os.open = instrumented_open
        try:
            rc, out, err, exc = capture(
                lambda: UI.cmd_claim(root, key, False,
                                     claim_id=resolve_self('self')))
        finally:
            os.open = real_open
        data = base(root, rc, out, err, exc,
                    dict(state, ensureBarrier=True, at=time.time()))
        write_json(result, data)
        emit(data)
        return 0 if rc == 0 else 3
    if MODE == 'release-race':
        # T-12 F-04: wrap the REAL new mirror commit point. cmd_release now
        # prepares the commit in-lock (prepare_fn) and commits it in-lock
        # (after_fn). The old standalone _update_pm_state_claim is no longer on
        # this path and is deliberately NOT wrapped; waiting on a marker that
        # production never emits would be a false product failure.
        root = pathlib.Path(A[2])
        key, marker, gate, result = A[3], A[4], A[5], A[6]
        lock_path = root.parent / '.mw' / 'index.lock'
        original_prepare = UI._prepare_pm_state_claim
        state = {'prepared': False, 'gated': False, 'lockHeld': None,
                 'commitClaimId': None}

        def instrumented_prepare(key_dir, claim_id):
            commit = original_prepare(key_dir, claim_id)   # REAL read-only prepare
            state['prepared'] = True
            state['commitClaimId'] = claim_id

            def instrumented_commit():
                if not state['gated']:
                    state['gated'] = True
                    state['lockHeld'] = lock_path.exists()
                    write_json(marker, {'pid': os.getpid(),
                                        'phase': 'real-mirror-commit',
                                        'lockHeld': state['lockHeld'],
                                        'claimId': claim_id})
                    wait_for(gate, 30.0)
                return commit()                            # REAL mirror write
            return instrumented_commit

        UI._prepare_pm_state_claim = instrumented_prepare
        rc, out, err, exc = capture(lambda: UI.cmd_release(root, key))
        pm = root / key / 'pm-state.md'
        data = base(root, rc, out, err, exc,
                    dict(state, mirrorBarrier=True, at=time.time(),
                         pmState=pm.read_text(encoding='utf-8') if pm.is_file() else None))
        write_json(result, data)
        emit(data)
        return 0 if rc == 0 else 3
    if MODE == 'framework-invalid':
        root = pathlib.Path(A[2])
        key = A[3]
        before = (root / '_index.parallel').read_bytes()
        rc, out, err, exc = capture(lambda: UI.cmd_set_phase(root, key, 'PLAN'))
        after = (root / '_index.parallel').read_bytes()
        emit(base(root, rc, out, err, exc,
                  {'authorityChanged': before != after,
                   'partialMessage': 'PARTIAL' in err}))
        return 0
    if MODE == 'mirror-fail' or MODE == 'mirror-and-projection-fail':
        # T-12 F-05: real prepare/commit API + real _write_projection signature
        # (md_path, rows, pid). The projection call is COUNTED, not replaced by
        # a mocked predicate: mirror IO failure must still ATTEMPT the projection.
        root = pathlib.Path(A[2])
        key = A[3]
        error_text = 'simulated pm-state mirror commit failure (T-12 contract)'
        projection_error = 'simulated projection write failure (T-12 contract)'
        both = MODE == 'mirror-and-projection-fail'

        def bad_prepare(key_dir, claim_id):
            def commit():
                raise OSError(error_text)
            return commit

        UI._prepare_pm_state_claim = bad_prepare
        real_projection = UI._write_projection
        state = {'projectionAttempts': 0}

        def counted_projection(md_path, rows, pid):
            state['projectionAttempts'] += 1
            if both:
                raise UI._ProjectionFailed(UI._partial_failure_msg(projection_error))
            return real_projection(md_path, rows, pid)

        UI._write_projection = counted_projection
        rc, out, err, exc = capture(
            lambda: UI.cmd_claim(root, key, False, claim_id=resolve_self('self')))
        combined = err + (exc or '')
        emit(base(root, rc, out, err, exc, {
            'partialMessage': 'PARTIAL' in combined,
            'errorText': error_text in combined,
            'projectionErrorText': projection_error in combined,
            'mirrorNotWritten': 'pm-state mirror: NOT written' in err,
            'projectionRefreshed': 'refreshed successfully' in err,
            'projectionNotRefreshed': 'NOT refreshed' in err,
            'projectionAttempts': state['projectionAttempts'],
            'exceptionPropagated': exc is not None,
            'pmStateExists': (root / key / 'pm-state.md').is_file(),
        }))
        return 0
    if MODE == 'partial-once':
        root = pathlib.Path(A[2])
        key = A[3]
        real = UI._write_projection
        state = {'n': 0}
        def fail_once(md_path, rows, pid):
            state['n'] += 1
            if state['n'] == 1:
                raise UI._ProjectionFailed(
                    UI._partial_failure_msg('simulated disk error (T-05B)'))
            return real(md_path, rows, pid)
        UI._write_projection = fail_once
        rc, out, err, exc = capture(lambda: UI.cmd_set_phase(root, key, 'PLAN'))
        emit(base(root, rc, out, err, exc,
                  {'partialMessage': 'PARTIAL' in err, 'failCalls': state['n']}))
        return 0
    emit({'mode': MODE, 'ok': False, 'error': 'unknown mode'})
    return 2

sys.exit(main())
"""


# ── Runner infrastructure ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def helpers(tmp_path_factory):
    """Materialise the multi-line helpers into an OS temp dir; delete on exit."""
    with tempfile.TemporaryDirectory(prefix="mwcl-helpers-") as d:
        base = pathlib.Path(d)
        node = base / "mwcl_node.mjs"
        py = base / "mwcl_py.py"
        node.write_text(NODE_HELPER, encoding="utf-8", newline="\n")
        py.write_text(PY_HELPER, encoding="utf-8", newline="\n")
        yield (node, py)
    # TemporaryDirectory cleanup removed both helper files (no leftovers).


@pytest.fixture(scope="session")
def ui():
    """Parent-side read-only import of the production framework module."""
    spec = importlib.util.spec_from_file_location("mwcl_parent_ui", _UPDATE_INDEX)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter missing; TS production store cannot be measured (fail-closed)")
    return node


def _node_argv(helpers, mode, *args):
    return [_node(), "--experimental-strip-types", "--no-warnings",
            str(helpers[0]), mode, str(_TS_MODULE), *(str(a) for a in args)]


def _py_argv(helpers, mode, *args):
    return [sys.executable, "-X", "utf8", str(helpers[1]), mode,
            str(_UPDATE_INDEX), *(str(a) for a in args)]


def _marker(stdout):
    lines = [line for line in stdout.splitlines() if line.startswith("MWCL_JSON ")]
    if not lines:
        raise AssertionError("helper emitted no MWCL_JSON line")
    return json.loads(lines[-1][len("MWCL_JSON "):])


def run_node(helpers, mode, *args, timeout=90):
    proc = subprocess.run(_node_argv(helpers, mode, *args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    if "MWCL_JSON " not in proc.stdout:
        pytest.fail(f"node helper {mode} failed: rc={proc.returncode}\n"
                    f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}")
    return proc, _marker(proc.stdout)


def run_py(helpers, mode, *args, timeout=90):
    proc = subprocess.run(_py_argv(helpers, mode, *args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    if "MWCL_JSON " not in proc.stdout:
        pytest.fail(f"python helper {mode} failed: rc={proc.returncode}\n"
                    f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}")
    return proc, _marker(proc.stdout)


def popen_node(helpers, mode, *args):
    return subprocess.Popen(_node_argv(helpers, mode, *args), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace")


def popen_py(helpers, mode, *args):
    return subprocess.Popen(_py_argv(helpers, mode, *args), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace")


def test_helper_files_live_only_in_os_temp_and_are_cleaned(helpers):
    """Multi-line helpers are temp files, argv-only, never inline -c/-e scripts."""
    node, py = helpers
    assert node.is_file() and py.is_file()
    assert str(_REPO) not in str(node) and str(_REPO) not in str(py)
    assert sorted(p.name for p in node.parent.iterdir()) == ["mwcl_node.mjs", "mwcl_py.py"]
    print(f"[HELPERS] dir={node.parent} files=mwcl_node.mjs,mwcl_py.py "
          f"cleanup=TemporaryDirectory(session_teardown)", flush=True)


def wait_file(path, timeout=30.0):
    p = pathlib.Path(path)
    end = time.time() + timeout
    while not p.exists():
        if time.time() > end:
            raise AssertionError(f"marker never appeared: {p}")
        time.sleep(0.02)
    return json.loads(p.read_text(encoding="utf-8"))


def signal_file(path, payload="go"):
    pathlib.Path(path).write_text(str(payload), encoding="utf-8")


def child_communicate(proc, timeout=60):
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out, err


def reap(proc, timeout=15, grace=0.6):
    """Clean up a child without calling communicate() twice on closed pipes."""
    if proc.poll() is None:
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    return proc.poll()


# ── Independent read/assertion helpers (no product imports) ─────────────────

@pytest.fixture()
def project(tmp_path):
    p = tmp_path / "proj"
    (p / ".agenticdoc").mkdir(parents=True)
    (p / ".mw").mkdir(parents=True)
    return p


def adoc(project):
    return project / ".agenticdoc"


def row_line(key, status="active", claim="old:1", phase="EXECUTE", deps="-",
             desc="desc", updated="2026-01-01 00:00"):
    return f"| {key} | {status} | {phase} | {claim} | {deps} | {desc} | {updated} |"


def seed(project, lines, stale_md=None):
    a = adoc(project)
    (a / "_index.parallel").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    if stale_md is not None:
        (a / "_index.md").write_bytes(stale_md)


def expected_projection(keys):
    return ("# AgenticTask Index\n\nactive_keys: "
            + json.dumps(keys, ensure_ascii=False) + "\n").encode("utf-8")


def projection(project):
    p = adoc(project) / "_index.md"
    return p.read_bytes() if p.is_file() else None


def authority(project):
    return (adoc(project) / "_index.parallel").read_bytes()


def rows(project):
    out = []
    for line in authority(project).decode("utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|[\s:\-|]+\|?\s*$", s):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) < 5 or cols[0] in ("Key", ""):
            continue
        if len(cols) >= 7:
            out.append(dict(zip(("key", "status", "phase", "claim_id", "deps", "desc", "updated"), cols[:7])))
        else:
            out.append({"key": cols[0], "status": cols[1], "phase": _DASH,
                        "claim_id": cols[2], "deps": _DASH, "desc": cols[3],
                        "updated": cols[4]})
    return out


def active_keys(project):
    seen, keys = set(), []
    for r in rows(project):
        if r["status"] != "active":
            continue
        nk = r["key"].lower()
        if nk in seen:
            continue
        seen.add(nk)
        keys.append(r["key"])
    return keys


def snapshot(project):
    out = {}
    for p in sorted(project.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(project)).replace("\\", "/")
        if rel.endswith("index.lock"):
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def assert_clean(project):
    assert not (project / ".mw" / "index.lock").exists(), "shared index.lock was not released"
    leftovers = sorted(str(p.relative_to(project)) for p in project.rglob("*.tmp*"))
    assert leftovers == [], f"tmp leftovers: {leftovers}"


def hold_lock(project):
    lock = project / ".mw" / "index.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    return lock


def release_lock(lock):
    if pathlib.Path(lock).exists():
        pathlib.Path(lock).unlink()


# ── VC-006 / VC-007: exact projection bytes across all three writers ─────────

_BYTE_CASES = (
    ("zero", [row_line("idle-0", "idle")], [], "idle-0", "idle"),
    ("one", [row_line("k-one")], ["k-one"], "k-one", "active"),
    ("many", [row_line("Key-A"), row_line("mid-idle", "idle"),
              row_line("key-b"), row_line("MW-Key.C_2")],
     ["Key-A", "key-b", "MW-Key.C_2"], "MW-Key.C_2", "active"),
    ("case-dup", [row_line("MW-Key"), row_line("mw-key", claim="other:2"),
                  row_line("Z-last")], ["MW-Key", "Z-last"], "Z-last", "active"),
)


def _fresh_case_root(tmp_path, name, lines):
    p = tmp_path / name / "proj"
    (p / ".agenticdoc").mkdir(parents=True)
    (p / ".mw").mkdir(parents=True)
    seed(p, _HEADER_LINES + lines, stale_md=b"# AgenticTask Index\n\nactive_keys: [\"STALE\"]\n")
    return p


def _ts_entry(case_key, target, status):
    # TS IndexEntry field names (camelCase claimId); a Python-style claim_id
    # key would silently serialize as an empty claim cell via Array.join.
    return json.dumps({
        "key": target, "status": status, "phase": "PLAN", "claimId": "ts-upsert:1",
        "deps": "-", "desc": "ts-upsert", "updated": "2026-01-01 00:00",
    }, ensure_ascii=False)


@pytest.mark.parametrize("name,lines,keys,target,status", _BYTE_CASES,
                         ids=[c[0] for c in _BYTE_CASES])
def test_three_writers_produce_identical_projection_bytes(
        helpers, tmp_path, name, lines, keys, target, status):
    expected = expected_projection(keys)
    outputs = {}
    facts = {}

    # 1) TS production IndexStore.upsert (real node + strip-types, no dist).
    p = _fresh_case_root(tmp_path, name + "-ts", lines)
    proc, data = run_node(helpers, "upsert", adoc(p), _ts_entry(name, target, status))
    assert proc.returncode == 0 and data["ok"] is True, data
    outputs["ts"] = projection(p)
    facts["ts"] = {"pid": data["pid"], "rc": proc.returncode,
                   "node": shutil.which("node"), "tsModule": str(_TS_MODULE)}
    assert_clean(p)

    # 2) framework update_index.py set-phase (real python child).
    p = _fresh_case_root(tmp_path, name + "-framework", lines)
    proc, data = run_py(helpers, "framework", adoc(p), "set-phase", target, "PLAN")
    assert proc.returncode == 0 and data["rc"] == 0, data
    outputs["framework"] = projection(p)
    facts["framework"] = {"pid": data["pid"], "rc": proc.returncode, "cmdRc": data["rc"]}
    assert_clean(p)

    # 3) conductor index_parallel.set_claim (real python child, one-cell write).
    p = _fresh_case_root(tmp_path, name + "-conductor", lines)
    proc, data = run_py(helpers, "conductor", p, _PKG, target, "conductor:new-claim")
    assert proc.returncode == 0 and data["ok"] is True, data
    outputs["conductor"] = projection(p)
    facts["conductor"] = {"pid": data["pid"], "rc": proc.returncode,
                          "authorityChanged": data["authorityChanged"]}
    assert_clean(p)

    assert outputs["ts"] == expected, (name, "ts", outputs["ts"])
    assert outputs["framework"] == expected, (name, "framework", outputs["framework"])
    assert outputs["conductor"] == expected, (name, "conductor", outputs["conductor"])
    assert outputs["ts"] == outputs["framework"] == outputs["conductor"]
    assert b"\r" not in outputs["ts"] and not outputs["ts"].startswith(b"\xef\xbb\xbf")

    # TS reader must parse the framework / conductor output as the same set.
    for writer, blob in outputs.items():
        reread = tmp_path / (name + "-reread-" + writer) / "proj"
        (reread / ".agenticdoc").mkdir(parents=True, exist_ok=True)
        (reread / ".agenticdoc" / "_index.md").write_bytes(blob)
        proc, read = run_node(helpers, "read-keys-many", reread / ".agenticdoc")
        assert proc.returncode == 0, read
        assert read["results"][0]["ok"] is True, (writer, read)
        assert read["results"][0]["keys"] == keys, (writer, read)
    print(f"[VERIFY] VC-006/VC-007 case={name} active={keys} "
          f"ts_framework_conductor_bytes_equal=True reader_ok=True", flush=True)


def test_sequential_0_1_N_transitions_in_one_root(project, helpers):
    """One root, three writers in sequence: foreign row stays byte-stable."""
    seed(project, _HEADER_LINES + [
        row_line("foreign", claim="foreign-window:1", phase="VERIFY", desc="keep"),
        row_line("solo", claim="old:1"),
        row_line("idle-1", "idle"),
    ], stale_md=expected_projection(["STALE"]))
    foreign_before = dict(next(r for r in rows(project) if r["key"] == "foreign"))

    # N=2 active: each writer rebuilds the exact same projection in the same root.
    _, ts = run_node(helpers, "upsert", adoc(project), _ts_entry("n", "idle-1", "idle"))
    assert ts["ok"] is True
    assert projection(project) == expected_projection(["foreign", "solo"])
    _, fw = run_py(helpers, "framework", adoc(project), "set-phase", "solo", "PLAN")
    assert fw["rc"] == 0
    assert projection(project) == expected_projection(["foreign", "solo"])
    _, co = run_py(helpers, "conductor", project, _PKG, "idle-1", "conductor:1")
    assert co["ok"] is True
    assert projection(project) == expected_projection(["foreign", "solo"])
    assert dict(next(r for r in rows(project) if r["key"] == "foreign")) == foreign_before

    # 1 active, then 0 active through the framework release entrance.
    _, rel = run_py(helpers, "framework", adoc(project), "release", "solo")
    assert rel["rc"] == 0
    assert projection(project) == expected_projection(["foreign"])
    _, rel2 = run_py(helpers, "framework", adoc(project), "release", "foreign")
    assert rel2["rc"] == 0
    assert projection(project) == expected_projection([])

    # 1 -> N active again: framework claim then a NEW active row via TS upsert.
    _, c1 = run_py(helpers, "framework", adoc(project), "claim", "new-a", "self")
    assert c1["rc"] == 0, c1
    assert projection(project) == expected_projection(["new-a"])
    _, c2 = run_node(helpers, "upsert", adoc(project), _ts_entry("n", "new-b", "active"))
    assert c2["ok"] is True
    assert projection(project) == expected_projection(active_keys(project))
    assert active_keys(project) == ["new-a", "new-b"]
    assert_clean(project)
    print("[VERIFY] VC-006: 0_1_N_transitions=True ts_framework_conductor=TRUE "
          f"foreign_unchanged=True final_active={active_keys(project)}", flush=True)


# ── F-01 / F-02 positive contracts: legal legacy / bad active / illegal key ─

_STALE_BLOB = expected_projection(["STALE"])


def _writer_case(helpers, tmp_path, tag, writer, lines, target, entry, framework_cmd):
    """Run ONE real production writer on a fresh root and record a tree snapshot.

    A writer either SUCCEEDS (all original rows preserved + exact projection) or
    REFUSES with a byte-identical tree snapshot (zero write). Nothing in between
    is accepted: dropping a row and then reporting success is a contract breach.
    """
    p = _fresh_case_root(tmp_path, tag, lines)
    before = snapshot(p)
    if writer == "ts":
        proc, data = run_node(helpers, "invalid-active", adoc(p), entry)
        success = proc.returncode == 0 and data["ok"] is True
        refusal = "" if success else str(data.get("error") or "")
    elif writer == "framework":
        proc, data = run_py(helpers, "framework-invalid", adoc(p), framework_cmd)
        success = data["rc"] == 0
        refusal = "" if success else str(data.get("stderr") or "")
    else:
        proc, data = run_py(helpers, "conductor", p, _PKG, target, "conductor:contract")
        success = data["ok"] is True
        refusal = "" if success else str(data.get("exception") or "")
    after = snapshot(p)
    assert_clean(p)
    return {"project": p, "before": before, "after": after,
            "projection": projection(p), "authority": authority(p).decode("utf-8"),
            "meta": data, "success": success, "refusal": refusal,
            "zero_write": after == before}


def _f01_contract(case, writer, original_keys, expected_keys):
    if case["success"]:
        assert not case["zero_write"], (writer, "succeeded without writing")
        keys_after = [r["key"] for r in rows(case["project"])]
        assert set(original_keys).issubset(set(keys_after)), (
            writer, "a row was dropped then success reported", original_keys, keys_after)
        assert case["projection"] == expected_projection(expected_keys), (
            writer, case["projection"])
    else:
        assert case["zero_write"] is True, (writer, "refusal wrote files", case["meta"])
        assert case["projection"] == _STALE_BLOB, (writer, case["projection"])
        assert case["refusal"], (writer, "refusal had no reason")


def test_f01_legal_legacy_five_col_contract_across_three_writers(helpers, tmp_path):
    """Former repro F-01: legal legacy 5-col (NO bad row) is a support choice.

    T-07 may explicitly refuse unsupported structures with ZERO writes; the
    framework/conductor may support the legal 5-col row. No new compatibility
    is demanded, but no writer may drop a row and still report success.
    """
    lines = ["| legacy | active | oldhost:1 | legacy-desc | 2026-01-01 00:00 |",
             row_line("anchor", claim="old:1")]
    entry = _ts_entry("f01", "anchor", "active")
    outcomes = {}
    for writer in ("ts", "framework", "conductor"):
        case = _writer_case(helpers, tmp_path, "f01-legal-" + writer, writer,
                            lines, "anchor", entry, "anchor")
        _f01_contract(case, writer, {"legacy", "anchor"}, ["legacy", "anchor"])
        outcomes[writer] = "success-full-set" if case["success"] else "zero-write-refusal"
    print(f"[VERIFY] VC-007/F01 legal_legacy_5col: {outcomes} "
          f"no_row_dropped_then_success=True projection_exact_for_success=True", flush=True)


def test_f01_mixed_bad_active_rows_zero_write_for_all_three_writers(helpers, tmp_path):
    """Former strict xfail F-01: the old 'all three byte-equivalent' assertion
    was not a design contract. Mixed bad-active rows must be ZERO-WRITE refused
    by EVERY writer; legal 5-col alone stays in the separate contract above.
    """
    lines = ["| broken | active |", row_line("anchor", claim="old:1")]
    entry = _ts_entry("f01bad", "anchor", "active")
    for writer in ("ts", "framework", "conductor"):
        case = _writer_case(helpers, tmp_path, "f01-bad-" + writer, writer,
                            lines, "anchor", entry, "anchor")
        assert case["success"] is False, (writer, "bad active row was accepted", case["meta"])
        assert case["zero_write"] is True, (writer, "bad active row changed the tree")
        assert case["projection"] == _STALE_BLOB
        reason = case["refusal"].lower()
        assert any(word in reason for word in (
            "unsupported", "unparsed", "untrusted", "refused", "active key refused")), (
            writer, case["refusal"])
    print("[VERIFY] VC-007/F01 mixed_bad_active: ts=zero_write framework=zero_write "
          "conductor=zero_write projection_stale=True", flush=True)


def test_d002_case_normalized_projection_is_exact_not_authority_byte_equality(
        helpers, tmp_path):
    """D-002: pure set projection, case-normalized dedup keeps FIRST spelling.

    The three writers need NOT produce byte-equal authority tables; the frozen
    contract is that their PROJECTION bytes are exactly equal.
    """
    lines = [row_line("MW-Key", claim="old:1"),
             row_line("mw-key", claim="other:2"),
             row_line("Z-last", claim="old:1")]
    expected = expected_projection(["MW-Key", "Z-last"])
    projections, authorities = {}, {}
    for writer in ("ts", "framework", "conductor"):
        case = _writer_case(helpers, tmp_path, "d002-" + writer, writer,
                            lines, "Z-last",
                            _ts_entry("d002", "Z-last", "active"), "Z-last")
        assert case["success"] is True, (writer, case["meta"])
        assert case["projection"] == expected, (writer, case["projection"])
        projections[writer] = case["projection"]
        authorities[writer] = case["authority"]
    assert projections["ts"] == projections["framework"] == projections["conductor"]
    # Deliberately NO assertion that authority bytes are equal across writers.
    assert len(set(authorities.values())) >= 1
    print("[VERIFY] VC-007/D002 projection_exact=True case_normalize_dedup=True "
          "authority_byte_equality_not_required=True", flush=True)


def test_d005_conductor_keeps_non_target_authority_bytes_verbatim(helpers, tmp_path):
    """D-005 dedicated assertion: conductor copies every non-target fragment."""
    p = tmp_path / "d005" / "proj"
    (p / ".agenticdoc").mkdir(parents=True)
    (p / ".mw").mkdir(parents=True)
    raw = (b"# Index Parallel\r\n\r\n"
           b"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |\r\n"
           b"|-----|--------|-------|---------|------|------|---------|\r\n"
           b"| keep-one | active | EXECUTE | old:1 | - | keep-desc | 2026-01-01 00:00 |\r\n"
           b"| target | active | EXECUTE | old:1 | - | desc | 2026-01-01 00:00 |\n")
    (adoc(p) / "_index.parallel").write_bytes(raw)
    (adoc(p) / "_index.md").write_bytes(_STALE_BLOB)
    proc, data = run_py(helpers, "conductor", p, _PKG, "target", "conductor:d005")
    assert proc.returncode == 0 and data["ok"] is True, data
    before_lines = raw.decode("utf-8").splitlines(keepends=True)
    after_lines = authority(p).decode("utf-8").splitlines(keepends=True)
    assert len(before_lines) == len(after_lines), (before_lines, after_lines)
    target_idx = next(i for i, line in enumerate(before_lines)
                      if line.startswith("| target |"))
    for i, (was, now) in enumerate(zip(before_lines, after_lines)):
        if i != target_idx:
            assert was == now, (i, was, now)
    assert after_lines[target_idx].startswith(
        "| target | active | EXECUTE | conductor:d005 |"), after_lines[target_idx]
    assert projection(p) == expected_projection(["keep-one", "target"])
    assert_clean(p)
    print("[VERIFY] VC-006/D005 conductor_non_target_bytes_identical=True "
          "mixed_EOL_preserved=True projection_exact=True", flush=True)


def test_f02_illegal_active_row_zero_write_for_all_three_writers(helpers, tmp_path):
    """Former repro F-02: all three writers must refuse BEFORE any write."""
    lines = [row_line("_index.md", claim="bad:1", desc="reserved"),
             row_line("anchor", claim="old:1")]
    entry = _ts_entry("f02", "anchor", "active")
    for writer in ("ts", "framework", "conductor"):
        case = _writer_case(helpers, tmp_path, "f02-" + writer, writer,
                            lines, "anchor", entry, "anchor")
        assert case["success"] is False, (writer, case["meta"])
        assert case["zero_write"] is True, (writer, "illegal active key wrote files")
        assert case["projection"] == _STALE_BLOB
        assert "PARTIAL" not in case["refusal"].upper(), (
            writer, "refusal was reported as a partial write")
    print("[VERIFY] VC-006/F02 illegal_active_all_three_zero_write=True "
          "authority_unchanged=True projection_stale=True", flush=True)


def test_f02_framework_zero_write_before_authority_replace(helpers, tmp_path):
    """Former strict xfail F-02: now a measured PASS via the real framework entry.

    xfail removed because update_index._write_index_atomic validates projection
    BEFORE os.replace; a tree snapshot proves zero authority/mirror/projection
    writes. The old 'authority written then PARTIAL' expectation was a defect,
    not a contract.
    """
    p = _fresh_case_root(tmp_path, "f02-xfail-contract",
                         [row_line("_index.md", claim="bad:1"),
                          row_line("anchor", claim="old:1")])
    before = snapshot(p)
    proc, data = run_py(helpers, "framework-invalid", adoc(p), "anchor")
    assert proc.returncode == 0
    assert data["rc"] == 1 and data["authorityChanged"] is False, data
    assert data["partialMessage"] is False, data
    assert snapshot(p) == before, "framework wrote files before refusing"
    assert projection(p) == _STALE_BLOB
    assert_clean(p)
    print("[VERIFY] VC-006/F02 framework_zero_write=True rc=1 "
          "partial_message_absent=True tree_snapshot_identical=True", flush=True)


# ── VC-004 / VC-001: real shared-lock competition ───────────────────────────

def _live_holder(helpers, tmp_path, tag):
    marker = tmp_path / (tag + "-alive.json")
    hold = tmp_path / (tag + "-go")
    proc = popen_py(helpers, "sleep-hold", marker, hold)
    info = wait_file(marker, timeout=20)
    assert proc.poll() is None
    return proc, hold, info


def _stop_holder(proc, hold):
    signal_file(hold)
    rc, out, err = child_communicate(proc, timeout=30)
    return rc, out, err


def _claim_child(helpers, role, tmp_path, tag, root, key, hold_path="-",
                 force=False, mirror=False):
    gate = tmp_path / (tag + "-gate")
    ready = tmp_path / (tag + "-ready.json")
    waiting = tmp_path / (tag + "-waiting.json")
    result = tmp_path / (tag + "-result.json")
    if role == "node":
        proc = popen_node(helpers, "claim", root, key, "self", gate, ready,
                          waiting, result, hold_path,
                          "force" if force else "-",
                          "mirror" if mirror else "-")
    else:
        proc = popen_py(helpers, "claim-hold", root, key, "self", gate, ready,
                        waiting, result, hold_path)
    return {"role": role, "proc": proc, "gate": gate, "ready": ready,
            "waiting": waiting, "result": result, "hold": hold_path,
            "tag": tag, "key": key}


@pytest.mark.parametrize("first", ("node", "python"), ids=("node-first", "python-first"))
def test_different_keys_coexist_while_both_children_queue_on_shared_lock(
        helpers, project, tmp_path, first):
    holder, holder_go, holder_info = _live_holder(helpers, tmp_path, "dk-" + first)
    foreign_claim = f"{_HOST}:{holder_info['pid']}"
    foreign_row = row_line("foreign", claim=foreign_claim, phase="VERIFY", desc="keep-me")
    seed(project, _HEADER_LINES + [foreign_row],
         stale_md=expected_projection(["STALE"]))
    foreign_before = dict(next(r for r in rows(project) if r["key"] == "foreign"))

    lock = hold_lock(project)
    tag = "dk-" + first
    node_c = _claim_child(helpers, "node", tmp_path, tag + "-node", adoc(project), "key-node")
    py_c = _claim_child(helpers, "python", tmp_path, tag + "-py", adoc(project), "key-py")
    children = [node_c, py_c]
    try:
        for c in children:
            info = wait_file(c["ready"], timeout=20)
            assert c["proc"].poll() is None, c["tag"]
            print(f"[RACE] queued_child role={c['role']} pid={info['pid']} "
                  f"self={info['self']} key={c['key']} lock=<proj>/.mw/index.lock", flush=True)
        order = children if first == "node" else list(reversed(children))
        for c in order:
            signal_file(c["gate"])
        for c in children:
            wait_file(c["waiting"], timeout=20)
        time.sleep(0.35)
        for c in children:
            assert c["proc"].poll() is None, f"{c['tag']} did not queue on the shared lock"
        release_lock(lock)  # both real children now contend for the SAME lock
        results = {}
        for c in children:
            results[c["role"]] = wait_file(c["result"], timeout=40)
            assert results[c["role"]]["ok"] is True, (c["role"], results[c["role"]])
        for c in children:
            rc, out, err = child_communicate(c["proc"], timeout=40)
            assert rc == 0, (c["tag"], rc, out, err)

        table = {r["key"]: r for r in rows(project)}
        assert table["key-node"]["status"] == "active"
        assert table["key-py"]["status"] == "active"
        assert table["key-node"]["claim_id"] == f"{_HOST}:{results['node']['pid']}"
        assert table["key-py"]["claim_id"] == f"{_HOST}:{results['python']['pid']}"
        assert table["foreign"] == foreign_before, "foreign row fields changed"
        assert projection(project) == expected_projection(active_keys(project))
        assert set(active_keys(project)) == {"foreign", "key-node", "key-py"}
        assert_clean(project)
        finish = sorted((role, r["at"]) for role, r in results.items())
        print(f"[VERIFY] VC-004/VC-001 order={first} both_blocked_on_lock=True "
              f"active={active_keys(project)} foreign_unchanged=True "
              f"finish_timestamps={finish}", flush=True)
    finally:
        for c in children:
            if c["hold"] != "-":
                signal_file(c["hold"])
        for c in children:
            reap(c["proc"])
        release_lock(lock)
        if holder.poll() is None:
            _stop_holder(holder, holder_go)
        else:
            reap(holder)


@pytest.mark.parametrize("winner_role", ("node", "python"),
                         ids=("node-wins", "python-wins"))
def test_same_key_one_wins_and_loser_rechecks_inside_lock(
        helpers, project, tmp_path, winner_role):
    loser_role = "python" if winner_role == "node" else "node"
    tag = "sk-" + winner_role
    seed(project, _HEADER_LINES, stale_md=expected_projection(["STALE"]))
    winner_hold = tmp_path / (tag + "-winner-go")
    winner = _claim_child(helpers, winner_role, tmp_path, tag + "-winner",
                          adoc(project), "race-key", hold_path=winner_hold)
    loser = _claim_child(helpers, loser_role, tmp_path, tag + "-loser",
                         adoc(project), "race-key")
    children = [winner, loser]
    lock = hold_lock(project)
    try:
        w_ready = wait_file(winner["ready"], timeout=20)
        l_ready = wait_file(loser["ready"], timeout=20)
        print(f"[RACE] same_key winner={winner_role} winner_pid={w_ready['pid']} "
              f"loser={loser_role} loser_pid={l_ready['pid']} key=race-key", flush=True)

        # Winner queues on the parent-held shared lock, then wins it alone.
        signal_file(winner["gate"])
        wait_file(winner["waiting"], timeout=20)
        time.sleep(0.3)
        assert winner["proc"].poll() is None, "winner was not queued on the shared lock"
        release_lock(lock)
        w_result = wait_file(winner["result"], timeout=40)
        assert w_result["ok"] is True, w_result
        winner_claim = w_result["self"]
        table = {r["key"]: r for r in rows(project)}
        assert table["race-key"]["status"] == "active"
        assert table["race-key"]["claim_id"] == winner_claim
        assert winner["proc"].poll() is None, "winner died before loser verdict (stale-pid risk)"
        assert not winner_hold.exists()

        # Loser now queues on the SAME lock while the parent holds it; the loser
        # must re-read FRESH rows INSIDE the lock and refuse the live foreign claim.
        lock = hold_lock(project)
        signal_file(loser["gate"])
        wait_file(loser["waiting"], timeout=20)
        time.sleep(0.3)
        assert loser["proc"].poll() is None, "loser was not queued on the shared lock"
        before = snapshot(project)
        before_projection = projection(project)
        release_lock(lock)
        l_result = wait_file(loser["result"], timeout=40)
        assert l_result["ok"] is False, l_result
        loser_message = (l_result.get("stderr") or "") + str(l_result.get("blockedBy") or "")
        assert "CONFLICT" in loser_message or winner_claim in loser_message, l_result
        assert winner_claim in loser_message, (
            "loser did not name the live foreign winner claim", l_result)
        if loser_role == "python":
            assert "index.lock" in loser_message, (
                "framework loser did not report the in-lock re-validation", l_result)
        assert winner["proc"].poll() is None, "winner process died before loser's verdict"
        l_rc, l_out, l_err = child_communicate(loser["proc"], timeout=40)
        assert l_rc != 0, (l_rc, l_out, l_err)
        assert snapshot(project) == before, "loser wrote files on refusal"
        assert projection(project) == before_projection == expected_projection(["race-key"])
        table = {r["key"]: r for r in rows(project)}
        assert table["race-key"]["claim_id"] == winner_claim
        assert_clean(project)
        print(f"[VERIFY] VC-004 winner={winner_role} loser={loser_role} "
              f"one_active_row=True winner_claim={winner_claim} loser_rc={l_rc} "
              f"blockedBy={l_result.get('blockedBy')} "
              f"loser_conflict_evidence={loser_message.strip()[:220]!r} "
              f"winner_alive_at_verdict=True loser_zero_write=True", flush=True)
    finally:
        signal_file(winner_hold)
        for c in children:
            reap(c["proc"])
        release_lock(lock)


# ── VC-002 / VC-009: verified-identity same-window switches ─────────────────

def test_python_verified_parent_bridge_switch_demotes_only_own_rows(
        helpers, project, tmp_path):
    holder, holder_go, info = _live_holder(helpers, tmp_path, "pb")
    try:
        parent_claim = f"{_HOST}:{os.getpid()}"  # child's verified DIRECT parent
        foreign_claim = f"{_HOST}:{info['pid']}"  # a genuinely live other process
        seed(project, _HEADER_LINES + [
            row_line("own-1", claim=parent_claim),
            row_line("own-2", claim=parent_claim, phase="DESIGN", desc="mine"),
            row_line("foreign", claim=foreign_claim, phase="VERIFY", desc="keep"),
            row_line("legacy", "idle", claim="20260101-000000-1"),
        ], stale_md=expected_projection(["STALE"]))
        before = {r["key"]: dict(r) for r in rows(project)}
        proc, data = run_py(helpers, "switch-parent", adoc(project), "own-new")
        assert proc.returncode == 0 and data["ok"] is True, data
        assert data["self"] == parent_claim, data
        table = {r["key"]: r for r in rows(project)}
        assert table["own-1"]["status"] == "idle" and table["own-2"]["status"] == "idle"
        assert table["own-new"]["status"] == "active"
        assert table["own-new"]["claim_id"] == parent_claim
        for k in ("foreign", "legacy"):
            assert table[k] == before[k], k
        assert projection(project) == expected_projection(["foreign", "own-new"])
        assert_clean(project)
        print(f"[VERIFY] VC-002/VC-009 python_parent_bridge: verified_parent_pid={os.getpid()} "
              f"foreign_live_pid={info['pid']} demote_scope=self only_own_idle=True", flush=True)
    finally:
        if holder.poll() is None:
            _stop_holder(holder, holder_go)
        else:
            reap(holder)


def test_ts_real_process_switch_demotes_only_own_rows(helpers, project, tmp_path):
    holder, holder_go, info = _live_holder(helpers, tmp_path, "ts")
    tag = "tsw"
    ready = tmp_path / (tag + "-ready.json")
    gate = tmp_path / (tag + "-gate")
    result = tmp_path / (tag + "-result.json")
    child = popen_node(helpers, "switch", adoc(project), "own-new", ready, gate, result)
    try:
        r = wait_file(ready, timeout=20)
        self_claim = r["self"]
        foreign_claim = f"{_HOST}:{info['pid']}"
        seed(project, _HEADER_LINES + [
            row_line("own-1", claim=self_claim),
            row_line("own-2", claim=self_claim, phase="DESIGN", desc="mine"),
            row_line("foreign", claim=foreign_claim, phase="VERIFY", desc="keep"),
            row_line("legacy", "idle", claim="20260101-000000-1"),
        ], stale_md=expected_projection(["STALE"]))
        before = {r["key"]: dict(r) for r in rows(project)}
        signal_file(gate)
        data = wait_file(result, timeout=40)
        rc, out, err = child_communicate(child, timeout=40)
        assert rc == 0 and data["ok"] is True, (rc, data, out, err)
        table = {r["key"]: r for r in rows(project)}
        assert table["own-1"]["status"] == "idle" and table["own-2"]["status"] == "idle"
        assert table["own-new"]["status"] == "active"
        assert table["own-new"]["claim_id"] == self_claim
        for k in ("foreign", "legacy"):
            assert table[k] == before[k], k
        assert projection(project) == expected_projection(["foreign", "own-new"])
        assert_clean(project)
        print(f"[VERIFY] VC-002 ts_window_switch: real_node_pid={r['pid']} "
              f"self={self_claim} foreign_live_pid={info['pid']} "
              f"demote_scope=self only_own_idle=True", flush=True)
    finally:
        if gate.exists() is False:
            signal_file(gate)
        reap(child)
        if holder.poll() is None:
            _stop_holder(holder, holder_go)
        else:
            reap(holder)


# ── VC-003 / VC-006: partial failure, cross-language recovery, lock release ──

def test_framework_partial_projection_failure_is_recovered_by_ts_upsert(
        helpers, project):
    seed(project, _HEADER_LINES + [
        row_line("k-one", claim="old:1"),
        row_line("k-two", claim="old:2"),
    ], stale_md=expected_projection(["STALE"]))
    proc, data = run_py(helpers, "partial-once", adoc(project), "k-one")
    assert proc.returncode == 0 and data["rc"] == 1, data
    assert data["partialMessage"] is True and data["failCalls"] == 1
    assert projection(project) == expected_projection(["STALE"]), "partial write refreshed projection"
    assert rows(project)[0]["phase"] == "PLAN", "authority was not written"
    assert_clean(project)  # lock released even on partial failure

    # A real Node production writer rebuilds the complete projection from the
    # EXACT authority rows the framework left behind (value-preserving upsert).
    framework_written_authority_rows = rows(project)
    r0 = framework_written_authority_rows[0]
    entry = json.dumps({
        "key": r0["key"], "status": r0["status"], "phase": r0["phase"],
        "claimId": r0["claim_id"], "deps": r0["deps"], "desc": r0["desc"],
        "updated": r0["updated"],
    })
    proc, ts = run_node(helpers, "upsert", adoc(project), entry)
    assert proc.returncode == 0 and ts["ok"] is True, ts
    assert projection(project) == expected_projection(["k-one", "k-two"])
    assert rows(project) == framework_written_authority_rows
    _, read = run_node(helpers, "read-keys-many", adoc(project))
    assert read["results"][0]["keys"] == ["k-one", "k-two"]
    assert_clean(project)
    print("[VERIFY] VC-006: partial_write_visible=True ts_upsert_recovery=True "
          "lock_released=True tmp_leftovers=0", flush=True)


def test_ts_reader_fails_closed_on_old_scalar_bad_json_duplicate_crlf_illegal(
        helpers, tmp_path):
    canonical = "# AgenticTask Index\n\nactive_keys: [\"a\", \"b\"]\n"
    cases = [
        ("canonical", canonical, True),
        ("old-scalar", "# AgenticTask Index\n\nactive: a\n", False),
        ("bad-json", "# AgenticTask Index\n\nactive_keys: [\"a\",]\n", False),
        ("duplicate-case", "# AgenticTask Index\n\nactive_keys: [\"MW-Key\", \"mw-key\"]\n", False),
        ("crlf", canonical.replace("\n", "\r\n"), False),
        ("illegal-name", "# AgenticTask Index\n\nactive_keys: [\"_index.md\"]\n", False),
        ("non-canonical-spacing", "# AgenticTask Index\n\nactive_keys: [\"a\",\"b\"]\n", False),
    ]
    roots = []
    for name, text, _ in cases:
        r = tmp_path / name / "proj" / ".agenticdoc"
        r.mkdir(parents=True)
        if name != "missing-file":
            (r / "_index.md").write_bytes(text.encode("utf-8"))
        roots.append(r)
    missing = tmp_path / "missing" / "proj" / ".agenticdoc"
    missing.mkdir(parents=True)
    roots.append(missing)
    proc, data = run_node(helpers, "read-keys-many", *roots)
    assert proc.returncode == 0 and len(data["results"]) == len(roots), (proc.returncode, data)
    for (name, _, ok), item in zip(cases, data["results"][:len(cases)]):
        assert item["ok"] is ok, (name, item)
        if ok:
            assert item["keys"] == ["a", "b"]
        else:
            assert item["error"], (name, item)
    assert data["results"][-1]["ok"] is False, data["results"][-1]
    print(f"[VERIFY] VC-007: ts_reader_fail_closed_cases={len(cases) + 1} "
          f"canonical_ok=True stale_or_bad_refused=True", flush=True)


def test_reachable_update_index_mirrors_are_byte_identical():
    """VC-008 static half (read-only): the canonical script and its mirrors."""
    paths = [
        ".agents/skills/agentic-task/scripts/update_index.py",
        ".agents/skills/agentic-task/core/scripts/update_index.py",
        ".agents/skills/agentic-task/claude/scripts/update_index.py",
        ".claude/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/core/scripts/update_index.py",
        "packages/multi-workers/.tmp/agentic-task/claude/scripts/update_index.py",
    ]
    hashes = set()
    for rel in paths:
        p = _REPO / rel
        assert p.is_file(), rel
        hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
    assert len(hashes) == 1, f"framework mirrors diverge: {hashes}"
    physical = {os.path.realpath(str(_REPO / rel)) for rel in paths}
    assert len(physical) == 4, f"expected 4 physical copies, got {sorted(physical)}"
    assert _TS_MODULE.is_file() and "dist" not in str(_TS_MODULE)
    print(f"[VERIFY] VC-008: update_index_paths={len(paths)} "
          f"physical_copies={len(physical)} junction_aliases={len(paths) - len(physical)} "
          f"identical=True ts_source_not_dist=True", flush=True)


# ── F-03 / F-04 / F-05 positive contracts: real processes, real entry points ─

def _ensure_race_run(helpers, tmp_path, tag, competitor_role):
    """F-03: production _ensure_index is INTACT; only its real O_EXCL header
    create is fenced inside the shared lock. A second REAL process (node or
    python) queues on that lock; both rows must survive in one authority table.
    """
    p = tmp_path / tag / "proj"
    (p / ".agenticdoc").mkdir(parents=True)
    (p / ".mw").mkdir(parents=True)
    a = p / ".agenticdoc"
    marker = tmp_path / (tag + "-marker.json")
    gate = tmp_path / (tag + "-gate")
    result = tmp_path / (tag + "-ensure-result.json")
    child = popen_py(helpers, "ensure-race", a, "key-a", marker, gate, result)
    comp = None
    try:
        seen = wait_file(marker, timeout=20)
        assert seen["observedMissing"] is True, seen
        assert seen["lockHeld"] is True, "first create was outside the shared lock"
        comp = _claim_child(helpers, competitor_role, tmp_path, tag + "-comp", a, "key-b")
        ready = wait_file(comp["ready"], timeout=20)
        assert comp["proc"].poll() is None, comp["tag"]
        signal_file(comp["gate"])
        wait_file(comp["waiting"], timeout=20)
        time.sleep(0.35)
        assert comp["proc"].poll() is None, "competitor did not queue on the shared lock"
        assert (p / ".mw" / "index.lock").exists(), "index.lock not held during the fence"
        signal_file(gate)
        rc, out, err = child_communicate(child, timeout=40)
        assert rc == 0, (rc, out, err)
        ensure_result = wait_file(result, timeout=40)
        comp_result = wait_file(comp["result"], timeout=40)
        assert comp_result["ok"] is True, comp_result
        crc, cout, cerr = child_communicate(comp["proc"], timeout=40)
        assert crc == 0, (crc, cout, cerr)
        keys = [r["key"] for r in rows(p)]
        assert set(keys) == {"key-a", "key-b"} and len(keys) == 2, keys
        assert set(active_keys(p)) == {"key-a", "key-b"}
        assert projection(p) == expected_projection(active_keys(p))
        assert_clean(p)
        order = ("ensure-first"
                 if result.stat().st_mtime_ns <= comp["result"].stat().st_mtime_ns
                 else "competitor-first")
        # Node's Date.now() is epoch ms; Python's time.time() is epoch seconds.
        ensure_at = float(ensure_result["at"])
        comp_at = float(comp_result["at"]) / (1000.0 if competitor_role == "node" else 1.0)
        finish = sorted((("ensure-python", round(ensure_at, 6)),
                         (competitor_role, round(comp_at, 6))), key=lambda item: item[1])
        print(f"[RACE] F03 ensure_pid={seen['pid']} competitor={competitor_role} "
              f"competitor_pid={ready['pid']} lockHeld={seen['lockHeld']} "
              f"competitor_blocked=True real_create_calls={ensure_result['realCreateCalls']} "
              f"order_by_result_mtime={order} finish_order={finish} final_keys={keys}", flush=True)
        print("[VERIFY] VC-004/F03 first_create_zero_loss=True both_real_processes=True "
              "same_shared_lock=True projection_exact=True", flush=True)
        return {"keys": keys, "ensure": ensure_result, "competitor": comp_result,
                "order": order,
                "pids": {"ensure": seen["pid"], "competitor": ready["pid"]}}
    finally:
        if not gate.exists():
            signal_file(gate)
        if comp is not None:
            if not comp["gate"].exists():
                signal_file(comp["gate"])
            reap(comp["proc"])
        reap(child)


@pytest.mark.parametrize("competitor_role", ("node", "python"),
                         ids=("node-competitor", "python-competitor"))
def test_f03_first_create_inside_shared_lock_preserves_both_writers(
        helpers, tmp_path, competitor_role):
    """Former repro F-03: the old probe REPLACED _ensure_index with an
    unconditional HEADER write (a fabricated defect). Now the real production
    exists/write logic is preserved and both real processes keep their rows.
    """
    facts = _ensure_race_run(helpers, tmp_path, "f03-" + competitor_role,
                             competitor_role)
    assert set(facts["keys"]) == {"key-a", "key-b"}


def test_f03_first_create_zero_loss_contract(helpers, tmp_path):
    """Former strict xfail F-03: removed after the real first-create contract
    was measured through two real processes on the shared lock.
    """
    facts = _ensure_race_run(helpers, tmp_path, "f03-xfail-contract", "python")
    assert set(facts["keys"]) == {"key-a", "key-b"}
    assert facts["ensure"]["realCreateCalls"] == 1
    assert facts["ensure"]["gated"] is True


def _mirror_race_run(helpers, tmp_path, tag, competitor_role):
    """F-04: only the REAL in-lock mirror commit is fenced; a later claim must
    wait on the same shared lock and its Claim-Id mirror must survive.
    """
    p = tmp_path / tag / "proj"
    (p / ".agenticdoc").mkdir(parents=True)
    (p / ".mw").mkdir(parents=True)
    a = p / ".agenticdoc"
    seed(p, _HEADER_LINES + [row_line("k", claim="old:1")], stale_md=_STALE_BLOB)
    key_dir = a / "k"
    key_dir.mkdir()
    (key_dir / "pm-state.md").write_text(
        "# PM State: k\n- Key: k\n- Claim-Id: old:1\n- Phase: init\n",
        encoding="utf-8")
    marker = tmp_path / (tag + "-marker.json")
    gate = tmp_path / (tag + "-gate")
    result = tmp_path / (tag + "-release-result.json")
    child = popen_py(helpers, "release-race", a, "k", marker, gate, result)
    comp = None
    try:
        seen = wait_file(marker, timeout=20)
        assert seen["phase"] == "real-mirror-commit", seen
        assert seen["lockHeld"] is True, "mirror commit was outside the shared lock"
        comp = _claim_child(helpers, competitor_role, tmp_path, tag + "-comp", a, "k",
                            mirror=(competitor_role == "node"))
        ready = wait_file(comp["ready"], timeout=20)
        signal_file(comp["gate"])
        wait_file(comp["waiting"], timeout=20)
        time.sleep(0.35)
        assert comp["proc"].poll() is None, "claim did not wait on the shared lock"
        assert (p / ".mw" / "index.lock").exists(), "index.lock not held during mirror commit"
        signal_file(gate)
        rc, out, err = child_communicate(child, timeout=40)
        assert rc == 0, (rc, out, err)
        release_result = wait_file(result, timeout=40)
        comp_result = wait_file(comp["result"], timeout=40)
        assert comp_result["ok"] is True, comp_result
        crc, cout, cerr = child_communicate(comp["proc"], timeout=40)
        assert crc == 0, (crc, cout, cerr)
        if competitor_role == "node":
            assert comp_result["mirrorSync"] == {"ok": True}, comp_result
        comp_claim = comp_result["self"]
        pm_text = (a / "k" / "pm-state.md").read_text(encoding="utf-8")
        table = {r["key"]: r for r in rows(p)}
        assert len(table) == 1
        assert table["k"]["status"] == "active"
        assert table["k"]["claim_id"] == comp_claim
        assert f"- Claim-Id: {comp_claim}" in pm_text, pm_text
        assert _DASH not in pm_text, "release mirror overwrote the later claim"
        assert projection(p) == expected_projection(["k"])
        assert_clean(p)
        order = ("release-first"
                 if result.stat().st_mtime_ns <= comp["result"].stat().st_mtime_ns
                 else "claim-first")
        release_at = float(release_result["at"])
        comp_at = float(comp_result["at"]) / (1000.0 if competitor_role == "node" else 1.0)
        finish = sorted((("release-python", round(release_at, 6)),
                         ("claim-" + competitor_role, round(comp_at, 6))),
                        key=lambda item: item[1])
        print(f"[RACE] F04 release_pid={seen['pid']} competitor={competitor_role} "
              f"claim_pid={ready['pid']} mirror_lockHeld={seen['lockHeld']} "
              f"claim_blocked=True prepared={release_result['prepared']} "
              f"order_by_result_mtime={order} finish_order={finish} "
              f"final_authority_claim={comp_claim}", flush=True)
        print("[VERIFY] VC-003/F04 release_claim_mirror_consistent=True "
              "in_lock_commit=True projection_exact=True", flush=True)
        return {"pm_text": pm_text, "claim": comp_claim,
                "release": release_result, "competitor": comp_result,
                "order": order,
                "pids": {"release": seen["pid"], "competitor": ready["pid"]}}
    finally:
        if not gate.exists():
            signal_file(gate)
        if comp is not None:
            if not comp["gate"].exists():
                signal_file(comp["gate"])
            reap(comp["proc"])
        reap(child)


@pytest.mark.parametrize("competitor_role", ("node", "python"),
                         ids=("node-competitor", "python-competitor"))
def test_f04_release_mirror_commit_inside_lock_serializes_later_claim(
        helpers, tmp_path, competitor_role):
    """Former repro F-04: the old probe wrapped _update_pm_state_claim, which
    the fixed cmd_release no longer calls. Now the real mirror commit is fenced
    and the competing claim is proven to wait on the shared lock.
    """
    facts = _mirror_race_run(helpers, tmp_path, "f04-" + competitor_role,
                             competitor_role)
    assert f"- Claim-Id: {facts['claim']}" in facts["pm_text"]
    assert facts["release"]["gated"] is True


def test_f04_release_claim_mirror_consistency_contract(helpers, tmp_path):
    """Former strict xfail F-04: removed after the real in-lock mirror commit
    was measured with a real competing claim process.
    """
    facts = _mirror_race_run(helpers, tmp_path, "f04-xfail-contract", "python")
    assert _DASH not in facts["pm_text"]
    assert facts["claim"] in facts["pm_text"]


def _mirror_fail_run(helpers, tmp_path, tag, mode="mirror-fail"):
    p = tmp_path / tag / "proj"
    (p / ".agenticdoc").mkdir(parents=True)
    (p / ".mw").mkdir(parents=True)
    a = p / ".agenticdoc"
    seed(p, _HEADER_LINES, stale_md=_STALE_BLOB)
    proc, data = run_py(helpers, mode, a, "k-mirror")
    assert proc.returncode == 0, (proc.returncode, data)
    return p, data


def test_f05_mirror_io_failure_reports_partial_and_still_projects(
        helpers, tmp_path):
    """Former repro F-05: inverted into the design contract. The mirror error
    must be a visible PARTIAL write; the projection must STILL BE ATTEMPTED.
    """
    p, data = _mirror_fail_run(helpers, tmp_path, "f05-partial")
    assert data["rc"] == 1, data
    assert data["partialMessage"] is True and data["errorText"] is True, data
    assert data["mirrorNotWritten"] is True, data
    assert data["projectionRefreshed"] is True, data
    assert data["projectionAttempts"] >= 1, data
    assert data["exceptionPropagated"] is False, data
    assert data["pmStateExists"] is False, data
    assert [r["key"] for r in rows(p)] == ["k-mirror"], "authority was not written"
    assert projection(p) == expected_projection(["k-mirror"]), (
        "projection was not attempted after the mirror IO failure")
    assert_clean(p)
    proc, rec = run_py(helpers, "framework", adoc(p), "set-phase", "k-mirror", "PLAN")
    assert proc.returncode == 0 and rec["rc"] == 0, rec
    assert projection(p) == expected_projection(["k-mirror"])
    assert_clean(p)
    print(f"[VERIFY] VC-006/F05 mirror_partial={data['partialMessage']} "
          f"projection_attempts={data['projectionAttempts']} projection_refreshed=True "
          f"authority_written=True recovery_by_real_mutation=True", flush=True)


def test_f05_mirror_io_failure_partial_recovery_by_next_mutation(
        helpers, tmp_path):
    """Former strict xfail F-05: removed after the real framework entry reported
    an exact PARTIAL error and the projection was rebuilt by the next mutation.
    """
    _, data = _mirror_fail_run(helpers, tmp_path, "f05-xfail-contract")
    assert data["partialMessage"] is True and data["rc"] == 1, data
    p2, both = _mirror_fail_run(helpers, tmp_path, "f05-both",
                                mode="mirror-and-projection-fail")
    assert both["partialMessage"] is True and both["rc"] == 1, both
    assert both["mirrorNotWritten"] is True, both
    assert both["projectionNotRefreshed"] is True, both
    assert both["errorText"] is True and both["projectionErrorText"] is True, both
    assert both["projectionAttempts"] >= 1, both
    assert projection(p2) == _STALE_BLOB, "failed projection must stay stale"
    assert_clean(p2)
    proc, rec = run_py(helpers, "framework", adoc(p2), "set-phase", "k-mirror", "PLAN")
    assert proc.returncode == 0 and rec["rc"] == 0, rec
    assert projection(p2) == expected_projection(["k-mirror"])
    assert_clean(p2)
    print("[VERIFY] VC-006/F05 both_mirror_and_projection_errors_reported=True "
          "projection_still_attempted=True stale_projection_rebuilt=True", flush=True)


# ── Added: same-self reclaim + explicit force boundary (temp projects only) ──

def test_same_self_reclaim_through_real_framework_entry(
        helpers, project, tmp_path):
    holder, holder_go, info = _live_holder(helpers, tmp_path, "self-reclaim")
    try:
        parent_claim = f"{_HOST}:{os.getpid()}"
        foreign_claim = f"{_HOST}:{info['pid']}"
        seed(project, _HEADER_LINES + [
            row_line("self-key", claim=parent_claim),
            row_line("foreign", claim=foreign_claim),
        ], stale_md=_STALE_BLOB)
        before = {r["key"]: dict(r) for r in rows(project)}
        proc, data = run_py(helpers, "switch-parent", adoc(project), "self-key")
        assert proc.returncode == 0 and data["ok"] is True, data
        assert data["self"] == parent_claim, data
        table = {r["key"]: r for r in rows(project)}
        assert len(table) == 2, "reclaim invented a duplicate row"
        assert table["self-key"]["status"] == "active"
        assert table["self-key"]["claim_id"] == parent_claim
        assert table["foreign"] == before["foreign"]
        assert projection(project) == expected_projection(["self-key", "foreign"])
        assert_clean(project)
        print(f"[VERIFY] VC-003 same_self_reclaim=True parent_pid={os.getpid()} "
              f"foreign_live_pid={info['pid']} no_duplicate_row=True", flush=True)
    finally:
        if holder.poll() is None:
            _stop_holder(holder, holder_go)
        else:
            reap(holder)


def test_explicit_force_is_temp_root_only_and_not_a_tool_confirmation_proof(
        helpers, project, tmp_path):
    """A low-level ``force=True`` in a temp project is NOT the user-confirmation
    tool path. The real switch_key tool still defaults force off and documents
    explicit user confirmation; this test neither invokes nor validates it.
    """
    holder, holder_go, info = _live_holder(helpers, tmp_path, "explicit-force")
    try:
        foreign_claim = f"{_HOST}:{info['pid']}"
        parent_claim = f"{_HOST}:{os.getpid()}"
        seed(project, _HEADER_LINES + [
            row_line("forced", claim=foreign_claim),
            row_line("other", "idle"),
        ], stale_md=_STALE_BLOB)
        proc, data = run_py(helpers, "framework", adoc(project),
                            "claim-force", "forced", "parent")
        assert proc.returncode == 0 and data["rc"] == 0, data
        table = {r["key"]: r for r in rows(project)}
        assert table["forced"]["status"] == "active"
        assert table["forced"]["claim_id"] == parent_claim
        assert projection(project) == expected_projection(["forced"])
        assert_clean(project)
        assert str(project).startswith(str(tmp_path)), "force must stay in a temp root"
        bridge = (_REPO / "packages" / "coding-agent" / "src" / "extensions" /
                  "agent-team-loop" / "pm" / "ui-bridge.ts").read_text(encoding="utf-8")
        assert "Only with the user's explicit confirmation" in bridge
        assert "force = false" in bridge
        print("[VERIFY] VC-003 explicit_force_temp_root=True low_level_param_only=True "
              "tool_user_confirmation_path_NOT_validated=True "
              "tool_defaults_force_false=True", flush=True)
    finally:
        if holder.poll() is None:
            _stop_holder(holder, holder_go)
        else:
            reap(holder)
