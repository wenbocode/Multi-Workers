"""T-19: independent final-boundary cross-language and REAL lock-attempt acceptance.

Non-T16/17/18 implementer, on the current single product version. Product and
ALL old tests are STRICTLY READ-ONLY. The only new test file is this one.

This file builds its OWN temporary subprocess harnesses (materialised into an
OS-temp dir) that call the REAL production entry points:

  * TS ``shared/index-store.ts`` (source, via --experimental-strip-types):
    ``IndexStore.claim`` / ``IndexStore.upsert``;
  * framework ``update_index.py`` (junction alias -> canonical physical):
    ``cmd_set_phase``;
  * conductor ``autopilot.index_parallel.set_claim``;
  * ``mw.cmd_init`` (real, offline bundle/guide monkeypatch);
  * the REAL shared lock IO: Node ``fs.openSync(lock,"wx")`` and Python
    ``os.open(lock, O_CREAT|O_EXCL)`` are wrapped (delegate to the real IO,
    log EEXIST/FileExistsError, then re-raise to the real retry), never replaced.

New coverage (the gaps T-14A/B and T-16/17/18 closed) is measured here as a
black box: a three-writer shape matrix, a real ``cmd_init`` matrix (no private
``_projection_shape`` pre-assert), and four cross-language lock-contention groups
with a winner child that ACTUALLY holds the lock via a gate while the loser makes
a REAL EEXIST attempt on the same path, both languages alternating as winner.
T-22 adds a second loser gate for the two same-key groups: after the winner has
committed/unlocked, the loser blocks at its own SUCCESSFUL real O_EXCL open
before the fd is returned and before any read/write under that lock. A full
project byte snapshot at that point is compared, path set and bytes, after the
loser verdict. "acquired" means the real open returned an fd; a pre-unlink log
is "unlink_call_attempt" and only a post-success log is "released". No fake
locks or predicates are introduced.
Old T-12 scenarios are NOT deleted or weakened: the unchanged
``test_window_claim_cross_language.py`` is run as-is (separate command) and a
preservation test here reuses its REAL helper strings for 0/1/N three-writer
bytes, D005 byte preservation and partial recovery.

All subprocesses use argv lists (no shell), finite timeouts and isolated
TEMP/PYTHONPYCACHEPREFIX. No model/decision/claim/QG/sign/global/production
index is touched. Detailed IO/gate evidence is written to MWFA_EVIDENCE_DIR
when set.
"""
from __future__ import annotations

import base64
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

_HERE = pathlib.Path(__file__).resolve().parent          # packages/multi-workers
_REPO = _HERE.parent.parent
_PKG = _HERE
_TS_MODULE = _REPO / "packages" / "coding-agent" / "src" / "extensions" / "agent-team-loop" / "shared" / "index-store.ts"
_UPDATE_INDEX = _REPO / ".agents" / "skills" / "agentic-task" / "scripts" / "update_index.py"
_AUTOPILOT_PKG = _REPO / "packages" / "multi-workers"
_HOST = socket.gethostname()
_EVIDENCE = os.environ.get("MWFA_EVIDENCE_DIR")
_RUN_ID = os.environ.get("MWFA_RUN_ID") or "unset-%d-%d" % (os.getpid(), time.time_ns())
_COMMAND_RUN_ID = os.environ.get("MWFA_COMMAND_RUN_ID")
_COMMAND_START_UTC = os.environ.get("MWFA_COMMAND_START_UTC")
_RUNNER_PID = os.environ.get("MWFA_RUNNER_PID")
_CR = bytes((13,))
_LF_B = bytes((10,))
_CRLF_B = bytes((13, 10))
_LF = "\n"


# ── Import the OLD T-12 test module (REAL helpers / fixtures; no mocked
#    predicate is rewritten). Used by the preservation test below. ────────────
def _load_t12():
    spec = importlib.util.spec_from_file_location(
        "_mwfa_t12_module", str(_HERE / "test_window_claim_cross_language.py"))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T12 = _load_t12()

_HEADER_LINES = T12._HEADER_LINES  # real canonical header/separator control


# ── Node subprocess harness (source TS via syncBuiltinESMExports) ───────────
NODE_FINAL = r"""
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { syncBuiltinESMExports } from 'node:module';

const A = process.argv.slice(2);
const MODE = A[0];
const TS = A[1];
const emit = (d) => process.stdout.write('MWFA_JSON ' + JSON.stringify(d) + '\n');
const readText = (p) => fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
const sleepWait = (ms) => { const s = new Int32Array(new SharedArrayBuffer(4)); Atomics.wait(s, 0, 0, ms); };
function waitFor(file, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (!fs.existsSync(file)) {
    if (Date.now() > end) throw new Error('timeout waiting for ' + file);
    sleepWait(15);
  }
}
async function load() { return await import(pathToFileURL(TS).href); }
function ioAppend(file, ev) { fs.appendFileSync(file, JSON.stringify(ev) + '\n', 'utf8'); }

// Install a wrapper around the REAL node:fs lock IO. Each call delegates to the
// real openSync/unlinkSync; EEXIST is logged then re-thrown to the real retry.
function installLockInstrument(lockPath, control, tag, role, gateLoser) {
  const realOpenSync = fs.openSync;
  const realUnlinkSync = fs.unlinkSync;
  const iofile = path.join(control, tag + '.iolog.jsonl');
  let seq = 0, first = true, held = (role === 'winner'), gated = !!gateLoser;
  fs.openSync = function (p, flags, ...rest) {
    if (String(p) === lockPath && flags === 'wx') {
      seq += 1;
      const ev = { pid: process.pid, role, tag, at_ms: Date.now(), ev: 'attempt',
                   path: String(p), flags: String(flags), attempt: seq };
      try {
        const fd = realOpenSync.call(this, p, flags, ...rest);
        ev.ev = 'acquired'; ev.real_open_success = true; ev.fd = fd;
        ioAppend(iofile, ev);
        if (first) { first = false; fs.writeFileSync(path.join(control, tag + '.first_acquired'), JSON.stringify(ev), 'utf8'); }
        if (held && !fs.existsSync(path.join(control, 'winner_gate'))) {
          held = false;   // hold ONLY on the first successful real acquire
          fs.writeFileSync(path.join(control, tag + '.holding'), JSON.stringify(ev), 'utf8');
          waitFor(path.join(control, 'winner_gate'), 30000);
          ioAppend(iofile, { pid: process.pid, role, tag, at_ms: Date.now(), ev: 'hold_released', path: String(p) });
        }
        if (gated && !fs.existsSync(path.join(control, 'loser_gate'))) {
          gated = false;  // gate ONLY after this successful real open, before fd return
          const gate = { ...ev, ev: 'gated_acquired', fd_released_to_caller: false,
                         winner_committed: fs.existsSync(path.join(control, 'w.wrote')) };
          fs.writeFileSync(path.join(control, tag + '.gated_acquired'), JSON.stringify(gate), 'utf8');
          waitFor(path.join(control, 'loser_gate'), 30000);
          ioAppend(iofile, { pid: process.pid, role, tag, at_ms: Date.now(), ev: 'loser_gate_released', fd, path: String(p) });
        }
        return fd;
      } catch (e) {
        ev.ev = 'eexist'; ev.errno = (e && e.code) || String(e);
        ioAppend(iofile, ev);
        fs.writeFileSync(path.join(control, tag + '.eexist'), JSON.stringify(ev), 'utf8');
        throw e;  // delegate to the REAL acquireLock retry
      }
    }
    return realOpenSync.call(this, p, flags, ...rest);
  };
  fs.unlinkSync = function (p, ...rest) {
    if (String(p) !== lockPath) return realUnlinkSync.call(this, p, ...rest);
    ioAppend(iofile, { pid: process.pid, role, tag, at_ms: Date.now(), ev: 'unlink_call_attempt', path: String(p) });
    try {
      const out = realUnlinkSync.call(this, p, ...rest);
      ioAppend(iofile, { pid: process.pid, role, tag, at_ms: Date.now(), ev: 'released', path: String(p) });
      return out;
    } catch (e) {
      ioAppend(iofile, { pid: process.pid, role, tag, at_ms: Date.now(), ev: 'unlink_failed', path: String(p), error: String(e && (e.code || e.message) || e) });
      throw e;
    }
  };
  syncBuiltinESMExports();
  return iofile;
}

async function main() {
  // BATCH matrix: real IndexStore.claim / upsert, one subprocess, many roots.
  if (MODE === 'batch') {
    const cases = JSON.parse(fs.readFileSync(A[2], 'utf8'));
    const M = await load();
    for (const c of cases) {
      const store = new M.IndexStore(c.root);
      const self = c.self === 'self' ? (os.hostname() + ':' + process.pid) : c.self;
      const held = (claimId) => M.conductorClaimState(claimId, self) === 'live';
      let out;
      try {
        if (c.op === 'claim') {
          const r = await store.claim(c.key, self, held, { force: false });
          out = { ok: r.ok, refusal: r.refusal ?? null, blockedBy: r.blockedBy ?? null };
        } else {
          await store.upsert(c.entry);
          out = { ok: true };
        }
      } catch (e) { out = { ok: false, exception: String(e && e.message || e) }; }
      emit({ case: c.name, writer: 'ts-' + c.op, pid: process.pid, ...out,
             projection: readText(path.join(c.root, '_index.md')),
             authority: readText(path.join(c.root, '_index.parallel')) });
    }
    return;
  }

  // LOCK child: real IndexStore.claim with real lock IO instrumented.
  if (MODE === 'locknode') {
    const [root, key, selfSpec, control, tag, role, relation] = A.slice(2);
    const lockPath = path.join(root, '..', '.mw', 'index.lock');
    installLockInstrument(lockPath, control, tag, role, relation === 'same' && role === 'loser');
    const M = await load();
    const store = new M.IndexStore(root);
    const self = selfSpec === 'self' ? (os.hostname() + ':' + process.pid) : selfSpec;
    const held = (claimId) => M.conductorClaimState(claimId, self) === 'live';
    let outcome;
    try { outcome = await store.claim(key, self, held, { force: false }); }
    catch (e) { outcome = { ok: false, exception: String(e && e.message || e) }; }
    const data = { mode: 'locknode', writer: 'ts-claim', ok: outcome.ok, role, tag,
      pid: process.pid, host: os.hostname(), self, key,
      blockedBy: outcome.blockedBy ?? null, refusal: outcome.refusal ?? null,
      exception: outcome.exception ?? null,
      projection: readText(path.join(root, '_index.md')),
      authority: readText(path.join(root, '_index.parallel')), at_ms: Date.now() };
    fs.writeFileSync(path.join(control, tag + '.result'), JSON.stringify(data), 'utf8');
    if (role === 'winner') {
      fs.writeFileSync(path.join(control, tag + '.wrote'), JSON.stringify({ pid: data.pid, at_ms: data.at_ms, ok: data.ok }), 'utf8');
      fs.writeFileSync(path.join(control, tag + '.alive'), JSON.stringify({ pid: data.pid, at_ms: Date.now() }), 'utf8');
      waitFor(path.join(control, 'winner_alive_gate'), 30000);
    }
    emit(data);
    if (!outcome.ok) process.exitCode = 3;
    return;
  }
  emit({ ok: false, error: 'unknown mode ' + MODE });
  process.exitCode = 2;
}
main().catch((e) => { emit({ ok: false, fatal: String(e && e.stack || e) }); process.exitCode = 1; });
"""


