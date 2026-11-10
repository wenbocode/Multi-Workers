"""worker_thinking.py - read-only Worker thinking-level policy (mw-worker-thinking W1).

Resolves the ``--thinking`` level for a newly spawned Worker from the control
project's ``.mw/dispatch.yml`` ``thinking:`` block. This helper is deliberately
standalone: it does not change the shared ``load_dispatch_config`` return shape,
writes no file, caches nothing, performs no network or model-capability checks
(pi clamps levels natively), and adds no dependency beyond the PyYAML already
used by the MW config readers.

Contract (design sec.2)::

    resolve_worker_thinking(project_dir, task_type) -> (level, source, error)

    * missing file / no ``thinking`` block / no effective level
        -> (None, "unset", None)
    * role override wins -> (level, "config:<role>", None)
    * otherwise default  -> (level, "config:default", None)
    * any invalid thinking block, or unreadable / non-mapping dispatch.yml
        -> (None, "invalid", "<path>: <thinking diagnostic>")

Priority is role > default > None. Level values must be exact strings from
``THINKING_LEVELS`` (no case-folding, no whitespace normalization, no
truthiness shortcut). YAML parses bare ``off``/``on``/``yes``/``no`` as
booleans and ``null``/``~`` as None; those are rejected with a quote hint
rather than silently treated as unset, so ``False`` is never mistaken for
"not configured".

Interpretation choices (documented for the reviewer):
  * ``thinking`` present -> MUST be a mapping (card: "thinking exists must be
    a mapping"). A scalar / list / bool / null block is invalid.
  * ``roles`` present -> MUST be a mapping; an empty mapping ``{}`` is
    accepted as "no overrides". A null / list / scalar / bool is invalid.
  * level VALUES (``default`` and each ``roles.<role>``) -> bool/None/other
    types/illegal levels reject the ENTIRE thinking block.
"""
from __future__ import annotations

import pathlib

import mw_common

try:
    import yaml  # PyYAML: implicit dep shared with mw_common / target.yml
except ImportError:  # pragma: no cover - PyYAML is an implicit MW dependency
    yaml = None  # type: ignore[assignment]

# Valid pi thinking levels, in documented order. Strict equality is required.
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")

_THINKING_KEYS = ("default", "roles")


def _level_error(value: object, where: str, path: pathlib.Path) -> str | None:
    """Diagnostic for one ``default`` / ``roles.<role>`` value, else None."""
    if value is None or isinstance(value, bool):
        return (
            f"{path}: thinking.{where} must be a quoted thinking level string "
            "(YAML parses bare off/on/yes/no as booleans and null/~ as None; "
            "quote the value, e.g. \"off\", to use it as a level)"
        )
    if not isinstance(value, str) or value not in THINKING_LEVELS:
        return (
            f"{path}: thinking.{where} has invalid thinking level {value!r} "
            f"(valid: {', '.join(THINKING_LEVELS)})"
        )
    return None


def _validate_thinking(thinking: object, path: pathlib.Path) -> str | None:
    """Validate the whole ``thinking`` block; reject it ENTIRELY on any error.

    Only ``default`` and ``roles`` keys are allowed; ``roles`` maps a dispatch
    role (``mw_common.DISPATCH_ROLES`` minus ``main``) to a level. Any bad
    value, unknown key, or unknown role invalidates the whole block so that no
    illegal value is ever consumed.
    """
    if not isinstance(thinking, dict):
        return f"{path}: thinking must be a mapping (got {type(thinking).__name__})"
    unknown = [str(key) for key in thinking if key not in _THINKING_KEYS]
    if unknown:
        return (
            f"{path}: thinking has unknown key(s) {', '.join(unknown)} "
            f"(valid: {', '.join(_THINKING_KEYS)})"
        )
    if "default" in thinking:
        error = _level_error(thinking["default"], "default", path)
        if error:
            return error
    if "roles" in thinking:
        roles = thinking["roles"]
        if not isinstance(roles, dict):
            return (
                f"{path}: thinking.roles must be a mapping "
                f"(got {type(thinking['roles']).__name__})"
            )
        valid_roles = frozenset(role for role in mw_common.DISPATCH_ROLES if role != "main")
        for role, value in roles.items():
            if role not in valid_roles:
                return (
                    f"{path}: thinking.roles has unknown role {role!r} "
                    f"(valid: {', '.join(sorted(valid_roles))})"
                )
            error = _level_error(value, f"roles.{role}", path)
            if error:
                return error
    return None


def resolve_worker_thinking(
    project_dir: pathlib.Path, task_type: str
) -> tuple[str | None, str, str | None]:
    """Resolve the thinking level for one spawn -> ``(level, source, error)``.

    Reads ``<project_dir>/.mw/dispatch.yml`` on EVERY call (no cache, no writes,
    BOM-tolerant). ``task_type`` is bucketed to a dispatch role via
    ``mw_common.TASK_TYPE_TO_ROLE`` (unknown / empty / non-string -> ``coding``);
    a configured role override beats ``default``; otherwise there is no override.
    Other top-level keys (``models``, ``fallback_models``, ``rag``, ...) are
    irrelevant and never inspected.
    """
    path = pathlib.Path(project_dir) / ".mw" / "dispatch.yml"
    if not path.exists():
        return (None, "unset", None)
    if yaml is None:  # pragma: no cover - dependency guard
        return (None, "invalid", f"{path}: thinking config unreadable (PyYAML not installed)")
    try:
        text = path.read_text(encoding="utf-8-sig")  # strip a UTF-8 BOM if present
        data = yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return (
            None,
            "invalid",
            f"{path}: dispatch.yml unreadable while reading thinking config: {exc}",
        )
    if data is None:  # empty / comment-only file -> nothing configured
        return (None, "unset", None)
    if not isinstance(data, dict):
        return (
            None,
            "invalid",
            f"{path}: dispatch.yml must be a mapping at top level (thinking config)",
        )
    if "thinking" not in data:
        return (None, "unset", None)  # valid config, other top-level keys unaffected

    thinking = data["thinking"]
    error = _validate_thinking(thinking, path)
    if error:
        return (None, "invalid", error)

    roles = thinking.get("roles") or {}
    key = task_type if isinstance(task_type, str) else ""
    role = mw_common.TASK_TYPE_TO_ROLE.get(key, "coding")
    if role in roles:
        return (roles[role], f"config:{role}", None)
    if "default" in thinking:
        return (thinking["default"], "config:default", None)
    return (None, "unset", None)  # empty / roles-only block with no effective level
