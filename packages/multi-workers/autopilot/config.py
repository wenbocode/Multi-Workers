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
    xkey_verify_cwd    str     ""   (workspace cwd for xkey verification; "" = auto.
                                    Schema only requires a string; root-name
                                    validity is resolved at parse time)
    auto_gate_mode     str     "off" (off|shadow|live; AC-018 kill switch for
                                    the automatic gate path - off leaves every
                                    existing flow untouched. Project layer only:
                                    deliberately NOT in effective_config
                                    EFFECTIVE_KEYS, so the machine layer cannot
                                    silently turn automation on. Any other value
                                    fails closed like every other field.)
    launcher_max_workers int   8    (1..64; launcher concurrency cap, T-18/D-027.
                                    Bounded by default: an absent value or an
                                    explicit ``None`` must never mean "unbounded"
                                    - IN-3 spawned 66 workers at once that way.)
    dispatch_max_per_scan int  3    (1..64; how many NEW queue rows one dispatch
                                    scan may add before it stops (T-17/D-026).
                                    A quota of rows, not of tasks.)
    queue_alarm_delta   int    50   (10..10000; doctor `queue-burst-shape`
                                    threshold: more than this many non-terminal
                                    rows AND > 90% of the queue non-terminal is
                                    the IN-3 fingerprint (252 rows, 0 terminal).)
    l3_abort_retry_limit int   1   (0..10; T-01/AC-003 dedicated re-roll budget
                                    for G1 aborted rounds - the `l3abort:{key}`
                                    loop, never charged against `l3_limit`.)
    gate_reminder_after_min int 30  (1..1440; T-07/G2 age threshold in minutes
                                    for the first pending-gate reminder. Upper
                                    bound 24 h keeps the active reminder strictly
                                    ahead of doctor's passive 24h/72h text.)
    gate_reminder_max   int    2    (1..2; T-07/G2 cap on reminders for one gate.
                                    Bounded at 2 by design D-007 so a config can
                                    only lower, never raise, AC-005's "at most
                                    two reminders" contract.)

One optional key sits outside :data:`DEFAULT_CONFIG`: ``envelope_fallback``
(bool, default false when absent). It is the T-14 service-layer envelope
escape hatch, validated like every other boolean but deliberately kept out of
the frozen 20-key schema and the TS parity table (read via
:func:`envelope_fallback_enabled`).

:func:`cached_load` is a thin alias of :func:`load_config` plus a JSON
round-trip defensive copy. It no longer caches by mtime/size, so an external
edit of equal byte length is always picked up on the next poll.
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
    "xkey_verify_cwd": "",
    "auto_gate_mode": "off",
    "launcher_max_workers": 8,
    "dispatch_max_per_scan": 3,
    "queue_alarm_delta": 50,
    "l3_abort_retry_limit": 1,
    "gate_reminder_after_min": 30,
    "gate_reminder_max": 2,
}

# bool must be rejected before the int rules (bool is an int subclass).
#
# The T-14 service-layer escape hatch (mw-dispatch-card-gate AC-009/P-10) is a
# validated boolean that is deliberately NOT a member of DEFAULT_CONFIG: the
# frozen 20-key project schema (D-110) and the TS <-> Python parity table stay
# untouched, while a project can still opt in explicitly. It is read by the
# launcher's envelope gate via :func:`envelope_fallback_enabled`.
ENVELOPE_FALLBACK_KEY = "envelope_fallback"
_BOOL_FIELDS = ("enabled", "paused", "xkey_repair", ENVELOPE_FALLBACK_KEY)
_LIST_FIELDS = ("xkey_verify_cmd",)
_STRING_FIELDS = ("xkey_verify_cwd",)
_ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "auto_gate_mode": ("off", "shadow", "live"),
}
_INT_RANGES: dict[str, tuple[int, int | None]] = {
    "poll_interval_sec": (1, 5),
    "max_parallel_keys": (2, None),
    "round_budget": (1, None),
    "worker_timeout_min": (1, None),
    "l2_read_file_cap": (1, None),
    "l2_read_byte_cap": (1, None),
    "advance_stall_ticks": (1, 50),
    "xkey_verify_timeout_s": (1, None),
    "launcher_max_workers": (1, 64),
    "dispatch_max_per_scan": (1, 64),
    "queue_alarm_delta": (10, 10000),
    "l3_abort_retry_limit": (0, 10),
    "gate_reminder_after_min": (1, 1440),
    "gate_reminder_max": (1, 2),
}


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
    unknown = sorted(set(cfg) - set(DEFAULT_CONFIG) - {ENVELOPE_FALLBACK_KEY})
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
    for field in _STRING_FIELDS:
        if field in cfg and not isinstance(cfg[field], str):
            errors.append(f"{field}: expected string, got {cfg[field]!r}")
    for field, allowed in _ENUM_FIELDS.items():
        if field not in cfg:
            continue
        value = cfg[field]
        if not isinstance(value, str) or value not in allowed:
            errors.append(
                f"{field}: expected one of {', '.join(allowed)}, got {value!r}"
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
    created). Present file -> parse + validate the raw data (fail-closed:
    unknown keys, wrong types and out-of-range values still raise), then
    return the raw data itself: a partial file yields exactly the keys it
    actually carries, never a silent default fill.

    Consumers that need the complete 20-key view must use
    :func:`default_config` or :func:`autopilot.effective_config.load_effective`;
    a key a human may have omitted must be read with ``.get(...)``, not by
    subscripting."""
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
    trailing newline, non-ASCII preserved verbatim). The console
    enable/disable/pause/resume flow writes through this function only."""
    validate_config(cfg)
    path = config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = pathlib.Path(str(path) + ".tmp")
    tmp_path.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    tmp_path.replace(path)
    return path


def envelope_fallback_enabled(project_root: pathlib.Path) -> bool:
    """True only when ``envelope_fallback: true`` is explicitly set (T-14).

    The launcher's envelope gate is fail-closed by default; this knob is the
    explicit operator escape hatch that lets the service inject a canonical
    envelope skeleton for a legacy/skewed producer instead of refusing the
    row. Anything other than an explicit ``true`` - an absent file, an absent
    key, a wrong type, an unreadable or invalid file - is False (closed): the
    loader's :class:`ConfigError` never propagates into the poll loop.
    """
    try:
        return load_config(project_root).get(ENVELOPE_FALLBACK_KEY) is True
    except ConfigError:
        return False


def cached_load(project_root: pathlib.Path) -> dict:
    """:func:`load_config` plus a JSON round-trip defensive copy.

    No mtime/size cache: every poll re-reads and re-parses the file, so an
    external edit is always visible (even when byte length is unchanged).
    The round-trip keeps callers from mutating shared state."""
    return json.loads(json.dumps(load_config(project_root)))


def invalidate_cache() -> None:
    """Kept for API compatibility; loading no longer caches anything."""
    return None
