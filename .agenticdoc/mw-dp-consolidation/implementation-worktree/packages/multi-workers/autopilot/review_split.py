"""Review-split switch resolution (claim-driven-review-orchestration design 2.1).

Python twin of `packages/coding-agent/src/extensions/agent-team-loop/shared/
review-split.ts` (T-01), which is the authority for these semantics: the same
constants, the same precedence (``MW_REVIEW_SPLIT`` > ``.mw/review-split.json``
> ``"off"``), and the same diagnostic strings, verbatim —

* ``config-invalid-json``  — the file exists but is not JSON
* ``config-invalid-shape`` — the top level is not an object
* ``config-invalid-v:<v>`` — ``v`` is not the number 1 (missing renders as
  ``undefined``, like ``JSON.stringify(undefined)``)
* ``config-invalid-mode:<mode>`` — ``mode`` is not one of the legal values
* ``config-unreadable:<code>`` — the read failed for a reason other than
  "missing file" (Node error codes, e.g. ``EACCES``)

Why this module exists instead of living in ``mw.py``: the conductor (service
process) never imports the CLI module, so the switch was unreadable from the
side that actually drives review dispatch. Under ``autopilot/`` it is a plain
importable seam with no CLI dependency.

Tolerance contract (mirrors P-048 on the TS side): :func:`resolve_review_split`
never throws and never writes — a missing ``.mw`` directory is simply "no
config", an illegal env value acts as unset while its raw text rides along in
``invalid``, and an unusable config file degrades to the default layer. Only
:func:`set_review_split` writes, and it raises ``ValueError`` for an illegal
mode before touching the filesystem (the CLI turns that into exit 2).

Pure read: no ``exists``/``stat`` probes, no directory creation.
"""

from __future__ import annotations

import errno
import json
import os
import pathlib
import time

#: Legal switch values, in escalation order: off < plan < on.
REVIEW_SPLIT_MODES: tuple[str, ...] = ("off", "plan", "on")

#: Modes that actually do something. The `on` tier (dispatch k unit cards +
#: merge) was cancelled with the M1 verdict of
#: `claim-driven-review-orchestration`, so only `off` and `plan` are wired;
#: setting `on` used to persist silently and then behave exactly like `off`.
REVIEW_SPLIT_WIRED_MODES: tuple[str, ...] = ("off", "plan")

#: Default when neither env nor config says anything (off is byte-identical to
#: the behavior before the switch existed).
REVIEW_SPLIT_DEFAULT = "off"

#: Env override (highest precedence).
REVIEW_SPLIT_ENV = "MW_REVIEW_SPLIT"

#: Persisted switch file, relative to the project root: ``{"v":1,"mode":...}``.
REVIEW_SPLIT_CONFIG = ".mw/review-split.json"

#: JSON has no "missing" value; JS renders ``undefined`` for absent keys and
#: the diagnostics above are part of the cross-language contract.
_MISSING = object()

#: ``readFileSync`` failures that mean "no config" rather than "bad config".
_MISSING_CODES = frozenset({"ENOENT", "ENOTDIR", "EISDIR"})


def review_split_config_path(project_dir: str | pathlib.Path) -> pathlib.Path:
    """Path of the persisted switch file for a project root."""
    return pathlib.Path(project_dir) / REVIEW_SPLIT_CONFIG