# ── Python subprocess harness (real update_index / conductor / mw / lock) ───
PY_FINAL = r"""
import argparse
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
    spec = importlib.util.spec_from_file_location('mwfa_ui', UI_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


UI = load_ui()


def emit(d):
    print('MWFA_JSON ' + json.dumps(d, ensure_ascii=False), flush=True)


def capture(fn):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = fn(); exc = None
        except BaseException as e:
            rc = None; exc = repr(e)
    return rc, out.getvalue(), err.getvalue(), exc


def projection_text(ad):
    p = pathlib.Path(ad) / '_index.md'
    return p.read_text(encoding='utf-8') if p.is_file() else None


def authority_text(ad):
    p = pathlib.Path(ad) / '_index.parallel'
    return p.read_text(encoding='utf-8') if p.is_file() else None


def resolve_self(spec):
    if spec == 'self':
        return HOST + ':' + str(os.getpid())
    return spec


_MW = None
_GLOBAL_EXT = None


def ensure_mw(global_ext, pkg):
    global _MW, _GLOBAL_EXT
    if _MW is None:
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        import mw
        _MW = mw
        _GLOBAL_EXT = pathlib.Path(global_ext)
        _GLOBAL_EXT.mkdir(parents=True, exist_ok=True)
        (_GLOBAL_EXT / 'agent-team-loop.js').write_text('// offline dummy\n', encoding='utf-8')
        mw._check_bundle = lambda: True
        mw._global_ext_dir = lambda: _GLOBAL_EXT
        mw._install_project_agent_guide = lambda pd: pd / 'AGENTS.md'
    return _MW


def run_init(project, global_ext, pkg):
    mw = ensure_mw(global_ext, pkg)
    args = argparse.Namespace(project=str(project), no_framework=True,
                              codex_scope='project', sync_agentictask=None)
    return capture(lambda: mw.cmd_init(args))


def main():
    # BATCH matrix: framework set-phase / conductor set_claim, and real cmd_init.
    if MODE == 'batch':
        cases = json.loads(pathlib.Path(A[2]).read_text(encoding='utf-8'))
        global_ext = A[3]
        pkg = A[4]
        for c in cases:
            w = c['writer']
            ad = pathlib.Path(c['ad'])
            if w == 'framework':
                rc, out, err, exc = capture(lambda: UI.cmd_set_phase(ad, c['key'], c.get('phase', 'PLAN')))
                emit({'case': c['name'], 'writer': w, 'rc': rc, 'exception': exc,
                      'stdout': out[-400:], 'stderr': err[-700:],
                      'projection': projection_text(ad), 'authority': authority_text(ad)})
            elif w == 'conductor':
                project = pathlib.Path(c['project'])
                if str(pkg) not in sys.path:
                    sys.path.insert(0, str(pkg))
                from autopilot import index_parallel
                rc, out, err, exc = capture(
                    lambda: index_parallel.set_claim(project, c['key'], claim_id=c['claim_id']))
                emit({'case': c['name'], 'writer': w, 'rc': rc, 'value': rc if isinstance(rc, bool) else str(rc),
                      'exception': exc, 'stdout': out[-400:], 'stderr': err[-700:],
                      'projection': projection_text(ad), 'authority': authority_text(ad)})
            elif w == 'init':
                project = pathlib.Path(c['project'])
                rc, out, err, exc = run_init(project, global_ext, pkg)
                emit({'case': c['name'], 'writer': w, 'rc': rc, 'exception': exc,
                      'stdout': out[-400:], 'stderr': err[-700:],
                      'projection': projection_text(ad), 'authority': authority_text(ad)})
            else:
                emit({'case': c['name'], 'writer': w, 'error': 'unknown writer'})
        return 0

    # PARTIAL recovery: real _write_projection fails once, then a real mutation rebuilds.
    if MODE == 'partial':
        root = pathlib.Path(A[2]); key = A[3]
        real = UI._write_projection
        state = {'n': 0}
        def fail_once(md_path, rows, pid):
            state['n'] += 1
            if state['n'] == 1:
                raise UI._ProjectionFailed(UI._partial_failure_msg('simulated disk error (T-19)'))
            return real(md_path, rows, pid)
        UI._write_projection = fail_once
        rc1, o1, e1, x1 = capture(lambda: UI.cmd_set_phase(root, key, 'PLAN'))
        rc2, o2, e2, x2 = capture(lambda: UI.cmd_set_phase(root, key, 'EXECUTE'))
        emit({'mode': 'partial', 'projectionAttempts': state['n'],
              'firstPartial': 'PARTIAL' in (e1 + (x1 or '')),
              'secondRc': rc2, 'exception1': x1, 'exception2': x2,
              'projection': projection_text(root), 'authority': authority_text(root)})
        return 0

    # LOCK child: real cmd_claim with real os.open/os.unlink lock IO instrumented.
    if MODE == 'lockclaim':
        root = pathlib.Path(A[2]); key = A[3]; self_spec = A[4]
        control = pathlib.Path(A[5]); tag = A[6]; role = A[7]
        relation = A[8] if len(A) > 8 else 'diff'
        gate_loser = relation == 'same' and role == 'loser'
        LOCK = root.parent / '.mw' / 'index.lock'
        self_claim = resolve_self(self_spec)
        # Post-claim phase-chain audit is unrelated to the lock/conflict
        # predicate under test; stub ONLY that non-predicate helper to avoid a
        # stray external subprocess. The claim predicate stays entirely real.
        UI._audit_after_claim = lambda *a, **k: None
        real_open = os.open
        real_unlink = os.unlink
        iofile = control / (tag + '.iolog.jsonl')
        state = {'seq': 0, 'first': True, 'held': role == 'winner', 'gated': gate_loser}
        def io_log(ev):
            with open(iofile, 'a', encoding='utf-8') as f:
                f.write(json.dumps(ev) + '\n')
        def wait_for(p, timeout=30.0):
            end = time.time() + timeout
            while not p.exists():
                if time.time() > end:
                    raise RuntimeError('timeout waiting for ' + str(p))
                time.sleep(0.02)
        def wrapped_open(path, flags, *rest, **kwargs):
            if os.path.normcase(str(path)) == os.path.normcase(str(LOCK)) and (flags & os.O_EXCL):
                state['seq'] += 1
                ev = {'pid': os.getpid(), 'role': role, 'tag': tag,
                      'at_ms': int(time.time() * 1000), 'ev': 'attempt',
                      'path': str(path), 'flags': flags, 'attempt': state['seq']}
                try:
                    fd = real_open(path, flags, *rest, **kwargs)
                    ev['ev'] = 'acquired'
                    ev['real_open_success'] = True
                    ev['fd'] = fd
                    io_log(ev)
                    if state['first']:
                        state['first'] = False
                        (control / (tag + '.first_acquired')).write_text(json.dumps(ev), encoding='utf-8')
                    if state['held'] and not (control / 'winner_gate').exists():
                        state['held'] = False  # hold ONLY on the first successful real acquire
                        (control / (tag + '.holding')).write_text(json.dumps(ev), encoding='utf-8')
                        wait_for(control / 'winner_gate', 30.0)
                        io_log({'pid': os.getpid(), 'role': role, 'tag': tag,
                                'at_ms': int(time.time() * 1000), 'ev': 'hold_released', 'path': str(path)})
                    if state['gated'] and not (control / 'loser_gate').exists():
                        state['gated'] = False  # gate ONLY after this successful real open
                        gate_ev = dict(ev)
                        gate_ev.update({'ev': 'gated_acquired',
                                        'fd_released_to_caller': False,
                                        'winner_committed': (control / 'w.wrote').exists()})
                        (control / (tag + '.gated_acquired')).write_text(json.dumps(gate_ev), encoding='utf-8')
                        wait_for(control / 'loser_gate', 30.0)
                        io_log({'pid': os.getpid(), 'role': role, 'tag': tag,
                                'at_ms': int(time.time() * 1000), 'ev': 'loser_gate_released',
                                'fd': fd, 'path': str(path)})
                    return fd
                except FileExistsError as e:
                    ev['ev'] = 'eexist'; ev['errno'] = e.errno
                    io_log(ev)
                    (control / (tag + '.eexist')).write_text(json.dumps(ev), encoding='utf-8')
                    raise  # delegate to the REAL _index_lock retry
            return real_open(path, flags, *rest, **kwargs)
        def wrapped_unlink(path, *rest, **kwargs):
            if os.path.normcase(str(path)) != os.path.normcase(str(LOCK)):
                return real_unlink(path, *rest, **kwargs)
            io_log({'pid': os.getpid(), 'role': role, 'tag': tag,
                    'at_ms': int(time.time() * 1000), 'ev': 'unlink_call_attempt', 'path': str(path)})
            try:
                result = real_unlink(path, *rest, **kwargs)
            except OSError as e:
                io_log({'pid': os.getpid(), 'role': role, 'tag': tag,
                        'at_ms': int(time.time() * 1000), 'ev': 'unlink_failed',
                        'path': str(path), 'error': repr(e)})
                raise
            io_log({'pid': os.getpid(), 'role': role, 'tag': tag,
                    'at_ms': int(time.time() * 1000), 'ev': 'released', 'path': str(path)})
            return result
        os.open = wrapped_open
        os.unlink = wrapped_unlink
        try:
            rc, out, err, exc = capture(lambda: UI.cmd_claim(root, key, False, claim_id=self_claim))
        finally:
            os.open = real_open
            os.unlink = real_unlink
        data = {'mode': 'lockclaim', 'writer': 'framework-claim', 'ok': rc == 0,
                'role': role, 'tag': tag, 'rc': rc, 'exception': exc,
                'pid': os.getpid(), 'host': HOST, 'self': self_claim, 'key': key,
                'stdout': out[-500:], 'stderr': err[-900:],
                'projection': projection_text(root), 'authority': authority_text(root),
                'at_ms': int(time.time() * 1000)}
        (control / (tag + '.result')).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        if role == 'winner':
            (control / (tag + '.wrote')).write_text(json.dumps({'pid': data['pid'], 'at_ms': data['at_ms'], 'ok': data['ok']}), encoding='utf-8')
            (control / (tag + '.alive')).write_text(json.dumps({'pid': data['pid'], 'at_ms': int(time.time() * 1000)}), encoding='utf-8')
            wait_for(control / 'winner_alive_gate', 30.0)
        emit(data)
        return 0 if rc == 0 else 3
    emit({'ok': False, 'error': 'unknown mode ' + MODE})
    return 2


sys.exit(main())
"""


