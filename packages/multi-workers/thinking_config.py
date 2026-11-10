"""thinking_config.py - ``mw thinking`` CLI semantics (mw-worker-thinking-command W1).

Python is the single authority for show/set/clear of the control project's
``.mw/dispatch.yml`` ``thinking:`` block. ``mw.py`` (and the ``/mw thinking``
window wrapper) only forward argv to :func:`cmd_thinking`; that function takes
``writer(path, text)`` from the caller (``mw._atomic_write_yml``) and owns
argument validation, rendering, and return codes. This module never imports
``mw`` and never writes a file on its own.

Contract::

    cmd_thinking(args, writer) -> 0 (success) | 1 (safe, sanitized failure)

    args.project          control project directory (default ``"."``)
    args.thinking_action  show | set | clear (missing/None -> show)
    args.target           default | coding | review | research | vision |
                          decide_prepare | all (clear only)
    args.level            one of worker_thinking.THINKING_LEVELS (set only)

Safety properties (AC-001..004):
  * only the ``thinking`` top-level key is ever changed; all other mapping
    data (models, fallback_models, rag, ...) is preserved semantically.
  * existing config is strictly validated with the resolver's own public
    ``worker_thinking.validate_thinking`` before a write; invalid YAML, a
    non-mapping root, a broken thinking block (including ``clear all``) and
    read/write/replace failures are refused with a nonzero code.
  * diagnostics are fixed strings: raw YAML text, PyYAML's line context,
    raw values, exception text and tracebacks are never printed.
  * show and no-op clear (including an existing empty roles/thinking block)
    perform zero writes; the writer is called only for a real change, after
    serialization succeeded, so a failed atomic replace leaves the original
    bytes intact.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Callable

import mw_common
import worker_thinking

try:
    import yaml  # PyYAML: implicit dependency shared with mw_common / worker_thinking
except ImportError:  # pragma: no cover - PyYAML is an implicit MW dependency
    yaml = None  # type: ignore[assignment]

Writer = Callable[[pathlib.Path, str], None]

VALID_ACTIONS = ("show", "set", "clear")
SET_TARGETS = ("default",) + worker_thinking.THINKING_ROLES
CLEAR_TARGETS = SET_TARGETS + ("all",)

# Fixed, sanitized diagnostics. Never interpolate config content, exception
# text, or user input into these (PyYAML errors embed original source lines).
_ERR_UNREADABLE = (
    "existing dispatch.yml is unreadable or is not valid YAML "
    "(fix or restore it); no changes written"
)
_ERR_NOT_MAPPING = (
    "existing dispatch.yml must be a YAML mapping at top level; no changes written"
)
_ERR_BAD_THINKING = (
    "existing dispatch.yml has an invalid thinking block; no changes written"
)
_ERR_MUTATE = "dispatch.yml could not be updated; no changes written"
_ERR_SERIALIZE = "dispatch.yml could not be serialized; no changes written"
_ERR_WRITE = "dispatch.yml could not be written atomically; the write was aborted"

_SET_TARGET_HELP = (
    "default, " + ", ".join(worker_thinking.THINKING_ROLES) + " ('main' is not configurable)"
)
_CLEAR_TARGET_HELP = (
    "default, " + ", ".join(worker_thinking.THINKING_ROLES)
    + ", all ('main' is not configurable)"
)
_LEVEL_HELP = ", ".join(worker_thinking.THINKING_LEVELS)

_READ_ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError)
if yaml is not None:
    _READ_ERRORS += (yaml.YAMLError,)


def _error(label: str, message: str) -> None:
    """One fixed stderr line; ``label`` is always a known action or ``thinking``."""
    print(f"[mw thinking {label}] Error: {message}", file=sys.stderr)


def load_config(project_dir: pathlib.Path) -> tuple[dict, str | None]:
    """Strict read + validate -> ``(full_mapping, fixed_error_or_None)``.

    Missing / empty / comment-only files yield ``({}, None)`` (nothing
    configured). A UTF-8 BOM is tolerated. Errors are fixed, sanitized strings;
    the underlying ``yaml.YAMLError`` / ``validate_thinking`` diagnostic is
    deliberately discarded because both can contain raw config values.
    """
    path = mw_common.dispatch_config_path(pathlib.Path(project_dir))
    if not path.exists():
        return {}, None
    if yaml is None:
        return {}, _ERR_UNREADABLE
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = yaml.safe_load(text)
        if data is None:
            # Empty documents and explicit null both construct to None. Only
            # a missing/zero-width YAML node is truly an empty document.
            node = yaml.compose(text, Loader=yaml.SafeLoader)
            if node is not None and node.start_mark.index != node.end_mark.index:
                return {}, _ERR_NOT_MAPPING
            return {}, None
    except _READ_ERRORS:
        return {}, _ERR_UNREADABLE
    if not isinstance(data, dict):
        return {}, _ERR_NOT_MAPPING
    if "thinking" in data and worker_thinking.validate_thinking(data["thinking"], path):
        return {}, _ERR_BAD_THINKING
    return data, None


def mutate(
    data: dict, action: str, target: str, level: str | None
) -> tuple[dict, bool]:
    """Return ``(new_mapping, changed)``; only ``thinking`` is touched.

    ``changed=False`` means no write at all (idempotent set, or clearing a
    field that is not configured). Empty ``roles: {}`` / ``thinking: {}``
    containers are left exactly as they are when the requested field is absent.
    """
    thinking = data.get("thinking")
    if action == "set":
        if isinstance(thinking, dict):
            if target == "default" and thinking.get("default") == level:
                return data, False
            if (
                target != "default"
                and isinstance(thinking.get("roles"), dict)
                and thinking["roles"].get(target) == level
            ):
                return data, False
        # Copy only the mutation path. A whole-document deepcopy preserves
        # aliases between thinking and other top-level fields, so changing
        # that copy could still alter unrelated configuration data.
        new = dict(data)
        block = dict(thinking) if isinstance(thinking, dict) else {}
        new["thinking"] = block
        if target == "default":
            block["default"] = level
        else:
            original_roles = block.get("roles")
            roles = dict(original_roles) if isinstance(original_roles, dict) else {}
            block["roles"] = roles
            roles[target] = level
        return new, True

    # clear: never create the block just to remove something.
    if not isinstance(thinking, dict):
        return data, False
    if target == "all":
        new = dict(data)
        del new["thinking"]
        return new, True
    if target == "default":
        if "default" not in thinking:
            return data, False
        new = dict(data)
        new["thinking"] = dict(thinking)
        del new["thinking"]["default"]
        return new, True
    roles = thinking.get("roles")
    if not isinstance(roles, dict) or target not in roles:
        return data, False
    new = dict(data)
    new["thinking"] = dict(thinking)
    new["thinking"]["roles"] = dict(roles)
    del new["thinking"]["roles"][target]
    return new, True


def _dump(data: dict) -> str:
    """Serialize the full mapping (``off`` stays a quoted string)."""
    return yaml.safe_dump(
        data, allow_unicode=True, default_flow_style=False, sort_keys=True
    )


def _show(project_dir: pathlib.Path, data: dict, path: pathlib.Path) -> int:
    """Print config path, default, and the five roles' effective sources."""
    missing = not path.exists()
    print(
        f"[mw thinking show] config: {path}"
        + (" (missing — nothing configured)" if missing else "")
    )
    thinking = data.get("thinking")
    default = thinking.get("default") if isinstance(thinking, dict) else None
    if default is None:
        print("default: pi native [unset]")
    else:
        print(f"default: {default} [config:default]")
    for role in worker_thinking.THINKING_ROLES:
        level, source, error = worker_thinking.resolve_worker_thinking(project_dir, role)
        if error or source not in ("unset", "config:default", f"config:{role}"):
            _error("show", _ERR_BAD_THINKING)
            return 1
        print(f"{role}: {level if level is not None else 'pi native'} [{source}]")
    return 0


