"""
mw.py — Multi-Workers service manager.

Subcommands:
  serve  — foreground: start proxy_multi + launcher, block until Ctrl-C/SIGTERM
  start  — background: detach and run serve
  stop   — send SIGTERM to running mw serve
  status — check if mw serve is running
  init   — install Extension bundle + AgenticTask framework into project
  pull-agentictask — clone/update the AgenticTask framework repo into .tmp/
  push-agentictask — commit+push local framework changes back to the remote repo
  setup  — one-time machine bootstrap: clone framework + install extension globally
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from mw_common import (
    check_pid as _check_pid,
    port_is_bound as _port_is_bound,
)

_SCRIPT_DIR = pathlib.Path(__file__).parent
_LAUNCHER_PY = _SCRIPT_DIR / "launcher.py"
_PROXY_MULTI_PY = _SCRIPT_DIR / "proxy_multi.py"

# Local, gitignored clone of the AgenticTask framework repo — the bootstrap
# fallback for `init` on machines without a live framework checkout.
# `pull-agentictask` clones it from the remote once (then fast-forward-updates
# it). Because it is a real git clone, `push-agentictask` can commit+push
# framework changes straight back to the remote — Multi-Workers only records
# the remote URL, not any local path. `.tmp/` stays gitignored here; the
# nested `.git` is an independent repo. `init` source priority (see
# _resolve_framework_source): --sync-agentictask > the mw checkout's own
# .agents/skills/agentic-task (dev machine: the live working repo) > this cache.
_TMP_AGENTICTASK = _SCRIPT_DIR / ".tmp" / "agentic-task"
_DEFAULT_AGENTICTASK_REMOTE = "https://github.com/wenbocode/AgenticTask.git"
_DEFAULT_AGENTICTASK_BRANCH = "master"
_AGENTICTASK_IGNORE = {".git", "__pycache__"}


def _is_git_url(s: str) -> bool:
    """Heuristic: does `s` name a git remote (vs. a local source directory)?"""
    return s.startswith(("http://", "https://", "git@", "ssh://")) or s.endswith(".git")


# ── Port helpers ─────────────────────────────────────────────────────────────
# _port_is_bound / _check_pid live in mw_common (shared with doctor).


def _source_desc(source: dict) -> str:
    return mw_common._source_desc(source)  # noqa: SLF001 - re-export for serve logging


# ── PID helpers ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _pid_path(project_dir: pathlib.Path) -> pathlib.Path:
    return mw_common.pid_file(project_dir)


def _write_pid(pid_path: pathlib.Path) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid(pid_path: pathlib.Path) -> None:
    try:
        pid_path.unlink()
    except FileNotFoundError:
        pass


def _stop_request_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".mw" / "mw.stop"


def _write_stop_request(project_dir: pathlib.Path) -> None:
    p = _stop_request_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stop", encoding="utf-8")


def _clear_stop_request(project_dir: pathlib.Path) -> None:
    try:
        _stop_request_path(project_dir).unlink()
    except FileNotFoundError:
        pass


# ── Subcommand: serve ────────────────────────────────────────────────────────

def cmd_serve(args: argparse.Namespace) -> int:
    import threading

    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    mw_dir = project_dir / ".mw"
    mw_dir.mkdir(parents=True, exist_ok=True)

    existing = _check_pid(pid_path)
    if existing is not None:
        print(
            f"[mw serve] already running (PID {existing}). Use 'mw stop' first.",
            file=sys.stderr,
        )
        return 1

    _clear_stop_request(project_dir)

    # ── Logging: redirect own stdout/stderr to mw.log ──
    mw_log = open(mw_dir / "mw.log", "a", encoding="utf-8")
    proxy_log = open(mw_dir / "proxy.log", "a", encoding="utf-8")
    # launcher.log is truncated per serve session: it belongs to the launcher
    # child of THIS serve instance, and stale FATAL lines from previous
    # (pre-fix) sessions would otherwise keep doctor reporting a false issue.
    launcher_log = open(mw_dir / "launcher.log", "w", encoding="utf-8")
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = mw_log
    sys.stderr = mw_log

    intentional_stop = threading.Event()
    exit_code = 1  # default: unexpected/error exit
    proxy_proc: subprocess.Popen[bytes] | None = None
    launcher_proc: subprocess.Popen[bytes] | None = None
    wrote_pid = False

    try:
        # ── Route precheck (design D-002 / AC-002, AC-003) ──
        # Runs BEFORE the PID file is written, so "PID file exists" implies
        # "service actually started" (the PM stable-window relies on it).
        # Default: the providers.json shipped next to mw.py (the package copy),
        # NOT the in-memory defaults — the file is the source of truth.
        providers_path = (
            pathlib.Path(args.providers)
            if args.providers
            else pathlib.Path(__file__).parent / "providers.json"
        )
        config = mw_common.load_providers(providers_path)
        precheck = mw_common.route_precheck(config, os.environ)
        for st in precheck["routes"]:
            if st["available"]:
                print(
                    f"[mw serve] route {st['route']}: available ({_source_desc(st['source'])})",
                    flush=True,
                )
            else:
                print(f"[mw serve] route {st['route']}: missing ({st['missing']})", flush=True)
        if precheck["all_missing"]:
            msg = "[mw serve] FATAL: no route has credentials; refusing to start. Set at least one credential (env or configured file source) before mw serve."
            print(msg, flush=True)
            print(msg, file=real_stderr, flush=True)
            exit_code = 1
            return 1

        _write_pid(pid_path)
        wrote_pid = True
        # Build spawn kwargs: hide console window on Windows
        spawn_kwargs: dict = {}
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        proxy_cmd = [
            sys.executable,
            str(_PROXY_MULTI_PY),
            f"--pi-port={args.pi_port}",
            f"--claude-port={args.claude_port}",
        ]
        if args.deepseek_port:
            proxy_cmd.append(f"--deepseek-port={args.deepseek_port}")
        # If another mw instance already has the proxy running on these ports,
        # share it instead of starting a second one (supports multiple pi windows).
        proxy_already_running = _port_is_bound(args.pi_port) and _port_is_bound(args.claude_port)
        if proxy_already_running:
            proxy_proc = None
            print(
                f"[mw serve] ports {args.pi_port}/{args.claude_port} already bound"
                " — sharing existing proxy",
                flush=True,
            )
        else:
            proxy_proc = subprocess.Popen(proxy_cmd, stdout=proxy_log, stderr=proxy_log, **spawn_kwargs)  # noqa: S603

        launcher_cmd = [
            sys.executable,
            str(_LAUNCHER_PY),
            f"--project={project_dir}",
            f"--poll-interval={args.poll_interval}",
            f"--pi-port={args.pi_port}",
            f"--claude-port={args.claude_port}",
        ]
        if args.deepseek_port:
            launcher_cmd.append(f"--deepseek-port={args.deepseek_port}")
        if args.max_workers:
            launcher_cmd.append(f"--max-workers={args.max_workers}")
        if args.providers:
            launcher_cmd.append(f"--providers={args.providers}")

        launcher_proc = subprocess.Popen(launcher_cmd, stdout=launcher_log, stderr=launcher_log, **spawn_kwargs)  # noqa: S603

        proxy_info = f"proxy={proxy_proc.pid}" if proxy_proc else "proxy=shared"
        print(
            f"[mw serve] started (PID {os.getpid()}) — {proxy_info} launcher={launcher_proc.pid}",
            flush=True,
        )

        if sys.platform != "win32":
            def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001
                intentional_stop.set()
            signal.signal(signal.SIGTERM, _on_sigterm)

        try:
            while True:
                if intentional_stop.is_set():
                    break
                if _stop_request_path(project_dir).exists():
                    _clear_stop_request(project_dir)
                    intentional_stop.set()
                    break
                if launcher_proc.poll() is not None:
                    break
                if proxy_proc is not None and proxy_proc.poll() is not None:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            intentional_stop.set()

        exit_code = 0 if intentional_stop.is_set() else 1

    finally:
        for proc in (launcher_proc, proxy_proc):
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                except Exception:
                    pass
        if wrote_pid:
            _remove_pid(pid_path)
        _clear_stop_request(project_dir)
        print("[mw serve] stopped", flush=True)
        # Restore the real streams (in-process callers like tests keep working)
        sys.stdout = real_stdout
        sys.stderr = real_stderr
        # Close log files
        mw_log.close()
        proxy_log.close()
        launcher_log.close()

    return exit_code


# ── Subcommand: start ────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace) -> int:
    """Detach and run mw serve in the background."""
    cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), "serve"]
    # Forward serve-relevant args
    cmd += [
        f"--project={args.project}",
        f"--pi-port={args.pi_port}",
        f"--claude-port={args.claude_port}",
        f"--poll-interval={args.poll_interval}",
    ]
    if args.max_workers:
        cmd.append(f"--max-workers={args.max_workers}")
    if args.providers:
        cmd.append(f"--providers={args.providers}")
    if args.deepseek_port:
        cmd.append(f"--deepseek-port={args.deepseek_port}")

    if sys.platform == "win32":
        # START /B equivalent: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS + CREATE_NO_WINDOW
        import subprocess as _sp

        proc = _sp.Popen(  # noqa: S603
            cmd,
            creationflags=_sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            start_new_session=True,
            close_fds=True,
        )

    print(f"[mw start] background PID: {proc.pid}")
    return 0


# ── Subcommand: stop ─────────────────────────────────────────────────────────

def cmd_stop(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is None:
        print("[mw stop] not running (no PID or process not found)")
        return 0
    _write_stop_request(project_dir)
    # Wait up to 30s for serve to exit (no force-kill)
    for _ in range(60):
        time.sleep(0.5)
        if _check_pid(pid_path) is None:
            print(f"[mw stop] stopped PID {pid}")
            return 0
    print(f"[mw stop] warning: process {pid} did not exit in 30s")
    return 1


# ── Subcommand: status ───────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is not None:
        print(f"[mw status] running (PID {pid})")
        return 0
    else:
        print("[mw status] not running")
        return 1


# ── Subcommand: doctor ───────────────────────────────────────────────────────

def cmd_doctor(args: argparse.Namespace) -> int:
    """One-shot full-chain diagnostic (service/proxy/orphan/log/queue/credentials/bundle).

    Exit 0 = healthy, 1 = issues found. --fix auto-fixes stale entries + stale
    PID; --json emits the machine-readable report (consumed by /mw doctor)."""
    project_dir = pathlib.Path(args.project).resolve()
    providers_path = (
        pathlib.Path(args.providers)
        if args.providers
        else pathlib.Path(__file__).parent / "providers.json"
    )
    config = mw_common.load_providers(providers_path)
    report = mw_common.doctor_report(project_dir, fix=args.fix, config=config, stale_after_sec=args.stale_after)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(mw_common.format_doctor_text(report))
    return 0 if report["summary"]["healthy"] else 1


# ── Subcommand: pull-agentictask ───────────────────────────────────────────────

def _git_short_commit(repo: pathlib.Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or "unknown"
    except Exception:
        return "unknown"


def _rmtree_robust(path: pathlib.Path) -> None:
    """rmtree that survives Windows read-only files (git pack/.idx are read-only,
    and plain shutil.rmtree raises PermissionError on them)."""
    def _on_error(func, p, _exc):
        try:
            os.chmod(p, 0o777)
        except OSError:
            pass
        func(p)
    # Python 3.12+ renamed onerror→onexc; pass onexc where available, else onerror.
    try:
        shutil.rmtree(path, onexc=_on_error)  # type: ignore[call-arg]
    except TypeError:
        shutil.rmtree(path, onerror=_on_error)


def _copy_agentictask_source(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy the framework source tree into the cache, excluding .git/__pycache__."""
    if dst.exists():
        _rmtree_robust(dst)
    shutil.copytree(
        str(src),
        str(dst),
        ignore=shutil.ignore_patterns(*_AGENTICTASK_IGNORE),
    )


