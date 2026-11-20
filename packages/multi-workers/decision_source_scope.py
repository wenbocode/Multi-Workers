"""Trusted Worker-card restrictions for DP evidence reads.

The card is located by the host's PI_WORKER_TASK binding, never by model
material. The CLI has no access to the Worker's in-memory lifetime counters.
Guarded cards therefore refuse implicit file hydration after checking path
permissions and declared caps; no independent budget grants extra reads.
"""

from __future__ import annotations

import fnmatch
import hashlib
import math
import os
import pathlib
import re
from dataclasses import dataclass

import mw_common

MAX_CARD_BYTES = 1024 * 1024


class WorkerSourceScopeError(ValueError):
    """A trusted card cannot authorize this evidence read."""


def _key(path: pathlib.Path) -> str:
    return os.path.normcase(str(path)).replace("\\", "/")


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    candidate, prefix = _key(path), _key(root).rstrip("/")
    return candidate == prefix or candidate.startswith(prefix + "/")


@dataclass
class WorkerSourceScope:
    root: pathlib.Path
    scope: tuple[pathlib.Path, ...] | None
    deny_globs: tuple[str, ...]
    file_cap: float
    byte_cap: float
    dependency: dict[str, object]
    guarded: bool

    def check_path(self, path: pathlib.Path) -> None:
        resolved = path.resolve()
        absolute = _key(resolved)
        # Check the lexical alias as well as its canonical target: a denied
        # alias cannot be used to reach an otherwise permitted target.
        lexical = pathlib.Path(os.path.abspath(path))
        names = [absolute, _key(lexical)]
        for candidate in (resolved, lexical):
            try:
                names.append(os.path.relpath(candidate, self.root).replace("\\", "/"))
            except ValueError:  # Different Windows drives: TS relative is absolute.
                names.append(_key(candidate))
        for raw in self.deny_globs:
            pattern = os.path.normcase(raw).replace("\\", "/")
            if any(fnmatch.fnmatchcase(name, pattern)
                   or (pattern.startswith("**/") and fnmatch.fnmatchcase(name, pattern[3:]))
                   or (pattern.endswith("/**") and fnmatch.fnmatchcase(name, pattern[:-3]))
                   for name in names):
                raise WorkerSourceScopeError("referenced file is excluded by the Worker card deny globs")
        if self.scope is not None and not any(_within(resolved, root) for root in self.scope):
            raise WorkerSourceScopeError("referenced file is outside the Worker card read_scope")

    def charge(self, path: pathlib.Path, size: int) -> None:
        if not self.guarded:
            return
        if self.scope is not None and self.file_cap < 1:
            raise WorkerSourceScopeError("Worker card read file cap would be exceeded by this hydration")
        if size > self.byte_cap:
            raise WorkerSourceScopeError("Worker card read byte cap would be exceeded by this hydration")
        raise WorkerSourceScopeError(
            "Worker lifetime read budget is unavailable to source hydration; "
            "supply already-authorized inline material or host-owned prepared evidence"
        )


def load_worker_source_scope(project_root: pathlib.Path) -> WorkerSourceScope | None:
    """Read the host-bound card once and retain its exact hash for freshness.

    Path authentication remains the CLI actor-binding responsibility. A
    present but invalid/unreadable binding fails closed even in direct clients.
    No material/preparation field can select a card or widen its scope.
    """
    raw_path = os.environ.get("PI_WORKER_TASK", "").strip()
    if not raw_path:
        return None
    card = pathlib.Path(os.path.abspath(raw_path))
    try:
        resolved = card.resolve(strict=True)
        with resolved.open("rb") as handle:
            before = os.fstat(handle.fileno())
            raw = handle.read(MAX_CARD_BYTES + 1)
            after = os.fstat(handle.fileno())
        if len(raw) > MAX_CARD_BYTES:
            raise WorkerSourceScopeError("Worker task card exceeds the scope metadata read limit")
        current = resolved.stat()
        signature = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if signature(before) != signature(after) or signature(before) != signature(current) or card.resolve() != resolved:
            raise WorkerSourceScopeError("Worker task card changed while preparing source scope")
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError, RuntimeError) as exc:
        raise WorkerSourceScopeError("Worker task card is unreadable; source scope cannot be verified") from exc
    lines, region = mw_common.read_task_header_region(text)
    header = lines[region.start_line:region.end_line + 1]
    lists: dict[str, list[str]] = {}
    values: dict[str, str] = {}
    active: str | None = None
    for line in header:
        if line in ("read_scope:", "deny_globs:"):
            active = line[:-1]
            if active in lists:
                raise WorkerSourceScopeError("Worker task card repeats a scope restriction; source read refused")
            lists[active] = []
        elif active is not None and line.startswith("- "):
            value = line[2:].strip()
            if active == "deny_globs" and len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                lists[active].append(value)
        else:
            active = None
            if ":" in line:
                key, value = line.split(":", 1)
                if key in ("read_scope", "deny_globs"):
                    raise WorkerSourceScopeError("Worker task card scope must use a block list; source read refused")
                if key in ("l2_read_file_cap", "l2_read_byte_cap") and key in values:
                    raise WorkerSourceScopeError("Worker task card repeats a read cap; source read refused")
                values.setdefault(key, value.strip())
    def cap(name: str, default: int) -> float:
        try:
            number = float(values.get(name, str(default)))
            return number if math.isfinite(number) and number > 0 else float(default)
        except ValueError:
            return float(default)
    scope = tuple((project_root / item).resolve() for item in lists["read_scope"]) if "read_scope" in lists else None
    if scope and re.search(r"^\[mw\] mode: partition[ \t]*$", text, re.MULTILINE):
        parent = re.search(r"^Parent root[^:\n]*:[ \t]*(.+)$", text, re.MULTILINE)
        if parent and parent[1].strip():
            scope += ((project_root / parent[1].strip()).resolve(),)
    deny = tuple(lists.get("deny_globs", []))
    # Python fnmatch supports the common firewall patterns. Refuse unsupported
    # minimatch extensions instead of silently weakening a card restriction.
    if any("{" in pattern or re.search(r"[!+@?*]\(", pattern) or pattern.startswith("!") for pattern in deny):
        raise WorkerSourceScopeError("Worker card deny glob requires an unsupported pattern; source read refused")
    dependency: dict[str, object] = {"path": str(card), "canonical_path": str(resolved),
                                     "sha256": hashlib.sha256(raw).hexdigest()}
    return WorkerSourceScope(project_root, scope, deny, cap("l2_read_file_cap", 8),
                             cap("l2_read_byte_cap", 65536), dependency,
                             "read_scope" in lists or "deny_globs" in lists)