# ── Fixtures & utilities ────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def helpers(tmp_path_factory):
    d = pathlib.Path(tmp_path_factory.mktemp("mwfa-helpers"))
    node = d / "mwfa_node.mjs"
    py = d / "mwfa_py.py"
    node.write_text(NODE_FINAL, encoding="utf-8", newline="\n")
    py.write_text(PY_FINAL, encoding="utf-8", newline="\n")
    yield (node, py)
    shutil.rmtree(d, ignore_errors=True)


def _ev(name, text):
    if _EVIDENCE and pathlib.Path(_EVIDENCE).is_dir():
        target_dir = pathlib.Path(_EVIDENCE) / _RUN_ID
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / name).write_text(text, encoding="utf-8", newline="\n")


def _ev_json(name, obj):
    _ev(name, json.dumps(obj, ensure_ascii=False, indent=2))


def _markers(stdout):
    return [json.loads(l[len("MWFA_JSON "):])
            for l in stdout.splitlines() if l.startswith("MWFA_JSON ")]


def _child_env(tmpdir, extra=None):
    tmpdir = pathlib.Path(tmpdir)
    tmpdir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not re.search(r"(KEY|TOKEN|SECRET|PASS|CRED|AUTH|API)", k, re.I)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["TEMP"] = str(tmpdir)
    env["TMP"] = str(tmpdir)
    env["TMPDIR"] = str(tmpdir)
    env["PYTHONPYCACHEPREFIX"] = str(tmpdir / "pycache")
    if extra:
        env.update(extra)
    return env


def _node():
    n = shutil.which("node")
    assert n, "node missing; TS production store cannot be measured (fail-closed)"
    return n


def _snap(project):
    """Full content snapshot of every FILE under project (relpath -> sha256).
    Harness markers/control live outside project, so zero-write == identical map."""
    project = pathlib.Path(project)
    d = {}
    if not project.exists():
        return d
    for p in sorted(project.rglob("*")):
        if p.is_file():
            d[str(p.relative_to(project)).replace("\\", "/")] = hashlib.sha256(p.read_bytes()).hexdigest()
    return d


def _data_bytes(project):
    """Exact bytes of every data file; exclude ONLY the transient shared lock."""
    project = pathlib.Path(project)
    out = {}
    if not project.exists():
        return out
    for p in sorted(project.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(project)).replace("\\", "/")
        if rel == ".mw/index.lock":
            continue
        out[rel] = p.read_bytes()
    return out


def _bytes_record(data):
    return [{"path": path,
             "sha256": hashlib.sha256(value).hexdigest(),
             "size": len(value),
             "bytes_base64": base64.b64encode(value).decode("ascii")}
            for path, value in sorted(data.items())]


def _snapshot_digest(data):
    canonical = json.dumps(_bytes_record(data), ensure_ascii=True, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _diff_data_snapshots(before, after):
    before_paths, after_paths = set(before), set(after)
    return {"created": sorted(after_paths - before_paths),
            "deleted": sorted(before_paths - after_paths),
            "changed": sorted(k for k in before_paths & after_paths if before[k] != after[k])}


def _read_io_events(path):
    p = pathlib.Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _wait_io_event(path, ev, tag, timeout=30.0):
    end = time.time() + timeout
    while True:
        found = [e for e in _read_io_events(path) if e.get("tag") == tag and e.get("ev") == ev]
        if found:
            return found
        if time.time() > end:
            raise AssertionError("timeout waiting for %s event %s/%s" % (path, tag, ev))
        time.sleep(0.02)


def _seed_lock_project_data(project, keys):
    """Meaningful mixed-EOL pm-state and extra data sentinels, all write_bytes."""
    project = pathlib.Path(project)
    crlf, lf = _CRLF_B, _LF_B
    seen = set()
    for key in ["foreign", "anchor"] + list(keys):
        if key in seen:
            continue
        seen.add(key)
        key_dir = project / ".agenticdoc" / key
        key_dir.mkdir(parents=True, exist_ok=True)
        key_bytes = key.encode("utf-8")
        (key_dir / "pm-state.md").write_bytes(
            b"# PM State: " + key_bytes + crlf + crlf +
            b"## Section 1: Snapshot" + lf +
            b"- Key: " + key_bytes + crlf +
            b"- Claim-Id: seed-" + key_bytes + lf +
            b"- Phase: seed" + lf +
            b"- Note: exact bytes sentinel" + crlf)
        (key_dir / "notes.txt").write_bytes(
            b"key=" + key_bytes + crlf + b"owner=seed" + lf +
            b"no-terminal-newline")
    (project / ".agenticdoc" / "project-data.json").write_bytes(
        b'{"seed":true,"mixed_eol":"crlf+lf"}' + crlf)
    archive = project / ".agenticdoc" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "old.bin").write_bytes(b"t22-archive-no-terminal-newline")
    (project / ".mw" / "seed.meta").write_bytes(b"t22-seed" + lf)
    (project / "README.txt").write_bytes(b"t22 project data" + crlf)