def _git(args: list[str], *, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    """Run a git command, capturing output. Never raises on non-zero exit."""
    cmd = ["git"]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True)


def _validate_agentictask_install(dst: pathlib.Path) -> tuple[bool, str]:
    """An AgenticTask checkout must carry install.py (the installer we invoke later)."""
    if not (dst / "install.py").is_file():
        return False, f"{dst} does not look like an AgenticTask repo (missing install.py)."
    return True, ""


def _checkout_framework_dir() -> pathlib.Path:
    """The mw checkout's own AgenticTask install (dev machines only).

    mw.py always lives inside a Multi-Workers checkout; when that checkout has
    itself been mw-inited, this is the live working repo the framework is
    developed and published from — always fresher than any cache. The directory
    is untracked in the Multi-Workers repo, so it only exists where someone ran
    `mw init` on the checkout itself.
    """
    return _repo_root() / ".agents" / "skills" / "agentic-task"


def _resolve_framework_source(sync_source: str | None) -> pathlib.Path:
    """Pick the AgenticTask install source, freshest first:

    1. --sync-agentictask <dir>  (explicit override)
    2. the mw checkout's own .agents/skills/agentic-task — the live working
       repo on a dev machine; bypasses the cache entirely, so installs can
       never go stale behind it. May carry uncommitted state: commit & push
       first when you want published state propagated.
    3. the .tmp/agentic-task cache — bootstrap fallback; auto-cloned once from
       the default remote when missing, refreshed later via pull-agentictask.
    """
    if sync_source:
        return pathlib.Path(sync_source).resolve()
    checkout = _checkout_framework_dir()
    if (checkout / "install.py").is_file():
        return checkout
    if not (_TMP_AGENTICTASK / "install.py").is_file():
        pulled, pull_msg = _pull_agentictask(_DEFAULT_AGENTICTASK_REMOTE, force=False)
        print(f"[mw init] auto-pull: {pull_msg}")
    return _TMP_AGENTICTASK


