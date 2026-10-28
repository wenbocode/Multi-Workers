r"""G4 tree watch (AC-010 collapse, AC-011 dangling junction).

Pure logic for the resident launcher's shared-tree sampler: the two criteria,
the state file, and the alarm/event output structure. `launcher.py` only adds
the thin hook (`TreeWatch.tick` once per poll) and prints the alarm lines on
its existing stderr channel (`.mw/launcher.log`).

Criterion 1 - collapse: `git --no-optional-locks ls-files -d` lists index
entries whose working-tree file is gone. The count is taken over the path
surface with every `*/dist/` component excluded (mirrors the `mw.py`
convention; 2,239 tracked files in this repo live under `*/dist/`, so
`npm run clean --workspaces` would otherwise look like a collapse). The alarm
fires when the sample-to-sample delta reaches `max(20, 1% * non_dist_tracked)`
and the absolute non-dist deleted count is at least 20.

`git ls-files` (index-only total) must never be the criterion: it does not
move when files are deleted from disk, and switching branches moves the total
(180<->200) while `-d` stays put.

Criterion 2 - dangling junction: a junction whose target does not exist. The
probe uses `lstat`/`os.path.isjunction` + `os.path.lexists` semantics
(`os.path.exists` follows the link and is False for a broken junction, but
`stat`/`existsSync` cannot see the link itself). `os.readlink` returns
Windows junction targets with a `\\?\` prefix and short (8.3) names, so the
target is prefix-stripped, absolutized and `normcase`d before comparison.

Every git invocation is read-only and passes `--no-optional-locks` so sampling
can never refresh `.git/index` (spec pit 15). `PI_TREE_WATCH_SEC` overrides the
cadence (seconds, converted to polls); `0` disables the watch entirely and
must not spawn a single git child.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys
import time

# Cadence: the launcher polls every DEFAULT_POLL_INTERVAL seconds
# (launcher.DEFAULT_POLL_INTERVAL == 5), so 6 polls == 30 s by default.
DEFAULT_INTERVAL_POLLS = 6
DEFAULT_POLL_INTERVAL_SEC = 5
ENV_TREE_WATCH_SEC = "PI_TREE_WATCH_SEC"

# Collapse criterion: threshold = max(20, 1% * non_dist_tracked).
MIN_COLLAPSE_THRESHOLD = 20
COLLAPSE_RATIO = 0.01

STATE_FILE_NAME = "tree-watch.json"
STATE_VERSION = 1
DIST_COMPONENT = "dist"
MAX_RECORDED_PATHS = 50
GIT_TIMEOUT_SEC = 60.0


class TreeWatchError(RuntimeError):
    """A sampling prerequisite failed (git error, unreadable tree)."""


# ---------------------------------------------------------------------------
# Cadence
# ---------------------------------------------------------------------------

def watch_interval_polls(
    poll_interval: float = DEFAULT_POLL_INTERVAL_SEC,
    env: dict | None = None,
) -> int:
    """How many launcher polls between samples; 0 means the watch is off.

    Unset/invalid `PI_TREE_WATCH_SEC` -> the 6-poll default. A value <= 0
    disables the watch. A positive value is converted to polls with `ceil`
    so a sub-poll interval still samples every poll.
    """
    environ = os.environ if env is None else env
    raw = environ.get(ENV_TREE_WATCH_SEC)
    if raw is None or raw == "":
        return DEFAULT_INTERVAL_POLLS
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_POLLS
    if seconds <= 0:
        return 0
    if poll_interval is None or poll_interval <= 0:
        return DEFAULT_INTERVAL_POLLS
    return max(1, int(math.ceil(seconds / float(poll_interval))))


# ---------------------------------------------------------------------------
# Criterion helpers
# ---------------------------------------------------------------------------

def is_dist_path(rel_path: str) -> bool:
    """True when `rel_path` has a `dist` directory component (`*/dist/`).

    A root-level file literally named `dist` is not a directory component and
    is not excluded - it matches the `*/dist/` path-surface glob.
    """
    parts = rel_path.replace("\\", "/").split("/")
    return DIST_COMPONENT in parts[:-1]


def collapse_threshold(non_dist_tracked: int) -> int:
    """`max(20, round(1% * non_dist_tracked))` - recomputable every sample.

    Round-half-up reproduces the design's stated arithmetic (`1% * 2756 =
    27.56 -> 28`) and keeps this repo's threshold at 28 as the tracked base
    drifts (2,822 -> 28.22 -> 28); `ceil` would silently raise it to 29 and
    miss the card's documented `>= 28` trigger.
    """
    scaled = COLLAPSE_RATIO * max(0, non_dist_tracked)
    return max(MIN_COLLAPSE_THRESHOLD, int(math.floor(scaled + 0.5)))


def _git_paths(root: pathlib.Path, args: list[str]) -> list[str]:
    """NUL-separated `git ls-files` output; raises `TreeWatchError` on failure.

    Read-only and lock-free: `--no-optional-locks` keeps the sampler from
    refreshing `.git/index` while another git writer runs.
    """
    cmd = ["git", "--no-optional-locks", "-C", str(root), *args, "-z"]
    kwargs: dict = {"capture_output": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        proc = subprocess.run(cmd, timeout=GIT_TIMEOUT_SEC, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TreeWatchError(f"git {' '.join(args)} failed to start: {exc}") from None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise TreeWatchError(f"git {' '.join(args)} rc={proc.returncode}: {detail}")
    text = proc.stdout.decode("utf-8", "replace")
    return [chunk for chunk in text.split("\0") if chunk]


# ---------------------------------------------------------------------------
# Junction inventory (AC-011)
# ---------------------------------------------------------------------------

def _is_reparse_point(path: str) -> bool:
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(path):
        return True
    return os.path.islink(path)


def _iter_link_candidates(node_modules: pathlib.Path):
    """Yield `node_modules/*` plus one level of scoped (`@scope/*`) entries.

    The explicit stack never descends through a reparse point (spec pit 3/4:
    recursive walks follow junctions and can loop). This bounded domain covers
    every workspace link in this repo (5 `pi-extension-*` at the top level plus
    9 `@earendil-works/*`).
    """
    try:
        top = list(os.scandir(node_modules))
    except OSError:
        return
    for entry in top:
        path = entry.path
        if _is_reparse_point(path):
            yield path
            continue
        if entry.name.startswith("@") and entry.is_dir(follow_symlinks=False):
            try:
                scoped = list(os.scandir(path))
            except OSError:
                continue
            for sub in scoped:
                if _is_reparse_point(sub.path):
                    yield sub.path


def resolve_link_target(link_path: str, raw_target: str) -> str:
    r"""Strip the `\\?\` junction prefix, absolutize, and `normpath`.

    The returned path keeps its original casing (for display); comparison uses
    `target_key`. Handles the `\\?\UNC\` form and relative symlink targets.
    """
    target = raw_target
    if target.startswith("\\\\?\\UNC\\"):
        target = "\\\\" + target[len("\\\\?\\UNC\\"):]
    elif target.startswith("\\\\?\\"):
        target = target[len("\\\\?\\"):]
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(link_path), target)
    return os.path.normpath(target)


def _describe_link(path: str) -> dict:
    raw_target = os.readlink(path)
    resolved = resolve_link_target(path, raw_target)
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(path):
        link_type = "Junction"
    elif os.path.islink(path):
        link_type = "SymbolicLink"
    else:
        link_type = "Other"
    return {
        "path": path,
        "link_type": link_type,
        "target": resolved,
        "target_key": os.path.normcase(resolved),
        # os.path.exists FOLLOWS the link: False for a broken junction, which
        # is exactly the AC-011 signal (`lstat` is used to find the link).
        "target_exists": os.path.exists(resolved),
    }


def scan_links(root) -> list[dict]:
    """Inventory the default junction domain under `<root>/node_modules`."""
    node_modules = pathlib.Path(root) / "node_modules"
    inventory = [_describe_link(path) for path in _iter_link_candidates(node_modules)]
    inventory.sort(key=lambda item: item["path"].lower())
    return inventory


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def sample_once(root) -> dict:
    """One read-only sample: deleted non-dist count, threshold, link inventory."""
    root_path = pathlib.Path(root)
    tracked = _git_paths(root_path, ["ls-files"])
    deleted = _git_paths(root_path, ["ls-files", "-d"])
    tracked_non_dist = [path for path in tracked if not is_dist_path(path)]
    deleted_non_dist = [path for path in deleted if not is_dist_path(path)]
    return {
        "ts": time.time(),
        "iso": _iso_now(),
        "root": str(root_path),
        "tracked_total": len(tracked),
        "tracked_non_dist": len(tracked_non_dist),
        "deleted_total": len(deleted),
        "deleted_non_dist": len(deleted_non_dist),
        "deleted_paths": sorted(deleted_non_dist)[:MAX_RECORDED_PATHS],
        "threshold": collapse_threshold(len(tracked_non_dist)),
        "links": scan_links(root_path),
    }


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _link_key(link: dict) -> str:
    return os.path.normcase(os.path.normpath(str(link.get("path", ""))))


def evaluate(previous: dict | None, sample: dict) -> dict:
    """Derive this sample's events and alarm lines from the prior state.

    - collapse: `delta = deleted_non_dist(t) - deleted_non_dist(t-1)` reaches
      `threshold` while the absolute count is at least 20. No baseline (first
      sample) never alarms.
    - dangling junction: a `Junction` whose `target_exists` is False. Broken
      `SymbolicLink`s are recorded but do not trigger (spec: git does not
      traverse symlinks).
    - inventory migration: a link present last sample is gone, or its target
      changed (covers "only one link left and nobody noticed").
    """
    alarms: list[str] = []
    events: list[dict] = []

    previous = previous or {}
    prev_deleted = previous.get("deleted_non_dist")
    threshold = int(sample.get("threshold") or 0)
    deleted = int(sample.get("deleted_non_dist") or 0)
    delta = None
    if isinstance(prev_deleted, int):
        delta = deleted - prev_deleted

    # Same-window junction-inventory delta (design §6.1 AC-010 action (3),
    # T-W09). This is the one inventory comparison `evaluate` performs: the
    # counts feed the `collapse` event field and the `link-removed` /
    # `link-retargeted` events below. No baseline (first sample) reports all
    # zeroes - "added" against nothing is not a migration.
    link_delta = {"removed": 0, "changed": 0, "added": 0}
    inventory_events: list[dict] = []
    inventory_alarms: list[str] = []
    prev_links = {
        _link_key(link): link for link in (previous.get("links") or [])
    }
    current_links = {
        _link_key(link): link for link in (sample.get("links") or [])
    }
    if prev_links:
        for key, old in prev_links.items():
            current = current_links.get(key)
            if current is None:
                link_delta["removed"] += 1
                inventory_events.append({
                    "kind": "link-removed", "path": old.get("path"), "target": old.get("target"),
                })
                inventory_alarms.append(
                    f"[TREE-WATCH] link-inventory: removed {old.get('path')} -> {old.get('target')}"
                )
            elif current.get("target_key") != old.get("target_key"):
                link_delta["changed"] += 1
                inventory_events.append({
                    "kind": "link-retargeted",
                    "path": current.get("path"),
                    "old_target": old.get("target"),
                    "target": current.get("target"),
                })
                inventory_alarms.append(
                    f"[TREE-WATCH] link-inventory: retargeted {current.get('path')} "
                    f"{old.get('target')} -> {current.get('target')}"
                )
        for key in current_links:
            if key not in prev_links:
                link_delta["added"] += 1

    collapse = (
        delta is not None
        and delta >= threshold
        and deleted >= MIN_COLLAPSE_THRESHOLD
    )
    if collapse:
        events.append({
            "kind": "collapse",
            "ts": sample.get("ts"),
            "deleted_non_dist": deleted,
            "delta": delta,
            "threshold": threshold,
            "tracked_non_dist": sample.get("tracked_non_dist"),
            "paths": list(sample.get("deleted_paths") or []),
            "link_delta": dict(link_delta),
        })
        alarms.append(
            f"[TREE-WATCH] collapse: deleted_non_dist={deleted} delta={delta} "
            f"threshold={threshold} tracked_non_dist={sample.get('tracked_non_dist')} "
            f"links={len(sample.get('links') or [])} "
            f"paths={','.join(list(sample.get('deleted_paths') or [])[:5]) or '-'}"
        )

    broken = [
        link for link in (sample.get("links") or [])
        if link.get("link_type") == "Junction" and not link.get("target_exists")
    ]
    broken_symlinks = [
        link for link in (sample.get("links") or [])
        if link.get("link_type") == "SymbolicLink" and not link.get("target_exists")
    ]
    for link in broken:
        events.append({"kind": "broken-link", "path": link["path"], "target": link["target"]})
        alarms.append(
            f"[TREE-WATCH] broken-link: {link['path']} -> {link['target']} (junction target missing)"
        )
    for link in broken_symlinks:
        events.append({"kind": "dangling-symlink", "path": link["path"], "target": link["target"]})

    # Inventory-migration events are appended after the broken-link events so
    # the historical event order (collapse, broken-link, dangling-symlink,
    # inventory) is unchanged.
    events.extend(inventory_events)
    alarms.extend(inventory_alarms)

    return {
        "ts": sample.get("ts"),
        "iso": sample.get("iso"),
        "delta": delta,
        "collapse": collapse,
        "broken_links": broken,
        "events": events,
        "alarms": alarms,
    }


# ---------------------------------------------------------------------------
# State file (`.mw/tree-watch.json`, tmp + atomic replace)
# ---------------------------------------------------------------------------

def state_path(project_dir) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / STATE_FILE_NAME


def read_state(project_dir) -> dict:
    """Prior sample or `{}`. A missing/corrupt file is a missing baseline."""
    try:
        text = state_path(project_dir).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def write_state(project_dir, sample: dict, verdict: dict) -> pathlib.Path:
    """Persist the sample + this sample's events through tmp + `os.replace`."""
    path = state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "ts": sample.get("ts"),
        "iso": sample.get("iso"),
        "tracked_total": sample.get("tracked_total"),
        "tracked_non_dist": sample.get("tracked_non_dist"),
        "deleted_total": sample.get("deleted_total"),
        "deleted_non_dist": sample.get("deleted_non_dist"),
        "deleted_paths": sample.get("deleted_paths") or [],
        "threshold": sample.get("threshold"),
        "delta": verdict.get("delta"),
        "links": sample.get("links") or [],
        "events": verdict.get("events") or [],
        "alarms": verdict.get("alarms") or [],
    }
    tmp = path.parent / f"{STATE_FILE_NAME}.tmp{os.getpid()}"
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1),
            encoding="utf-8",
            errors="replace",
        )
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return path


# ---------------------------------------------------------------------------
# Launcher-facing driver
# ---------------------------------------------------------------------------

class TreeWatch:
    """Poll-cadence driver held by `launcher.run` and ticked by `_poll_once`.

    `tick()` never raises: a git/permission failure only logs and skips this
    round, so the resident launcher loop always survives.
    """

    def __init__(self, project_dir, poll_interval: float = DEFAULT_POLL_INTERVAL_SEC, env=None):
        self.project_dir = pathlib.Path(project_dir)
        try:
            interval = float(poll_interval)
        except (TypeError, ValueError):
            interval = DEFAULT_POLL_INTERVAL_SEC
        self.poll_interval = interval
        self.interval_polls = watch_interval_polls(interval, env)
        self._polls = 0

    @property
    def enabled(self) -> bool:
        return self.interval_polls > 0

    def tick(self) -> dict | None:
        """One poll. Samples when due; returns the verdict, else None."""
        if not self.enabled:
            return None
        self._polls += 1
        if self._polls < self.interval_polls:
            return None
        self._polls = 0
        return self.sample_and_record()

    def sample_and_record(self) -> dict | None:
        """Force one sample now (cadence bypassed); never raises."""
        try:
            sample = sample_once(self.project_dir)
        except TreeWatchError as exc:
            _log(f"[TREE-WATCH] sample skipped: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001 - the poll loop must survive
            _log(f"[TREE-WATCH] sample skipped: {type(exc).__name__}: {exc}")
            return None
        verdict = evaluate(read_state(self.project_dir), sample)
        try:
            write_state(self.project_dir, sample, verdict)
        except OSError as exc:
            _log(f"[TREE-WATCH] state write skipped: {exc}")
        return verdict


def _log(message: str) -> None:
    """Best-effort diagnostic on the launcher's own channel (`.mw/launcher.log`)."""
    try:
        print(f"[launcher] {message}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 - logging must never break the caller
        pass


def emit_alarms(verdict: dict | None) -> None:
    """Print a verdict's alarm lines through the launcher's existing channel."""
    if not verdict:
        return
    for line in verdict.get("alarms") or ():
        _log(line)
