"""
worktree_cmd.py — `mw worktree add|rm|list` (G2, T-W02).

Why this exists: `git worktree remove --force` follows reparse points and
deletes the *target* tree (the 2026-10-09 incident deleted 3,456 tracked files
through `node_modules` junctions). `rm` is therefore a six-step transaction
that unlinks reparse points first, re-verifies the main tree, and only then
lets git remove the worktree. There is no switch that skips a step and no
compensating write on failure: an abort preserves the scene.

Six steps, one process, one call (design 4.2):

    1 enumerate reparse points in the worktree + snapshot the main tree
      (`node_modules/@earendil-works/*` link set)
    2 classify every link (D-1); any `foreign` link aborts with ZERO unlinks
    3 unlink only, `cmd /c rmdir <link>` (no /S, no trailing separator)
    4 re-snapshot the main tree and compare it with step 1 entry by entry
    5 `git worktree remove --force` (only when step 4 passes)
    6 print the before/after report

Step 2 and step 3 share the frozen list from step 1; nothing is written
between them. ABORT paths return immediately with ``ABORT at step N/6`` and an
explicit "未降级继续" line.

The three-way target classification (design 4.4 / decision D-1) is a pure
function so it can be unit-tested without touching a filesystem:

    classify_link_target(target, *, repo_root, worktree_root) ->
        "worktree"  target inside the to-be-deleted worktree (npm ci self-link;
                    harmless, unlink only)
      | "repo"      target inside repo_root but outside the worktree (the
                    incident shape; unlink -> recheck -> remove)
      | "foreign"   anything else (fail-closed: abort with zero unlinks)
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
from collections import Counter
from typing import Callable

import worktree_registry

#: Step number -> name, used in logs and in the `--json` `steps` array.
STEP_NAMES = {
    1: "enumerate",
    2: "validate",
    3: "unlink",
    4: "recheck",
    5: "remove",
    6: "report",
}

_GIT = Callable[..., subprocess.CompletedProcess]
_NPM_HYDRATE = Callable[[pathlib.Path], bool]
_LOG = Callable[[str], None]

_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class WorktreeCommandError(RuntimeError):
    """A G2 operation that cannot proceed (bad target, unlink failure, ...)."""


# ── pure helpers (classification + path normalization) ───────────────────────


def _norm(path: object) -> str:
    """Normalize a path for prefix comparisons.

    Junction ``readlink`` returns a ``\\\\?\\``-prefixed path, and Windows mixes
    short (``WENBOZ~1``) and long names, so strip the prefix, canonicalize with
    ``realpath`` (this is what expands an 8.3 short name — ``normcase`` alone
    does not equate the two spellings), then apply ``normcase``/``normpath``
    before any ``startswith`` (spec pitfall 9).
    """
    text = str(path)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    try:
        text = os.path.realpath(text)
    except (OSError, ValueError):
        pass
    return os.path.normcase(os.path.normpath(text))


def _is_within(child: object, parent: object) -> bool:
    child_norm = _norm(child)
    parent_norm = _norm(parent)
    if not parent_norm:
        return False
    return child_norm == parent_norm or child_norm.startswith(parent_norm + os.sep)


def classify_link_target(
    target: object, *, repo_root: pathlib.Path, worktree_root: pathlib.Path
) -> str:
    """Pure D-1 classification of one link target.

    ``target`` may be the raw ``os.readlink`` string (``\\\\?\\`` prefix and
    all). Returns one of ``"worktree"`` / ``"repo"`` / ``"foreign"``; the
    worktree subtree wins over the repo so an ``npm ci`` self-link inside a
    worktree nested in the repo is not mistaken for the dangerous main-tree
    case.
    """
    if _is_within(target, worktree_root):
        return "worktree"
    if _is_within(target, repo_root):
        return "repo"
    return "foreign"


# ── filesystem primitives ────────────────────────────────────────────────────


def _is_reparse_point(path: pathlib.Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def _link_info(path: pathlib.Path) -> dict:
    """Freeze Path/LinkType/Target into a plain dict.

    Windows `FileSystemInfo.Target` is lazily resolved and returns an empty
    string once the link is gone (spec pitfall 10), so every link is read into
    a plain object before step 3 touches it.
    """
    try:
        raw_target = os.readlink(path)
    except OSError:
        raw_target = ""
    if os.path.isjunction(path):
        link_type = "Junction"
    elif os.path.islink(path):
        link_type = "SymbolicLink"
    else:
        link_type = "ReparsePoint"
    return {
        "path": str(path),
        "link_type": link_type,
        "target": raw_target,
        "target_normalized": _norm(raw_target),
    }


def enumerate_reparse_links(root: pathlib.Path) -> list[dict]:
    """Explicit-stack walk: record reparse points, never descend into one.

    `os.walk` (even with ``followlinks=False``) and ``scandir(recursive=True)``
    both descend into junctions (spec pitfalls 3/4), which would enumerate the
    target tree and can loop.
    """
    links: list[dict] = []
    stack = [pathlib.Path(root)]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            path = pathlib.Path(entry.path)
            if _is_reparse_point(path):
                links.append(_link_info(path))
            elif entry.is_dir(follow_symlinks=False):
                stack.append(path)
    links.sort(key=lambda item: item["target_normalized"] or item["path"])
    return links


def snapshot_workspace_links(repo_root: pathlib.Path) -> list[dict]:
    """The step 1/4 comparison surface: `repo_root/node_modules/@earendil-works/*`.

    Records every entry (real directory or reparse point) with its frozen
    target, so "the link targets did not change" is a set comparison, not a
    re-read of a live object.
    """
    scope = pathlib.Path(repo_root) / "node_modules" / "@earendil-works"
    snapshot: list[dict] = []
    try:
        entries = list(os.scandir(scope))
    except OSError:
        return snapshot
    for entry in entries:
        path = pathlib.Path(entry.path)
        if _is_reparse_point(path):
            info = _link_info(path)
        else:
            info = {
                "path": str(path),
                "link_type": None,
                "target": None,
                "target_normalized": None,
            }
        info["name"] = entry.name
        snapshot.append(info)
    snapshot.sort(key=lambda item: item["name"])
    return snapshot


def _snapshot_diff(before: list[dict], after: list[dict]) -> str:
    before_index = {item["name"]: item for item in before}
    after_index = {item["name"]: item for item in after}
    parts: list[str] = []
    for name in sorted(set(before_index) | set(after_index)):
        old = before_index.get(name)
        new = after_index.get(name)
        if old == new:
            continue
        if old is None:
            parts.append(f"{name}: added -> {new and new.get('target')}")
        elif new is None:
            parts.append(f"{name}: removed (was {old.get('target')})")
        else:
            parts.append(
                f"{name}: {old.get('target')} -> {new.get('target')}"
            )
    return "; ".join(parts) or "unknown change"


def _unlink_reparse_point(link: pathlib.Path) -> None:
    """The single unlink primitive: ``cmd /c rmdir <link>``.

    No ``/S``, no trailing separator, no shell. `rmdir` on a directory
    reparse point removes the link only; it does not follow it (measured).
    Non-Windows refuses outright rather than silently degrading.
    """
    if sys.platform != "win32":
        raise WorktreeCommandError(
            "unlinking reparse points is only supported on Windows "
            "(cmd /c rmdir has no cross-platform equivalent that provably does not follow the link)"
        )
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["cmd", "/c", "rmdir", str(link)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise WorktreeCommandError(
            f"cmd /c rmdir failed for {link} (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '').strip()}"
        )


def _create_junction(link: pathlib.Path, target: pathlib.Path) -> None:
    if sys.platform != "win32":
        raise WorktreeCommandError("--link-deps needs Windows (directory junctions)")
    if os.path.lexists(link):
        raise WorktreeCommandError(f"link path already exists: {link}")
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise WorktreeCommandError(
            f"mklink /J failed for {link} -> {target} (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '').strip()}"
        )


# ── git helpers ──────────────────────────────────────────────────────────────


def parse_worktree_porcelain(text: str) -> list[dict]:
    worktrees: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = {
                "path": line[len("worktree "):].strip(),
                "head": None,
                "branch": None,
                "detached": False,
                "bare": False,
                "prunable": False,
            }
        elif current is None:
            continue
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].strip()
        elif line.strip() == "detached":
            current["detached"] = True
        elif line.strip() == "bare":
            current["bare"] = True
        elif line.startswith("prunable"):
            current["prunable"] = True
    if current is not None:
        worktrees.append(current)
    return worktrees


def _worktree_paths(git: _GIT, repo_root: pathlib.Path) -> set[str] | None:
    proc = git(["worktree", "list", "--porcelain"], cwd=repo_root)
    if proc.returncode != 0:
        return None
    return {_norm(item["path"]) for item in parse_worktree_porcelain(proc.stdout or "")}


def _tail(text: object, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


# ── six-step rm ──────────────────────────────────────────────────────────────


def remove_worktree(
    target: pathlib.Path,
    *,
    repo_root: pathlib.Path,
    project_dir: pathlib.Path,
    git: _GIT,
    unlink: Callable[[pathlib.Path], None] | None = None,
    log: _LOG | None = None,
) -> dict:
    """The six-step transaction; returns the report dict (also the JSON payload)."""
    emit = log or (lambda _message: None)
    unlink = unlink or _unlink_reparse_point
    target = pathlib.Path(target).resolve()
    repo_root = pathlib.Path(repo_root).resolve()
    project_dir = pathlib.Path(project_dir).resolve()
    result: dict = {
        "action": "rm",
        "target": str(target),
        "repo_root": str(repo_root),
        "project": str(project_dir),
        "ok": False,
        "abort_step": None,
        "error": None,
        "steps": [],
        "links": [],
        "unlinked": [],
        "main_tree_before": [],
        "main_tree_after": [],
        "registry_unregistered": [],
    }

    # Step 0 (precondition, NOT one of the six): target must be a linked
    # worktree of repo_root. Nothing has been touched yet on this path.
    if not target.is_dir():
        return _precondition_error(result, f"target is not a directory: {target}", emit)
    if _norm(target) == _norm(repo_root):
        return _precondition_error(result, f"refusing to remove the main working tree: {target}", emit)
    known = _worktree_paths(git, repo_root)
    if known is None:
        return _precondition_error(result, f"git worktree list --porcelain failed in {repo_root}", emit)
    if _norm(target) not in known:
        return _precondition_error(result, f"not a linked worktree of {repo_root}: {target}", emit)

    # Step 1: enumerate + freeze the main-tree snapshot before any mutation.
    links = enumerate_reparse_links(target)
    before = snapshot_workspace_links(repo_root)
    result["links"] = links
    result["main_tree_before"] = before
    _record(result, 1, True, (
        f"enumerated {len(links)} reparse point(s) under {target}; "
        f"main-tree @earendil-works snapshot: {len(before)} entry(ies)"
    ))
    emit(
        f"[mw worktree rm] step 1/6: enumerated {len(links)} reparse point(s) under {target}; "
        f"main-tree @earendil-works snapshot: {len(before)}"
    )

    # Step 2: classify every link BEFORE unlinking anything. The `links` list
    # is the frozen step-1 list; no write happens between step 2 and step 3.
    foreign: list[dict] = []
    for link in links:
        link["classification"] = classify_link_target(
            link["target"], repo_root=repo_root, worktree_root=target
        )
        if link["classification"] == "foreign":
            foreign.append(link)
    if foreign:
        for link in foreign:
            emit(
                "[mw worktree rm] Error: link target outside both the repo and this worktree: "
                f"{link['path']} -> {link['target']}"
            )
        return _abort(
            result, 2,
            f"{len(foreign)} link(s) failed the fail-closed target check; zero link(s) unlinked",
            emit,
        )
    counts = Counter(link["classification"] for link in links)
    _record(result, 2, True, (
        f"validated {len(links)} link(s): repo={counts.get('repo', 0)} "
        f"worktree={counts.get('worktree', 0)} foreign=0"
    ))
    emit(
        f"[mw worktree rm] step 2/6: validated {len(links)} link(s) "
        f"(repo={counts.get('repo', 0)}, worktree={counts.get('worktree', 0)}, foreign=0)"
    )

    # Step 3: unlink only. A failure aborts immediately; remaining links stay.
    for link in links:
        try:
            unlink(pathlib.Path(link["path"]))
        except (OSError, WorktreeCommandError) as exc:
            return _abort(result, 3, f"unlink failed for {link['path']}: {exc}", emit)
        link["unlinked"] = True
        result["unlinked"].append(link)
    _record(result, 3, True, (
        f"{len(result['unlinked'])} reparse point(s) unlinked "
        "(cmd /c rmdir, no /S, no trailing separator)"
    ))
    emit(
        f"[mw worktree rm] step 3/6: unlinked {len(result['unlinked'])} reparse point(s) "
        "(cmd /c rmdir, no /S)"
    )

    # Step 4: main-tree link set must be byte-for-byte unchanged.
    after = snapshot_workspace_links(repo_root)
    result["main_tree_after"] = after
    if after != before:
        return _abort(result, 4, (
            f"main-tree @earendil-works link set changed: {_snapshot_diff(before, after)}"
        ), emit)
    _record(result, 4, True, f"main-tree @earendil-works links unchanged ({len(after)})")
    emit(
        f"[mw worktree rm] step 4/6: main-tree @earendil-works links unchanged ({len(after)})"
    )

    # Step 5: only now let git remove the worktree.
    proc = git(["worktree", "remove", "--force", str(target)], cwd=repo_root)
    if proc.returncode != 0:
        return _abort(
            result, 5,
            f"git worktree remove --force failed (rc={proc.returncode}): {_tail(proc.stderr)}",
            emit,
        )
    _record(result, 5, True, "git worktree remove --force rc=0")
    emit(f"[mw worktree rm] step 5/6: git worktree remove --force rc=0")

    # Registry cleanup is post-transaction housekeeping, not one of the six
    # steps: the worktree is already gone, so a registry error is a warning.
    for link in result["unlinked"]:
        try:
            if worktree_registry.unregister_link(project_dir, link["path"]):
                result["registry_unregistered"].append(link["path"])
        except (OSError, worktree_registry.WorktreeRegistryError) as exc:
            emit(f"[mw worktree rm] Warning: registry unregister failed for {link['path']}: {exc}")

    # Step 6: before/after report (link tables + unlinked entries).
    _record(result, 6, True, (
        f"before={len(before)} after={len(after)} unlinked={len(result['unlinked'])} "
        f"registry_unregistered={len(result['registry_unregistered'])}"
    ))
    emit(
        f"[mw worktree rm] step 6/6: before/after main-tree @earendil-works links "
        f"(before={len(before)}, after={len(after)})"
    )
    _emit_link_table(emit, "before", before)
    _emit_link_table(emit, "after", after)
    for link in result["unlinked"]:
        emit(
            f"[mw worktree rm]   unlinked: {link['path']} "
            f"({link['link_type']} -> {link['target']}, classification={link['classification']})"
        )
    emit(
        f"[mw worktree rm] step 6/6: before={len(before)} after={len(after)} "
        f"unlinked={len(result['unlinked'])} registry_unregistered={len(result['registry_unregistered'])}"
    )
    result["ok"] = True
    return result


def _emit_link_table(emit: _LOG, label: str, snapshot: list[dict]) -> None:
    if not snapshot:
        emit(f"[mw worktree rm]   {label}: (none)")
        return
    for item in snapshot:
        if item.get("link_type"):
            emit(f"[mw worktree rm]   {label}: {item['name']} ({item['link_type']}) -> {item['target']}")
        else:
            emit(f"[mw worktree rm]   {label}: {item['name']} (directory)")


def _record(result: dict, step: int, ok: bool, detail: str) -> None:
    result["steps"].append(
        {"step": step, "name": STEP_NAMES[step], "ok": ok, "detail": detail}
    )


def _abort(result: dict, step: int, message: str, emit: _LOG) -> dict:
    result["ok"] = False
    result["abort_step"] = step
    result["error"] = message
    _record(result, step, False, message)
    emit(f"[mw worktree rm] ABORT at step {step}/6: {message}")
    emit(
        "[mw worktree rm] 未降级继续 (no degraded continuation): scene preserved; "
        "git worktree remove NOT executed; every remaining link stays where it is"
    )
    for link in result["links"]:
        if not link.get("unlinked"):
            emit(
                f'[mw worktree rm]   manual: cmd /c rmdir "{link["path"]}" '
                "(never /S, never a trailing separator)"
            )
    return result


def _precondition_error(result: dict, message: str, emit: _LOG) -> dict:
    result["ok"] = False
    result["error"] = message
    emit(f"[mw worktree rm] Error: {message}")
    return result


# ── add ──────────────────────────────────────────────────────────────────────


def add_worktree(
    target: pathlib.Path,
    *,
    repo_root: pathlib.Path,
    project_dir: pathlib.Path,
    git: _GIT,
    npm_hydrate: _NPM_HYDRATE,
    ref: str = "HEAD",
    link_deps: bool = False,
    dry_run: bool = False,
    log: _LOG | None = None,
) -> dict:
    """Create a linked worktree; junctions only with ``--link-deps`` (AC-008)."""
    emit = log or (lambda _message: None)
    target = pathlib.Path(target).resolve()
    repo_root = pathlib.Path(repo_root).resolve()
    project_dir = pathlib.Path(project_dir).resolve()
    link = target / "node_modules"
    link_target = repo_root / "node_modules"
    result: dict = {
        "action": "add",
        "target": str(target),
        "ref": ref,
        "link_deps": link_deps,
        "dry_run": dry_run,
        "ok": False,
        "steps": [],
        "planned": ["git worktree add --detach " + str(target) + " " + ref],
        "link": None,
        "link_target": None,
        "hydrated": False,
        "registered": None,
        "error": None,
    }
    if link_deps:
        result["planned"].append(f'cmd /c mklink /J "{link}" "{link_target}"')
    else:
        result["planned"].append("npm ci --ignore-scripts (npm install when node_modules exists)")

    if dry_run:
        for line in result["planned"]:
            emit(f"[mw worktree add] would run: {line}")
        result["ok"] = True
        return result

    if _norm(target) == _norm(repo_root):
        return _add_error(result, f"refusing to add a worktree at the repo root: {target}", emit)
    if os.path.lexists(target):
        return _add_error(result, f"target already exists: {target}", emit)
    if link_deps and sys.platform != "win32":
        return _add_error(result, "--link-deps needs Windows (directory junctions)", emit)

    proc = git(["worktree", "add", "--detach", str(target), ref], cwd=repo_root)
    _add_record(result, 1, "worktree-add", proc.returncode == 0, f"rc={proc.returncode}")
    if proc.returncode != 0:
        return _add_error(
            result,
            f"git worktree add failed (rc={proc.returncode}): {_tail(proc.stderr)}",
            emit,
        )
    emit(f"[mw worktree add] created worktree {target} at {ref}")

    if link_deps:
        try:
            _create_junction(link, link_target)
        except WorktreeCommandError as exc:
            return _add_error(result, f"failed to create junction {link} -> {link_target}: {exc}", emit)
        result["link"] = str(link)
        result["link_target"] = str(link_target)
        try:
            result["registered"] = worktree_registry.register_link(
                project_dir,
                link=str(link),
                target=str(link_target),
                worktree=str(target),
                repo_root=str(repo_root),
                created_by=worktree_registry.created_by_now(),
            )
        except (OSError, worktree_registry.WorktreeRegistryError) as exc:
            return _add_error(result, f"link created but registry write failed: {exc}", emit)
        _add_record(result, 2, "link-deps", True, f"{link} -> {link_target} (registered)")
        emit(f"[mw worktree add] junction created and registered: {link} -> {link_target}")
    else:
        hydrated = bool(npm_hydrate(target))
        result["hydrated"] = hydrated
        _add_record(result, 2, "npm-hydrate", hydrated, "npm ci/install --ignore-scripts")
        if not hydrated:
            return _add_error(
                result, "dependency hydration failed (npm ci/install --ignore-scripts)", emit
            )
        emit(f"[mw worktree add] dependencies hydrated in {target} (npm ci/install --ignore-scripts)")

    result["ok"] = True
    return result


def _add_record(result: dict, step: int, name: str, ok: bool, detail: str) -> None:
    result["steps"].append({"step": step, "name": name, "ok": ok, "detail": detail})


def _add_error(result: dict, message: str, emit: _LOG) -> dict:
    result["ok"] = False
    result["error"] = message
    emit(f"[mw worktree add] Error: {message}")
    return result


# ── list ─────────────────────────────────────────────────────────────────────


def list_worktrees(
    *, repo_root: pathlib.Path, project_dir: pathlib.Path, git: _GIT
) -> dict:
    """Read-only merged view: registry entries + `git worktree list --porcelain`."""
    repo_root = pathlib.Path(repo_root).resolve()
    project_dir = pathlib.Path(project_dir).resolve()
    registry_error: str | None = None
    try:
        entries = worktree_registry.read_registry(project_dir)
    except worktree_registry.WorktreeRegistryError as exc:
        entries = []
        registry_error = str(exc)
    proc = git(["worktree", "list", "--porcelain"], cwd=repo_root)
    git_error = None if proc.returncode == 0 else _tail(proc.stderr) or f"rc={proc.returncode}"
    worktrees = parse_worktree_porcelain(proc.stdout or "") if proc.returncode == 0 else []
    return {
        "action": "list",
        "repo_root": str(repo_root),
        "project": str(project_dir),
        "registry_path": str(worktree_registry.registry_path(project_dir)),
        "registry": entries,
        "worktrees": worktrees,
        "count": len(entries),
        "worktree_count": len(worktrees),
        "ok": registry_error is None and git_error is None,
        "error": registry_error or git_error,
    }


def _print_list(result: dict) -> None:
    print(f"[mw worktree list] registry: {result['registry_path']} ({result['count']} entry(ies))")
    for entry in result["registry"]:
        print(
            f"  - {entry['link']} -> {entry['target']}  "
            f"[worktree {entry['worktree']}, {entry['created_at']}, {entry['created_by']}]"
        )
    print(f"[mw worktree list] git worktrees: {result['worktree_count']}")
    for item in result["worktrees"]:
        branch = item["branch"] or ("detached" if item["detached"] else "?")
        print(f"  - {item['path']}  ({branch})")


# ── CLI dispatch ─────────────────────────────────────────────────────────────


def cmd_worktree(args, *, repo_root: pathlib.Path, git: _GIT, npm_hydrate: _NPM_HYDRATE) -> int:
    repo_root = pathlib.Path(repo_root).resolve()
    project = getattr(args, "project", None)
    project_dir = pathlib.Path(project).resolve() if project else repo_root
    json_mode = bool(getattr(args, "json", False))

    def emit(message: str) -> None:
        # In --json mode the human progress goes to stderr so stdout stays a
        # single parseable JSON document.
        print(message, file=sys.stderr) if json_mode else print(message)

    action = getattr(args, "worktree_action", None)
    if action == "rm":
        result = remove_worktree(
            pathlib.Path(args.path),
            repo_root=repo_root,
            project_dir=project_dir,
            git=git,
            log=emit,
        )
        if json_mode:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1
    if action == "add":
        result = add_worktree(
            pathlib.Path(args.path),
            repo_root=repo_root,
            project_dir=project_dir,
            git=git,
            npm_hydrate=npm_hydrate,
            ref=args.ref,
            link_deps=bool(getattr(args, "link_deps", False)),
            dry_run=bool(getattr(args, "dry_run", False)),
            log=emit,
        )
        if json_mode:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1
    if action == "list":
        result = list_worktrees(repo_root=repo_root, project_dir=project_dir, git=git)
        if json_mode:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_list(result)
        return 0 if result["ok"] else 1
    print(f"[mw worktree] Error: unknown action {action!r}", file=sys.stderr)
    return 1