def _pull_via_git(url: str, *, force: bool, branch: str) -> tuple[bool, str]:
    """Clone the framework repo into the cache, or fast-forward an existing clone.
    The cache becomes a real, independently pushable git repo (see push-agentictask)."""
    dst = _TMP_AGENTICTASK
    git_dir = dst / ".git"

    if git_dir.exists():
        # Existing clone → update in place, preserving local commits/edits.
        fetch = _git(["fetch", "origin"], cwd=dst)
        if fetch.returncode != 0:
            return False, f"git fetch failed: {(fetch.stderr or fetch.stdout).strip()}"
        if force:
            # Explicitly discard local state and align with the remote branch.
            reset = _git(["reset", "--hard", f"origin/{branch}"], cwd=dst)
            if reset.returncode != 0:
                return False, f"git reset --hard failed: {(reset.stderr or reset.stdout).strip()}"
        else:
            pull = _git(["pull", "--ff-only", "origin", branch], cwd=dst)
            if pull.returncode != 0:
                return False, (
                    f"git pull --ff-only failed (local diverged from origin/{branch}?): "
                    f"{(pull.stderr or pull.stdout).strip()} — resolve manually or use --force."
                )
    elif dst.exists():
        # A non-git cache (old copytree layout) sits here. Converting it to a clone
        # is destructive, so require --force before we rmtree it.
        if not force:
            return False, (
                f"non-git cache present at {dst}. Use --force to replace it with a fresh clone."
            )
        _rmtree_robust(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        clone = _git(["clone", "--branch", branch, url, str(dst)])
        if clone.returncode != 0:
            return False, f"git clone failed: {(clone.stderr or clone.stdout).strip()}"
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        clone = _git(["clone", "--branch", branch, url, str(dst)])
        if clone.returncode != 0:
            return False, f"git clone failed: {(clone.stderr or clone.stdout).strip()}"

    ok, err = _validate_agentictask_install(dst)
    if not ok:
        return False, err
    return True, f"cloned/updated from {url}@{branch} (commit {_git_short_commit(dst)}) → {dst}"


def _pull_via_copy(src: pathlib.Path, *, force: bool) -> tuple[bool, str]:
    """Copy a local framework source dir into the cache (no .git → not pushable).
    Fallback for offline/vendored sources; the git path is preferred."""
    src = src.resolve()
    if not src.is_dir():
        return False, f"source not found: {src}"
    ok, err = _validate_agentictask_install(src)
    if not ok:
        return False, err
    if _TMP_AGENTICTASK.exists() and not force:
        return True, f"cache already present: {_TMP_AGENTICTASK} (use --force to refresh)"
    _TMP_AGENTICTASK.parent.mkdir(parents=True, exist_ok=True)
    _copy_agentictask_source(src, _TMP_AGENTICTASK)
    return True, (
        f"copied from {src} (commit {_git_short_commit(src)}) → {_TMP_AGENTICTASK} "
        "(plain copy, no .git — not pushable; use a git URL for push support)"
    )


def _pull_agentictask(source: str, *, force: bool, branch: str = _DEFAULT_AGENTICTASK_BRANCH) -> tuple[bool, str]:
    """Populate the local cache. A git URL (or an absent local dir) clones/updates a
    real git repo; an existing local dir is copied byte-for-byte. Returns (ok, message)."""
    source = str(source)
    if _is_git_url(source):
        return _pull_via_git(source, force=force, branch=branch)
    # Non-URL: an existing local directory → copytree; otherwise treat as a git target
    # only if it looks like a URL (handled above). A missing local path is an error.
    return _pull_via_copy(pathlib.Path(source), force=force)


def cmd_pull_agentictask(args: argparse.Namespace) -> int:
    ok, msg = _pull_agentictask(args.source, force=args.force, branch=args.branch)
    if ok:
        print(f"[mw pull-agentictask] {msg}")
        return 0
    print(f"[mw pull-agentictask] Error: {msg}", file=sys.stderr)
    return 1


def cmd_push_agentictask(args: argparse.Namespace) -> int:
    """Commit (optional) + push local framework changes from the .tmp clone back to
    its remote. Requires the cache to be a real git clone (pull from a git URL first)."""
    dst = _TMP_AGENTICTASK
    if not (dst / ".git").exists():
        print(
            f"[mw push-agentictask] Error: {dst} is not a git clone. "
            "Run 'python mw.py pull-agentictask --force' (from a git URL) first.",
            file=sys.stderr,
        )
        return 1

    # Is the working tree dirty?
    status = _git(["status", "--porcelain"], cwd=dst)
    if status.returncode != 0:
        print(f"[mw push-agentictask] Error: git status failed: {(status.stderr or status.stdout).strip()}",
              file=sys.stderr)
        return 1
    dirty = bool(status.stdout.strip())

    if dirty:
        if not args.message:
            print(
                "[mw push-agentictask] Error: working tree has uncommitted changes. "
                "Pass -m/--message to commit them, or commit manually first.",
                file=sys.stderr,
            )
            return 1
        add = _git(["add", "-A"], cwd=dst)
        if add.returncode != 0:
            print(f"[mw push-agentictask] Error: git add failed: {(add.stderr or add.stdout).strip()}",
                  file=sys.stderr)
            return 1
        commit = _git(["commit", "-m", args.message], cwd=dst)
        if commit.returncode != 0:
            print(f"[mw push-agentictask] Error: git commit failed: {(commit.stderr or commit.stdout).strip()}",
                  file=sys.stderr)
            return 1
        print(f"[mw push-agentictask] committed: {args.message} ({_git_short_commit(dst)})")

    push = _git(["push", "origin", args.branch], cwd=dst)
    if push.returncode != 0:
        print(f"[mw push-agentictask] Error: git push failed: {(push.stderr or push.stdout).strip()}",
              file=sys.stderr)
        return 1
    print(f"[mw push-agentictask] pushed to origin/{args.branch} (commit {_git_short_commit(dst)})")
    return 0


# ── Subcommand: init ─────────────────────────────────────────────────────────

_BUNDLE_REL = pathlib.Path("dist") / "extensions" / "agent-team-loop.js"


def _bundle_path() -> pathlib.Path:
    return _SCRIPT_DIR / _BUNDLE_REL


def _check_bundle() -> bool:
    return _bundle_path().exists()


# ── Bundle build (bash-free, cwd-independent) ──────────────────────────────────

# Source entry point, relative to the repo root (mw.py lives at
# <repo>/packages/multi-workers/mw.py, so the root is two levels up).
_EXT_SRC_REL = (
    pathlib.Path("packages") / "coding-agent" / "src" / "extensions" / "agent-team-loop" / "index.ts"
)

# esbuild + self-check, driven by node. SRC/OUT come from env vars (MW_SRC/MW_OUT)
# so no Windows backslash ever lands inside a JS string literal. Mirrors the
# format/target/external contract of build-extension.sh (ESM so the host's
# jiti.import(path, {default:true}) unwraps the activate() function reliably).
_BUILD_NODE_SCRIPT = r"""
const esbuild = require('esbuild');
const { createJiti } = require('jiti');
const url = require('url');
const SRC = process.env.MW_SRC;
const OUT = process.env.MW_OUT;
esbuild.build({
  entryPoints: [SRC],
  bundle: true,
  outfile: OUT,
  platform: 'node',
  format: 'esm',
  target: 'node18',
  external: ['node:*'],
  logLevel: 'warning',
}).then(() => {
  const j = createJiti(url.pathToFileURL(process.cwd() + '/').href, { moduleCache: false });
  return j.import(OUT, { default: true });
}).then((f) => {
  if (typeof f !== 'function') {
    console.error('Self-check FAILED: host loader expects a function, got ' + typeof f);
    process.exit(1);
  }
  console.log('built + self-check OK (' + (f.name || 'anon') + ')');
}).catch((e) => {
  console.error('Build FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
"""


def _repo_root() -> pathlib.Path:
    return _SCRIPT_DIR.parent.parent


def _build_bundle() -> tuple[bool, str]:
    """Compile the agent-team-loop extension bundle with esbuild and self-check
    that it loads as a function (the host loader contract).

    Pure Python + node: no bash, no msys `pwd -W`, and cwd-independent — all
    paths derive from mw.py's own location, so ANY pi window can rebuild mw
    regardless of its working directory. node runs with cwd=repo root so that
    require('esbuild')/require('jiti') resolve from the repo's node_modules.
    """
    repo_root = _repo_root()
    src = repo_root / _EXT_SRC_REL
    out = _bundle_path()
    if not src.is_file():
        return False, f"extension source not found: {src}"
    node = shutil.which("node")
    if node is None:
        return False, "node not found on PATH — install Node.js to build the extension."

    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["MW_SRC"] = str(src)
    env["MW_OUT"] = str(out)
    result = subprocess.run(  # noqa: S603
        [node, "-e", _BUILD_NODE_SCRIPT],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "esbuild build failed").strip()
    return True, (result.stdout or "").strip() or f"built {out}"


def _mw_py_path_file() -> pathlib.Path:
    """Sidecar next to the global extension recording mw.py's absolute path, so
    the extension's findMwPy() resolves mw.py from any project (the repo-relative
    lookup fails when the bundle is loaded from the global install dir)."""
    return _global_ext_dir() / ".mw-py-path"


def _write_mw_py_path() -> None:
    p = _mw_py_path_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(pathlib.Path(__file__).resolve()), encoding="utf-8")


