"""
worktree_doctor.py — AC-009 leftover-junction section for `mw doctor` (G3, T-W03).

Pure, read-only logic: ``build_section(project_root)`` inspects three domains
(decisions D-2/D-10) and returns the ``report["worktree_links"]`` dict consumed
by ``mw_common.doctor_report`` / ``_doctor_issues`` / ``format_doctor_text``.
It never writes, never follows a junction out of the repo, and never raises for
a missing registry or lockfile — doctor must always produce a verdict.

Domains:

(a) registry (default on) — every ``worktree_registry.read_registry`` entry:
    the link is still on disk (``os.path.lexists``) while its ``worktree`` is
    gone -> ``leftover``; the link itself is gone -> ``stale-entry``.
(b) repo-local (default on) — ``<repo>/node_modules/*`` (plus one ``@scope/*``
    level) reparse points whose resolved target lands inside the repo and whose
    link path is NOT in ``package-lock.json``'s ``"link": true`` expected set ->
    ``leftover``. Workspace links in the expected set are normal and stay
    silent (AC-009 reverse control: this repo has 14 expected == 14 on disk ->
    zero findings, zero lines, unchanged rc).
(c) scan roots (opt-in via ``--worktree-scan-roots``) — depth-1
    ``<root>/<worktree>/node_modules`` reparse points pointing back into this
    repo -> ``leftover``. Decision D-12: a hit whose ``link`` is registered and
    whose ``worktree`` still exists is the *normal* state of a live worktree and
    stays silent; only a vanished worktree or an unregistered link is reported.
    The registry read is the one shared with domain (a) (passed in, never
    re-read). An entry budget bounds the cost; over budget the scan stops and
    ``scanned["truncated"]`` is set.

Reuse, not reimplementation (task constraint): link enumeration and the
``\\\\?\\`` prefix stripping live in ``tree_watch.scan_links`` /
``tree_watch.resolve_link_target``; the registry is the single source of truth
via ``worktree_registry.read_registry``. Only the domain classification (which
link counts as leftover) lives here.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

import tree_watch
import worktree_registry

#: Depth-1 scan budget (design §7: "entry 预算（20 万条）").
DEFAULT_SCAN_BUDGET = 200_000

LOCKFILE_NAME = "package-lock.json"

# Entry kinds. The registry has two (leftover vs stale-entry); the two scan
# domains only ever produce leftovers.
REGISTRY_LEFTOVER_KIND = "registry-leftover"
REGISTRY_STALE_KIND = "registry-stale"
REPO_LOCAL_KIND = "repo-local-leftover"
SCAN_ROOT_KIND = "scan-root-leftover"


def _entry(path: object, target: object, kind: str, worktree: object = None) -> dict:
    """One finding: path / target / kind, plus `worktree` when the domain knows it."""
    return {
        "path": str(path),
        "target": str(target),
        "kind": kind,
        "worktree": None if worktree is None else str(worktree),
    }


def _real_key(path: object) -> str:
    """Normalized containment key for a possibly-aliased Windows path.

    `os.path.realpath` expands 8.3 short names (`WENBOZ~1` -> `wenbozhou`),
    which is required because `mw.py` resolves `--project` while a junction's
    `os.readlink` target keeps whatever spelling was used at creation (and
    `%TEMP%` is short-named on this machine). Without this the target would
    look 'outside the repo' for every fixture under `%TEMP%`.
    """
    raw = str(path)
    try:
        raw = os.path.realpath(raw)
    except OSError:
        pass
    return os.path.normcase(os.path.normpath(raw))


def _is_within(child: object, parent: object) -> bool:
    """True when `child` is strictly inside `parent` (case-insensitive on Windows).

    `commonpath` raises on different drives (ValueError) -> not within.
    """
    child_key = _real_key(child)
    parent_key = _real_key(parent)
    if child_key == parent_key:
        return False
    try:
        return os.path.commonpath([child_key, parent_key]) == parent_key
    except ValueError:
        return False


def _normalize_roots(scan_roots) -> list[str]:
    """`None` / `""` / `"a;b"` / `["a", "b"]` -> a stripped string list."""
    if scan_roots is None:
        return []
    if isinstance(scan_roots, str):
        scan_roots = scan_roots.split(";")
    return [str(root) for root in scan_roots if str(root).strip()]


def expected_link_keys(repo_root: pathlib.Path) -> set[str]:
    """Normalized link paths declared by `package-lock.json` with `"link": true`.

    The lockfile is the authority for "these workspace links are normal".
    Missing / malformed lockfile -> empty set (nothing is pre-authorized, so an
    in-repo link is reported rather than silently trusted).
    """
    lockfile = pathlib.Path(repo_root) / LOCKFILE_NAME
    try:
        data = json.loads(lockfile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    packages = data.get("packages") if isinstance(data, dict) else None
    if not isinstance(packages, dict):
        return set()
    keys: set[str] = set()
    for rel_path, meta in packages.items():
        if not isinstance(meta, dict) or meta.get("link") is not True:
            continue
        parts = str(rel_path).replace("\\", "/").split("/")
        keys.add(os.path.normcase(os.path.normpath(os.path.join(str(repo_root), *parts))))
    return keys


# ---------------------------------------------------------------------------
# Domain (a): registry
# ---------------------------------------------------------------------------

def _registry_domain(
    project_root: pathlib.Path,
) -> tuple[list[dict], list[dict], list[dict], int, str | None]:
    """(leftover, stale_entries, registry entries, entries examined, error).

    The raw ``entries`` list is returned so domain (c) can apply D-12 against
    the *same* read instead of opening the registry file a second time.
    """
    leftover: list[dict] = []
    stale: list[dict] = []
    try:
        entries = worktree_registry.read_registry(project_root)
    except worktree_registry.WorktreeRegistryError as exc:
        # Fail-closed registry reads raise; doctor must still render a verdict,
        # so the error is surfaced in `scanned` instead of aborting the scan.
        return leftover, stale, [], 0, str(exc)
    for entry in entries:
        link = entry["link"]
        if not os.path.lexists(link):
            stale.append(
                _entry(link, entry.get("target", ""), REGISTRY_STALE_KIND, entry.get("worktree"))
            )
            continue
        worktree = entry.get("worktree")
        # No recorded worktree -> cannot judge; stay silent (no false positive).
        if worktree and not os.path.exists(worktree):
            leftover.append(
                _entry(link, entry.get("target", ""), REGISTRY_LEFTOVER_KIND, worktree)
            )
    return leftover, stale, entries, len(entries), None


# ---------------------------------------------------------------------------
# Domain (b): repo-local top level
# ---------------------------------------------------------------------------

def _repo_local_domain(repo_root: pathlib.Path, expected: set[str]) -> tuple[list[dict], int]:
    """`<repo>/node_modules/*` links inside the repo minus the expected set."""
    leftover: list[dict] = []
    links = tree_watch.scan_links(repo_root)
    for link in links:
        # The target is already `\\?\`-stripped by tree_watch.resolve_link_target.
        if not _is_within(link["target"], repo_root):
            continue
        link_key = os.path.normcase(os.path.normpath(str(link["path"])))
        if link_key in expected:
            continue
        leftover.append(_entry(link["path"], link["target"], REPO_LOCAL_KIND))
    return leftover, len(links)


# ---------------------------------------------------------------------------
# Domain (c): explicit scan roots
# ---------------------------------------------------------------------------

def _link_key(path: object) -> str:
    """Identity key for a reparse-point path that must NOT be followed.

    `os.path.realpath` resolves a junction to its target, so only the parent
    directory is canonicalized (this expands `%TEMP%`'s 8.3 short name, spec
    pitfall 9) while the final component is kept verbatim. Idempotent for a
    link spelling that already resolved.
    """
    text = str(path)
    parent = os.path.dirname(text)
    if parent:
        try:
            parent = os.path.realpath(parent)
        except OSError:
            pass
    return os.path.normcase(os.path.normpath(os.path.join(parent, os.path.basename(text))))


def _scan_roots_domain(
    roots: list[str],
    repo_root: pathlib.Path,
    budget: int,
    registry_entries: list[dict] | None = None,
) -> tuple[list[dict], int, bool]:
    """Depth-1 `<root>/<worktree>/node_modules` hunt, bounded by `budget`.

    D-12: a registered link whose `worktree` still exists is a live worktree's
    normal dependency shortcut and is skipped. Only the incident shape (the
    worktree is gone but the link remains, e.g. `%TEMP%/mwvg-t5`) or an
    unregistered link is a `scan-root-leftover`.
    """
    leftover: list[dict] = []
    visited = 0
    truncated = False
    registered_alive: set[str] = set()
    for entry in registry_entries or []:
        link = entry.get("link")
        worktree = entry.get("worktree")
        if link and worktree and os.path.exists(worktree):
            registered_alive.add(_link_key(link))
    for root in roots:
        root_path = pathlib.Path(root)
        try:
            with os.scandir(root_path) as iterator:
                children = list(iterator)
        except OSError:
            continue
        for child in children:
            if visited >= budget:
                truncated = True
                break
            visited += 1
            try:
                if not child.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            link = os.path.join(child.path, "node_modules")
            # Reuse the shared reparse probe instead of a second junction check.
            if not tree_watch._is_reparse_point(link):
                continue
            try:
                raw_target = os.readlink(link)
            except OSError:
                continue
            target = tree_watch.resolve_link_target(link, raw_target)
            if not _is_within(target, repo_root):
                continue
            if _link_key(link) in registered_alive:
                continue
            leftover.append(_entry(link, target, SCAN_ROOT_KIND, child.path))
        if truncated:
            break
    return leftover, visited, truncated


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_section(
    project_root,
    scan_roots=None,
    entry_budget: int = DEFAULT_SCAN_BUDGET,
) -> dict:
    """The `report["worktree_links"]` section. Pure and read-only.

    Shape: ``leftover[]`` / ``stale_entries[]`` / ``count`` (the two lengths
    summed) / ``registry_error`` (AC-015) / ``domains{registry, repo_local,
    scan_roots}`` (entries examined per domain) / ``scanned`` cost+context /
    ``registry_path``.
    """
    started = time.perf_counter()
    project_root = pathlib.Path(project_root)
    roots = _normalize_roots(scan_roots)
    budget = max(0, int(entry_budget))

    expected = expected_link_keys(project_root)
    reg_leftover, reg_stale, reg_entries, reg_examined, reg_error = _registry_domain(
        project_root
    )
    repo_leftover, repo_examined = _repo_local_domain(project_root, expected)
    scan_leftover, scan_visited, scan_truncated = _scan_roots_domain(
        roots, project_root, budget, reg_entries
    )

    leftover = reg_leftover + repo_leftover + scan_leftover
    leftover.sort(key=lambda item: item["path"].lower())
    reg_stale.sort(key=lambda item: item["path"].lower())
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "leftover": leftover,
        "stale_entries": reg_stale,
        "count": len(leftover) + len(reg_stale),
        # AC-015 (D-14): top-level mirror of `scanned["registry_error"]` so the
        # doctor issue/text face can consume it without reaching into `scanned`.
        "registry_error": reg_error,
        "domains": {
            "registry": reg_examined,
            "repo_local": repo_examined,
            "scan_roots": scan_visited,
        },
        "scanned": {
            "roots": roots,
            "budget": budget,
            "entries_visited": scan_visited,
            "truncated": scan_truncated,
            "elapsed_ms": elapsed_ms,
            "expected_links": len(expected),
            "repo_local_links": repo_examined,
            "registry_error": reg_error,
        },
        "registry_path": str(worktree_registry.registry_path(project_root)),
    }