def _read_json(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _wait_file(p, timeout=30.0):
    p = pathlib.Path(p)
    end = time.time() + timeout
    while not p.exists():
        if time.time() > end:
            raise AssertionError("timeout waiting for " + str(p))
        time.sleep(0.02)
    return _read_json(p)


def _independent_active_keys(text):
    """INDEPENDENT oracle (does NOT use production active_projection)."""
    keys, seen = [], set()
    for line in (text or "").splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) == 7 and cells[0] == "Key" and cells[1] == "Status":
            continue  # real 7-column header is decoration
        if len(cells) not in (5, 7):
            continue
        if cells[1] != "active":
            continue
        nk = cells[0].strip().lower()
        if nk in seen:
            continue
        seen.add(nk)
        keys.append(cells[0])
    return keys


def _expected_projection(keys):
    return "# AgenticTask Index" + _LF + _LF + "active_keys: " + json.dumps(keys, ensure_ascii=False) + _LF


def _no_temp_artifacts(snapshot):
    bad = [k for k in snapshot if ".tmp" in k or k.endswith("index.lock")]
    return bad


# ── Authority fixtures ──────────────────────────────────────────────────────
_HDR = _LF.join(_HEADER_LINES) + _LF
_STALE_PROJECTION = "# AgenticTask Index" + _LF + _LF + 'active_keys: ["stale-sentinel"]' + _LF
_ANCHOR = "| anchor | idle | SPEC | - | - | anchor desc | 2026-01-01 00:00 |"
_FOREIGN = "| foreign | active | EXECUTE | otherhost:999 | - | foreign desc | 2026-01-01 00:00 |"
_KEY7 = "| Key | active | EXECUTE | otherhost:111 | - | key desc | 2026-01-01 00:00 |"

BAD_ROWS = {
    "-bad": "| -bad | active | EXECUTE | otherhost:1 | - | d | 2026-01-01 00:00 |",
    "#bad": "| #bad | active | EXECUTE | otherhost:1 | - | d | 2026-01-01 00:00 |",
    "empty": "|  | active | EXECUTE | otherhost:1 | - | d | 2026-01-01 00:00 |",
    "bare7": "lost | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00 |",
    "no_edge": "| lost | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00",
    "six": "| lost | active | EXECUTE | foreign:1 | desc | EXTRA |",
    "eight": "| lost | active | EXECUTE | foreign:1 | - | desc | 2026-01-01 00:00 | EXTRA |",
    "header_looking": "| Key | active |",
}
_FIVE = "| legacy-five | active | otherhost:2 | legacy desc | 2026-01-01 00:00 |"


def _authority(rows):
    return _HDR + _LF.join(rows) + _LF


def _setup_project(base, authority, projection=None):
    project = base
    ad = project / ".agenticdoc"
    mw = project / ".mw"
    ad.mkdir(parents=True, exist_ok=True)
    mw.mkdir(parents=True, exist_ok=True)
    (ad / "_index.parallel").write_text(authority, encoding="utf-8", newline="\n")
    (ad / "_index.md").write_text(projection if projection is not None else _STALE_PROJECTION,
                                  encoding="utf-8", newline="\n")
    anchor_dir = ad / "anchor"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    (anchor_dir / "pm-state.md").write_text(
        "# PM State: anchor\n\n- Key: anchor\n- Claim-Id: original\n- Phase: init\n",
        encoding="utf-8", newline="\n")
    return project, ad


# ── TEST 1: three-writer shape matrix ───────────────────────────────────────
def test_three_writer_shape_matrix(helpers, tmp_path):
    node_h, py_h = helpers
    root = tmp_path / "matrix"
    root.mkdir()
    cases_dir = root / "cases"
    cases_dir.mkdir()

    shape_defs = []
    # legal Key-first 7-column active + real header/separator control
    shape_defs.append(("legal_key7", "legal", [_KEY7, _FOREIGN, _ANCHOR]))
    for label, bad in BAD_ROWS.items():
        shape_defs.append((label, "illegal", [_FOREIGN, bad, _ANCHOR]))
    shape_defs.append(("five_col", "five", [_FOREIGN, _FIVE, _ANCHOR]))

    ts_cases, py_cases, meta = [], [], {}
    for name, kind, rows in shape_defs:
        authority = _authority(rows)
        for op in ("claim", "upsert"):
            cn = "ts%s__%s" % (op, name)
            proj, ad = _setup_project(cases_dir / cn, authority)
            meta[cn] = {"kind": kind, "before": _snap(proj), "ad": str(ad)}
            entry = {"key": "anchor", "status": "idle", "phase": "SPEC",
                     "claimId": "-", "deps": "-", "desc": "anchor desc",
                     "updated": "2026-01-01 00:00"}
            ts_cases.append({"name": cn, "root": str(ad), "op": op,
                             "key": "anchor", "self": "self", "entry": entry})
        for writer in ("framework", "conductor"):
            cn = "%s__%s" % (writer, name)
            proj, ad = _setup_project(cases_dir / cn, authority)
            meta[cn] = {"kind": kind, "before": _snap(proj), "ad": str(ad)}
            if writer == "framework":
                py_cases.append({"name": cn, "writer": "framework", "ad": str(ad),
                                 "project": str(proj), "key": "anchor", "phase": "PLAN"})
            else:
                py_cases.append({"name": cn, "writer": "conductor", "ad": str(ad),
                                 "project": str(proj), "key": "anchor",
                                 "claim_id": "host:12345"})

    ts_cases_file = cases_dir / "ts_cases.json"
    py_cases_file = cases_dir / "py_cases.json"
    ts_cases_file.write_text(json.dumps(ts_cases), encoding="utf-8", newline="\n")
    py_cases_file.write_text(json.dumps(py_cases), encoding="utf-8", newline="\n")
    env = _child_env(root / "tmp")

    nrun = subprocess.run(
        [_node(), "--experimental-strip-types", "--no-warnings", str(node_h),
         "batch", str(_TS_MODULE), str(ts_cases_file)],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=180)
    prun = subprocess.run(
        [sys.executable, "-X", "utf8", str(py_h), "batch", str(_UPDATE_INDEX),
         str(py_cases_file), str(root / "global-ext"), str(_AUTOPILOT_PKG)],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=180)
    assert nrun.returncode == 0, "node batch failed: " + nrun.stderr[-2000:]
    assert prun.returncode == 0, "py batch failed: " + prun.stderr[-2000:]

    results = _markers(nrun.stdout) + _markers(prun.stdout)
    by_case = {r["case"]: r for r in results}
    assert len(results) == len(meta), "expected %d case results, got %d" % (len(meta), len(results))

    summary = {}
    for cn, m in meta.items():
        r = by_case[cn]
        after = _snap(m["ad"] + "/..")  # project root is parent of .agenticdoc
        zero_write = (after == m["before"])
        stray = _no_temp_artifacts(after)
        kind = m["kind"]
        verdict = {"writer": r.get("writer"), "ok": r.get("ok"),
                   "rc": r.get("rc"), "value": r.get("value"),
                   "refusal": r.get("refusal"), "exception": r.get("exception"),
                   "zero_write": zero_write, "stray": stray}
        if kind == "illegal":
            assert zero_write, "%s: illegal shape must be ZERO data write; after!=before (refusal=%s exc=%s)" % (
                cn, r.get("refusal") or r.get("rc"), r.get("exception"))
            assert not stray, "%s: stray temp/lock artifacts %s" % (cn, stray)
            rejected = (r.get("ok") is False or (r.get("rc") not in (0, None)) or r.get("exception"))
            assert rejected, "%s: illegal shape must be an explicit rejection: %s" % (cn, r)
            verdict["classification"] = "zero_write_refusal"
        elif kind == "legal":
            assert r.get("ok") is True or r.get("rc") == 0 or r.get("value") is True, \
                "%s: legal Key-first 7-col must SUCCEED: %s" % (cn, r)
            final_authority = r.get("authority")
            keys = _independent_active_keys(final_authority)
            assert "Key" in keys and "foreign" in keys, \
                "%s: full active set must be preserved (Key/foreign), got %s" % (cn, keys)
            assert r.get("projection") == _expected_projection(keys), \
                "%s: projection must be exact %r, got %r" % (cn, _expected_projection(keys), r.get("projection"))
            hdr = "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |"
            assert hdr in final_authority, "%s: real complete header control must survive" % cn
            assert not stray, "%s: stray temp/lock artifacts %s" % (cn, stray)
            verdict["classification"] = "success_full_set"
            verdict["active_keys"] = keys
        else:  # five col: success-full-set OR explicit zero-write refusal
            assert not stray, "%s: stray temp/lock artifacts %s" % (cn, stray)
            if zero_write:
                assert (r.get("ok") is False or (r.get("rc") not in (0, None)) or r.get("exception")), \
                    "%s: zero write must be an explicit refusal: %s" % (cn, r)
                verdict["classification"] = "zero_write_refusal"
            else:
                keys = _independent_active_keys(r.get("authority"))
                assert r.get("projection") == _expected_projection(keys), \
                    "%s: success must preserve exact full set: %s" % (cn, r)
                assert "foreign" in keys and "legacy-five" in keys, \
                    "%s: 5-col success must not drop rows: %s" % (cn, keys)
                verdict["classification"] = "success_full_set"
                verdict["active_keys"] = keys
        summary[cn] = verdict
        print("[MWFA][MATRIX] %s kind=%s -> %s" % (cn, kind, verdict["classification"]))

    _ev_json("matrix-results.json", summary)
    print("[MWFA][MATRIX] cases=%d legal/illegal/five all measured; 3 writers (ts-claim/ts-upsert/framework/conductor)" % len(summary))