def as_review_split_mode(value: object) -> str | None:
    """Case-insensitive, whitespace-tolerant mode match; None when illegal."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in REVIEW_SPLIT_MODES else None


def is_review_split_wired(mode: object) -> bool:
    """Does this mode have an implementation behind it?

    `on` is a legal value of the contract but has no implementation (M3 was
    cancelled), so a caller that persists it gets a no-op. Parsing still
    accepts it — an existing config file must stay readable — which is why the
    CLI reports `wired: false` instead of pretending the file is invalid.
    """
    return isinstance(mode, str) and mode.strip().lower() in REVIEW_SPLIT_WIRED_MODES


def _describe(value: object) -> str:
    """Render a rejected JSON value for the ``invalid`` reason (never throws).

    Mirrors the TS ``describe``: ``JSON.stringify`` with compact separators,
    ``undefined`` for an absent key. Non-JSON payloads fall back to ``str``.
    """
    if value is _MISSING:
        return "undefined"
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _reject_constant(token: str) -> object:
    """``json.loads`` hook: reject NaN/Infinity like ``JSON.parse`` does."""
    raise ValueError(f"non-JSON constant {token}")


def _read_config_mode(config_path: pathlib.Path) -> tuple[str | None, str | None]:
    """Read the config file. Returns ``(mode, invalid)``; ``mode=None`` means
    "no usable config" and ``invalid`` says why when the file was rejected.

    Pure read and fail-soft: a missing file/dir yields ``(None, None)``, while
    an unparsable/ill-shaped/wrong-version/illegal-mode file degrades with a
    diagnostic. Invalid UTF-8 bytes decode to U+FFFD (``readFileSync("utf-8")``
    semantics) so they surface as ``config-invalid-json``, not as a crash.
    """
    try:
        raw = config_path.read_bytes().decode("utf-8", "replace")
    except OSError as exc:
        code = errno.errorcode.get(exc.errno) if exc.errno is not None else None
        if isinstance(exc, (FileNotFoundError, NotADirectoryError, IsADirectoryError)):
            return None, None
        # Node reports EISDIR where Python can report EACCES (Windows: opening a
        # directory for read); both mean "the config path is not a file".
        try:
            if config_path.is_dir():
                return None, None
        except OSError:
            pass
        if code is None or code in _MISSING_CODES:
            return None, None
        return None, f"config-unreadable:{code}"
    try:
        payload = json.loads(raw, parse_constant=_reject_constant)
    except ValueError:
        return None, "config-invalid-json"
    if not isinstance(payload, dict):
        return None, "config-invalid-shape"
    # Format version gate: only the number 1 is understood; anything else
    # (missing, string "1", boolean true, future 2) degrades, never guesses.
    version = payload.get("v", _MISSING)
    if isinstance(version, bool) or version != 1:
        return None, f"config-invalid-v:{_describe(version)}"
    mode = as_review_split_mode(payload.get("mode", _MISSING))
    if mode is None:
        return None, f"config-invalid-mode:{_describe(payload.get('mode', _MISSING))}"
    return mode, None


def _state(
    mode: str, source: str, config_path: pathlib.Path, invalid: str | None
) -> dict:
    return {
        "mode": mode,
        "source": source,
        "config_path": str(config_path),
        "invalid": invalid,
    }


def resolve_review_split(
    project_dir: str | pathlib.Path,
    env: dict[str, str | None] | None = None,
) -> dict:
    """Resolve the effective review-split switch for a project root.

    Precedence env > ``.mw/review-split.json`` > :data:`REVIEW_SPLIT_DEFAULT`:
    an illegal env value falls through to the config file (and is still
    reported in ``invalid``), an unusable config file falls through to the
    default. The env's raw value is the more actionable warning (the operator
    set it), so it wins over the config downgrade reason when both are present.

    Returns exactly ``{"mode", "source", "config_path", "invalid"}`` where
    ``invalid`` is ``None`` when nothing was rejected. ``env`` defaults to
    ``os.environ``; a key mapped to ``None`` counts as unset, like a JS
    ``undefined``. Never throws, never writes (defensive fallback included).
    """
    try:
        config_path = review_split_config_path(project_dir)
        environ = os.environ if env is None else env
        invalid: str | None = None
        raw_env = environ.get(REVIEW_SPLIT_ENV)
        if raw_env is not None:
            env_mode = as_review_split_mode(raw_env)
            if env_mode is not None:
                return _state(env_mode, "env", config_path, None)
            # Illegal env value: act as unset (P-048) but keep the raw text for
            # the upper layer's `split:mode-invalid:<v>` warning.
            invalid = raw_env if isinstance(raw_env, str) else str(raw_env)

        config_mode, config_invalid = _read_config_mode(config_path)
        if config_mode is not None:
            return _state(config_mode, "config", config_path, invalid)
        if invalid is None:
            invalid = config_invalid
        return _state(REVIEW_SPLIT_DEFAULT, "default", config_path, invalid)
    except Exception:  # noqa: BLE001 - resolver must never throw (P-048)
        try:
            fallback_path = str(review_split_config_path(project_dir))
        except Exception:  # noqa: BLE001
            fallback_path = ""
        return {
            "mode": REVIEW_SPLIT_DEFAULT,
            "source": "default",
            "config_path": fallback_path,
            "invalid": "config-unreadable:internal",
        }


def set_review_split(project_dir: str | pathlib.Path, mode: str) -> dict:
    """Persist the switch atomically (temp file + ``os.replace``).

    The mode is validated BEFORE anything touches the filesystem, so an illegal
    value raises ``ValueError`` as a pure no-op — not even ``.mw/`` appears.
    A legal-but-unwired mode (``on``) is refused the same way: persisting it
    would be a silent no-op at dispatch time, which is worse than an error.
    Write failures propagate as ``OSError`` after the temp file is cleaned up,
    so the CLI can keep reporting them as exit 1. Returns
    ``{"mode": <normalized>, "config_path": <str>}``.
    """
    normalized = as_review_split_mode(mode)
    if normalized is None:
        raise ValueError(
            f"invalid mode {mode!r}; use {'|'.join(REVIEW_SPLIT_MODES)}"
        )
    if not is_review_split_wired(normalized):
        raise ValueError(
            f"mode {normalized!r} is not wired (only "
            f"{'|'.join(REVIEW_SPLIT_WIRED_MODES)} have an implementation; the "
            "`on` tier was cancelled with the M1 verdict of "
            "`claim-driven-review-orchestration`)"
        )
    config_path = review_split_config_path(project_dir)
    payload = {
        "v": 1,
        "mode": normalized,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp_path = config_path.with_name(config_path.name + ".tmp")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp_path, config_path)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    return {"mode": normalized, "config_path": str(config_path)}