def cmd_build(args: argparse.Namespace) -> int:
    ok, msg = _build_bundle()
    if not ok:
        print(f"[mw build] Error: {msg}", file=sys.stderr)
        return 1
    print(f"[mw build] {msg}")
    print(f"[mw build] bundle: {_bundle_path()}")
    if args.install:
        ext_dst = _global_ext_dir() / "agent-team-loop.js"
        ext_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_bundle_path()), str(ext_dst))
        _write_mw_py_path()
        print(f"[mw build] installed globally: {ext_dst}")
        print("[mw build] Restart open pi windows to load the new bundle.")
    return 0


def _sync_dir(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy files from src into dst; only update files that exist in src. Keep dst-only files."""
    import shutil
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(target))


def _install_framework(
    project_dir: pathlib.Path,
    *,
    source: pathlib.Path,
    codex_scope: str = "project",
) -> tuple[bool, str]:
    """Install the AgenticTask framework into project_dir by invoking the
    installer bundled with the framework source (single source of truth). This
    lays down .claude/ + .agents/skills/agentic-task and writes .agentic-framework.
    Returns (ok, message)."""
    installer = source / "install.py"
    if not installer.is_file():
        return (
            False,
            f"AgenticTask framework not found at {source}. "
            "Run 'python mw.py pull-agentictask' to clone it from the remote repo first.",
        )
    cmd = [
        sys.executable,
        str(installer),
        str(project_dir),
        "--codex-scope",
        codex_scope,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "install.py failed").strip()
    return True, f"framework installed from {source}"


def cmd_init(args: argparse.Namespace) -> int:
    # AC-036: bundle must exist before creating any directories
    if not _check_bundle():
        print(
            f"[mw init] Error: Extension bundle not found at {_bundle_path()}\n"
            "Run 'bash packages/multi-workers/build-extension.sh' to build it first.",
            file=sys.stderr,
        )
        return 1

    project_dir = pathlib.Path(args.project).resolve()

    # AC-020: create directory structure
    (project_dir / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (project_dir / ".mw").mkdir(parents=True, exist_ok=True)
    (project_dir / ".pi" / "extensions").mkdir(parents=True, exist_ok=True)

    # Create placeholder files
    index_md = project_dir / ".agenticdoc" / "_index.md"
    if not index_md.exists():
        index_md.write_text("# AgenticTask Index\n\nactive: \n", encoding="utf-8")

    index_parallel = project_dir / ".agenticdoc" / "_index.parallel"
    if not index_parallel.exists():
        index_parallel.write_text("", encoding="utf-8")

    # Project goal is the north-star that every key/spec derives from. Seed a
    # `status: draft` skeleton so the goal brainstorm workflow (/goal) — or the
    # user editing it by hand — has something to fill in. Do NOT write real
    # content here: the goal must be co-created interactively, not fabricated.
    goal_md = project_dir / ".agenticdoc" / "goal.md"
    if not goal_md.exists():
        goal_md.write_text(
            "# Project Goal\n\n"
            "> status: draft\n"
            "> 项目总目标尚未确立。运行 /goal 与 Agent 对话共创，"
            "或直接编辑本文件填好三段内容后把 status 改为 active。\n\n"
            "## Goal\n\n"
            "<!-- 项目要达成的总目标：要构建/解决什么，核心交付是什么 -->\n\n"
            "## Context\n\n"
            "<!-- Agent 应知的上下文：技术栈、已有系统、相关约束 -->\n\n"
            "## Key Constraints\n\n"
            "<!-- 关键约束：性能要求、禁止的做法、测试规则等 -->\n",
            encoding="utf-8",
        )

    # AC-036: install Extension bundle — GLOBAL WINS.
    # The extension is normally installed globally by `mw setup` (~/.pi/agent/
    # extensions/), which loads for every project. A project-local copy would then
    # register the same tools a second time and the host rejects the load with a
    # "tool conflicts" error. So: only install locally when there is NO global copy,
    # and delete any stale local copy when a global one exists.
    global_bundle = _global_ext_dir() / "agent-team-loop.js"
    bundle_dst = project_dir / ".pi" / "extensions" / "agent-team-loop.js"
    if global_bundle.exists():
        if bundle_dst.exists():
            bundle_dst.unlink()
            print(f"[mw init] Removed redundant project-local extension (global install active): {bundle_dst}")
        else:
            print(f"[mw init] Using global extension install: {global_bundle}")
    else:
        shutil.copy2(str(_bundle_path()), str(bundle_dst))
        print(f"[mw init] Extension installed: {bundle_dst}")

    # Install the AgenticTask framework (.claude/ + .agents/skills/agentic-task)
    # by default so pi/codex can run the framework out of the box. Skippable
    # with --no-framework.
    #   - --sync-agentictask SOURCE overrides the install source with a local dir.
    #   - Otherwise _resolve_framework_source picks the freshest source: the mw
    #     checkout's own framework repo (dev machine), then the .tmp cache
    #     (auto-cloned once from the default remote so fresh machines work
    #     unattended).
    # Framework failure is a WARNING, not fatal: the bundle + mw service must still
    # come up so any project (even offline/unrelated) initializes cleanly.
    if not args.no_framework:
        source = _resolve_framework_source(args.sync_agentictask)
        ok, msg = _install_framework(project_dir, source=source, codex_scope=args.codex_scope)
        print(f"[mw init] {msg}" if ok else f"[mw init] Warning: {msg}", file=sys.stderr if not ok else None)

    print(f"[mw init] Project initialized: {project_dir}")
    return 0


# ── Subcommand: setup (one-time per machine) ───────────────────────────────────

def _global_ext_dir() -> pathlib.Path:
    """pi's global extensions dir (single source: mw_common.global_ext_dir)."""
    return mw_common.global_ext_dir()


def cmd_setup(args: argparse.Namespace) -> int:
    """Bootstrap the machine so ANY project auto-installs on pi launch:
    (1) cache the framework source, (2) install the extension bundle GLOBALLY so
    pi loads it in every project → its session_start auto-runs `mw init` per project."""
    # Rebuild first when asked (bash-free) so a single `mw setup --build` from any
    # window refreshes and deploys the bundle in one shot.
    if args.build:
        ok, msg = _build_bundle()
        if not ok:
            print(f"[mw setup] Error: build failed: {msg}", file=sys.stderr)
            return 1
        print(f"[mw setup] {msg}")

    if not _check_bundle():
        print(
            f"[mw setup] Error: Extension bundle not found at {_bundle_path()}\n"
            "Run 'python mw.py build' (or 'mw setup --build') to build it first.",
            file=sys.stderr,
        )
        return 1

    # (1) framework source cache (clone from remote URL, or copy from a local dir)
    ok, msg = _pull_agentictask(args.source, force=args.force, branch=args.branch)
    print(f"[mw setup] {msg}" if ok else f"[mw setup] Warning: pull failed: {msg}",
          file=sys.stderr if not ok else None)

    # (2) global extension install
    import shutil
    ext_dir = _global_ext_dir()
    ext_dir.mkdir(parents=True, exist_ok=True)
    ext_dst = ext_dir / "agent-team-loop.js"
    shutil.copy2(str(_bundle_path()), str(ext_dst))
    _write_mw_py_path()
    print(f"[mw setup] Extension installed globally: {ext_dst}")
    print("[mw setup] Done — pi will now auto-init the agent-team loop in every project on launch.")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument("--pi-port", type=int, default=7001)
    parser.add_argument("--claude-port", type=int, default=7003)
    parser.add_argument("--deepseek-port", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--providers", default=None)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers service manager")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    _add_serve_args(sub.add_parser("serve", help="Run in foreground"))
    _add_serve_args(sub.add_parser("start", help="Run in background"))

    for name in ("stop", "status"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)

    doctor_p = sub.add_parser(
        "doctor",
        help="Full-chain diagnostic: service, proxy ports, logs, queue, credentials, bundle",
    )
    doctor_p.add_argument("--project", required=True)
    doctor_p.add_argument("--providers", default=None,
                          help="Path to providers.json (default: the mw package copy)")
    doctor_p.add_argument("--json", action="store_true", help="Emit the JSON report (used by /mw doctor)")
    doctor_p.add_argument("--fix", action="store_true", help="Auto-fix stale entries and stale PID files")
    doctor_p.add_argument("--stale-after", type=int, default=90, metavar="SEC",
                          help="Worker heartbeat staleness threshold in seconds (default: %(default)s, "
                               "in sync with the TS HEARTBEAT_STALE_MS constant)")

    init_p = sub.add_parser("init", help="Initialize project and install Extension + framework")
    init_p.add_argument("--project", required=True)
    init_p.add_argument("--no-framework", action="store_true",
                        help="Skip installing the AgenticTask framework (.claude/ + .agents/skills)")
    init_p.add_argument("--codex-scope", choices=("project", "user"), default="project",
                        help="Where to install the codex/pi skill (default: project-local .agents/skills)")
    init_p.add_argument("--sync-agentictask", default=None, metavar="SOURCE_DIR",
                        help="Install the framework from SOURCE_DIR, overriding automatic "
                             "source resolution (checkout framework repo > .tmp cache)")

    pull_p = sub.add_parser("pull-agentictask",
                            help="Clone/update the AgenticTask framework repo into the local .tmp clone")
    pull_p.add_argument("--from", dest="source", default=_DEFAULT_AGENTICTASK_REMOTE,
                        metavar="SOURCE",
                        help="Git URL to clone/update, or a local dir to copy (default: %(default)s)")
    pull_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                        help="Branch to clone/track (default: %(default)s)")
    pull_p.add_argument("--force", action="store_true",
                        help="git reset --hard to the remote branch, or replace a non-git cache")

    push_p = sub.add_parser("push-agentictask",
                            help="Commit+push local framework changes from the .tmp clone to its remote")
    push_p.add_argument("-m", "--message", default=None,
                        help="Commit message for uncommitted changes before pushing")
    push_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                        help="Branch to push (default: %(default)s)")

    setup_p = sub.add_parser("setup",
                             help="One-time machine bootstrap: clone framework + install extension globally")
    setup_p.add_argument("--from", dest="source", default=_DEFAULT_AGENTICTASK_REMOTE,
                         metavar="SOURCE",
                         help="Git URL to clone, or a local dir to copy (default: %(default)s)")
    setup_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                         help="Branch to clone/track (default: %(default)s)")
    setup_p.add_argument("--force", action="store_true", help="Refresh an existing clone (reset --hard)")
    setup_p.add_argument("--build", action="store_true",
                         help="Rebuild the extension bundle (bash-free) before installing")

    build_p = sub.add_parser("build",
                             help="Rebuild the extension bundle with esbuild (bash-free, cwd-independent)")
    build_p.add_argument("--install", action="store_true",
                         help="Also install the freshly built bundle into the global extensions dir")

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    dispatch = {
        "serve": cmd_serve,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "doctor": cmd_doctor,
        "init": cmd_init,
        "pull-agentictask": cmd_pull_agentictask,
        "push-agentictask": cmd_push_agentictask,
        "setup": cmd_setup,
        "build": cmd_build,
    }
    sys.exit(dispatch[args.subcommand](args))
