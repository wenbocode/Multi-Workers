"""autopilot/config.py — _autopilot/config.json read/validate/write (D-110).

The autopilot config lives next to the task state under
``.agenticdoc/_autopilot/config.json`` (human-visible, human-editable; ``.mw/``
keeps only locks and PIDs). Loading is fail-closed: a present-but-invalid file
raises :class:`ConfigError` instead of silently falling back to defaults —
a wrong config must fail loudly, never run quietly on defaults (T-02/AC-025,
D-110). A *missing* file is not an error: it means "autopilot never enabled"
and yields the defaults with zero footprint (no file or directory is created).

Field set and defaults (D-110):

    enabled            bool    false
    paused             bool    false
    poll_interval_sec  int     4    (1..5; AC-019 beat budget caps this at 5)
    max_parallel_keys  int     2    (floor 2)
    round_budget       int     2    (single source for AC-011 test overrides)
    worker_timeout_min int     30
    l2_read_file_cap   int     8
    l2_read_byte_cap   int     65536
    advance_stall_ticks int    5    (1..50; consecutive same-edge advance
                                    failures before the key is marked stalled)
    xkey_repair        bool    false (cross-key red repair channel; AC-008 off
                                    by default so every existing flow is
                                    untouched until a project opts in)
    xkey_verify_cmd    list[str] []  (per-project verification argv, D-007;
                                    no shell, so a list is the contract)
    xkey_verify_timeout_s int  1800 (>=1; conductor subprocess timeout in s)

The mtime cache (:func:`cached_load`) lets ``mw serve`` and the conductor poll
the config every tick without re-reading and re-parsing the file each second.
"""

from __future__ import annotations

import json
import pathlib


class ConfigError(Exception):
    """config.json exists but is invalid. Never a silent default fallback."""


DEFAULT_CONFIG: dict = {
    "enabled": False,
    "paused": False,
    "poll_interval_sec": 4,
    "max_parallel_keys": 2,
    "round_budget": 2,
    "worker_timeout_min": 30,
    "l2_read_file_cap": 8,
    "l2_read_byte_cap": 65536,
    "advance_stall_ticks": 5,
    "xkey_repair": False,
    "xkey_verify_cmd": [],
    "xkey_verify_timeout_s": 1800,
}

# bool must be rejected before the int rules (bool is an int subclass).
_BOOL_FIELDS = ("enabled", "paused", "xkey_repair")
_LIST_FIELDS = ("xkey_verify_cmd",)
_INT_RANGES: dict[str, tuple[int, int | None]] = {
    "poll_interval_sec": (1, 5),
    "max_parallel_keys": (2, None),
    "round_budget": (1, None),
    "worker_timeout_min": (1, None),
    "l2_read_file_cap": (1, None),
    "l2_read_byte_cap": (1, None),
    "advance_stall_ticks": (1, 50),
    "xkey_verify_timeout_s": (1, None),
}

# resolved path -> (mtime_ns, size, config dict); None entry = file absent.
_CACHE: dict[str, tuple[int, int, dict] | None] = {}


def config_path(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".agenticdoc" / "_autopilot" / "config.json"


def default_config() -> dict:
    """Fresh copy of the defaults (callers may mutate freely)."""
    return json.loads(json.dumps(DEFAULT_CONFIG))


def validate_config(cfg: object) -> None:
    """Raise ConfigError naming every offending field; silent when valid."""
    if not isinstance(cfg, dict):
        raise ConfigError("config root must be a JSON object")
    errors: list[str] = []
    unknown = sorted(set(cfg) - set(DEFAULT_CONFIG))
    if unknown:
        errors.append(f"unknown field(s): {', '.join(unknown)}")
    for field in _BOOL_FIELDS:
        if field in cfg and not isinstance(cfg[field], bool):
            errors.append(f"{field}: expected true/false, got {cfg[field]!r}")
    for field in _LIST_FIELDS:
        if field not in cfg:
            continue
        value = cfg[field]
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            errors.append(
                f"{field}: expected a list of non-empty strings, got {value!r}"
            )
    for field, (lo, hi) in _INT_RANGES.items():
        if field not in cfg:
            continue
        value = cfg[field]
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{field}: expected integer, got {value!r}")
            continue
        if value < lo:
            errors.append(f"{field}: must be >= {lo}, got {value}")
        if hi is not None and value > hi:
            errors.append(f"{field}: must be <= {hi}, got {value}")
    if errors:
        raise ConfigError("invalid _autopilot/config.json: " + "; ".join(errors))


def load_config(project_root: pathlib.Path) -> dict:
    """Load config.json. Missing file -> defaults, zero footprint (nothing is
    created). Present file -> parse + validate; invalid raises ConfigError."""
    path = config_path(project_root)
    if not path.exists():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    validate_config(data)
    return data


def save_config(project_root: pathlib.Path, cfg: dict) -> pathlib.Path:
    """Validate, then atomically write config.json (tmp + replace, UTF-8,
    trailing newline). The console enable/disable/pause/resume flow writes
    through this function only."""
    validate_config(cfg)
    path = config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = pathlib.Path(str(path) + ".tmp")
    tmp_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp_path.replace(path)
    _CACHE.pop(str(path.resolve()), None)
    return path


def cached_load(project_root: pathlib.Path) -> dict:
    """:func:`load_config` behind an mtime+size cache for per-tick polls.

    Cache key is the resolved path; entries invalidate on mtime/size change,
    on :func:`save_config`, and via :func:`invalidate_cache` (tests). Returns
    a defensive copy so callers cannot corrupt the cache by mutating the
    result."""
    path = config_path(project_root)
    key = str(path.resolve())
    try:
        st = path.stat()
    except FileNotFoundError:
        if _CACHE.get(key, "unset") is not None:
            _CACHE[key] = None
        return default_config()
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return json.loads(json.dumps(cached[2]))
    cfg = load_config(project_root)
    _CACHE[key] = (st.st_mtime_ns, st.st_size, cfg)
    return json.loads(json.dumps(cfg))


def invalidate_cache() -> None:
    """Forget all cached configs (tests and manual refresh)."""
    _CACHE.clear()