# ── TEST 2: real cmd_init black-box (no private _projection_shape pre-assert) ─
def test_real_cmd_init_matrix(helpers, tmp_path):
    node_h, py_h = helpers
    root = tmp_path / "init"
    root.mkdir()
    global_ext = root / "global-ext"

    init_cases = {
        "personal_array": b'# Personal Notes\nactive_keys: ["my-list"]\n',
        "personal_scalar": b'# Personal Notes\nactive: my-list\n',
        "canonical_array": b'# AgenticTask Index\n\nactive_keys: ["stale"]\n',
        "legacy_scalar": b'# legacy\nactive: stale\n',
    }
    authority = _authority(["| k1 | active | EXECUTE | otherhost:1 | - | d | 2026-01-01 00:00 |"])
    py_cases, meta = [], {}
    for name, md in init_cases.items():
        project = root / name
        ad = project / ".agenticdoc"
        (project / ".mw").mkdir(parents=True, exist_ok=True)
        ad.mkdir(parents=True, exist_ok=True)
        (ad / "_index.parallel").write_bytes(authority.encode("utf-8"))
        (ad / "_index.md").write_bytes(md)
        meta[name] = {"md_before": md, "authority_before": (ad / "_index.parallel").read_bytes()}
        py_cases.append({"name": name, "writer": "init", "ad": str(ad), "project": str(project)})

    cases_file = root / "init_cases.json"
    cases_file.write_text(json.dumps(py_cases), encoding="utf-8", newline="\n")
    env = _child_env(root / "tmp")
    run = subprocess.run(
        [sys.executable, "-X", "utf8", str(py_h), "batch", str(_UPDATE_INDEX),
         str(cases_file), str(global_ext), str(_AUTOPILOT_PKG)],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, "init batch failed: " + run.stderr[-2000:]
    results = {r["case"]: r for r in _markers(run.stdout)}
    assert len(results) == len(init_cases)

    summary = {}
    for name, m in meta.items():
        r = results[name]
        project = root / name
        md_after = (project / ".agenticdoc" / "_index.md").read_bytes()
        authority_after = (project / ".agenticdoc" / "_index.parallel").read_bytes()
        assert authority_after == m["authority_before"], "%s: cmd_init must not rewrite authority" % name
        expected_keys = _independent_active_keys(authority)
        expected_proj = _expected_projection(expected_keys)
        verdict = {"rc": r.get("rc"), "exception": r.get("exception"),
                   "md_preserved": md_after == m["md_before"],
                   "projection": r.get("projection"), "expected": expected_proj,
                   "incomplete_stderr": "INCOMPLETE" in (r.get("stderr") or "")}
        if name in ("personal_array", "personal_scalar"):
            assert r.get("rc") == 1, "%s: user content must be INCOMPLETE (rc1): %s" % (name, r)
            assert md_after == m["md_before"], "%s: user content bytes must be preserved" % name
            assert verdict["incomplete_stderr"], "%s: INCOMPLETE must be reported" % name
            verdict["classification"] = "incomplete_preserved"
        else:  # canonical / legacy: real cmd_init migrates/corrects to exact set
            assert r.get("rc") == 0, "%s: canonical/legacy must migrate (rc0): %s" % (name, r)
            assert md_after.decode("utf-8") == expected_proj, \
                "%s: projection must equal exact active set %r, got %r" % (name, expected_proj, md_after)
            verdict["classification"] = "migrated_to_exact"
        summary[name] = verdict
        print("[MWFA][INIT] %s -> %s (rc=%s)" % (name, verdict["classification"], r.get("rc")))
    _ev_json("init-results.json", summary)


# ── TEST 3: four REAL lock-IO groups, both languages alternating as winner ──
_LOCK_GROUPS = [("node", "same"), ("python", "same"),
                ("node", "diff"), ("python", "diff")]


def _spawn(argv, cwd, env, creates):
    p = subprocess.Popen(argv, cwd=cwd, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ct = None
    try:
        import psutil
        ct = psutil.Process(p.pid).create_time()
    except Exception:
        ct = None
    creates.append((p, p.pid, ct))
    return p


def _safe_kill(p, ct):
    # only kill the process WE created; verify creation time to avoid a reused pid
    if p.poll() is not None:
        return
    if ct is not None:
        try:
            import psutil
            if abs(psutil.Process(p.pid).create_time() - ct) > 0.5:
                return
        except Exception:
            return
    p.kill()


@pytest.mark.parametrize("winner,rel", _LOCK_GROUPS)
def test_real_lock_io_four_groups(helpers, tmp_path, winner, rel):
    node_h, py_h = helpers
    base = tmp_path / ("lock_%s_%s" % (winner, rel))
    control = base / "control"       # harness markers: OUTSIDE project root
    project = base / "project"
    ad = project / ".agenticdoc"
    control.mkdir(parents=True)

    if rel == "same":
        authority = _authority([_FOREIGN])
        initial_proj = _expected_projection(_independent_active_keys(authority))
        wkey = lkey = "race-key"
    else:
        authority = _authority([_FOREIGN])
        initial_proj = _expected_projection(_independent_active_keys(authority))
        wkey, lkey = "key-w", "key-l"
    _setup_project(project, authority, initial_proj)
    _seed_lock_project_data(project, [wkey, lkey])

    lock_path = (project / ".mw" / "index.lock")
    env = _child_env(control / "tmp")
    creates = []

    def node_argv(tag, role, key):
        return [_node(), "--experimental-strip-types", "--no-warnings", str(node_h),
                "locknode", str(_TS_MODULE), str(ad), key, "self", str(control), tag, role, rel]

    def py_argv(tag, role, key):
        return [sys.executable, "-X", "utf8", str(py_h), "lockclaim",
                str(_UPDATE_INDEX), str(ad), key, "self", str(control), tag, role, rel]

    wproc = None
    lproc = None
    try:
        # 1) start WINNER; it really acquires the lock and HOLDS it via a gate.
        if winner == "node":
            wproc = _spawn(node_argv("w", "winner", wkey), str(_REPO), env, creates)
            l_argv = py_argv("l", "loser", lkey)
        else:
            wproc = _spawn(py_argv("w", "winner", wkey), str(_REPO), env, creates)
            l_argv = node_argv("l", "loser", lkey)

        # 2) wait for the winner's REAL acquired IO event (not a waiting label).
        w_acq = _wait_file(control / "w.first_acquired", 30.0)
        assert w_acq["ev"] == "acquired", w_acq
        assert os.path.normcase(w_acq["path"]) == os.path.normcase(str(lock_path)), \
            "winner acquired a DIFFERENT lock path: %s" % w_acq["path"]
        assert (w_acq.get("flags") == "wx" or int(w_acq.get("flags", 0)) & os.O_EXCL), \
            "winner did not use real wx/O_EXCL: %s" % w_acq

        # 3) start LOSER while winner still holds; it must make a REAL EEXIST attempt.
        lproc = _spawn(l_argv, str(_REPO), env, creates)
        l_eexist = _wait_file(control / "l.eexist", 30.0)
        assert l_eexist["ev"] == "eexist", l_eexist
        assert os.path.normcase(l_eexist["path"]) == os.path.normcase(str(lock_path)), \
            "loser EEXIST on a DIFFERENT lock path: %s" % l_eexist["path"]
        assert l_eexist.get("errno") in ("EEXIST", 17), l_eexist

        # 4) NOW release the winner (after the loser's real failed attempt).
        (control / "winner_gate").write_text("release", encoding="utf-8")

        # 5) winner result/wrote/alive, then same-key loser gated AFTER its
        # successful real open and BEFORE the fd reaches the claim predicate.
        group = "lock-%s-%s" % (winner, rel)
        loser_lang = "python" if winner == "node" else "node"
        bytes_events = None
        winner_alive_at_snapshot = None
        w_result = _wait_file(control / "w.result", 30.0)
        w_wrote = _wait_file(control / "w.wrote", 30.0)
        w_alive = _wait_file(control / "w.alive", 30.0)
        assert w_result["ok"] is True, "winner claim did not succeed: %s" % w_result
        assert w_result["pid"] == wproc.pid, "winner result PID mismatch: %s" % w_result
        winner_alive_at_snapshot = (wproc.poll() is None
                                    and (control / "w.alive").exists()
                                    and not (control / "winner_alive_gate").exists())
        assert winner_alive_at_snapshot, "winner must be alive at the snapshot point"
        if rel == "same":
            gated = _wait_file(control / "l.gated_acquired", 30.0)
            assert gated["ev"] == "gated_acquired", gated
            assert gated["real_open_success"] is True, "loser gate was not a successful real open: %s" % gated
            assert gated["fd_released_to_caller"] is False, "fd already delivered before snapshot: %s" % gated
            assert gated["pid"] == lproc.pid, "gated loser PID mismatch: %s" % gated
            assert os.path.normcase(gated["path"]) == os.path.normcase(str(lock_path)), \
                "gated loser acquired a DIFFERENT lock path: %s" % gated["path"]
            w_unlink_calls = _wait_io_event(control / "w.iolog.jsonl", "unlink_call_attempt", "w", 30.0)
            w_released_before = _wait_io_event(control / "w.iolog.jsonl", "released", "w", 30.0)
            l_acq_before = _wait_io_event(control / "l.iolog.jsonl", "acquired", "l", 30.0)
            assert min(e["at_ms"] for e in w_released_before) <= gated["at_ms"], \
                "winner post-success unlink was not observed before gated loser acquire"
            w_io_before = _read_io_events(control / "w.iolog.jsonl")
            l_io_before = _read_io_events(control / "l.iolog.jsonl")
            before_map = _data_bytes(project)
            assert before_map, "full data snapshot unexpectedly empty"
            before_record = _bytes_record(before_map)
            before_digest = _snapshot_digest(before_map)
            before_paths = sorted(before_map)
            _ev_json(group + "-bytes-before.json", {
                "group": group, "run_id": _RUN_ID, "command_run_id": _COMMAND_RUN_ID,
                "pytest_pid": os.getpid(),
                "command_start_utc": _COMMAND_START_UTC, "runner_pid": _RUNNER_PID,
                "winner_pid": wproc.pid, "loser_pid": lproc.pid,
                "gated_marker": gated, "winner_result": w_result,
                "snapshot": {"digest": before_digest, "paths": before_paths, "files": before_record},
                "snapshot_excluded_paths": [".mw/index.lock"],
                "snapshot_serialization": "evidence only; no authorization",
            })
            print("[MWFA][BYTES] %s run=%s wpid=%s lpid=%s before_paths=%d before_digest=%s gate=held" % (
                group, _RUN_ID, wproc.pid, lproc.pid, len(before_paths), before_digest), flush=True)

        # 6) release loser gate, wait for the loser's REAL verdict; winner stays alive.
        if rel == "same":
            (control / "loser_gate").write_text("release", encoding="utf-8")
        l_result = _wait_file(control / "l.result", 30.0)
        winner_alive_at_verdict = (wproc.poll() is None
                                   and (control / "w.alive").exists()
                                   and not (control / "winner_alive_gate").exists())
        assert winner_alive_at_verdict, "winner must be alive (holding gate) at loser's verdict"
        if rel == "same":
            after_map = _data_bytes(project)
            after_record = _bytes_record(after_map)
            after_digest = _snapshot_digest(after_map)
            after_paths = sorted(after_map)
            diff = _diff_data_snapshots(before_map, after_map)
            assert not diff["created"] and not diff["deleted"] and not diff["changed"], \
                "same-key loser changed project data: %s" % diff
            assert after_map == before_map, "same-key loser changed data PATHS or BYTES"
            assert after_digest == before_digest, "same-key snapshot digest changed"
            probe_path = ".agenticdoc/t22-probe-new.bin"
            first_path = sorted(before_map)[0]
            probe_created = dict(before_map)
            probe_created[probe_path] = b"x"
            probe_deleted = dict(before_map)
            probe_deleted.pop(first_path)
            probe_changed = dict(before_map)
            probe_changed[first_path] = before_map[first_path] + b"x"
            probe_created_diff = _diff_data_snapshots(before_map, probe_created)
            probe_deleted_diff = _diff_data_snapshots(before_map, probe_deleted)
            probe_changed_diff = _diff_data_snapshots(before_map, probe_changed)
            assert probe_created_diff["created"] == [probe_path], "new-write detector failed"
            assert probe_deleted_diff["deleted"] == [first_path], "delete detector failed"
            assert probe_changed_diff["changed"] == [first_path], "byte-change detector failed"
            bytes_events = {
                "group": group, "run_id": _RUN_ID, "command_run_id": _COMMAND_RUN_ID,
                "pytest_pid": os.getpid(),
                "command_start_utc": _COMMAND_START_UTC, "runner_pid": _RUNNER_PID,
                "winner_lang": winner, "loser_lang": loser_lang, "relation": rel,
                "winner_pid": wproc.pid, "loser_pid": lproc.pid,
                "winner_result_pid": w_result["pid"], "gated_loser_pid": gated["pid"],
                "lock_path": str(lock_path), "gated_marker": gated,
                "winner_wrote": w_wrote, "winner_alive": w_alive,
                "winner_unlink_call_attempt_at_ms": min(e["at_ms"] for e in w_unlink_calls),
                "winner_post_success_released_at_ms": min(e["at_ms"] for e in w_released_before),
                "loser_gated_acquired_at_ms": gated["at_ms"],
                "loser_first_acquired_at_ms": min(e["at_ms"] for e in l_acq_before),
                "io_event_counts_before": {"winner": len(w_io_before), "loser": len(l_io_before)},
                "winner_alive_at_snapshot": winner_alive_at_snapshot,
                "winner_alive_at_loser_verdict": winner_alive_at_verdict,
                "snapshot_excluded_paths": [".mw/index.lock"],
                "control_markers": "outside project root",
                "before": {"digest": before_digest, "path_count": len(before_paths),
                            "paths": before_paths, "files": before_record},
                "after": {"digest": after_digest, "path_count": len(after_paths),
                           "paths": after_paths, "files": after_record},
                "diff": diff,
                "synthetic_detector_probe": {
                    "created": probe_created_diff, "deleted": probe_deleted_diff,
                    "changed": probe_changed_diff},
                "assertions_reached": {
                    "gated_loser_successful_real_open": gated["real_open_success"] is True,
                    "fd_not_released_before_snapshot": gated["fd_released_to_caller"] is False,
                    "winner_post_success_released_observed": bool(w_released_before),
                    "winner_alive_at_snapshot": winner_alive_at_snapshot,
                    "winner_alive_at_loser_verdict": winner_alive_at_verdict,
                    "path_sets_equal": before_paths == after_paths,
                    "all_bytes_equal": after_map == before_map,
                    "digests_equal": after_digest == before_digest,
                    "new_write_detector": probe_created_diff["created"] == [probe_path],
                    "delete_detector": probe_deleted_diff["deleted"] == [first_path],
                    "byte_change_detector": probe_changed_diff["changed"] == [first_path],
                },
                "snapshot_serialization": "evidence only; no authorization",
                "acquired_semantics": "acquired is logged only after the real open returned an fd; EEXIST is rethrown",
                "release_event_semantics": "unlink_call_attempt is pre-unlink; released is post-success",
            }
            _ev_json(group + "-bytes.json", bytes_events)
            print("[MWFA][BYTES] %s run=%s wpid=%s lpid=%s before=%s after=%s paths=%d created=%d deleted=%d changed=%d full_data_bytes_equal=True assertions_reached=True" % (
                group, _RUN_ID, wproc.pid, lproc.pid, before_digest, after_digest,
                len(after_paths), len(diff["created"]), len(diff["deleted"]),
                len(diff["changed"])), flush=True)

        # 7) release winner's alive gate, collect both.
        (control / "winner_alive_gate").write_text("release", encoding="utf-8")
        w_out, w_err = wproc.communicate(timeout=30)
        l_out, l_err = lproc.communicate(timeout=30)
        w_final = _markers(w_out.decode("utf-8", "replace"))[0]
        l_final = _markers(l_out.decode("utf-8", "replace"))[0]

        # 8) merge the REAL IO logs (acquired/released/EEXIST with timestamps).
        w_io = [json.loads(x) for x in (control / "w.iolog.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        l_io = [json.loads(x) for x in (control / "l.iolog.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        merged = sorted(w_io + l_io, key=lambda e: e["at_ms"])
        group = "lock-%s-%s" % (winner, rel)
        _ev(group + "-io.jsonl", "\n".join(json.dumps(e) for e in merged) + "\n")

        w_acq_all = [e for e in merged if e["tag"] == "w" and e["ev"] == "acquired"]
        w_unlink_call_all = [e for e in merged if e["tag"] == "w" and e["ev"] == "unlink_call_attempt"]
        w_rel_all = [e for e in merged if e["tag"] == "w" and e["ev"] == "released"]
        l_eex_all = [e for e in merged if e["tag"] == "l" and e["ev"] == "eexist"]
        l_acq_all = [e for e in merged if e["tag"] == "l" and e["ev"] == "acquired"]
        assert w_acq_all and w_unlink_call_all and w_rel_all, \
            "winner must have real acquired + pre-unlink call-attempt + post-success released events"
        assert min(e["at_ms"] for e in w_unlink_call_all) <= min(e["at_ms"] for e in w_rel_all), \
            "pre-unlink call-attempt must not be after post-success release"
        assert l_eex_all, "loser must have a REAL EEXIST attempt"
        assert l_acq_all, "loser must EVENTUALLY really acquire the lock after winner releases"
        # acquisition ORDER from REAL IO timestamps (NOT gate issuance / finish-name sort)
        assert min(a["at_ms"] for a in w_acq_all) < min(a["at_ms"] for a in l_eex_all), \
            "winner real acquire must precede loser real EEXIST"
        assert min(a["at_ms"] for a in l_eex_all) < min(a["at_ms"] for a in l_acq_all), \
            "loser real EEXIST must precede its successful acquire"
        assert min(a["at_ms"] for a in w_acq_all) < min(a["at_ms"] for a in l_acq_all), \
            "REAL acquisition order: winner before loser"

        # 9) final-state assertions.
        final_authority = (ad / "_index.parallel").read_text(encoding="utf-8")
        final_projection = (ad / "_index.md").read_text(encoding="utf-8")
        keys = _independent_active_keys(final_authority)
        assert final_projection == _expected_projection(keys), \
            "projection must be exact %r, got %r" % (_expected_projection(keys), final_projection)
        # foreign row fields must be unchanged (D-005/AC-001)
        assert _FOREIGN in final_authority, "foreign-live original row must be preserved verbatim"

        if rel == "same":
            # exactly ONE active row for race-key, owned by the winner; loser zero data write.
            race_rows = [l for l in final_authority.splitlines()
                         if l.startswith("|") and l.split("|")[1].strip() == wkey]
            assert len(race_rows) == 1, "same-key: exactly one row for %s: %s" % (wkey, race_rows)
            assert "active" in race_rows[0], "same-key: winner's row must be active"
            assert w_final["self"] in race_rows[0], "same-key: winner's claimId must own the row"
            assert l_final["ok"] is False, "same-key: loser must be refused (conflict), got %s" % l_final
            assert "CONFLICT" in (l_final.get("stderr") or "") or l_final.get("blockedBy") or l_final.get("refusal"), \
                "same-key: loser refusal must be a real conflict verdict: %s" % l_final
            verdict = "same-key one-winner + loser full-data byte zero-write asserted"
        else:
            assert wkey in keys and lkey in keys, \
                "different-key: both keys must coexist active, got %s" % keys
            assert w_final["ok"] is True and l_final["ok"] is True, \
                "different-key: both claims must succeed: w=%s l=%s" % (w_final["ok"], l_final["ok"])
            verdict = "different-key both keys coexist"

        leftover = _no_temp_artifacts(_snap(project))
        assert not leftover, "no temp/lock leftovers in project: %s" % leftover

        events = {
            "group": group, "winner_lang": winner, "loser_lang": loser_lang, "relation": rel,
            "run_id": _RUN_ID, "command_run_id": _COMMAND_RUN_ID, "pytest_pid": os.getpid(),
            "command_start_utc": _COMMAND_START_UTC, "runner_pid": _RUNNER_PID,
            "wkey": wkey, "lkey": lkey,
            "lock_path": str(lock_path),
            "winner_pid": w_final["pid"], "loser_pid": l_final["pid"],
            "winner_self": w_final["self"], "loser_self": l_final["self"],
            "winner_alive_at_loser_verdict": winner_alive_at_verdict,
            "winner_acquired_first_at_ms": min(a["at_ms"] for a in w_acq_all),
            "loser_first_eexist_at_ms": min(a["at_ms"] for a in l_eex_all),
            "winner_first_unlink_call_attempt_at_ms": min(a["at_ms"] for a in w_unlink_call_all),
            "winner_post_success_released_at_ms": min(a["at_ms"] for a in w_rel_all),
            "loser_first_acquired_at_ms": min(a["at_ms"] for a in l_acq_all),
            "winner_alive_at_snapshot": winner_alive_at_snapshot,
            "full_data_byte_snapshot_assertion_reached": rel == "same" and bytes_events is not None,
            "acquired_semantics": "acquired is a successful real open that returned an fd; EEXIST is rethrown",
            "release_event_semantics": "unlink_call_attempt is pre-unlink; released is post-success",
            "io_event_count": len(merged),
            "w_acquired": len(w_acq_all), "w_released": len(w_rel_all),
            "l_eexist": len(l_eex_all), "l_acquired": len(l_acq_all),
            "w_ok": w_final["ok"], "l_ok": l_final["ok"],
            "l_refusal": (l_final.get("stderr") or "")[-300:],
            "final_active_keys": keys, "verdict": verdict,
        }
        _ev_json(group + "-events.json", events)
        print("[MWFA][LOCK] %s winner=%s wpid=%s lpid=%s acq_order(real)=%s<%s<%s verdict=%s" % (
            group, winner, w_final["pid"], l_final["pid"],
            events["winner_acquired_first_at_ms"], events["loser_first_eexist_at_ms"],
            events["loser_first_acquired_at_ms"], verdict))
    finally:
        # release every gate, then clean up ONLY processes we explicitly created
        for f in ("winner_gate", "loser_gate", "winner_alive_gate"):
            try:
                (control / f).write_text("release", encoding="utf-8")
            except OSError:
                pass
        for (p, pid, ct) in creates:
            try:
                out, err = p.communicate(timeout=6)
            except subprocess.TimeoutExpired:
                _safe_kill(p, ct)
                try:
                    p.communicate(timeout=6)
                except subprocess.TimeoutExpired:
                    pass
        shutil.rmtree(base, ignore_errors=True)


# ── TEST 4: preserve OLD T-12 scenarios by reusing its REAL helper strings ──
def test_preserve_old_scenarios_with_t12_helpers(helpers, tmp_path):
    """0/1/N three-writer projection bytes, D005 non-target byte preservation,
    and partial recovery, via the OLD T-12 Node/Python helpers (real fixtures,
    no mocked predicate). The unchanged old T-12 file is also run as-is by the
    acceptance command; these scenarios are retained, not deleted."""
    py_final_h = helpers[1]
    root = tmp_path / "preserve"
    root.mkdir()
    node_h = root / "t12_node.mjs"
    py_h = root / "t12_py.py"
    node_h.write_text(T12.NODE_HELPER, encoding="utf-8", newline="\n")
    py_h.write_text(T12.PY_HELPER, encoding="utf-8", newline="\n")
    env = _child_env(root / "tmp")

    def node_run(mode, *args):
        return subprocess.run([_node(), "--experimental-strip-types", "--no-warnings",
                               str(node_h), mode, str(T12._TS_MODULE), *(str(a) for a in args)],
                              cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=90)

    def py_run(mode, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(py_h), mode,
                               str(T12._UPDATE_INDEX), *(str(a) for a in args)],
                              cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=90)

    def t12_marker(stdout):
        lines = [l for l in stdout.splitlines() if l.startswith("MWCL_JSON ")]
        return [json.loads(l[len("MWCL_JSON "):]) for l in lines]

    # 0/1/N: three REAL writers on identical authority must yield byte-equal
    # canonical _index.md projections; no row dropped, active set preserved.
    active_sets = [[], ["k-one"], ["Key-A", "key-b", "MW-Key.C_2"]]
    byte_equal = {}
    for count, actives in enumerate(active_sets):
        rows = []
        for k in actives:
            rows.append("| %s | active | EXECUTE | otherhost:1 | - | d | 2026-01-01 00:00 |" % k)
        rows.append(_ANCHOR)
        authority = _authority(rows)
        projections = []
        for writer in ("node", "framework", "conductor"):
            p = root / ("z%d_%s" % (count, writer))
            proj, ad = _setup_project(p, authority)
            if writer == "node":
                entry = {"key": "anchor", "status": "idle", "phase": "SPEC",
                         "claimId": "-", "deps": "-", "desc": "anchor desc",
                         "updated": "2026-01-01 00:00"}
                r = node_run("upsert", str(ad), json.dumps(entry))
                m = t12_marker(r.stdout)[0]
                projections.append(m["projection"])
            elif writer == "framework":
                r = py_run("framework", str(ad), "set-phase", "anchor", "PLAN")
                m = t12_marker(r.stdout)[0]
                projections.append(m["projection"])
            else:
                r = py_run("conductor", str(proj), str(_AUTOPILOT_PKG), "anchor", "host:1")
                m = t12_marker(r.stdout)[0]
                projections.append(m["projection"])
        keys = _independent_active_keys(authority)
        expected = _expected_projection(keys)
        assert all(pr == expected for pr in projections), \
            "0/1/N count=%d: three writers must produce identical exact projection %r, got %r" % (
                count, expected, projections)
        byte_equal[str(count)] = {"active": actives, "three_writer_bytes_equal": True,
                                  "projection": expected}
        print("[MWFA][PRESERVE] 0/1/N count=%d active=%s three_writer_bytes_equal=True" % (count, actives))

    # D005: conductor set_claim preserves ALL non-target authority bytes while
    # the fixture genuinely contains CRLF, LF and a no-terminal-newline line.
    # T12.authority/projection/expected_projection/assert_clean and the
    # per-line keepends oracle below are independent of the product.
    mixed_foreign = "| foreign | active | EXECUTE | otherhost:9 | - | fd | 2026-01-01 00:00 |"
    crlf, lf = _CRLF_B, _LF_B
    d005_raw = (
        b"# Index Parallel" + crlf + crlf +
        b"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |" + crlf +
        b"|-----|--------|-------|---------|------|------|---------|" + crlf +
        mixed_foreign.encode("utf-8") + crlf +
        b"# a comment line" + lf +
        b"| anchor | active | SPEC | - | - | anchor desc | 2026-01-01 00:00 |" + lf +
        b"#  comment with  inner spacing " + crlf +
        b"| parked | idle | PLAN | - | - | parked desc | 2026-01-01 00:00 |" + crlf +
        b"# trailing no terminal newline")
    p = root / "d005"
    proj, ad = _setup_project(p, _LF, _STALE_PROJECTION)
    (ad / "_index.parallel").write_bytes(d005_raw)
    before = T12.authority(proj)
    before_lines = before.splitlines(keepends=True)
    crlf_lines_before = [i for i, line in enumerate(before_lines) if line.endswith(crlf)]
    lf_lines_before = [i for i, line in enumerate(before_lines) if line.endswith(lf) and not line.endswith(crlf)]
    no_eol_lines_before = [i for i, line in enumerate(before_lines)
                           if not (line.endswith(lf) or line.endswith(crlf))]
    assert crlf_lines_before and lf_lines_before, \
        "D005 fixture must contain BOTH CRLF and LF before the real conductor call"
    assert no_eol_lines_before and not before.endswith((crlf, lf)), \
        "D005 fixture must contain a no-terminal-newline line before the call"
    r = py_run("conductor", str(proj), str(_AUTOPILOT_PKG), "anchor", "host:77")
    m = t12_marker(r.stdout)[0]
    after = T12.authority(proj)
    after_lines = after.splitlines(keepends=True)
    assert r.returncode == 0 and m["ok"] is True, "D005: real conductor set_claim must succeed: %s" % m
    assert len(before_lines) == len(after_lines), \
        "D005: line count/order changed: %d -> %d" % (len(before_lines), len(after_lines))
    target_indices = [i for i, line in enumerate(before_lines) if line.startswith(b"| anchor |")]
    assert len(target_indices) == 1, "D005: exactly one target row must exist: %s" % target_indices
    target_idx = target_indices[0]
    non_target_facts = []
    for i, (was, now) in enumerate(zip(before_lines, after_lines)):
        if i == target_idx:
            continue
        assert was == now, "D005: non-target line %d bytes changed: %r -> %r" % (i, was, now)
        non_target_facts.append({"index": i, "before_hex": was.hex(),
                                  "after_hex": now.hex(), "equal": was == now})
    target_eol = crlf if before_lines[target_idx].endswith(crlf) else (lf if before_lines[target_idx].endswith(lf) else b"")
    assert target_eol == lf, "D005: target row must be the LF variant in this fixture"
    assert before_lines[target_idx] != after_lines[target_idx], "D005: target claim cell did not change"
    assert after_lines[target_idx].endswith(target_eol), "D005: target row line ending was normalized"
    assert after_lines[target_idx].startswith(b"| anchor | active | SPEC | host:77 |"), \
        "D005: target-only claim change not observed: %r" % after_lines[target_idx]
    assert not after.endswith((crlf, lf)), "D005: final no-terminal-newline bytes were normalized"
    # Preserve the old fragment assertions, but the proof above is byte-exact.
    assert (b"# a comment line" + lf) in after, "D005: non-target comment byte must survive"
    assert mixed_foreign.encode("utf-8") in after, "D005: foreign row bytes must survive"
    assert m["value"] is True or m["rows"], "D005: conductor set_claim must run"
    projection_bytes = T12.projection(proj)
    expected_projection_bytes = T12.expected_projection(T12.active_keys(proj))
    assert projection_bytes == expected_projection_bytes, \
        "D005: projection not exact %r, got %r" % (expected_projection_bytes, projection_bytes)
    T12.assert_clean(proj)
    crlf_lines_after = [i for i, line in enumerate(after_lines) if line.endswith(crlf)]
    lf_lines_after = [i for i, line in enumerate(after_lines) if line.endswith(lf) and not line.endswith(crlf)]
    no_eol_lines_after = [i for i, line in enumerate(after_lines)
                          if not (line.endswith(lf) or line.endswith(crlf))]
    d005_facts = {
        "run_id": _RUN_ID, "command_run_id": _COMMAND_RUN_ID, "pytest_pid": os.getpid(),
        "command_start_utc": _COMMAND_START_UTC, "runner_pid": _RUNNER_PID,
        "call": "T12 PY_HELPER conductor -> autopilot.index_parallel.set_claim(project, 'anchor', claim_id='host:77')",
        "target_only": True, "no_text_normalization_for_byte_proof": True,
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "before_lines_hex": [line.hex() for line in before_lines],
        "after_lines_hex": [line.hex() for line in after_lines],
        "before_eol": {"crlf_line_indices": crlf_lines_before,
                        "lf_line_indices": lf_lines_before,
                        "no_eol_line_indices": no_eol_lines_before,
                        "fixture_has_both_eol_forms": bool(crlf_lines_before and lf_lines_before),
                        "fixture_has_no_terminal_newline": not before.endswith((crlf, lf))},
        "after_eol": {"crlf_line_indices": crlf_lines_after,
                       "lf_line_indices": lf_lines_after,
                       "no_eol_line_indices": no_eol_lines_after,
                       "fixture_has_both_eol_forms": bool(crlf_lines_after and lf_lines_after),
                       "fixture_has_no_terminal_newline": not after.endswith((crlf, lf))},
        "line_count_before": len(before_lines), "line_count_after": len(after_lines),
        "target_index": target_idx,
        "target_line_before_hex": before_lines[target_idx].hex(),
        "target_line_after_hex": after_lines[target_idx].hex(),
        "non_target_line_facts": non_target_facts,
        "all_non_target_lines_byte_equal": len(non_target_facts) == len(before_lines) - 1 and all(f["equal"] for f in non_target_facts),
        "projection_exact_hex": expected_projection_bytes.hex(),
        "projection_oracle": "T12.expected_projection(T12.active_keys(project)), independent of product",
        "assertions_reached": {
            "fixture_both_eol_forms_before_call": bool(crlf_lines_before and lf_lines_before),
            "fixture_no_terminal_newline_before_call": not before.endswith((crlf, lf)),
            "real_set_claim_succeeded": m["ok"] is True,
            "line_count_and_order_equal": len(before_lines) == len(after_lines),
            "all_non_target_lines_byte_equal": len(non_target_facts) == len(before_lines) - 1 and all(f["equal"] for f in non_target_facts),
            "target_only_changed": before_lines[target_idx] != after_lines[target_idx],
            "target_eol_preserved": after_lines[target_idx].endswith(target_eol),
            "final_no_terminal_newline_preserved": not after.endswith((crlf, lf)),
            "projection_exact": projection_bytes == expected_projection_bytes,
            "t12_assert_clean": True,
        },
    }
    _ev_json("d005-mixed-eol-bytes.json", d005_facts)
    print("[MWFA][D005] run=%s pid=%d crlf=%d lf=%d no_eol=%d non_target=%d all_non_target_bytes_equal=True target_only_changed=True projection_exact=True assertions_reached=True before_sha=%s after_sha=%s" % (
        _RUN_ID, os.getpid(), len(crlf_lines_before), len(lf_lines_before),
        len(no_eol_lines_before), len(non_target_facts),
        d005_facts["before_sha256"], d005_facts["after_sha256"]), flush=True)

    # partial recovery: injected one-time projection failure, then a REAL second
    # mutation (PY_FINAL.partial) rebuilds the projection from authority.
    p2 = root / "partial"
    proj2, ad2 = _setup_project(p2, _authority(["| k | active | EXECUTE | otherhost:1 | - | d | 2026-01-01 00:00 |"]))
    r = subprocess.run([sys.executable, "-X", "utf8", str(py_final_h), "partial",
                        str(_UPDATE_INDEX), str(ad2), "k"],
                       cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=90)
    m = _markers(r.stdout)[0]
    assert m.get("firstPartial"), "partial must report PARTIAL: %s" % m
    assert m.get("projectionAttempts") == 2, "partial: projection must be attempted again on recovery: %s" % m
    assert m.get("secondRc") == 0, "partial: recovery mutation must succeed: %s" % m
    rebuilt = _expected_projection(_independent_active_keys(m["authority"]))
    assert m.get("projection") == rebuilt, "partial: projection rebuilt to exact set by real mutation: %s" % m
    print("[MWFA][PRESERVE] partial_write_visible=True recovery_by_real_mutation=True")

    _ev_json("preserve-results.json", {"run_id": _RUN_ID,
                                       "command_run_id": _COMMAND_RUN_ID,
                                       "pytest_pid": os.getpid(),
                                       "zero_one_many": byte_equal,
                                       "d005_non_target_bytes_preserved": True,
                                       "d005_mixed_eol": d005_facts,
                                       "partial_recovery": True})
