"""autopilot/effective_config.py — layered effective config (design D-002/D-003).

Resolves the *effective* autopilot configuration from two on-disk layers:

    project  <root>/.agenticdoc/_autopilot/config.json   fail-closed
    machine  ~/.agents/autopilot-defaults.json           fail-soft, two keys only

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
  ``HOME`` -> ``USERPROFILE``, each joined with
  ``/.agents/autopilot-defaults.json``. A missing file yields
  ``machine_path=None`` and creates no directory.

Machine overridability (2026-09-26 revision, user option 1) is limited to
:data:`EFFECTIVE_KEYS` = ``xkey_verify_cmd`` + ``xkey_verify_cwd``, and the
rule is **empty value = undecided**: both canonical writers
(``config.save_config`` and the TS ``saveConfig``) materialize the full key set
into the project file, so "key present wins" would let a materialized empty
``xkey_verify_cmd: []`` permanently shadow the machine layer. A project value
that is either absent or equal to :data:`EMPTY_VALUE` therefore defers to the
machine layer; a non-empty project value wins; two empty/absent layers fall
back to the built-in default. Keys outside ``EFFECTIVE_KEYS`` are never
machine-overridable: their origin is ``project`` when the project file carries
them explicitly and ``default`` otherwise.

The read path is strictly read-only: no file, directory or lock is ever
created (no ``.mw/``, no ``.agenticdoc/``).

Known deviation from design D-002 §4.3 (reported to PM, not worked around
here): the design says a project-level ``null`` must resolve to origin
``default`` without falling back to the machine layer. T-01's
``config.validate_config`` rejects ``null`` for all 13 keys (fail-closed), so
such a file raises :class:`ConfigError` before the merge is reached.
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Mapping

from autopilot import config

# Machine-overridable keys (2026-09-26 revision: narrowed from four to two).
EFFECTIVE_KEYS = (
    "xkey_verify_cmd",
    "xkey_verify_cwd",
)
# "Empty value = undecided": a project value equal to this defers to the
# machine layer. Materializing writers fill exactly these values when unset.
EMPTY_VALUE = {"xkey_verify_cmd": [], "xkey_verify_cwd": ""}
ORIGINS = ("project", "machine", "default")

_MISSING = object()
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


def _project_raw(project_root: pathlib.Path) -> dict:
    """Raw project file data, before default filling.

    ``config.load_config`` merges over the defaults, which erases the
    difference between "absent" and "explicitly set to the default value" —
    needed for the empty-value-means-undecided rule. Called only after
    ``load_config`` validated the file, so parsing here cannot fail-closed
    differently (a missing file yields an empty mapping).
    """
    path = config.config_path(project_root)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


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
    defaults = config.default_config()
    raw = _project_raw(project_root)

    machine_path = machine_config_path(env)
    machine, diagnostics = _load_machine_layer(machine_path)

    origins = {field: "default" for field in config.DEFAULT_CONFIG}
    for field in config.DEFAULT_CONFIG:
        if field not in EFFECTIVE_KEYS:
            # Never machine-overridable: explicit project key -> project, else default.
            if field in raw:
                origins[field] = "project"
            continue
        project_value = raw.get(field, _MISSING)
        machine_value = machine.get(field, _MISSING)
        project_unset = project_value is _MISSING or project_value == EMPTY_VALUE[field]
        machine_unset = (
            machine_value is _MISSING
            or machine_value is None
            or machine_value == EMPTY_VALUE[field]
        )
        if not project_unset:
            values[field] = project_value
            origins[field] = "project"
        elif not machine_unset:
            values[field] = machine_value
            origins[field] = "machine"
        else:
            values[field] = defaults[field]
            origins[field] = "default"

    return EffectiveConfig(
        values=values,
        origins=origins,
        diagnostics=diagnostics,
        machine_path=machine_path,
    )
