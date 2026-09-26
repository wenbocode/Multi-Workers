"""autopilot/effective_config.py — layered effective config (design D-002/D-003).

Resolves the *effective* autopilot configuration from two on-disk layers:

    project  <root>/.agenticdoc/_autopilot/config.json   fail-closed
    machine  ~/.agents/autopilot-defaults.json           fail-soft, xkey four keys only

and returns a complete 13-key view (:data:`autopilot.config.DEFAULT_CONFIG`
order) together with a per-field ``origin`` in :data:`ORIGINS` and the
machine-layer diagnostics.

Layer semantics (frozen contract for T-05/T-06 consumers):

* Project layer is **fail-closed**: ``config.load_config`` raises
  :class:`autopilot.config.ConfigError` and that error is re-raised verbatim
  *before* any merge, so a machine value can never "rescue" an invalid project
  file.
* Machine layer is **fail-soft, per field**: an unknown key, an out-of-domain
  (not machine-overridable) key, a known key with a wrong type/range, or a
  wholly broken JSON file is reported in :attr:`EffectiveConfig.diagnostics`
  and the offending field/layer is ignored — the layer is never voided
  wholesale (one typo must not poison every project on the machine).
* Machine path resolution (RAG shape, ``mw_common.machine_rag_servers_path``):
  ``MW_AUTOPILOT_FILE`` (whole-file hard override; set-but-missing means the
  layer is empty and ``HOME`` is **not** consulted) -> ``MW_AUTOPILOT_HOME`` ->
  ``HOME`` -> ``USERPROFILE``, each joined with ``/.agents/autopilot-defaults.json``.
  A missing file yields ``machine_path=None`` and creates no directory.

The read path is strictly read-only: no file, directory or lock is ever
created (no ``.mw/``, no ``.agenticdoc/``).

Known deviation from design D-002 §4.3 (reported to PM, not worked around
here): the design says a project-level ``null`` must resolve to origin
``default`` without falling back to the machine layer. T-01's
``config.validate_config`` rejects ``null`` for all 13 keys (fail-closed), so
such a file raises :class:`ConfigError` before the merge is reached. Explicit
project keys (including keys set to their default value) are still tracked via
the raw file so that "project wins over machine" holds for them.
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Mapping

from autopilot import config

EFFECTIVE_KEYS = (
    "xkey_repair",
    "xkey_verify_cmd",
    "xkey_verify_timeout_s",
    "xkey_verify_cwd",
)
ORIGINS = ("project", "machine", "default")

_ENV_FILE = "MW_AUTOPILOT_FILE"
_ENV_HOME = "MW_AUTOPILOT_HOME"
_DEFAULTS_BASENAME = "autopilot-defaults.json"

_VALIDATION_PREFIX = "invalid _autopilot/config.json: "


class EffectiveConfig:
    """Resolved configuration view.

    ``values`` always carries all 13 keys (config.DEFAULT_CONFIG order) and
    ``origins`` maps the same 13 keys to one of ORIGINS. ``diagnostics`` lists
    the fail-soft machine-layer warnings (empty when the layer is absent or
    clean). ``machine_path`` is the resolved machine file or None.
    """

    def __init__(
        self,
        values: dict,
        origins: dict,
        diagnostics: list[str],
        machine_path: pathlib.Path | None,
    ) -> None:
        self.values = values
        self.origins = origins
        self.diagnostics = diagnostics
        self.machine_path = machine_path

    def __repr__(self) -> str:
        return (
            f"EffectiveConfig(values={self.values!r}, origins={self.origins!r}, "
            f"diagnostics={self.diagnostics!r}, machine_path={self.machine_path!r})"
        )


def machine_config_path(env: Mapping[str, str] | None = None) -> pathlib.Path | None:
    """Resolve the machine-level defaults file, or None when the layer is empty.

    ``MW_AUTOPILOT_FILE`` is a whole-file hard override: when set it is the
    only candidate (a missing override does **not** fall back to HOME). The
    directory is never created.
    """
    env = os.environ if env is None else env
    override = (env.get(_ENV_FILE) or "").strip()
    if override:
        path = pathlib.Path(override)
        return path if path.is_file() else None
    for var in (_ENV_HOME, "HOME", "USERPROFILE"):
        home = (env.get(var) or "").strip()
        if not home:
            continue
        path = pathlib.Path(home) / ".agents" / _DEFAULTS_BASENAME
        if path.is_file():
            return path
    return None


def _field_reason(exc: config.ConfigError) -> str:
    message = str(exc)
    if message.startswith(_VALIDATION_PREFIX):
        return message[len(_VALIDATION_PREFIX) :]
    return message


def _load_machine_layer(
    path: pathlib.Path | None,
) -> tuple[dict, list[str]]:
    """Parse the machine layer fail-soft. Returns (accepted fields, diagnostics).

    Only EFFECTIVE_KEYS may be overridden; every rejection is a diagnostic and
    the field is dropped so the lower layer (project or built-in default)
    wins. A broken file empties the layer but keeps the project layer intact.
    """
    diagnostics: list[str] = []
    if path is None:
        return {}, diagnostics
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        diagnostics.append(
            f"{path}: machine layer unreadable ({exc}); layer treated as empty"
        )
        return {}, diagnostics
    if not isinstance(raw, dict):
        diagnostics.append(
            f"{path}: machine layer must be a JSON object, got "
            f"{type(raw).__name__}; layer treated as empty"
        )
        return {}, diagnostics

    machine: dict = {}
    for key, value in raw.items():
        if key not in config.DEFAULT_CONFIG:
            diagnostics.append(f"{path}: unknown key {key!r} (ignored)")
            continue
        if key not in EFFECTIVE_KEYS:
            diagnostics.append(f"{path}: {key!r} is not machine-overridable (ignored)")
            continue
        if value is None:
            continue  # machine null = no-op (design D-002): layer/field untouched
        try:
            config.validate_config({key: value})
        except config.ConfigError as exc:
            diagnostics.append(f"{path}: {key}: {_field_reason(exc)} (field ignored)")
            continue
        machine[key] = value
    return machine, diagnostics


def _project_present_keys(project_root: pathlib.Path) -> set[str]:
    """Keys the project file explicitly carries (not default-filled).

    ``config.load_config`` merges over the defaults, which erases the
    difference between "absent" and "explicitly set to the default value" —
    needed to let the project layer win over the machine layer in both cases.
    """
    path = config.config_path(project_root)
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data) if isinstance(data, dict) else set()


def load_effective(
    project_root: pathlib.Path | str,
    env: Mapping[str, str] | None = None,
) -> EffectiveConfig:
    """Resolve the effective config (see module docstring for semantics).

    Validates the project layer first (fail-closed, ``ConfigError`` propagates
    unchanged), then merges the fail-soft machine layer per field, producing a
    complete 13-key value view, a 13-key origin view and machine diagnostics.
    """
    project_root = pathlib.Path(project_root)
    values = config.load_config(project_root)  # fail-closed, before any merge
    present = _project_present_keys(project_root)

    machine_path = machine_config_path(env)
    machine, diagnostics = _load_machine_layer(machine_path)

    origins = {field: "default" for field in config.DEFAULT_CONFIG}
    for field in config.DEFAULT_CONFIG:
        if field in present:
            origins[field] = "project"
            continue
        if field in machine:
            values[field] = machine[field]
            origins[field] = "machine"

    return EffectiveConfig(
        values=values,
        origins=origins,
        diagnostics=diagnostics,
        machine_path=machine_path,
    )