def cmd_thinking(args: argparse.Namespace, writer: Writer) -> int:
    """``mw thinking [show|set|clear]`` implementation. See module docstring.

    Argument validation happens before ANY file read or write. All config or
    filesystem failures return 1 with a fixed diagnostic, never a traceback.
    """
    action = getattr(args, "thinking_action", None) or "show"
    label = action if action in VALID_ACTIONS else "thinking"
    if label == "thinking":
        _error(label, "unknown thinking action (valid: show, set, clear)")
        return 1

    target = getattr(args, "target", None)
    level = getattr(args, "level", None)
    if action == "set":
        if not isinstance(target, str) or target not in SET_TARGETS:
            _error(label, f"unknown or unsupported target (valid: {_SET_TARGET_HELP})")
            return 1
        if not isinstance(level, str) or level not in worker_thinking.THINKING_LEVELS:
            _error(label, f"invalid thinking level (valid: {_LEVEL_HELP})")
            return 1
    elif action == "clear":
        if not isinstance(target, str) or target not in CLEAR_TARGETS:
            _error(label, f"unknown or unsupported target (valid: {_CLEAR_TARGET_HELP})")
            return 1

    try:
        project_dir = pathlib.Path(getattr(args, "project", ".")).resolve()
        path = mw_common.dispatch_config_path(project_dir)
    except (OSError, ValueError, TypeError):
        _error(label, "invalid --project directory")
        return 1

    try:
        data, err = load_config(project_dir)
    except Exception:  # noqa: BLE001 - no traceback / raw config on any read failure
        data, err = {}, _ERR_UNREADABLE
    if err:
        _error(label, err)
        return 1

    if action == "show":
        return _show(project_dir, data, path)

    try:
        new_data, changed = mutate(data, action, target, level)
    except Exception:  # noqa: BLE001 - never write on a failed mutation
        _error(label, _ERR_MUTATE)
        return 1
    if not changed:
        print(f"[mw thinking {action}] nothing to change (no write)")
        return 0

    if yaml is None:
        _error(label, _ERR_UNREADABLE)
        return 1
    try:
        text = _dump(new_data)  # serialize BEFORE the writer can touch the file
    except _READ_ERRORS + (TypeError, AttributeError):
        _error(label, _ERR_SERIALIZE)
        return 1
    try:
        writer(path, text)
    except Exception:  # noqa: BLE001 - atomic writer failure stays a fixed message
        _error(label, _ERR_WRITE)
        return 1

    if action == "set":
        print(f"[mw thinking set] {target} = {level} -> {path}")
    else:
        print(f"[mw thinking clear] {target} -> {path}")
    print(
        "[mw thinking] takes effect for the next worker spawn; "
        "current PM/worker windows are unchanged"
    )
    return 0
